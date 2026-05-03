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

RAG_COLORS = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}
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
def base_filters(account_alias: str = "a") -> str:
    """Return WHERE-clause fragments to apply global filters at the account level."""
    parts = []
    if region_filter:
        regions = ", ".join(f"'{r}'" for r in region_filter)
        parts.append(f"r.region IN ({regions})")
    if segment_filter:
        segments = ", ".join(f"'{s}'" for s in segment_filter)
        parts.append(f"r.segment IN ({segments})")
    if exclude_cold_start:
        parts.append(f"{account_alias}.cold_start_flag = FALSE")
    return " AND ".join(parts) if parts else "TRUE"


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

st.title("GCS North Star — AVRI Dashboard")
st.caption("Customer Value Realization, measured at account · CSM · region grain.")

tab_overview, tab_csm, tab_account, tab_renewals = st.tabs([
    "📊 Executive Overview",
    "👤 CSM Detail",
    "🔍 Account Drill-down",
    "🚨 At-Risk Renewals",
])


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
