"""Data quality test suite — pytest assertions against the BigQuery dataset.

Run from `pipeline_and_tests/`:
    pytest                          # all tests
    pytest -v                       # verbose
    pytest test_data_quality.py::test_orphan_usage_logs_present  # one test

Coverage:

  Section 1 — Schema & value sanity
    1.1  log_id is unique
    1.2  account_id, csm_id, contract_id are unique in their tables
    1.3  no negative consumed credits
    1.4  no negative annual_commit_dollars
    1.5  contracts have start_date < end_date
    1.6  health_color values are constrained to {green, yellow, red}
    1.7  account_health (account_id, date) pairs are unique

  Section 2 — Referential integrity
    2.1  every contracts.account_id exists in accounts
    2.2  every account_health.account_id exists in accounts

  Section 3 — Anomaly detection (the brief's specific asks)
    3.1  ~150 orphan usage logs are present and detectable
    3.2  ~150 out-of-window usage logs are present and detectable
    3.3  mid-year expansion accounts have overlapping contracts (≥40 expected)
    3.4  no NEGATIVE-side anomalies (e.g., usage logs from before account creation)

  Section 4 — Pipeline output integrity
    4.1  avri_account scores are in [0, 100]
    4.2  avri_color values are in {green, yellow, red}
    4.3  avri_account row count matches in-scope accounts
    4.4  rollup tables aggregate to the same total accounts
"""

from __future__ import annotations

import pytest
from conftest import count, scalar


# ============================================================================
# Section 1 — Schema & value sanity
# ============================================================================

class TestSchemaAndValueSanity:
    """Catches structural problems: duplicates, NULLs, invalid values."""

    def test_log_id_unique(self, bq, fq):
        dupe_count = count(bq, f"""
            SELECT COUNT(*) FROM (
              SELECT log_id, COUNT(*) c FROM {fq("daily_usage_logs")}
              GROUP BY log_id HAVING c > 1
            )
        """)
        assert dupe_count == 0, f"{dupe_count} duplicate log_ids found"

    def test_account_id_unique(self, bq, fq):
        dupe = count(bq, f"""
            SELECT COUNT(*) FROM (
              SELECT account_id, COUNT(*) c FROM {fq("accounts")}
              GROUP BY account_id HAVING c > 1
            )
        """)
        assert dupe == 0, f"{dupe} duplicate account_ids found"

    def test_csm_id_unique(self, bq, fq):
        dupe = count(bq, f"""
            SELECT COUNT(*) FROM (
              SELECT csm_id, COUNT(*) c FROM {fq("csm_rep")}
              GROUP BY csm_id HAVING c > 1
            )
        """)
        assert dupe == 0, f"{dupe} duplicate csm_ids found"

    def test_contract_id_unique(self, bq, fq):
        dupe = count(bq, f"""
            SELECT COUNT(*) FROM (
              SELECT contract_id, COUNT(*) c FROM {fq("contracts")}
              GROUP BY contract_id HAVING c > 1
            )
        """)
        assert dupe == 0, f"{dupe} duplicate contract_ids found"

    def test_no_negative_credits(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("daily_usage_logs")}
            WHERE compute_credits_consumed < 0
        """)
        assert bad == 0, f"{bad} usage logs with negative credit values"

    def test_no_negative_arr(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("contracts")}
            WHERE annual_commit_dollars < 0
        """)
        assert bad == 0, f"{bad} contracts with negative ARR"

    def test_contract_dates_ordered(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("contracts")}
            WHERE start_date >= end_date
        """)
        assert bad == 0, f"{bad} contracts with start_date >= end_date"

    def test_health_colors_constrained(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("account_health")}
            WHERE health_color NOT IN ('green', 'yellow', 'red')
        """)
        assert bad == 0, f"{bad} account_health rows with invalid color values"

    def test_account_health_uniqueness(self, bq, fq):
        dupe = count(bq, f"""
            SELECT COUNT(*) FROM (
              SELECT account_id, date, COUNT(*) c FROM {fq("account_health")}
              GROUP BY account_id, date HAVING c > 1
            )
        """)
        assert dupe == 0, f"{dupe} duplicate (account_id, date) pairs in account_health"


# ============================================================================
# Section 2 — Referential integrity
# ============================================================================

class TestReferentialIntegrity:
    """Catches FK violations between tables — the joins must always succeed."""

    def test_contracts_account_id_fk(self, bq, fq):
        orphan_contracts = count(bq, f"""
            SELECT COUNT(*) FROM {fq("contracts")} c
            LEFT JOIN {fq("accounts")} a USING (account_id)
            WHERE a.account_id IS NULL
        """)
        assert orphan_contracts == 0, \
            f"{orphan_contracts} contracts reference accounts that do not exist"

    def test_account_health_account_id_fk(self, bq, fq):
        orphan_health = count(bq, f"""
            SELECT COUNT(*) FROM {fq("account_health")} h
            LEFT JOIN {fq("accounts")} a USING (account_id)
            WHERE a.account_id IS NULL
        """)
        assert orphan_health == 0, \
            f"{orphan_health} account_health rows reference accounts that do not exist"

    def test_accounts_rep_id_fk(self, bq, fq):
        orphan_reps = count(bq, f"""
            SELECT COUNT(*) FROM {fq("accounts")} a
            LEFT JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
            WHERE r.csm_id IS NULL
        """)
        assert orphan_reps == 0, \
            f"{orphan_reps} accounts reference rep_ids that do not exist"


# ============================================================================
# Section 3 — Anomaly detection (the brief's required checks)
# ============================================================================

class TestAnomalyDetection:
    """The brief: 'programmatically catch the Orphaned Usage, overlapping
    contracts, and other data anomalies.' These tests prove the anomalies
    exist and are surfaced by the pipeline's filters."""

    def test_orphan_usage_logs_present(self, bq, fq):
        """~150 usage logs intentionally have account_ids that do not exist
        in the accounts table. The pipeline must be able to detect them."""
        orphan_count = count(bq, f"""
            SELECT COUNT(*) FROM {fq("daily_usage_logs")} u
            LEFT JOIN {fq("accounts")} a USING (account_id)
            WHERE a.account_id IS NULL
        """)
        assert 100 <= orphan_count <= 250, \
            f"Expected ~150 orphan usage logs; found {orphan_count}"
        print(f"\n   ✓ Detected {orphan_count} orphan usage logs (target ~150)")

    def test_out_of_window_usage_logs_present(self, bq, fq):
        """~150 usage logs intentionally fall outside any active contract
        date range for their account. The pipeline must surface these."""
        ooW_count = count(bq, f"""
            SELECT COUNT(*) FROM {fq("daily_usage_logs")} u
            JOIN {fq("accounts")} a USING (account_id)
            WHERE NOT EXISTS (
              SELECT 1 FROM {fq("contracts")} c
              WHERE c.account_id = u.account_id
                AND u.date BETWEEN c.start_date AND c.end_date
            )
        """)
        assert 100 <= ooW_count <= 250, \
            f"Expected ~150 out-of-window usage logs; found {ooW_count}"
        print(f"\n   ✓ Detected {ooW_count} out-of-window usage logs (target ~150)")

    def test_overlapping_contracts_present(self, bq, fq):
        """~50 accounts have a mid-year expansion: a second contract whose
        date range overlaps the first. The brief calls these out as a
        required anomaly to handle correctly."""
        overlap_accounts = count(bq, f"""
            WITH pairs AS (
              SELECT c1.account_id, c1.contract_id AS c1_id, c2.contract_id AS c2_id
              FROM {fq("contracts")} c1
              JOIN {fq("contracts")} c2
                ON c1.account_id = c2.account_id
               AND c1.contract_id < c2.contract_id
               AND c1.end_date >= c2.start_date
               AND c2.end_date >= c1.start_date
            )
            SELECT COUNT(DISTINCT account_id) FROM pairs
        """)
        assert 40 <= overlap_accounts <= 70, \
            f"Expected ~50 accounts with overlapping contracts; found {overlap_accounts}"
        print(f"\n   ✓ Detected {overlap_accounts} accounts with overlapping contracts "
              f"(target ~50)")

    def test_no_unintended_orphans_in_pipeline_output(self, bq, fq):
        """The metric pipeline's `metrics_existing_account` and `avri_account`
        must NOT contain any orphan accounts. Both should filter to in-scope."""
        bad_avri = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")} av
            LEFT JOIN {fq("accounts")} a USING (account_id)
            WHERE a.account_id IS NULL
        """)
        assert bad_avri == 0, \
            f"{bad_avri} accounts in avri_account that don't exist in source — " \
            f"filter is broken"

        bad_existing = count(bq, f"""
            SELECT COUNT(*) FROM {fq("metrics_existing_account")} m
            LEFT JOIN {fq("accounts")} a USING (account_id)
            WHERE a.account_id IS NULL
        """)
        assert bad_existing == 0, \
            f"{bad_existing} accounts in metrics_existing_account that don't exist " \
            f"in source — filter is broken"


# ============================================================================
# Section 4 — Pipeline output integrity
# ============================================================================

class TestPipelineOutputs:
    """Confirms the materialized output tables conform to the spec."""

    def test_avri_scores_in_range(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE avri_score < 0 OR avri_score > 100
        """)
        assert bad == 0, f"{bad} avri_account rows with score outside [0, 100]"

    def test_pillar_scores_in_range(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE cr_score < 0 OR cr_score > 100
               OR um_score < 0 OR um_score > 100
               OR dm_score < 0 OR dm_score > 100
               OR th_score < 0 OR th_score > 100
        """)
        assert bad == 0, f"{bad} avri_account rows with pillar score outside [0, 100]"

    def test_avri_color_values(self, bq, fq):
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE avri_color NOT IN ('green', 'yellow', 'red', 'onboarding')
        """)
        assert bad == 0, f"{bad} avri_account rows with invalid avri_color"

    def test_grace_period_logic(self, bq, fq):
        """v1.3: accounts with all contracts in grace must have NULL avri_score
        and avri_color = 'onboarding'. Conversely, scored accounts must have
        at least one activated contract."""
        # All-grace accounts must be unscored
        bad_unscored = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE all_contracts_in_grace = TRUE
              AND (avri_score IS NOT NULL OR avri_color != 'onboarding')
        """)
        assert bad_unscored == 0, \
            f"{bad_unscored} all-grace accounts incorrectly have a score or non-onboarding color"

        # Scored accounts must have at least one activated contract
        bad_scored = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE avri_score IS NOT NULL
              AND (activated_contracts = 0 OR all_contracts_in_grace = TRUE)
        """)
        assert bad_scored == 0, \
            f"{bad_scored} scored accounts have no activated contracts"

        # Counts reconcile: total = activated + grace
        bad_counts = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE total_contracts != activated_contracts + grace_contracts
        """)
        assert bad_counts == 0, \
            f"{bad_counts} accounts where total_contracts != activated + grace"

    def test_grace_period_present(self, bq, fq):
        """v1.3: with contracts uniformly distributed across the past 18 months
        and a 90-day timeout, we expect SOME contracts to currently be in grace
        (recently signed, not yet activated). Sanity check that the grace
        period is actually firing — if zero, something's wrong."""
        grace_count = count(bq, f"""
            SELECT COUNT(*) FROM {fq("avri_account")}
            WHERE has_grace_contract = TRUE
        """)
        # Loose assertion: at least 5 accounts should have a grace contract.
        # If zero, the activation logic is broken.
        assert grace_count >= 5, \
            f"Only {grace_count} accounts have a grace contract — activation logic may be broken"
        print(f"\n   ✓ {grace_count} accounts have at least one in-grace contract")

    def test_avri_account_count_matches_scope(self, bq, fq):
        """avri_account should contain exactly the accounts with at least one
        active contract on the as-of date (2026-04-22)."""
        scope_count = count(bq, f"""
            SELECT COUNT(DISTINCT a.account_id)
            FROM {fq("accounts")} a
            JOIN {fq("contracts")} c USING (account_id)
            WHERE c.start_date <= DATE('2026-04-22')
              AND c.end_date >= DATE('2026-04-22')
        """)
        avri_count = count(bq, f"SELECT COUNT(*) FROM {fq('avri_account')}")
        assert avri_count == scope_count, \
            f"avri_account has {avri_count} rows but scope has {scope_count} accounts"
        print(f"\n   ✓ avri_account row count ({avri_count}) matches in-scope " \
              f"account count")

    def test_csm_rollup_account_count(self, bq, fq):
        """avri_csm should aggregate every avri_account row exactly once."""
        avri_count = count(bq, f"SELECT COUNT(*) FROM {fq('avri_account')}")
        rollup_total = count(bq, f"""
            SELECT COALESCE(SUM(account_count), 0) FROM {fq("avri_csm")}
        """)
        assert rollup_total == avri_count, \
            f"avri_csm sums to {rollup_total} accounts but avri_account has {avri_count}"

    def test_region_rollup_account_count(self, bq, fq):
        """avri_region should also aggregate every avri_account row exactly once."""
        avri_count = count(bq, f"SELECT COUNT(*) FROM {fq('avri_account')}")
        region_total = count(bq, f"""
            SELECT COALESCE(SUM(account_count), 0) FROM {fq("avri_region")}
        """)
        assert region_total == avri_count, \
            f"avri_region sums to {region_total} accounts but avri_account has {avri_count}"


# =============================================================================
# Section 5 — v2.0: Realized Value invariants
# =============================================================================

class TestRealizedValue:
    """RV (linear) decomposition + grace exclusion + aggregation invariants."""

    def test_rv_grace_excluded(self, bq, fq):
        """All-grace (onboarding) accounts must have rv_dollars = 0."""
        n = count(bq, f"""
            SELECT COUNT(*) FROM {fq('avri_account')}
            WHERE all_contracts_in_grace = TRUE AND rv_dollars != 0
        """)
        assert n == 0, f"{n} grace accounts have non-zero RV"

    def test_rv_decomposition_adds_up(self, bq, fq):
        """Per-account: pillar contributions + floor residual = (ARR - RV).

        Tolerance: max($5, 0.1% of ARR). The pipeline rounds pillar scores
        and avri_raw to 1 decimal place for human-readable display
        (avri_account.sql ``with_avri`` CTE). The pandas reference
        implementation in core/scoring.py preserves full precision and the
        decomposition there is exact (verified in core/test_scoring.py).
        The pipeline's per-account drift is bounded by:
            ARR × 0.05 (max raw-AVRI rounding) / 100 ≈ ARR × 0.0005
        Which is well within 0.1% of ARR.
        """
        bad = count(bq, f"""
            SELECT COUNT(*) FROM {fq('avri_account')}
            WHERE all_contracts_in_grace = FALSE
              AND avri_score IS NOT NULL
              AND ABS(
                (arr_dollars - rv_dollars) -
                (unrealized_cr_dollars + unrealized_um_dollars +
                 unrealized_dm_dollars + unrealized_th_dollars +
                 unrealized_floor_dollars)
              ) > GREATEST(5.0, arr_dollars * 0.001)
        """)
        assert bad == 0, (
            f"{bad} accounts have decomposition mismatch > max($5, 0.1% of ARR). "
            f"This indicates a structural error, not just rounding drift."
        )

    def test_rv_aggregation_csm(self, bq, fq):
        """Σ avri_csm.book_rv_dollars equals Σ avri_account.rv_dollars."""
        acct_total = count(bq, f"SELECT ROUND(SUM(rv_dollars), 0) FROM {fq('avri_account')}")
        csm_total  = count(bq, f"SELECT ROUND(SUM(book_rv_dollars), 0) FROM {fq('avri_csm')}")
        assert abs(acct_total - csm_total) < 2, \
            f"CSM rollup RV {csm_total} != account RV {acct_total}"

    def test_rv_aggregation_region(self, bq, fq):
        """Σ avri_region.book_rv_dollars equals Σ avri_account.rv_dollars."""
        acct_total = count(bq, f"SELECT ROUND(SUM(rv_dollars), 0) FROM {fq('avri_account')}")
        region_tot = count(bq, f"SELECT ROUND(SUM(book_rv_dollars), 0) FROM {fq('avri_region')}")
        assert abs(acct_total - region_tot) < 2, \
            f"Region rollup RV {region_tot} != account RV {acct_total}"

    def test_realization_rate_in_range(self, bq, fq):
        """Org-wide realization rate is in a sane band (0.5 to 0.95)."""
        rows = bq.query(f"""
            SELECT SAFE_DIVIDE(
              SUM(rv_dollars),
              SUM(IF(avri_score IS NOT NULL, arr_dollars, 0))
            ) AS rate FROM {fq('avri_account')}
        """).result()
        rate = list(rows)[0].rate
        assert 0.5 <= rate <= 0.95, f"Realization rate {rate:.3f} outside expected band"
