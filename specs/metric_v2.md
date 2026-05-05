# Metric v2.0 — Realized Value (RV) addition

_v1.3 status: stable. v2.0 adds RV as a complementary dimension and centralizes calibration. Implemented in `core/scoring.py` and `core/config_v1.json`._

## What changed in v2

1. **Realized Value (RV) — new metric.** A scale-aware composition of AVRI and ARR. Linear: `RV = ARR × (AVRI/100)`.
2. **Calibration centralized.** All weights, thresholds, decay rates, and curve breakpoints moved from SQL/Python literals into `core/config_v1.json`. Pipeline and dashboard read the same file.
3. **Pillar decomposition of unrealized $.** Falls out of linear math. Surfaces *which pillar is dragging which aggregate*.
4. **Pillar heatmap** as the primary diagnostic view in the dashboard. Replaces "AVRI distribution" as the landing page.
5. **Activation grace extended to RV.** In-grace contracts excluded from both ARR and RV — signing never penalizes the CSM, in either metric.

AVRI itself is unchanged. v2 adds a layer above it; it does not modify v1.3 scoring.

---

## 1. Why RV exists

v1.3 AVRI is a *quality* index — a 0–100 score that estimates how well an account is realizing the value of what it bought. By design, it is segment-fair and scale-blind: a CSM with a $25M book at AVRI=80 ranks identically to a CSM with a $1M book at AVRI=80. This is correct for *performance evaluation* (you don't reward someone for being assigned to a bigger book) but wrong for *executive decision-making* (which CSM has more $ on the line is a real question).

RV closes that gap without distorting AVRI. It composes the two:

> **RV = ARR × AVRI/100.**
>
> *AVRI is velocity. RV is momentum. Both belong on the dashboard, neither replaces the other.*

The metric architecture is now:

- **AVRI** — quality of execution. Comp-grade signal. Used for CSM ranking and performance review.
- **RV** — value at stake. Risk-grade signal. Used for executive triage, prioritization, and answering "where are dollars leaking?"
- **Unrealized $ (= ARR − RV)** — operational signal. Used by individual CSMs to triage their book.

These three answer different questions and live on different surfaces. They do *not* combine into a single score; collapsing them would re-introduce exactly the trade-off AVRI was designed to eliminate.

---

## 2. The formula

```
RV   = ARR × (AVRI / 100)              [linear, v2 default]
Unr  = ARR − RV
     = ARR × (1 − AVRI / 100)
```

Decomposition by pillar (linearity makes this clean):

```
Unr  = ARR × Σ_pillar [weight × (100 − pillar_score) / 100]
     = ARR × [0.30 × (100−CR)/100
              + 0.30 × (100−UM)/100
              + 0.20 × (100−DM)/100
              + 0.20 × (100−TH)/100]   if floor rule didn't fire
```

When the floor rule fires (TH < 30), AVRI is capped at 50, which produces *more* unrealized $ than the weighted-pillar sum predicts. The residual is attributed to a separate `unrealized_floor` line item. The five contributions sum to total unrealized $ within rounding tolerance — verified by `test_rv_decomposition_adds_up`.

### Aggregation property

Because RV is linear in AVRI and ARR is additive, RV decomposes cleanly at every aggregate level:

```
RV_org    = Σ_account (ARR_i × AVRI_i / 100)
          = Σ_region (Σ_csm Σ_account (ARR × AVRI / 100))
          = TotalARR × DollarWeightedAvgAVRI / 100   [factored form]
```

This is a non-trivial property. It means:

- The dashboard can drill from $311M total → $190M AMER → $7M for one CSM → $500K for one account, and at every level the numbers reconcile to their parent.
- The pillar heatmap is *exactly* the metric, not an approximation.
- Realization rate is interpretable at any aggregate: *"AMER is realizing 79% of its book."*

Quadratic and sigmoidal RV alternatives **do not factor cleanly**. They were considered and rejected for v2 — see Section 4.

---

## 3. Calibration architecture

All v1.3 magic numbers — pillar weights, util-curve breakpoints, decay rate, color thresholds, grace period rules — moved into `core/config_v1.json`. The Python implementation in `core/scoring.py` reads this config; the SQL pipeline reads it via templating (the `{project}.{dataset}` substitution mechanism is extended for config values in v2.1+ — for v2.0, the SQL hardcodes match the config defaults and a snapshot test cross-checks).

The dashboard's new **Calibration** tab provides a sandbox: sliders and inputs for every parameter, plus a sticky banner reminding the viewer that production runs from the locked default config. Edits don't persist; reset returns to defaults.

This serves three purposes:
1. **Demonstrates** that no number in the metric is buried magic — every threshold is named, located in one file, and surfaced in the UI.
2. **Provides what-if** capability for calibration discussions: *"what if we drop CR's weight to 0.25?"* shows the effect across all rollups in real time.
3. **Documents** the v3 calibration roadmap: when real renewal data is available, this is where fitted parameters land.

---

## 4. Why linear (and not quadratic or sigmoidal)

Three formulas were on the table:

| Formula | Interpretation | Defensibility |
|---|---|---|
| Linear: `ARR × AVRI/100` | AVRI directly estimates realization rate | One-line panel defense; decomposable; no hidden curvature |
| Quadratic: `ARR × (AVRI/100)²` | Convex; punishes mediocrity disproportionately | Requires renewal data to defend the convexity |
| Sigmoidal: `ARR × σ(k·(AVRI−c))` | Empirically standard for churn modeling | Two parameters (k, c) need fitting from renewal outcomes |

**v2 chose linear for three reasons:**

1. **Decomposability.** Only linear factors cleanly across pillars and aggregates. Quadratic and sigmoidal don't, which would force the dashboard to either misrepresent the math or surface arithmetic that doesn't add up.

2. **Empirical honesty.** Without renewal-outcome data, the convexity in quadratic is a speculation about the AVRI-to-renewal-revenue curve. Inspired by general observations in CS literature (Bain on NPS-revenue, churn-modeling default of logistic regression) but not specifically validated on this dataset. Choosing linear keeps us from defending a curvature we can't justify.

3. **Calibratable.** v3 candidate work is to fit the actual function from historical renewals. Linear is the conservative starting point; replacing it later doesn't require restructuring anything except the `rv_formula.type` field in the config.

The lesson — captured in `lessons_learned.md` entries 16–19 — is that the kinetic-energy analogy was a good *story device* but a poor *derivation*. Mass-as-extensive plus curvature-on-quality is good physics intuition, but AVRI doesn't have an integral structure that produces v² from anywhere. Linear is the more honest v1.

---

## 5. Where RV is *not* used

This is as important as where it is used.

- **Not for CSM performance ranking.** Empirical check (Phase D scratch work): under RV-as-ranking, AMER Enterprise CSMs with $14–18M books at AVRI=44 outrank Mid-Market CSMs at AVRI=89 with $1M books. That's mechanically rewarding segment assignment, not performance. Comp plans should stay AVRI-based.
- **Not for comparing across segments at the individual level.** A $5M renewal landmine at AVRI=20 and a $50K perfect account at AVRI=100 are differently-shaped problems. RV gives us "$4M unrealized" vs "$0 unrealized" — useful for triage. It does not tell us which CSM is doing better work.
- **Not as a single replacement for AVRI.** AVRI continues to exist, continues to power CSM evaluation, continues to drive the case-study narratives.

---

## 6. Implementation surfaces

| Surface | Change |
|---|---|
| `core/scoring.py` | New module. Pure functions consumed by pipeline tests and dashboard. |
| `core/config_v1.json` | All calibration params. |
| `pipeline_and_tests/sql/avri/avri_account.sql` | Added `rv_dollars` + 5 pillar-attribution columns. |
| `pipeline_and_tests/sql/avri/avri_csm.sql` | Added `book_rv_dollars`, `realization_rate`, pillar totals. |
| `pipeline_and_tests/sql/avri/avri_region.sql` | Same as CSM. |
| `pipeline_and_tests/test_data_quality.py` | +5 tests (Section 5: TestRealizedValue). Total 24→29. |
| `pipeline_and_tests/snapshot_pillar_decomposition.py` | New. BQ-backed JSON snapshot for lobby. |
| `dashboard/app.py` | New Realized Value tab (heatmap, headline, drill). New Calibration tab. Existing tabs read scores via `core/scoring.py`. |
| `metrics-explorer.html` | New Realized Value tab. Project Map adds Phase 6. Defending Choices, AVRI vs CHS Stories, Architecture, Schema-to-Metric updated. |
| `AVRI_Deck.pptx` | New slide 5 (Quality × Scale = RV). Light edits to slides 2, 4. Slide 6 (Proof) gains RV/unrealized $ line per case card. Slide 7 (Retro) refreshes v2 roadmap. Total 7→8 slides. |

---

## 7. Open questions for v3

- **Per-segment AVRI weights.** Enterprise probably over-indexes on TH; Mid-Market on UM. v3 fits these per segment from renewal outcomes.
- **Sigmoidal RV formula.** Once renewal data exists, refit the AVRI-to-realization function. May be sigmoidal; may turn out linear is fine.
- **Multi-period RV.** Current RV is single-snapshot. A v3 might compose 4 quarters of RV trailing — a "trailing realized value" that's less spiky than any single snapshot.
- **Comp-plan integration.** AVRI is the comp metric of choice; whether RV should appear in any compensation-adjacent capacity (e.g., "RV improvement YoY" as a stretch goal) is a v4 conversation.
