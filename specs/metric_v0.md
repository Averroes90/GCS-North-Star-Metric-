# Metric v0: Account Value Realization Index (AVRI)

> **READ ME FIRST.** This is the *historical* v0 spec. The pipeline and dashboard implement **v2.0** — see [`metric_v1.md`](metric_v1.md) for the v0→v1.3 diff (grace period, floor rule refinement) and [`metric_v2.md`](metric_v2.md) for v2.0 (Realized Value addition, calibration centralization, pillar decomposition). v0 is preserved for narrative purposes — the "before" state in the inductive workflow. Read v0 → v1 → v2 → `inspection_findings.md` to see why each evolution was earned.

**Status:** Initial hypothesis (frozen). Refined inductively after Phase 3 inspection.
**Owner:** Principal IT PM, GCS
**Audience:** Self / data-gen agent / pipeline implementer

---

## 1. The metric in one sentence

**AVRI** is a 0–100 composite score, computed at the `account_id` level and rolled up to `csm_id` and `region`, that measures whether a customer is realizing the value of what they purchased, combining commit-to-consumption fit, usage momentum, deployment maturity, and technical health.

---

## 2. Why a composite (not a single metric)

The brief asks the metric to balance four dimensions: initial **bookings**, full **deployment**, **technical health**, and **sustained usage**. No single existing metric covers all four (see `metrics-explorer.html`). A composite is the only honest answer; the design problem is *which components, weighted how, with what edge-case rules*.

---

## 3. The four pillars

Each pillar is computed as a 0–100 sub-score, then weighted into the final AVRI. The pillars map 1:1 to the four dimensions in the brief.

### Pillar 1: Commit Realization (CR): weight 30%
**Captures:** Bookings ↔ Usage fit.
**Inputs:** `Contracts.included_monthly_compute_credits`, `Daily_Usage_Logs.compute_credits_consumed`.
**Calculation:** Trailing-90-day consumed credits / (3 × included_monthly_compute_credits).
**Score curve:** Piecewise rather than linear, because both under- and over-consumption are signals:
- 0–50% utilization → score = utilization × 100 (under-realized)
- 50–110% → score = 100 (sweet spot)
- 110–150% → score = 100 (still healthy; flagged as expansion candidate)
- 150%+ → score = max(60, 100 − (util − 150) × 0.5) (capacity warning, but not a failure)

**Why piecewise:** A linear utilization metric punishes overages as if they were equivalent to underuse. They are not. Overages are positive churn signals.

### Pillar 2: Usage Momentum (UM): weight 30%
**Captures:** Sustained usage over the lifecycle, with explicit trajectory awareness. The differentiator vs Gainsight CHS, which is snapshot-only.
**Inputs:** `Daily_Usage_Logs.compute_credits_consumed`.
**Calculation:** Ratio of last-90-day daily average consumption to trailing-12-month daily average. Anchors level against trajectory.
**Score curve:**
- ratio ≥ 1.0 → 100
- 0.7 ≤ ratio < 1.0 → 70 + (ratio − 0.7) × 100
- 0.3 ≤ ratio < 0.7 → 30 + (ratio − 0.3) × 100
- ratio < 0.3 → ratio × 100 (severe decay)

**Why this matters:** This is the pillar that catches Spike-and-Drop. An account that burned 90% of credits in Month 1 and nothing since has CR ≈ 100 (annualized) but UM near 0. The composite drops accordingly.

### Pillar 3: Deployment Maturity (DM): weight 20%
**Captures:** Whether the product is actually operationalized, the proxy in this synthetic dataset is **breadth of active days** (we do not have license/feature data per the schema). In production this pillar would also pull license provisioning %, feature adoption breadth, and onboarding milestone attainment.
**Inputs:** `Daily_Usage_Logs` (count of distinct active days).
**Calculation:** active_days_last_90 / 90.
**Score curve:** Linear, 0 → 0, 1.0 → 100.
**Why this matters:** Distinguishes "burned credits in 5 big bursts" (low DM) from "consistent daily use" (high DM). Two accounts with identical CR can have very different DM.

### Pillar 4: Technical Health (TH): weight 20%
**Captures:** The technical/operational health overlay. Synthetic-data proxy is `Account_Health.health_color` (green/yellow/red), exponentially weighted toward recent observations. In production, this pillar would be driven by Sev-1 frequency, SLA attainment, and active escalations.
**Inputs:** `Account_Health.health_color`, `Account_Health.date`.
**Calculation:** `Σ(color_score_t × decay^age_t) / Σ(decay^age_t)` over last 90 days, where `color_score = {green: 100, yellow: 50, red: 0}` and `decay = 0.95`.
**Score curve:** Direct (already 0–100).
**Why this matters:** A fully consumed, fully deployed account can still be a renewal risk if it's technically painful. Tech health is the hygiene layer.

---

## 4. Composite formula

```
AVRI_raw = 0.30·CR + 0.30·UM + 0.20·DM + 0.20·TH

# Floor rule: technical health cannot be papered over
if TH < 30:
    AVRI = min(AVRI_raw, 50)
else:
    AVRI = AVRI_raw
```

**Why the floor rule:** Linear weighted averages are substitutable, high CR can mathematically offset low TH. In reality, a customer with critical platform issues will not renew regardless of their consumption. The floor rule expresses a non-substitutability that pure weighted averaging cannot.

---

## 5. RAG thresholds

| Color | Range | Interpretation |
|---|---|---|
| **Green** | AVRI ≥ 75 | Healthy. Renewal trajectory positive. Eligible for expansion conversations. |
| **Yellow** | 50 ≤ AVRI < 75 | Watch. Specific pillar(s) underperforming. CSM intervention recommended. |
| **Red** | AVRI < 50 | At risk. Active renewal risk. Escalate to leadership review. |

Thresholds are set heuristically in v0. **Production calibration plan:** regress historical AVRI against actual renewal outcomes and choose thresholds that maximize predictive accuracy at the green/yellow and yellow/red boundaries.

---

## 6. Edge case treatment (from brief)

| Edge Case | Pillar Behavior | Net AVRI Impact |
|---|---|---|
| **Spike & Drop** (5%) | CR high (annualized), **UM near 0**, DM low, TH any | AVRI lands in Yellow/Red. Caught by UM. |
| **Shelfware** (10%) | CR ≈ 0, UM ≈ 0, DM ≈ 0, TH any | AVRI deep Red regardless of TH. Three pillars collapse. |
| **Consistent Overages** (15%) | CR = 100 (sweet spot, even at 130% util), UM stable, DM high, TH any | AVRI high. Correctly rewards engaged customers. *Diagnostic flag* exposed separately as "Capacity Risk." |
| **Mid-Year Expansion** | Contract precedence: at any point in time, use the **sum of active commits** for any contract whose date range covers that point. Overlap windows aggregate, not double-count. | No distortion. Documented in pipeline. |
| **Orphaned/Rogue Usage** | Pipeline rejects records where `account_id` not in Accounts, or `date` outside any active contract for that account. Rejected records reported via DQ test, never silently dropped. | Quarantined; not included in metric. |

---

## 7. Aggregation rules

- **Account-level:** AVRI computed from raw signals as above.
- **CSM-level:** Dollar-weighted average of account AVRIs in the CSM's book, where weight = `annual_commit_dollars`. Rationale: a CSM's portfolio health should not be dominated by long-tail accounts.
- **Region-level:** Same dollar-weighted rollup across all CSMs in the region.

---

## 8. What the metric explicitly does NOT do (v0 scope)

- No predictive ML model. AVRI is a transparent rules-based scorecard. A future v2 could layer a churn-probability model on top, but explainability matters for comp plans, the panel will challenge any black box.
- No per-segment weight tuning yet. v0 uses one weight set across Enterprise and Mid-Market. v1 should fork weights by segment.
- No NPS/sentiment input. The brief's schema does not include survey data.
- No expansion ARR or financial-trajectory pillar. Deliberately. AVRI measures *health*, not *growth*. They should be separate, complementary metrics on the dashboard.

---

## 9. Open design questions to revisit

1. **Weight calibration:** Are 30/30/20/20 defensible? Production answer is to regress against renewal outcomes; v0 anchors on intuition.
2. **Trend window:** Is 90-day the right momentum window, or should it be 60? Shorter = more responsive, more noise.
3. **Per-segment weights:** Do Enterprise and Mid-Market deserve different pillar weights? Probably yes, Enterprise typically over-indexes on TH, Mid-Market on UM.
4. **Comp-plan integration:** Which AVRI components, if any, should drive variable comp? Any answer creates gameability risk in that component.
5. **Capacity Risk side-flag:** Should accounts in the 110–150% utilization band trigger a separate alert independent of AVRI?
6. **Treatment of brand-new accounts (<90 days tenure):** Cold-start problem, UM and DM windows aren't valid yet. Need a tenure adjustment or "Onboarding" RAG state.

---

## 10. Anchoring decisions for the data generator

This spec implies the data generator must produce time series that are **realistic enough for AVRI to discriminate between healthy and unhealthy accounts.** Specifically:

- Daily usage logs must have realistic *temporal shape* (not uniform random), ramps, plateaus, decays, weekly seasonality.
- Edge case patterns must be **detectable by AVRI's pillars**, not just statistically present. A "spike and drop" that decays gradually over 6 months is invisible to a 90-day momentum window; the brief's pattern of "Month 1 burst, then near zero" is what we should generate.
- `Account_Health.health_color` must have temporal coherence (not flip every day). Use a Markov-chain-style transition.
- Mid-year expansion contracts must overlap by a meaningful window (at least 30 days) to actually exercise the precedence logic.

These constraints will move into `/specs/data_generation_spec.md` next.
