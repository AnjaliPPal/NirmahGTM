# SignalOS — CLAUDE.md

## What This Project Is

SignalOS is a **production AI reasoning engine** for B2B GTM teams.
It does not replace Clay — it sits **inside Clay** as a Custom HTTP column and adds the reasoning layer Clay cannot provide natively.

**Stack:** FastAPI + Python + Claude API (claude-sonnet-4-6) + Supabase + Slack + HubSpot + n8n

**Positioning for hiring managers:** This demonstrates what a Forward Deployed Engineer / AI Engineer does in production — real customers, real integrations, evals, agent orchestration, MCP tooling.

---

## Architecture

```
Clay table row → POST /score-company
                        │
                        ├─ Auto-detects signals (Google News RSS, Greenhouse/Lever, website scan)
                        ├─ RAG: retrieves 5 nearest past scored companies + their outcomes
                        ├─ Claude Sonnet reasons over signals + RAG context
                        ├─ Returns: score 1-10, aha_moment, top_signal, contact_window, pitch_block
                        │
                        ├─ score ≥ 6 + confidence ≥ 0.7 → HubSpot CRM push + Slack alert
                        ├─ confidence < 0.7 → quarantine to #human-review-required
                        └─ All results → Supabase (analytics + RAG source)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scorer/scorer.py` | Core scoring logic — Claude prompt, RAG retrieval, CRM gating |
| `scorer/models.py` | All Pydantic models: Signals, ScoreResult, CRMResult |
| `scorer/signal_detector.py` | Auto-detects 5 GTM triggers from free public sources |
| `scorer/crm.py` | HubSpot: upsert contact (409 fallback), create deal, associate |
| `scorer/slack.py` | Slack alert with ROI receipt, HubSpot deep link |
| `scorer/prompts.py` | All Claude prompts — keep prompt changes logged in roadmap |
| `api/main.py` | FastAPI routes: POST /score-company, GET /health, POST /push-to-crm |
| `db/schema.sql` | Supabase schema — run once in SQL editor |
| `n8n/signalos_workflow.json` | n8n automation workflow |

---

## Code Rules

- Python 3.11+, type hints on all functions
- Pydantic v2 models for all inputs/outputs
- Every new function gets a test in `tests/`
- Never raise from CRM/Slack — return error in result model, log, continue
- Prompt changes: document old→new in GTMFinalroadmapv1.md under changelog
- Free-tier only: Supabase free, Railway free, no paid APIs except Claude + OpenAI (as needed)
- Multiple free accounts allowed (legal): Railway x4, Supabase x4, Vercel x4

---

## Env Variables

```
ANTHROPIC_API_KEY=          # Required — Claude API
SLACK_WEBHOOK_URL=          # Optional — Slack alerts
SUPABASE_URL=               # Optional — DB + RAG storage
SUPABASE_KEY=               # Optional — DB key
HUBSPOT_ACCESS_TOKEN=       # Optional — CRM push
OPENAI_API_KEY=             # Optional — multi-LLM routing pre-filter
GROQ_API_KEY=               # Optional — cheap cache hits
SCORE_THRESHOLD=6           # Minimum score to trigger CRM push
CONFIDENCE_THRESHOLD=0.7    # Below this → human review queue
```

---

## v2.0 WOW Features (build order)

1. **Pitch block** — domain-specific sales opener in ScoreResult (Phase 1, no deps)
2. **RAG + pgvector** — embed past scored companies, retrieve outcomes as scoring context (Phase 2, needs Supabase pgvector enabled)
3. **LLM Evals Dashboard** — log every Claude call, track score→reply_rate correlation (Phase 2)
4. **LangGraph agent** — state-machine: detect → enrich → score → route → notify (Phase 3)
5. **MCP server** — Model Context Protocol wrapping SignalOS tools for Claude Desktop (Phase 3)
6. **Multi-LLM routing** — GPT-4o-mini pre-filter, Claude Sonnet for scoring, Groq for cache hits (Phase 3)
7. **TypeScript client** — auto-generated from OpenAPI spec via openapi-typescript-codegen (Phase 4)
8. **Next.js live demo** — Vercel free tier, hiring managers self-serve test (Phase 4)

---

## Target Jobs (validated from real JDs in jobfrominternet.md)

| Company | Role | Why This Project Hits It |
|---------|------|--------------------------|
| Anthropic | GTM Engineer / Solutions Architect | Evals dashboard, MCP server, Claude API production use |
| Cohere | Forward Deployed Engineer | LangGraph, multi-LLM, customer-facing deployment |
| Sierra | AI Engineer | Agent orchestration, CRM integration, real customer workflows |
| Decagon | AI Engineer | Production AI system, Supabase, FastAPI, eval loops |
| Glean | GTM Engineer | Clay integration, signal detection, pipeline automation |
| Webflow | Solutions Engineer | TypeScript client, live demo, customer onboarding |
| Harvey | Forward Deployed Engineer | Complex workflow automation, CRM push, reasoning traces |

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

All 6 CRM tests pass. Run before every commit.

---

## Deploy

```bash
# Railway (free tier)
railway login
railway init
railway up

# Local
uvicorn api.main:app --reload --port 8000
```

---

## Roadmap File

`D:\GTMSignolos\GTMFinalroadmapv1.md` — full changelog, v2.0 plan, job coverage matrix.
Update this file whenever you change prompts, add features, or modify the architecture.
