# SignalOS

**Know which of your 500 target accounts is ready to buy — right now.**

SignalOS monitors target companies 24/7, detects when 3+ buying signals converge, and fires a Slack alert with a ready-to-send email opener. Your SDRs stop cold-calling everyone and start calling the 3 accounts that are actually in-market today.

---

## The Problem It Solves

B2B sales teams pay $3K–$8K/month for signal intelligence (Clay, Bombora, 6sense).
Most still get 2% reply rates because their timing is wrong.

SignalOS detects **when** to reach out — not just **who** to reach out to.

---

## How It Works

```
Your target account list
        │
        ▼
POST /score-company
        │
        ▼
Claude reasoning over 4 live signals
  → score 1-10 + aha_moment + top_signal + contact window
  → if score ≥ 6: generate cold email opener
        │
        ├──► Supabase (every result, for analytics)
        └──► Slack alert (high-intent only, < 3 seconds)
             🔥 8/10: Just closed funding and hired 3+ GTM roles. 
                      This is a total outbound rebuild. Window is NOW.
```

**4 signals tracked:**
- Raised funding in last 90 days
- Actively hiring GTM/Sales roles
- Headcount growth % last 6 months
- Current tech stack

---

## Quickstart

```bash
git clone https://github.com/yourusername/signalos
cd signalos-v1
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, SLACK_WEBHOOK_URL, SUPABASE_URL, SUPABASE_KEY

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
# Import n8n/signalos_workflow.json
# Set schedule — runs every 2 hours automatically
```

---

## Pricing

| Item | Cost |
|------|------|
| AWS / hosting | ~$15/mo |
| Claude API | ~$35/mo (at scale) |
| **Total infra** | **~$50/mo** |
| **Client price** | **$1,500/mo** |

Comparable services charge $3K–$8K/month. Client owns the code.

---

## Stack

- **API:** FastAPI + uvicorn
- **AI:** Claude Sonnet (reasoning, not rules)
- **DB:** Supabase (Postgres)
- **Alerts:** Slack Incoming Webhooks
- **Orchestration:** n8n (local, free)

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
