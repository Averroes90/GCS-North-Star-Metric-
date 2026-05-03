# Metric v1: AVRI (refinement diff from v0)

**Status:** Refinement spec. Documents what changed between `metric_v0.md` (the hypothesized design) and v1 (the inductively-refined design). v0 remains the canonical full reference; this file only records the deltas.

**Trigger:** Phase 3.3 inspection findings, see `lessons_learned.md` #7, #10, and `inspection_findings.md`.

---

## What changed

### 1. Explicit scope filter: accounts must have an active contract

**v0 behavior:** AVRI was computed for every row in the `accounts` table. Accounts whose contracts had all expired (or hadn't yet started) on the as-of date received scores of 0 across every pillar. They appeared in the output table as Red, polluting the distribution and the rep/region rollups.

**v1 behavior:** AVRI is computed only for accounts with at least one contract whose `[start_date, end_date]` window contains the as-of date. Out-of-scope accounts do not appear in `avri_account` at all (NULL is the absence of a row, not a row with NULL columns).

**Why:** AVRI measures *value realization* against an active commit. An account with no active commit has no commit to realize against; the metric is undefined for it, not zero.

**Implementation:** `accounts_in_scope` CTE at the top of `avri_account.sql`. Same filter applied to `metrics_existing_account.sql` so the comparison is apples-to-apples.

**Distribution impact:** Pre-fix the output had ~280 Red accounts (533 G / 187 Y / 280 R). Post-fix the count drops by the number of out-of-scope accounts (~230 of the original 1,000). Distribution should look more like 533 G / 187 Y / 50 R, with the Red group now actually representing at-risk customers rather than expired contracts.

### 2. UM level guard (added in v1.1 after second inspection pass)

**v0/v1 behavior:** UM = `avg_90d / avg_365d` over rows present in the window. A near-zero baseline produced UM=100 for shelfware accounts (tiny/tiny = 1.0).

**v1.1 behavior:**
- Use `SUM/N` (N = days in window) instead of `AVG` over present rows, so missing days count as zero.
- Add a **level guard**: if trailing-365 total consumption is less than 5% of annual commit, UM = 0 regardless of ratio.

**Why 5%:** ~18 days of full-rate usage in a year. Below that, the account hasn't meaningfully adopted the product, and "momentum" is mathematically undefined.

**Distribution impact:** Pushes ~15-25 borderline shelfware-light accounts from Yellow → Red. After this fix, AVRI's Red count should exceed naive CHS's Red count, restoring the intended narrative ("AVRI surfaces hidden risk").

### 3. Contract context columns added to output (v1.2)

**v0/v1 behavior:** `avri_account` exposed only the score columns. Tenure, contract dates, and renewal timing weren't surfaced, they were "implicit context" but not queryable.

**v1.2 behavior:** Added the following columns to `avri_account`:
- `earliest_contract_start_date`, for tenure calculation
- `latest_active_contract_end`, for renewal horizon
- `tenure_days`, `as_of_date - earliest_contract_start_date`
- `days_to_renewal`, `latest_active_contract_end - as_of_date`
- `cold_start_flag`, `tenure_days < 90`
- `renewal_imminent_flag`, `days_to_renewal <= 90`

Rollup tables (`avri_csm`, `avri_region`) gained:
- `avg_tenure_days`
- `cold_start_accounts` (count)
- `renewal_imminent_accounts` (count)
- `at_risk_renewals_90d` (count of renewal-imminent accounts that are NOT green), the single most actionable view for a CSM dashboard

**Why:** Distinguishing cold-start from shelfware is critical for proper interpretation of low-AVRI accounts. Without tenure, an account scoring Red could be a brand-new ramp or an established under-realizer; the action is very different. Surfacing tenure as a first-class column also enables the dashboard's "filter to mature accounts" lens.

**No change to scoring logic.** The new columns are diagnostic context, not metric inputs.

### 4. (Other formula elements unchanged)

The four pillar weights (30/30/20/20), RAG thresholds (75/50), CR piecewise curve, DM linear, TH exponential decay, and floor rule (TH<30 → cap 50) all unchanged from v0. Inspection validated these.

---

## What we considered changing but did not

### a. UM "absolute level guardrail"

**Observation:** Shelfware accounts can produce UM = 100 because both the 90-day and 365-day averages are tiny, the *ratio* is ~1.0 even though the *level* is essentially zero. See `lessons_learned.md` #9.

**Why not changed:** CR and DM both correctly tank for these accounts, so the composite score still ends up Red. The misleading UM number is a diagnostic artifact, not a scoring failure. The composite is what matters.

**Future consideration (v2):** If UM is ever used standalone (e.g., as a comp-plan input), add an absolute-level floor. For the composite, leave it.

### b. Spike-and-drop differentiation from shelfware

**Observation:** Both patterns score deep red on AVRI, even though they're causally distinct. See `lessons_learned.md` #8.

**Why not changed:** AVRI's job is to score *value realization at this moment*. Both patterns represent zero current value. Differentiating *why* is a diagnostic task, handled by the dashboard's account-drilldown view (where the time series visually separates them).

---

## What this doesn't address (deferred to future versions)

- **Per-segment weight tuning**, Enterprise vs Mid-Market may justify different weights.
- **Renewal-correlation calibration**, weights and thresholds are still heuristic. Production tuning would regress against historical renewal outcomes.
- **Cold-start handling**, accounts with <90 days tenure don't have valid 90-day windows. Currently scored as if mature; should have an "Onboarding" RAG state.
- **Ticket / NPS / feature-adoption signals**, would replace the `health_color` and `active_days` proxies in the production v2.

---

## Re-run sequence

After v1 SQL changes:

```
cd pipeline_and_tests
python run_pipeline.py
python inspection.py
```

Compare the new distribution against v0's. Expect:
- Total accounts in `avri_account` drops by ~230 (out-of-scope removed).
- Naive CHS distribution shifts more red-heavy than AVRI (the right narrative, AVRI is more *trustworthy*, naive CHS over-penalizes some healthy accounts and over-rewards others).
- The "naive CHS overscored AVRI" gap analysis becomes meaningful, top-N rows should now be real shelfware accounts with substantive ARR, not zero-everything expired contracts.
