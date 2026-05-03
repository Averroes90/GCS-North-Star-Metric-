-- =============================================================================
-- avri_account
-- =============================================================================
-- Computes the Account Value Realization Index per account, with all four
-- pillar sub-scores exposed as columns for diagnostics.
--
-- Pillars (each 0-100):
--   CR  Commit Realization  — piecewise on 90-day utilization
--   UM  Usage Momentum      — 90-day avg / 12-month avg
--   DM  Deployment Maturity — active days last 90 / 90
--   TH  Technical Health    — exponentially decayed health_color (decay 0.95/day)
--
-- Composite:
--   AVRI_raw = 0.30·CR + 0.30·UM + 0.20·DM + 0.20·TH
--   Floor rule: if TH < 30, AVRI = LEAST(50, AVRI_raw)
--
-- RAG:
--   Green ≥ 75, Yellow 50-74, Red < 50
-- =============================================================================

DECLARE as_of_date DATE DEFAULT DATE('{as_of_date}');

CREATE OR REPLACE TABLE `{project}.{dataset}.avri_account` AS

WITH

-- ============ Scope filter ============
-- AVRI is only computed for accounts with at least one ACTIVE contract on
-- the as-of date. Accounts whose contracts have all expired (or haven't yet
-- started) are not currently customers — they should not appear in the
-- metric. See lessons_learned.md #7.
accounts_in_scope AS (
  SELECT DISTINCT a.*
  FROM `{project}.{dataset}.accounts` a
  JOIN `{project}.{dataset}.contracts` c ON a.account_id = c.account_id
  WHERE c.start_date <= as_of_date AND c.end_date >= as_of_date
),

active_commits AS (
  SELECT
    account_id,
    SUM(included_monthly_compute_credits) AS monthly_commit_credits,
    SUM(annual_commit_dollars) AS arr_dollars,
    -- Active-contract date bounds: latest end becomes the renewal horizon
    MAX(end_date) AS latest_active_contract_end
  FROM `{project}.{dataset}.contracts`
  WHERE start_date <= as_of_date AND end_date >= as_of_date
  GROUP BY account_id
),

-- Tenure is measured from the earliest contract this account ever had,
-- regardless of whether it's still active. Captures total customer history.
account_tenure AS (
  SELECT
    account_id,
    MIN(start_date) AS earliest_contract_start_date
  FROM `{project}.{dataset}.contracts`
  GROUP BY account_id
),

-- ============ CR pillar — Commit Realization (piecewise) ============
util_90d AS (
  SELECT
    account_id,
    SUM(compute_credits_consumed) AS consumed_90d
  FROM `{project}.{dataset}.daily_usage_logs`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 90 DAY) AND as_of_date
  GROUP BY account_id
),
cr_calc AS (
  SELECT
    a.account_id,
    SAFE_DIVIDE(u.consumed_90d, ac.monthly_commit_credits * 3.0) AS util_pct
  FROM accounts_in_scope a
  LEFT JOIN util_90d u ON a.account_id = u.account_id
  LEFT JOIN active_commits ac ON a.account_id = ac.account_id
),
cr_pillar AS (
  SELECT
    account_id,
    util_pct,
    CASE
      WHEN util_pct IS NULL THEN 0.0           -- No active commit OR no usage
      WHEN util_pct < 0.50 THEN util_pct * 200 -- 0% → 0, 50% → 100
      WHEN util_pct <= 1.50 THEN 100.0         -- Sweet spot + expansion zone
      ELSE GREATEST(60.0, 100.0 - (util_pct - 1.50) * 50.0)  -- Gentle decay
    END AS cr_score
  FROM cr_calc
),

-- ============ UM pillar — Usage Momentum (90d / 365d) ============
-- Uses SUM/N (not AVG over present rows), so missing days correctly count
-- as zero in both numerator and denominator. Then a LEVEL GUARD: if total
-- annual consumption is less than 5% of annual commit, the account has not
-- meaningfully adopted; momentum is undefined → UM = 0.
-- See lessons_learned.md #9.
daily_totals AS (
  SELECT
    account_id,
    SUM(IF(date BETWEEN DATE_SUB(as_of_date, INTERVAL 90 DAY) AND as_of_date,
           compute_credits_consumed, 0)) AS total_90d,
    SUM(compute_credits_consumed) AS total_365d
  FROM `{project}.{dataset}.daily_usage_logs`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 365 DAY) AND as_of_date
  GROUP BY account_id
),
um_pillar AS (
  SELECT
    t.account_id,
    SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) AS momentum_ratio,
    CASE
      -- Level guard: insufficient annual usage → momentum undefined
      WHEN ac.monthly_commit_credits IS NULL THEN 0.0
      WHEN t.total_365d < ac.monthly_commit_credits * 12 * 0.05 THEN 0.0
      WHEN t.total_365d = 0 THEN 0.0
      -- Standard piecewise momentum scoring
      WHEN SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) >= 1.0 THEN 100.0
      WHEN SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) >= 0.7
        THEN 70.0 + (SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) - 0.7) * 100.0
      WHEN SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) >= 0.3
        THEN 30.0 + (SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) - 0.3) * 100.0
      ELSE SAFE_DIVIDE(t.total_90d / 90.0, t.total_365d / 365.0) * 100.0
    END AS um_score
  FROM daily_totals t
  LEFT JOIN active_commits ac ON t.account_id = ac.account_id
),

-- ============ DM pillar — active-day breadth (last 90 days) ============
dm_pillar AS (
  SELECT
    account_id,
    COUNT(DISTINCT date) AS active_days_90,
    ROUND(COUNT(DISTINCT date) / 90.0 * 100.0, 1) AS dm_score
  FROM `{project}.{dataset}.daily_usage_logs`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 90 DAY) AND as_of_date
  GROUP BY account_id
),

-- ============ TH pillar — exponentially decayed health color ============
th_pillar AS (
  SELECT
    account_id,
    ROUND(
      SAFE_DIVIDE(
        SUM(
          CASE health_color
            WHEN 'green'  THEN 100.0
            WHEN 'yellow' THEN  50.0
            WHEN 'red'    THEN   0.0
            ELSE 0.0
          END
          * POW(0.95, DATE_DIFF(as_of_date, date, DAY))
        ),
        SUM(POW(0.95, DATE_DIFF(as_of_date, date, DAY)))
      ),
    1) AS th_score
  FROM `{project}.{dataset}.account_health`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 90 DAY) AND as_of_date
  GROUP BY account_id
),

-- ============ Combine the pillars ============
combined AS (
  SELECT
    a.account_id,
    a.company_name,
    a.industry,
    a.rep_id,
    COALESCE(ac.arr_dollars, 0)           AS arr_dollars,

    -- Contract context (helps distinguish cold-start from shelfware)
    ten.earliest_contract_start_date,
    ac.latest_active_contract_end,
    DATE_DIFF(as_of_date, ten.earliest_contract_start_date, DAY) AS tenure_days,
    DATE_DIFF(ac.latest_active_contract_end, as_of_date, DAY)   AS days_to_renewal,

    ROUND(COALESCE(cr.util_pct, 0), 3)    AS util_pct,
    ROUND(COALESCE(cr.cr_score, 0), 1)    AS cr_score,
    ROUND(COALESCE(um.momentum_ratio, 0), 3) AS momentum_ratio,
    ROUND(COALESCE(um.um_score, 0), 1)    AS um_score,
    COALESCE(dm.active_days_90, 0)        AS active_days_90,
    COALESCE(dm.dm_score, 0)              AS dm_score,
    COALESCE(th.th_score, 0)              AS th_score
  FROM accounts_in_scope a
  LEFT JOIN active_commits ac ON a.account_id = ac.account_id
  LEFT JOIN account_tenure ten ON a.account_id = ten.account_id
  LEFT JOIN cr_pillar cr      ON a.account_id = cr.account_id
  LEFT JOIN um_pillar um      ON a.account_id = um.account_id
  LEFT JOIN dm_pillar dm      ON a.account_id = dm.account_id
  LEFT JOIN th_pillar th      ON a.account_id = th.account_id
),

-- ============ Composite + floor rule ============
with_avri AS (
  SELECT
    *,
    ROUND(0.30 * cr_score + 0.30 * um_score + 0.20 * dm_score + 0.20 * th_score, 1) AS avri_raw,
    ROUND(
      CASE
        WHEN th_score < 30 THEN LEAST(50.0,
          0.30 * cr_score + 0.30 * um_score + 0.20 * dm_score + 0.20 * th_score)
        ELSE 0.30 * cr_score + 0.30 * um_score + 0.20 * dm_score + 0.20 * th_score
      END,
    1) AS avri_score,
    th_score < 30 AS floor_rule_triggered
  FROM combined
)

SELECT
  *,
  CASE
    WHEN avri_score >= 75 THEN 'green'
    WHEN avri_score >= 50 THEN 'yellow'
    ELSE 'red'
  END AS avri_color,
  -- Capacity warning side-flag: utilization in the 110-150% expansion band
  util_pct >= 1.10 AND util_pct <= 1.50 AS capacity_expansion_flag,
  -- Cold-start flag: account too new for momentum to be meaningful.
  -- Read alongside avri_color when filtering — Red + cold_start = "give it time."
  tenure_days < 90 AS cold_start_flag,
  -- Renewal-imminent flag: standard CSM cue
  days_to_renewal IS NOT NULL AND days_to_renewal <= 90 AS renewal_imminent_flag
FROM with_avri;
