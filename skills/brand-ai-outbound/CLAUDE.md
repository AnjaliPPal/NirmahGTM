# Skill: /brand-ai-outbound
# Purpose: Build brand.ai's ICP prospect list, score with SignalOS, generate full application package.

---

## What this skill does

You are running a 4-phase autonomous workflow as part of Anjali's job application to brand.ai.
brand.ai is hiring a GTM Engineer (careers@brand.ai). The application requires:
1. A Loom walkthrough of a real workflow you built
2. 3 short-answer questions (answered below)
3. Resume (Anjali handles separately)

You will produce 4 files as output. Do not summarise — write the files.

---

## PHASE 1 — Research (lock the ICP)

### What you know (do not re-research, it's validated)

**Execution:** This workflow runs via `python skills/brand-ai-outbound/run.py` (there is no
`/brand-ai-outbound` slash command). This file documents the logic; run.py is the source of truth.

**brand.ai confirmed customers (verified on brand.ai homepage, May 30 2026 — THREE, not one):**
- Brian Irving, CMO at **Lyft** (lyft.com) — two-sided mobility marketplace
- David Corns, CMO at **Turo** (turo.com) — two-sided mobility marketplace
- Chelsey Susin Kantor, CMO at **Groq** (groq.com) — AI-native infrastructure
- Mouthwash Studio = agency partner, not a target
→ Ocean.io lookalike seeds = lyft.com + turo.com + groq.com (all three)

**brand.ai's ICP (derived from their site + JD):**
- CMO or Head of Brand at a company where AI is disrupting brand work
- Multi-product or global brand (brand consistency = the problem)
- Currently investing in brand talent (hiring signal = budget confirmed)
- AI-native company OR deploying AI content at scale (Midjourney, Runway, Adobe Firefly in stack)
- Company size: 50–500 employees (Series A–C), tech-adjacent

**5 signals that qualify a brand.ai prospect:**
1. Actively hiring "Head of Brand" OR "Brand Designer" OR "Brand Strategist" RIGHT NOW (Greenhouse/Lever)
2. New CMO hired in last 90 days (leadership change = mandate window)
3. AI-native company OR 2+ distinct customer-facing products
4. Recent rebrand OR new market/product expansion in last 90 days
5. AI content tools in tech stack (Midjourney, Runway, Adobe Firefly, Canva for Teams, Figma AI)

**Scoring context string to pass to SignalOS for every company:**
```
Lookalike of Lyft (anchor: lyft.com). Brian Irving CMO at Lyft is brand.ai's confirmed customer.
Target = CMO/Head of Brand at multi-product tech company actively investing in brand.
Qualify if: hiring brand talent NOW + AI-native or AI-disrupted brand stack.
Disqualify if: pure B2C consumer brand, no AI dimension, <50 employees.
```

### Only do this if something is unclear
If you need to verify the Lyft testimonial or brand.ai product, you may WebFetch brand.ai's homepage.
Otherwise skip — the ICP is locked.

---

## PHASE 2 — Ingest company list

### Primary path (if Anjali ran Clay Ocean.io)
Look for a file at `skills/brand-ai-outbound/prospects.csv` or `skills/brand-ai-outbound/prospects.md`.
If it exists, read it. Expected columns: company_name, domain (minimum).
Use all rows as the candidate list.

### No generic fallback — real data only
There is NO fallback list of famous companies. That is the junior move and is banned.
Every candidate must carry a real, dated `why_now` signal. The list comes from:
1. Run Clay Ocean.io "Find Lookalike Companies" on each seed: lyft.com, turo.com, groq.com (limit 50 each).
2. Merge + dedupe.
3. Keep ONLY companies with a real why-now (ranked): hiring Head of Brand/Brand Designer now >
   new CMO in last 90 days > recent rebrand/new product/market expansion > 2026 funding.
4. Export CSV with columns: company_name, domain, why_now → save as `skills/brand-ai-outbound/prospects.csv`.

run.py refuses to run without this file and never invents companies.

---

## PHASE 3 — Score with SignalOS

### Setup check
Before calling the API, verify it is running:
```
GET http://localhost:8000/health
```
If health check fails, tell Anjali: "Start SignalOS: cd D:\GTMSignolos\signalos-v1 && uvicorn api.main:app --reload --port 8000"
Then wait for her confirmation before continuing.

If ngrok is running, use the ngrok URL instead of localhost. Ask Anjali: "Is ngrok running? If yes, paste the https:// URL."

### Batch scoring (preferred — faster)
POST to `/batch-score`:
```json
{
  "companies": [
    {
      "company_name": "{{name}}",
      "domain": "{{domain}}",
      "client_id": "brand-ai-demo",
      "scoring_context": "Lookalike of Lyft (anchor: lyft.com). Brian Irving CMO at Lyft is brand.ai confirmed customer. Target = CMO/Head of Brand at multi-product tech company actively investing in brand. Qualify if: hiring brand talent NOW + AI-native or AI-disrupted brand stack. Disqualify if: pure B2C consumer brand no AI dimension <50 employees."
    }
  ],
  "min_score": 6
}
```
Include ALL candidates in a single request (up to 50).

### Fallback (if langgraph not installed)
Loop `/score-company` for each company individually. Same body structure, without the `companies` wrapper.

### After scoring
Filter: keep only results where `score >= 6` AND `error` is null AND `suppressed` is false.
Rank by `score` descending. Take top 10.
If fewer than 10 pass, lower threshold to score >= 5 and note this in the output.

---

## PHASE 4 — Write output files

Write all 4 files below. Do not print them to the terminal — write them as files.

---

### File 1: `skills/brand-ai-outbound/brand-ai-top10.md`

```
# brand.ai ICP — Top 10 Prospects
# Generated: {{date}}
# Anchor: lyft.com (Brian Irving, CMO)
# Scoring model: SignalOS v1.2 / Groq llama-3.3-70b

| Rank | Company | Domain | Score | Confidence | Aha Moment | Pitch Block | Contact Window |
|------|---------|--------|-------|------------|------------|-------------|----------------|
| 1    | ...     | ...    | ...   | ...        | ...        | ...         | ...            |
...

## Clay table setup (paste these rows)
[same data formatted for copy-paste into Clay]

## Discard list (scored but below threshold)
[company, domain, score, reason]
```

---

### File 2: `skills/brand-ai-outbound/loom-script.md`

Write a word-for-word Loom script. Max 3 minutes 30 seconds. Use the real company names and scores from Phase 3.

Structure:
```
LOOM SCRIPT — brand.ai GTM Engineer Application
Total runtime: 3:30 max
Face cam: ON. Screen: Clay table open.

[0:00–0:20] HOOK
"Hi [FIND THE HIRING MANAGER NAME — search LinkedIn: 'brand.ai GTM head of growth'
or check brand.ai/about or their LinkedIn company page before recording].
I built a prospect scoring system using your actual ICP — starting from
Brian Irving at Lyft, who you've worked with — to find 10 companies
that look like your best-fit buyer right now."

[0:20–1:00] SHOW CLAY TABLE
Show the table with 10 rows. All scores populated.
"These came from Ocean.io's lookalike engine seeded with lyft.com.
I filtered for one thing: companies actively investing in brand leadership RIGHT NOW —
because that's when your evaluation window is open."
Scroll through the table slowly.

[1:00–2:00] SHOW ONE ROW IN DETAIL
Click on the highest-scoring row.
Show: score, confidence, aha_moment, pitch_block from SignalOS.
"SignalOS — the reasoning layer I built — detected [TOP SIGNAL from row].
The aha moment it generated: [AHA MOMENT TEXT].
That's not a firmographic filter. That's a buying signal."

[2:00–2:45] SHOW SIGNALOS CUSTOM HTTP COLUMN
Click on the SignalOS Score column header. Show the POST config.
"This is SignalOS running inside Clay as a Custom HTTP column.
Clay gives you the enrichment breadth. SignalOS gives you the reasoning depth.
Neither does the other's job. That's the architecture I'd bring to your team."

[2:45–3:00] CTA
"The code is on GitHub [link]. I'd be happy to walk through
how I'd wire this to your Attio CRM in week 1.
Would you be opposed to a 20-minute call?"
```

---

### File 3: `skills/brand-ai-outbound/application-email.md`

```
Subject: Built your ICP scoring system — 3 min demo

Hi [HIRING MANAGER NAME],

Saw you're hiring a GTM Engineer. I built a proof of concept:
10 Lyft-lookalike companies scored by buying signal, not firmographics —
starting from Brian Irving's testimonial on your site.

Demo (3 min): [LOOM LINK]
Clay table: [PUBLIC CLAY LINK]
Code: [GITHUB LINK]

Would you be opposed to a 20-minute call?

— Anjali Pal
anjalipal931@gmail.com
```

Note: Total body = 45 words max. DATA (Lyft ICP anchor) → ASSUMPTION (signal = budget confirmed) → CTA (call).
Forbidden words: "passionate", "excited", "love to", "reach out", "synergy", "touch base", "just following up".

---

### File 4: `skills/brand-ai-outbound/short-answers.md`

The brand.ai JD requires 3 short answers (2–3 sentences each).
Write them grounded only in what SignalOS actually does — no embellishment.

```
# brand.ai — Short Answer Questions

## Q1: What's the most complex workflow you've built and what did it accomplish?

SignalOS is a multi-stage signal intelligence pipeline: it auto-detects 5 GTM triggers
from public sources (Google News RSS, Greenhouse/Lever, website scan), runs a RAG
retrieval step against past-scored companies, feeds everything to a Groq LLM for scoring,
then routes results through governance (confidence gating), HubSpot CRM push, and Slack
Block Kit alerts — all triggered from a Clay Custom HTTP column. The outcome:
a rep gets a prioritised account list with a data-backed reason to call, not a gut-feel tier.

## Q2: Describe a time you had to choose between "done quickly" vs "done perfectly" — what did you choose and why?

When building SignalOS's confidence routing, I chose "done quickly" on the HubSpot integration
and "done perfectly" on the governance layer — because a bad CRM push corrupts data for everyone,
while a rough Slack alert is just a formatting complaint. The principle: get the irreversible parts
right first, ship the reversible parts fast, fix them on feedback.

## Q3: What's your favourite automation tool and why?

n8n — because it forces you to treat every step as an explicit node with a named input and output,
which means failures are inspectable and the workflow is readable by a non-engineer.
Clay is my favourite for enrichment specifically, but for multi-path orchestration with error
handling and webhook logic, n8n is still the most honest tool in the stack.
```

---

## Output summary (print this to terminal when done)

```
✅ PHASE 1 — ICP locked
✅ PHASE 2 — {{N}} candidates ingested (Clay file / self-sourced)
✅ PHASE 3 — {{N}} scored, {{N}} passed threshold
✅ PHASE 4 — 4 files written:

  skills/brand-ai-outbound/brand-ai-top10.md      → top 10 ranked prospects
  skills/brand-ai-outbound/loom-script.md          → word-for-word Loom script (3:30)
  skills/brand-ai-outbound/application-email.md   → 45-word email to careers@brand.ai
  skills/brand-ai-outbound/short-answers.md        → 3 JD short answers

NEXT (Day 2 — you do):
1. Start SignalOS:   cd D:\GTMSignolos\signalos-v1 && uvicorn api.main:app --reload --port 8000
2. Start ngrok:      ngrok http 8000
3. Run Clay Ocean.io lookalike: lyft.com → 50 results → export → save as prospects.csv here
4. Re-run skill:     /brand-ai-outbound   (will use your Clay list this time)
5. Build Clay table: paste top 10, add SignalOS Custom HTTP column, run all rows
6. Record Loom using loom-script.md
7. Send email from application-email.md to careers@brand.ai
```

---

## Rules for this skill

- Never fabricate a company name, score, or signal. Use only what SignalOS returns.
- Never claim Clay can call SignalOS autonomously — it uses a Custom HTTP column that Anjali runs.
- If SignalOS is not running, do not proceed to Phase 3. Tell Anjali to start it first.
- If a company domain fails health check inside SignalOS (unreachable), skip it — do not guess a score.
- Write files in `skills/brand-ai-outbound/` relative to the `signalos-v1/` project root.
- The Attio gap is real: SignalOS pushes HubSpot, brand.ai uses Attio. Name this in the Loom and short answers — do not hide it.
- Hiring manager name: always search before recording. Never use "Hi there" or "Hi team".
