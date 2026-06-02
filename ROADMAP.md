# SignalOS — Roadmap

Forward-looking only. Past changes → [`CHANGELOG.md`](CHANGELOG.md).

**Status: June 1, 2026** — 90/90 tests passing. Core engine production-ready.

---

## Remaining (in order)

### Phase B — Multi-LLM Cost Breakdown
`model_costs: dict[str, float]` already exists on `ScoreResult`. Wire actual per-call costs from each model into the field on every run.

- `scorer/router.py` — `pre_filter()` returns cost; populate `model_costs["gpt-4o-mini"]`
- `scorer/scorer.py` — populate `model_costs["llama-3.3-70b-versatile"]` and `model_costs["llama-3.1-8b-instant"]`
- Slack ROI receipt — add per-model cost line

**Effort:** ~2 hours

---

### Phase C — pgvector RAG
`scorer/rag.py` is implemented. `store_embedding()` and `retrieve_similar()` exist. One blocker.

**Blocker:** Run `CREATE EXTENSION IF NOT EXISTS vector;` in Supabase SQL editor.

After that:
- Wire `retrieve_similar()` call into `score_company()` in `scorer/scorer.py`
- Inject top-5 similar past accounts + their outcomes into the scoring prompt

**Effort:** ~3 hours after extension is enabled

---

### Phase D — Deploy + Clay Table + Loom

This is the job application deliverable. Everything else exists.

1. **Public endpoint** — `ngrok http 8000` (no Railway needed for demo)
2. **Clay Custom HTTP column** — new table with real companies, one Custom HTTP column calling `/score-company`. Map `score`, `confidence`, `aha_moment`, `email_opener`, `contact_window` as output columns.
3. **Numbers to capture for Loom narration** — cost per company (`cost_usd`), cache hit rate, API response time under 3 seconds
4. **SignalOS Loom** — 3–4 min. Show Clay table → Custom HTTP column wired to SignalOS → one row running live → Slack alert firing. This is the single missing artifact.

**Effort:** ~1 day

---

## Known Issues (unfixed, tracked here as single source of truth)

| Priority | Issue | File |
|---|---|---|
| High | Blocking I/O in `score_company()` — signal detection and enrichment block the FastAPI event loop. Fix: `asyncio.to_thread` or full async rewrite | `scorer/scorer.py` |
| Medium | N+1 Supabase queries — cache check + cooldown = 2 SELECT per request; combine into one | `api/main.py` |
| Medium | Global mutable `_client` / `_langfuse` not thread-safe under concurrent workers | `scorer/scorer.py`, `router.py` |
| Medium | Webhook auth silently skipped when `WEBHOOK_SECRET` not set — log warning on startup | `api/main.py` |
| Low | `/health` returns `"model": "claude-sonnet-4-6"` — stale string, actual model is Groq | `api/main.py:158` |

---

## Job Application Targets (June 1, 2026)

Founding GTM Engineer roles at small well-funded AI startups (seed–Series B). Global-remote-open or visa-sponsoring. Low applicant volume.

**Primary board:** [community.clay.com/x/full-time-jobs](https://community.clay.com/x/full-time-jobs)

**Not targeting:** Anthropic, OpenAI, or other large AI labs — visa problem + high applicant volume.

---

## Deliberately Out of Scope

- Email execution layer (Instantly / Smartlead) — needed for consulting, not job applications. Defer to first client.
- Multi-tenancy / billing / auth — portfolio piece, not a SaaS yet.
- Indian government API integration — only relevant for India-market customers. Defer.
