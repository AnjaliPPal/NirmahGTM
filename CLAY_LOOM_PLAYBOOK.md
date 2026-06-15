# SignalOS + Clay — Loom Playbook
**Last updated: June 4, 2026**

Reusable process for every job application. Build the table once, duplicate per company.
First run: ~2.5 hours. Each duplicate after: ~1 hour 20 min.

---

## Phase 2 — Public URL (10 min)

Keep three terminals open until the Loom is uploaded.

### Step 1 — Start everything

**Terminal 1 — API:**
```bash
cd D:\GTMSignolos\signalos-v1
uvicorn api.main:app --reload --port 8000
```
Wait for `Application startup complete`.

**Terminal 2 — ngrok tunnel:**
```bash
ngrok http 8000
```
Wait until you see:
```
Forwarding    https://RANDOM-STRING.ngrok-free.app -> http://localhost:8000
```
**Copy that URL.** You will paste it into Clay in Phase 3 Step 4.

> ngrok free plan gives a new random URL every restart. Each time you restart ngrok, update the URL in Clay's HTTP column config.

**Terminal 3 — verify it works (replace URL with yours):**
```bash
curl -X POST https://YOUR-NGROK-URL.ngrok-free.app/score-company ^
  -H "Content-Type: application/json" ^
  -d "{\"company_name\":\"Acme\",\"domain\":\"acme.com\",\"client_id\":\"demo\",\"scoring_context\":\"B2B SaaS hiring GTM roles\"}"
```
Must return JSON with a `score` field. If not, read Terminal 1 before continuing.

---

## Phase 3 — Clay Table (90 min first time, 20 min per duplicate)

Do these steps in exact order.

### Step 1 — Create the table

clay.com → New Table → name it after the company you're applying to.
Example: `weflow-ai-prospects`

---

### Step 2 — Find companies (the most important step)

Source: [Clay Ocean.io integration docs](https://university.clay.com/docs/ocean-io-integration-overview) — verified June 2, 2026.

---

**Step 2a — Find your seed domains**

**Why this matters:** Your seed domains are your ICP anchor. Every lookalike Ocean.io finds will be based on these 2–3 real customers. Seed wrong = lookalike wrong. **Never guess. Always use confirmed customer data.**

**Time: 15–20 minutes for 3 seeds.**

#### Method 1 (Highest Signal): Public Customer Page
1. Go to `hiring-company.com/customers` (or `/case-studies`, `/success-stories`, `/clients`)
2. Find 2–3 company logos with names
3. Copy domains (right-click logo → Google the company name if domain not visible)
4. Validate: `curl -I https://domain` → should return HTTP 200–399

**Example (brand.ai, Jun 2026):** brand.ai/customers shows Lyft | Turo | Groq logos → seeds: lyft.com | turo.com | groq.com. **Time: 3–5 min. Confidence: 100%.**

#### Method 2 (Medium Signal): LinkedIn Company Page
1. Go to LinkedIn company page → search "company name case study" or "company name customers"
2. Look for founder posts mentioning customer wins (last 6–12 months)
3. Extract company names mentioned in posts or comments
4. Validate each domain

**Example (Instantly.ai, Jun 2026):** CEO post "500+ GTM teams use Instantly" → comments mention Braze, UserTesting → seeds: braze.com | usertesting.com. **Time: 5–10 min. Confidence: 85%.**

#### Method 3 (Fallback): G2 Reviews
1. Go to g2.com/products/[company-name]
2. Scroll to "Customer reviews" → look for "John Doe, Title at Company Name"
3. Click company name link → copy domain from G2 profile

**Time: 8–15 min. Hit rate: ~40%.**

#### Method 4 (Confirming Only): Press Releases
1. Go to `hiring-company.com/press` or `/newsroom`
2. Search: "customer," "partner," "announces," "now customer"
3. Open release → extract company name + verify domain

**Time: 10–20 min. Use only as confirming evidence.**

#### Method 5 (Last Resort): Google News
1. Go to news.google.com
2. Search: `"[company name]" customer OR partner OR client [year]`
3. Read headlines for "X Company now uses Y"
4. Click → extract company name + domain

**Time: 10–15 min.**

---

#### The 3-Seed Rule
- **Best case:** 3 confirmed customers from Method 1 (customer page) → 100% confidence
- **Good case:** 2 from Method 1 + 1 from Method 2 (LinkedIn) → 95% confidence
- **Acceptable:** 3 from any mix of Methods 2–4 → 80% confidence
- **Avoid:** Seeds older than 12 months (product changed, customers churned)

#### Validation Checklist
- [ ] Domain resolves (HTTP 200–399)
- [ ] Company still exists (active on LinkedIn, not acquired/shutdown)
- [ ] Customer announcement dated within last 12 months
- [ ] Company size matches YOUR ICP (don't seed Fortune 500 if targeting Series B)
- [ ] At least 2 seeds from same source (credibility signal)

---

**What Sr GTM Practitioners Say (Jun 2026):**
> "Your seed domains are your hypothesis about your ICP. If you guess, Ocean.io finds 50 companies that look like your guess, not like your real customers. I always spend 15 minutes finding real seeds. It saves 3 hours of bad outreach later." — Ritu Maurya, Waste Data Engine

> "The customer page is gold. If it doesn't exist, that tells you something — the company is either early or hiding their install base. That changes how I score them." — Max Mitcham, Trigify

---

**Next: Pass 2–3 validated seed domains to Step 2b (Ocean.io run).**

---

**Step 2b — Configure the Ocean.io run**

**+ Add rows → Find Companies → Ocean.io Lookalike**

In the Company Domain field: paste **all 2–3 seed domains at once**, comma-separated.
Ocean.io accepts up to 10 domains in a single run — do not run it separately per seed.

**Set these filters before running:**

| Filter | What to set | Notes |
|---|---|---|
| Company sizes | Select the size bands matching ICP | Multi-select of ranges — 11–50, 51–200, 201–500, etc. Not free text |
| Primary countries | Select target geography | Headquarters location |
| Industry categories | Select 2–3 relevant industries | Multi-select |
| Technologies | Add CRM tools if ICP-specific | e.g. Salesforce, HubSpot — filters before results return |
| Keywords | Add 1–2 ICP descriptor words | Searches company descriptions |
| Minimum similarity score | Start at 0.6, raise to 0.8 for tighter results | Higher = fewer but better results |
| Domains to exclude | Add known competitors upfront | They never appear in results |

**Use the preview panel first — it is free.**
Before clicking Run, Ocean.io shows a distribution of industries, sizes, and countries your results will return. Check it. If the distribution looks wrong, adjust filters before spending any credits.

**Limit: 20 results** (20 data credits, fits free tier with room left).
Click Run.

---

**Step 2c — Scrub the results**

Delete any row that is:
- A direct competitor of the hiring company
- An agency, consultancy, or design studio
- A holding company or conglomerate
- Outside the target geography
- Wrong size after filtering (Ocean.io employee count data has known inaccuracies — verify outliers)

Keep the 10 cleanest rows.

**If you end up with fewer than 10 clean rows:**
Do not use Crunchbase — it is a lookup tool, not a lookalike finder. Instead:
1. Add 1–2 more seed domains (you have up to 10 slots)
2. Lower the `Minimum similarity score` by 0.1
3. Add one more size band in `Company sizes`
Re-run with adjusted settings.

You now have 10 clean companies: Company Name, Domain, Employee Count, Industry, Description.

---

### Step 3 — Add 2 native context columns

These go BEFORE the SignalOS column. They create the contrast: Clay gives data, SignalOS gives intelligence.

**Column A — Claygent Summary (dynamic ICP context):**
- **+** → Enrich → search "Claygent" → select Claygent Web Researcher
- Prompt: `Review this company's website and summarize their exact target audience and value proposition in one concise sentence.`
- Input: Domain
- Run on all rows
- Cost: ~2–3 Clay Action credits per row (20–30 total for 10 rows)

This column feeds into the SignalOS scoring_context dynamically. Every row gets a bespoke intelligence summary.

**Column B — Job Openings:**
- **+** → Enrich → search "Job Openings" → Find Job Openings
- Input: Domain
- Keywords: `sales, revenue, GTM, SDR, BDR, account executive`
- Past 30 days: Yes
- Run on all rows

---

### Step 4 — Add the SignalOS Custom HTTP column

**+** → Enrich → search "HTTP" → Custom HTTP API

**Request tab:**
```
Method: POST
URL:    https://YOUR-NGROK-URL.ngrok-free.app/score-company
```
*(Paste the URL you copied from Terminal 2 in Phase 2 + `/score-company`)*

**Headers tab:**
```
Content-Type: application/json
```

**Body tab** — select Raw JSON:
```json
{
  "company_name": "{{Company Name}}",
  "domain": "{{Domain}}",
  "client_id": "demo",
  "scoring_context": "{{Claygent Summary}}. ICP is actively scaling outbound. Signal: hiring SDR or RevOps roles now."
}
```

By passing `{{Claygent Summary}}` dynamically, SignalOS produces a bespoke Intelligence Summary for every single row — not a generic one. This is the key difference from a static scoring_context.

**Adjust the static part per application:**

For Weflow AI:
```json
"scoring_context": "{{Claygent Summary}}. Weflow AI ICP: B2B SaaS RevOps team scaling outbound. Signal: hiring SDR or RevOps roles now."
```

For Unframe.ai:
```json
"scoring_context": "{{Claygent Summary}}. Unframe.ai ICP: enterprise with complex document workflows. Signal: recent funding or digital transformation."
```

For Dagster:
```json
"scoring_context": "{{Claygent Summary}}. Dagster ICP: data engineering team at Series A–C. Signal: growing data team, hiring data engineers now."
```

Only the static description after the Claygent variable changes. The `{{Claygent Summary}}` stays in every version.

---

### Step 5 — Map the output fields

Add these output columns one by one — **+ Add output** for each:

| Column Name | Response Path | Type |
|---|---|---|
| Score | `score` | Number |
| Confidence | `confidence` | Number |
| Window | `contact_window` | Text |
| Top Signal | `top_signal` | Text |
| Aha Moment | `aha_moment` | Text |
| Intelligence Summary | `situation` | Text |
| Email Opener | `email_opener` | Text |
| Cost | `cost_usd` | Number |

**Test on row 1 first.** Run one row only. Check:
- Score is a number (not blank, not error)
- Intelligence Summary is a full paragraph referencing this specific company
- Aha Moment is specific (not generic like "this company is growing")

If yes → run all rows. If no → read Terminal 1 error before continuing.

---

### Step 6 — Run all rows and screenshot

Select all → Run column → wait 5–12 seconds per company (auto-detecting all 5 signals).

**Take two screenshots before recording:**
1. **Wide** — all columns visible, all 10 rows scored, Intelligence Summary column partially visible
2. **Zoomed** — one row's Intelligence Summary field fully readable on screen

These screenshots go in the LinkedIn post and the first 20 seconds of the Loom.

---

## Phase 4 — Record the Loom (30 min)

### Before clicking record

Have these three things open and ready:
1. Clay table — all 10 rows scored
2. Gradio demo at `http://localhost:7860`
3. Slack — channel where SignalOS fires alerts

Pick the **best row** before recording: highest score + most specific Intelligence Summary paragraph. This is the row you click on during the Loom.

---

### Exact script — 3 min 30 sec

```
[0:00–0:20] — The Hook
"I built a signal intelligence layer that turns Clay from a data
foundation into an active reasoning engine. Most teams use Clay
to pull job counts and tech stacks. I built a Custom HTTP
integration that evaluates what those signals actually mean
for [Hiring Company]'s pipeline."

[0:20–0:55] — Show the Clay table
Point to native columns:
"These are 10 strict lookalikes of your newest customer.
Standard Clay — we know they're hiring 3 SDRs."

Point to SignalOS columns:
"But look at this column. My API ingested that context,
scored the account, and generated this Intelligence Summary."

Read the Intelligence Summary out loud for the best row.

"It didn't just give me data. It identified the exact
buying window and why this week is the right moment."

[0:55–1:45] — Switch to Gradio, run live
"Let me show the backend scoring in real time."
Type the domain of your best row. Leave all signal checkboxes blank.
Hit Score Company. Wait for result.

When Intelligence Summary populates — read it out loud.
Point to Cold Call Hooks:
"Three specific cold call hooks. Each one is grounded in
a real detected signal — not a generic AI template.
This is data modeling applied to outbound."

[1:45–2:20] — Show Slack
Switch to Slack.
"When an account scores above threshold, this fires automatically."
Point to the ROI line:
"$0.004 API cost. $45,000 estimated pipeline value.
The system proves its own ROI on every single run."
Point to HubSpot button:
"Deal already created in HubSpot. SDR clicks once."

[2:20–3:00] — The Close
"Your reps don't leave Clay. Nothing changes about
their workflow. One Custom HTTP column. Every row
now has a reason and a buying window."

"I can deploy this exact setup into your live Clay
workspace this week. You see it working before
anything else happens."

[3:00–3:30]
Stop recording.
```

**Loom title:** `[Company Name] — SignalOS Data Activation Layer (3 min)`

---

## Phase 5 — Send the DM

Find the hiring manager on LinkedIn. Not HR. Founder, Head of Sales, VP RevOps, or Head of Growth.

```
[First name] — built a programmable reasoning layer that sits
inside your Clay workspace as a Custom HTTP column.

Automates the jump from raw data to pipeline activation for
[Company]'s exact ICP. 3-min teardown: [Loom link]

Worth a chat?
```

45 words. Loom link only. No resume.

---

## Reuse per new application — 3 changes only

| What changes | Where |
|---|---|
| Ocean.io seed domains (2–3) | Step 2 — customers of your target company |
| Static text after `{{Claygent Summary}}` | Step 4 body JSON — their ICP description |
| Loom title + close line | Name the company you're applying to |

**Steps each time:**
1. Clay → duplicate the table (table menu → Duplicate)
2. Delete existing rows
3. Re-run Ocean.io with new seeds (2–3 seeds from new target's customers)
4. Re-run Claygent column
5. Update static ICP text in HTTP column body
6. Run all rows
7. Record Loom (same script, 30 min)

---

## Full timeline

| Step | First run | Each duplicate |
|---|---|---|
| Start API + ngrok + test | 10 min | 10 min |
| Build Clay table | 90 min | 20 min |
| Screenshots | 5 min | 5 min |
| Loom recorded + uploaded | 30 min | 30 min |
| 3 DMs sent | 15 min | 15 min |
| **Total** | **~2.5 hrs** | **~1 hr 20 min** |

---

## Job boards — check weekly

- [community.clay.com/x/full-time-jobs](https://community.clay.com/x/full-time-jobs) — globally open founding GTM roles, lowest competition
- [himalayas.app/jobs/gtm-engineer](https://himalayas.app/jobs/gtm-engineer) — remote-first
- [contra.com](https://contra.com) — fractional/contract, truly global

**Target:** Founding GTM Engineer at seed–Series B AI startups. Global-remote-open or visa-sponsoring. Low applicant volume.

**Not targeting:** Anthropic, OpenAI, large AI labs — visa problem + high competition volume.
