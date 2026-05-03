-- =============================================================================
-- metrics_existing_account
-- =============================================================================
-- Computes the standard "metrics zoo" at account_id grain — every existing
-- metric we'd compare AVRI against, in one wide table.
--
-- Columns:
--   account_id, company_name, industry, rep_id
--   tcv_dollars              Total Contract Value (full term, all contracts)
--   arr_dollars              ARR — sum of currently active commit
--   monthly_commit_credits   Total monthly compute credits across active contracts
--   consumed_90d_credits     Sum of consumed credits in last 90 days
--   utilization_90d          consumed / (3 × monthly_commit) — raw rate
--   latest_color             Most recent health_color
--   active_days_30           Count of distinct days with usage in last 30 days
--   naive_chs_score          Gainsight-style weighted blend (0–100)
-- =============================================================================

DECLARE as_of_date DATE DEFAULT DATE('{as_of_date}');

CREATE OR REPLACE TABLE `{project}.{dataset}.metrics_existing_account` AS

WITH

-- Scope filter: same as AVRI — only score accounts with ≥1 active contract
-- See lessons_learned.md #7 and #10.
accounts_in_scope AS (
  SELECT DISTINCT a.*
  FROM `{project}.{dataset}.accounts` a
  JOIN `{project}.{dataset}.contracts` c ON a.account_id = c.account_id
  WHERE c.start_date <= as_of_date AND c.end_date >= as_of_date
),

active_contracts AS (
  -- Sum across all contracts active as of the snapshot date
  -- (handles mid-year expansion: overlapping contracts both contribute)
  SELECT
    account_id,
    SUM(annual_commit_dollars) AS arr_dollars,
    SUM(included_monthly_compute_credits) AS monthly_commit_credits
  FROM `{project}.{dataset}.contracts`
  WHERE start_date <= as_of_date AND end_date >= as_of_date
  GROUP BY account_id
),
all_contracts AS (
  -- TCV = annual commit prorated over the full contract term
  SELECT
    account_id,
    SUM(annual_commit_dollars * DATE_DIFF(end_date, start_date, MONTH) / 12.0) AS tcv_dollars
  FROM `{project}.{dataset}.contracts`
  GROUP BY account_id
),
usage_90d AS (
  SELECT
    account_id,
    SUM(compute_credits_consumed) AS consumed_90d_credits
  FROM `{project}.{dataset}.daily_usage_logs`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 90 DAY) AND as_of_date
  GROUP BY account_id
),
latest_health AS (
  SELECT
    account_id,
    ARRAY_AGG(health_color ORDER BY date DESC LIMIT 1)[OFFSET(0)] AS latest_color
  FROM `{project}.{dataset}.account_health`
  WHERE date <= as_of_date
  GROUP BY account_id
),
active_days AS (
  SELECT
    account_id,
    COUNT(DISTINCT date) AS active_days_30
  FROM `{project}.{dataset}.daily_usage_logs`
  WHERE date BETWEEN DATE_SUB(as_of_date, INTERVAL 30 DAY) AND as_of_date
  GROUP BY account_id
)

SELECT
  a.account_id,
  a.company_name,
  a.industry,
  a.rep_id,

  ROUND(COALESCE(t.tcv_dollars, 0), 0) AS tcv_dollars,
  COALESCE(c.arr_dollars, 0)           AS arr_dollars,

  COALESCE(c.monthly_commit_credits, 0)         AS monthly_commit_credits,
  COALESCE(u.consumed_90d_credits, 0)           AS consumed_90d_credits,
  ROUND(SAFE_DIVIDE(u.consumed_90d_credits, c.monthly_commit_credits * 3.0), 3) AS utilization_90d,

  COALESCE(h.latest_color, 'unknown') AS latest_color,
  COALESCE(d.active_days_30, 0)        AS active_days_30,

  -- Naive Gainsight-style CHS:
  --   40% utilization (capped 0-100)
  --   30% latest health color
  --   20% engagement (active-days-30 / 30)
  --   10% has-active-ARR indicator
  -- Deliberately snapshot-based, no trend, no edge case awareness.
  ROUND(
      0.40 * LEAST(100.0, GREATEST(0.0, COALESCE(SAFE_DIVIDE(u.consumed_90d_credits, c.monthly_commit_credits * 3.0), 0) * 100.0))
    + 0.30 * CASE COALESCE(h.latest_color, 'unknown')
                WHEN 'green' THEN 100.0
                WHEN 'yellow' THEN 50.0
                WHEN 'red' THEN 0.0
                ELSE 0.0
             END
    + 0.20 * LEAST(100.0, COALESCE(d.active_days_30, 0) / 30.0 * 100.0)
    + 0.10 * CASE WHEN c.arr_dollars > 0 THEN 100.0 ELSE 0.0 END,
  1) AS naive_chs_score

FROM accounts_in_scope a
LEFT JOIN active_contracts c ON a.account_id = c.account_id
LEFT JOIN all_contracts    t ON a.account_id = t.account_id
LEFT JOIN usage_90d        u ON a.account_id = u.account_id
LEFT JOIN latest_health    h ON a.account_id = h.account_id
LEFT JOIN active_days      d ON a.account_id = d.account_id;
