# AVRI + RV Dashboard

Streamlit app connecting to BigQuery. v2.0 introduces the Realized Value
landing page and the Calibration sandbox; existing tabs were refactored
to read scores via `core/scoring.py` so calibration changes propagate
across all five tabs in real time.

## Run

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

Browser opens at `http://localhost:8501`.

## Authentication

Same as the rest of the project: `gcloud auth application-default login`
once per machine.

## Tabs (6 total in v2.0)

| Tab | Purpose | Consumer |
|---|---|---|
| 📈 **Realized Value** (landing) | Headline ARR vs Realized vs Unrealized + pillar-decomposition heatmap by region/segment/industry/CSM. Drill via dropdowns; selected cell highlighted with a blue ring. | Executive — *"where are dollars leaking?"* |
| 📊 Executive Overview | Region cards, AVRI distribution, CSM rankings — the v1 high-level dashboard. | Leadership |
| 👤 CSM Detail | Per-CSM book metrics, per-account table with pillar progress bars. | CS Operations |
| 🔍 Account Drill-down | Pick any account, see full pillar breakdown + time-series + comparison. | CSM, on-call |
| 🚨 At-Risk Renewals | Accounts renewing in 90 days, not Green. Sortable. | Individual CSMs |
| ⚙️ **Calibration** | Read-only display of every parameter in `core/config_v1.json` for transparency. | Reviewer / panel |

**AVRI vs CHS view is intentionally not a tab in v2.** The static crosstab on slide 3 of the deck and the AVRI vs CHS Stories tab in the lobby HTML carry that narrative. The interactive dashboard version was redundant; the code is preserved in `app.py` (wrapped in `if False:`) for easy revival.

## Sidebar global filters

- Region (multi-select)
- Segment (multi-select)
- Exclude cold-start (<90 days tenure)
- Include in-grace contracts (default: false; affects Realized Value tab)

## v2.0 architecture

The dashboard reads two kinds of data:

1. **BQ-materialized scored tables** (`avri_account`, `avri_csm`, `avri_region`)
   computed against the default config. Fast, used at startup and when no
   calibration changes are active.
2. **Live recomputation via `core/scoring.py`** when the Calibration tab
   has any non-default parameter. Pulls raw facts and composes scores in
   pandas. ~100 ms for the full 766-account population.

The contract guaranteeing both paths produce identical numbers for the
default config is the snapshot test in `core/test_scoring.py`. Re-run
after any change to either side.

## Calibration sandbox

The Calibration tab's purpose is **transparency**, not operational tuning.
It exists so that anyone reviewing this work can see — for every weight,
threshold, and curve breakpoint — that:

- The number is named and located in `core/config_v1.json`.
- Moving it has a visible, predictable effect across all five tabs.
- Production runs from the locked default config (version-controlled).

A sticky banner makes this explicit. The "Reset to defaults" button is
always visible.

## Demo flow

1. **Realized Value tab.** Headline: *"$291M total ARR, realizing 78%, $65M unrealized."* Heatmap by region — point at AMER's CR column, *"this is where most of the unrealized $ is concentrated."* Drill via the dropdowns: *"AMER × CR loss: 281 accounts contributing $15.8M. Top of the list is the renewal landmine."*
2. **At-Risk Renewals.** *"X accounts renewing in 90 days, sortable by unrealized $. The landmines surface at the top."*
3. **Account Drill-down → ACC-00026** (FLOOR RULE) → ACC-00876 (DECAY) → ACC-00298 (ESCALATE). The three deck stories.
4. **Calibration tab.** *"Every parameter in the metric is here. Production reads from `core/config_v1.json` and is locked; this tab is the transparency artifact."*

## Caching

All BigQuery queries cached for 10 minutes (`@st.cache_data(ttl=600)`).
Calibration tab edits invalidate the score cache (raw facts stay cached).
