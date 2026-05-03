# Metric Pipeline

SQL transforms that read from the BigQuery synthetic dataset and materialize four output tables for the dashboard:

| Table | What it contains |
|---|---|
| `metrics_existing_account` | TCV, ARR, raw utilization, latest health color, naive Gainsight-style CHS |
| `avri_account` | All four AVRI pillars (CR, UM, DM, TH) + composite + RAG color |
| `avri_csm` | Dollar-weighted AVRI per CSM with RAG count breakdown |
| `avri_region` | Dollar-weighted AVRI per region with RAG count breakdown |

## Run

```bash
cd pipeline_and_tests
python run_pipeline.py
```

Optional flags: `--project`, `--dataset`, `--as-of-date` (default 2026-04-22).

## File layout

```
pipeline_and_tests/
├── run_pipeline.py            ← SQL pipeline orchestrator
├── inspection.py              ← inductive comparison report generator
├── test_data_quality.py       ← pytest DQ assertions (Phase 3.5)
├── conftest.py                ← shared pytest fixtures
├── requirements.txt
└── sql/
    ├── existing_metrics/
    │   └── metrics_existing_account.sql
    └── avri/
        ├── avri_account.sql
        ├── avri_csm.sql
        └── avri_region.sql
```

## Data quality tests

Required by the brief: *"Write automated assertions/tests…to programmatically catch the Orphaned Usage, overlapping contracts, and other data anomalies."*

```bash
pip install -r requirements.txt
pytest -v
```

Coverage (~22 assertions across 4 sections):

| Section | What it checks |
|---|---|
| Schema & value sanity | Uniqueness of IDs; non-negative numeric values; date ordering; valid color enum |
| Referential integrity | All FKs resolve (contracts → accounts, account_health → accounts, accounts → csm_rep) |
| Anomaly detection | The brief's required anomalies are detectable: ~150 orphan usage logs, ~150 out-of-window logs, ~50 overlapping-contract accounts |
| Pipeline output integrity | AVRI scores in [0,100], color values constrained, rollup totals reconcile with account-level counts |

Run with verbose output (`pytest -v -s`) to see counts printed for the anomaly-detection tests, useful for verifying the injected-anomaly numbers match what was generated.

## Override project / dataset

Tests default to `panw-gcs-northstar.gcs_north_star`. Override via env vars:

```bash
BQ_PROJECT=other-project BQ_DATASET=other_dataset pytest
```

Each SQL file is a `CREATE OR REPLACE TABLE` statement with `{project}`, `{dataset}`, and `{as_of_date}` placeholders that the runner substitutes via Python `.format()`. Re-running is idempotent.

## Sanity checks (run in BigQuery Studio after pipeline)

```sql
-- Distribution of AVRI scores
SELECT avri_color, COUNT(*) AS n,
       ROUND(AVG(avri_score), 1) AS avg_avri,
       ROUND(MIN(avri_score), 1) AS min_avri,
       ROUND(MAX(avri_score), 1) AS max_avri
FROM `panw-gcs-northstar.gcs_north_star.avri_account`
GROUP BY avri_color
ORDER BY avg_avri DESC;
```

```sql
-- Where AVRI most strongly disagrees with naive CHS
SELECT a.account_id, a.industry,
       e.naive_chs_score, a.avri_score,
       (e.naive_chs_score - a.avri_score) AS gap,
       a.cr_score, a.um_score, a.dm_score, a.th_score,
       a.floor_rule_triggered, a.avri_color
FROM `panw-gcs-northstar.gcs_north_star.avri_account` a
JOIN `panw-gcs-northstar.gcs_north_star.metrics_existing_account` e USING (account_id)
ORDER BY ABS(e.naive_chs_score - a.avri_score) DESC
LIMIT 25;
```
