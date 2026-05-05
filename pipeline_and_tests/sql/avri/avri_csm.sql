-- =============================================================================
-- avri_csm — Dollar-weighted AVRI rolled up to CSM
-- =============================================================================

CREATE OR REPLACE TABLE `{project}.{dataset}.avri_csm` AS

SELECT
  r.csm_id,
  r.name AS csm_name,
  r.region,
  r.segment,

  COUNT(DISTINCT a.account_id) AS account_count,
  -- Scored accounts only (excludes all-grace / onboarding accounts)
  COUNT(DISTINCT IF(a.avri_score IS NOT NULL, a.account_id, NULL)) AS scored_account_count,
  SUM(a.arr_dollars)            AS book_arr_dollars,

  -- Primary: dollar-weighted by ARR (NULL avri_score rows excluded by SAFE_DIVIDE)
  ROUND(SAFE_DIVIDE(
    SUM(IF(a.avri_score IS NOT NULL, a.avri_score * a.arr_dollars, 0)),
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))
  ), 1) AS csm_avri_dollar_weighted,
  -- Secondary: equal-weighted (catches long-tail issues; NULL excluded by AVG)
  ROUND(AVG(a.avri_score), 1) AS csm_avri_equal_weighted,

  -- RAG breakdown
  SUM(IF(a.avri_color = 'green',      1, 0)) AS green_count,
  SUM(IF(a.avri_color = 'yellow',     1, 0)) AS yellow_count,
  SUM(IF(a.avri_color = 'red',        1, 0)) AS red_count,
  SUM(IF(a.avri_color = 'onboarding', 1, 0)) AS onboarding_count,

  -- Capacity expansion candidates in this book
  SUM(IF(a.capacity_expansion_flag, 1, 0)) AS capacity_expansion_accounts,

  -- Floor-rule triggered accounts (technical health crisis)
  SUM(IF(a.floor_rule_triggered, 1, 0)) AS floor_rule_accounts,

  -- Tenure / renewal context
  ROUND(AVG(a.tenure_days), 0) AS avg_tenure_days,
  SUM(IF(a.cold_start_flag, 1, 0)) AS cold_start_accounts,
  SUM(IF(a.renewal_imminent_flag, 1, 0)) AS renewal_imminent_accounts,
  -- Imminent-renewal accounts that are NOT green: the CSM's actual to-do list
  SUM(IF(a.renewal_imminent_flag AND a.avri_color != 'green', 1, 0)) AS at_risk_renewals_90d,

  -- v2.0: Realized Value rollup. RV = Σ(ARR * AVRI/100); onboarding accts contribute 0.
  ROUND(SUM(COALESCE(a.rv_dollars, 0)), 2) AS book_rv_dollars,
  -- ARR base for realization rate excludes in-grace accts (their RV is 0 by definition)
  ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)), 2) AS scored_arr_dollars,
  -- Realization rate = book_rv / scored_arr (ARR excluding grace)
  ROUND(SAFE_DIVIDE(
    SUM(COALESCE(a.rv_dollars, 0)),
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))
  ), 4) AS realization_rate,
  -- Total unrealized $ (= scored_arr − book_rv)
  ROUND(
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)) -
    SUM(COALESCE(a.rv_dollars, 0)),
  2) AS unrealized_total_dollars,
  -- Pillar attribution of unrealized $ — sums match parent at every level
  ROUND(SUM(COALESCE(a.unrealized_cr_dollars,    0)), 2) AS unrealized_cr_dollars,
  ROUND(SUM(COALESCE(a.unrealized_um_dollars,    0)), 2) AS unrealized_um_dollars,
  ROUND(SUM(COALESCE(a.unrealized_dm_dollars,    0)), 2) AS unrealized_dm_dollars,
  ROUND(SUM(COALESCE(a.unrealized_th_dollars,    0)), 2) AS unrealized_th_dollars,
  ROUND(SUM(COALESCE(a.unrealized_floor_dollars, 0)), 2) AS unrealized_floor_dollars

FROM `{project}.{dataset}.csm_rep` r
LEFT JOIN `{project}.{dataset}.avri_account` a ON r.csm_id = a.rep_id
GROUP BY 1, 2, 3, 4
ORDER BY csm_avri_dollar_weighted ASC NULLS LAST;
