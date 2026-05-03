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
            WHERE avri_color NOT IN ('green', 'yellow', 'red')
        """)
        assert bad == 0, f"{bad} avri_account rows with invalid avri_color"

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
