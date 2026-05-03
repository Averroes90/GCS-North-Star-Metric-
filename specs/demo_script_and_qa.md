# Demo Script + Q&A Prep: Live Presentation

**For the night before / morning of the interview.** Print this, mark it up, rehearse against it.

**Format reminder:** 60 minutes total = ~35 min presenting (intro 5 + context 5 + tech deep dive 15 + eval 10) + 25 min Q&A.

## Brief topic coverage map

The brief lists 5 PM topics to cover. Here's where each lives in the deck, make sure to hit them explicitly while presenting (don't assume the audience will infer):

| Brief topic | Where in deck | Cue word to say |
|---|---|---|
| **Data Strategy** | Slide 6 retrospective (LEFT column "what worked"); also implicit in Slide 5 "inductive validation" preamble | *"Spec-driven AI build"*, *"data was generated to be realistic"* |
| **System Design & Trade-offs** | Slide 4 (composite vs single, rules vs ML); Slide 3 footnote on Build vs Buy | *"Composite over single metric…"*, *"Build vs Buy — Gainsight as alternative…"* |
| **Human in the Loop** | Slide 5 left-bottom strip | *"Human-in-the-loop layer — AVRI scores, dashboard surfaces, CSM acts"* |
| **Evaluation & Success** | Slide 5 right-bottom strip + Slide 3 distribution comparison | *"Three success criteria — predictive accuracy, surprise-renewal reduction, expansion conversion"* |
| **Retrospective** | Slide 6 (entire slide) | *"What I learned, what v2 looks like, how to ship it"* |

If the panel asks "you didn't cover X" mid-presentation, use these cue words to point at where it actually lives.

---

## 1. Pre-flight (30 minutes before)

| ✓ | Action |
|---|---|
| ☐ | Open `AVRI_Deck.pptx` in presenter mode (or PDF if PowerPoint isn't installed). |
| ☐ | Open second browser tab: `metrics-explorer.html` — quick reference if a Q&A goes deep. |
| ☐ | Open terminal: `cd dashboard && streamlit run app.py`. Wait for browser to open at localhost:8501. |
| ☐ | In Streamlit: confirm Executive Overview loads cleanly (region cards, distribution bars). |
| ☐ | In Streamlit: open Account Drill-down → click "ACC-00202 (Shelfware)" in the deck-story picker. Confirm time series renders. |
| ☐ | In Streamlit: click At-Risk Renewals tab. Note the **headline `$X.XM at risk`** number — use this exact figure on slide 5. |
| ☐ | Close all unrelated tabs. Set browser to half-screen so you can switch between deck and dashboard cleanly. |
| ☐ | Have water nearby. Phone on silent. Mic test if remote. |

**If anything fails:** the dashboard is a nice-to-have, not the centerpiece. The deck stands alone. Don't panic, say "let me skip the live demo and walk you through it on the slide" and use slide 5's table.

---

## 2. Slide-by-slide script (35 min target)

### Slide 1: Cover + Philosophy (4 min)

**What to say (don't read the slide):**

> "I'm Rami Ibrahimi. Quick background: [30 seconds, your prior PM roles, especially anything technical or analytics-adjacent]."
>
> "My take on Technical PM in one line, it's a translation function. Between the business outcome someone wants, the data reality of what's actually happening, and the software that ships at the end."
>
> "For this case study, I built end to end, synthetic dataset, BigQuery pipeline, Streamlit dashboard, this deck, using Cursor and Claude Code with markdown specs at every step. Today I'll show what I built and the choices behind it. I want to leave 25 minutes for Q&A."

**Don't:** spend more than 4 minutes here. Resist the urge to backstory.

**Cue to advance:** when you've stated the 25-min Q&A target.

---

### Slide 2: The Problem (5 min)

**Talking points:**

- *"GCS is moving from selling deals to sustaining value. The shift from TCV-based comp to ARR + consumption hybrid is the structural problem driving this."*
- Point at the LEFT card: "Old world, book the deal, bank the credit. ONE moment, ONE signal, ONE incentive. Blind to everything that happens after signing."
- Point at the RIGHT card: "New world, value has to be realized. Compensation has to follow. Four very different things have to be balanced." Name each chip: Bookings, Deployment, Tech Health, Sustained Usage.
- Bottom callout: *"That's the business question I'm answering, what's the health of an account at a point in time, balancing all four, in a single defensible number?"*

**Don't:** explain what TCV or ARR mean unless asked. The audience knows.

**Cue to advance:** after stating the business question.

---

### Slide 3: Why No Existing Metric Works (6 min)

**Talking points:**

- "I scored 30+ industry-standard SaaS/CS metrics against the four dimensions. Here's the abridged version."
- Walk the table FAST, 3 seconds per row: *"TCV, bookings only, blind to the rest. ARR, same. NRR, better, partial usage signal but lagging. Raw utilization, usage and partial deployment but no commercial. Latest health color, only tech health. Gainsight CHS, closest pattern, composite, covers tech and usage well, partial on bookings and deployment."*
- Pause at the AVRI row: "Mine is the only one that covers all four."
- Point right: "On 766 in-scope accounts, AVRI is more conservative than the naive CHS, surfaces more risk in red. AND it's more lenient on the right things, overage accounts that naive CHS treats as broken, AVRI rewards as expansion candidates."
- The deck punchline (yellow callout): *"AVRI surfaces more risk than naive CHS, AND is more lenient on the right things."*
- **Build vs Buy explicit mention** (footnote on slide): *"On build vs buy, Gainsight CHS is the closest commercial alternative. Same composite pattern. The reason I'm building rather than buying is that none of the standard CHS configurations natively handle the consumption-hybrid model, commit-vs-consume, momentum, edge cases like shelfware. So either I extend Gainsight to do this, or I build it natively. I built it natively because the structural changes are non-trivial, and the metric is the central artifact, not infrastructure I want to outsource."*

**Don't:** get into individual metric definitions. The table is the reference; let it do the work.

**Cue to advance:** after the Build-vs-Buy mention.

---

### Slide 4: AVRI Proposal (8 min: the technical core)

**Talking points:**

- "Four pillars, mapped 1:1 to the four required dimensions. Weights 30/30/20/20."
- Walk each pillar in 60 seconds:
  - **CR**, *"Are they using what they paid for? 90-day consumption divided by 90-day commit. Piecewise, penalize under 50%, plateau between 50 and 110%, and over 150% gentle decay because it's a capacity warning, not a failure."*
  - **UM**, *"Is consumption holding up? 90-day average over 12-month baseline. This is what catches spike-and-drop. Has a level guard, if total annual usage is less than 5% of commit, UM forces to zero so shelfware doesn't accidentally score high."*
  - **DM**, *"Is the product genuinely operationalized? Active days in the last 90 over 90. In v0 this is a proxy. In production we'd add license provisioning, feature breadth, onboarding milestones."*
  - **TH**, *"Does it work for them? Exponentially-decayed health color, half-life of about two weeks. In production, replace the color with Sev-1 frequency, SLA attainment, escalation count."*
- Point at the formula bar: *"Weighted linear average of the four."*
- Point at the floor rule callout: *"This is the cleverest bit. Linear weighted averages are substitutable, high CR can mathematically offset low TH. In reality, a customer with a critical platform crisis won't renew regardless of consumption. The floor rule expresses non-substitutability, if TH is below 30, AVRI can't exceed 50, period."*
- Point at the RAG bands at the bottom: *"Green at 75 means every pillar is contributing positively. Red below 50 is a real renewal risk, escalate immediately."*

**Don't:** dive into the exact piecewise math unless asked. The detail is in the pillar cards.

**Cue to advance:** after the RAG bands.

---

### Slide 5: Proof + Live Demo (8 min)

**Slides portion (~3 min):**

- "Inductive validation. The data was generated to be realistic, not to flatter the metric. Here are three real account stories."
- Point at SHELFWARE card: *"ACC-00202, Financial Services account, 3.5 million ARR, zero active days in 90. The latest health color happens to still be green from earlier in the year, which is why naive CHS gives it 40, yellow-ish, marginal action. AVRI sees through it. Score: 19.5. Deep red. The exact account a CSM should be on the phone with."*
- Point at FLOOR RULE card: *"ACC-00226, 8 million dollar Tech account. Consumption pillars all 100. Looks great. But TH is 15, they have a critical technical issue. Without the floor rule, AVRI computes to 86, Green. The floor rule kicks in, caps it at 50, Yellow. The metric refuses to let consumption paper over a tech crisis."*
- Point at REWARDED card: *"ACC-00876, Manufacturing, 246K ARR. All consumption pillars high, but the latest health color happened to be red after one bad week. Naive CHS over-penalizes, gives it 57 yellow. AVRI's decay-weighted TH gets the trend right, 92, Green. AVRI rewards what naive CHS unfairly flags."*

**SWITCH TO DASHBOARD (~4 min):**

1. **Start on At-Risk Renewals tab.** Point at the headline: *"$10.3M at risk. 20 accounts. Top one, 3.6 million Tech account, 72 days to renewal, AVRI=12. No existing metric flags this with that urgency on that timeline."*
2. **Switch to Account Drill-down.** Use the deck-story quick picker → **ACC-00202**.
   - Point at pillar breakdown: *"All four pillars at zero. Composite at 19. The decayed health color carries the score from 0 to 19, that's why."*
   - Point at the time series: *"Look at the daily consumption chart. Pure flat zero. This isn't a spike-and-drop. It's pure shelfware. Existing metrics don't see this; AVRI does."*
3. **Quick aside:** *"If I had time, I'd also walk you through ACC-00226 in the same view to show how the floor rule renders. Happy to come back to it in Q&A."*
4. **Switch back to deck.**

**Then call out the two strips at the bottom of slide 5 explicitly (~1 min):**

- Point at the **HUMAN IN THE LOOP** strip: *"This is the human-in-the-loop layer. AVRI is the score; the dashboard is the surface; the CSM is the actor. The metric directs the human, it doesn't replace them. That's an intentional design choice, composites should augment CS judgment, not automate it away."*
- Point at the **SUCCESS CRITERIA** strip: *"And here's how I'd evaluate whether AVRI is actually working, three business KPIs. First, predictive accuracy: what percentage of accounts AVRI flags Red actually churn within 90 days? Second, reduction in 'Green-to-Lost' surprise renewals, accounts that looked fine and were lost anyway. Third, expansion conversion in the 110-150% utilization band, accounts AVRI marks as expansion candidates that actually convert. Day-30 milestone is to validate AVRI against historical renewal outcomes via regression."*

**Don't:** linger in the dashboard. 4 minutes max for live demo, then return to the deck and explicitly cover the two bottom strips. The story is on the slide; the dashboard is the proof; the strips close out the brief's required topics.

**Cue to advance:** when you've explicitly walked the SUCCESS CRITERIA strip.

---

### Slide 6: Retrospective + Roadmap (4 min)

**Talking points:**

- "Three things to leave you with."
- LEFT column (60 sec): *"Spec-driven AI worked. The codebase is about 3000 lines, generated from markdown specs in roughly 8 hours of focused work. Lessons captured in lessons_learned.md, 13 entries so far. Next time I'd build CI from day one, would have caught the UM zero-baseline bug 2 hours earlier."*
- MIDDLE column (60 sec): *"v2 with newer tech: agentic data quality, LLM-summarized account briefs, tenure-aware cold-start handling, per-segment weight tuning, real signal in DM and TH instead of proxies."*
- RIGHT column (60 sec): *"30-60-90 day rollout. Validate against historical renewal outcomes first. Integrate ticket data and license provisioning. Then roll into CSM compensation as a 25% factor at day 90."*
- Final beat (orange callout): *"This is a real product. The repo is reproducible end-to-end. Anyone on your team can clone it and have AVRI scoring real data on day one."*
- Pause. *"Happy to take questions."*

**Cue to advance:** stop talking, take questions.

---

## 3. Anticipated Q&A: 12 most likely questions

For each: the question, a 30-second answer, the "if they push" deeper response, and the reference for after the interview.

### Q1. "Why those weights: 30/30/20/20?"

**Answer:** "Heuristic in v1. CR and UM tied at the top because consumption level and trajectory each tell half the story, without UM, spike-and-drop is invisible. DM and TH at 20 each because in v0 they're running on proxies, not the rich signal we'd have in production."

**If pushed:** "Production calibration is to regress component scores against historical renewal outcomes, weight by correlation strength. We can run that experiment on day 30."

**Reference:** Defending Choices tab → entries `w-cr`, `w-um`, `w-dm`, `w-th`.

---

### Q2. "Why a composite at all? Why not just use the strongest single metric?"

**Answer:** "The brief explicitly asks the metric to balance four dimensions. No single raw metric covers more than two. A composite is the only honest answer to that requirement."

**If pushed:** "Single metrics also create perverse incentives, a comp plan tied to utilization gets you over-consumption gaming. A composite with offsetting components is much harder to game."

**Reference:** Metrics Explorer tab, every standalone metric scored against the four dimensions.

---

### Q3. "Why not use ML to predict churn directly? Skip the rules?"

**Answer:** "Two reasons. First, explainability, when a CSM's compensation is on the line, a black-box probability that says 'this account is 40% likely to churn' will get rejected. Reps need to know why. Rules-based scoring tells them which pillar to act on. Second, ML works best when you have years of labeled outcomes. We don't yet."

**If pushed:** "v2 is exactly this, once we have a year of AVRI scores plus actual renewal outcomes, layer a churn-prediction model on top. AVRI becomes a feature, not the answer."

---

### Q4. "How does the floor rule not over-trigger? What if a customer has one bad week?"

**Answer:** "The TH score is a 90-day exponentially-decayed weighted average of health color. One bad week doesn't pull it under 30, you need sustained issues over weeks. Empirically, the rule fires on about 2-3% of accounts in our sample, and every one of them had multiple consecutive red weeks."

**If pushed:** "The threshold is tunable. 30 is heuristic. Production tuning would set it at the TH score below which 90-day churn probability exceeds 40%."

**Reference:** Defending Choices tab → entries `f-trigger`, `f-cap`.

---

### Q5. "What if a CSM games the metric to inflate their score?"

**Answer:** "The composite makes individual gaming hard. To game CR, you'd push the customer to over-consume, but that hits the 150% threshold and starts to decay. To game UM, you'd need consistent usage, but that's what we want anyway. The most gameable component would be TH, which is why the floor rule is a hard cap, not a weighted contribution."

**If pushed:** "Manual inputs are the gaming surface. We've kept the metric machine-measurable end to end, no CSM-rated colors, no CSM-input fields. Compare to Gainsight CHS, which often includes CSM-pulse fields that become gaming vectors."

---

### Q6. "Why not just use Gainsight CHS? It's the industry standard."

**Answer:** "Gainsight CHS is the right pattern, composite, weighted, RAG. AVRI is essentially a Gainsight CHS specialized for PANW's consumption-hybrid model. The differentiators: native commit-vs-consume, momentum (trajectory) as a first-class component, edge-case handling for shelfware and overage, and a floor rule for non-substitutability."

**If pushed:** "Standard Gainsight CHS configurations don't natively penalize shelfware specifically, the financial component looks at ARR, not at usage relative to commit. They also don't include trajectory, so spike-and-drop is invisible."

---

### Q7. "What about brand new accounts? Cold start?"

**Answer:** "Known gap, documented in lessons_learned. The level guard on UM correctly zeroes momentum for accounts that haven't accumulated usage, but it incidentally penalizes accounts that just haven't had time to ramp. v2 fix is a tenure-aware Onboarding RAG state separate from the existing G/Y/R buckets."

**Reference:** lessons_learned.md entry #11.

---

### Q8. "How did you decide what data to generate? Did you tune it to make AVRI look good?"

**Answer:** "Deliberately did the opposite. I built the data first based on industry-realistic patterns, long-tail account sizes, weekly seasonality, the 5 brief-specified anomalies, without anchoring to what would make my metric score well. Then I computed every existing metric on it AND AVRI. The inspection report compares them. Where AVRI wins or loses, that's the data telling the truth, not me cooking it."

**If pushed:** "The risk in the deductive approach, design metric, then build data to validate, is circular. The inductive approach removes that risk. I've documented the methodology choice in lessons_learned.md as the first entry."

---

### Q9. "Walk me through the architecture."

**Answer:** "Five layers, decoupled. Python data generator produces Parquet files locally. Loader script uploads to BigQuery. SQL pipeline runs as templated CREATE OR REPLACE TABLE statements, 4 output tables. Inspection and dashboard read those output tables. Each layer has a contract with the next; you can swap the generator for a real production data feed without touching anything downstream."

**Reference:** "How It Connects" tab in metrics-explorer.html.

---

### Q10. "How would you operationalize this?"

**Answer:** "Three phases. Day 30, validate AVRI against historical renewal outcomes, calibrate weights via regression. Day 60, integrate ticket data and license provisioning, replace proxy signals in DM and TH. Day 90, roll into CSM compensation as a 25% factor alongside book ARR retention. Day 180, productionize the dashboard. Day 365, re-tune."

---

### Q11. "What was the hardest decision in the design?"

**Answer:** "The piecewise CR curve, specifically the over-150% behavior. The default instinct is to penalize over-consumption, looks like a customer in distress. But after looking at real consumption-model data, over-consumption is more often a positive signal, they're getting more value than they bought. So I made it a gentle decay, with a separate 'capacity expansion candidate' flag rather than a score penalty. This is the choice most likely to get pushback, and the one I'd defend most strongly."

---

### Q12. "If you redid this with newer tools today, what would change?"

**Answer:** "Three things. First, an agentic data quality monitor, agent watches the pipeline, surfaces anomalies in Slack autonomously, instead of me running inspection.py manually. Second, LLM-summarized account briefs, for each at-risk account, generate a CSM-ready talking points doc from the consumption and ticket history. Third, tenure-aware cold-start, separate Onboarding RAG state instead of forcing new accounts into Green/Yellow/Red buckets."

---

## 4. Tactical advice

**If you don't know an answer:**
> *"I haven't tested that specifically. My instinct is X. The way I'd validate is Y."* (Then move on.)

**If they push hard on a weight or threshold:**
Bring the conversation back to *"Weights are the easiest thing to tune; the structure is what matters. Production calibration would set them empirically. Defending intuition is the honest answer for v0."*

**If they question the inductive workflow:**
*"I made this choice deliberately to avoid circularity. The data was built to look like the world; the existing metrics were computed first; AVRI's gaps were derived from where the existing metrics fail."*

**If they ask about a competitor (Gainsight, Totango, ChurnZero):**
Acknowledge the category, then differentiate on consumption-hybrid model handling. Don't trash competitors.

**If they push on cost or scale:**
*"$0/month in BigQuery Sandbox for the case study. Production scales linearly with data volume, at PANW's scale, BQ costs would be in the low thousands per month, fully offset by even one prevented churn event."*

**If they ask "what would you do if you had another week":**
1. Per-segment weight tuning (Enterprise vs Mid-Market)
2. Validate AVRI against historical renewal outcomes (regression)
3. Add ticket data integration
4. Add the cold-start Onboarding state
Then: *"But the case study scope was a working prototype, and that's what I delivered."*

**Body language reminders:**
- Smile when explaining the floor rule. It's clever; show that you think so.
- Pause after the punchline on slide 3. Let them absorb.
- Direct eye contact with the VP on the philosophy slide.
- When switching to the dashboard, narrate what you're doing ("opening Streamlit now").

---

## 5. Backup ammunition

If a question goes deep into technical territory and you want to give a thorough answer, these are your reference materials available in the live HTML lobby:

- **Defending Choices tab**, every numeric value in the metric, with the rationale and "if pushed" line
- **Edge Cases tab**, how the brief's 5 anomalies are handled
- **Schema → Metric tab**, visual of how columns flow into pillars
- **Lessons Learned** (specs/lessons_learned.md), 13 documented pitfalls

If asked something you can't answer in the moment but want to follow up:
> *"Let me get back to you on that, I want to give you a precise answer, not a guess."*
> Then: write it down, follow up by email within 24 hours.

---

## 6. Final 5-minute pre-talk ritual

1. Re-read your tagline aloud once.
2. Pull up slide 5 and look at the three account stories. Make sure you can name them from memory.
3. Open the dashboard. Click ACC-00202 in the deck-story picker. Look at the time series for 10 seconds, burn the visual into your head.
4. Take three deep breaths.
5. Smile and start.

Good luck.
