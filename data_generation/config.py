"""Central configuration for the GCS North Star synthetic data generator.

All parameters live here so that tuning the dataset (volume, edge case
prevalence, noise, etc.) doesn't require touching the generation code.

All RNG is seeded from SEED — re-running produces byte-identical output.
"""

from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 20260422

# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"

# ---------------------------------------------------------------------------
# Time bounds
# ---------------------------------------------------------------------------
TODAY = date(2026, 4, 22)        # data generation "today"
HISTORY_MONTHS = 12              # observation window (brief minimum)
CONTRACT_LOOKBACK_MONTHS = 18    # contracts can have started up to this far back

# ---------------------------------------------------------------------------
# Row count targets
# ---------------------------------------------------------------------------
N_CSM_REPS = 50
N_ACCOUNTS = 1000
TARGET_USAGE_LOGS = 200_000      # approximate; actual will vary

# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------
REGION_WEIGHTS = {"AMER": 0.60, "EMEA": 0.25, "APAC": 0.15}
SEGMENT_WEIGHTS = {"Enterprise": 0.40, "Mid-Market": 0.60}

INDUSTRY_WEIGHTS = {
    "Financial Services": 0.18,
    "Tech":               0.17,
    "Healthcare":         0.15,
    "Manufacturing":      0.12,
    "Retail":             0.10,
    "Government":         0.09,
    "Energy":             0.08,
    "Telecom":            0.06,
    "Education":          0.05,
}

# Contract term in months
CONTRACT_TERM_WEIGHTS = {12: 0.70, 24: 0.22, 36: 0.08}

# Annual commit dollars: lognormal parameters per segment
# We compute mu/sigma from the desired median + p90.
COMMIT_TARGETS = {
    "Enterprise": {"median": 400_000, "p90": 2_000_000, "max": 8_000_000},
    "Mid-Market": {"median": 50_000,  "p90": 250_000,   "max": 800_000},
}

# Price-per-credit: annual_commit_dollars × multiplier / 12 = monthly credits
CREDIT_MULTIPLIER_RANGE = (0.4, 1.0)

# ---------------------------------------------------------------------------
# Persona mix (sums to 1.0)
# ---------------------------------------------------------------------------
PERSONA_WEIGHTS = {
    "healthy_steady":     0.40,
    "healthy_growing":    0.15,
    "healthy_mature":     0.10,
    "healthy_declining":  0.05,
    "spike_drop":         0.05,
    "shelfware":          0.10,
    "consistent_overage": 0.15,
}
assert abs(sum(PERSONA_WEIGHTS.values()) - 1.0) < 1e-9

# Mid-year expansion is an OVERLAY (independent of persona)
MID_YEAR_EXPANSION_PCT = 0.05

# ---------------------------------------------------------------------------
# Time series generation
# ---------------------------------------------------------------------------
NOISE_SIGMA = 0.15               # multiplicative Gaussian noise
NOISE_CLIP = (0.5, 1.5)
WEEKEND_MULTIPLIER = 0.6
WEEKEND_JITTER = 0.05
EVENTS_PER_DAY_RANGE = (1, 2)    # log events generated per active day

# ---------------------------------------------------------------------------
# Markov chain transitions for account_health.health_color
# ---------------------------------------------------------------------------
HEALTH_TRANSITIONS_HEALTHY = {
    "green":  {"green": 0.85, "yellow": 0.13, "red": 0.02},
    "yellow": {"green": 0.40, "yellow": 0.45, "red": 0.15},
    "red":    {"green": 0.10, "yellow": 0.40, "red": 0.50},
}

# Used for shelfware accounts and spike_drop after Month 1: drift toward red
HEALTH_TRANSITIONS_DECAY = {
    "green":  {"green": 0.55, "yellow": 0.35, "red": 0.10},
    "yellow": {"green": 0.15, "yellow": 0.50, "red": 0.35},
    "red":    {"green": 0.05, "yellow": 0.20, "red": 0.75},
}

INITIAL_HEALTH_DIST = {"green": 0.75, "yellow": 0.20, "red": 0.05}

# ---------------------------------------------------------------------------
# Industry seasonality multipliers (applied per-day based on month)
# ---------------------------------------------------------------------------
# month_idx (1-12) -> multiplier; 1.0 means no effect
INDUSTRY_SEASONALITY = {
    "Retail": {11: 1.30, 12: 1.30},                    # Q4 spike
    "Education": {6: 0.65, 7: 0.55, 8: 0.65},          # summer dip
}

# ---------------------------------------------------------------------------
# Edge case injection counts
# ---------------------------------------------------------------------------
N_ORPHAN_LOGS = 150          # account_id not in accounts table
N_OUT_OF_WINDOW_LOGS = 150   # date outside any active contract for that account
