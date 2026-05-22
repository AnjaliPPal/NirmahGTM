"""Tests for scorer/crm.py — HubSpot push logic."""
import pytest
import responses as rsps_lib
import responses
from unittest.mock import patch

from scorer.crm import push_to_hubspot, _BASE
from scorer.models import ScoreResult, Signals, EnrichmentData


def _result(**kwargs) -> ScoreResult:
    defaults = dict(
        company_name="Acme Corp",
        domain="acme.com",
        client_id="test",
        signals=Signals(funded_90d=True, hiring_gtm=True),
        enrichment=EnrichmentData(
            decision_maker_name="Sarah Jenkins",
            decision_maker_title="VP Sales",
            decision_maker_email="sarah@acme.com",
            enriched=True,
        ),
        score=9,
        confidence=92,
        top_signal="funded_90d",
        contact_window="now",
        aha_moment="Closed Series B, hired VP Sales last week.",
        pipeline_value_usd=45000.0,
        scored=True,
    )
    defaults.update(kwargs)
    return ScoreResult(**defaults)


# ── No token ──────────────────────────────────────────────────────────────────

def test_push_no_token():
    with patch.dict("os.environ", {}, clear=True):
        r = push_to_hubspot(_result())
    assert r.pushed is False
    assert "HUBSPOT_ACCESS_TOKEN" in r.error


# ── Successful push ───────────────────────────────────────────────────────────

@responses.activate
def test_push_success():
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/contacts",  json={"id": "c-001"}, status=201)
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/deals",     json={"id": "d-001"}, status=201)
    responses.add(responses.POST, f"{_BASE}/crm/v3/associations/contacts/deals/batch/create", json={}, status=200)

    with patch.dict("os.environ", {"HUBSPOT_ACCESS_TOKEN": "pat-test"}):
        r = push_to_hubspot(_result())

    assert r.pushed is True
    assert r.contact_id == "c-001"
    assert r.deal_id    == "d-001"
    assert r.error is None


# ── Contact already exists (409) → search fallback ───────────────────────────

@responses.activate
def test_push_contact_exists_409():
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/contacts", json={"message": "Contact already exists"}, status=409)
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/contacts/search", json={"results": [{"id": "c-existing"}]}, status=200)
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/deals",    json={"id": "d-002"}, status=201)
    responses.add(responses.POST, f"{_BASE}/crm/v3/associations/contacts/deals/batch/create", json={}, status=200)

    with patch.dict("os.environ", {"HUBSPOT_ACCESS_TOKEN": "pat-test"}):
        r = push_to_hubspot(_result())

    assert r.pushed      is True
    assert r.contact_id  == "c-existing"
    assert r.deal_id     == "d-002"


# ── No enrichment email → contact skipped, deal still created ─────────────────

@responses.activate
def test_push_no_email_skips_contact():
    result = _result(enrichment=EnrichmentData(enriched=False))
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/deals", json={"id": "d-003"}, status=201)
    # No association call expected (no contact_id)

    with patch.dict("os.environ", {"HUBSPOT_ACCESS_TOKEN": "pat-test"}):
        r = push_to_hubspot(result)

    assert r.pushed     is True
    assert r.contact_id is None
    assert r.deal_id    == "d-003"


# ── HubSpot API error → returns CRMResult with error, never raises ────────────

@responses.activate
def test_push_api_error_non_fatal():
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/contacts", json={"message": "Unauthorized"}, status=401)

    with patch.dict("os.environ", {"HUBSPOT_ACCESS_TOKEN": "bad-token"}):
        r = push_to_hubspot(_result())

    assert r.pushed is False
    assert "401" in r.error


# ── Deal name includes signal ─────────────────────────────────────────────────

@responses.activate
def test_deal_name_includes_signal():
    responses.add(responses.POST, f"{_BASE}/crm/v3/objects/contacts", json={"id": "c-001"}, status=201)
    deal_response = responses.add(responses.POST, f"{_BASE}/crm/v3/objects/deals", json={"id": "d-001"}, status=201)
    responses.add(responses.POST, f"{_BASE}/crm/v3/associations/contacts/deals/batch/create", json={}, status=200)

    with patch.dict("os.environ", {"HUBSPOT_ACCESS_TOKEN": "pat-test"}):
        push_to_hubspot(_result(top_signal="funded_90d"))

    body = responses.calls[1].request.body.decode()
    assert "funded_90d" in body
    assert "Acme Corp" in body
