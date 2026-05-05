"""Snapshot pillar-decomposition data for the lobby's Realized Value tab.

Run from `pipeline_and_tests/`:
    python snapshot_pillar_decomposition.py

Output:
    specs/pillar_decomposition_snapshot.json

Use this to refresh the static pillar heatmap and headline in the lobby's
Realized Value tab after any pipeline change. The JSON includes:
  - org-wide RV / ARR / unrealized totals
  - per-region RV with pillar decomposition
  - per-segment RV with pillar decomposition
  - top-15 renewal landmines (largest single-account unrealized $)
  - timestamp
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

DEFAULT_PROJECT = "panw-gcs-northstar"
DEFAULT_DATASET = "gcs_north_star"

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "specs" / "pillar_decomposition_snapshot.json"
)

HEADLINE_SQL = """
SELECT
  COUNT(*) AS n_total,
  COUNTIF(avri_score IS NOT NULL) AS n_scored,
  COUNTIF(avri_score IS NULL)     AS n_grace,
  ROUND(SUM(arr_dollars), 2) AS total_arr,
  ROUND(SUM(IF(avri_score IS NOT NULL, arr_dollars, 0)), 2) AS scored_arr,
  ROUND(SUM(rv_dollars),  2) AS total_rv,
  ROUND(SUM(IF(avri_score IS NOT NULL, arr_dollars, 0)) - SUM(rv_dollars), 2) AS total_unrealized,
  ROUND(SAFE_DIVIDE(SUM(rv_dollars),
                    SUM(IF(avri_score IS NOT NULL, arr_dollars, 0))), 4) AS realization_rate,
  ROUND(SUM(unrealized_cr_dollars),    2) AS unrealized_cr,
  ROUND(SUM(unrealized_um_dollars),    2) AS unrealized_um,
  ROUND(SUM(unrealized_dm_dollars),    2) AS unrealized_dm,
  ROUND(SUM(unrealized_th_dollars),    2) AS unrealized_th,
  ROUND(SUM(unrealized_floor_dollars), 2) AS unrealized_floor
FROM `{project}.{dataset}.avri_account`
"""

REGION_SQL = """
SELECT
  region, account_count,
  ROUND(book_arr_dollars, 2)   AS book_arr,
  ROUND(book_rv_dollars, 2)    AS book_rv,
  ROUND(scored_arr_dollars, 2) AS scored_arr,
  ROUND(unrealized_total_dollars, 2) AS unrealized_total,
  ROUND(realization_rate, 4) AS realization_rate,
  ROUND(unrealized_cr_dollars,    2) AS unrealized_cr,
  ROUND(unrealized_um_dollars,    2) AS unrealized_um,
  ROUND(unrealized_dm_dollars,    2) AS unrealized_dm,
  ROUND(unrealized_th_dollars,    2) AS unrealized_th,
  ROUND(unrealized_floor_dollars, 2) AS unrealized_floor
FROM `{project}.{dataset}.avri_region`
ORDER BY book_rv DESC
"""

SEGMENT_SQL = """
SELECT
  r.segment,
  COUNT(DISTINCT a.account_id)            AS account_count,
  ROUND(SUM(a.arr_dollars), 2)            AS book_arr,
  ROUND(SUM(a.rv_dollars), 2)             AS book_rv,
  ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)), 2) AS scored_arr,
  ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))
        - SUM(a.rv_dollars), 2)           AS unrealized_total,
  ROUND(SAFE_DIVIDE(SUM(a.rv_dollars),
        SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))), 4) AS realization_rate,
  ROUND(SUM(a.unrealized_cr_dollars),    2) AS unrealized_cr,
  ROUND(SUM(a.unrealized_um_dollars),    2) AS unrealized_um,
  ROUND(SUM(a.unrealized_dm_dollars),    2) AS unrealized_dm,
  ROUND(SUM(a.unrealized_th_dollars),    2) AS unrealized_th,
  ROUND(SUM(a.unrealized_floor_dollars), 2) AS unrealized_floor
FROM `{project}.{dataset}.csm_rep` r
LEFT JOIN `{project}.{dataset}.avri_account` a ON r.csm_id = a.rep_id
GROUP BY r.segment
ORDER BY book_rv DESC
"""

LANDMINES_SQL = """
SELECT
  account_id, industry, rep_id,
  ROUND(arr_dollars, 0)            AS arr_dollars,
  ROUND(rv_dollars, 0)             AS rv_dollars,
  ROUND(arr_dollars - rv_dollars, 0) AS unrealized,
  ROUND(avri_score, 1)             AS avri_score,
  avri_color, floor_rule_triggered
FROM `{project}.{dataset}.avri_account`
WHERE avri_score IS NOT NULL AND avri_color != 'green'
ORDER BY (arr_dollars - rv_dollars) DESC
LIMIT 15
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    args = parser.parse_args()

    client = bigquery.Client(project=args.project)
    params = {"project": args.project, "dataset": args.dataset}

    print(f"Snapshotting RV pillar decomposition from {args.project}.{args.dataset}...")

    headline = client.query(HEADLINE_SQL.format(**params)).to_dataframe().iloc[0].to_dict()
    region = client.query(REGION_SQL.format(**params)).to_dataframe().to_dict("records")
    segment = client.query(SEGMENT_SQL.format(**params)).to_dataframe().to_dict("records")
    landmines = client.query(LANDMINES_SQL.format(**params)).to_dataframe().to_dict("records")

    snapshot = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "config_version": "v2.0",
        "rv_formula": "linear",
        "as_of_date": "2026-04-22",
        "headline": {k: (float(v) if pd.notna(v) else None) for k, v in headline.items()},
        "by_region": region,
        "by_segment": segment,
        "top_landmines": landmines,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

    print(f"\n✓ Snapshot written to {OUTPUT_PATH}")
    print(f"  Total ARR:     ${headline['total_arr']/1e6:.1f}M")
    print(f"  Total RV:      ${headline['total_rv']/1e6:.1f}M")
    print(f"  Realization:   {headline['realization_rate']*100:.1f}%")
    print(f"  Unrealized by pillar:")
    for k in ["cr", "um", "dm", "th", "floor"]:
        v = headline[f"unrealized_{k}"]
        print(f"    {k:>5s}: ${v/1e6:.1f}M")
    return 0


if __name__ == "__main__":
    sys.exit(main())
