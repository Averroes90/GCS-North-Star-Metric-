# Lessons Learned: running log

A running log of the technical pitfalls, design tensions, and surprises encountered during this project. Source material for the **Retrospective slide** in the executive deck, and a useful artifact for any PM facing a similar problem in future.

Each entry records what happened, why, the fix, and the generalizable lesson.

---

## 1. Inductive vs deductive metric design

**When:** Phase 1, before any code was written.

**What happened:** Initial instinct was the deductive path, design AVRI first, then generate data calibrated to demonstrate it works. The user pushed back: build realistic data first, observe where existing metrics fail, derive the metric in response.

**Lesson:** When designing metrics from synthetic data, the inductive workflow produces a much stronger interview/exec narrative. *"I built data the way the world looks; here's where every existing metric fails it; here's the metric that doesn't"* is harder to dismiss than *"I designed a metric and engineered data to validate it."* The deductive path also creates a circular validation risk: you tune the data to make your metric look good, then claim it works.

**Generalization:** Whenever the data is yours to shape, deliberately resist shaping it to favor your hypothesis.

---

## 2. numpy Generator capped at int64: UUID bug

**When:** First run of `data_generation/main.py`.

**Symptom:** `ValueError: high is out of bounds for int64` when generating UUIDs via `rng.integers(0, 2**128)`.

**Cause:** numpy's seeded `Generator.integers()` only handles up to int64 (2^63 - 1). UUIDs are 128 bits.

**Fix:** Compose two 64-bit integer draws and shift-OR them: `(high << 64) | low`. See `_make_uuid()` in `data_generation/generate.py`.

**Lesson:** numpy's deterministic RNG is convenient but has tighter bounds than Python's stdlib `random`. For 128-bit values, compose from two 64-bit draws, don't fall back to `random.randint()` because it breaks reproducibility from the seed.

---

## 3. Persona distribution sampling variance vs validation tolerance

**When:** First successful generator run.

**Symptom:** Validation gate failed: `persona healthy_growing dist 0.126 differs from target 0.150 by >2pp`.

**Cause:** Statistical sampling variance. With N=1000 accounts and a 7-class categorical, ±2pp is tight on every persona simultaneously. The expected standard deviation of any single bucket's proportion at N=1000 is roughly √(p(1-p)/N), for p=0.15 that's ~1.1pp, so a 2.4pp deviation is well within normal sampling.

**Fix:** Loosened tolerance to ±3pp.

**Lesson:** Validation tolerances must reflect sample size. The "right" tolerance is approximately 2σ, which depends on N. Hard-coded thresholds without thought to N create false-failure noise.

---

## 4. Parquet date types vs BigQuery DATE: round-trip mismatch

**When:** First BigQuery load attempt.

**Symptom:** `Parquet column 'end_date' has type INT64 which does not match the target cpp_type INT32.`

**Cause:** When pandas writes a `datetime64[ns]` column to Parquet, pyarrow stores it as `timestamp[ns]` (INT64 nanoseconds since epoch). BigQuery's DATE column is INT32 (days since epoch). Loader rejects the type mismatch.

**Fix:** Convert date columns with `.dt.date` before writing, produces Python `date` objects (object dtype in pandas), which pyarrow stores as `date32[day]` in Parquet, which BigQuery loads cleanly into DATE.

**Lesson:** "Date" and "Timestamp" are distinct types at every layer of the stack. Even when conceptually you mean a date, if it's stored as a timestamp, downstream type-checked systems will reject it. Always verify the actual storage type after a round-trip, not just the in-memory representation.

---

## 5. BigQuery LoadJobConfig: schema_update_options doesn't compose with WRITE_TRUNCATE

**When:** First BQ load attempt with explicit schema.

**Symptom:** `Schema update options should only be specified with WRITE_APPEND disposition, or with WRITE_TRUNCATE disposition on a table partition.`

**Cause:** `schema_update_options=[ALLOW_FIELD_ADDITION]` is meaningful only when adding to an existing schema. With WRITE_TRUNCATE on a non-partitioned table, the schema is being replaced entirely, so the option is contradictory.

**Fix:** Remove the option, when providing a full explicit schema with WRITE_TRUNCATE, no update options are needed.

**Lesson:** BQ load options have non-obvious composition rules. If the option doesn't apply to your write disposition, you'll get an error rather than a silent ignore. Read the option's documentation in context of your disposition.

---

## 6. gcloud CLI vs ADC: two different login commands

**When:** Phase 2, BigQuery setup.

**Symptom:** User ran `gcloud auth login` and tried Python BQ client, got "Compute Engine Metadata server unavailable" errors.

**Cause:** `gcloud auth login` authenticates the gcloud CLI itself (so you can run `gcloud` commands). `gcloud auth application-default login` writes the credential file (`~/.config/gcloud/application_default_credentials.json`) that Python SDK libraries use. They're separate.

**Fix:** Run `gcloud auth application-default login` explicitly.

**Lesson:** When onboarding non-Google-Cloud-native users to BQ, surface this distinction up front. The "Compute Engine Metadata server" error message is misleading, it's gcloud trying a fallback auth method appropriate for code running on a GCP VM, not the actual problem.

---

## 7. AVRI scoring accounts that aren't currently customers

**When:** Phase 3.3 inspection.

**Symptom:** Top-N "naive CHS overscored AVRI" results were dominated by accounts with `arr_dollars = 0` and every pillar at 0. These weren't useful comparisons, they were accounts whose contract had ended.

**Cause:** AVRI was being computed for every row in the `accounts` table regardless of whether the account had an active contract on the snapshot date. Accounts with expired contracts got scored as zeros, which is technically correct ("no value being realized") but pollutes the metric and the comparisons.

**Fix:** Add an `accounts_in_scope` filter to the pipeline, only score accounts with at least one active contract on the as-of date. Out-of-scope accounts get NULL, not 0.

**Lesson:** Every metric needs an explicit *scope definition*: which entities is it meant to score? Don't assume "all rows in the entity table." For lifecycle metrics in particular, status-at-snapshot matters as much as the metric formula. This deserves a dedicated section in the spec.

---

## 8. Spike-and-drop and shelfware look identical on a 90-day snapshot

**When:** Phase 3.3 inspection.

**Symptom:** The query `cr_score > 60 AND um_score < 30` (intended to surface spike-and-drop) returned zero rows.

**Cause:** Both spike-and-drop and shelfware accounts present as low CR + low UM in the trailing 90-day window. For spike-and-drop, the burst event happened 6–12 months ago, which is outside the CR window. UM correctly tanks (because the 365-day average is much higher than the 90-day average). But CR also tanks because there's been almost no recent consumption.

**Functional impact:** None, AVRI correctly scores both as deep red. *Narrative impact:* the deck loses one of the visual stories I'd hoped for ("UM uniquely catches what CR misses").

**Fix:** Move the visual differentiation to the dashboard's account drill-down view. A 12-month time series visually separates them, spike-and-drop has a tall bar in month 1 and zeros after; shelfware is flat zero throughout. Same end-state, different causal pathway, only visible in the trajectory.

**Lesson:** Snapshot metrics conflate similar end-states from different causal pathways. Time-series visualization is essential for diagnosis, even when the score itself is correct.

---

## 9. UM ratio undefined / misleading at zero baseline

**When:** Inspection.

**Observation:** Some shelfware accounts had UM = 100 ("perfect momentum") despite near-zero absolute usage. The ratio of two near-zero numbers is mathematically ~1.0.

**Cause:** UM measures *change* in level (90d avg / 365d avg), not absolute level. A flat-zero pattern has no change → ratio 1.0 → score 100. The metric is technically correct, momentum is fine; the level is what's broken.

**First-pass reaction:** Saved by CR and DM also being 0, so the composite still tanks correctly. Worth noting but not fixing.

**Second-pass reaction (after v1 inspection):** The bug bites harder than expected. ~15-25 borderline shelfware accounts (very low usage but with occasional health-color green) end up at AVRI ~50 (Yellow) when they should be Red. With UM=100 and TH high, only CR and DM tanking isn't enough to push them under 50. Fix needed.

**Fix (v1.1):** Two changes to UM calculation:
1. Compute averages as `SUM/N` (where N = days in window), not `AVG` over present rows. This makes missing days count as zero in the denominator.
2. Add a **level guard**: if total trailing-365 consumption is less than 5% of annual commit, UM = 0 regardless of ratio. Rationale: 5% of annual commit ≈ 18 days of full-rate usage. Below that, the account has not meaningfully adopted the product, and momentum is undefined.

**Lesson:** Ratio metrics need absolute-level guardrails. A single ratio in isolation can produce nonsensical readings at the edges of the input distribution. The composite buffer ("other pillars will tank it") fails for accounts with mixed signals (low usage + good health color). Add the guardrail at the pillar level, not at the composite.

---

## 10. Naive CHS distribution skewed by inactive accounts

**When:** Inspection.

**Symptom:** AVRI showed *more* green and *fewer* red than naive CHS (533/187/280 vs 451/167/382). Counterintuitive, the deck narrative needs AVRI to be the *more conservative* metric (surfacing risk hidden by existing metrics).

**Cause:** The naive CHS includes "has-ARR" as a 10% component. Accounts with no active contract get a 0 from that component, dragging their CHS lower than they'd otherwise score. AVRI scores them at 0 across the board (which is also wrong per #7). Both metrics are mishandling out-of-scope accounts in different ways, and the comparison is therefore meaningless.

**Fix:** Apply the in-scope filter to *both* AVRI and the naive CHS. After filtering, the comparison should show AVRI as the more conservative metric, which is the right narrative.

**Lesson:** Comparison metrics need apples-to-apples scope filters. Different metrics often handle out-of-scope entities differently, and the differences leak into the headline distribution comparison without anyone noticing.

---

## 11. Level guard creates a cold-start concern

**When:** Inspection of v1.1 output.

**Observation:** The 5%-of-annual-commit level guard correctly zeroes UM for shelfware accounts. But it also zeroes UM for accounts whose contracts only started 1-3 months ago, they haven't had time to accumulate 5% of annual commit yet, even if they're ramping healthily.

**Functional impact:** Modest. New accounts in early ramp can be incorrectly classed as Red. From the inspection view, hard to distinguish "new and ramping" from "established but never adopted" without contract start date as a column.

**Mitigation (v2):** Tenure-aware scoring. If contract is <90 days old, either (a) skip UM and let the other pillars carry the score, (b) compute UM over the available tenure window only, or (c) introduce an "Onboarding" RAG state that's neither Red/Yellow/Green.

**Why not fix now:** The case study evaluates v1; cold-start is documented as a v0 known limitation in `metric_v0.md` Section 9 already. Fixing properly requires schema changes (need contract age in the AVRI table) and a fifth RAG state.

**Lesson:** Pillar-level guards solve one edge case (zero baseline) but can introduce another (cold start). When tightening a metric to handle one pathology, audit whether it creates a new failure mode at a different boundary.

---

## 12. BigQuery SQL gotchas (collected from dashboard debugging)

**When:** Phase 4, first dashboard run.

**Pattern:** Five separate query failures in quick succession on first dashboard run. None were architectural; all were SQL syntax / naming issues that are easy to make and easy to fix once you know the rule. Collected here as reference because they will absolutely come up again in any BigQuery work.

**12a, `at` is a reserved keyword.** Aliasing a CTE as `at` (e.g., `LEFT JOIN account_tenure at ON ...`) errors with cryptic "Expected ')' but got AT". Lesson: avoid 2-character aliases that match SQL keywords (`at`, `as`, `or`, `in`, `is`, etc.). Use 3+ character aliases.

**12b, `ORDER BY` inside `UNION ALL` arms requires parentheses.** This errors:
```sql
SELECT * FROM ranked ORDER BY x DESC LIMIT 5
UNION ALL
SELECT * FROM ranked ORDER BY x ASC LIMIT 5
```
Fix: use `ROW_NUMBER() OVER (...)` window functions to label rows, then `WHERE rk <= 5` in each arm. Cleaner and portable.

**12c, Column doesn't exist on the source you think it does.** Aliased a column in a downstream view (`avri_csm.csm_name`), then tried to reference `csm_name` directly off `csm_rep` (where it's just `name`). Lesson: keep mental model of what columns exist on which table; don't assume aliases propagate.

**12d, `ORDER BY r.alias` doesn't work for SELECT-clause aliases.** BigQuery's ORDER BY can reference output column aliases by bare name, but not via table prefix. `ORDER BY r.avri` errors because `avri` is the alias, not a column on `r`. Fix: just `ORDER BY avri`.

**12e, Schema drift between SQL files.** Referenced `commit_90d_credits` in the dashboard query, but `metrics_existing_account` only exposes `monthly_commit_credits`. The 90-day version had to be computed inline (`monthly_commit_credits * 3`). Lesson: when deriving columns at the consumption layer, check the actual materialized schema, not what you thought you put there.

**General lesson:** SQL is tightly typed. The errors are loud and fast, you don't ship wrong answers, you ship clear failures. That's the right failure mode. If the equivalent code were pandas in Python, these mistakes would silently produce wrong numbers and you'd discover them in the deck. Trust the type system.

---

## 13. Streamlit cache staleness

**When:** Phase 4, post-fix iteration.

**Symptom:** Fixed an SQL query in `app.py`, hit save, refreshed the browser, still saw the old error.

**Cause:** Streamlit's `@st.cache_data(ttl=600)` caches function outputs by argument hash. When the underlying SQL string changes, the cache key changes, but if you fixed the SQL and the BQ error was *cached* from the previous query, the cached error gets served back.

**Fix:** Hamburger menu → Clear cache → Rerun. Or hard-stop the Streamlit process and restart.

**Lesson:** Aggressive caching is fast in steady state and confusing during development. For the production demo this is fine; for iteration it's worth setting `ttl=0` temporarily or invalidating manually.

---

## 14. Multicollinearity in composite pillars: TH proxy leaks the consumption signal

**When:** Q&A prep review of metric_v1.2.

**Concern raised:** AVRI claims to balance four independent dimensions. But in v1.2, the TH pillar reads `account_health.health_color`, which in real systems is a CSM-set rating that's partly informed by usage levels. So TH is partly correlated with the CR/UM/DM pillars (which are all derived from consumption data). The composite may be measuring 3 dimensions plus a noisy proxy of one of them, not 4 independent dimensions.

**In our synthetic data, the correlation is real by construction:**
- Shelfware persona: low consumption AND drifts to red.
- Spike-and-drop persona: low recent consumption AND drifts to red after Month 1.
- Healthy personas: normal consumption AND stays green.

So `health_color` is partially correlated with the consumption pillars even in our generated data.

**Why it doesn't fully break AVRI:**

AVRI is not a regression. We're not estimating coefficients statistically; we're declaring weights heuristically. So strict multicollinearity (which destabilizes coefficient estimates in regression models) doesn't directly degrade AVRI's stability. But the softer concern is real: if TH leaks the consumption signal, "usage" is implicitly weighted >60% in the composite even though the explicit weights say 60%. The "four independent pillars" framing slightly overstates the orthogonality.

**Why CR / UM / DM are decorrelated by design** (despite all being usage-derived):
- CR measures **level** (consumed vs commit, last 90 days)
- UM measures **trend** (recent 90d / trailing 365d ratio)
- DM measures **breadth** (count of distinct active days last 90)

A 95% utilization account can have high or low UM depending on trajectory. High DM doesn't imply high CR (could be daily but tiny consumption). Spike-and-drop has high DM in Month 1 and low DM after, with the same source data producing very different signals. They encode distinct features even from a shared source.

**The fix (v2 plan):** Replace `health_color` with three signals that are genuinely orthogonal to consumption:
- **Sev-1 frequency** — about platform reliability for the customer; independent of how much they use
- **SLA attainment %** — about whether PANW met its commitments; independent of usage
- **Active escalation count** — about relationship dysfunction; independent of usage

These signals require schema additions (tickets table, SLA log, escalation log) that aren't in the brief's data model. metric_v0.md and metric_v1.md already document this as the v2 path; this entry makes the *reason* explicit.

**Day-30 production milestone:** compute the correlation matrix between pillar scores on real data.
- If `corr(TH, CR/UM/DM) > 0.6`: confirms heavy redundancy → accelerate the proxy replacement.
- If `corr(TH, CR/UM/DM) < 0.3`: proxy is doing more independent work than feared → keep `health_color` and add the orthogonal signals as additive enrichments rather than replacements.

**Lesson:** When designing a composite from a thin schema, audit your "independent" components for shared upstream causes. A pillar that *appears* orthogonal because it has a different *name* may not be orthogonal in *signal*. The right defense is a measured correlation matrix, not a designed-in claim of independence.

**Q&A defense scripted:**
> *"You're right that TH is the weakest pillar in terms of orthogonality. In v1.2, `health_color` is a CSM-rated proxy that partly leaks the consumption signal back in. The v2 fix is to replace it with three independent inputs — Sev-1 frequency, SLA attainment, exec escalations — that measure platform reliability and relationship health, not usage. Once those replace the proxy, TH becomes truly independent of CR/UM/DM. Day-30 milestone is to compute the actual correlation matrix and let the data confirm whether the swap is urgent or incremental."*

---

## 15. Bookings rewards: cold-start trap and the Activation Grace Period (v1.3)

**When:** Q&A prep, working through the brief's "balances initial contract bookings" requirement.

**The flaw discovered:** v1.2 AVRI did not reward new bookings — and in practice, *penalized* them. The moment a contract was signed, it counted in CR's denominator. Consumption hadn't yet ramped (cold-start), so CR scored low for ~90 days. A CSM who landed $2M of new ARR could *lower* their dollar-weighted AVRI vs a CSM who landed nothing, because the new accounts at $2M ARR were dragging the rollup down.

**Concrete example that broke the design:**
- CSM A: 20 stable healthy accounts, $5M ARR, all Green → CSM AVRI ~90
- CSM B: same 20 + 5 newly-signed accounts ($2M new) at AVRI ~30 (cold-start) → CSM AVRI ~78

CSM B was punished for landing new business. That's the wrong incentive shape.

**Two design alternatives considered:**

1. **Commercial Health pillar** — explicit 5th pillar rewarding active contracts, multi-year commits, mid-year expansion. Risks: TCV-trap (rewards size); briefly masks shelfware-from-day-one accounts during the recency-bonus window; breaks "4 pillars for 4 dimensions" elegance.

2. **Activation Grace Period** — a contract is excluded from CR's denominator until it's "activated" by either Trigger A (cumulative usage ≥ 15% of monthly commit) or Trigger B (90 days since signing), whichever first. Accounts with all contracts in grace get NULL AVRI scores and an `onboarding` color. Adopted in v1.3.

**Why the grace period won:**
- **Solves the cold-start drop completely** — new contracts don't penalize during ramp
- **Doesn't reward raw size** — stays a value-realization metric philosophically
- **Catches shelfware-from-day-one** correctly via Trigger B at day 91
- **Mid-year expansion handled cleanly** — old contract continues scoring; new contract is in grace until it ramps
- **Smaller implementation footprint** — fits inside existing CR pillar; no re-weighting

**Parameter choices:**
- 15% threshold = ~4-5 days of full-rate usage in a month. Meaningful adoption without being unreachable.
- 90-day timeout = matches existing CR/UM/DM trailing windows; aligns with quarterly business reviews.
- Either trigger fires first → activates. Encourages fast ramp without rewarding it directly.
- All-grace accounts: NULL scores, `onboarding` color. Not falsely Red; visible in the table for diagnostics.

**Edge case audit:**

| Scenario | v1.2 behavior | v1.3 behavior |
|---|---|---|
| Brand new contract, ramps fast | Score drops then recovers | Stays neutral, then activates as Green |
| Brand new contract, never ramps | Drops, stays low | Stays neutral until day 91, then drops correctly |
| Mid-year expansion (existing healthy account) | Score temporarily drops (denominator inflation) | Old contract keeps scoring; new contract in grace; no drop |
| Multi-year contract | No effect | No effect (CS pillar would have rewarded; grace doesn't) |
| Contract renewal | No effect | No effect |

**What this design does NOT do:**
- Doesn't directly reward signing (no positive contribution for a contract existing)
- Doesn't reward multi-year commitments specifically
- Doesn't reward mid-year expansion as an event (just doesn't penalize it)

For panel responses asking "where do you reward bookings?": *"AVRI is the value-realization overlay; bookings stays measured commercially via ARR. The grace period ensures AVRI never penalizes the act of signing. If you want direct booking rewards inside AVRI, v2 candidate is an Initial Adoption Speed pillar — measures time-to-first-X% utilization. But that's bookings-adjacent, not bookings itself, by design."*

**Lesson:** When designing a metric that the brief asks to "balance" multiple dimensions, "balance" can mean either (a) explicit positive contribution from each dimension or (b) integrated treatment such that no single dimension dominates. The strict reading is (a); the generous reading is (b). For dimensions you don't want to *directly reward* (because rewarding them creates perverse incentives), the right move is to ensure they're *not penalized* either — neutrality. The grace period is the neutrality construct for bookings.

---

## 16. Scale-vs-quality tension; surfaced by user pushback, not first design pass

**The catch:** During v2 strategizing, the question came up: *"Two CSMs with identical % usage profiles but very different book sizes — does AVRI distinguish them?"* My initial answer was "no, by design — health is a ratio." That answer was wrong-shaped. The brief lists *bookings* as one of four dimensions to balance; we'd operationalized bookings as Commit Realization (a ratio), which addresses the *quality* of bookings but not their *scale*. Two CSMs at 80% util on $25M and $1M books are doing different jobs — both well, but different. AVRI alone treated them as identical. That's the dimension we'd skipped.

**The resolution:** RV (Realized Value) — `RV = ARR × AVRI/100` — adds the scale dimension *without* contaminating AVRI. AVRI stays the quality signal (segment-fair, comp-grade); RV lives at the executive-dashboard layer (scale-aware, $-grade). Three views on the same engine, three different consumers.

**Lesson:** When you've made an interpretive choice about how to operationalize a brief requirement, *flag it as a choice* in the spec. Don't bury it under "by design." The brief said balance four dimensions; we made bookings into a ratio; that was a choice, not a derivation. Adversarial reviewers (or just thoughtful users) will surface buried choices, and you want to be the one who surfaced them first.

---

## 17. KE analogy was a story device, not a derivation; chose linear RV instead

**The over-reach:** I initially proposed `RV = ARR × (AVRI/100)²` with the kinetic-energy analogy as justification — *"mass linear, velocity squared, like KE."* The user asked "are you sure that's the right power, or is this just speculation?" Pushed on it, I conceded: KE squares velocity because it falls out of `∫F·dx = ½mv²`, an integral structure that exists because position and velocity have a definite kinematic relationship. AVRI doesn't have an analogous structure that produces "(AVRI)²" from anywhere. The analogy is *suggestive*, not *implied*.

**The empirical-fit defense was also speculative.** I claimed CS literature shows sigmoidal renewal curves, and quadratic is a first-order approximation. What I actually know: logistic regression for churn prediction produces sigmoidal outputs *by construction of the model class*, not because the underlying reality is sigmoidal. The claim that "CS data shows" a particular AVRI-to-revenue shape was loose; I don't have a study to cite.

**The chosen path:** v2 ships linear RV. Three concrete reasons:
1. **Decomposability** — linear factors cleanly across pillars and aggregates; quadratic doesn't.
2. **Honesty** — without renewal data, we can't justify the convexity.
3. **Calibratability** — v3 fits the actual function from historical outcomes.

**Lesson:** A clean analogy can mislead the chooser before the chosen formula has been challenged. The user's "are you sure?" question is the move that broke the spell. When designing under uncertainty, the conservative version of a metric is the one defensible under "what if the empirical curve is something completely different?" Linear handles that; quadratic doesn't.

**Process improvement:** track unverified empirical claims explicitly. If a paragraph contains the words "real data shows" or "studies suggest," verify the citation or replace with "we hypothesize."

---

## 18. RV is value-at-stake, not performance — almost misused it for CSM ranking

**The near-miss:** Once RV was on the table, my reflex was to use it for everything, including CSM ranking. The chart-of-CSMs-shifted-under-RV-vs-AVRI showed dramatic position changes (some CSMs +30, others −30). I framed this as a feature. The user asked: *"pick a big mover and explain materially what caused the move."*

**What the data showed:** CSM-019 (AMER Enterprise, $17.4M book, AVRI=44, $5.2M RV) rises from rank 48 to rank 16 under RV. CSM-001 (AMER Mid-Market, $1.3M book, AVRI=89, $1.14M RV) falls from rank 5 to rank 39. Pattern: every big riser is Enterprise with mediocre AVRI; every big faller is Mid-Market with excellent AVRI. RV-as-ranking *mechanically rewards segment assignment*, not performance.

**The resolution:** AVRI stays the CSM evaluation metric. RV is for executive risk views, account-level triage, and the "where are dollars leaking?" question. Three metrics, three consumers, three uses. Documented as the metric architecture in `metric_v2.md` Section 1.

**Lesson:** A useful new metric is also a tempting hammer. The next instinct is to swing it at every nail, including ones it doesn't fit. Asking *"who consumes this number, and what decision does it drive?"* before deciding where to surface a metric is the discipline that catches misuse. RV's consumer is "executive looking at risk concentration." That's not the same audience as "CSM evaluating their performance," and the metric should respect the distinction.

---

## 19. Pillar decomposition fell out of linearity; visualization design followed the math

**The discovery:** While strategizing dashboard visualizations, the user asked which option would best surface "where RV is being lost, by which pillar." I started reaching for treemaps (Finviz-style — beautiful for clustering but wrong for diagnosis). Stopped, looked at the math: under linear RV,

    Unrealized = ARR × Σ_pillar (weight × (100 − pillar_score) / 100)

This isn't an approximation; it's algebra. Each pillar has a *real, summable contribution* to the unrealized $ figure at every aggregate level. The visualization that displays this most clearly is a heatmap matrix: rows = aggregate units (regions/CSMs), cols = pillars, cells = $ unrealized to that pillar in that aggregate.

**Why this matters:** the heatmap is *exactly* the metric, not a summary or an approximation. A VP scanning down the TH column to spot "TH is dragging EMEA" is reading the formula directly. That's a property linear RV gives us for free; quadratic and sigmoidal versions do not factor like this.

**Lesson:** The right visualization isn't always the most elegant one. It's the one whose visual encoding maps directly to the underlying math. Treemap → "where do dollars cluster" (good for one question, wrong for another). Pillar heatmap → "where are dollars being lost and why" (the question we actually had). Ask "what does this chart's geometry mean mathematically?" — and pick the chart whose geometry IS the answer.

**Process improvement:** before sketching dashboards, write down the math of the metric and ask "what does this expression *look like*?" Often the natural visualization is sitting right there in the formula's structure.

---

## 20. (template: add new entries here)
