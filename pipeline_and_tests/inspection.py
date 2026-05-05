"""Inductive inspection — find accounts where existing metrics tell the
wrong story and AVRI tells the right one.

Reads from the four materialized tables and produces a markdown report
at /specs/inspection_findings.md (relative to project root).

Run from pipeline_and_tests/:
    python inspection.py

Output:
    Console: distribution summaries + top-N gap accounts
    File:    ../specs/inspection_findings.md
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from datetime import datetime

import pandas as pd
from google.cloud import bigquery

DEFAULT_PROJECT = "panw-gcs-northstar"
DEFAULT_DATASET = "gcs_north_star"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "specs" / "inspection_findings.md"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

Q_DISTRIBUTION = """
SELECT
  avri_color,
  COUNT(*)                         AS n,
  ROUND(AVG(avri_score), 1)        AS avg_avri,
  ROUND(MIN(avri_score), 1)        AS min_avri,
  ROUND(MAX(avri_score), 1)        AS max_avri,
  ROUND(AVG(cr_score), 1)          AS avg_cr,
  ROUND(AVG(um_score), 1)          AS avg_um,
  ROUND(AVG(dm_score), 1)          AS avg_dm,
  ROUND(AVG(th_score), 1)          AS avg_th
FROM `{project}.{dataset}.avri_account`
GROUP BY avri_color
ORDER BY avg_avri DESC
"""

Q_NAIVE_CHS_DISTRIBUTION = """
SELECT
  CASE
    WHEN naive_chs_score >= 75 THEN 'green'
    WHEN naive_chs_score >= 50 THEN 'yellow'
    ELSE 'red'
  END AS naive_color,
  COUNT(*) AS n,
  ROUND(AVG(naive_chs_score), 1) AS avg_score
FROM `{project}.{dataset}.metrics_existing_account`
GROUP BY naive_color
ORDER BY avg_score DESC
"""

Q_TOP_GAP_OVERSCORED = """
-- Accounts where naive CHS rates them HIGHER than AVRI (CHS is being fooled)
-- Filter out cold-start accounts so this view shows the "real shelfware" deck story.
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.tenure_days,
  e.naive_chs_score,
  a.avri_score,
  ROUND(e.naive_chs_score - a.avri_score, 1) AS gap_chs_minus_avri,
  a.cr_score, a.um_score, a.dm_score, a.th_score,
  a.util_pct,
  a.active_days_90,
  a.floor_rule_triggered,
  e.latest_color,
  a.avri_color
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE e.naive_chs_score - a.avri_score > 15
  AND a.cold_start_flag = FALSE
ORDER BY (e.naive_chs_score - a.avri_score) DESC
LIMIT 10
"""

Q_TOP_GAP_UNDERSCORED = """
-- Accounts where AVRI rates them HIGHER than naive CHS (CHS missed the upside)
-- Often: overage accounts that naive CHS treats as "broken"
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  e.naive_chs_score,
  a.avri_score,
  ROUND(a.avri_score - e.naive_chs_score, 1) AS gap_avri_minus_chs,
  a.cr_score, a.um_score, a.dm_score, a.th_score,
  a.util_pct,
  a.capacity_expansion_flag,
  e.latest_color,
  a.avri_color
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE a.avri_score - e.naive_chs_score > 15
ORDER BY (a.avri_score - e.naive_chs_score) DESC
LIMIT 10
"""

Q_SHELFWARE_LIKE = """
-- Likely shelfware: high ARR, near-zero usage
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.util_pct,
  a.active_days_90,
  e.naive_chs_score,
  a.avri_score,
  a.avri_color,
  a.cr_score, a.um_score, a.dm_score, a.th_score
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE a.arr_dollars > 100000
  AND a.active_days_90 <= 5
ORDER BY a.arr_dollars DESC
LIMIT 10
"""

Q_SPIKE_DROP_LIKE = """
-- Likely spike-and-drop: high CR (annualized utilization OK) but low UM
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.util_pct,
  a.momentum_ratio,
  a.cr_score,
  a.um_score,
  e.naive_chs_score,
  a.avri_score,
  a.avri_color
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE a.um_score < 30 AND a.cr_score > 60
ORDER BY (a.cr_score - a.um_score) DESC
LIMIT 10
"""

Q_OVERAGE_REWARDED = """
-- Accounts in the 110-150% utilization band (expansion candidates per AVRI)
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.util_pct,
  a.cr_score,
  a.um_score,
  a.dm_score,
  a.th_score,
  e.naive_chs_score,
  a.avri_score,
  a.avri_color
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE a.capacity_expansion_flag = TRUE
ORDER BY a.util_pct DESC
LIMIT 10
"""

Q_FLOOR_RULE_TRIGGERED = """
-- Accounts where the TH-based floor rule fired
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.cr_score, a.um_score, a.dm_score, a.th_score,
  a.avri_raw,
  a.avri_score,
  e.naive_chs_score,
  a.avri_color,
  e.latest_color
FROM `{project}.{dataset}.avri_account` a
JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
WHERE a.floor_rule_triggered = TRUE
ORDER BY a.avri_raw DESC
LIMIT 10
"""

Q_REGION_VIEW = """
SELECT * FROM `{project}.{dataset}.avri_region`
ORDER BY region_avri_dollar_weighted DESC
"""

Q_GRACE_BREAKDOWN = """
-- v1.3: how many accounts are in grace, how does it break down by tenure
SELECT
  CASE
    WHEN all_contracts_in_grace THEN 'all-grace (onboarding)'
    WHEN has_grace_contract THEN 'mixed (some activated, some grace)'
    ELSE 'fully activated'
  END AS grace_status,
  COUNT(*) AS n,
  ROUND(AVG(arr_dollars), 0) AS avg_arr,
  ROUND(AVG(tenure_days), 0) AS avg_tenure_days,
  ROUND(AVG(grace_contracts), 2) AS avg_grace_contracts
FROM `{project}.{dataset}.avri_account`
GROUP BY grace_status
ORDER BY n DESC
"""

Q_TENURE_COLOR_BREAKDOWN = """
-- AVRI distribution split by tenure bucket. Cold-start accounts (<90 days)
-- legitimately can't be assessed by the momentum-based pillars; their
-- distribution should be treated separately for executive reporting.
SELECT
  CASE
    WHEN tenure_days < 90 THEN 'cold_start (<90d)'
    WHEN tenure_days < 270 THEN 'ramping (90-270d)'
    ELSE 'mature (270d+)'
  END AS tenure_bucket,
  avri_color,
  COUNT(*) AS n,
  ROUND(AVG(avri_score), 1) AS avg_avri,
  ROUND(AVG(arr_dollars), 0) AS avg_arr
FROM `{project}.{dataset}.avri_account`
GROUP BY tenure_bucket, avri_color
ORDER BY tenure_bucket, avg_avri DESC
"""

Q_AT_RISK_RENEWALS = """
-- The single most actionable view for a CSM dashboard.
SELECT
  a.account_id,
  a.industry,
  a.arr_dollars,
  a.days_to_renewal,
  a.tenure_days,
  a.avri_score,
  a.avri_color,
  a.cr_score, a.um_score, a.dm_score, a.th_score,
  a.rep_id
FROM `{project}.{dataset}.avri_account` a
WHERE a.renewal_imminent_flag = TRUE
  AND a.avri_color != 'green'
ORDER BY a.arr_dollars DESC
LIMIT 15
"""

Q_CSM_TOP_BOTTOM = """
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (ORDER BY csm_avri_dollar_weighted DESC) AS rk_top,
    ROW_NUMBER() OVER (ORDER BY csm_avri_dollar_weighted ASC NULLS LAST) AS rk_bot
  FROM `{project}.{dataset}.avri_csm`
)
SELECT 'TOP' AS pos, csm_id, csm_name, region, segment, account_count, book_arr_dollars,
       csm_avri_dollar_weighted, green_count, yellow_count, red_count
FROM ranked WHERE rk_top <= 5
UNION ALL
SELECT 'BOTTOM' AS pos, csm_id, csm_name, region, segment, account_count, book_arr_dollars,
       csm_avri_dollar_weighted, green_count, yellow_count, red_count
FROM ranked WHERE rk_bot <= 5
ORDER BY pos, csm_avri_dollar_weighted DESC
"""


# ---------------------------------------------------------------------------
# v2.0: Realized Value queries
# ---------------------------------------------------------------------------

Q_RV_HEADLINE = """
SELECT
  COUNT(*) AS n_total,
  COUNTIF(avri_score IS NOT NULL) AS n_scored,
  COUNTIF(avri_score IS NULL)     AS n_grace,
  ROUND(SUM(arr_dollars)  / 1e6, 2)        AS total_arr_m,
  ROUND(SUM(rv_dollars)   / 1e6, 2)        AS total_rv_m,
  ROUND((SUM(IF(avri_score IS NOT NULL, arr_dollars, 0)) - SUM(rv_dollars)) / 1e6, 2)
                                            AS total_unrealized_m,
  ROUND(SAFE_DIVIDE(SUM(rv_dollars),
                    SUM(IF(avri_score IS NOT NULL, arr_dollars, 0))), 4)
                                            AS realization_rate
FROM `{project}.{dataset}.avri_account`
"""

Q_RV_PILLAR_DECOMP_GLOBAL = """
SELECT
  ROUND(SUM(unrealized_cr_dollars)    / 1e6, 2) AS unrealized_cr_m,
  ROUND(SUM(unrealized_um_dollars)    / 1e6, 2) AS unrealized_um_m,
  ROUND(SUM(unrealized_dm_dollars)    / 1e6, 2) AS unrealized_dm_m,
  ROUND(SUM(unrealized_th_dollars)    / 1e6, 2) AS unrealized_th_m,
  ROUND(SUM(unrealized_floor_dollars) / 1e6, 2) AS unrealized_floor_m
FROM `{project}.{dataset}.avri_account`
WHERE all_contracts_in_grace = FALSE
"""

Q_RV_BY_REGION = """
SELECT
  region,
  account_count,
  ROUND(book_arr_dollars / 1e6, 2)     AS book_arr_m,
  ROUND(book_rv_dollars  / 1e6, 2)     AS book_rv_m,
  ROUND((scored_arr_dollars - book_rv_dollars) / 1e6, 2) AS unrealized_m,
  ROUND(realization_rate * 100, 1)     AS realization_pct,
  ROUND(unrealized_cr_dollars    / 1e6, 2) AS unr_cr_m,
  ROUND(unrealized_um_dollars    / 1e6, 2) AS unr_um_m,
  ROUND(unrealized_dm_dollars    / 1e6, 2) AS unr_dm_m,
  ROUND(unrealized_th_dollars    / 1e6, 2) AS unr_th_m,
  ROUND(unrealized_floor_dollars / 1e6, 2) AS unr_floor_m
FROM `{project}.{dataset}.avri_region`
ORDER BY book_rv_m DESC
"""

Q_RV_TOP_LANDMINES = """
SELECT
  account_id, industry, rep_id,
  ROUND(arr_dollars,            0) AS arr,
  ROUND(rv_dollars,             0) AS rv,
  ROUND(arr_dollars - rv_dollars, 0) AS unrealized,
  ROUND(avri_score, 1)             AS avri,
  avri_color
FROM `{project}.{dataset}.avri_account`
WHERE avri_score IS NOT NULL AND avri_color != 'green'
ORDER BY (arr_dollars - rv_dollars) DESC
LIMIT 15
"""


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def df_to_md(df: pd.DataFrame, max_rows: int = 10) -> str:
    if df.empty:
        return "_(no rows)_\n"
    return df.head(max_rows).to_markdown(index=False, floatfmt=".1f")


def write_report(
    distribution_df: pd.DataFrame,
    chs_dist_df: pd.DataFrame,
    overscored_df: pd.DataFrame,
    underscored_df: pd.DataFrame,
    shelfware_df: pd.DataFrame,
    spike_drop_df: pd.DataFrame,
    overage_df: pd.DataFrame,
    floor_df: pd.DataFrame,
    region_df: pd.DataFrame,
    csm_df: pd.DataFrame,
    tenure_df: pd.DataFrame,
    at_risk_df: pd.DataFrame,
    grace_df: pd.DataFrame,
    rv_headline_df: pd.DataFrame | None = None,
    rv_pillar_df: pd.DataFrame | None = None,
    rv_region_df: pd.DataFrame | None = None,
    rv_landmines_df: pd.DataFrame | None = None,
):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    parts = []
    parts.append(f"# Inspection findings — AVRI vs existing metrics\n")
    parts.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from BigQuery materialized tables._\n")

    parts.append("## 1. Distribution comparison\n")
    parts.append("**AVRI distribution:**\n")
    parts.append(df_to_md(distribution_df))
    parts.append("\n\n**Naive CHS distribution (same accounts, same data):**\n")
    parts.append(df_to_md(chs_dist_df))

    parts.append("\n\n## 2. Where naive CHS is fooled (CHS > AVRI by 15+)\n")
    parts.append("These are accounts the existing metric thinks are healthy but AVRI flags. "
                 "These are the deck's strongest 'no single metric works' examples.\n")
    parts.append(df_to_md(overscored_df))

    parts.append("\n\n## 3. Where AVRI rewards what naive CHS misses (AVRI > CHS by 15+)\n")
    parts.append("Often expansion candidates (consistent overage). The naive metric treats high "
                 "utilization as broken; AVRI correctly treats it as a positive signal.\n")
    parts.append(df_to_md(underscored_df))

    parts.append("\n\n## 4. Shelfware-like accounts (ARR > $100K, ≤5 active days in 90)\n")
    parts.append("The classic case: paid customers not using the product. ARR-based metrics show "
                 "them as healthy revenue; AVRI correctly scores them red.\n")
    parts.append(df_to_md(shelfware_df))

    parts.append("\n\n## 5. Spike-and-drop pattern (high CR, low UM)\n")
    parts.append("Annual utilization looks acceptable but momentum has collapsed. UM pillar catches it.\n")
    parts.append(df_to_md(spike_drop_df))

    parts.append("\n\n## 6. Consistent overage (110–150% utilization, expansion candidates)\n")
    parts.append("Customers consuming above commit. AVRI rewards this; naive CHS often penalizes.\n")
    parts.append(df_to_md(overage_df))

    parts.append("\n\n## 7. Floor-rule triggered (technical health crisis)\n")
    parts.append("Accounts where TH < 30 forced the AVRI cap. These would be Yellow/Red regardless "
                 "of how good their consumption looks.\n")
    parts.append(df_to_md(floor_df))

    parts.append("\n\n## 8. Region rollup\n")
    parts.append(df_to_md(region_df, max_rows=10))

    parts.append("\n\n## 9. Top & bottom CSMs (dollar-weighted AVRI)\n")
    parts.append(df_to_md(csm_df, max_rows=20))

    parts.append("\n\n## 10. AVRI distribution by tenure bucket\n")
    parts.append("Cold-start accounts (<90 days) legitimately can't be assessed by momentum-based pillars. "
                 "Their distribution should be reported separately from mature accounts. "
                 "If cold_start accounts skew red, that's mostly the level-guard firing on a thin tenure window — "
                 "not a real renewal risk signal.\n")
    parts.append(df_to_md(tenure_df, max_rows=20))

    parts.append("\n\n## 11. At-risk renewals (next 90 days, not green)\n")
    parts.append("The most actionable view for a CSM dashboard — accounts whose renewal is imminent and "
                 "AVRI flags them as Yellow or Red. These are the accounts a CSM should be working *today*.\n")
    parts.append(df_to_md(at_risk_df, max_rows=20))

    parts.append("\n\n## 12. v1.3 Activation Grace Period status\n")
    parts.append("New in v1.3: each contract has a 90-day activation grace window. A contract is excluded "
                 "from CR's denominator until it has either hit 15% of monthly commit in cumulative usage "
                 "OR been signed for 90+ days. Accounts with all contracts in grace are flagged "
                 "`onboarding` with NULL scores; they don't drag the CSM's average down during ramp.\n")
    parts.append(df_to_md(grace_df, max_rows=10))

    if rv_headline_df is not None and not rv_headline_df.empty:
        parts.append("\n\n## 13. v2.0 Realized Value — org headline\n")
        parts.append("RV = ARR × AVRI/100 (linear). Onboarding accounts contribute 0 by definition; "
                     "their ARR is reported separately and not part of the realization-rate denominator. "
                     "The realization rate answers, in one number, the executive question: "
                     "*\"of every dollar booked, how much is being actively realized?\"*\n")
        parts.append(df_to_md(rv_headline_df, max_rows=5))

    if rv_pillar_df is not None and not rv_pillar_df.empty:
        parts.append("\n\n## 14. v2.0 Realized Value — pillar attribution of unrealized $\n")
        parts.append("Unrealized $ decomposes cleanly across the four pillars (and floor-rule "
                     "residual). Each column = `Σ ARR × weight × (100 − pillar_score) / 100`. "
                     "The five contributions sum to total unrealized $ within rounding. This is "
                     "the data behind the lobby's pillar heatmap.\n")
        parts.append(df_to_md(rv_pillar_df, max_rows=5))

    if rv_region_df is not None and not rv_region_df.empty:
        parts.append("\n\n## 15. v2.0 Realized Value — by region\n")
        parts.append("Realization rate, total RV, and pillar-decomposition of unrealized $ at the "
                     "region grain. Drill in the dashboard for CSM and account level.\n")
        parts.append(df_to_md(rv_region_df, max_rows=10))

    if rv_landmines_df is not None and not rv_landmines_df.empty:
        parts.append("\n\n## 16. v2.0 Renewal landmines — top 15 unrealized-$ accounts\n")
        parts.append("Largest single-account contributions to the total unrealized-$ figure. "
                     "These are the operationally important accounts: high ARR, low AVRI, "
                     "biggest dollar weight. The deck's case-card stories are pulled from this list.\n")
        parts.append(df_to_md(rv_landmines_df, max_rows=15))

    parts.append("\n\n## Recommended next steps\n")
    parts.append(textwrap.dedent("""\
        - **Pick 3 deck-story accounts** from sections 4, 5, 6 above. One shelfware,
          one spike-and-drop, one overage. These become the visual narrative on the slide
          titled "No single existing metric handles all four dimensions."
        - **Examine the floor-rule triggered list** for false positives. If any look like
          legitimately healthy accounts, the floor rule's threshold may be too aggressive.
        - **Compare AVRI distribution to naive CHS distribution.** A meaningful difference
          in shape (more red in AVRI than CHS) is the visual proof that AVRI surfaces risk
          existing metrics hide.
        - **Check region rollups against intuition.** If AMER, EMEA, APAC look identical
          on AVRI, the dataset's persona distribution is too uniform across regions.
        """))

    OUTPUT_PATH.write_text("".join(parts))
    print(f"\n✓ Report written to {OUTPUT_PATH.relative_to(OUTPUT_PATH.parent.parent.parent)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    args = parser.parse_args()

    print("=" * 64)
    print("Inductive Inspection — AVRI vs existing metrics")
    print("=" * 64)
    print(f"  Project: {args.project}")
    print(f"  Dataset: {args.dataset}")
    print()

    client = bigquery.Client(project=args.project)
    params = {"project": args.project, "dataset": args.dataset}

    def q(name: str, sql: str) -> pd.DataFrame:
        print(f"  → {name}", end=" ", flush=True)
        df = client.query(sql.format(**params)).to_dataframe()
        print(f"({len(df)} rows)")
        return df

    distribution_df = q("AVRI distribution", Q_DISTRIBUTION)
    chs_dist_df     = q("Naive CHS distribution", Q_NAIVE_CHS_DISTRIBUTION)
    overscored_df   = q("CHS-overscored (CHS > AVRI by 15+)", Q_TOP_GAP_OVERSCORED)
    underscored_df  = q("AVRI-overscored (AVRI > CHS by 15+)", Q_TOP_GAP_UNDERSCORED)
    shelfware_df    = q("Shelfware-like accounts", Q_SHELFWARE_LIKE)
    spike_drop_df   = q("Spike-and-drop pattern", Q_SPIKE_DROP_LIKE)
    overage_df      = q("Consistent overage accounts", Q_OVERAGE_REWARDED)
    floor_df        = q("Floor-rule triggered", Q_FLOOR_RULE_TRIGGERED)
    region_df       = q("Region rollup", Q_REGION_VIEW)
    csm_df          = q("Top/bottom CSMs", Q_CSM_TOP_BOTTOM)
    tenure_df       = q("Tenure bucket × color", Q_TENURE_COLOR_BREAKDOWN)
    at_risk_df      = q("At-risk renewals (next 90d)", Q_AT_RISK_RENEWALS)
    grace_df        = q("v1.3 grace status breakdown", Q_GRACE_BREAKDOWN)
    rv_headline_df  = q("v2.0 RV headline", Q_RV_HEADLINE)
    rv_pillar_df    = q("v2.0 RV pillar attribution", Q_RV_PILLAR_DECOMP_GLOBAL)
    rv_region_df    = q("v2.0 RV by region", Q_RV_BY_REGION)
    rv_landmines_df = q("v2.0 Top renewal landmines", Q_RV_TOP_LANDMINES)

    print()
    print("AVRI distribution:")
    print(distribution_df.to_string(index=False))
    print()
    print("Naive CHS distribution:")
    print(chs_dist_df.to_string(index=False))
    print()
    print(f"Found {len(overscored_df)} accounts where CHS overscores AVRI by 15+ points")
    print(f"Found {len(underscored_df)} accounts where AVRI overscores CHS by 15+ points")
    print(f"Found {len(shelfware_df)} shelfware-like accounts")
    print(f"Found {len(spike_drop_df)} spike-and-drop pattern accounts")
    print(f"Found {len(overage_df)} consistent overage accounts")
    print(f"Found {len(floor_df)} floor-rule triggered accounts")

    write_report(
        distribution_df, chs_dist_df,
        overscored_df, underscored_df,
        shelfware_df, spike_drop_df, overage_df, floor_df,
        region_df, csm_df,
        tenure_df, at_risk_df, grace_df,
        rv_headline_df=rv_headline_df,
        rv_pillar_df=rv_pillar_df,
        rv_region_df=rv_region_df,
        rv_landmines_df=rv_landmines_df,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
