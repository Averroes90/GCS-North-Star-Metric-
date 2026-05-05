# core/

Single source of truth for AVRI and RV calibration parameters and scoring math.

## Why this exists

Both the BigQuery pipeline (SQL) and the Streamlit dashboard (Python) need
to score accounts. If those two implementations were independent, they would
inevitably drift. To prevent that, every calibratable parameter lives in
`config_v1.json` and the scoring math has a Python reference implementation
in `scoring.py`. The SQL pipeline reads the same JSON via templating; the
dashboard imports `scoring.py` directly. A snapshot regression test
(`test_scoring.py`) verifies that for the default config, both produce
identical numbers per account.

## Files

| File | Purpose |
|---|---|
| `config_v1.json` | All calibratable parameters: AVRI weights, pillar curves, floor rule, grace period, RV formula, naive CHS weights. Schema-validated. |
| `scoring.py` | Pure functions: `score_population()`, `aggregate_realization()`, `compute_realization_summary()`. Takes (facts, config) → scores. |
| `build_facts.py` | Local stand-in for the BigQuery upstream: rebuilds per-account facts from parquet. Used by tests so they run without BQ access. |
| `test_scoring.py` | Pytest suite. Invariants on the math, decomposition that should sum, and a frozen golden snapshot. |
| `golden_scored.parquet` | Frozen snapshot of `score_population()` output for the bundled default config. Refresh via `python -m core.test_scoring --update-golden`. |

## The contract

Pipeline and dashboard agree on:

1. **Inputs** — per-account "facts": ARR, monthly commit, 90d/365d consumed,
   active days, decayed TH, grace status. Materialized by BQ; reproducible
   locally via `build_facts.py`.
2. **Scoring math** — implemented in `scoring.py` (Python) and mirrored in
   `pipeline_and_tests/sql/avri/avri_account.sql` (BigQuery). The snapshot
   test in `test_scoring.py` is the cross-check.
3. **Aggregation property** — RV decomposes by linearity:

       RV_aggregate = Σ (ARR × AVRI/100) over children
                    = TotalARR × DollarWeightedAvgAVRI / 100

   This holds at every level: region, segment, CSM, account. Tested by
   `test_aggregation_sums_match_account_level`.

4. **Pillar decomposition** — unrealized $ attributes cleanly to each pillar:

       Unrealized = ARR × (1 − AVRI/100)
                  = ARR × Σ_pillar (weight × (100 − pillar_score) / 100)

   Plus a `unrealized_floor` residual when the floor rule fires. The five
   contributions sum to total unrealized $ within rounding (tested).

## Running tests

```bash
# From project root
python -m pytest core/test_scoring.py -v

# Or directly
cd core && python -m pytest test_scoring.py -v
```

After intentional config or scoring changes, refresh the golden snapshot:

```bash
cd core && python -m core.test_scoring --update-golden
```

## Editing config_v1.json

The dashboard's Calibration tab provides a sandbox for previewing parameter
changes without touching this file. **In production**, this file is the
source of truth and changes go through code review like any other code
change. Don't edit on the fly during a presentation; the version field is
there to surface inadvertent drift.

## RV formula

v2.0 uses **linear** RV: `RV = ARR × AVRI/100`. Three reasons:

1. **Decomposable.** Linear sums clean across pillars and aggregations.
   Quadratic doesn't.
2. **Defensible.** AVRI directly estimates realization rate; multiply by
   ARR for dollars. No curvature to justify without renewal data.
3. **Calibratable.** v3 candidate is to fit a non-linear function from
   historical renewal outcomes. The config schema's `rv_formula.type`
   field accepts `linear` or `quadratic`; future values can be added.
