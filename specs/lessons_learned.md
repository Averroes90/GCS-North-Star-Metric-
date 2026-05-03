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

## 14. (template: add new entries here)
