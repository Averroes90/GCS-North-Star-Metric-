"""Snapshot the AVRI vs CHS crosstab and sample accounts to a JSON file.

Run from `pipeline_and_tests/`:
    python snapshot_avri_vs_chs.py

Output:
    specs/avri_vs_chs_snapshot.json

Use this to refresh the static "AVRI vs CHS Stories" tab in metrics-explorer.html
after any pipeline change. The JSON includes:
  - the 4×3 (or 3×3) crosstab matrix (counts + ARR per cell)
  - top 5 accounts per off-diagonal cell with their pillar scores and signals
  - a timestamp
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

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "specs" / "avri_vs_chs_snapshot.json"


CROSSTAB_SQL = """
WITH joined AS (
  SELECT
    a.account_id,
    a.avri_color,
    CASE
      WHEN e.naive_chs_score >= 75 THEN 'green'
      WHEN e.naive_chs_score >= 50 THEN 'yellow'
      ELSE 'red'
    END AS chs_color,
    a.arr_dollars
  FROM `{project}.{dataset}.avri_account` a
  JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
)
SELECT
  avri_color,
  chs_color,
  COUNT(*) AS n,
  ROUND(SUM(arr_dollars) / 1e6, 2) AS total_arr_m
FROM joined
GROUP BY avri_color, chs_color
ORDER BY avri_color, chs_color
"""


SAMPLES_SQL = """
WITH joined AS (
  SELECT
    a.*,
    CASE
      WHEN e.naive_chs_score >= 75 THEN 'green'
      WHEN e.naive_chs_score >= 50 THEN 'yellow'
      ELSE 'red'
    END AS chs_color,
    e.naive_chs_score,
    e.utilization_90d AS naive_util,
    e.latest_color    AS chs_latest_color,
    e.active_days_30
  FROM `{project}.{dataset}.avri_account` a
  JOIN `{project}.{dataset}.metrics_existing_account` e USING (account_id)
)
SELECT
  account_id, industry, arr_dollars, tenure_days,
  cr_score, um_score, dm_score, th_score,
  avri_score, avri_color,
  naive_chs_score, chs_color,
  naive_util, chs_latest_color, active_days_30,
  has_grace_contract, floor_rule_triggered
FROM joined
WHERE avri_color != chs_color
ORDER BY arr_dollars DESC
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--samples-per-cell", type=int, default=5)
    args = parser.parse_args()

    print(f"Snapshotting AVRI vs CHS from {args.project}.{args.dataset}...")

    client = bigquery.Client(project=args.project)
    params = {"project": args.project, "dataset": args.dataset}

    # Crosstab
    crosstab_df = client.query(CROSSTAB_SQL.format(**params)).to_dataframe()
    crosstab = []
    for _, r in crosstab_df.iterrows():
        crosstab.append({
            "avri_color": r["avri_color"],
            "chs_color":  r["chs_color"],
            "n":          int(r["n"]),
            "total_arr_m": float(r["total_arr_m"] or 0),
        })

    # Samples per off-diagonal cell
    samples_df = client.query(SAMPLES_SQL.format(**params)).to_dataframe()
    samples_by_cell: dict = {}
    for _, r in samples_df.iterrows():
        key = f"{r['avri_color']}__{r['chs_color']}"
        if key not in samples_by_cell:
            samples_by_cell[key] = []
        if len(samples_by_cell[key]) >= args.samples_per_cell:
            continue
        def f(v):  # nullable float
            return float(v) if pd.notna(v) else None
        def i(v):  # nullable int
            return int(v) if pd.notna(v) else None
        def b(v):  # nullable bool → defaults to False on NA
            return bool(v) if pd.notna(v) else False

        samples_by_cell[key].append({
            "account_id": r["account_id"],
            "industry":   r["industry"],
            "arr_dollars": i(r["arr_dollars"]) or 0,
            "tenure_days": i(r["tenure_days"]),
            "avri_score":  f(r["avri_score"]),
            "avri_color":  r["avri_color"],
            "naive_chs_score": f(r["naive_chs_score"]),
            "chs_color":   r["chs_color"],
            "pillars": {
                "cr": f(r["cr_score"]),
                "um": f(r["um_score"]),
                "dm": f(r["dm_score"]),
                "th": f(r["th_score"]),
            },
            "naive_signals": {
                "naive_util":       f(r["naive_util"]),
                "chs_latest_color": r["chs_latest_color"] if pd.notna(r["chs_latest_color"]) else None,
                "active_days_30":   i(r["active_days_30"]),
            },
            "flags": {
                "has_grace_contract":   b(r["has_grace_contract"]),
                "floor_rule_triggered": b(r["floor_rule_triggered"]),
            },
        })

    snapshot = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "project":      args.project,
        "dataset":      args.dataset,
        "as_of_date":   "2026-04-22",
        "crosstab":     crosstab,
        "samples_by_cell": samples_by_cell,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    # Print summary
    print(f"\n✓ Snapshot written to {OUTPUT_PATH}")
    print(f"\nCrosstab summary:")
    for cell in crosstab:
        marker = " (DIAG)" if cell["avri_color"] == cell["chs_color"] else ""
        print(f"  AVRI {cell['avri_color']:>10s} × CHS {cell['chs_color']:>6s}: "
              f"{cell['n']:>4d} accounts, ${cell['total_arr_m']:>5.1f}M ARR{marker}")

    print(f"\nSample accounts captured per off-diagonal cell:")
    for key, samples in sorted(samples_by_cell.items()):
        avri_c, chs_c = key.split("__")
        print(f"  AVRI {avri_c} × CHS {chs_c}: {len(samples)} samples")

    print(f"\nTo update the static lobby HTML with these examples:")
    print(f"  1. Open specs/avri_vs_chs_snapshot.json")
    print(f"  2. Pick the most narratively interesting accounts from the off-diagonal cells")
    print(f"  3. Update the case-card sections in metrics-explorer.html → 'AVRI vs CHS Stories' tab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
