"""GCS North Star synthetic data generator — orchestrator.

Run:
    cd data_generation
    python main.py

Output:
    output/csm_rep.parquet
    output/accounts.parquet
    output/contracts.parquet
    output/daily_usage_logs.parquet
    output/account_health.parquet
    output/manifest.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import numpy as np
from faker import Faker

from config import OUTPUT_DIR, SEED
from generate import (
    generate_account_health,
    generate_accounts,
    generate_contracts,
    generate_csm_reps,
    generate_usage_logs,
    inject_orphans,
)
from personas import assign_personas
from validators import validate_all


def main():
    print("=" * 64)
    print("GCS North Star — Synthetic Dataset Generator")
    print("=" * 64)
    print(f"  Seed: {SEED}")
    print(f"  Output dir: {OUTPUT_DIR}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Single RNG; Faker is seeded separately
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)

    t0 = time.time()

    # 1. csm_rep
    print("[1/6] Generating csm_rep...")
    reps = generate_csm_reps(rng, fake)

    # 2. accounts (with internal _segment column for downstream)
    print("[2/6] Generating accounts...")
    accounts = generate_accounts(reps, rng, fake)

    # Persona assignment (internal _persona column)
    accounts["_persona"] = assign_personas(len(accounts), rng)

    # 3. contracts (primary + mid-year expansion overlay)
    print("[3/6] Generating contracts (incl. mid-year expansions)...")
    contracts = generate_contracts(accounts, rng)

    # 4. daily_usage_logs
    print("[4/6] Generating daily_usage_logs (this is the heavy step)...")
    usage_logs = generate_usage_logs(accounts, contracts, rng)

    # 5. account_health (depends on usage_logs for weekly aggregation)
    print("[5/6] Generating account_health...")
    account_health = generate_account_health(accounts, contracts, usage_logs, rng)

    # 6. Inject orphans + out-of-window edge cases
    print("[6/6] Injecting orphan & out-of-window logs...")
    usage_logs = inject_orphans(usage_logs, accounts, contracts, rng)

    # ---- Validation ----
    print()
    print("Running validation gates...")
    reports = validate_all(reps, accounts, contracts, usage_logs, account_health)
    for r in reports:
        print(r)

    # ---- Strip internal columns and write ----
    accounts_clean = accounts.drop(columns=[c for c in ["_persona", "_segment"] if c in accounts.columns])

    # Convert date columns to actual date objects (not datetime). pyarrow
    # writes these as date32 in Parquet, which BigQuery loads cleanly into
    # DATE columns. datetime64[ns] writes as timestamp[ns] (INT64) which
    # mismatches BigQuery's DATE type (INT32 days since epoch).
    import pandas as pd
    for col in ("start_date", "end_date"):
        contracts[col] = pd.to_datetime(contracts[col]).dt.date
    usage_logs["date"] = pd.to_datetime(usage_logs["date"]).dt.date
    account_health["date"] = pd.to_datetime(account_health["date"]).dt.date

    print()
    print("Writing parquet files...")
    reps.to_parquet(OUTPUT_DIR / "csm_rep.parquet", index=False)
    accounts_clean.to_parquet(OUTPUT_DIR / "accounts.parquet", index=False)
    contracts.to_parquet(OUTPUT_DIR / "contracts.parquet", index=False)
    usage_logs.to_parquet(OUTPUT_DIR / "daily_usage_logs.parquet", index=False)
    account_health.to_parquet(OUTPUT_DIR / "account_health.parquet", index=False)

    # ---- Manifest ----
    manifest = {
        "seed": SEED,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "elapsed_seconds": round(time.time() - t0, 2),
        "row_counts": {
            "csm_rep": len(reps),
            "accounts": len(accounts),
            "contracts": len(contracts),
            "daily_usage_logs": len(usage_logs),
            "account_health": len(account_health),
        },
        "files": [
            "csm_rep.parquet",
            "accounts.parquet",
            "contracts.parquet",
            "daily_usage_logs.parquet",
            "account_health.parquet",
        ],
    }
    with open(OUTPUT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print()
    print(f"✓ Done in {manifest['elapsed_seconds']}s")
    print(f"  Files written to {OUTPUT_DIR}/")
    print(f"  See manifest.json for details.")


if __name__ == "__main__":
    main()
