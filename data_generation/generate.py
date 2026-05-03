"""Entity & event generation for the GCS North Star synthetic dataset.

Public functions (called in this order from main.py):

    generate_csm_reps(rng, fake)        -> DataFrame
    generate_accounts(reps, rng, fake)  -> DataFrame
    generate_contracts(accounts, rng)   -> DataFrame
    generate_usage_logs(accounts, contracts, rng)   -> DataFrame
    generate_account_health(accounts, contracts, daily_usage, rng) -> DataFrame
    inject_orphans(usage_logs, accounts, contracts, rng) -> DataFrame
"""

from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from config import (
    COMMIT_TARGETS,
    CONTRACT_LOOKBACK_MONTHS,
    CONTRACT_TERM_WEIGHTS,
    CREDIT_MULTIPLIER_RANGE,
    EVENTS_PER_DAY_RANGE,
    HEALTH_TRANSITIONS_DECAY,
    HEALTH_TRANSITIONS_HEALTHY,
    INDUSTRY_WEIGHTS,
    INITIAL_HEALTH_DIST,
    MID_YEAR_EXPANSION_PCT,
    N_ACCOUNTS,
    N_CSM_REPS,
    N_ORPHAN_LOGS,
    N_OUT_OF_WINDOW_LOGS,
    REGION_WEIGHTS,
    SEGMENT_WEIGHTS,
    TODAY,
)
from personas import (
    PERSONAS,
    apply_noise,
    apply_seasonal,
    consumption_baseline,
    is_decay_persona,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_uuid(rng: np.random.Generator) -> str:
    """Deterministic UUID4-shaped string from the seeded RNG."""
    # Compose 128 bits from two 64-bit draws
    high = int(rng.integers(0, 2**63 - 1))
    low = int(rng.integers(0, 2**63 - 1))
    bits = (high << 64) | low
    return str(uuid.UUID(int=bits))


def _choose(rng: np.random.Generator, weights_dict: dict, n: int = 1):
    keys = list(weights_dict.keys())
    weights = np.array(list(weights_dict.values()), dtype=float)
    weights = weights / weights.sum()
    return rng.choice(keys, size=n, p=weights)


def _lognormal_from_targets(median: float, p90: float, max_val: float,
                             n: int, rng: np.random.Generator) -> np.ndarray:
    """Sample n values from a lognormal whose median/p90 match the targets."""
    mu = math.log(median)
    # p90 of lognormal: exp(mu + 1.2816*sigma)  => sigma = (ln(p90) - mu) / 1.2816
    sigma = (math.log(p90) - mu) / 1.2816
    samples = rng.lognormal(mean=mu, sigma=sigma, size=n)
    return np.minimum(samples, max_val)


# ---------------------------------------------------------------------------
# csm_rep
# ---------------------------------------------------------------------------

def generate_csm_reps(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    n = N_CSM_REPS
    rows = []
    regions = _choose(rng, REGION_WEIGHTS, n)
    segments = _choose(rng, SEGMENT_WEIGHTS, n)
    for i in range(n):
        rows.append({
            "csm_id": f"CSM-{i+1:03d}",
            "name": fake.name(),
            "region": regions[i],
            "segment": segments[i],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

def generate_accounts(reps: pd.DataFrame, rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    """Generate ~N_ACCOUNTS accounts. Each account is assigned to a rep
    matching its segment. Enterprise reps get fewer larger books;
    Mid-Market reps get more accounts each.
    """
    enterprise_reps = reps[reps.segment == "Enterprise"].csm_id.tolist()
    mm_reps = reps[reps.segment == "Mid-Market"].csm_id.tolist()

    # Roughly: 30% Enterprise accounts, 70% Mid-Market accounts
    n_enterprise = int(N_ACCOUNTS * 0.30)
    n_mm = N_ACCOUNTS - n_enterprise

    # Sample reps for each account (with replacement)
    enterprise_assignments = rng.choice(enterprise_reps, size=n_enterprise) if enterprise_reps else []
    mm_assignments = rng.choice(mm_reps, size=n_mm) if mm_reps else []

    rows = []
    industries = _choose(rng, INDUSTRY_WEIGHTS, N_ACCOUNTS)

    rep_assignments = list(enterprise_assignments) + list(mm_assignments)
    segment_per_account = ["Enterprise"] * n_enterprise + ["Mid-Market"] * n_mm

    for i in range(N_ACCOUNTS):
        rows.append({
            "account_id": f"ACC-{i+1:05d}",
            "company_name": fake.company(),
            "industry": industries[i],
            "rep_id": rep_assignments[i],
            "_segment": segment_per_account[i],  # internal — dropped before write
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------

def generate_contracts(accounts: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """One primary contract per account, plus a mid-year expansion overlay
    on ~5% of accounts (which produces a second overlapping contract).
    """
    contracts = []
    contract_counter = 0

    earliest = TODAY - timedelta(days=CONTRACT_LOOKBACK_MONTHS * 30)

    for _, acct in accounts.iterrows():
        seg = acct["_segment"]
        # Primary contract
        days_back = int(rng.integers(0, CONTRACT_LOOKBACK_MONTHS * 30))
        start = TODAY - timedelta(days=days_back)
        term_months = int(rng.choice(
            list(CONTRACT_TERM_WEIGHTS.keys()),
            p=np.array(list(CONTRACT_TERM_WEIGHTS.values())) / sum(CONTRACT_TERM_WEIGHTS.values())
        ))
        end = start + timedelta(days=term_months * 30)

        # Annual commit per segment (lognormal)
        params = COMMIT_TARGETS[seg]
        annual = float(_lognormal_from_targets(
            params["median"], params["p90"], params["max"], 1, rng
        )[0])
        annual = round(annual, -2)  # round to nearest $100

        # Monthly credits = annual * multiplier / 12
        mult = rng.uniform(*CREDIT_MULTIPLIER_RANGE)
        monthly_credits = int(round(annual * mult / 12))

        contract_counter += 1
        contracts.append({
            "contract_id": f"CON-{contract_counter:06d}",
            "account_id": acct["account_id"],
            "start_date": start,
            "end_date": end,
            "annual_commit_dollars": int(annual),
            "included_monthly_compute_credits": monthly_credits,
        })

    # Mid-year expansion overlay
    expansion_n = int(N_ACCOUNTS * MID_YEAR_EXPANSION_PCT)
    expansion_account_ids = rng.choice(accounts["account_id"].values, size=expansion_n, replace=False)

    for acct_id in expansion_account_ids:
        # Find primary contract
        primary = next(c for c in contracts if c["account_id"] == acct_id)
        # Expansion starts 4-8 months after primary start
        offset = int(rng.integers(120, 240))
        exp_start = primary["start_date"] + timedelta(days=offset)
        # Term length similar mix
        term_months = int(rng.choice(
            list(CONTRACT_TERM_WEIGHTS.keys()),
            p=np.array(list(CONTRACT_TERM_WEIGHTS.values())) / sum(CONTRACT_TERM_WEIGHTS.values())
        ))
        exp_end = exp_start + timedelta(days=term_months * 30)

        # Expansion is 1.5x - 3x the original commit
        boost = rng.uniform(1.5, 3.0)
        new_annual = int(round(primary["annual_commit_dollars"] * boost, -2))
        mult = rng.uniform(*CREDIT_MULTIPLIER_RANGE)
        new_credits = int(round(new_annual * mult / 12))

        contract_counter += 1
        contracts.append({
            "contract_id": f"CON-{contract_counter:06d}",
            "account_id": acct_id,
            "start_date": exp_start,
            "end_date": exp_end,
            "annual_commit_dollars": new_annual,
            "included_monthly_compute_credits": new_credits,
        })

    return pd.DataFrame(contracts)


# ---------------------------------------------------------------------------
# daily_usage_logs
# ---------------------------------------------------------------------------

def generate_usage_logs(
    accounts: pd.DataFrame,
    contracts: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """For each account, generate event-level usage logs based on its persona
    and active contract dates. Multiple logs per active day (1-8, Dirichlet split).

    Returns a DataFrame with columns: log_id, account_id, date, compute_credits_consumed.
    Also returns per-account daily totals (used by account_health generator).
    """
    rows = []
    persona_map = dict(zip(accounts["account_id"], accounts["_persona"]))
    industry_map = dict(zip(accounts["account_id"], accounts["industry"]))

    # Build per-account list of contracts (sorted by start)
    contracts_by_account = {}
    for c in contracts.itertuples(index=False):
        contracts_by_account.setdefault(c.account_id, []).append(c)
    for k in contracts_by_account:
        contracts_by_account[k].sort(key=lambda c: c.start_date)

    observation_start = TODAY - timedelta(days=365)

    for acct_id in accounts["account_id"]:
        persona = persona_map[acct_id]
        industry = industry_map[acct_id]
        acct_contracts = contracts_by_account.get(acct_id, [])
        if not acct_contracts:
            continue

        # Define the per-day commit timeline (handles overlap/expansion)
        # For each day in observation window, compute total active monthly_credits.
        primary = acct_contracts[0]
        # We start consumption from max(primary.start, observation_start)
        gen_start = max(primary.start_date, observation_start)
        gen_end = min(primary.end_date, TODAY)
        if gen_end <= gen_start:
            continue
        n_days = (gen_end - gen_start).days
        if n_days <= 0:
            continue

        dates = np.array([gen_start + timedelta(days=int(i)) for i in range(n_days)])

        # Per-day monthly commit (sum of all active contracts)
        daily_commit = np.zeros(n_days)
        for c in acct_contracts:
            for i, d in enumerate(dates):
                if c.start_date <= d <= c.end_date:
                    daily_commit[i] += c.included_monthly_compute_credits
        # Convert to a "monthly commit at this point" — same units throughout
        # For consumption_baseline we need a single monthly_commit value, but
        # we want the expansion to lift consumption mid-stream. We'll use the
        # primary contract's monthly_commit for the persona shape, then scale
        # by (daily_commit / primary.monthly_commit) to inject the expansion lift.
        primary_monthly = primary.included_monthly_compute_credits
        if primary_monthly <= 0:
            continue
        commit_lift = daily_commit / primary_monthly  # >=1.0 once expansion kicks in

        # Persona baseline (uses primary monthly as anchor)
        baseline = consumption_baseline(persona, n_days, primary_monthly, rng)
        # Apply expansion lift
        baseline = baseline * commit_lift
        # Apply seasonal + noise
        baseline = apply_seasonal(baseline, dates, industry, rng)
        baseline = apply_noise(baseline, rng)

        # Convert to event logs: split each day's consumption into 1-8 events
        for i, d in enumerate(dates):
            day_total = baseline[i]
            if day_total < 0.5:
                # No usage event for this day
                continue
            n_events = int(rng.integers(EVENTS_PER_DAY_RANGE[0], EVENTS_PER_DAY_RANGE[1] + 1))
            # Dirichlet split
            splits = rng.dirichlet(np.ones(n_events))
            for k in range(n_events):
                amt = int(round(day_total * splits[k]))
                if amt <= 0:
                    continue
                rows.append({
                    "log_id": _make_uuid(rng),
                    "account_id": acct_id,
                    "date": d,
                    "compute_credits_consumed": amt,
                })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# account_health
# ---------------------------------------------------------------------------

def generate_account_health(
    accounts: pd.DataFrame,
    contracts: pd.DataFrame,
    usage_logs: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Weekly snapshot per account over the observation window, with:
       - health_color via Markov chain (decay-biased for shelfware/spike-drop)
       - compute_credits_consumed = sum of usage_logs in that week
    """
    rows = []
    persona_map = dict(zip(accounts["account_id"], accounts["_persona"]))

    # Build per-account contract date range
    acct_contract_dates = {}
    for c in contracts.itertuples(index=False):
        existing = acct_contract_dates.get(c.account_id, (c.start_date, c.end_date))
        acct_contract_dates[c.account_id] = (
            min(existing[0], c.start_date),
            max(existing[1], c.end_date),
        )

    observation_start = TODAY - timedelta(days=365)

    # Pre-aggregate usage by (account_id, week_start)
    if not usage_logs.empty:
        usage_logs = usage_logs.copy()
        usage_logs["date"] = pd.to_datetime(usage_logs["date"])
        usage_logs["week_start"] = (
            usage_logs["date"] - pd.to_timedelta(usage_logs["date"].dt.weekday, unit="D")
        ).dt.date
        weekly_usage = (
            usage_logs.groupby(["account_id", "week_start"])["compute_credits_consumed"]
            .sum()
            .to_dict()
        )
    else:
        weekly_usage = {}

    for acct_id in accounts["account_id"]:
        persona = persona_map[acct_id]
        if acct_id not in acct_contract_dates:
            continue
        start, end = acct_contract_dates[acct_id]
        gen_start = max(start, observation_start)
        gen_end = min(end, TODAY)
        if gen_end <= gen_start:
            continue

        # Snap to Monday of the gen_start week
        gen_start = gen_start - timedelta(days=gen_start.weekday())

        # Initial color
        keys = list(INITIAL_HEALTH_DIST.keys())
        probs = np.array(list(INITIAL_HEALTH_DIST.values()))
        probs = probs / probs.sum()
        current_color = str(rng.choice(keys, p=probs))

        # Walk weeks
        cursor = gen_start
        week_idx = 0
        while cursor <= gen_end:
            # Choose transition matrix
            if is_decay_persona(persona):
                # Spike-drop uses healthy in week 0-3, decay after
                if persona == "spike_drop" and week_idx < 4:
                    matrix = HEALTH_TRANSITIONS_HEALTHY
                else:
                    matrix = HEALTH_TRANSITIONS_DECAY
            else:
                matrix = HEALTH_TRANSITIONS_HEALTHY

            # Transition (skip on the very first week — keep initial)
            if week_idx > 0:
                trans = matrix[current_color]
                next_keys = list(trans.keys())
                next_probs = np.array(list(trans.values()))
                next_probs = next_probs / next_probs.sum()
                current_color = str(rng.choice(next_keys, p=next_probs))

            consumed = int(weekly_usage.get((acct_id, cursor), 0))

            rows.append({
                "account_id": acct_id,
                "date": cursor,
                "health_color": current_color,
                "compute_credits_consumed": consumed,
            })
            cursor = cursor + timedelta(days=7)
            week_idx += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Edge case injection: orphaned + out-of-window usage logs
# ---------------------------------------------------------------------------

def inject_orphans(
    usage_logs: pd.DataFrame,
    accounts: pd.DataFrame,
    contracts: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Append:
       - N_ORPHAN_LOGS rows where account_id does NOT exist in accounts
       - N_OUT_OF_WINDOW_LOGS rows where date is outside any active contract for the account
    Returns the combined DataFrame.
    """
    extras = []

    # Orphan logs: fake account_ids
    for _ in range(N_ORPHAN_LOGS):
        fake_id = f"ACC-{rng.integers(N_ACCOUNTS + 100, N_ACCOUNTS + 5000):05d}"
        # Random date in observation window
        days_back = int(rng.integers(0, 365))
        d = TODAY - timedelta(days=days_back)
        extras.append({
            "log_id": _make_uuid(rng),
            "account_id": fake_id,
            "date": d,
            "compute_credits_consumed": int(rng.integers(50, 500)),
        })

    # Out-of-window logs: existing account, but date outside all its contracts
    contracts_by_account = {}
    for c in contracts.itertuples(index=False):
        contracts_by_account.setdefault(c.account_id, []).append((c.start_date, c.end_date))

    candidate_accts = list(contracts_by_account.keys())
    chosen = rng.choice(candidate_accts, size=N_OUT_OF_WINDOW_LOGS, replace=True)
    for acct_id in chosen:
        # Pick a date well before the earliest contract start
        ranges = contracts_by_account[acct_id]
        earliest = min(s for s, _ in ranges)
        # Date 30-200 days BEFORE earliest contract
        d = earliest - timedelta(days=int(rng.integers(30, 200)))
        extras.append({
            "log_id": _make_uuid(rng),
            "account_id": acct_id,
            "date": d,
            "compute_credits_consumed": int(rng.integers(50, 500)),
        })

    extras_df = pd.DataFrame(extras)
    if usage_logs.empty:
        return extras_df
    # Strip helper columns from usage_logs if present
    cols = ["log_id", "account_id", "date", "compute_credits_consumed"]
    return pd.concat([usage_logs[cols], extras_df[cols]], ignore_index=True)
