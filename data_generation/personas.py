"""Persona assignment + persona-driven daily consumption baselines.

Every account is assigned exactly one persona (see config.PERSONA_WEIGHTS).
The persona governs the *shape* of consumption over the contract lifecycle.
Mid-year expansion is an independent overlay handled in generate.py — it
modifies the absolute level of consumption mid-stream but doesn't change persona.
"""

from __future__ import annotations

import numpy as np

from config import PERSONA_WEIGHTS, NOISE_SIGMA, NOISE_CLIP, WEEKEND_MULTIPLIER, WEEKEND_JITTER

PERSONAS = list(PERSONA_WEIGHTS.keys())


def assign_personas(n_accounts: int, rng: np.random.Generator) -> list[str]:
    """Return a list of persona labels of length n_accounts."""
    weights = np.array(list(PERSONA_WEIGHTS.values()))
    weights = weights / weights.sum()
    return list(rng.choice(PERSONAS, size=n_accounts, p=weights))


def consumption_baseline(
    persona: str,
    n_days: int,
    monthly_commit: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate a deterministic daily-baseline consumption vector for a persona.

    Returns an array of length n_days containing per-day credit consumption
    (BEFORE seasonal/noise modifiers are applied).
    """
    daily_target = monthly_commit / 30.0
    t = np.arange(n_days)
    out = np.zeros(n_days)

    if persona == "healthy_steady":
        plateau = rng.uniform(0.70, 0.95)
        ramp_days = rng.integers(30, 60)
        ramp = np.minimum(t / ramp_days, 1.0)
        out = daily_target * ramp * plateau

    elif persona == "healthy_growing":
        start, end = 0.40, 0.90
        progress = np.minimum(t / 365, 1.0)
        out = daily_target * (start + (end - start) * progress)

    elif persona == "healthy_mature":
        out = np.full(n_days, daily_target * rng.uniform(0.80, 0.92))

    elif persona == "healthy_declining":
        start, end = 0.90, 0.55
        progress = np.minimum(t / 365, 1.0)
        out = daily_target * (start - (start - end) * progress)

    elif persona == "spike_drop":
        # Burn 80-95% of ANNUAL credits in the first 30 days, then near-zero.
        annual = monthly_commit * 12
        burst_pct = rng.uniform(0.80, 0.95)
        first_n = min(30, n_days)
        out[:first_n] = (annual * burst_pct) / first_n
        if n_days > first_n:
            out[first_n:] = daily_target * 0.03

    elif persona == "shelfware":
        # Near zero; occasional tiny pulses
        out = np.maximum(0, rng.normal(0.0, 0.5, n_days)) * daily_target * 0.01

    elif persona == "consistent_overage":
        overage = rng.uniform(1.10, 1.50)
        out = np.full(n_days, daily_target * overage)

    else:
        raise ValueError(f"Unknown persona: {persona}")

    return out


def apply_seasonal(
    baseline: np.ndarray,
    dates: np.ndarray,
    industry: str,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply weekday/weekend dampener and industry-specific monthly multipliers."""
    from config import INDUSTRY_SEASONALITY

    # Weekday/weekend factor
    # numpy datetime64 -> day of week (0=Monday, 6=Sunday)
    dow = np.array([d.weekday() for d in dates])
    is_weekend = (dow >= 5).astype(float)
    weekend_mult = 1.0 - is_weekend * (1.0 - WEEKEND_MULTIPLIER)
    # Add jitter
    weekend_mult = weekend_mult + rng.uniform(-WEEKEND_JITTER, WEEKEND_JITTER, len(dates))

    # Industry monthly multipliers
    months = np.array([d.month for d in dates])
    industry_mult = np.ones(len(dates))
    for month, mult in INDUSTRY_SEASONALITY.get(industry, {}).items():
        industry_mult[months == month] = mult

    return baseline * weekend_mult * industry_mult


def apply_noise(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Multiplicative Gaussian noise, clipped to NOISE_CLIP."""
    n = len(values)
    noise = rng.normal(1.0, NOISE_SIGMA, n)
    noise = np.clip(noise, NOISE_CLIP[0], NOISE_CLIP[1])
    return np.maximum(0.0, values * noise)


def is_decay_persona(persona: str) -> bool:
    """Personas whose health color drifts toward red over time."""
    return persona in ("shelfware", "spike_drop")
