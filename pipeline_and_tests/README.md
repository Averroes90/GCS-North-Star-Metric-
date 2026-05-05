# Metric Pipeline

SQL transforms that read from the BigQuery synthetic dataset and materialize four output tables for the dashboard:

| Table | What it contains |
|---|---|
| `metrics_existing_account` | TCV, ARR, raw utilization, latest health color, naive Gainsight-style CHS |
| `avri_account` | Four AVRI pillars (CR, UM, DM, TH) + composite + RAG color + **v2.0: rv_dollars + pillar-attribution columns** |
| `avri_csm` | Dollar-weighted AVRI per CSM with RAG counts + **v2.0: book_rv_dollars, realization_rate, pillar totals** |
| `avri_region` | Same rollup at region grain |

The scoring math is implemented in two parallel places that **must produce identical numbers** for the bundled default config: the SQL files in `sql/avri/` (BigQuery side) and `core/scoring.py` (Python side). The snapshot test in `core/test_scoring.py` verifies this contract. See `core/README.md` for the contract details.

## Run

```bash
cd pipeline_and_tests
python run_pipeline.py
```

Optional flags: `--project`, `--dataset`, `--as-of-date` (default 2026-04-22).

## File layout

```
pipeline_and_tests/
├── run_pipeline.py                       ← SQL pipeline orchestrator
├── inspection.py                         ← v1+v2 comparison report generator
├── test_data_quality.py                  ← 29 pytest DQ assertions
├── snapshot_avri_vs_chs.py               ← lobby snapshot: AVRI vs CHS
├── snapshot_pillar_decomposition.py      ← v2.0 lobby snapshot: pillar decomposition
├── conftest.py
├── requirements.txt
└── sql/
    ├── existing_metrics/metrics_existing_account.sql
    └── avri/avri_account.sql, avri_csm.sql, avri_region.sql
```

## Data quality tests

Required by the brief: *"Write automated assertions/tests…to programmatically catch the Orphaned Usage, overlapping contracts, and other data anomalies."*

```bash
pip install -r requirements.txt
pytest -v
```

Coverage (29 assertions: 24 v1 + 5 new v2 RV invariants):

| Section | What it checks |
|---|---|
| 1. Schema & value sanity | Uniqueness of IDs; non-negative numeric values; date ordering; valid color enum |
| 2. Referential integrity | All FKs resolve (contracts → accounts, account_health → accounts, accounts → csm_rep) |
| 3. Anomaly detection | The brief's required anomalies are detectable: ~150 orphan usage logs, ~150 out-of-window logs, ~50 overlapping-contract accounts |
| 4. Pipeline output integrity | AVRI scores in [0,100], color values constrained, rollup totals reconcile |
| **5. v2 Realized Value invariants** | RV = 0 for grace; pillar decomposition sums to unrealized $; CSM/region rollups match account total; realization rate is in 0.5–0.95 band |

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
