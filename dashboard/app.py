"""GCS North Star — AVRI Dashboard

Streamlit prototype for the case study. Connects to BigQuery and surfaces:

  • Executive Overview — region & CSM performance at a glance
  • CSM Detail — drill into one CSM's book of accounts
  • Account Drill-down — full AVRI breakdown + comparison to existing metrics + time series
  • At-Risk Renewals — the worklist view (renewal-imminent + not green)

Run:
    cd dashboard
    pip install -r requirements.txt
    streamlit run app.py

Authentication:
    Same as pipeline — `gcloud auth application-default login` once on this machine.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from google.cloud import bigquery

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT = "panw-gcs-northstar"
DATASET = "gcs_north_star"

RAG_COLORS = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626", "onboarding": "#6366f1"}
PILLAR_COLORS = {
    "CR": "#2563eb",  # commit realization — blue
    "UM": "#ea580c",  # usage momentum — orange
    "DM": "#7c3aed",  # deployment maturity — purple
    "TH": "#059669",  # technical health — green
}

st.set_page_config(
    page_title="AVRI Dashboard — GCS North Star",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# BigQuery helpers (cached)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


@st.cache_data(ttl=600, show_spinner="Loading from BigQuery…")
def query(sql: str) -> pd.DataFrame:
    return get_client().query(sql).to_dataframe()


def fq(table: str) -> str:
    """Fully-qualified table name."""
    return f"`{PROJECT}.{DATASET}.{table}`"


# ---------------------------------------------------------------------------
# Sidebar — global filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("AVRI Dashboard")
    st.caption("Account Value Realization Index")
    st.divider()

    st.subheader("Global filters")
    region_filter = st.multiselect(
        "Region",
        options=["AMER", "EMEA", "APAC"],
        default=["AMER", "EMEA", "APAC"],
    )
    segment_filter = st.multiselect(
        "Segment",
        options=["Enterprise", "Mid-Market"],
        default=["Enterprise", "Mid-Market"],
    )
    exclude_cold_start = st.checkbox(
        "Exclude cold-start (<90 days tenure)",
        value=True,
        help="Cold-start accounts can't be reliably scored by momentum-based pillars. "
             "Hide them from rep performance views.",
    )

    st.divider()
    st.caption(f"Project: `{PROJECT}`")
    st.caption(f"Dataset: `{DATASET}`")
    st.caption("As-of: 2026-04-22")


# Filter clauses for SQL
def base_filters(account_alias: str = "a", apply_cold_start: bool = True) -> str:
    """Return WHERE-clause fragments to apply global filters at the account level.

    Pass apply_cold_start=False on tabs where the cold-start filter would
    distort the analysis (e.g., metric comparisons should be apples-to-apples
    across all in-scope accounts, not filtered to mature ones).
    """
    parts = []
    if region_filter:
        regions = ", ".join(f"'{r}'" for r in region_filter)
        parts.append(f"r.region IN ({regions})")
    if segment_filter:
        segments = ", ".join(f"'{s}'" for s in segment_filter)
        parts.append(f"r.segment IN ({segments})")
    if apply_cold_start and exclude_cold_start:
        parts.append(f"{account_alias}.cold_start_flag = FALSE")
    return " AND ".join(parts) if parts else "TRUE"


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

st.title("GCS North Star — AVRI + RV Dashboard")
st.caption("v2.0 — AVRI scores quality of execution; RV (Realized Value) composes ARR with AVRI to surface dollars at stake.")

tab_rv, tab_overview, tab_csm, tab_account, tab_renewals, tab_calib = st.tabs([
    "📈 Realized Value",
    "📊 Executive Overview",
    "👤 CSM Detail",
    "🔍 Account Drill-down",
    "🚨 At-Risk Renewals",
    "⚙️ Calibration",
])
# AVRI vs CHS view removed from the main tab row (v2.0). The static crosstab
# matrix on slide 3 of the deck and the AVRI vs CHS Stories tab in the lobby
# carry that narrative; the interactive dashboard version was redundant.
# To restore: re-add "🔄 AVRI vs CHS" to the tabs list above and uncomment the
# `with tab_crosstab:` block below.
tab_crosstab = None


# ===========================================================================
# TAB 0 — Realized Value (NEW v2.0 landing tab)
# ===========================================================================
with tab_rv:
    st.subheader("Where is ARR being realized? Where is it leaking?")
    st.caption("Linear v1: RV = ARR × AVRI/100. Onboarding accounts contribute zero. "
               "Headline below; pillar decomposition heatmap underneath.")

    # Drill-down state lives in session_state and is driven by the dropdowns
    # below the heatmap. The heatmap is purely visual; the matching cell
    # gets a highlight ring when the dropdowns are set to a specific
    # group × pillar.

    # Headline numbers
    rv_headline_sql = f"""
    SELECT
      COUNT(*) AS n_total,
      COUNTIF(a.avri_score IS NOT NULL) AS n_scored,
      COUNTIF(a.avri_score IS NULL)     AS n_grace,
      ROUND(SUM(a.arr_dollars), 2) AS total_arr,
      ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)), 2) AS scored_arr,
      ROUND(SUM(a.rv_dollars),  2) AS total_rv,
      ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)) - SUM(a.rv_dollars), 2) AS unrealized,
      ROUND(SAFE_DIVIDE(SUM(a.rv_dollars),
                        SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0))), 4) AS rate
    FROM {fq("avri_account")} a
    JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
    WHERE {base_filters(apply_cold_start=False)}
    """
    rv_h = query(rv_headline_sql).iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total ARR",       f"${rv_h['total_arr']/1e6:.1f}M",
                f"{int(rv_h['n_total'])} accounts")
    col2.metric("Realized $",      f"${rv_h['total_rv']/1e6:.1f}M",
                f"{rv_h['rate']*100:.1f}% realization", delta_color="off")
    col3.metric("Unrealized $",    f"${rv_h['unrealized']/1e6:.1f}M",
                "the renewal-risk pile", delta_color="inverse")
    col4.metric("In grace",        f"{int(rv_h['n_grace'])} accts",
                "deferred from scoring", delta_color="off")

    st.divider()

    # Pillar decomposition heatmap — group-by selector + sidebar-filter aware
    st.markdown("### Where the $ is being lost — by pillar")
    col_left, col_right = st.columns([1, 3])
    with col_left:
        group_by = st.selectbox(
            "Group rows by",
            options=["Region", "Segment", "Industry", "CSM (top 15)"],
            index=0,
            key="rv_group_by",
        )
    with col_right:
        st.caption("Cell shows $ unrealized to that pillar in that group, plus % of group's "
                   "scored ARR. Scan down a column to spot which group is weakest at that pillar. "
                   "Sidebar filters apply.")

    GROUP_COL = {
        "Region":        "r.region",
        "Segment":       "r.segment",
        "Industry":      "a.industry",
        "CSM (top 15)":  "r.csm_id",
    }[group_by]

    limit_clause = "LIMIT 15" if group_by == "CSM (top 15)" else ""

    heatmap_sql = f"""
    SELECT
      {GROUP_COL} AS grp,
      COUNT(*) AS n_accts,
      ROUND(SUM(a.arr_dollars), 0)            AS book_arr,
      ROUND(SUM(IF(a.avri_score IS NOT NULL, a.arr_dollars, 0)), 0) AS scored_arr,
      ROUND(SUM(a.rv_dollars), 0)             AS book_rv,
      ROUND(SUM(COALESCE(a.unrealized_cr_dollars,    0)), 0) AS u_cr,
      ROUND(SUM(COALESCE(a.unrealized_um_dollars,    0)), 0) AS u_um,
      ROUND(SUM(COALESCE(a.unrealized_dm_dollars,    0)), 0) AS u_dm,
      ROUND(SUM(COALESCE(a.unrealized_th_dollars,    0)), 0) AS u_th,
      ROUND(SUM(COALESCE(a.unrealized_floor_dollars, 0)), 0) AS u_floor
    FROM {fq("avri_account")} a
    JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
    WHERE {base_filters(apply_cold_start=False)}
    GROUP BY grp
    ORDER BY book_rv DESC
    {limit_clause}
    """
    rh = query(heatmap_sql)

    if rh.empty:
        st.info("No accounts in scope after sidebar filters.", icon="ℹ️")
    else:
        # Render heatmap as an HTML table — guaranteed visual control over
        # text color and background color. Plotly's annotation layer was not
        # honoring font.color in this Streamlit version, hence this fallback.
        pillar_short  = ["CR", "UM", "DM", "TH", "Floor"]
        pillar_full   = ["Commit<br>Realization",
                         "Usage<br>Momentum",
                         "Deployment<br>Maturity",
                         "Technical<br>Health",
                         "Floor<br>rule residual"]
        pillar_keys   = ["u_cr", "u_um", "u_dm", "u_th", "u_floor"]

        groups = rh["grp"].astype(str).tolist()

        # Compute per-cell percentages and find the global max for color scaling
        cell_pct = []
        for _, row in rh.iterrows():
            scored = max(row["scored_arr"], 1)
            cell_pct.append([row[k] / scored * 100 for k in pillar_keys])
        max_pct = max(max(r) for r in cell_pct) if cell_pct else 1.0
        max_pct = max(max_pct, 4.0)

        def cell_color(pct: float) -> tuple[str, str]:
            """Return (background_hex, text_hex) for a given pct value."""
            t = min(pct / max_pct, 1.0)
            # Interpolate between cream (#ffedd5) and dark amber (#7c2d12)
            stops = [(0.00, (255, 237, 213)),  # cream
                     (0.35, (253, 186, 116)),  # tan
                     (0.70, (234, 88,  12)),   # bright orange
                     (1.00, (124, 45,  18))]   # dark amber
            for i in range(len(stops) - 1):
                t0, c0 = stops[i]
                t1, c1 = stops[i + 1]
                if t <= t1:
                    f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                    r = int(c0[0] + f * (c1[0] - c0[0]))
                    g = int(c0[1] + f * (c1[1] - c0[1]))
                    b = int(c0[2] + f * (c1[2] - c0[2]))
                    bg = f"#{r:02x}{g:02x}{b:02x}"
                    # Text color: white if cell is dark (luminance threshold),
                    # else near-black for max contrast on light cells
                    luminance = 0.299*r + 0.587*g + 0.114*b
                    text = "#ffffff" if luminance < 140 else "#0a0a0a"
                    return bg, text
            return "#ffffff", "#0a0a0a"

        # Currently-selected cell (from previous click or selectbox)
        sel_group_now  = st.session_state.get("rv_drill_group")
        sel_pillar_now = st.session_state.get("rv_drill_pillar")
        sel_gb_now     = st.session_state.get("rv_drill_group_by")
        # Only apply highlight if drill matches current group_by (otherwise the drill is stale)
        if sel_gb_now != group_by:
            sel_group_now = None
            sel_pillar_now = None

        HIGHLIGHT_RING = "#1d4ed8"   # vivid blue for selected cell

        # Build HTML table — purely visual. Drill is driven by dropdowns below.
        html = ['<style>',
                '.rv-heatmap { width: 100%; border-collapse: separate; border-spacing: 4px; '
                '              font-family: -apple-system, "Segoe UI", system-ui, sans-serif; }',
                '.rv-heatmap th { padding: 10px 8px; font-size: 11px; font-weight: 700; '
                '                 color: #475569; text-transform: uppercase; letter-spacing: 0.04em; '
                '                 background: #f8fafc; border-radius: 6px; text-align: center; }',
                '.rv-heatmap td.rv-row-label { padding: 10px 12px; background: #f1f5f9; '
                '                              border-radius: 6px; font-weight: 700; color: #0f172a; '
                '                              font-size: 13px; }',
                '.rv-heatmap td.rv-row-label .rv-row-sub { display: block; font-weight: 400; '
                '                                          color: #64748b; font-size: 11px; '
                '                                          margin-top: 2px; }',
                '.rv-heatmap td.rv-cell { padding: 14px 8px; text-align: center; border-radius: 6px; '
                '                         min-width: 100px; }',
                '.rv-heatmap td.rv-cell .rv-d { font-size: 16px; font-weight: 700; }',
                '.rv-heatmap td.rv-cell .rv-p { font-size: 12px; font-weight: 500; opacity: 0.85; '
                '                                margin-top: 2px; }',
                f'.rv-heatmap td.rv-selected {{ outline: 3px solid {HIGHLIGHT_RING}; '
                f'                              outline-offset: -1px; '
                f'                              box-shadow: 0 0 0 2px white, 0 4px 12px rgba(29,78,216,0.35); }}',
                '</style>',
                '<table class="rv-heatmap">']
        # Header row
        html.append('<tr><th></th>')
        for i, p in enumerate(pillar_short):
            html.append(f'<th>{p}<br><span style="font-size:9px;font-weight:400;opacity:0.7">{pillar_full[i]}</span></th>')
        html.append('</tr>')
        # Data rows
        for i, group_name in enumerate(groups):
            arr_m = rh.iloc[i]["book_arr"] / 1e6
            n_a = int(rh.iloc[i]["n_accts"])
            html.append('<tr>')
            html.append(f'<td class="rv-row-label">{group_name}'
                        f'<span class="rv-row-sub">${arr_m:.0f}M ARR · {n_a} accts</span></td>')
            for j, k in enumerate(pillar_keys):
                v = rh.iloc[i][k]
                pct = cell_pct[i][j]
                bg, txt = cell_color(pct)
                is_selected = (group_name == sel_group_now) and (pillar_short[j] == sel_pillar_now)
                cell_class = "rv-cell rv-selected" if is_selected else "rv-cell"
                html.append(f'<td class="{cell_class}" style="background:{bg};color:{txt};">'
                            f'<div class="rv-d">${v/1e6:.1f}M</div>'
                            f'<div class="rv-p">{pct:.1f}%</div></td>')
            html.append('</tr>')
        html.append('</table>')
        st.markdown("".join(html), unsafe_allow_html=True)

        st.write("")  # spacer

        # Drill-down dropdowns — reflect session state (set by clicks or by manual choice)
        st.markdown(
            "**🔎 Drill into a cell** — click any cell above, or use the dropdowns. "
            "Clicking will highlight the cell and populate these selectors."
        )
        dcol1, dcol2, dcol3 = st.columns([2, 2, 1])
        # Compute defaults from session state
        _gp_default = st.session_state.get("rv_drill_group_pick") or st.session_state.get("rv_drill_group")
        _pl_default = st.session_state.get("rv_drill_pillar_pick") or st.session_state.get("rv_drill_pillar")
        with dcol1:
            drill_group_options = ["(no drill — show top-15 globally)"] + groups
            _idx = drill_group_options.index(_gp_default) if _gp_default in drill_group_options else 0
            sel_group = st.selectbox(f"{group_by} →", drill_group_options, index=_idx,
                                     key="rv_drill_group_pick")
        with dcol2:
            drill_pillar_options = ["(any)"] + pillar_short
            _idx = drill_pillar_options.index(_pl_default) if _pl_default in drill_pillar_options else 0
            sel_pillar = st.selectbox("Pillar →", drill_pillar_options, index=_idx,
                                      key="rv_drill_pillar_pick")
        with dcol3:
            st.write("")
            if st.button("Clear", key="rv_drill_clear"):
                for k in ("rv_drill_group", "rv_drill_pillar", "rv_drill_group_by",
                          "rv_drill_group_pick", "rv_drill_pillar_pick"):
                    st.session_state.pop(k, None)
                st.query_params.clear()
                st.rerun()

        is_drilled = sel_group != "(no drill — show top-15 globally)" and sel_pillar != "(any)"
        if is_drilled:
            st.session_state["rv_drill_group"]    = sel_group
            st.session_state["rv_drill_pillar"]   = sel_pillar
            st.session_state["rv_drill_group_by"] = group_by
        else:
            for k in ("rv_drill_group", "rv_drill_pillar", "rv_drill_group_by"):
                st.session_state.pop(k, None)

    st.divider()

    # Top renewal landmines — drilled by heatmap click if any
    drill_group   = st.session_state.get("rv_drill_group")
    drill_pillar  = st.session_state.get("rv_drill_pillar")
    drill_groupby = st.session_state.get("rv_drill_group_by")

    if drill_group and drill_pillar:
        st.markdown(f"### Renewal landmines — **{drill_group} × {drill_pillar} loss**")
        st.caption(f"Drilled view: top accounts in {drill_group} sorted by their {drill_pillar}-pillar "
                   f"contribution to unrealized $. Click the heatmap again to clear and return to the "
                   f"top-15 global landmines.")
    else:
        st.markdown("### Top 15 renewal landmines (largest single-account unrealized $)")
        st.caption("Where executive attention should go first. Sorted by unrealized $ descending. "
                   "Click any heatmap cell above to drill into a specific group × pillar.")

    # Build SQL based on whether we're drilled or not
    pillar_to_col = {
        "CR":    "a.unrealized_cr_dollars",
        "UM":    "a.unrealized_um_dollars",
        "DM":    "a.unrealized_dm_dollars",
        "TH":    "a.unrealized_th_dollars",
        "Floor": "a.unrealized_floor_dollars",
    }
    groupby_col_map = {
        "Region":       "r.region",
        "Segment":      "r.segment",
        "Industry":     "a.industry",
        "CSM (top 15)": "r.csm_id",
    }

    extra_where = ""
    sort_col = "(a.arr_dollars - a.rv_dollars)"
    if drill_group and drill_pillar and drill_groupby:
        gb = groupby_col_map.get(drill_groupby, "r.region")
        # Escape single quotes in the group value
        safe_group = drill_group.replace("'", "''")
        extra_where = f" AND {gb} = '{safe_group}'"
        sort_col = pillar_to_col.get(drill_pillar, sort_col)

    landmines_sql = f"""
    SELECT
      a.account_id, a.industry,
      ROUND(a.arr_dollars, 0) AS arr_dollars,
      ROUND(a.rv_dollars, 0)  AS rv_dollars,
      ROUND(a.arr_dollars - a.rv_dollars, 0) AS unrealized,
      ROUND(COALESCE(a.unrealized_cr_dollars,    0), 0) AS u_cr,
      ROUND(COALESCE(a.unrealized_um_dollars,    0), 0) AS u_um,
      ROUND(COALESCE(a.unrealized_dm_dollars,    0), 0) AS u_dm,
      ROUND(COALESCE(a.unrealized_th_dollars,    0), 0) AS u_th,
      ROUND(COALESCE(a.unrealized_floor_dollars, 0), 0) AS u_floor,
      ROUND(a.avri_score, 1)  AS avri_score,
      a.avri_color, a.floor_rule_triggered,
      a.rep_id, r.region, r.segment
    FROM {fq("avri_account")} a
    JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
    WHERE a.avri_score IS NOT NULL
      AND a.avri_color != 'green'
      AND {base_filters(apply_cold_start=False)}
      {extra_where}
    ORDER BY {sort_col} DESC
    LIMIT 15
    """
    lm = query(landmines_sql)
    if not lm.empty:
        # Pick which pillar contribution column to highlight
        pillar_col_short = {
            "CR": "u_cr", "UM": "u_um", "DM": "u_dm", "TH": "u_th", "Floor": "u_floor",
        }.get(drill_pillar)

        display_cols = ["account_id", "industry", "region", "segment",
                        "arr_dollars", "rv_dollars", "unrealized"]
        col_config = {
            "arr_dollars":  st.column_config.NumberColumn("ARR", format="$%d"),
            "rv_dollars":   st.column_config.NumberColumn("RV", format="$%d"),
            "unrealized":   st.column_config.NumberColumn("Unrealized $", format="$%d"),
            "avri_score":   st.column_config.ProgressColumn("AVRI", min_value=0, max_value=100, format="%.1f"),
        }
        if pillar_col_short:
            display_cols.append(pillar_col_short)
            col_config[pillar_col_short] = st.column_config.NumberColumn(
                f"{drill_pillar} loss $", format="$%d"
            )
        display_cols += ["avri_score", "avri_color", "floor_rule_triggered"]

        st.dataframe(
            lm[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
        )
    else:
        st.info("No landmines in this slice.", icon="ℹ️")

    st.info(
        "ℹ️ Sidebar filters (region/segment) apply. The cold-start exclusion is overridden on this tab "
        "so the matrix shows the full in-scope population. Realization rate denominator excludes "
        "in-grace accounts (their RV is 0 by construction).",
        icon="ℹ️",
    )


# ===========================================================================
# TAB X — Calibration sandbox (read-only display in this build)
# ===========================================================================
with tab_calib:
    st.subheader("Calibration sandbox")
    st.warning(
        "**Calibration sandbox.** Production runs locked defaults from `core/config_v1.json`. "
        "The values below are surfaced for transparency — every weight, threshold, and curve "
        "breakpoint is named and located in one file. In a future build, this tab adds live sliders.",
        icon="⚙️",
    )

    try:
        import json as _json
        from pathlib import Path as _Path
        cfg_path = _Path(__file__).resolve().parent.parent / "core" / "config_v1.json"
        with open(cfg_path) as _f:
            _cfg = _json.load(_f)

        st.markdown(f"**Config version:** `{_cfg.get('version', '?')}` · "
                    f"as-of `{_cfg.get('as_of_date', '?')}`")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### AVRI weights")
            w = _cfg["avri"]["weights"]
            st.write({k: v for k, v in w.items() if not k.startswith("_")})
            st.markdown("### Floor rule")
            st.write(_cfg["avri"]["floor_rule"])
            st.markdown("### Color thresholds")
            st.write(_cfg["avri"]["color_thresholds"])
            st.markdown("### Grace period (v1.3)")
            st.write({k: v for k, v in _cfg["grace_period"].items() if not k.startswith("_")})

        with col_b:
            st.markdown("### RV formula")
            st.write({k: v for k, v in _cfg["rv_formula"].items() if not k.startswith("_")})
            st.markdown("### TH pillar")
            st.write({k: v for k, v in _cfg["th_pillar"].items() if not k.startswith("_")})
            st.markdown("### DM pillar")
            st.write(_cfg["dm_pillar"])

        with st.expander("Full config JSON"):
            st.json(_cfg)
    except Exception as e:
        st.error(f"Could not load config: {e}")


# ===========================================================================
# TAB 1 — Executive Overview
# ===========================================================================
with tab_overview:
    st.subheader("How is the business doing?")

    # ---- Region cards ----
    region_sql = f"""
    SELECT
      r.region,
      COUNT(DISTINCT r.csm_id) AS csm_count,
      COUNT(DISTINCT a.account_id) AS account_count,
      SUM(a.arr_dollars) AS total_arr,
      ROUND(SAFE_DIVIDE(SUM(a.avri_score * a.arr_dollars), SUM(a.arr_dollars)), 1)
        AS region_avri,
      SUM(IF(a.avri_color = 'green',  1, 0)) AS green_count,
      SUM(IF(a.avri_color = 'yellow', 1, 0)) AS yellow_count,
      SUM(IF(a.avri_color = 'red',    1, 0)) AS red_count,
      SUM(IF(a.renewal_imminent_flag AND a.avri_color != 'green', 1, 0))
        AS at_risk_renewals
    FROM {fq("csm_rep")} r
    LEFT JOIN {fq("avri_account")} a ON r.csm_id = a.rep_id
    WHERE {base_filters()}
    GROUP BY r.region
    ORDER BY region_avri DESC
    """
    region_df = query(region_sql)

    if region_df.empty:
        st.warning("No data matches current filters.")
        st.stop()

    region_cols = st.columns(len(region_df))
    for col, (_, row) in zip(region_cols, region_df.iterrows()):
        with col:
            avri = row["region_avri"]
            color = (
                RAG_COLORS["green"] if avri >= 75
                else RAG_COLORS["yellow"] if avri >= 50
                else RAG_COLORS["red"]
            )
            st.markdown(
                f"""
                <div style="padding:14px 18px; border-radius:8px; border:1px solid #e2e8f0;
                            border-left:4px solid {color}; background:#ffffff;">
                  <div style="font-size:11px; color:#64748b; font-weight:700;
                              text-transform:uppercase; letter-spacing:0.04em;">
                    {row['region']}
                  </div>
                  <div style="font-size:36px; font-weight:700; color:{color}; line-height:1.0; margin:6px 0 4px;">
                    {avri:.1f}
                  </div>
                  <div style="font-size:12px; color:#475569;">
                    {int(row['account_count']):,} accounts ·
                    ${row['total_arr']/1_000_000:.1f}M ARR
                  </div>
                  <div style="font-size:11px; color:#64748b; margin-top:6px;">
                    🟢 {int(row['green_count'])}
                    🟡 {int(row['yellow_count'])}
                    🔴 {int(row['red_count'])}
                    &nbsp;|&nbsp;
                    <span style="color:#dc2626;">⚠ {int(row['at_risk_renewals'])} renewals at risk</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # ---- AVRI distribution chart ----
    col_dist, col_csm_chart = st.columns([1, 2])

    with col_dist:
        st.markdown("**AVRI distribution**")
        dist_sql = f"""
        SELECT a.avri_color, COUNT(*) AS n
        FROM {fq("avri_account")} a
        JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
        WHERE {base_filters()}
        GROUP BY a.avri_color
        """
        dist_df = query(dist_sql)
        dist_df["color_order"] = dist_df["avri_color"].map({"green": 0, "yellow": 1, "red": 2})
        dist_df = dist_df.sort_values("color_order")

        chart = alt.Chart(dist_df).mark_bar().encode(
            x=alt.X("avri_color:N", sort=["green", "yellow", "red"], title=None),
            y=alt.Y("n:Q", title="Accounts"),
            color=alt.Color(
                "avri_color:N",
                scale=alt.Scale(
                    domain=["green", "yellow", "red"],
                    range=[RAG_COLORS["green"], RAG_COLORS["yellow"], RAG_COLORS["red"]],
                ),
                legend=None,
            ),
            tooltip=["avri_color", "n"],
        ).properties(height=240)
        st.altair_chart(chart, use_container_width=True)

    with col_csm_chart:
        st.markdown("**Top & bottom CSMs (dollar-weighted AVRI)**")
        csm_chart_sql = f"""
        WITH ranked AS (
          SELECT
            r.name AS csm_name,
            r.region,
            ROUND(SAFE_DIVIDE(SUM(a.avri_score * a.arr_dollars), SUM(a.arr_dollars)), 1)
              AS csm_avri,
            COUNT(*) AS account_count
          FROM {fq("csm_rep")} r
          LEFT JOIN {fq("avri_account")} a ON r.csm_id = a.rep_id
          WHERE {base_filters()}
          GROUP BY r.name, r.region
          HAVING COUNT(*) >= 5
        ),
        labeled AS (
          SELECT
            *,
            ROW_NUMBER() OVER (ORDER BY csm_avri DESC NULLS LAST) AS rk_top,
            ROW_NUMBER() OVER (ORDER BY csm_avri ASC  NULLS LAST) AS rk_bot
          FROM ranked
          WHERE csm_avri IS NOT NULL
        )
        SELECT csm_name, region, csm_avri, account_count, 'TOP' AS pos
        FROM labeled WHERE rk_top <= 5
        UNION ALL
        SELECT csm_name, region, csm_avri, account_count, 'BOTTOM' AS pos
        FROM labeled WHERE rk_bot <= 5
        """
        csm_chart_df = query(csm_chart_sql)
        if not csm_chart_df.empty:
            chart = alt.Chart(csm_chart_df).mark_bar().encode(
                x=alt.X("csm_avri:Q", title="Dollar-weighted AVRI"),
                y=alt.Y("csm_name:N", sort="-x", title=None),
                color=alt.Color(
                    "pos:N",
                    scale=alt.Scale(
                        domain=["TOP", "BOTTOM"],
                        range=[RAG_COLORS["green"], RAG_COLORS["red"]],
                    ),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=["csm_name", "region", "csm_avri", "account_count"],
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

    st.divider()

    # ---- The "metrics zoo" comparison ----
    st.markdown("### Why AVRI beats the existing metrics")
    st.caption(
        "On the same 766 in-scope accounts: AVRI surfaces more risk than naive CHS, "
        "and rewards consistent overage that naive CHS misses."
    )

    compare_sql = f"""
    WITH m AS (
      SELECT
        a.account_id, a.avri_score, a.avri_color, e.naive_chs_score
      FROM {fq("avri_account")} a
      JOIN {fq("metrics_existing_account")} e USING (account_id)
      JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
      WHERE {base_filters()}
    )
    SELECT
      'AVRI' AS metric,
      SUM(IF(avri_color = 'green', 1, 0)) AS green,
      SUM(IF(avri_color = 'yellow', 1, 0)) AS yellow,
      SUM(IF(avri_color = 'red', 1, 0)) AS red
    FROM m
    UNION ALL
    SELECT
      'Naive CHS' AS metric,
      SUM(IF(naive_chs_score >= 75, 1, 0)) AS green,
      SUM(IF(naive_chs_score >= 50 AND naive_chs_score < 75, 1, 0)) AS yellow,
      SUM(IF(naive_chs_score < 50, 1, 0)) AS red
    FROM m
    """
    cmp_df = query(compare_sql)
    cmp_df["green"]  = cmp_df["green"].fillna(0).astype(int)
    cmp_df["yellow"] = cmp_df["yellow"].fillna(0).astype(int)
    cmp_df["red"]    = cmp_df["red"].fillna(0).astype(int)

    def stacked_bar_html(label: str, g: int, y: int, r: int) -> str:
        total = g + y + r
        if total == 0:
            return f"<div style='margin:8px 0;'>{label}: <em>no data</em></div>"
        g_pct, y_pct, r_pct = (100*g/total, 100*y/total, 100*r/total)
        return f"""
        <div style="display:grid; grid-template-columns: 110px 1fr 180px;
                    align-items:center; gap:14px; margin:10px 0;">
          <div style="font-weight:700; font-size:14px; color:#0f172a;">{label}</div>
          <div style="display:flex; height:34px; border-radius:6px; overflow:hidden;
                      border:1px solid #cbd5e1;">
            <div style="width:{g_pct:.2f}%; background:{RAG_COLORS['green']};
                        display:flex; align-items:center; justify-content:center;
                        color:#fff; font-size:12px; font-weight:600;"
                 title="Green: {g} accounts ({g_pct:.0f}%)">
              {g_pct:.0f}%
            </div>
            <div style="width:{y_pct:.2f}%; background:{RAG_COLORS['yellow']};
                        display:flex; align-items:center; justify-content:center;
                        color:#fff; font-size:12px; font-weight:600;"
                 title="Yellow: {y} accounts ({y_pct:.0f}%)">
              {y_pct:.0f}%
            </div>
            <div style="width:{r_pct:.2f}%; background:{RAG_COLORS['red']};
                        display:flex; align-items:center; justify-content:center;
                        color:#fff; font-size:12px; font-weight:600;"
                 title="Red: {r} accounts ({r_pct:.0f}%)">
              {r_pct:.0f}%
            </div>
          </div>
          <div style="font-size:12px; color:#64748b;">
            🟢 {g} &nbsp;·&nbsp; 🟡 {y} &nbsp;·&nbsp; 🔴 {r}
            &nbsp;|&nbsp; <b>{total}</b>
          </div>
        </div>
        """

    bars_html = ""
    for metric_name in ["AVRI", "Naive CHS"]:
        row = cmp_df[cmp_df["metric"] == metric_name]
        if not row.empty:
            r = row.iloc[0]
            bars_html += stacked_bar_html(metric_name, r["green"], r["yellow"], r["red"])

    st.markdown(bars_html, unsafe_allow_html=True)


# ===========================================================================
# TAB — AVRI vs CHS Crosstab (DISABLED in v2.0 — see tab list above)
# ===========================================================================
with tab_csm:  # placeholder no-op context; this entire block is unreachable
  if False:
    st.subheader("Where do AVRI and naive CHS disagree?")
    st.caption("Each cell shows accounts that fall in that AVRI×CHS combination. Diagonal cells = agreement. "
               "Off-diagonal cells reveal where AVRI's decisions differ — and why those differences matter.")
    st.info(
        "ℹ️ This tab **overrides the sidebar's 'exclude cold-start' filter** so the matrix shows all in-scope "
        "accounts (matches the lobby HTML's static snapshot). Region and segment filters still apply. "
        "Cold-start filtering is for CSM/rep-performance views, not for metric comparison.",
        icon="ℹ️",
    )

    # ---- Compute the crosstab ----
    crosstab_sql = f"""
    WITH joined AS (
      SELECT
        a.account_id,
        a.avri_color,
        CASE
          WHEN e.naive_chs_score >= 75 THEN 'green'
          WHEN e.naive_chs_score >= 50 THEN 'yellow'
          ELSE 'red'
        END AS chs_color,
        a.arr_dollars
      FROM {fq("avri_account")} a
      JOIN {fq("metrics_existing_account")} e USING (account_id)
      JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
      WHERE {base_filters(apply_cold_start=False)}
    )
    SELECT
      avri_color,
      chs_color,
      COUNT(*) AS n,
      ROUND(SUM(arr_dollars) / 1e6, 2) AS total_arr_m
    FROM joined
    GROUP BY avri_color, chs_color
    """
    cx = query(crosstab_sql)
    cx["n"] = cx["n"].fillna(0).astype(int)

    # ---- Build pivoted matrix for HTML render ----
    chs_order = ["green", "yellow", "red"]
    avri_order = ["green", "yellow", "red", "onboarding"]
    n_pivot = (
        cx.pivot_table(index="avri_color", columns="chs_color", values="n", fill_value=0, aggfunc="sum")
        .reindex(index=avri_order, columns=chs_order, fill_value=0)
    )
    arr_pivot = (
        cx.pivot_table(index="avri_color", columns="chs_color", values="total_arr_m", fill_value=0, aggfunc="sum")
        .reindex(index=avri_order, columns=chs_order, fill_value=0)
    )

    # Cell narratives — the reason each disagreement exists
    NARRATIVES = {
        ("green", "green"):       ("AGREEMENT", "Both metrics see this account as healthy. No action needed."),
        ("yellow", "yellow"):     ("AGREEMENT", "Both flag for watch. CSM intervention recommended."),
        ("red", "red"):           ("AGREEMENT", "Both escalate. Active renewal risk."),
        ("green", "yellow"):      ("AVRI rescues", "Naive CHS over-penalizes accounts with one bad week. AVRI's decay-weighted TH gets the trend right."),
        ("green", "red"):         ("AVRI strongly disagrees", "Usually consistent overage. Naive CHS treats high utilization as failure; AVRI rewards it as healthy expansion."),
        ("yellow", "green"):      ("AVRI flags watch", "AVRI catches early signals naive CHS misses — borderline shelfware, momentum decay, or floor-rule trigger."),
        ("yellow", "red"):        ("AVRI moderates", "Naive CHS over-escalates; AVRI sees enough positive signals (consumption, breadth, momentum) to keep it in watch zone, not red."),
        ("red", "green"):         ("AVRI catches hidden risk", "The strongest deck story. Usually shelfware where health_color is still green from earlier in the year but consumption has collapsed. CHS is fooled; AVRI sees through."),
        ("red", "yellow"):        ("AVRI is more decisive", "CHS hedges; AVRI escalates. Usually accounts where multiple pillars are weak in addition to a yellow color signal."),
        ("onboarding", "green"):  ("Out of scope (v1.3)", "Newly-signed contract still in 90-day grace. Not yet scored. Naive CHS still rates it (largely on the ARR component)."),
        ("onboarding", "yellow"): ("Out of scope (v1.3)", "Newly-signed contract still in grace; CHS rates it ambiguously."),
        ("onboarding", "red"):    ("Out of scope (v1.3)", "Newly-signed contract still in grace; CHS may flag based on ARR component or low utilization, but AVRI defers judgment."),
    }

    # ---- Render the crosstab as styled HTML ----
    cell_color_for = {
        "green":       RAG_COLORS["green"],
        "yellow":      RAG_COLORS["yellow"],
        "red":         RAG_COLORS["red"],
        "onboarding":  RAG_COLORS["onboarding"],
    }
    diagonal_pairs = {("green", "green"), ("yellow", "yellow"), ("red", "red")}

    def cell_style(avri_c, chs_c):
        n = int(n_pivot.loc[avri_c, chs_c])
        is_diag = (avri_c, chs_c) in diagonal_pairs
        is_zero = n == 0
        # Diagonal = neutral light gray (agreement). Off-diagonal = orange-tinted (interesting).
        if is_zero:
            bg = "#F8FAFC"
            border = "#E2E8F0"
        elif is_diag:
            bg = "#F1F5F9"
            border = "#CBD5E1"
        else:
            # Heatmap: lighter for small disagreements, darker for big
            intensity = min(n / 100.0, 1.0)
            r, g, b = 254, 215, 170  # warm orange tint
            bg = f"#{r:02x}{g:02x}{b:02x}"
            border = "#EA580C" if n >= 20 else "#FDBA74"
        return bg, border

    html = ['<table style="border-collapse: separate; border-spacing: 4px; width: 100%; max-width: 800px;">']
    # Header row
    html.append('<tr><th style="padding: 8px;"></th>')
    for chs_c in chs_order:
        html.append(
            f'<th style="padding: 10px; background: {cell_color_for[chs_c]}; '
            f'color: white; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; '
            f'border-radius: 6px;">CHS {chs_c}</th>'
        )
    html.append("</tr>")
    # Data rows
    for avri_c in avri_order:
        row_total = int(n_pivot.loc[avri_c].sum())
        if row_total == 0:
            continue
        html.append("<tr>")
        html.append(
            f'<th style="padding: 10px; background: {cell_color_for[avri_c]}; '
            f'color: white; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; '
            f'border-radius: 6px; text-align: right;">AVRI {avri_c}</th>'
        )
        for chs_c in chs_order:
            n = int(n_pivot.loc[avri_c, chs_c])
            arr_m = float(arr_pivot.loc[avri_c, chs_c])
            bg, border = cell_style(avri_c, chs_c)
            label, _ = NARRATIVES.get((avri_c, chs_c), ("", ""))
            label_html = (
                f'<div style="font-size:9.5px; color:#64748b; text-transform:uppercase; '
                f'letter-spacing: 0.04em; margin-top: 4px;">{label}</div>' if label and not (avri_c, chs_c) in diagonal_pairs else ""
            )
            html.append(
                f'<td style="background: {bg}; border: 1.5px solid {border}; '
                f'padding: 14px 12px; text-align: center; border-radius: 6px;">'
                f'<div style="font-size: 24px; font-weight: 700; color: #0f172a;">{n}</div>'
                f'<div style="font-size: 11px; color: #64748b;">${arr_m:.1f}M ARR</div>'
                f'{label_html}'
                f"</td>"
            )
        html.append("</tr>")
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.write("")
    st.markdown(
        "**Reading the matrix:** rows are AVRI's verdict; columns are naive CHS's verdict. "
        "**Diagonal cells** (gray-ish) are where the two metrics agree. **Off-diagonal cells** "
        "(orange-tinted) are where they disagree — that's the analytically interesting territory."
    )

    st.divider()

    # ---- Drill-down: pick a cell, see the accounts ----
    st.markdown("### Drill into a specific cell")
    st.caption("Pick an AVRI verdict and a CHS verdict. The table below shows accounts in that cell — "
               "their pillar scores, both metric scores, and key signals — so you can see exactly why they disagree.")

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        sel_avri = st.selectbox(
            "AVRI color",
            options=[c for c in avri_order if int(n_pivot.loc[c].sum()) > 0],
            index=0,
        )
    with col_b:
        sel_chs = st.selectbox(
            "CHS color",
            options=chs_order,
            index=0,
        )
    with col_c:
        # Show the narrative for this cell
        label, narrative = NARRATIVES.get((sel_avri, sel_chs), ("", "No accounts in this cell."))
        cell_n = int(n_pivot.loc[sel_avri, sel_chs])
        if cell_n == 0:
            st.info(f"**No accounts** match AVRI {sel_avri} × CHS {sel_chs}.")
        else:
            st.markdown(
                f"<div style='padding:10px 14px; background:#fef3c7; border-left:3px solid #ea580c; "
                f"border-radius:4px; font-size:13px; color:#78350f;'>"
                f"<b style='color:#0f172a;'>{label}</b> "
                f"<span style='color:#475569;'>— {narrative}</span> "
                f"<span style='color:#94a3b8;'>({cell_n} accounts in this cell)</span></div>",
                unsafe_allow_html=True,
            )

    if cell_n > 0:
        # Pull the actual accounts in this cell
        # CHS color thresholds inverted from naive_chs_score (75 / 50)
        if sel_chs == "green":
            chs_filter = "e.naive_chs_score >= 75"
        elif sel_chs == "yellow":
            chs_filter = "e.naive_chs_score >= 50 AND e.naive_chs_score < 75"
        else:
            chs_filter = "e.naive_chs_score < 50"

        detail_sql = f"""
        SELECT
          a.account_id, a.industry, a.arr_dollars, a.tenure_days,
          a.cr_score, a.um_score, a.dm_score, a.th_score,
          a.avri_score,
          e.naive_chs_score,
          e.utilization_90d AS naive_util,
          e.latest_color    AS chs_latest_color,
          e.active_days_30  AS active_days_30,
          a.has_grace_contract,
          a.grace_contracts,
          a.floor_rule_triggered
        FROM {fq("avri_account")} a
        JOIN {fq("metrics_existing_account")} e USING (account_id)
        JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
        WHERE a.avri_color = '{sel_avri}'
          AND {chs_filter}
          AND {base_filters(apply_cold_start=False)}
        ORDER BY a.arr_dollars DESC
        LIMIT 50
        """
        detail_df = query(detail_sql)

        st.dataframe(
            detail_df,
            use_container_width=True,
            height=420,
            hide_index=True,
            column_config={
                "arr_dollars":      st.column_config.NumberColumn("ARR", format="$%d"),
                "tenure_days":      st.column_config.NumberColumn("Tenure"),
                "avri_score":       st.column_config.ProgressColumn("AVRI", min_value=0, max_value=100, format="%.1f"),
                "naive_chs_score":  st.column_config.ProgressColumn("CHS", min_value=0, max_value=100, format="%.1f"),
                "cr_score":         st.column_config.ProgressColumn("CR", min_value=0, max_value=100, format="%.0f"),
                "um_score":         st.column_config.ProgressColumn("UM", min_value=0, max_value=100, format="%.0f"),
                "dm_score":         st.column_config.ProgressColumn("DM", min_value=0, max_value=100, format="%.0f"),
                "th_score":         st.column_config.ProgressColumn("TH", min_value=0, max_value=100, format="%.0f"),
                "naive_util":       st.column_config.NumberColumn("Naive util", format="%.2f"),
                "chs_latest_color": "Latest color",
                "active_days_30":   st.column_config.NumberColumn("Active days/30"),
                "has_grace_contract": "Has grace?",
                "grace_contracts":   st.column_config.NumberColumn("# grace"),
                "floor_rule_triggered": "Floor rule",
            },
        )

        st.caption(
            "**How to read a row:** compare the pillar columns (CR / UM / DM / TH) to see which dimension is "
            "driving AVRI's verdict, vs `naive_util` and `chs_latest_color` which together drive most of CHS. "
            "Big disagreements usually trace to one of: (a) trajectory — AVRI sees decay UM doesn't see snapshot; "
            "(b) decay weighting — AVRI's TH softens a single bad color where CHS hits hard; (c) floor rule — "
            "AVRI capped at 50 even when other pillars are high."
        )


# ===========================================================================
# TAB 2 — CSM Detail
# ===========================================================================
with tab_csm:
    st.subheader("CSM book health")

    # CSM picker
    csm_sql = f"""
    SELECT
      r.csm_id, r.csm_name AS name, r.region, r.segment, r.book_arr_dollars,
      r.csm_avri_dollar_weighted AS avri,
      r.green_count, r.yellow_count, r.red_count, r.at_risk_renewals_90d
    FROM {fq("avri_csm")} r
    WHERE r.region IN ({", ".join(f"'{x}'" for x in region_filter) or "''"})
      AND r.segment IN ({", ".join(f"'{x}'" for x in segment_filter) or "''"})
    ORDER BY avri ASC NULLS LAST
    """
    csm_df = query(csm_sql)

    if csm_df.empty:
        st.warning("No CSMs match current filters.")
    else:
        sel_csm = st.selectbox(
            "Select CSM",
            csm_df["csm_id"],
            format_func=lambda c: f"{c} — {csm_df[csm_df.csm_id==c].iloc[0]['name']} "
                                  f"({csm_df[csm_df.csm_id==c].iloc[0]['region']}, "
                                  f"{csm_df[csm_df.csm_id==c].iloc[0]['segment']})",
        )

        csm_row = csm_df[csm_df.csm_id == sel_csm].iloc[0]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Dollar-weighted AVRI", f"{csm_row['avri']:.1f}" if pd.notna(csm_row['avri']) else "—")
        c2.metric("Book ARR", f"${csm_row['book_arr_dollars']/1e6:.2f}M" if pd.notna(csm_row['book_arr_dollars']) else "—")
        c3.metric("🟢 Green",  int(csm_row["green_count"]))
        c4.metric("🟡 Yellow", int(csm_row["yellow_count"]))
        c5.metric("🔴 Red",    int(csm_row["red_count"]))

        if csm_row["at_risk_renewals_90d"] and csm_row["at_risk_renewals_90d"] > 0:
            st.error(
                f"⚠ {int(csm_row['at_risk_renewals_90d'])} accounts in this book are "
                f"renewing in the next 90 days AND not Green."
            )

        st.markdown("**Accounts in this book**")
        accts_sql = f"""
        SELECT
          account_id, company_name, industry, arr_dollars, tenure_days,
          days_to_renewal, avri_score, avri_color,
          cr_score, um_score, dm_score, th_score,
          floor_rule_triggered, capacity_expansion_flag, renewal_imminent_flag
        FROM {fq("avri_account")}
        WHERE rep_id = '{sel_csm}'
        ORDER BY avri_score ASC
        """
        accts_df = query(accts_sql)

        st.dataframe(
            accts_df,
            use_container_width=True,
            height=400,
            hide_index=True,
            column_config={
                "arr_dollars": st.column_config.NumberColumn("ARR", format="$%d"),
                "avri_score": st.column_config.ProgressColumn("AVRI", min_value=0, max_value=100, format="%.1f"),
                "cr_score": st.column_config.ProgressColumn("CR", min_value=0, max_value=100, format="%.0f"),
                "um_score": st.column_config.ProgressColumn("UM", min_value=0, max_value=100, format="%.0f"),
                "dm_score": st.column_config.ProgressColumn("DM", min_value=0, max_value=100, format="%.0f"),
                "th_score": st.column_config.ProgressColumn("TH", min_value=0, max_value=100, format="%.0f"),
                "tenure_days": st.column_config.NumberColumn("Tenure (d)"),
                "days_to_renewal": st.column_config.NumberColumn("→Renewal (d)"),
                "floor_rule_triggered": "Floor rule",
                "capacity_expansion_flag": "Expansion",
                "renewal_imminent_flag": "Renewal soon",
            },
        )


# ===========================================================================
# TAB 3 — Account Drill-down
# ===========================================================================
with tab_account:
    st.subheader("Account drill-down")
    st.caption("Pick an account to see its full AVRI breakdown, comparison to existing metrics, and consumption history.")

    accounts_sql = f"""
    SELECT a.account_id, a.company_name, a.industry, a.arr_dollars, a.avri_score, a.avri_color
    FROM {fq("avri_account")} a
    JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
    WHERE {base_filters()}
    ORDER BY a.arr_dollars DESC
    """
    accts_df = query(accounts_sql)

    if accts_df.empty:
        st.warning("No accounts match current filters.")
    else:
        # Search/select
        col_sel, col_jump = st.columns([3, 1])
        with col_sel:
            sel_acct = st.selectbox(
                "Account",
                accts_df["account_id"],
                format_func=lambda x: (
                    f"{x} — {accts_df[accts_df.account_id==x].iloc[0]['company_name']} · "
                    f"{accts_df[accts_df.account_id==x].iloc[0]['industry']} · "
                    f"${accts_df[accts_df.account_id==x].iloc[0]['arr_dollars']:,.0f} ARR · "
                    f"AVRI {accts_df[accts_df.account_id==x].iloc[0]['avri_score']:.1f} "
                    f"({accts_df[accts_df.account_id==x].iloc[0]['avri_color']})"
                ),
            )
        with col_jump:
            jump_options = {
                "Pick deck story…": None,
                "ACC-00202 (Shelfware)": "ACC-00202",
                "ACC-00226 (Floor rule)": "ACC-00226",
                "ACC-00876 (Overage rewarded)": "ACC-00876",
                "ACC-00218 (At-risk $3.6M)": "ACC-00218",
            }
            jumped = st.selectbox("Quick deck examples", list(jump_options.keys()))
            if jump_options[jumped]:
                sel_acct = jump_options[jumped]

        # Account details
        detail_sql = f"""
        SELECT
          a.*, e.naive_chs_score, e.tcv_dollars, e.consumed_90d_credits,
          e.monthly_commit_credits * 3 AS commit_90d_credits,
          e.utilization_90d AS naive_util_90d, e.latest_color
        FROM {fq("avri_account")} a
        LEFT JOIN {fq("metrics_existing_account")} e USING (account_id)
        WHERE a.account_id = '{sel_acct}'
        """
        detail = query(detail_sql).iloc[0]

        # Header card
        avri_color_hex = RAG_COLORS.get(detail["avri_color"], "#64748b")
        st.markdown(
            f"""
            <div style="padding:18px 22px; border-radius:8px; background:#0f172a; color:#fff;
                       border-left:6px solid {avri_color_hex};">
              <div style="font-size:13px; color:#cbd5e1;">{detail['account_id']} · {detail['industry']}</div>
              <div style="font-size:24px; font-weight:700; margin:4px 0;">{detail['company_name']}</div>
              <div style="font-size:13px; color:#cbd5e1;">
                ${detail['arr_dollars']:,.0f} ARR · {int(detail['tenure_days'])} days tenure ·
                {int(detail['days_to_renewal'])} days to renewal
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")

        # Pillar breakdown vs metrics zoo
        col_pillars, col_metrics = st.columns([3, 2])

        with col_pillars:
            st.markdown("**AVRI pillar breakdown**")
            pillars_df = pd.DataFrame({
                "pillar": ["CR", "UM", "DM", "TH"],
                "name":   ["Commit Realization", "Usage Momentum", "Deployment Maturity", "Technical Health"],
                "score":  [detail["cr_score"], detail["um_score"], detail["dm_score"], detail["th_score"]],
                "weight": [30, 30, 20, 20],
            })
            pillars_df["weighted"] = pillars_df["score"] * pillars_df["weight"] / 100

            chart = alt.Chart(pillars_df).mark_bar().encode(
                y=alt.Y("name:N", sort=["Commit Realization", "Usage Momentum", "Deployment Maturity", "Technical Health"], title=None),
                x=alt.X("score:Q", title="Pillar score (0-100)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color(
                    "pillar:N",
                    scale=alt.Scale(
                        domain=["CR", "UM", "DM", "TH"],
                        range=[PILLAR_COLORS["CR"], PILLAR_COLORS["UM"],
                               PILLAR_COLORS["DM"], PILLAR_COLORS["TH"]],
                    ),
                    legend=None,
                ),
                tooltip=["name", "score", "weight", "weighted"],
            ).properties(height=200)
            st.altair_chart(chart, use_container_width=True)

            st.markdown(
                f"<div style='font-size:13px; color:#475569;'>"
                f"Composite raw: <b>{detail['avri_raw']:.1f}</b> · "
                f"Final AVRI (after floor rule): <b style='color:{avri_color_hex};'>{detail['avri_score']:.1f}</b>"
                f"{' · ⚠ Floor rule triggered (TH<30)' if detail['floor_rule_triggered'] else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_metrics:
            st.markdown("**vs. existing metrics**")
            zoo_df = pd.DataFrame({
                "Metric": ["AVRI (ours)", "Naive CHS", "Raw 90d Util %", "Latest health color"],
                "Value": [
                    f"{detail['avri_score']:.1f} ({detail['avri_color']})",
                    f"{detail['naive_chs_score']:.1f}",
                    f"{detail['naive_util_90d']*100:.0f}%" if pd.notna(detail['naive_util_90d']) else "—",
                    detail['latest_color'] if pd.notna(detail['latest_color']) else "—",
                ],
            })
            st.dataframe(zoo_df, hide_index=True, use_container_width=True)

            st.metric("TCV (lifetime)", f"${detail['tcv_dollars']:,.0f}")
            st.metric("Consumed (90d)", f"{int(detail['consumed_90d_credits']):,} credits")
            st.metric("Commit (90d)",   f"{int(detail['commit_90d_credits']):,} credits")

        st.divider()

        # ---- Time series ----
        st.markdown("**Daily consumption (last 365 days)**")
        ts_sql = f"""
        WITH days AS (
          SELECT DATE_SUB(DATE('2026-04-22'), INTERVAL n DAY) AS date
          FROM UNNEST(GENERATE_ARRAY(0, 364)) AS n
        )
        SELECT
          d.date,
          COALESCE(SUM(u.compute_credits_consumed), 0) AS credits
        FROM days d
        LEFT JOIN {fq("daily_usage_logs")} u
          ON u.account_id = '{sel_acct}' AND u.date = d.date
        GROUP BY d.date
        ORDER BY d.date
        """
        ts_df = query(ts_sql)

        if not ts_df.empty:
            ts_chart = alt.Chart(ts_df).mark_area(
                color=PILLAR_COLORS["UM"], opacity=0.6,
            ).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("credits:Q", title="Credits consumed"),
                tooltip=["date:T", "credits:Q"],
            ).properties(height=200)
            st.altair_chart(ts_chart, use_container_width=True)
            st.caption(
                "Look for spike-and-drop (tall early bar then zero), shelfware (flat zero throughout), "
                "or steady growth (gradually rising baseline)."
            )

        # ---- Health color timeline ----
        st.markdown("**Health color timeline (weekly snapshots)**")
        health_sql = f"""
        SELECT date, health_color
        FROM {fq("account_health")}
        WHERE account_id = '{sel_acct}'
        ORDER BY date
        """
        health_df = query(health_sql)
        if not health_df.empty:
            health_chart = alt.Chart(health_df).mark_rect(width=8, height=30).encode(
                x=alt.X("date:T", title=None),
                color=alt.Color(
                    "health_color:N",
                    scale=alt.Scale(
                        domain=["green", "yellow", "red"],
                        range=[RAG_COLORS["green"], RAG_COLORS["yellow"], RAG_COLORS["red"]],
                    ),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=["date:T", "health_color"],
            ).properties(height=60)
            st.altair_chart(health_chart, use_container_width=True)


# ===========================================================================
# TAB 4 — At-Risk Renewals
# ===========================================================================
with tab_renewals:
    st.subheader("At-risk renewals — the CSM worklist")
    st.caption("Accounts whose contract is renewing in the next 90 days AND AVRI is not Green. "
               "Sorted by ARR — biggest dollars at risk at the top.")

    days_filter = st.slider("Days to renewal (max)", min_value=30, max_value=180, value=90, step=15)
    min_arr = st.number_input("Minimum ARR (filter)", min_value=0, value=0, step=10000, format="%d")

    risk_sql = f"""
    SELECT
      a.account_id, a.company_name, a.industry, a.arr_dollars,
      a.days_to_renewal, a.tenure_days, a.avri_score, a.avri_color,
      a.cr_score, a.um_score, a.dm_score, a.th_score,
      a.rep_id, r.name AS csm_name, r.region
    FROM {fq("avri_account")} a
    JOIN {fq("csm_rep")} r ON a.rep_id = r.csm_id
    WHERE a.days_to_renewal IS NOT NULL
      AND a.days_to_renewal <= {days_filter}
      AND a.avri_color != 'green'
      AND a.arr_dollars >= {min_arr}
      AND r.region IN ({", ".join(f"'{x}'" for x in region_filter) or "''"})
      AND r.segment IN ({", ".join(f"'{x}'" for x in segment_filter) or "''"})
    ORDER BY a.arr_dollars DESC
    """
    risk_df = query(risk_sql)

    if risk_df.empty:
        st.success("No at-risk renewals in the selected window.")
    else:
        # Headline: dollars at risk
        total_at_risk = risk_df["arr_dollars"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("$ at risk", f"${total_at_risk/1e6:.2f}M")
        c2.metric("Accounts", f"{len(risk_df)}")
        c3.metric("Avg AVRI", f"{risk_df['avri_score'].mean():.1f}")

        st.dataframe(
            risk_df,
            use_container_width=True,
            height=480,
            hide_index=True,
            column_config={
                "arr_dollars": st.column_config.NumberColumn("ARR", format="$%d"),
                "days_to_renewal": st.column_config.NumberColumn("Days→Renewal"),
                "tenure_days": st.column_config.NumberColumn("Tenure"),
                "avri_score": st.column_config.ProgressColumn("AVRI", min_value=0, max_value=100, format="%.1f"),
                "cr_score": st.column_config.ProgressColumn("CR", min_value=0, max_value=100, format="%.0f"),
                "um_score": st.column_config.ProgressColumn("UM", min_value=0, max_value=100, format="%.0f"),
                "dm_score": st.column_config.ProgressColumn("DM", min_value=0, max_value=100, format="%.0f"),
                "th_score": st.column_config.ProgressColumn("TH", min_value=0, max_value=100, format="%.0f"),
            },
        )
