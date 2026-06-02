import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _make_supabase_mock(insert_data=None, select_data=None):
    mock_sb = MagicMock()
    # insert chain
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=insert_data or [{}])
    # select chain for webhook (find signal)
    sig_result = MagicMock()
    sig_result.data = select_data or []
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = sig_result
    # select chain for eval-report (no filters)
    report_result = MagicMock()
    report_result.data = select_data or []
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = report_result
    return mock_sb


@patch("api.main._WEBHOOK_SECRET", "test-secret")
@patch("api.main.get_supabase")
def test_hubspot_reply_webhook(mock_supabase):
    mock_supabase.return_value = _make_supabase_mock(
        select_data=[{"id": "abc-123", "score": 8, "confidence": 85, "prompt_version": "v2.0"}]
    )

    from api.main import app
    client = TestClient(app)
    response = client.post(
        "/webhook/hubspot-reply",
        json={
            "domain": "acme.com",
            "client_id": "test-client",
            "outcome": "replied",
            "days_to_outcome": 3,
        },
        headers={"X-Signalos-Webhook-Secret": "test-secret"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recorded"] is True
    assert data["outcome"] == "replied"


@patch("api.main.get_supabase")
def test_hubspot_reply_webhook_invalid_outcome(mock_supabase):
    from api.main import app
    client = TestClient(app)
    response = client.post("/webhook/hubspot-reply", json={
        "domain": "acme.com",
        "client_id": "test-client",
        "outcome": "invalid_outcome",
    })
    assert response.status_code == 422


@patch("api.main.get_supabase")
def test_eval_report_empty(mock_supabase):
    mock_sb = MagicMock()
    empty_result = MagicMock()
    empty_result.data = []
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = empty_result
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.get("/eval-report/test-client")

    assert response.status_code == 200
    data = response.json()
    assert data["total_outcomes"] == 0
    assert data["versions"] == []


@patch("api.main.get_supabase")
def test_eval_report_with_outcomes(mock_supabase):
    mock_sb = MagicMock()
    outcomes_result = MagicMock()
    outcomes_result.data = [
        {"prompt_version": "v2.0", "outcome": "replied", "score": 8},
        {"prompt_version": "v2.0", "outcome": "replied", "score": 7},
        {"prompt_version": "v2.0", "outcome": "closed", "score": 9},
        {"prompt_version": "v2.0", "outcome": "no_reply", "score": 6},
        {"prompt_version": "v2.1", "outcome": "replied", "score": 8},
    ]
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = outcomes_result
    mock_supabase.return_value = mock_sb

    from api.main import app
    client = TestClient(app)
    response = client.get("/eval-report/test-client")

    assert response.status_code == 200
    data = response.json()
    assert data["total_outcomes"] == 5

    v20 = next(r for r in data["versions"] if r["prompt_version"] == "v2.0")
    assert v20["total"] == 4
    assert v20["replied"] == 2
    assert v20["closed"] == 1
    assert v20["reply_rate"] == 0.5
    assert v20["close_rate"] == 0.25
