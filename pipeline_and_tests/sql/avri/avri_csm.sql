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
  SUM(a.arr_dollars)            AS book_arr_dollars,

  -- Primary: dollar-weighted by ARR
  ROUND(SAFE_DIVIDE(SUM(a.avri_score * a.arr_dollars), SUM(a.arr_dollars)), 1) AS csm_avri_dollar_weighted,
  -- Secondary: equal-weighted (catches long-tail issues)
  ROUND(AVG(a.avri_score), 1) AS csm_avri_equal_weighted,

  -- RAG breakdown
  SUM(IF(a.avri_color = 'green',  1, 0)) AS green_count,
  SUM(IF(a.avri_color = 'yellow', 1, 0)) AS yellow_count,
  SUM(IF(a.avri_color = 'red',    1, 0)) AS red_count,

  -- Capacity expansion candidates in this book
  SUM(IF(a.capacity_expansion_flag, 1, 0)) AS capacity_expansion_accounts,

  -- Floor-rule triggered accounts (technical health crisis)
  SUM(IF(a.floor_rule_triggered, 1, 0)) AS floor_rule_accounts,

  -- Tenure / renewal context
  ROUND(AVG(a.tenure_days), 0) AS avg_tenure_days,
  SUM(IF(a.cold_start_flag, 1, 0)) AS cold_start_accounts,
  SUM(IF(a.renewal_imminent_flag, 1, 0)) AS renewal_imminent_accounts,
  -- Imminent-renewal accounts that are NOT green: the CSM's actual to-do list
  SUM(IF(a.renewal_imminent_flag AND a.avri_color != 'green', 1, 0)) AS at_risk_renewals_90d

FROM `{project}.{dataset}.csm_rep` r
LEFT JOIN `{project}.{dataset}.avri_account` a ON r.csm_id = a.rep_id
GROUP BY 1, 2, 3, 4
ORDER BY csm_avri_dollar_weighted ASC NULLS LAST;
