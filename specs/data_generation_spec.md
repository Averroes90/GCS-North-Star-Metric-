# Data Generation Spec: GCS North Star Synthetic Dataset

> **Status: Implemented as specified.** The Python data generator (`/data_generation/main.py`) is built to this spec. Validation gates pass on every run. See [`/data_generation/README.md`](../data_generation/README.md) for the implementation walkthrough and run instructions.

**Spec status:** Frozen reference. Treat as the source of truth for what the data should look like. Any future edits to the generator should update both the code and this spec.
**Output target:** Local Parquet first, then BigQuery Sandbox.
**Reproducibility:** Single random seed (`SEED = 20260422`) governs all RNG. Re-running produces identical data.

---

## 1. Goals

The dataset must be:

1. **Schema-faithful** to the brief (5 tables, specified columns, row counts at floor).
2. **Realistic enough** that existing metrics (TCV, ARR, raw utilization, naive CHS) compute meaningfully on it, not random noise.
3. **Pathological enough** that the 5 edge cases are visible and that AVRI's pillars demonstrably discriminate where existing metrics fail.
4. **Internally consistent**, IDs reconcile across tables (except where orphaning is intentional), dates align with contract windows, segment-correlated patterns hold.

---

## 2. Table schemas

### 2.1 `csm_rep`: ~50 rows
| Column | Type | Notes |
|---|---|---|
| csm_id | string | Format: `CSM-001` to `CSM-050` |
| name | string | Faker name |
| region | string | One of: AMER, EMEA, APAC |
| segment | string | Enterprise or Mid-Market |

**Distribution:** 60% AMER, 25% EMEA, 15% APAC. 40% Enterprise / 60% Mid-Market.

### 2.2 `accounts`: ~1,000 rows
| Column | Type | Notes |
|---|---|---|
| account_id | string | Format: `ACC-00001` to `ACC-01000` |
| company_name | string | Faker company |
| industry | string | One of: Financial Services, Healthcare, Tech, Retail, Manufacturing, Government, Education, Energy, Telecom |
| rep_id | string | FK to csm_rep.csm_id |

**Distribution:** Industry mix biased to enterprise verticals (FS 18%, Tech 17%, Healthcare 15%, Manufacturing 12%, others lower). Account-to-rep assignment respects segment: Enterprise reps get fewer larger accounts (~10–15 per rep), Mid-Market reps get more (~25–35 per rep).

### 2.3 `contracts`: ~1,200 rows
| Column | Type | Notes |
|---|---|---|
| contract_id | string | Format: `CON-000001` |
| account_id | string | FK to accounts.account_id |
| start_date | date | See distribution below |
| end_date | date | start_date + term_length |
| annual_commit_dollars | int | See distribution below |
| included_monthly_compute_credits | int | Roughly $/credit ratio of 1:1 to 4:1 depending on segment |

**Term length:** 70% 12-month, 22% 24-month, 8% 36-month.

**Start date:** uniformly distributed across the 18 months *prior* to the dataset's "today" (so all contracts have ≥ some history within the 12-month observation window).

**`annual_commit_dollars` distribution (segment-conditional):**
- Enterprise accounts: lognormal, median $400K, p90 $2M, max $8M.
- Mid-Market accounts: lognormal, median $50K, p90 $250K, max $800K.

**`included_monthly_compute_credits`:** annual_commit_dollars × (0.4 to 1.0 random multiplier) / 12. Encodes that price-per-credit varies by deal.

**Account-to-contracts:** Most accounts have 1 active contract. ~5% of accounts (50 accounts) have a **mid-year expansion**, a second contract starting 4–8 months after the first, with 1.5×–3× the commit. Overlap window 30–120 days (this exercises the precedence logic in AVRI).

### 2.4 `account_health`: ~50,000 rows
| Column | Type | Notes |
|---|---|---|
| account_id | string | FK |
| date | date | Weekly snapshot |
| health_color | string | green / yellow / red |
| compute_credits_consumed | int | Aggregated for the week |

**Cadence:** Weekly snapshot per account over 52 weeks ≈ 50K rows. Some accounts may have shorter histories if their first contract started <12 months ago.

**Health color generation:** Markov chain with segment-modulated transition matrices.

Baseline transitions (healthy accounts):
| From → To | green | yellow | red |
|---|---|---|---|
| green | 0.85 | 0.13 | 0.02 |
| yellow | 0.40 | 0.45 | 0.15 |
| red | 0.10 | 0.40 | 0.50 |

Edge-case accounts get **decay-biased** transitions (e.g., shelfware accounts drift toward yellow/red over time; spike-and-drop accounts decay sharply after Month 1).

Initial state: 75% green, 20% yellow, 5% red.

### 2.5 `daily_usage_logs`: ~200,000 rows
| Column | Type | Notes |
|---|---|---|
| log_id | string | UUID |
| account_id | string | FK (or rogue, see edge cases) |
| date | date | Daily timestamp |
| compute_credits_consumed | int | Per-event credits |

**Cadence:** Average ~200 logs per account over 12 months, but variance is high: heavy users generate many small logs per day; infrequent users generate batched logs. Logs are *event-level*, not daily aggregates.

---

## 3. Account "personas" (population mix)

Every account is assigned exactly one persona. Persona governs the time-series shape of consumption. Total = 100%.

| Persona | % of accounts | Behavior |
|---|---|---|
| **Healthy Steady** | 40% | Consumption ramps over 30–60 days, plateaus at 70–95% of monthly commit, holds steady. |
| **Healthy Growing** | 15% | Starts at 40%, grows to ~90% by Month 12. |
| **Healthy Mature** | 10% | High consumption (~85% of commit) from Day 1, no ramp. |
| **Healthy Declining** | 5% | Starts at 90%, gradually declines to ~55% (acceptable lifecycle decay, NOT spike-and-drop). |
| **Spike & Drop** ⚠️ | 5% | Burns 80–95% of *annual* credits in Month 1, drops to <5% of monthly commit thereafter. |
| **Shelfware** ⚠️ | 10% | Near-zero usage throughout. Health color drifts toward yellow/red. |
| **Consistent Overage** ⚠️ | 15% | Consumption holds at 110–150% of monthly commit every month. |

**Mid-year Expansion overlay (~5% of accounts):** Independent overlay applied to ~50 accounts (any persona except Shelfware). A second, larger contract is signed 4–8 months in, and consumption ramps to a higher absolute level after the new contract starts.

---

## 4. Time-series shape generation

Each account's daily consumption is generated by composing four functions:

```
consumption(t) = baseline(t, persona) × seasonal(t) × noise(t) × edge_modifier(t, persona)
```

- **`baseline(t, persona)`**, deterministic shape per persona (ramp, plateau, decay, burst).
- **`seasonal(t)`**, weekly seasonality: weekdays = 1.0, weekends = 0.6 ± 0.05.
- **`noise(t)`**, multiplicative Gaussian noise, σ = 0.15. Clipped to [0.5, 1.5].
- **`edge_modifier(t, persona)`**, applies persona-specific perturbations (e.g., spike-and-drop's Month 1 burst is in the modifier).

Logs are then generated from the daily total by splitting it into 1–8 events per active day with a Dirichlet-distributed split. Inactive days produce zero logs.

---

## 5. Edge case injection (explicit)

| Edge case | Target count | Injection logic |
|---|---|---|
| **Spike & Drop** | ~50 accounts (5%) | Persona assignment. Month 1 baseline = 80–95% of annual commit; Months 2–12 = <5% of monthly commit. |
| **Shelfware** | ~100 accounts (10%) | Persona assignment. Daily consumption = max(0, normal(0, 0.5)) — typically zero, occasional tiny logs. Health color biased red. |
| **Consistent Overage** | ~150 accounts (15%) | Persona assignment. Baseline floored at 110% of monthly commit, allowed to reach 150%. |
| **Mid-year Expansion** | ~50 accounts (5% overlay) | Add second contract row in `contracts`. Consumption baseline jumps after expansion start_date. |
| **Orphaned/Rogue Usage** | ~300 log rows | Generate `account_id` values not in `accounts` table (~150 rows). Generate ~150 rows where `date` falls outside any active contract for an existing account. |

All edge cases are **flagged in a hidden `_persona` and `_anomaly_type` column during generation** but those columns are *dropped before persistence*, the downstream pipeline must detect them from the data alone (which is the point of the DQ tests).

---

## 6. Cross-table correlations to enforce

These make the data feel real and let existing metrics produce non-trivial outputs:

1. **Segment ↔ commit size.** Enterprise commits are ~5–10× Mid-Market commits.
2. **Industry ↔ seasonality.** Retail accounts get a Q4 spike (×1.3 in Nov–Dec). Education accounts dip in summer. Others are flat.
3. **Persona ↔ health color.** Healthy personas spend 80%+ time in green. Shelfware drifts to red. Spike-and-drop starts green, decays through yellow to red after Month 2.
4. **Persona ↔ active days.** Healthy Steady ≈ 4–5 active days/week. Spike & Drop ≈ 25 active days then ~0. Shelfware ≈ 0–2 active days/quarter.
5. **Account ↔ rep segment.** An Enterprise account is always assigned to an Enterprise rep, and vice versa. No mixing.

---

## 7. Reproducibility & versioning

- Single seed: `SEED = 20260422` (today's date as int).
- All RNG (faker, numpy, random) seeded from this single value.
- Pin library versions in `requirements.txt`.
- Output written to `/data_generation/output/` as Parquet (one file per table) plus a `manifest.json` with row counts and seed.
- BigQuery upload is a separate script (`load_to_bigquery.py`) so we can iterate on data locally without re-uploading every time.

---

## 8. Validation gates (pre-upload)

Before pushing to BigQuery, the generator runs assertions:

1. Row counts within ±5% of targets.
2. All `account_id` in `contracts` exist in `accounts` (no unintended orphans there).
3. ~150 `daily_usage_logs.account_id` are NOT in `accounts` (intentional orphans).
4. ~150 `daily_usage_logs.date` fall outside any active contract (intentional rogues).
5. Persona distribution within ±2pp of targets.
6. Mid-year expansion accounts have exactly 2 contracts with overlapping dates.
7. `account_health` rows are weekly per account; no duplicate weeks.

Failures abort the run with a clear message.

---

## 9. What the data generator does NOT do

- No license/seat data (not in schema).
- No support tickets or feature adoption events (not in schema). The TH pillar therefore relies on `health_color` as a proxy.
- No NPS/CSAT events.
- No real-time/streaming generation; all data is generated as a single batch.

---

## 10. Hand-off to BigQuery

`load_to_bigquery.py`:
- Reads `/data_generation/output/*.parquet`.
- Creates dataset `gcs_north_star` if not exists.
- Loads each table with explicit schema (no auto-detection).
- Verifies row counts post-load.

After load, the next deliverable is the metric pipeline (`/pipeline_and_tests/`).
