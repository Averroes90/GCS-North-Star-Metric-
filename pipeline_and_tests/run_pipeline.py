"""Metric pipeline orchestrator.

Reads SQL files from sql/ in dependency order and executes them against
BigQuery. Each file uses string templating for {project}, {dataset},
{as_of_date}.

Run from pipeline_and_tests/:
    python run_pipeline.py

Optional flags:
    --project       GCP project ID  (default: panw-gcs-northstar)
    --dataset       BQ dataset name (default: gcs_north_star)
    --as-of-date    Snapshot date for metric calc (default: 2026-04-22)

Requires:
    pip install google-cloud-bigquery
    gcloud auth application-default login
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google.cloud import bigquery

DEFAULT_PROJECT = "panw-gcs-northstar"
DEFAULT_DATASET = "gcs_north_star"
DEFAULT_AS_OF   = "2026-04-22"

SQL_DIR = Path(__file__).resolve().parent / "sql"

# Execution order — downstream files depend on tables created upstream
PIPELINE = [
    ("Existing metrics zoo", "existing_metrics/metrics_existing_account.sql"),
    ("AVRI per account",     "avri/avri_account.sql"),
    ("AVRI per CSM",         "avri/avri_csm.sql"),
    ("AVRI per region",      "avri/avri_region.sql"),
]


def run_sql(client: bigquery.Client, sql_path: Path, params: dict) -> None:
    sql = sql_path.read_text().format(**params)
    job = client.query(sql)
    job.result()
    mb = (job.total_bytes_processed or 0) / 1024 / 1024
    print(f"    ✓ {mb:>7.1f} MB processed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project",     default=DEFAULT_PROJECT)
    parser.add_argument("--dataset",     default=DEFAULT_DATASET)
    parser.add_argument("--as-of-date",  default=DEFAULT_AS_OF)
    args = parser.parse_args()

    print("=" * 64)
    print("Metric Pipeline — GCS North Star")
    print("=" * 64)
    print(f"  Project:    {args.project}")
    print(f"  Dataset:    {args.dataset}")
    print(f"  As-of date: {args.as_of_date}")
    print()

    try:
        client = bigquery.Client(project=args.project)
    except Exception as e:
        print(f"  ✗ Could not create BigQuery client: {e}", file=sys.stderr)
        return 1

    params = {
        "project":      args.project,
        "dataset":      args.dataset,
        "as_of_date":   args.as_of_date,
    }

    for label, sql_file in PIPELINE:
        print(f"  → {label}")
        sql_path = SQL_DIR / sql_file
        if not sql_path.exists():
            print(f"    ✗ Missing SQL file: {sql_path}", file=sys.stderr)
            return 1
        try:
            run_sql(client, sql_path, params)
        except Exception as e:
            print(f"    ✗ FAILED: {e}", file=sys.stderr)
            return 1

    print()
    print("✓ Pipeline complete. Materialized tables:")
    for table in ["metrics_existing_account", "avri_account", "avri_csm", "avri_region"]:
        print(f"    {args.project}.{args.dataset}.{table}")
    print()
    print(f"View in BigQuery Studio:")
    print(f"  https://console.cloud.google.com/bigquery"
          f"?project={args.project}&ws=!1m4!1m3!3m2!1s{args.project}!2s{args.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
