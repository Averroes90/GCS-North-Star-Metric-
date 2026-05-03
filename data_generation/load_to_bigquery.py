"""Load generated Parquet files to BigQuery.

Run from the project's data_generation/ folder:

    python load_to_bigquery.py

Optional flags:
    --project   GCP project ID  (default: panw-gcs-northstar)
    --dataset   BQ dataset name (default: gcs_north_star)
    --location  BQ location     (default: US)

Idempotent — safe to re-run. Each table load uses WRITE_TRUNCATE, so the
table is replaced with the current Parquet contents on every run.

Authentication:
    Run `gcloud auth application-default login` once on this machine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PROJECT = "panw-gcs-northstar"
DEFAULT_DATASET = "gcs_north_star"
DEFAULT_LOCATION = "US"

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ---------------------------------------------------------------------------
# Explicit BigQuery schemas
# ---------------------------------------------------------------------------
# We define schemas explicitly rather than relying on Parquet auto-detection
# so the BQ table types match what the downstream pipeline expects.

SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "csm_rep": [
        bigquery.SchemaField("csm_id",  "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("region",  "STRING", mode="REQUIRED"),
        bigquery.SchemaField("segment", "STRING", mode="REQUIRED"),
    ],
    "accounts": [
        bigquery.SchemaField("account_id",   "STRING", mode="REQUIRED"),
        bigquery.SchemaField("company_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("industry",     "STRING", mode="REQUIRED"),
        bigquery.SchemaField("rep_id",       "STRING", mode="REQUIRED"),
    ],
    "contracts": [
        bigquery.SchemaField("contract_id",                      "STRING", mode="REQUIRED"),
        bigquery.SchemaField("account_id",                       "STRING", mode="REQUIRED"),
        bigquery.SchemaField("start_date",                       "DATE",   mode="REQUIRED"),
        bigquery.SchemaField("end_date",                         "DATE",   mode="REQUIRED"),
        bigquery.SchemaField("annual_commit_dollars",            "INT64",  mode="REQUIRED"),
        bigquery.SchemaField("included_monthly_compute_credits", "INT64",  mode="REQUIRED"),
    ],
    "daily_usage_logs": [
        bigquery.SchemaField("log_id",                   "STRING", mode="REQUIRED"),
        bigquery.SchemaField("account_id",               "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date",                     "DATE",   mode="REQUIRED"),
        bigquery.SchemaField("compute_credits_consumed", "INT64",  mode="REQUIRED"),
    ],
    "account_health": [
        bigquery.SchemaField("account_id",               "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date",                     "DATE",   mode="REQUIRED"),
        bigquery.SchemaField("health_color",             "STRING", mode="REQUIRED"),
        bigquery.SchemaField("compute_credits_consumed", "INT64",  mode="REQUIRED"),
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    """Create the dataset if it doesn't exist."""
    full_id = f"{client.project}.{dataset_id}"
    try:
        client.get_dataset(full_id)
        print(f"  ✓ Dataset {full_id} exists")
    except NotFound:
        ds = bigquery.Dataset(full_id)
        ds.location = location
        client.create_dataset(ds)
        print(f"  ✓ Created dataset {full_id} ({location})")


def load_table(
    client: bigquery.Client,
    dataset_id: str,
    table_name: str,
    parquet_path: Path,
    schema: list[bigquery.SchemaField],
) -> int:
    """Load one Parquet file to a BQ table. Returns row count."""
    table_id = f"{client.project}.{dataset_id}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
    )

    print(f"  Loading {table_name:20s}", end=" ", flush=True)
    with open(parquet_path, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)
    job.result()  # Wait for completion
    table = client.get_table(table_id)
    print(f"→ {table.num_rows:>9,} rows")
    return table.num_rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Load Parquet → BigQuery")
    parser.add_argument("--project",  default=DEFAULT_PROJECT)
    parser.add_argument("--dataset",  default=DEFAULT_DATASET)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    args = parser.parse_args()

    print("=" * 64)
    print("BigQuery Loader — GCS North Star")
    print("=" * 64)
    print(f"  Project:  {args.project}")
    print(f"  Dataset:  {args.dataset}")
    print(f"  Location: {args.location}")
    print(f"  Source:   {OUTPUT_DIR}")
    print()

    # Verify Parquet files exist before contacting BigQuery
    missing = [n for n in SCHEMAS if not (OUTPUT_DIR / f"{n}.parquet").exists()]
    if missing:
        print(f"  ✗ Missing Parquet files: {missing}", file=sys.stderr)
        print(f"     Run `python main.py` first to generate them.", file=sys.stderr)
        return 1

    try:
        client = bigquery.Client(project=args.project)
    except Exception as e:
        print(f"  ✗ Could not create BigQuery client: {e}", file=sys.stderr)
        print(f"     Did you run `gcloud auth application-default login`?", file=sys.stderr)
        return 1

    print("Setting up dataset...")
    ensure_dataset(client, args.dataset, args.location)

    print()
    print("Loading tables...")
    total = 0
    for table_name, schema in SCHEMAS.items():
        path = OUTPUT_DIR / f"{table_name}.parquet"
        rows = load_table(client, args.dataset, table_name, path, schema)
        total += rows

    print()
    print(f"✓ Done. Total rows loaded: {total:,}")
    print(f"  View: https://console.cloud.google.com/bigquery"
          f"?project={args.project}&ws=!1m4!1m3!3m2!1s{args.project}!2s{args.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
