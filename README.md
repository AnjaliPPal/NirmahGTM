# NirmahGTM

**Know which of your 500 target accounts is ready to buy — right now.**

NirmahGTM monitors target companies 24/7, detects when 3+ buying signals converge, and fires a Slack alert with a ready-to-send email opener. Your SDRs stop cold-calling everyone and start calling the 3 accounts that are actually in-market today.

---

## The Problem It Solves

B2B sales teams pay $3K–$8K/month for signal intelligence (Clay, Bombora, 6sense).
Most still get 2% reply rates because their timing is wrong.

NirmahGTM detects **when** to reach out — not just **who** to reach out to.

---

## How It Works

```
Your target account list
        │
        ▼
POST /score-company
        │
        ▼
Groq llama-3.3-70b reasoning over 5 live signals
  → score 1-10 + aha_moment + top_signal + contact window
  → if score ≥ 6: generate cold email opener
        │
        ├──► Supabase (every result, for analytics)
        └──► Slack alert (high-intent only, < 3 seconds)
             🔥 8/10: Just closed funding and hired 3+ GTM roles. 
                      This is a total outbound rebuild. Window is NOW.
```

**5 signals tracked:**
- Leadership changes (new exec hires — VP Sales, CRO)
- Hiring GTM/Sales roles
- Tech stack (CRM + sales-engagement gaps)
- Funding & M&A in last 90 days
- Hidden intent (expansion/growth news before job posts appear)

---

## Quickstart

```bash
git clone https://github.com/yourusername/NirmahGTM
cd NirmahGTM-v1
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
cp .env.example .env
# Fill in GROQ_API_KEY (required); add SLACK + SUPABASE keys for full functionality

uvicorn api.main:app --reload --port 8000
```

**Test it:**
```bash
curl -X POST http://localhost:8000/score-company \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "domain": "acme.com",
    "client_id": "demo",
    "signals": {
      "funded_90d": true,
      "hiring_gtm": true,
      "growth_pct": 45,
      "tech_stack": ["Salesforce", "Outreach", "LinkedIn Sales Navigator"]
    }
  }'
```

Expected: score 8–9, Slack fires, result in Supabase.

**API docs:** `http://localhost:8000/docs`

---

## Database Setup

Run `db/schema.sql` once in your Supabase SQL editor.

---

## n8n Automation

```bash
npx n8n
# Open http://localhost:5678
# Import n8n/NirmahGTM_workflow.json
# Set schedule — runs every 2 hours automatically
```

---

## Pricing

| Item | Cost |
|------|------|
| Hosting (ngrok/Railway free tier) | ~$0–15/mo |
| LLM API (Groq free tier; optional OpenAI pre-filter) | ~$0–35/mo (at scale) |
| **Total infra** | **~$15–50/mo** |
| **Client price** | **$1,500/mo** |

Comparable services charge $3K–$8K/month. Client owns the code.

---

## Stack

- **API:** FastAPI + uvicorn
- **AI:** Groq llama-3.3-70b-versatile (free tier) + optional GPT-4o-mini pre-filter
- **DB:** Supabase (Postgres + pgvector)
- **Alerts:** Slack Incoming Webhooks
- **Orchestration:** n8n (local, free)

---

## Evals

Two layers prove the scoring engine works:

- **Offline** — a labeled golden set you can run in ~3 minutes, no live campaign needed:
  ```bash
  python evals/run_eval.py
  ```
  Prints band accuracy, high/low separation, top-signal agreement, and confidence
  calibration, and exits non-zero if quality drops below `--min-accuracy` (a
  regression gate). See [`evals/README.md`](evals/README.md). Sample scorecard:
  ```
  NirmahGTM Offline Eval - prompt v2.0 - 30 cases
  Band accuracy:        100.0%  (30/30)
  High/low separation:  PASS  (min high 7 vs max low 2)
  Top-signal agreement: 75.0%  (3/4 labeled)
  ```
- **Online** — `/eval-report/{client_id}` tracks real reply/close rates by prompt
  version from `/webhook/hubspot-reply` outcomes.

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
