# GCS North Star Metric: PANW Case Study

Working repository for the Principal IT PM, Data Analytics case study. Designs a North Star metric ("AVRI": Account Value Realization Index) for Palo Alto Networks' Global Customer Services org as it transitions from a TCV bookings model to an ARR + consumption hybrid.

The interactive lobby for everything in this repo is **`metrics-explorer.html`**. Open it in a browser; all other artifacts are linked from there.

📖 **First time here?** Read [`REVIEW_GUIDE.md`](REVIEW_GUIDE.md) for the recommended order to walk through everything, depending on whether you have 15 minutes (orientation), 1 hour (full read-through), or you're a developer wanting to read the code.

---

## Repository layout

```
.
├── metrics-explorer.html        ← MAIN LOBBY, open this first
├── README.md                    ← you are here
├── core/                        ← v2.0 — single source of truth for scoring
│   ├── config_v1.json           ← all calibratable parameters
│   ├── scoring.py               ← shared scoring module (pipeline + dashboard)
│   ├── build_facts.py           ← local fact reconstruction (for tests)
│   ├── test_scoring.py          ← snapshot tests (math invariants + golden)
│   └── README.md                ← contract: facts in, scores out
├── specs/
│   ├── metric_v0.md             ← initial hypothesis
│   ├── metric_v1.md             ← v0 → v1.3 diff (grace period, refinements)
│   ├── metric_v2.md             ← v2.0 spec: RV, calibration, decomposition
│   ├── data_generation_spec.md  ← synthetic data spec
│   ├── inspection_findings.md   ← AVRI/RV vs existing metrics — generated
│   ├── pillar_decomposition_snapshot.json ← lobby's RV tab data — generated
│   ├── avri_vs_chs_snapshot.json
│   ├── lessons_learned.md       ← 19 entries: design tensions + retrospectives
│   ├── deck_outline.md          ← pre-build outline for the executive deck
│   └── demo_script_and_qa.md    ← presentation script + Q&A
├── AVRI_Deck.pptx               ← executive presentation (8 slides)
├── AVRI_Deck.pdf                ← PDF copy for submission
├── charts/                      ← static PNGs embedded in lobby + deck
├── data_generation/
│   ├── main.py
│   ├── config.py / personas.py / generate.py / validators.py
│   ├── load_to_bigquery.py
│   └── output/                  ← parquet files + manifest.json
├── pipeline_and_tests/
│   ├── run_pipeline.py          ← SQL pipeline orchestrator
│   ├── inspection.py            ← v1 + v2 comparison report generator
│   ├── test_data_quality.py     ← 29 DQ tests (24 v1 + 5 v2)
│   ├── snapshot_avri_vs_chs.py
│   ├── snapshot_pillar_decomposition.py  ← v2.0 — lobby snapshot from BQ
│   ├── conftest.py
│   └── sql/
│       ├── existing_metrics/metrics_existing_account.sql
│       └── avri/avri_account.sql, avri_csm.sql, avri_region.sql
└── dashboard/
    ├── app.py                   ← 6 tabs: Realized Value (v2 landing), Executive Overview, CSM Detail, Account Drill-down, At-Risk Renewals, Calibration (v2)
    ├── requirements.txt
    └── README.md
```

---

## Quick start (full end-to-end)

```bash
# One-time machine setup
gcloud auth application-default login
gcloud config set project panw-gcs-northstar

# 1. Generate synthetic data
cd data_generation
pip install -r requirements.txt
python main.py

# 2. Upload to BigQuery
python load_to_bigquery.py

# 3. Run metric pipeline
cd ../pipeline_and_tests
python run_pipeline.py

# 4. Generate inspection report and v2 snapshot
python inspection.py
python snapshot_pillar_decomposition.py
python snapshot_avri_vs_chs.py

# 4b. Run data quality tests (29 — 24 v1 + 5 v2 RV invariants)
pytest -v

# 4c. Verify scoring module against pipeline output (v2 contract test)
cd ..
python -m pytest core/test_scoring.py -v

# 5. Launch dashboard
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

Each script is idempotent, safe to re-run. See the **Scripts & Run Guide** tab in `metrics-explorer.html` for full per-script documentation.

### Browse the project
```bash
open metrics-explorer.html
```
Use the **Project Map** tab as the navigation hub. **Scripts & Run Guide** for execution details. **How It Connects** for the architecture diagram.

---

## Project status (high-level)

| Phase | Status |
|---|---|
| 1. Strategy & Specs | ✅ Complete |
| 2. Data Generation | ✅ Working — see `data_generation/output/manifest.json` |
| 3. Metric Pipeline | ✅ AVRI v1.3 complete (Activation Grace Period). |
| 4. Dashboard | ✅ Streamlit running (`dashboard/app.py`) |
| 5. Executive Presentation | ✅ Deck (8 slides) + demo script. |
| **6. v2.0: Realized Value** | ✅ RV linear formula, pillar decomposition, calibration centralization, pillar heatmap. 29 of 29 DQ tests pass. |

Detailed status, decisions, and assumptions for each step are surfaced in the **Project Map** tab of `metrics-explorer.html`.

---

## Methodology

This project follows a **spec-driven AI-assisted development** approach as required by the brief. Each phase begins with a markdown specification (in `/specs/`) that becomes the input to AI-assisted code generation. Work proceeds **inductively**: the dataset is built to be realistic, existing metrics are calculated on it, the gaps in those metrics inform refinement of the proposed AVRI metric, rather than designing the metric first and engineering the data to validate it.

---

## Datasets

Five tables, generated to match the brief's schema:

| Table | Rows | Description |
|---|---|---|
| `csm_rep` | 50 | Customer Success reps (region, segment) |
| `accounts` | 1,000 | Customer accounts (industry, rep_id) |
| `contracts` | 1,050 | Active contracts (incl. ~50 mid-year expansion overlaps) |
| `daily_usage_logs` | ~290,000 | Event-level credit consumption (incl. ~300 orphan/rogue) |
| `account_health` | ~33,000 | Weekly health snapshots (color + aggregated consumption) |

See `specs/data_generation_spec.md` for full schema, distributions, persona mix, and edge case injection logic.
