# Review Guide: A to Z

How to walk through everything in this project, in the right order, depending on what you want to get out of it. Pick the track that matches your time budget and goal.

---

## Track 1: 15-minute orientation

For when you have one coffee and want the whole picture.

| # | Open | What to look for |
|---|---|---|
| 1 | `README.md` (top-level) | The status table. Confirms what's done vs pending. |
| 2 | `metrics-explorer.html` → **Project Map** tab | Visual phase progress. Click any phase to see step-by-step what was built. |
| 3 | `metrics-explorer.html` → **How It Connects** tab | The 5-column architecture diagram. This is the mental model for the whole project. |
| 4 | `AVRI_Deck.pdf` | The 8-slide executive narrative (6 main + new RV slide + edge-case appendix). Skim. |

**You're done.** You now know what the project is, how it's structured, and what its narrative is.

---

## Track 2: 1-hour full walkthrough

For when you want to fully understand the metric and the design choices.

### Phase 1: Problem framing (10 min)
| # | Open | Why |
|---|---|---|
| 1 | `metrics-explorer.html` → **Overview** tab | The problem in plain language. |
| 2 | `metrics-explorer.html` → **Four Dimensions** tab | The four things the metric must balance, with definitions. |
| 3 | `metrics-explorer.html` → **Key Concepts** tab | TCV vs ARR vs Consumption Revenue, leading vs lagging, gameability — background you'll need for the rest. |

### Phase 2: Why existing metrics fall short (10 min)
| # | Open | Why |
|---|---|---|
| 4 | `metrics-explorer.html` → **Metrics Explorer** tab | Interactive table of ~30 industry metrics. Toggle filters; click any row for detail. |
| 5 | `metrics-explorer.html` → **Edge Cases** tab | The 5 messy patterns the brief specified — these are what existing metrics fail on. |

### Phase 3: The proposal (20 min)
| # | Open | Why |
|---|---|---|
| 6 | `metrics-explorer.html` → **AVRI Spec** tab | The full quality metric: 4 pillars, formulas, RAG bands, edge case behavior. Click ⓘ icons for rationale. |
| 7 | `metrics-explorer.html` → **Realized Value** tab | v2.0 — RV linear formula, pillar decomposition, $ realized vs unrealized. Where the scale dimension lives. |
| 8 | `metrics-explorer.html` → **Schema → Metric** tab | Visual flow showing how raw data rolls into pillars and out into RV. |
| 9 | `metrics-explorer.html` → **Defending Choices** tab | Every numeric value, with the rationale and scripted defense. |

### Phase 4: How it played out on real data (10 min)
| # | Open | Why |
|---|---|---|
| 10 | `specs/inspection_findings.md` | Auto-generated comparison report. v2 sections 13–16 cover RV totals, pillar attribution, and renewal landmines. |
| 11 | `specs/lessons_learned.md` | 19 documented pitfalls. Entries 16–19 are the v2 design tensions — the strongest retrospective material. |

### Phase 5: The pitch (15 min)
| # | Open | Why |
|---|---|---|
| 12 | `AVRI_Deck.pptx` (or PDF) | Read each slide carefully now that you understand the underlying work. 8 slides: cover, problem, gap, AVRI, RV (NEW), proof, retro, edge-case appendix. |
| 13 | `metrics-explorer.html` → **Takeaways** tab | The big claims, distilled. |

**You're done.** You now understand the metric, the choices, and how it performed.

---

## Track 3: Developer / code review

For when you want to read the actual implementation and verify it works.

### Sequence (matches the data flow)

| # | File | What it does |
|---|---|---|
| 1 | `data_generation/README.md` | Folder-level orientation. |
| 2 | `data_generation/config.py` | Every parameter that controls the synthetic dataset. Read this before reading any other Python. |
| 3 | `data_generation/personas.py` | The 7 persona shapes — how each population segment's consumption is modeled. |
| 4 | `data_generation/generate.py` | Table builders. Most of the data shape lives here. |
| 5 | `data_generation/validators.py` | Pre-write sanity gates. |
| 6 | `data_generation/main.py` | Orchestrator — the 6-step pipeline. |
| 7 | `data_generation/load_to_bigquery.py` | Parquet → BQ loader with explicit schemas. |
| 8 | `pipeline_and_tests/sql/existing_metrics/metrics_existing_account.sql` | TCV, ARR, raw util, naive CHS — the "metrics zoo" comparison baseline. |
| 9 | `pipeline_and_tests/sql/avri/avri_account.sql` | The AVRI formula in SQL. v2.0 added: rv_dollars + 5 pillar-attribution columns. |
| 10 | `pipeline_and_tests/sql/avri/avri_csm.sql` and `avri_region.sql` | Dollar-weighted rollups + v2.0 RV totals + realization rate. |
| 11 | `core/scoring.py` | **v2.0 — single source of truth.** Python implementation that mirrors the SQL. Both pipeline tests and dashboard call it. |
| 12 | `core/config_v1.json` | v2.0 — every calibratable parameter in one place. |
| 13 | `pipeline_and_tests/run_pipeline.py` | SQL pipeline orchestrator. |
| 14 | `pipeline_and_tests/inspection.py` | The comparison queries — v2 added RV totals, pillar attribution, renewal-landmine sections. |
| 15 | `pipeline_and_tests/test_data_quality.py` | 29 pytest assertions — 24 v1 + 5 v2 RV invariants (decomposition, grace exclusion, aggregation). |
| 16 | `core/test_scoring.py` | 20 unit tests on the scoring module — math invariants + golden snapshot. |
| 17 | `dashboard/app.py` | Streamlit UI. 6 tabs: Realized Value (v2 landing), Executive Overview, CSM Detail, Account Drill-down, At-Risk Renewals, Calibration (v2). The static AVRI vs CHS interactive view was removed in v2 (the static lobby tab + slide 3 carry that story); code preserved under `if False:` for revival. |

### To run end-to-end yourself

```bash
# One-time
gcloud auth application-default login
gcloud config set project panw-gcs-northstar

# Generate
cd data_generation && pip install -r requirements.txt
python main.py
python load_to_bigquery.py

# Pipeline + DQ tests
cd ../pipeline_and_tests && pip install -r requirements.txt
python run_pipeline.py
python inspection.py
python snapshot_pillar_decomposition.py
pytest -v                  # 29 tests

# v2 contract test (scoring.py vs SQL parity)
cd .. && python -m pytest core/test_scoring.py -v

# Dashboard
cd dashboard && pip install -r requirements.txt
streamlit run app.py
```

`metrics-explorer.html` → **Scripts & Run Guide** tab has the same sequence with per-script details.

---

## Track 4: Interview prep (the night before)

| # | Open | Time | Why |
|---|---|---|---|
| 1 | `specs/demo_script_and_qa.md` | 20 min | Read the whole runbook once. Mark it up in your voice. |
| 2 | `AVRI_Deck.pptx` | 15 min | Walk slide-by-slide alongside the script's per-slide talking points. Edit the slide-1 tagline, slide-5 `$X.XM` placeholder, slide-6 lessons to be in your voice. |
| 3 | `metrics-explorer.html` → **Defending Choices** tab | 15 min | Read every "If pushed" line aloud. These are your Q&A scripts. |
| 4 | `specs/lessons_learned.md` | 10 min | Pick 2-3 entries to be ready to talk about. The retrospective slide leans on these. |
| 5 | Streamlit dashboard | 10 min | Run it. Click through the demo flow from `demo_script_and_qa.md` Section 2 → Slide 5. Confirm ACC-00202 / ACC-00226 / ACC-00876 / ACC-00218 all load cleanly. |
| 6 | `AVRI_Deck.pptx` again | 10 min | Final dry run. Time yourself. Aim for 35 minutes of presenting. |

**Day-of:** the 8-step pre-flight checklist in `demo_script_and_qa.md` Section 1.

---

## Recommended live-use window setup

For the actual interview, have these open at start:

1. **Browser tab 1:** `AVRI_Deck.pptx` (in PowerPoint presenter mode) or `AVRI_Deck.pdf` (full-screen)
2. **Browser tab 2:** Streamlit dashboard at `http://localhost:8501`
3. **Browser tab 3:** `metrics-explorer.html`, for fallback if a Q&A goes deep
4. **Side window:** `specs/demo_script_and_qa.md` open for reference (don't read from it during; just refer if you blank)

Set the deck to half-screen left, the dashboard to half-screen right. When demoing, drag the deck off-screen and bring the dashboard fullscreen.

---

## File map by purpose

If you forget where something is, this is the index:

### Documentation
- `README.md`, top-level repo overview
- `REVIEW_GUIDE.md`, this file
- `metrics-explorer.html`, interactive lobby (open this to browse, not as a doc to read)

### Specs (source of truth)
- `specs/metric_v0.md`, initial AVRI hypothesis (frozen, historical)
- `specs/metric_v1.md`, refinement diff (current, what's implemented)
- `specs/data_generation_spec.md`, synthetic data spec
- `specs/inspection_findings.md`, auto-generated comparison report
- `specs/lessons_learned.md`, running pitfall log
- `specs/deck_outline.md`, pre-build outline for the deck
- `specs/demo_script_and_qa.md`, presentation runbook

### Code
- `data_generation/`, Python data generator (5 modules + loader)
- `pipeline_and_tests/sql/`, 4 SQL files defining all transforms
- `pipeline_and_tests/run_pipeline.py`, pipeline orchestrator
- `pipeline_and_tests/inspection.py`, comparison report generator
- `pipeline_and_tests/test_data_quality.py`, pytest DQ assertions
- `dashboard/app.py`, Streamlit dashboard

### Folder READMEs
- `data_generation/README.md`
- `pipeline_and_tests/README.md`
- `dashboard/README.md`

### Deliverables
- `AVRI_Deck.pptx`, editable presentation
- `AVRI_Deck.pdf`, submission copy
- `data_generation/output/*.parquet`, generated dataset (regeneratable)

---

## Pre-submission cleanup checklist

Before pushing to GitHub:

- [ ] **Delete `data_generation/venv/`**, Python virtualenv shouldn't be committed (huge folder; user will recreate). Add `venv/` to `.gitignore`.
- [ ] **Delete `data_generation/__pycache__/`** and any `*.pyc`, bytecode artifacts.
- [ ] **Decide whether to commit `data_generation/output/*.parquet`**, pro: zero-setup for reviewer; con: ~12 MB binary. I'd commit them; they regenerate identically anyway.
- [ ] **Verify `AVRI_Deck.pptx` and `.pdf` are at repo root**, brief asks for "PDF copy of your slide deck."
- [ ] **Strip personal/sandbox paths** from any output (none expected, but worth a quick `grep` for `/sessions/`).
- [ ] **Test clone-and-run on a fresh terminal**, confirm the README's quick-start sequence actually works end-to-end. This is the most important test before submission.

A `.gitignore` to drop in repo root:

```
venv/
__pycache__/
*.pyc
.DS_Store
.pytest_cache/
*.egg-info/
```
