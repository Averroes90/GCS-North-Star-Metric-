# AVRI Dashboard

Streamlit prototype connecting to BigQuery. Demo-ready interactive view of the AVRI metric.

## Run

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

Browser opens automatically at `http://localhost:8501`.

## Authentication

Same as the rest of the project, `gcloud auth application-default login` once on the machine.

## Views

1. **📊 Executive Overview**, region cards, AVRI distribution, top/bottom CSMs, "AVRI vs Naive CHS" comparison stack chart.
2. **👤 CSM Detail**, pick a CSM, see their book metrics + per-account table with pillar progress bars.
3. **🔍 Account Drill-down**, pick any account (or use the "deck story" quick picker) for full AVRI breakdown, comparison to existing metrics, daily-consumption time series, weekly health-color timeline.
4. **🚨 At-Risk Renewals**, the worklist. Renewal-imminent + not-Green accounts, sorted by ARR. Filterable by days-to-renewal and minimum ARR.

## Sidebar global filters

- Region (multi-select)
- Segment (multi-select)
- Exclude cold-start (<90 days tenure), checkbox

These filters apply to all four tabs.

## Demo flow (5 minutes)

1. **Open Executive Overview.** Show region cards, point at AMER's lower AVRI and at-risk renewal count.
2. **Switch to At-Risk Renewals.** Headline: "$X.XM in revenue is renewing in 90 days and AVRI flags it."
3. **Click into Account Drill-down → ACC-00202** (use the quick picker). Show: $3.5M Financial Services, AVRI=19.5 Red, naive CHS=40 Yellow. Time series shows complete shelfware.
4. **Switch to ACC-00226** (the floor rule example). All consumption pillars at 100, but TH=15, floor rule fires, AVRI capped at 50.
5. **Switch to ACC-00876** (overage rewarded). All pillars high, latest_color=red, naive CHS knocks it down, AVRI correctly rewards.

## Caching

All BigQuery queries are cached for 10 minutes (`@st.cache_data(ttl=600)`). Re-running the dashboard within that window won't re-hit BigQuery.
