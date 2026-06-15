import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from scorer.scorer import score_company
from scorer.models import CompanyInput, ScoreResult, Signals, EnrichmentData, CRMResult, EvalOutcome, EvalReport, BatchScoreRequest, BatchScoreResult, ReplyClassifyRequest, ReplyClassifyResult
from scorer.crm import push_to_hubspot
from api.deps import get_supabase
import httpx

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

_FAILED_INSERTS_PATH = Path(__file__).parent.parent / "failed_inserts.jsonl"

app = FastAPI(
    title="SignalOS",
    description="GTM signal intelligence — detect buying intent, score with Claude",
    version="1.2.0",
)

_CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Signalos-Webhook-Secret"],
)

_CACHE_DAYS = int(os.environ.get("CACHE_DAYS", "28"))


def _rehydrate(row: dict) -> ScoreResult:
    """Reconstruct ScoreResult from a raw Supabase row (JSONB fields are plain dicts)."""
    if isinstance(row.get("signals"), dict):
        row["signals"] = Signals(**row["signals"])
    if isinstance(row.get("enrichment"), dict):
        row["enrichment"] = EnrichmentData(**row["enrichment"])
    return ScoreResult(**row)


@app.post("/score-company", response_model=ScoreResult)
async def score(company: CompanyInput):
    """
    Score a company's buying intent.

    Cache: returns cached result if same domain+client scored within CACHE_DAYS (default 28).
    Quarantine: low-confidence leads route to #human-review-required, not main Slack.
    """
    # ── Domain validation: catch typos before burning tokens ─────────────────
    try:
        async with httpx.AsyncClient() as client:
            r = await client.head(f"https://{company.domain}", timeout=5, follow_redirects=True)
        if r.status_code >= 400:
            return ScoreResult(
                company_name=company.company_name,
                domain=company.domain,
                client_id=company.client_id,
                signals=company.signals or Signals(),
                error=f"domain unreachable: {company.domain} (HTTP {r.status_code})",
            )
    except Exception:
        return ScoreResult(
            company_name=company.company_name,
            domain=company.domain,
            client_id=company.client_id,
            signals=company.signals or Signals(),
            error=f"domain unreachable: {company.domain}",
        )

    # ── Cache check: avoid burning Claude credits on recently-scored companies ──
    try:
        supabase = get_supabase()
        cutoff = (datetime.utcnow() - timedelta(days=_CACHE_DAYS)).isoformat()
        cached = (
            supabase.table("signals")
            .select("*")
            .eq("domain", company.domain)
            .eq("client_id", company.client_id)
            .eq("scored", True)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if cached.data:
            result = _rehydrate(cached.data[0])
            result.cached = True
            return result
    except Exception as e:
        logger.warning("Cache check failed for %s: %s", company.domain, e)

    # ── Cooldown: suppress re-alerting the same domain within 45 days ────────
    supabase = None
    try:
        supabase = get_supabase()
        cutoff_45d = (datetime.utcnow() - timedelta(days=45)).isoformat()
        recent = (
            supabase.table("signals")
            .select("created_at")
            .eq("domain", company.domain)
            .eq("client_id", company.client_id)
            .eq("alerted_slack", True)
            .gte("created_at", cutoff_45d)
            .limit(1)
            .execute()
        )
        if recent.data:
            return ScoreResult(
                company_name=company.company_name,
                domain=company.domain,
                client_id=company.client_id,
                signals=company.signals or Signals(),
                suppressed=True,
                suppression_reason=f"alerted within last 45 days (last: {recent.data[0]['created_at'][:10]})",
            )
    except Exception as e:
        logger.warning("Cooldown check failed for %s: %s", company.domain, e)

    # ── Cache miss — score fresh ───────────────────────────────────────────
    # score_company is synchronous and does blocking network I/O (signal
    # detection, enrichment, LLM calls). Run it off the event loop so it
    # doesn't stall concurrent requests.
    result = await asyncio.to_thread(score_company, company, supabase=supabase)

    try:
        supabase = get_supabase()
        supabase.table("signals").insert(result.model_dump()).execute()
        result.db_persisted = True
    except Exception as e:
        logger.error("Supabase insert failed for %s: %s — writing local backup", company.domain, e)
        try:
            with _FAILED_INSERTS_PATH.open("a") as f:
                f.write(json.dumps(result.model_dump()) + "\n")
        except Exception as backup_err:
            logger.critical("BOTH Supabase AND local backup failed for %s: %s", company.domain, backup_err)

    return result


@app.get("/health")
async def health():
    try:
        supabase = get_supabase()
        supabase.table("signals").select("id").limit(1).execute()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {
        "status": "ok",
        "model": "llama-3.3-70b-versatile",
        "version": "1.2.0",
        "score_threshold": int(os.environ.get("SCORE_THRESHOLD", "6")),
        "confidence_threshold": int(os.environ.get("CONFIDENCE_THRESHOLD", "80")),
        "cache_days": _CACHE_DAYS,
        "deal_acv": float(os.environ.get("DEAL_ACV", "45000")),
        "db": db_status,
    }


@app.get("/leads/{client_id}")
async def get_leads(client_id: str, min_score: int = 6, limit: int = 10):
    """Return hot leads for a client, sorted by score descending. Excludes quarantined leads."""
    try:
        supabase = get_supabase()
        response = (
            supabase.table("signals")
            .select("*")
            .eq("client_id", client_id)
            .gte("score", min_score)
            .eq("requires_human_review", False)
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )
        return {"client_id": client_id, "leads": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/push-to-crm")
async def push_to_crm(domain: str, client_id: str) -> CRMResult:
    """
    Manually push a lead to HubSpot CRM.

    Use this for:
    - Quarantined leads that a human has reviewed and approved
    - Cached results that were scored before HubSpot was connected

    Fetches the latest score for domain+client from Supabase, then pushes.
    """
    try:
        supabase  = get_supabase()
        response  = (
            supabase.table("signals")
            .select("*")
            .eq("domain", domain)
            .eq("client_id", client_id)
            .eq("scored", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail=f"No scored lead found for {domain} / {client_id}")

        result = _rehydrate(response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    crm = push_to_hubspot(result)

    if crm.pushed:
        try:
            supabase = get_supabase()
            supabase.table("signals").update({
                "pushed_to_crm":      True,
                "hubspot_contact_id": crm.contact_id,
                "hubspot_deal_id":    crm.deal_id,
            }).eq("domain", domain).eq("client_id", client_id).execute()
        except Exception as e:
            print(f"[WARN] Supabase CRM update failed: {e}")

    return crm


@app.get("/review-queue/{client_id}")
async def get_review_queue(client_id: str, limit: int = 20):
    """Return leads quarantined for human review (low confidence)."""
    try:
        supabase = get_supabase()
        response = (
            supabase.table("signals")
            .select("*")
            .eq("client_id", client_id)
            .eq("requires_human_review", True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"client_id": client_id, "queue": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
_ADMIN_API_KEY  = os.environ.get("ADMIN_API_KEY", "")


@app.post("/webhook/hubspot-reply")
async def hubspot_reply_webhook(
    outcome: EvalOutcome,
    x_signalos_webhook_secret: str = Header(default=""),
):
    """
    Record what happened after a lead was scored — replied, closed, no_reply, bounced.

    Call this from HubSpot workflows when a deal stage changes or a rep marks a reply.
    Powers the /eval-report accuracy story: "v2.0 prompts had 78% reply rate."

    Auth: set X-Signalos-Webhook-Secret header in your HubSpot workflow to match
    the WEBHOOK_SECRET env var.
    """
    if not _WEBHOOK_SECRET or x_signalos_webhook_secret != _WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret — set WEBHOOK_SECRET env var")

    try:
        supabase = get_supabase()

        # Find the most recent signal for this domain+client so we can link it
        sig_resp = (
            supabase.table("signals")
            .select("id, score, confidence, prompt_version")
            .eq("domain", outcome.domain)
            .eq("client_id", outcome.client_id)
            .eq("scored", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        signal_row = sig_resp.data[0] if sig_resp.data else {}

        row = {
            "domain":              outcome.domain,
            "client_id":           outcome.client_id,
            "outcome":             outcome.outcome,
            "hubspot_deal_id":     outcome.hubspot_deal_id,
            "days_to_outcome":     outcome.days_to_outcome,
            "signal_id":           signal_row.get("id"),
            "score":               signal_row.get("score"),
            "confidence":          signal_row.get("confidence"),
            "prompt_version":      signal_row.get("prompt_version"),
        }
        supabase.table("eval_outcomes").insert(row).execute()
        return {"recorded": True, "domain": outcome.domain, "outcome": outcome.outcome}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/eval-report/{client_id}")
async def eval_report(client_id: str):
    """
    Return reply/close rates broken down by prompt_version.

    Example output: "v2.0 → 78% reply rate, 45% close rate across 89 leads"
    Use this to prove your prompts improved over time.
    """
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("eval_outcomes")
            .select("prompt_version, outcome, score")
            .eq("client_id", client_id)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Group by prompt_version in Python (Supabase free tier has no GROUP BY via SDK)
    from collections import defaultdict
    buckets: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        version = row.get("prompt_version") or "unknown"
        buckets[version].append(row.get("outcome", "no_reply"))

    reports = []
    for version, outcomes in sorted(buckets.items()):
        total   = len(outcomes)
        replied = outcomes.count("replied")
        closed  = outcomes.count("closed")
        reports.append(EvalReport(
            client_id=client_id,
            prompt_version=version,
            total=total,
            replied=replied,
            closed=closed,
            no_reply=outcomes.count("no_reply"),
            bounced=outcomes.count("bounced"),
            reply_rate=round(replied / total, 3) if total else 0.0,
            close_rate=round(closed / total, 3) if total else 0.0,
        ))

    return {"client_id": client_id, "versions": [r.model_dump() for r in reports], "total_outcomes": len(rows)}


@app.post("/batch-score", response_model=BatchScoreResult)
async def batch_score(req: BatchScoreRequest):
    """
    Score multiple companies in parallel using the LangGraph fan-out agent.

    Accepts up to 50 companies. Each is scored concurrently; results are ranked
    by score and Claude synthesizes a VP-of-Sales-ready executive brief.

    Requires: pip install langgraph>=0.2.0
    """
    if len(req.companies) > 50:
        raise HTTPException(status_code=400, detail="max 50 companies per batch request")

    try:
        from scorer.agent import run_batch
    except ImportError:
        raise HTTPException(status_code=503, detail="LangGraph not installed. Run: pip install langgraph>=0.2.0")

    try:
        result = await asyncio.to_thread(run_batch, req.companies, req.min_score)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return BatchScoreResult(
        total_scored=result["total_scored"],
        hot_leads_count=result["hot_leads_count"],
        ranked=result["ranked"],
        summary=result["summary"],
    )


@app.post("/classify-reply", response_model=ReplyClassifyResult)
async def classify_reply(req: ReplyClassifyRequest):
    """
    Classify an inbound email reply and return routing decision.

    Labels: hot / warm / not_now / not_interested / out_of_office / bounce
    Routing: human / nurture / suppress / auto-reply

    - hot      → human      (forward to rep immediately)
    - warm     → nurture    (add to follow-up sequence)
    - not_now  → nurture    (retry in 30-60 days)
    - not_interested → suppress   (remove from sequence)
    - out_of_office  → auto-reply (retry when they return)
    - bounce         → suppress   (invalid address, update contact data)
    """
    from scorer.router import classify_reply as _classify
    result = await asyncio.to_thread(_classify, req.reply_text, req.context)
    return ReplyClassifyResult(**result)


@app.get("/admin/failed-inserts")
async def get_failed_inserts(x_admin_key: str = Header(default="")):
    """
    Return any Supabase inserts that failed and were written to the local backup file.
    Use this to replay missed writes manually after fixing the DB connection.

    Auth: set X-Admin-Key header to match the ADMIN_API_KEY env var.
    """
    if not _ADMIN_API_KEY or x_admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key — set ADMIN_API_KEY env var")

    if not _FAILED_INSERTS_PATH.exists():
        return {"count": 0, "records": []}
    try:
        records = []
        with _FAILED_INSERTS_PATH.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return {"count": len(records), "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
