"""Reconstruct per-account "facts" from the local parquet files.

This is the local stand-in for what the BigQuery pipeline computes upstream.
The output is the input that ``core.scoring.score_population`` consumes.

In production, BigQuery materializes this fact table (roughly the existing
``avri_account`` table minus the score columns); locally we rebuild it from
parquet so unit tests can run without BQ access.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data_generation" / "output"
AS_OF = pd.Timestamp("2026-04-22")

COLOR_TO_NUM = {"green": 100, "yellow": 50, "red": 0}


def build_facts(as_of: pd.Timestamp = AS_OF) -> pd.DataFrame:
    """Compute per-account facts ready for scoring.

    Note: the local fact builder approximates the v1.3 grace-period logic
    in a simplified way. Production grace evaluation (per-contract usage
    threshold OR age) is implemented in the BigQuery pipeline. Local
    facts treat every account with at least one active contract as
    fully_activated, with a minimal grace heuristic for accounts under 30
    days old.
    """
    accounts  = pd.read_parquet(DATA / "accounts.parquet")
    contracts = pd.read_parquet(DATA / "contracts.parquet")
    usage     = pd.read_parquet(DATA / "daily_usage_logs.parquet")
    health    = pd.read_parquet(DATA / "account_health.parquet")

    contracts["start_date"] = pd.to_datetime(contracts["start_date"])
    contracts["end_date"]   = pd.to_datetime(contracts["end_date"])
    usage["date"]   = pd.to_datetime(usage["date"])
    health["date"]  = pd.to_datetime(health["date"])

    # In-scope: accounts with ≥1 active contract
    active = contracts[(contracts["start_date"] <= as_of) & (contracts["end_date"] >= as_of)]
    arr = active.groupby("account_id").agg(
        arr_dollars=("annual_commit_dollars", "sum"),
        monthly_commit_credits=("included_monthly_compute_credits", "sum"),
        n_active_contracts=("contract_id", "count"),
    ).reset_index()
    in_scope_ids = set(arr["account_id"])

    # Tenure
    earliest = contracts.groupby("account_id")["start_date"].min().reset_index()
    earliest["tenure_days"] = (as_of - earliest["start_date"]).dt.days

    # Filter usage to in-scope and within active contract windows
    u = usage.merge(active[["account_id", "start_date", "end_date"]], on="account_id", how="inner")
    u = u[(u["date"] >= u["start_date"]) & (u["date"] <= u["end_date"])]

    win90 = as_of - pd.Timedelta(days=90)
    win30 = as_of - pd.Timedelta(days=30)
    win365 = as_of - pd.Timedelta(days=365)

    u90  = u[(u["date"] > win90)  & (u["date"] <= as_of)]
    u30  = u[(u["date"] > win30)  & (u["date"] <= as_of)]
    uy   = u[(u["date"] > win365) & (u["date"] <= as_of)]

    consumed_90d   = u90.groupby("account_id")["compute_credits_consumed"].sum().rename("consumed_90d")
    consumed_365d  = uy.groupby("account_id")["compute_credits_consumed"].sum().rename("consumed_365d")
    active_days_90 = u90.groupby("account_id")["date"].nunique().rename("active_days_90")
    active_days_30 = u30.groupby("account_id")["date"].nunique().rename("active_days_30")

    # TH: exponentially-decayed health color over last 90d
    h90 = health[(health["date"] > win90) & (health["date"] <= as_of)].copy()
    h90["score"]    = h90["health_color"].map(COLOR_TO_NUM).fillna(50)
    h90["age_days"] = (as_of - h90["date"]).dt.days
    h90["weight"]   = 0.95 ** h90["age_days"]
    h90["wscore"]   = h90["score"] * h90["weight"]
    th = h90.groupby("account_id").agg(
        th_score=("wscore", "sum"),
        th_w=("weight", "sum"),
    )
    th["th_score"] = (th["th_score"] / th["th_w"]).clip(0, 100)
    th = th[["th_score"]].reset_index()

    # Latest health color (for naive CHS)
    latest = (health.sort_values(["account_id", "date"])
                    .groupby("account_id").tail(1)[["account_id", "health_color"]])

    # Grace heuristic: if the only active contract is < 30 days old AND
    # consumed_90d < 15% of monthly_commit, mark as all_grace. This is a
    # conservative local stand-in for the production logic.
    df = accounts[accounts["account_id"].isin(in_scope_ids)].copy()
    df = df.merge(arr, on="account_id", how="left")
    df = df.merge(earliest[["account_id", "tenure_days"]], on="account_id", how="left")
    df = df.merge(consumed_90d,  on="account_id", how="left").fillna({"consumed_90d":  0})
    df = df.merge(consumed_365d, on="account_id", how="left").fillna({"consumed_365d": 0})
    df = df.merge(active_days_90, on="account_id", how="left").fillna({"active_days_90": 0})
    df = df.merge(active_days_30, on="account_id", how="left").fillna({"active_days_30": 0})
    df = df.merge(th, on="account_id", how="left").fillna({"th_score": 50.0})
    df = df.merge(latest[["account_id", "health_color"]].rename(columns={"health_color": "latest_color"}),
                  on="account_id", how="left").fillna({"latest_color": "yellow"})

    young = df["tenure_days"] < 30
    low_use = df["consumed_90d"] < 0.15 * df["monthly_commit_credits"].fillna(0) * 3
    df["grace_status"] = np.where(young & low_use, "all_grace", "fully_activated")
    df["has_grace_contract"]   = df["grace_status"] == "all_grace"
    df["all_contracts_in_grace"] = df["grace_status"] == "all_grace"

    return df


if __name__ == "__main__":
    facts = build_facts()
    out = Path(__file__).resolve().parent / "facts_local.parquet"
    facts.to_parquet(out, index=False)
    print(f"Wrote {len(facts)} rows to {out}")
    print(facts["grace_status"].value_counts())
