import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from scorer.models import ScoreResult, Signals


def _mock_async_client(status_code: int = 200):
    """Return a mock that works with `async with httpx.AsyncClient() as client: await client.head(...)`"""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_client = MagicMock()
    mock_client.head = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client

SAMPLE_PAYLOAD = {
    "company_name": "Acme Corp",
    "domain": "acme.com",
    "client_id": "test-client",
    "signals": {
        "funded_90d": True,
        "hiring_gtm": True,
        "growth_pct": 45.0,
        "tech_stack": ["Salesforce", "Outreach"],
    },
}


def _mock_score_result() -> ScoreResult:
    return ScoreResult(
        company_name="Acme Corp",
        domain="acme.com",
        client_id="test-client",
        signals=Signals(funded_90d=True, hiring_gtm=True, growth_pct=45.0, tech_stack=["Salesforce"]),
        score=8,
        reasoning="Funding + GTM hiring firing simultaneously",
        top_signal="funded_90d",
        contact_window="now",
        aha_moment="Just closed funding and actively hiring 3+ GTM roles. Outbound rebuild underway.",
        email_opener="Acme just closed a round — your outbound stack needs to scale.",
        alerted_slack=True,
        cost_usd=0.001234,
        scored=True,
    )


@patch("api.main.httpx.AsyncClient")
@patch("api.main.get_supabase")
@patch("api.main.score_company")
def test_score_company_endpoint(mock_score, mock_supabase, mock_async_client_cls):
    mock_score.return_value = _mock_score_result()
    mock_async_client_cls.return_value = _mock_async_client(200)

    # Both cache and cooldown checks must return empty data so scoring runs
    mock_empty = MagicMock()
    mock_empty.data = []
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_empty
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = mock_empty
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.post("/score-company", json=SAMPLE_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 8
    assert data["alerted_slack"] is True
    assert data["aha_moment"] is not None
    assert data["email_opener"] is not None


def test_health_endpoint():
    from api.main import app
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model"] == "claude-sonnet-4-6"


@patch("api.main.httpx.AsyncClient")
@patch("api.main.get_supabase")
@patch("api.main.score_company")
def test_supabase_failure_does_not_fail_request(mock_score, mock_supabase, mock_async_client_cls):
    mock_score.return_value = _mock_score_result()
    mock_async_client_cls.return_value = _mock_async_client(200)
    mock_supabase.side_effect = Exception("DB down")

    from api.main import app
    client = TestClient(app)
    response = client.post("/score-company", json=SAMPLE_PAYLOAD)

    assert response.status_code == 200


# ── /webhook/hubspot-reply ────────────────────────────────────────────────────

EVAL_OUTCOME_PAYLOAD = {
    "domain": "acme.com",
    "client_id": "test-client",
    "outcome": "replied",
    "hubspot_deal_id": "deal-123",
    "days_to_outcome": 7,
}


@patch("api.main.get_supabase")
def test_webhook_records_outcome(mock_supabase, monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "_WEBHOOK_SECRET", "test-secret")

    mock_sb = MagicMock()
    mock_sig = MagicMock()
    mock_sig.data = [{"id": "sig-1", "score": 8, "confidence": 85, "prompt_version": "v2.0"}]
    mock_insert = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_sig
    mock_sb.table.return_value.insert.return_value.execute.return_value = mock_insert
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.post(
        "/webhook/hubspot-reply",
        json=EVAL_OUTCOME_PAYLOAD,
        headers={"X-Signalos-Webhook-Secret": "test-secret"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recorded"] is True
    assert data["outcome"] == "replied"


@patch("api.main.get_supabase")
def test_webhook_rejects_invalid_secret(mock_supabase, monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "_WEBHOOK_SECRET", "secret123")

    from api.main import app
    client = TestClient(app)
    response = client.post(
        "/webhook/hubspot-reply",
        json=EVAL_OUTCOME_PAYLOAD,
        headers={"X-Signalos-Webhook-Secret": "wrong"},
    )
    assert response.status_code == 401


@patch("api.main.get_supabase")
def test_webhook_accepts_correct_secret(mock_supabase, monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "_WEBHOOK_SECRET", "secret123")

    mock_sb = MagicMock()
    mock_sig = MagicMock()
    mock_sig.data = []
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_sig
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock()
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.post(
        "/webhook/hubspot-reply",
        json=EVAL_OUTCOME_PAYLOAD,
        headers={"X-Signalos-Webhook-Secret": "secret123"},
    )
    assert response.status_code == 200


# ── /eval-report/{client_id} ──────────────────────────────────────────────────

@patch("api.main.get_supabase")
def test_eval_report_computes_rates(mock_supabase):
    mock_sb = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [
        {"prompt_version": "v2.0", "outcome": "replied", "score": 8},
        {"prompt_version": "v2.0", "outcome": "replied", "score": 9},
        {"prompt_version": "v2.0", "outcome": "no_reply", "score": 6},
        {"prompt_version": "v2.0", "outcome": "closed", "score": 9},
    ]
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.get("/eval-report/test-client")

    assert response.status_code == 200
    data = response.json()
    assert data["total_outcomes"] == 4
    version = data["versions"][0]
    assert version["prompt_version"] == "v2.0"
    assert version["total"] == 4
    assert version["replied"] == 2
    assert version["reply_rate"] == 0.5


@patch("api.main.get_supabase")
def test_eval_report_empty_returns_empty_versions(mock_supabase):
    mock_sb = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = []
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.get("/eval-report/new-client")

    assert response.status_code == 200
    data = response.json()
    assert data["total_outcomes"] == 0
    assert data["versions"] == []


# ── /admin/failed-inserts ─────────────────────────────────────────────────────

def test_admin_failed_inserts_no_file(tmp_path, monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "_FAILED_INSERTS_PATH", tmp_path / "nonexistent.jsonl")
    monkeypatch.setattr(main_module, "_ADMIN_API_KEY", "test-admin-key")

    from api.main import app
    client = TestClient(app)
    response = client.get("/admin/failed-inserts", headers={"X-Admin-Key": "test-admin-key"})

    assert response.status_code == 200
    assert response.json() == {"count": 0, "records": []}


def test_admin_failed_inserts_returns_records(tmp_path, monkeypatch):
    import api.main as main_module
    path = tmp_path / "failed_inserts.jsonl"
    path.write_text('{"domain":"bad.com","error":"timeout"}\n{"domain":"other.com","error":"500"}\n')
    monkeypatch.setattr(main_module, "_FAILED_INSERTS_PATH", path)
    monkeypatch.setattr(main_module, "_ADMIN_API_KEY", "test-admin-key")

    from api.main import app
    client = TestClient(app)
    response = client.get("/admin/failed-inserts", headers={"X-Admin-Key": "test-admin-key"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["records"][0]["domain"] == "bad.com"


def test_admin_failed_inserts_rejects_wrong_key(monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "_ADMIN_API_KEY", "secret")

    from api.main import app
    client = TestClient(app)
    response = client.get("/admin/failed-inserts", headers={"X-Admin-Key": "wrong"})

    assert response.status_code == 403
