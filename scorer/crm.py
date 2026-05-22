"""
HubSpot CRM integration — push hot leads as contacts + deals.

Requires: HUBSPOT_ACCESS_TOKEN (private app token, HubSpot developer portal → Apps → Private Apps)
Free CRM: unlimited contacts/deals on HubSpot free tier.

Flow: upsert contact by email → create deal → associate contact ↔ deal
"""
import os
import requests
from .models import ScoreResult, CRMResult

_BASE        = "https://api.hubapi.com"
_DEAL_STAGE  = "appointmentscheduled"   # first stage in HubSpot default pipeline
_DEAL_PIPE   = "default"


def _headers() -> dict:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _upsert_contact(result: ScoreResult, hdrs: dict) -> str | None:
    """Create contact; on 409 (email exists) fetch the existing ID instead."""
    if not result.enrichment or not result.enrichment.decision_maker_email:
        return None

    email = result.enrichment.decision_maker_email
    name_parts = (result.enrichment.decision_maker_name or "").split(" ", 1)

    r = requests.post(
        f"{_BASE}/crm/v3/objects/contacts",
        json={
            "properties": {
                "email":          email,
                "firstname":      name_parts[0] if name_parts else "",
                "lastname":       name_parts[1] if len(name_parts) > 1 else "",
                "company":        result.company_name,
                "jobtitle":       result.enrichment.decision_maker_title or "",
                "website":        result.domain,
                "hs_lead_status": "NEW",
            }
        },
        headers=hdrs,
        timeout=10,
    )

    if r.status_code == 201:
        return r.json()["id"]

    if r.status_code == 409:
        # Email already exists — look up existing contact
        search = requests.post(
            f"{_BASE}/crm/v3/objects/contacts/search",
            json={
                "filterGroups": [
                    {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                ],
                "properties": ["email"],
                "limit": 1,
            },
            headers=hdrs,
            timeout=10,
        )
        search.raise_for_status()
        rows = search.json().get("results", [])
        return rows[0]["id"] if rows else None

    r.raise_for_status()
    return None


def _create_deal(result: ScoreResult, hdrs: dict) -> str:
    """Create a deal scoped to this signal and return its ID."""
    r = requests.post(
        f"{_BASE}/crm/v3/objects/deals",
        json={
            "properties": {
                "dealname":   f"SignalOS: {result.company_name} — {result.top_signal}",
                "dealstage":  _DEAL_STAGE,
                "pipeline":   _DEAL_PIPE,
                "amount":     str(int(result.pipeline_value_usd)) if result.pipeline_value_usd else "",
                "description": result.aha_moment or result.reasoning or "",
            }
        },
        headers=hdrs,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def _associate(contact_id: str, deal_id: str, hdrs: dict) -> None:
    r = requests.post(
        f"{_BASE}/crm/v3/associations/contacts/deals/batch/create",
        json={"inputs": [{"from": {"id": contact_id}, "to": {"id": deal_id}, "type": "contact_to_deal"}]},
        headers=hdrs,
        timeout=10,
    )
    r.raise_for_status()


def push_to_hubspot(result: ScoreResult) -> CRMResult:
    """Push a scored lead to HubSpot. Never raises — returns CRMResult with error on failure."""
    if not os.environ.get("HUBSPOT_ACCESS_TOKEN"):
        return CRMResult(pushed=False, error="HUBSPOT_ACCESS_TOKEN not set")

    hdrs = _headers()
    try:
        contact_id = _upsert_contact(result, hdrs)
        deal_id    = _create_deal(result, hdrs)

        if contact_id:
            _associate(contact_id, deal_id, hdrs)

        return CRMResult(pushed=True, contact_id=contact_id, deal_id=deal_id)

    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        return CRMResult(pushed=False, error=f"HubSpot {e.response.status_code}: {body}")
    except Exception as e:
        return CRMResult(pushed=False, error=str(e))
