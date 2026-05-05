"""Snapshot tests for ``core.scoring``.

These tests verify that:
  1. The scoring module's outputs are stable for the bundled default config
     (regression test against unintended changes).
  2. RV decomposition adds up at every aggregate level (mathematical
     invariants of the linear formula).
  3. Grace-period accounts are correctly excluded from RV totals.
  4. The four AVRI weights sum to 1.0.
  5. The piecewise scoring curves are continuous at their breakpoints.

Run from the project root:
    python -m pytest core/test_scoring.py -v

Or directly:
    cd core && python -m pytest test_scoring.py -v
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.scoring import (
    aggregate_realization,
    avri_color_for,
    compute_avri,
    compute_pillar_decomposition,
    compute_realization_summary,
    compute_rv,
    load_config,
    piecewise_score,
    score_population,
    validate_config,
)
from core.build_facts import build_facts


HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden_scored.parquet"


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def facts():
    return build_facts()


@pytest.fixture(scope="module")
def scored(facts, config):
    return score_population(facts, config)


# =============================================================================
# Config invariants
# =============================================================================

def test_config_loads(config):
    assert config["version"].startswith("v2")


def test_avri_weights_sum_to_one(config):
    validate_config(config)  # raises if violated


def test_color_thresholds_ordered(config):
    t = config["avri"]["color_thresholds"]
    assert 0 < t["yellow"] < t["green"] <= 100


# =============================================================================
# Piecewise curve continuity
# =============================================================================

def test_cr_curve_continuous(config):
    """The util curve should be (approximately) continuous at breakpoints."""
    curve = config["cr_pillar"]["util_curve"]
    breakpoints = [0.10, 0.50, 1.10, 1.50, 2.00]
    for bp in breakpoints:
        left  = piecewise_score(bp - 1e-6, curve)
        right = piecewise_score(bp + 1e-6, curve)
        assert abs(left - right) < 0.5, f"Discontinuity at util={bp}: {left} vs {right}"


def test_cr_sweet_spot(config):
    """Util in [0.50, 1.10] should always score 100."""
    curve = config["cr_pillar"]["util_curve"]
    for u in [0.50, 0.75, 1.00, 1.10]:
        assert piecewise_score(u, curve) == 100, f"Expected 100 at util={u}"


def test_cr_zero_at_extremes(config):
    """Util below 10% or above 200% scores zero."""
    curve = config["cr_pillar"]["util_curve"]
    assert piecewise_score(0.0, curve) == 0
    assert piecewise_score(0.05, curve) == 0
    assert piecewise_score(2.5, curve) == 0


# =============================================================================
# Floor rule
# =============================================================================

def test_floor_rule_caps_at_50(config):
    """If TH < 30, AVRI is capped at 50 even with all other pillars at 100."""
    raw, score, fired = compute_avri(100, 100, 100, 25, config)
    assert fired is True
    assert score == 50.0
    assert raw > 50  # raw composite was higher


def test_floor_rule_inactive_when_th_high(config):
    raw, score, fired = compute_avri(100, 100, 100, 50, config)
    assert fired is False
    assert score == raw


# =============================================================================
# RV invariants
# =============================================================================

def test_rv_perfect_account(config):
    """AVRI=100 → RV = ARR (full realization)."""
    assert compute_rv(1_000_000, 100, config) == pytest.approx(1_000_000)


def test_rv_zero_avri(config):
    """AVRI=0 → RV=0."""
    assert compute_rv(1_000_000, 0, config) == 0


def test_rv_grace_returns_zero(config):
    """All-grace accounts (NULL AVRI) contribute 0 RV."""
    assert compute_rv(5_000_000, None, config) == 0
    assert compute_rv(5_000_000, np.nan, config) == 0


def test_rv_linear(config):
    """v1 RV is linear: AVRI=80 → 80% of ARR realized."""
    assert compute_rv(1_000_000, 80, config) == pytest.approx(800_000)
    assert compute_rv(1_000_000, 50, config) == pytest.approx(500_000)


# =============================================================================
# Pillar decomposition
# =============================================================================

def test_decomposition_sums_to_unrealized_no_floor(config):
    """When floor rule doesn't fire, sum of pillar contributions = unrealized."""
    arr = 1_000_000
    cr, um, dm, th = 70, 60, 80, 90
    _, avri, fired = compute_avri(cr, um, dm, th, config)
    assert not fired
    decomp = compute_pillar_decomposition(arr, cr, um, dm, th, avri, fired, config)
    expected_unrealized = arr * (1 - avri / 100)
    actual_sum = (decomp["unrealized_cr"] + decomp["unrealized_um"]
                  + decomp["unrealized_dm"] + decomp["unrealized_th"]
                  + decomp["unrealized_floor"])
    assert actual_sum == pytest.approx(expected_unrealized, rel=1e-9)


def test_decomposition_with_floor_includes_residual(config):
    """When floor rule fires, the floor-residual column captures the extra hit."""
    arr = 1_000_000
    cr, um, dm, th = 100, 100, 100, 25  # raw=85, capped to 50
    _, avri, fired = compute_avri(cr, um, dm, th, config)
    assert fired
    decomp = compute_pillar_decomposition(arr, cr, um, dm, th, avri, fired, config)
    expected_unrealized = arr * (1 - avri / 100)  # 50% unrealized
    actual_sum = (decomp["unrealized_cr"] + decomp["unrealized_um"]
                  + decomp["unrealized_dm"] + decomp["unrealized_th"]
                  + decomp["unrealized_floor"])
    assert actual_sum == pytest.approx(expected_unrealized, rel=1e-9)
    assert decomp["unrealized_floor"] > 0  # floor produced a residual


# =============================================================================
# End-to-end population scoring
# =============================================================================

def test_population_scored_count(scored):
    """We expect approximately 766 in-scope accounts (matches v1.3 count)."""
    assert 700 <= len(scored) <= 800


def test_population_realization_in_range(scored):
    summary = compute_realization_summary(scored)
    rate = summary["realization_rate"]
    # Linear v1: expected ~70-80% realization on the synthetic data
    assert 0.60 <= rate <= 0.85, f"Realization rate {rate:.3f} outside expected band"


def test_population_decomposition_adds_up(scored):
    """At population level, sum of pillar contributions = total unrealized $."""
    summary = compute_realization_summary(scored)
    unrealized_from_pillars = sum(summary["unrealized_by_pillar"].values())
    assert unrealized_from_pillars == pytest.approx(summary["total_unrealized"], rel=1e-6)


def test_aggregation_sums_match_account_level(scored):
    """Region-level book_arr sum == account-level book_arr sum."""
    region_sum = aggregate_realization(scored, "rep_id")["book_arr"].sum()
    acct_sum = scored["arr_dollars"].sum()
    assert region_sum == pytest.approx(acct_sum, rel=1e-9)


def test_grace_accounts_excluded_from_rv(scored):
    """Onboarding accounts have NaN AVRI and zero RV contribution."""
    grace = scored[scored["avri_score"].isna()]
    if len(grace):
        assert (grace["rv_dollars"] == 0).all()


# =============================================================================
# Snapshot regression test
# =============================================================================

def test_snapshot_regression(scored):
    """Compare current scored output to a frozen golden snapshot.

    Run ``python -m core.test_scoring --update-golden`` to refresh after
    intentional changes.
    """
    if not GOLDEN.exists():
        pytest.skip(f"Golden snapshot not found at {GOLDEN}; run with --update-golden")
    golden = pd.read_parquet(GOLDEN)
    cols = ["account_id", "cr_score", "um_score", "dm_score", "th_score",
            "avri_score", "rv_dollars", "unrealized_cr", "unrealized_um",
            "unrealized_dm", "unrealized_th", "unrealized_floor"]
    cur = scored[cols].sort_values("account_id").reset_index(drop=True)
    gold = golden[cols].sort_values("account_id").reset_index(drop=True)
    assert len(cur) == len(gold), f"Row count drift: {len(cur)} vs {len(gold)}"
    pd.testing.assert_frame_equal(cur, gold, check_exact=False, rtol=1e-6, atol=1e-3)


def update_golden():
    facts = build_facts()
    cfg = load_config()
    scored = score_population(facts, cfg)
    cols = ["account_id", "cr_score", "um_score", "dm_score", "th_score",
            "avri_score", "rv_dollars", "unrealized_cr", "unrealized_um",
            "unrealized_dm", "unrealized_th", "unrealized_floor"]
    scored[cols].to_parquet(GOLDEN, index=False)
    print(f"Wrote golden snapshot ({len(scored)} rows) to {GOLDEN}")


if __name__ == "__main__":
    import sys
    if "--update-golden" in sys.argv:
        update_golden()
    else:
        sys.exit(pytest.main([__file__, "-v"]))
