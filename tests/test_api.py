import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from scorer.models import ScoreResult, Signals

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


@patch("api.main.httpx.head")
@patch("api.main.get_supabase")
@patch("api.main.score_company")
def test_score_company_endpoint(mock_score, mock_supabase, mock_head):
    mock_score.return_value = _mock_score_result()
    mock_head.return_value = MagicMock(status_code=200)

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


@patch("api.main.httpx.head")
@patch("api.main.get_supabase")
@patch("api.main.score_company")
def test_supabase_failure_does_not_fail_request(mock_score, mock_supabase, mock_head):
    mock_score.return_value = _mock_score_result()
    mock_head.return_value = MagicMock(status_code=200)
    mock_supabase.side_effect = Exception("DB down")

    from api.main import app
    client = TestClient(app)
    response = client.post("/score-company", json=SAMPLE_PAYLOAD)

    assert response.status_code == 200
