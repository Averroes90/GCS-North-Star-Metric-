"""
core.scoring — single source of truth for AVRI and RV computation.

Both the BigQuery pipeline (via SQL) and the Streamlit dashboard (via direct
import) compute scores from the same parameter definitions in
``core/config_v1.json``. This module is the Python implementation;
``pipeline_and_tests/sql/avri/avri_account.sql`` is the SQL implementation,
and ``test_scoring.py`` snapshot-tests them against each other to prevent
drift.

Inputs (per-account "facts"):
    arr_dollars                 sum of active commits ARR
    monthly_commit_credits      sum across active contracts
    consumed_90d                sum of credits consumed in trailing 90d
    consumed_365d               sum of credits consumed in trailing 365d
    active_days_90              count of distinct days with usage in 90d
    th_score                    pre-computed exponentially-decayed health
                                color score (0-100). Pre-aggregation lives
                                in SQL because of the date-window join cost.
    grace_status                'fully_activated' | 'all_grace' | 'mixed'
    has_grace_contract          bool

Outputs (per-account):
    cr_score, um_score, dm_score, th_score (passthrough), avri_raw,
    avri_score, avri_color, floor_rule_triggered, rv_dollars,
    plus pillar-level unrealized $ contributions for decomposition.

All-grace ("onboarding") accounts get NULL scores and are excluded from
RV totals.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# =============================================================================
# Config loading
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config_v1.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the calibration config. Defaults to bundled config_v1.json."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p) as f:
        return json.load(f)


def validate_config(config: dict[str, Any]) -> None:
    """Sanity-check the config. Raises on structural violations."""
    weights = config["avri"]["weights"]
    total = sum(v for k, v in weights.items() if not k.startswith("_"))
    if not abs(total - 1.0) < 1e-6:
        raise ValueError(f"AVRI weights must sum to 1.0; got {total}")
    if config["rv_formula"]["type"] not in {"linear", "quadratic"}:
        raise ValueError(f"Unsupported rv_formula.type: {config['rv_formula']['type']}")


# =============================================================================
# Piecewise curve evaluator
# =============================================================================

def piecewise_score(value: float, curve: list[dict]) -> float:
    """Evaluate a piecewise-linear curve from the config.

    Each curve segment specifies the upper bound (``util_le`` or ``ratio_le``,
    null for "infinity") and either a flat ``score`` or a ``score_max``
    interpolated linearly from the previous segment's endpoint.

    Returns a score in [0, 100].
    """
    if pd.isna(value):
        return 0.0
    prev_bound = 0.0
    prev_score = 0.0
    for seg in curve:
        bound_key = "util_le" if "util_le" in seg else "ratio_le"
        upper = seg.get(bound_key)
        if upper is None:
            upper = float("inf")
        if value <= upper:
            if "score" in seg:
                return float(seg["score"])
            # interpolate from prev_score to score_max linearly
            score_max = float(seg["score_max"])
            if seg.get("interpolation") == "linear":
                if upper == prev_bound:
                    return score_max
                t = (value - prev_bound) / (upper - prev_bound)
                return prev_score + t * (score_max - prev_score)
            return score_max
        # advance prev pointers
        prev_bound = upper if upper != float("inf") else prev_bound
        prev_score = float(seg.get("score", seg.get("score_max", prev_score)))
    return prev_score


# =============================================================================
# Pillar computations
# =============================================================================

def compute_cr_score(util_pct: float, config: dict) -> float:
    return piecewise_score(util_pct, config["cr_pillar"]["util_curve"])


def compute_um_score(
    consumed_90d: float,
    consumed_365d: float,
    monthly_commit: float,
    config: dict,
) -> float:
    cfg = config["um_pillar"]
    annual_floor = cfg["level_guard"]["annual_pct_threshold"] * 12.0 * monthly_commit
    if consumed_365d < annual_floor:
        return 0.0
    avg_90d  = consumed_90d / 90.0
    avg_365d = consumed_365d / 365.0
    if avg_365d <= 0:
        return 0.0
    ratio = avg_90d / avg_365d
    return piecewise_score(ratio, cfg["ratio_curve"])


def compute_dm_score(active_days_90: float, config: dict) -> float:
    window = config["dm_pillar"]["window_days"]
    return float(np.clip(active_days_90 / window * 100, 0, 100))


# th_score is a passthrough — exponentially-decayed in SQL upstream (or
# precomputed in pandas before calling). Kept here for symmetry of API.
def compute_th_score(decayed_health_score: float, config: dict) -> float:
    return float(np.clip(decayed_health_score, 0, 100))


# =============================================================================
# AVRI composite (with floor rule)
# =============================================================================

def compute_avri(
    cr: float,
    um: float,
    dm: float,
    th: float,
    config: dict,
) -> tuple[float, float, bool]:
    """Return (avri_raw, avri_score, floor_rule_triggered)."""
    w = config["avri"]["weights"]
    raw = w["cr"]*cr + w["um"]*um + w["dm"]*dm + w["th"]*th
    floor = config["avri"]["floor_rule"]
    triggered = th < floor["th_threshold"]
    score = min(raw, floor["avri_cap"]) if triggered else raw
    return raw, score, triggered


def avri_color_for(avri_score: float | None, config: dict) -> str:
    if avri_score is None or pd.isna(avri_score):
        return "onboarding"
    t = config["avri"]["color_thresholds"]
    if avri_score >= t["green"]:
        return "green"
    if avri_score >= t["yellow"]:
        return "yellow"
    return "red"


# =============================================================================
# Realized Value (RV) and pillar-attribution decomposition
# =============================================================================

def compute_rv(arr_dollars: float, avri_score: float | None, config: dict) -> float:
    """Linear v1: RV = ARR * AVRI/100. Onboarding accts (NULL AVRI) → 0."""
    if avri_score is None or pd.isna(avri_score):
        return 0.0
    rv_cfg = config["rv_formula"]
    base = avri_score / 100.0
    if rv_cfg["type"] == "linear":
        factor = base ** rv_cfg.get("exponent", 1.0)
    elif rv_cfg["type"] == "quadratic":
        factor = base ** 2
    else:
        factor = base
    return float(arr_dollars * factor)


def compute_pillar_decomposition(
    arr_dollars: float,
    cr: float, um: float, dm: float, th: float,
    avri_score: float | None,
    floor_rule_triggered: bool,
    config: dict,
) -> dict[str, float]:
    """Attribute unrealized $ to each pillar (and floor rule).

    Under linear RV:
        Unrealized = ARR - RV = ARR * (1 - AVRI/100)
                   = ARR * Σ_pillar (weight * (100 - pillar) / 100)   [no floor]

    The floor rule introduces extra penalty when fired; that residual is
    attributed to a separate ``unrealized_floor`` column. The five
    contributions sum to total unrealized $ within rounding tolerance.
    """
    if avri_score is None or pd.isna(avri_score):
        return {
            "unrealized_cr": 0.0,
            "unrealized_um": 0.0,
            "unrealized_dm": 0.0,
            "unrealized_th": 0.0,
            "unrealized_floor": 0.0,
            "_grace": True,
        }

    w = config["avri"]["weights"]
    # Linear pillar attribution to weighted-avg (pre-floor) unrealized $
    unr_cr = arr_dollars * w["cr"] * (100 - cr) / 100
    unr_um = arr_dollars * w["um"] * (100 - um) / 100
    unr_dm = arr_dollars * w["dm"] * (100 - dm) / 100
    unr_th = arr_dollars * w["th"] * (100 - th) / 100

    # Floor residual: extra unrealized $ due to AVRI being capped below raw
    unrealized_total = arr_dollars * (1 - avri_score / 100.0)
    pillar_sum = unr_cr + unr_um + unr_dm + unr_th
    unr_floor = max(0.0, unrealized_total - pillar_sum) if floor_rule_triggered else 0.0

    return {
        "unrealized_cr":    unr_cr,
        "unrealized_um":    unr_um,
        "unrealized_dm":    unr_dm,
        "unrealized_th":    unr_th,
        "unrealized_floor": unr_floor,
        "_grace": False,
    }


# =============================================================================
# DataFrame-level convenience: score a whole population in one call
# =============================================================================

def score_population(
    facts: pd.DataFrame,
    config: dict | None = None,
) -> pd.DataFrame:
    """Score a DataFrame of per-account facts. Returns the same DataFrame
    with score columns appended.

    Required input columns:
        account_id, arr_dollars, monthly_commit_credits, consumed_90d,
        consumed_365d, active_days_90, th_score, grace_status

    Optional input columns:
        active_days_30 (used for naive_chs), latest_color (used for naive_chs)
    """
    if config is None:
        config = load_config()
    validate_config(config)

    df = facts.copy()
    is_grace = df["grace_status"] == "all_grace"

    # --- pillar-level scores ---
    df["util_pct"] = df["consumed_90d"] / (3.0 * df["monthly_commit_credits"]).replace(0, np.nan)
    df["util_pct"] = df["util_pct"].fillna(0).clip(lower=0)

    df["cr_score"] = df["util_pct"].apply(lambda u: compute_cr_score(u, config))
    df["um_score"] = df.apply(
        lambda r: compute_um_score(
            r["consumed_90d"], r["consumed_365d"], r["monthly_commit_credits"], config
        ),
        axis=1,
    )
    df["dm_score"] = df["active_days_90"].apply(lambda d: compute_dm_score(d, config))
    df["th_score"] = df["th_score"].apply(lambda t: compute_th_score(t, config))

    # --- composite + floor rule ---
    avri_results = df.apply(
        lambda r: compute_avri(r["cr_score"], r["um_score"], r["dm_score"], r["th_score"], config),
        axis=1,
        result_type="expand",
    )
    avri_results.columns = ["avri_raw", "avri_score", "floor_rule_triggered"]
    df = pd.concat([df, avri_results], axis=1)

    # All-grace accounts: NULL the pillar + composite scores
    df.loc[is_grace, ["cr_score", "um_score", "dm_score", "th_score",
                      "avri_raw", "avri_score"]] = np.nan
    df.loc[is_grace, "floor_rule_triggered"] = False

    # --- color ---
    df["avri_color"] = df["avri_score"].apply(lambda s: avri_color_for(s, config))

    # --- RV ---
    df["rv_dollars"] = df.apply(
        lambda r: compute_rv(r["arr_dollars"], r["avri_score"], config),
        axis=1,
    )

    # --- pillar decomposition ---
    decomp = df.apply(
        lambda r: compute_pillar_decomposition(
            r["arr_dollars"], r["cr_score"], r["um_score"],
            r["dm_score"], r["th_score"], r["avri_score"],
            r["floor_rule_triggered"], config,
        ),
        axis=1,
        result_type="expand",
    )
    df = pd.concat([df, decomp.drop(columns=["_grace"], errors="ignore")], axis=1)

    return df


# =============================================================================
# Aggregation (region / segment / CSM rollups)
# =============================================================================

def aggregate_realization(
    scored: pd.DataFrame,
    group_cols: list[str] | str,
) -> pd.DataFrame:
    """Roll up scored accounts to any aggregate level. RV decomposition holds
    at every level by linearity.

    Returns columns:
        n_accts, book_arr, book_rv, realization_rate (rv/arr),
        unrealized_cr/um/dm/th/floor, unrealized_total
    """
    if isinstance(group_cols, str):
        group_cols = [group_cols]

    # exclude grace accounts from book_rv but keep them visible in n_accts
    g = scored.copy()
    g["_in_grace"] = g["avri_score"].isna()

    out = g.groupby(group_cols, dropna=False).agg(
        n_accts=("account_id", "count"),
        n_grace=("_in_grace", "sum"),
        book_arr=("arr_dollars", "sum"),
        book_rv=("rv_dollars", "sum"),
        unrealized_cr=("unrealized_cr", "sum"),
        unrealized_um=("unrealized_um", "sum"),
        unrealized_dm=("unrealized_dm", "sum"),
        unrealized_th=("unrealized_th", "sum"),
        unrealized_floor=("unrealized_floor", "sum"),
    ).reset_index()

    # Exclude in-grace ARR from the realization-rate denominator; their
    # RV is 0 by construction so they'd drag the rate down spuriously.
    grace_arr = g[g["_in_grace"]].groupby(group_cols, dropna=False)["arr_dollars"].sum()
    out = out.merge(grace_arr.rename("grace_arr"), on=group_cols, how="left").fillna({"grace_arr": 0})
    out["scored_arr"] = out["book_arr"] - out["grace_arr"]
    out["realization_rate"] = (out["book_rv"] / out["scored_arr"]).where(out["scored_arr"] > 0, np.nan)
    out["unrealized_total"] = out["scored_arr"] - out["book_rv"]

    return out


def compute_realization_summary(scored: pd.DataFrame, config: dict | None = None) -> dict:
    """One-line org-wide summary numbers. Used by dashboard headline + tests."""
    if config is None:
        config = load_config()
    in_scope = scored[scored["avri_score"].notna()]
    return {
        "n_total":        len(scored),
        "n_scored":       len(in_scope),
        "n_grace":        int(scored["avri_score"].isna().sum()),
        "total_arr":      float(in_scope["arr_dollars"].sum()),
        "total_rv":       float(in_scope["rv_dollars"].sum()),
        "total_unrealized": float(in_scope["arr_dollars"].sum() - in_scope["rv_dollars"].sum()),
        "realization_rate": float(in_scope["rv_dollars"].sum() / in_scope["arr_dollars"].sum())
                           if in_scope["arr_dollars"].sum() > 0 else 0.0,
        "unrealized_by_pillar": {
            "cr":    float(in_scope["unrealized_cr"].sum()),
            "um":    float(in_scope["unrealized_um"].sum()),
            "dm":    float(in_scope["unrealized_dm"].sum()),
            "th":    float(in_scope["unrealized_th"].sum()),
            "floor": float(in_scope["unrealized_floor"].sum()),
        },
    }
