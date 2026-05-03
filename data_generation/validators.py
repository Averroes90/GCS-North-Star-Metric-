"""Pre-write validation gates. Aborts the run with a clear message if violated.

These are NOT data quality tests for the downstream pipeline (those live in
/pipeline_and_tests/). These are sanity checks that the generator did its job
before we persist the data.
"""

from __future__ import annotations

import pandas as pd

from config import (
    MID_YEAR_EXPANSION_PCT,
    N_ACCOUNTS,
    N_CSM_REPS,
    N_ORPHAN_LOGS,
    N_OUT_OF_WINDOW_LOGS,
    PERSONA_WEIGHTS,
)


def _within(actual: int, target: int, pct: float) -> bool:
    return abs(actual - target) <= max(1, int(target * pct))


def validate_all(reps, accounts, contracts, usage_logs, account_health) -> list[str]:
    """Run all validation gates. Returns a list of human-readable reports.
    Raises AssertionError if any gate fails.
    """
    reports = []

    # 1. Row counts within tolerance
    assert _within(len(reps), N_CSM_REPS, 0.05), \
        f"csm_rep row count {len(reps)} not within ±5% of {N_CSM_REPS}"
    reports.append(f"  csm_rep:           {len(reps):>7,} rows (target {N_CSM_REPS:,})")

    assert _within(len(accounts), N_ACCOUNTS, 0.05), \
        f"accounts row count {len(accounts)} not within ±5% of {N_ACCOUNTS}"
    reports.append(f"  accounts:          {len(accounts):>7,} rows (target {N_ACCOUNTS:,})")

    expected_contracts = N_ACCOUNTS + int(N_ACCOUNTS * MID_YEAR_EXPANSION_PCT)
    assert _within(len(contracts), expected_contracts, 0.05), \
        f"contracts row count {len(contracts)} not within ±5% of {expected_contracts}"
    reports.append(f"  contracts:         {len(contracts):>7,} rows (target ~{expected_contracts:,})")

    reports.append(f"  daily_usage_logs:  {len(usage_logs):>7,} rows")
    reports.append(f"  account_health:    {len(account_health):>7,} rows")

    # 2. Contracts FK integrity (every contract.account_id must exist in accounts)
    bad = set(contracts["account_id"]) - set(accounts["account_id"])
    assert not bad, f"{len(bad)} contracts have account_id not in accounts: e.g. {list(bad)[:3]}"

    # 3. Orphan usage logs are present
    orphan_count = len(usage_logs[~usage_logs["account_id"].isin(accounts["account_id"])])
    assert _within(orphan_count, N_ORPHAN_LOGS, 0.10), \
        f"orphan log count {orphan_count} not near target {N_ORPHAN_LOGS}"
    reports.append(f"  orphan logs:       {orphan_count:>7,} (target {N_ORPHAN_LOGS:,})")

    # 4. Out-of-window logs are present (date before any contract start for that account)
    contracts_min = contracts.groupby("account_id")["start_date"].min().to_dict()
    valid_accts = set(accounts["account_id"])
    out_of_window = 0
    for row in usage_logs.itertuples(index=False):
        if row.account_id in valid_accts:
            min_start = contracts_min.get(row.account_id)
            if min_start is not None and row.date < min_start:
                out_of_window += 1
    assert out_of_window >= int(N_OUT_OF_WINDOW_LOGS * 0.5), \
        f"out-of-window log count {out_of_window} suspiciously low (target {N_OUT_OF_WINDOW_LOGS})"
    reports.append(f"  out-of-window logs:{out_of_window:>7,} (target {N_OUT_OF_WINDOW_LOGS:,})")

    # 5. Persona distribution within ±2pp
    if "_persona" in accounts.columns:
        actual_dist = accounts["_persona"].value_counts(normalize=True).to_dict()
        for persona, target in PERSONA_WEIGHTS.items():
            actual = actual_dist.get(persona, 0.0)
            assert abs(actual - target) <= 0.03, \
                f"persona {persona} dist {actual:.3f} differs from target {target:.3f} by >3pp"
        reports.append("  persona distribution: within ±3pp of all targets ✓")

    # 6. Mid-year expansion accounts have exactly 2 overlapping contracts
    multi = contracts.groupby("account_id").size()
    expansion_accts = multi[multi >= 2].index
    expansion_count = len(expansion_accts)
    expected_exp = int(N_ACCOUNTS * MID_YEAR_EXPANSION_PCT)
    assert _within(expansion_count, expected_exp, 0.10), \
        f"expansion account count {expansion_count} differs from target {expected_exp}"
    reports.append(f"  mid-year expansion accounts: {expansion_count:,} (target {expected_exp:,})")

    # 7. account_health uniqueness per (account_id, date)
    dupes = account_health.duplicated(subset=["account_id", "date"]).sum()
    assert dupes == 0, f"{dupes} duplicate (account_id, date) rows in account_health"

    return reports
