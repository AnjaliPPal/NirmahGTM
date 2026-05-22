import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scorer.scorer import score_company
from scorer.models import CompanyInput, ScoreResult, Signals, EnrichmentData, CRMResult
from scorer.crm import push_to_hubspot
from api.deps import get_supabase
import httpx

app = FastAPI(
    title="SignalOS",
    description="GTM signal intelligence — detect buying intent, score with Claude",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE_DAYS = int(os.environ.get("CACHE_DAYS", "14"))


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

    Cache: returns cached result if same domain+client scored within CACHE_DAYS (default 14).
    Quarantine: low-confidence leads route to #human-review-required, not main Slack.
    """
    # ── Domain validation: catch typos before burning tokens ─────────────────
    try:
        r = httpx.head(f"https://{company.domain}", timeout=5, follow_redirects=True)
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
        print(f"[WARN] Cache check failed: {e}")

    # ── Cooldown: suppress re-alerting the same domain within 45 days ────────
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
        print(f"[WARN] Cooldown check failed: {e}")

    # ── Cache miss — score fresh ───────────────────────────────────────────
    result = score_company(company)

    try:
        supabase = get_supabase()
        supabase.table("signals").insert(result.model_dump()).execute()
    except Exception as e:
        print(f"[WARN] Supabase insert failed: {e}")

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
        "model": "claude-sonnet-4-6",
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
