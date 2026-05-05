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

-- v1.3 Activation Grace Period parameters
DECLARE GRACE_USAGE_THRESHOLD FLOAT64 DEFAULT 0.15;  -- 15% of monthly commit
DECLARE GRACE_DAY_TIMEOUT INT64 DEFAULT 90;          -- 90-day fallback

CREATE OR REPLACE TABLE `{project}.{dataset}.avri_account` AS

WITH

-- ============ v1.3: Activation Grace Period ============
-- Each currently-active contract is either "activated" (counts in scoring)
-- or "in grace" (excluded from CR's denominator and from rollup commits).
-- A contract activates when EITHER:
--   Trigger A: cumulative consumption since start_date >= 15% of monthly commit
--   Trigger B: contract age in days >= 90
-- Whichever fires first. See metric_v1.md §4 and lessons_learned.md #7.

contract_consumption AS (
  SELECT
    c.contract_id,
    c.account_id,
    c.start_date,
    c.end_date,
    c.included_monthly_compute_credits,
    c.annual_commit_dollars,
    DATE_DIFF(as_of_date, c.start_date, DAY) AS contract_age_days,
    COALESCE(SUM(u.compute_credits_consumed), 0) AS cum_consumed_since_start
  FROM `{project}.{dataset}.contracts` c
  LEFT JOIN `{project}.{dataset}.daily_usage_logs` u
    ON u.account_id = c.account_id
   AND u.date >= c.start_date
   AND u.date <= as_of_date
  WHERE c.start_date <= as_of_date AND c.end_date >= as_of_date
  GROUP BY
    c.contract_id, c.account_id, c.start_date, c.end_date,
    c.included_monthly_compute_credits, c.annual_commit_dollars
),
contract_status AS (
  SELECT
    *,
    cum_consumed_since_start >= included_monthly_compute_credits * GRACE_USAGE_THRESHOLD AS hit_usage_trigger,
    contract_age_days >= GRACE_DAY_TIMEOUT AS hit_time_trigger,
    (cum_consumed_since_start >= included_monthly_compute_credits * GRACE_USAGE_THRESHOLD
     OR contract_age_days >= GRACE_DAY_TIMEOUT) AS is_activated
  FROM contract_consumption
),
account_grace_status AS (
  SELECT
    account_id,
    COUNT(*) AS total_contracts,
    SUM(IF(is_activated, 1, 0)) AS activated_contracts,
    SUM(IF(NOT is_activated, 1, 0)) AS grace_contracts,
    SUM(IF(NOT is_activated, 1, 0)) > 0 AS has_grace_contract,
    SUM(IF(is_activated, 1, 0)) = 0 AS all_contracts_in_grace
  FROM contract_status
  GROUP BY account_id
),

-- ============ Scope filter ============
-- AVRI is only computed for accounts with at least one ACTIVATED contract.
-- Accounts whose contracts have all expired, haven't started, or are still
-- in grace will appear with NULL scores (or be excluded). See metric_v1.md §1, §4.
accounts_in_scope AS (
  SELECT DISTINCT a.*
  FROM `{project}.{dataset}.accounts` a
  JOIN account_grace_status g ON a.account_id = g.account_id
),

-- Activated contracts only — these drive the scored metrics
active_commits AS (
  SELECT
    account_id,
    SUM(included_monthly_compute_credits) AS monthly_commit_credits,
    SUM(annual_commit_dollars) AS arr_dollars,
    MAX(end_date) AS latest_active_contract_end
  FROM contract_status
  WHERE is_activated = TRUE
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

    -- v1.3 grace period diagnostics
    COALESCE(g.total_contracts, 0)        AS total_contracts,
    COALESCE(g.activated_contracts, 0)    AS activated_contracts,
    COALESCE(g.grace_contracts, 0)        AS grace_contracts,
    COALESCE(g.has_grace_contract, FALSE) AS has_grace_contract,
    COALESCE(g.all_contracts_in_grace, FALSE) AS all_contracts_in_grace,

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
  LEFT JOIN account_grace_status g ON a.account_id = g.account_id
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
  account_id,
  company_name,
  industry,
  rep_id,
  arr_dollars,
  earliest_contract_start_date,
  latest_active_contract_end,
  tenure_days,
  days_to_renewal,
  total_contracts,
  activated_contracts,
  grace_contracts,
  has_grace_contract,
  all_contracts_in_grace,
  -- Pillar inputs / diagnostics: keep visible even for all-grace accounts
  util_pct,
  momentum_ratio,
  active_days_90,
  -- Pillar scores: NULL for all-grace accounts (not yet ready to score)
  IF(all_contracts_in_grace, NULL, cr_score) AS cr_score,
  IF(all_contracts_in_grace, NULL, um_score) AS um_score,
  IF(all_contracts_in_grace, NULL, dm_score) AS dm_score,
  IF(all_contracts_in_grace, NULL, th_score) AS th_score,
  IF(all_contracts_in_grace, NULL, avri_raw)   AS avri_raw,
  IF(all_contracts_in_grace, NULL, avri_score) AS avri_score,
  IF(all_contracts_in_grace, NULL, floor_rule_triggered) AS floor_rule_triggered,
  -- RAG color: Onboarding for all-grace; Green/Yellow/Red otherwise
  CASE
    WHEN all_contracts_in_grace THEN 'onboarding'
    WHEN avri_score >= 75 THEN 'green'
    WHEN avri_score >= 50 THEN 'yellow'
    ELSE 'red'
  END AS avri_color,
  -- v2.0: Realized Value (linear). Onboarding accounts contribute 0.
  -- RV = ARR * AVRI/100. See core/scoring.py and core/config_v1.json.
  IF(all_contracts_in_grace, 0.0,
     ROUND(arr_dollars * avri_score / 100.0, 2)) AS rv_dollars,
  -- v2.0: Pillar attribution of unrealized $ for decomposition views.
  -- Each = ARR * weight * (100 - pillar_score) / 100. Floor residual
  -- captures additional loss when AVRI is capped below the weighted-avg.
  IF(all_contracts_in_grace, 0.0,
     ROUND(arr_dollars * 0.30 * (100 - cr_score) / 100.0, 2)) AS unrealized_cr_dollars,
  IF(all_contracts_in_grace, 0.0,
     ROUND(arr_dollars * 0.30 * (100 - um_score) / 100.0, 2)) AS unrealized_um_dollars,
  IF(all_contracts_in_grace, 0.0,
     ROUND(arr_dollars * 0.20 * (100 - dm_score) / 100.0, 2)) AS unrealized_dm_dollars,
  IF(all_contracts_in_grace, 0.0,
     ROUND(arr_dollars * 0.20 * (100 - th_score) / 100.0, 2)) AS unrealized_th_dollars,
  IF(all_contracts_in_grace, 0.0,
     ROUND(GREATEST(
       0.0,
       arr_dollars * (1 - avri_score / 100.0) - (
         arr_dollars * 0.30 * (100 - cr_score) / 100.0 +
         arr_dollars * 0.30 * (100 - um_score) / 100.0 +
         arr_dollars * 0.20 * (100 - dm_score) / 100.0 +
         arr_dollars * 0.20 * (100 - th_score) / 100.0
       )
     ), 2)) AS unrealized_floor_dollars,
  -- Capacity warning side-flag: utilization in the 110-150% expansion band
  IF(all_contracts_in_grace, FALSE, util_pct >= 1.10 AND util_pct <= 1.50) AS capacity_expansion_flag,
  -- Cold-start flag: account too new for momentum to be meaningful.
  tenure_days < 90 AS cold_start_flag,
  -- Renewal-imminent flag: standard CSM cue
  days_to_renewal IS NOT NULL AND days_to_renewal <= 90 AS renewal_imminent_flag
FROM with_avri;
