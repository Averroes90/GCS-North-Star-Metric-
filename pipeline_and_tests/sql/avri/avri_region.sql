-- =============================================================================
-- avri_region — Dollar-weighted AVRI rolled up to region
-- =============================================================================

CREATE OR REPLACE TABLE `{project}.{dataset}.avri_region` AS

SELECT
  r.region,

  COUNT(DISTINCT r.csm_id)      AS csm_count,
  COUNT(DISTINCT a.account_id)  AS account_count,
  COUNT(DISTINCT IF(a.avri_score IS NOT NULL, a.account_id, NULL)) AS scored_account_count,
  SUM(a.arr_dollars)             AS book_arr_dollars,

  ROUND(SAFE_DIVIDE(
    SUM(IF(a.avri_score IS NOT NULL, a.avri_score * a.arr_dollars, 0)),
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))
  ), 1) AS region_avri_dollar_weighted,
  ROUND(AVG(a.avri_score), 1) AS region_avri_equal_weighted,

  SUM(IF(a.avri_color = 'green',      1, 0)) AS green_count,
  SUM(IF(a.avri_color = 'yellow',     1, 0)) AS yellow_count,
  SUM(IF(a.avri_color = 'red',        1, 0)) AS red_count,
  SUM(IF(a.avri_color = 'onboarding', 1, 0)) AS onboarding_count,

  SUM(IF(a.capacity_expansion_flag, 1, 0)) AS capacity_expansion_accounts,
  SUM(IF(a.floor_rule_triggered,    1, 0)) AS floor_rule_accounts,

  ROUND(AVG(a.tenure_days), 0) AS avg_tenure_days,
  SUM(IF(a.cold_start_flag, 1, 0)) AS cold_start_accounts,
  SUM(IF(a.renewal_imminent_flag, 1, 0)) AS renewal_imminent_accounts,
  SUM(IF(a.renewal_imminent_flag AND a.avri_color != 'green', 1, 0)) AS at_risk_renewals_90d,

  -- v2.0: Realized Value rollup
  ROUND(SUM(COALESCE(a.rv_dollars, 0)), 2) AS book_rv_dollars,
  ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)), 2) AS scored_arr_dollars,
  ROUND(SAFE_DIVIDE(
    SUM(COALESCE(a.rv_dollars, 0)),
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))
  ), 4) AS realization_rate,
  ROUND(
    SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)) -
    SUM(COALESCE(a.rv_dollars, 0)),
  2) AS unrealized_total_dollars,
  ROUND(SUM(COALESCE(a.unrealized_cr_dollars,    0)), 2) AS unrealized_cr_dollars,
  ROUND(SUM(COALESCE(a.unrealized_um_dollars,    0)), 2) AS unrealized_um_dollars,
  ROUND(SUM(COALESCE(a.unrealized_dm_dollars,    0)), 2) AS unrealized_dm_dollars,
  ROUND(SUM(COALESCE(a.unrealized_th_dollars,    0)), 2) AS unrealized_th_dollars,
  ROUND(SUM(COALESCE(a.unrealized_floor_dollars, 0)), 2) AS unrealized_floor_dollars

FROM `{project}.{dataset}.csm_rep` r
LEFT JOIN `{project}.{dataset}.avri_account` a ON r.csm_id = a.rep_id
GROUP BY r.region
ORDER BY region_avri_dollar_weighted ASC NULLS LAST;
