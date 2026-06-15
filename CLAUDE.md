# SignalOS — CLAUDE.md
# Last updated: June 3, 2026
# Rule: update this file every time the architecture, LLM stack, or test count changes.

## What This Project Is

SignalOS is a **production AI reasoning engine** for B2B GTM teams.
It does not replace Clay — it sits **inside Clay** as a Custom HTTP column and adds the reasoning layer Clay cannot provide natively.

**Positioning for hiring managers:** This demonstrates what a Forward Deployed Engineer / AI Engineer does in production — real customers, real integrations, evals, agent orchestration, MCP tooling.

**Stack (actual, verified May 30 2026):**
- FastAPI + Python 3.11
- Groq API — llama-3.3-70b-versatile (scoring), llama-3.1-8b-instant (opener, situation, talking points, contact ranking, batch summary)
- OpenAI text-embedding-3-small (RAG embeddings — optional, degrades gracefully if key not set)
- GPT-4o-mini (pre-filter — optional, falls back to rule-based if OPENAI_API_KEY not set)
- Supabase (Postgres + pgvector) + Langfuse (tracing, optional) + HubSpot + Slack

---

## Architecture (current, verified against code)

```
Clay table row → POST /score-company
                        │
                        ├─ Domain validation (httpx.AsyncClient HEAD — returns error if unreachable)
                        ├─ Cache check (28-day Supabase lookup — returns cached result if hit)
                        ├─ Cooldown check (45-day suppression — returns suppressed=True if alerted recently)
                        │
                        ├─ Auto-detect 5 signals (signal_detector.py — Google News RSS, Greenhouse/Lever/Ashby ATS API, homepage HTML)
                        ├─ Enrich company (enrichment.py — Hunter → Apollo → Firecrawl waterfall)
                        ├─ Pre-filter (router.py — GPT-4o-mini or rule-based fallback)
                        ├─ RAG retrieval (rag.py — pgvector cosine similarity, top-5 similar past accounts)
                        │
                        ├─ Groq llama-3.3-70b-versatile scores: score 1-10, confidence, reasoning,
                        │   top_signal, contact_window, aha_moment, signal_scores, pitch_block
                        │
                        ├─ Contact ranking (llama-3.1-8b-instant — picks most relevant contact for top signal)
                        ├─ Email opener (llama-3.1-8b-instant via generate_opener_gemini() — DATA→ASSUMPTION→CTA)
                        ├─ Situation paragraph (llama-3.1-8b-instant — combines all 5 signals into analyst prose)
                        ├─ Talking points (llama-3.1-8b-instant — 3-5 BDR cold-call hooks)
                        │
                        ├─ score ≥ 6 + confidence ≥ 80 → HubSpot CRM push + Slack Block Kit alert (main channel)
                        ├─ score ≥ 6 + confidence < 80 → Slack #human-review-required (quarantine)
                        ├─ Store embedding in pgvector (for future RAG retrieval)
                        └─ All results → Supabase signals table (analytics + RAG source)
```

**Batch path:** `POST /batch-score` → `scorer/agent.py` LangGraph fan-out → parallel `score_company` per company → rank → Groq llama-3.3-70b executive brief.

---

## LLM Routing (actual — verified against router.py and scorer.py)

| Task | Model | Client | Cost |
|------|-------|--------|------|
| Pre-filter (has signals worth scoring?) | gpt-4o-mini | OpenAI (optional) | ~$0.0001/call |
| Pre-filter fallback (no OPENAI_API_KEY) | rule-based | None | $0 |
| Scoring | llama-3.3-70b-versatile | Groq | Free tier |
| Opener / Situation / Talking points / Contact ranking / Batch summary | llama-3.1-8b-instant | Groq | Free tier |
| RAG embeddings | text-embedding-3-small | OpenAI (optional) | ~$0.00002/call |

**Note on naming:** `router.py` exports `GEMINI_OPENER_MODEL = "llama-3.1-8b-instant"` — the variable is named "Gemini" but actually runs Groq. Historical naming artefact. Do not change without updating scorer.py imports.

**Note on reply classification:** `/classify-reply` (new June 3) labels incoming emails as hot/warm/not_now/not_interested/out_of_office/bounce. Routes to human/nurture/suppress/auto-reply. Implemented in `scorer/router.py` + `api/main.py`.

**Note on /health:** The `/health` endpoint reports `"model": "llama-3.3-70b-versatile"` (fixed June 5 2026 — previously a stale `claude-sonnet-4-6` string from v1).

---

## Key Files

| File | Purpose |
|------|---------|
| `scorer/scorer.py` | Core scoring logic — Groq calls, RAG injection, opener, situation, talking points, CRM gating |
| `scorer/models.py` | All Pydantic models: Signals, CompanyInput, ScoreResult, CRMResult, Batch*, Eval* |
| `scorer/agent.py` | LangGraph fan-out batch agent — scores up to 50 companies in parallel |
| `scorer/signal_detector.py` | Auto-detects 5 GTM triggers from free public sources (Google News RSS, ATS APIs, HTML scan) |
| `scorer/research_target.py` | Auto-detect a target company's confirmed customers (homepage + /customers page + Google News). Used by outbound skills to seed ICP lookalike lists without hardcoding. |
| `scorer/enrichment.py` | Waterfall enrichment: Hunter → Apollo → Firecrawl |
| `scorer/router.py` | Pre-filter (GPT-4o-mini or rule-based), opener generation (llama-3.1-8b-instant via Groq) |
| `scorer/rag.py` | pgvector embeddings via OpenAI, retrieves 5 similar past scored companies |
| `scorer/prompts.py` | All LLM prompts (SCORING_SYSTEM_PROMPT, SCORING_PROMPT_V2, OPENER_PROMPT_V1) — versioned, never inline |
| `scorer/crm.py` | HubSpot: upsert contact (409 fallback), create deal, associate |
| `scorer/slack.py` | Slack Block Kit ROI alert (main channel) + quarantine routing (#human-review-required) |
| `mcp_server.py` | FastMCP server — 3 tools: score_company_tool / get_hot_leads / get_pitch |
| `api/main.py` | FastAPI routes: /score-company, /batch-score, /classify-reply, /health, /leads, /push-to-crm, /review-queue, /webhook/hubspot-reply, /eval-report, /admin/failed-inserts |
| `api/deps.py` | Supabase client singleton |
| `demo/app.py` | Gradio UI — type domain, get full score result. Run: `python demo/app.py` (port 7860) |
| `db/schema.sql` | Canonical Supabase schema — must stay in sync with models.py |
| `db/migrations/` | ALTER TABLE scripts for upgrading existing DBs |
| `n8n/signalos_workflow.json` | Importable n8n workflow (scheduled scoring orchestration) |
| `skills/brand-ai-outbound/run.py` | brand.ai application workflow — research → brand signal check → score → 4 output files |
| `skills/brand-ai-outbound/CLAUDE.md` | Documentation for the brand-ai-outbound workflow |
| `evals/golden_set.py` | Offline eval — ~30 hand-labeled cases with fixed Signals (deterministic) |
| `evals/metrics.py` | Pure eval metric math (band accuracy, separation, top-signal, calibration) |
| `evals/run_eval.py` | Eval runner — scores golden set via `score_company(dry_run=True)`, prints scorecard, regression gate |

---

## Signal Detection — What's Detected and How

| Trigger | Source | Method |
|---------|--------|--------|
| 1. Leadership Changes | Google News RSS | Query for exec hires; returns name, title, hire date (RFC 2822) |
| 2. Hiring Signals | Greenhouse / Lever / Ashby public APIs | Tier 0: ATS embed from careers page HTML. Tier 1: slug guessing. Tier 2: Google News |
| 3. Tech Stack | Company homepage HTML | Scan for tool signatures (Salesforce, HubSpot, Outreach, etc.) |
| 4. Funding & M&A | Google News RSS | VC-firm-modifier guard prevents false positives (e.g. "Notion Capital" ≠ Notion) |
| 5. Hidden Intent | Google News RSS | Expansion/growth/scaling keywords before job posts appear |

**Gap (documented):** `signal_detector._GTM_KEYWORDS` detects sales-role hiring (SDR, BDR, AE, RevOps). It does NOT detect brand/marketing hiring (Head of Brand, CMO, Brand Designer). The `skills/brand-ai-outbound/run.py` fills this gap for the brand.ai use case by adding a parallel brand-keyword ATS check.

---

## Code Rules

- Python 3.11+, type hints on all functions
- Pydantic v2 models for all inputs/outputs
- Every new function gets a test in `tests/`
- Never raise from CRM/Slack — return error in result model, log, continue
- Prompt changes: document old→new in GTMFinalroadmapv1.md under changelog
- Free-tier only: Supabase free, Groq free tier, Gemini/OpenAI optional
- All LLM calls use Groq client (`chat.completions.create`) — NOT Anthropic SDK pattern (`messages.create`)
- `GEMINI_OPENER_MODEL` in router.py = llama-3.1-8b-instant on Groq — naming is historical, do not rename without updating imports
- Multiple free accounts allowed (legal): Railway x4, Supabase x4, Vercel x4

---

## Env Variables

```
GROQ_API_KEY=                       # Required — Groq API (free tier, llama-3.3-70b-versatile)
OPENAI_API_KEY=                     # Optional — pre-filter (gpt-4o-mini) + RAG embeddings (text-embedding-3-small)
SLACK_WEBHOOK_URL=                  # Slack main sales channel
SLACK_REVIEW_WEBHOOK_URL=           # Slack #human-review-required channel
NEXT_PUBLIC_SUPABASE_URL=           # Supabase project URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY= # Supabase publishable key
HUBSPOT_ACCESS_TOKEN=               # Optional — CRM push
HUBSPOT_PORTAL_ID=                  # Optional — HubSpot portal ID
SCORE_THRESHOLD=6                   # Minimum score to alert Slack
CONFIDENCE_THRESHOLD=80             # Below this → quarantine to review queue
CACHE_DAYS=28                       # Skip re-scoring same domain within N days (Ritu 4-week rule)
DEAL_ACV=45000                      # Client ACV for ROI estimate in Slack alert
WEBHOOK_SECRET=                     # Auth for POST /webhook/hubspot-reply
ADMIN_API_KEY=                      # Auth for GET /admin/failed-inserts
LANGFUSE_SECRET_KEY=                # Optional — LLM observability
LANGFUSE_PUBLIC_KEY=                # Optional — LLM observability
LANGFUSE_HOST=https://cloud.langfuse.com
HUNTER_API_KEY=                     # Optional — email enrichment (50 credits/month free)
APOLLO_API_KEY=                     # Optional — org enrichment (50 data credits/month free)
FIRECRAWL_API_KEY=                     # Optional — Firecrawl cloud (free 500 credits/mo at firecrawl.dev). Takes priority over API_URL.
FIRECRAWL_API_URL=http://localhost:3002 # Optional — self-hosted Firecrawl (Docker). Used only when API_KEY is not set.
CORS_ORIGINS=                       # Comma-separated allowed origins (defaults to *)
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

153/153 tests passing as of June 5 2026. Run before every code change.

**Offline eval (separate from pytest):** `python evals/run_eval.py` scores the labeled golden set through the real pipeline and prints band accuracy / separation / calibration with a `--min-accuracy` regression gate. Needs GROQ_API_KEY; all other integrations auto-disabled for determinism. See `evals/README.md`.

Test files:
- `tests/test_scorer.py` — core scoring logic, mock Groq calls
- `tests/test_api.py` — FastAPI routes, async domain validation, cache/cooldown
- `tests/test_signal_detector.py` — ATS detection (Greenhouse/Lever/Ashby/unknown), funding false-positive guard
- `tests/test_enrichment.py` — Hunter/Apollo/Firecrawl waterfall
- `tests/test_crm.py` — HubSpot upsert/409/no-email/error paths
- `tests/test_router.py` — pre-filter (GPT-4o-mini + rule-based fallback), opener generation
- `tests/test_rag.py` — embedding, storage, retrieval, format
- `tests/test_agent.py` — LangGraph fan-out, ranking, suppressed exclusion, summary
- `tests/test_eval.py` — webhook recording, eval report math
- `tests/test_research_target.py` — customer extraction (clean/dedup/sources), graceful degradation
- `tests/test_reply_classifier.py` — reply classification (all 6 labels, routing, rule-based fallback, endpoint)
- `tests/test_evals.py` — eval metric math, golden-set integrity, dry_run side-effect gate

---

## Running Locally

```bash
# API server
cd signalos-v1
uvicorn api.main:app --reload --port 8000

# Expose to Clay (for Custom HTTP column)
ngrok http 8000

# Gradio demo UI
python demo/app.py

# MCP server (for Claude Desktop)
python mcp_server.py

# brand.ai application workflow (needs prospects.csv first)
python skills/brand-ai-outbound/run.py
```

---

## Application Layer — brand.ai (May 30 2026)

`skills/brand-ai-outbound/` — job application workflow for brand.ai GTM Engineer role.

**Architecture:**
```
Anjali runs Clay Ocean.io lookalike(lyft.com + turo.com + groq.com) → exports prospects.csv
python skills/brand-ai-outbound/run.py
  Phase 1: ICP confirmation (locked from 3 real brand.ai customers)
  Phase 2: Ingest prospects.csv (company_name, domain only — no manual why_now)
  Phase 3: Brand hiring check (Head of Brand, CMO, Brand Designer via ATS API — gap SignalOS doesn't cover)
  Phase 4: POST → SignalOS /batch-score (auto-detects all 5 signals per company + brand_evidence in scoring_context)
  Phase 5: Write 4 files → brand-ai-top10.md, loom-script.md, application-email.md, short-answers.md
```

**Why this skill exists:** SignalOS's signal_detector uses sales keywords (SDR, BDR, AE, RevOps). brand.ai's ICP signal is brand/marketing hiring (CMO, Head of Brand, Brand Designer). The skill adds brand-keyword ATS detection as a parallel check, then passes the result into scoring_context so the LLM weights it.

**brand.ai real customers (verified May 30 2026 on brand.ai homepage):**
- Lyft — Brian Irving, CMO
- Turo — David Corns, CMO
- Groq — Chelsey Susin Kantor, CMO
- Mouthwash Studio = design agency partner, not a customer

---

## Known Issues (not yet fixed)

| # | Issue | File | Priority |
|---|-------|------|----------|
| 2 | `GEMINI_OPENER_MODEL` misleadingly named — it's Groq llama-3.1-8b-instant | `router.py` line 15 | Low (naming only) |
| 3 | N+1 Supabase queries (cache + cooldown = 2 SELECT per request) | `api/main.py` | Medium |
| 4 | Global mutable `_client`/`_langfuse` not thread-safe | `scorer.py`, `router.py` | Medium |
| 5 | `score_company()` is still synchronous — `/score-company` offloads via `asyncio.to_thread`, but MCP server + `agent.py` callers still block | `scorer.py` | Medium |
| 6 | Webhook auth skipped silently when `WEBHOOK_SECRET` not set | `api/main.py` | Medium |

**Fixed June 5 2026:** #1 `/health` stale model string; original #5 `/score-company` event-loop blocking (now `asyncio.to_thread`); `openai` added to `requirements.txt` (RAG + pre-filter were silently disabled on clean installs); `CACHE_DAYS` reconciled to 28.

---

## Roadmap File

`D:\GTMSignolos\GTMFinalroadmapv1.md` — full changelog, v2.0 plan, job coverage matrix.
Update this file whenever you change prompts, add features, or modify the architecture.

## Target Jobs

| Company | Role | Why This Project Hits It |
|---------|------|--------------------------|
| Anthropic | GTM Engineer / Solutions Architect | Evals dashboard, MCP server, multi-LLM production use |
| Cohere | Forward Deployed Engineer | LangGraph, multi-LLM, customer-facing deployment |
| Sierra | AI Engineer | Agent orchestration, CRM integration, real customer workflows |
| Decagon | AI Engineer | Production AI system, Supabase, FastAPI, eval loops |
| brand.ai | GTM Engineer | Clay + SignalOS demo, n8n, Python, LLM workflows |
| Glean | GTM Engineer | Clay integration, signal detection, pipeline automation |
