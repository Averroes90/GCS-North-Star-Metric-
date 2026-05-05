# Deck Outline: Executive Presentation

**Audience:** VP of Customer Success + Solutions Consultant (front row); analytics/AI panel for Q&A.
**Length:** 6 content slides + cover. Target ~35 minutes presented + 25 minutes Q&A.
**Format:** PowerPoint (.pptx); demo Streamlit live during slide 5.
**Purpose:** Win the role. The case study is the candidate; this deck is how the case is sold.

---

## Slide map (v2.0 — 8 slides)

| # | Title | Time | What it does |
|---|---|---|---|
| 1 | Cover + Technical PM philosophy | 3 min | Frames who I am and how I approach the problem |
| 2 | The problem GCS is trying to solve | 4 min | TCV → ARR + consumption hybrid; the 4 dimensions |
| 3 | Why no existing metric works | 5 min | Metrics zoo; AVRI × CHS crosstab; the gap |
| 4 | AVRI — quality of execution | 6 min | 4 pillars, weights, RAG, floor rule |
| **5** | **Quality × Scale = Realized Value** | **5 min** | **NEW: linear RV, decomposition, $202M of $311M realized headline** |
| 6 | Proof — three disagreements | 6 min | 3 case cards (now with RV/unrealized $ line); transition to demo |
| 7 | Retrospective + v3 roadmap | 4 min | Spec-driven AI; v2 what shipped; v3 calibration |
| 8 (appx) | Edge case handling matrix | Q&A | Brief's 5 edge cases × AVRI mechanism (defense backup) |

Total: ~33 minutes spoken, leaving Q&A room.

---

## Slide 1: Cover + Technical PM Philosophy

**Visual:** Clean title slide. Name, role, date. One-line tagline.

**Tagline candidate:** *"PM is a translation function, between business intent, data reality, and shippable software."*

**Speaker notes (~4 min):**
- Name + brief background (1–2 sentences). Tailor to your actual background.
- "Technical PM philosophy" is what they want here per the brief. My take:
  1. **Specs before code, always.** Even when AI writes the code. The spec is what survives the AI.
  2. **Data first, then opinions.** Build the data the way the world looks; let the metrics fail before I propose new ones.
  3. **Ship the dashboard, not the deck.** The dashboard is the actual product; the deck is the wrapper.
- Acknowledge: "I built this entire project, data generator, BigQuery pipeline, dashboard, using Cursor + Claude Code with markdown specs. Today I'll show what I built and the choices behind it."

---

## Slide 2: The Problem GCS Is Trying to Solve

**Visual:** Two-column comparison.
- LEFT: "Old world (TCV)", single arrow, "rep books deal, walks away"
- RIGHT: "New world (ARR + consumption)", four-dimension diagram (Bookings, Deployment, Tech Health, Sustained Usage)
- Centered call-out below: *"We need ONE metric that balances all four."*

**Speaker notes (~5 min):**
- The structural shift: GCS moving from booking-once compensation to ongoing value realization. TCV no longer captures success.
- The four dimensions the new metric must balance, pulled directly from the brief:
  1. **Initial bookings**, they signed something
  2. **Full deployment**, they actually stood it up
  3. **Technical health**, it works for them
  4. **Sustained platform usage**, they keep using it
- The friction this creates for leadership:
  - How do we compensate reps fairly?
  - What does "good" look like across these four?
  - Which accounts are at risk *right now*, not at renewal?
- The specific business question I'm answering: **"What's the health of an account at a point in time, balancing all four dimensions, in a single defensible number?"**
- Set expectation: "I'll show you the metric I propose and how it handles the messy realities, overage, shelfware, mid-year expansion, technical crises."

---

## Slide 3: Why No Existing Metric Works

**Visual:** Two halves.
- LEFT: a small table, 6 standard metrics (TCV, ARR, NRR, Utilization, Gainsight CHS, Health Color), each scored ✓/◐/○ on the four dimensions. Pulled from the Metrics Explorer table.
- RIGHT: A horizontal stacked bar comparison, naive CHS distribution vs AVRI distribution on the same 766 accounts. AVRI shows more red.

**Speaker notes (~6 min):**
- Walk the table fast. Three-second-per-row. Punchline: every single existing metric is blind to ≥ 1 of the 4 dimensions.
- Three callouts:
  - **TCV/ARR are commercial-only.** They tell you the customer is paying. They don't tell you the customer is using.
  - **Utilization is snapshot-only.** A spike-and-drop account at year-end shows 100% annual utilization while having zero usage for 11 months. The metric is fine; the reality isn't.
  - **Gainsight-style CHS is the closest match**, it's a composite, which is the right pattern. But in its standard configurations it doesn't natively handle commit-vs-consume, doesn't penalize shelfware specifically, and doesn't include trajectory.
- Show the distribution comparison: AVRI surfaces ~22% red vs naive CHS's 19%. The 64 accounts in AVRI's yellow band that *would* be naive CHS green are the most operationally important, these are the accounts no current dashboard is flagging for the CSM.
- Frame the design constraint: "I'm not reinventing customer health scoring. I'm building the version that PANW's specific consumption-hybrid model needs."

---

## Slide 4: AVRI: The Proposal

**Visual:** Four pillar cards in a 2×2 grid, each color-coded:
- **Commit Realization (30%)**, blue, "Are they using what they paid for?"
- **Usage Momentum (30%)**, orange, "Is consumption holding up?"
- **Deployment Maturity (20%)**, purple, "Is it operationalized?"
- **Technical Health (20%)**, green, "Does it work for them?"
- Below, the formula: `AVRI = 0.3·CR + 0.3·UM + 0.2·DM + 0.2·TH`
- Then a distinct callout: `IF TH < 30: AVRI = min(AVRI, 50)`, *"the floor rule"*
- RAG bands across the bottom: Green ≥ 75 / Yellow 50–74 / Red < 50

**Speaker notes (~8 min):**
- The four-pillar structure is intentional, it maps 1:1 to the four dimensions the brief required us to balance.
- Walk each pillar in 30 seconds:
  - **CR**, piecewise score. Sweet spot 50–110%. Above 150% gentle penalty (capacity warning, not failure). Overage is good.
  - **UM**, ratio of last-90 to last-365 daily averages. Catches spike-and-drop, which CR alone misses.
  - **DM**, active-day breadth. In production this would also include license provisioning and feature adoption.
  - **TH**, exponentially decayed health color. Recent matters more.
- The two design moves I'd push back on most strongly in the panel:
  - **Why composite over single metric:** brief explicitly says "balance four dimensions." Single raw metrics can't.
  - **Why floor rule:** linear weighted averages are *substitutable*, high CR can mathematically offset low TH. In reality, a customer with a critical platform crisis won't renew regardless of consumption. The floor rule expresses non-substitutability, which a pure linear average cannot.
- Acknowledge what's NOT in v0/v1:
  - No predictive ML, explainability matters for comp plans; black-box churn predictors get rejected by reps
  - No per-segment weight tuning yet
  - Cold-start handling is a known gap (documented in lessons_learned)
- Anchor the weight defense: "These weights are heuristic in v0/v1. Production calibration is to regress component scores against historical renewal outcomes, but for the case study, defending intuition is the honest answer."

---

## Slide 5 (NEW): Quality × Scale = Realized Value

**Visual:** Two halves.
- LEFT: the linear formula `RV = ARR × (AVRI / 100)` displayed prominently. Brief callout: *"Decomposable. Defensible. Calibratable."*
- RIGHT: stacked-bar headline showing total ARR split into Realized (green) + Unrealized (red). Numbers from `pillar_decomposition_snapshot.json`.
- BOTTOM: mini pillar-decomposition heatmap (3 regions × 4 pillars + floor) — the same chart from the dashboard's Realized Value tab.

**Speaker notes (~5 min):**
- "AVRI is our quality signal. But the brief asked us to balance four dimensions including bookings — and a quality-only score treats a $25M book at 80% identically to a $1M book at 80%. That's wrong for executive triage even if it's right for CSM evaluation."
- Define RV: *"RV = ARR × AVRI/100. Linear. Each account contributes its ARR weighted by how much it's realizing. Onboarding accounts contribute zero; signing never penalizes the CSM."*
- Walk through what RV gives us:
  - **Headline: $X realized of $Y total ARR.** Single executive number; one-sentence answer to "where are we leaking?"
  - **Pillar decomposition.** Unrealized $ splits cleanly across CR/UM/DM/TH/floor. The heatmap *is* the metric, not an approximation.
  - **Aggregation.** Sum at any level — region, segment, CSM, account — and the numbers reconcile to their parent.
- Address the "why linear?" question proactively: *"We considered quadratic and sigmoidal. Linear wins on three counts: it factors cleanly across pillars and aggregates, it doesn't pretend to know a curvature we can't justify without renewal data, and it's the conservative starting point — v3 calibration replaces it from real outcomes."*
- The thesis: *"AVRI is velocity. RV is momentum. Both belong on the dashboard, neither replaces the other."*

---

## Slide 6 (was 5): Proof — three disagreements

**Visual:** Three case-card columns. Same accounts as before; now each card carries an additional RV/unrealized $ line.

| Tag | Account | ARR | CHS | AVRI | RV / Unrealized | Why AVRI is right |
|---|---|---|---|---|---|---|
| FLOOR RULE | ACC-00026 (Healthcare) | $165K | 78 (G) | **50 (Y)** | $83K / $83K | TH=28.5; floor rule caps AVRI at 50. CHS has no analog. |
| DECAY | ACC-00876 (Mfg) | $246K | 57 (Y) | **92 (G)** | $227K / $19K | One-bad-week red color fooled CHS. AVRI's 90d decay TH gets the trend. |
| ESCALATE | ACC-00298 (FS) | $325K | 57 (Y) | **24 (R)** | $77K / $248K | Three pillars in collapse. CHS hedges; AVRI escalates. |

**Speaker notes (~6 min):**
- "Three accounts. Same data. Three different shapes of disagreement with naive CHS — each validates a specific AVRI design choice."
- Walk each card in 1.5 min. Reference the RV/unrealized $ explicitly: *"$248K of unrealized value in this one account — the largest single-account contribution to the renewal landmine pile we just looked at."*
- Then **switch to the Streamlit dashboard** and demo:
  - **Realized Value tab**, headline + heatmap. *"This is the executive dashboard. $X realized of $Y. EMEA's TH column tells me where to look."*
  - **At-Risk Renewals tab**, *"15 accounts renewing in 90 days; sortable by unrealized $. Top of the list is the renewal landmine."*
  - **Account Drill-down → ACC-00026** (FLOOR RULE example). *"This is where the floor rule lives — accounts naive CHS would not flag because consumption looks great, but TH crashed."* (The crosstab story is on slide 3 + the lobby's "AVRI vs CHS Stories" tab; the dashboard no longer has a dedicated AVRI vs CHS tab.)
  - Optionally: **Calibration tab.** *"Every parameter in the metric is here. Production is locked; this is the transparency artifact."*
- Close: *"This is the working tool. Three clicks from question to actionable list."*

---

## Slide 7 (was 6): Retrospective + Roadmap

**Visual:** Three columns.
- LEFT: "What I'd do differently" (lessons learned)
- MIDDLE: "v2 with today's stack" (agentic / LLM-enabled)
- RIGHT: "30/60/90 day rollout" (operational)

**Speaker notes (~4 min):**
- Spec-driven AI methodology worked. The codebase is ~3,000 lines of Python + SQL, all generated from markdown specs in roughly 8 hours of focused work. No way that's possible without AI co-pilots.
- What I'd change next time:
  - Build the data spec and metric spec in parallel from day one (not sequentially)
  - Set up CI from day one, the inspection script would have caught the UM zero-baseline bug earlier if I'd had it running on every pipeline change
  - Use a different LLM for code review than for code generation (separate the criticism from the construction)
- v2 with newer tech:
  - **Agentic data quality**, instead of running inspection.py manually, an agent that watches the pipeline and surfaces anomalies in Slack
  - **LLM-summarized account briefs**, for each at-risk account, generate a CSM-ready talking points doc from the consumption + ticket history
  - **Tenure-aware cold-start handling**, separate "Onboarding" RAG state instead of forcing accounts into the existing G/Y/R buckets
- Operational roadmap:
  - **Day 30:** validate AVRI against historical renewal data; tune weights
  - **Day 60:** integrate ticket data + license provisioning; replace proxies in DM and TH
  - **Day 90:** roll into CSM compensation as a 25% factor (alongside book ARR)
- Final beat: "This is a real product, not a deck artifact. The repo is reproducible end to end. Anyone on your team can clone, run, and have AVRI scoring real data on day one."

---

## Backup slides (optional, for Q&A)

Don't put these in the main flow but keep at end of deck for Q&A:

- **B1: Edge case handling matrix**, the 5 brief-specified anomalies × how AVRI handles each
- **B2: Defending the numbers**, top 5 most-likely-challenged numeric choices with the scripted defense
- **B3: Architecture diagram**, the "How It Connects" visual from the HTML lobby
- **B4: Lessons learned summary**, bulletpoint of the 13 entries from `lessons_learned.md`

---

## Anticipated Q&A topics (for prep)

The brief explicitly says "be ready to defend your technical trade-offs and product roadmap decisions." Most likely:

1. **"Why those weights?"**, see Defending Choices tab. Defense: heuristic v1, calibrated v2.
2. **"Why a composite vs single metric?"**, brief says balance 4 dimensions; no single metric does.
3. **"What about ML / black-box predictions?"**, explainability matters for comp; rejected by reps.
4. **"How does the floor rule not over-trigger?"**, TH<30 is "mostly red over 90 days," verified against the actual data.
5. **"What if a CSM games the metric?"**, composite + machine-measured signals + level guards make individual gaming hard.
6. **"How would this change in 2 years?"**, see slide 6 roadmap.
7. **"Why not just use Gainsight?"**, best in class for general CS, doesn't natively handle commit-vs-consume or trajectory.

Cross-reference each to the Defending Choices tab + lessons_learned.md.
