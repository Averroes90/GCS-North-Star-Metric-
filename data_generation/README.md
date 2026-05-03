# Data Generation

Synthetic GCS dataset builder. Implements [`/specs/data_generation_spec.md`](../specs/data_generation_spec.md). Output: 5 Parquet files representing 50 reps, 1,000 accounts, 1,050 contracts, ~294K usage logs, ~33K weekly health snapshots, all reproducible from a single seed.

## Run

```bash
pip install -r requirements.txt
python main.py                  # generate Parquet locally
python load_to_bigquery.py      # upload to BigQuery
```

Both scripts are idempotent. `main.py` produces byte-identical output every run (single seed). `load_to_bigquery.py` uses `WRITE_TRUNCATE`, re-runs replace tables in place.

## File layout

```
data_generation/
├── main.py                   # orchestrator, call this
├── config.py                 # all tunable parameters (seed, distributions, persona weights, transition matrices)
├── personas.py               # 7 persona shapes + seasonal/noise modifiers
├── generate.py               # entity & event generators (csm_rep, accounts, contracts, usage, health, edge cases)
├── validators.py             # pre-write sanity gates
├── load_to_bigquery.py       # Parquet → BigQuery loader (separate script, separate concern)
├── requirements.txt
└── output/                   # generated Parquet + manifest.json
    ├── csm_rep.parquet
    ├── accounts.parquet
    ├── contracts.parquet
    ├── daily_usage_logs.parquet
    ├── account_health.parquet
    └── manifest.json
```

## What gets generated

Per the data spec, each table has known characteristics:

| Table | Rows | Notes |
|---|---|---|
| `csm_rep` | 50 | Region (AMER 60% / EMEA 25% / APAC 15%); segment (Enterprise 40% / Mid-Market 60%) |
| `accounts` | 1,000 | 9 industries, lognormal account size, segment-respecting rep assignment |
| `contracts` | 1,050 | 70/22/8% mix of 12/24/36-month terms; ~50 mid-year-expansion overlays |
| `daily_usage_logs` | ~294K | Persona-driven time series + weekly seasonality + Gaussian noise; ~150 orphan + ~150 out-of-window injected |
| `account_health` | ~33K | Markov chain over green/yellow/red, weekly snapshots; decay-biased for shelfware/spike-drop personas |

## Authentication

The loader reads Application Default Credentials from `~/.config/gcloud/`. One-time setup:

```bash
gcloud auth application-default login
gcloud config set project panw-gcs-northstar
```

## Tuning

Every parameter is in `config.py`. To change the dataset shape, edit there, the generation logic doesn't need to change. Examples:

- More accounts: `N_ACCOUNTS = 5000`
- Different persona mix: edit `PERSONA_WEIGHTS`
- Stricter sampling tolerance: edit `validators.py` line near `±3pp`
- Different seed: `SEED = ...` (every other random number cascades from this)

## Validation

`validators.py` runs assertions before writing Parquet. Any structural problem aborts the run with a clear message. Currently checks:

1. Row counts within ±5% of targets
2. Persona distribution within ±3pp of targets
3. Contract FK integrity (no orphan contracts)
4. Orphan usage log count near 150
5. Out-of-window usage log count near 150
6. Mid-year expansion accounts have ≥2 overlapping contracts
7. `account_health` is unique by `(account_id, date)`

## Known gotchas

See [`/specs/lessons_learned.md`](../specs/lessons_learned.md) for the running log. The most relevant for this folder:

- **#2 (numpy 128-bit limit)**, UUIDs require composing two 64-bit draws
- **#3 (sampling variance)**, N=1000 + 7 personas needs ±3pp tolerance, not ±2pp
- **#4 (Parquet date types)**, `datetime64[ns]` writes as TIMESTAMP, not DATE; need `.dt.date` conversion before writing for BigQuery DATE compatibility
