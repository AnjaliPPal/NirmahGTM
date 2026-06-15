import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app
from scorer.router import classify_reply, _LABEL_TO_ROUTING, _VALID_LABELS

client = TestClient(app)


def _mock_groq_response(label: str, reason: str, confidence: int):
    """Build a mock Groq completion response returning the given classification JSON."""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({
        "label": label,
        "reason": reason,
        "confidence": confidence,
    })
    return mock_resp


# ── Unit tests: classify_reply() function ────────────────────────────────────

class TestClassifyReplyFunction:

    def test_hot_reply_routes_to_human(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("hot", "Prospect asked to book a call", 92)
            result = classify_reply("Yes, this sounds interesting! Can we connect Thursday?")
        assert result["label"] == "hot"
        assert result["routing"] == "human"
        assert result["confidence"] == 92

    def test_out_of_office_routes_to_auto_reply(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("out_of_office", "Standard OOO auto-reply", 98)
            result = classify_reply("I'm out of office until June 10. I'll respond when I return.")
        assert result["label"] == "out_of_office"
        assert result["routing"] == "auto-reply"

    def test_not_interested_routes_to_suppress(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("not_interested", "Flat rejection", 95)
            result = classify_reply("Not interested, please remove me from your list.")
        assert result["label"] == "not_interested"
        assert result["routing"] == "suppress"

    def test_not_now_routes_to_nurture(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("not_now", "Timing objection — Q4 mentioned", 88)
            result = classify_reply("We're heads down until Q4, reach out then.")
        assert result["label"] == "not_now"
        assert result["routing"] == "nurture"

    def test_bounce_routes_to_suppress(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("bounce", "Hard bounce — address does not exist", 99)
            result = classify_reply("550 5.1.1 The email account does not exist.")
        assert result["label"] == "bounce"
        assert result["routing"] == "suppress"

    def test_warm_routes_to_nurture(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("warm", "Curious but not committing", 70)
            result = classify_reply("Can you send me more info on how this works?")
        assert result["label"] == "warm"
        assert result["routing"] == "nurture"

    def test_invalid_label_from_llm_defaults_to_not_interested(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("garbage_label", "some reason", 60)
            result = classify_reply("Some ambiguous reply")
        assert result["label"] == "not_interested"
        assert result["label"] in _VALID_LABELS

    def test_llm_failure_falls_back_to_rule_based_ooo(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.side_effect = Exception("Groq timeout")
            result = classify_reply("I'm out of office until next week")
        assert result["label"] == "out_of_office"
        assert result["routing"] == "auto-reply"

    def test_llm_failure_falls_back_to_rule_based_not_interested(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.side_effect = Exception("Groq timeout")
            result = classify_reply("Please unsubscribe me from this list")
        assert result["label"] == "not_interested"
        assert result["routing"] == "suppress"

    def test_context_is_passed_to_prompt(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("hot", "Interested", 90)
            classify_reply("Yes, let's talk", context="Outreach for Instantly.ai email platform")
            call_args = mock_groq.return_value.chat.completions.create.call_args
            prompt = call_args[1]["messages"][0]["content"]
        assert "Instantly.ai" in prompt

    def test_all_valid_labels_have_routing(self):
        for label in _VALID_LABELS:
            assert label in _LABEL_TO_ROUTING, f"Missing routing for label: {label}"

    def test_result_always_has_required_fields(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("hot", "Interested", 85)
            result = classify_reply("Yes I'm interested")
        assert "label" in result
        assert "reason" in result
        assert "routing" in result
        assert "confidence" in result


# ── Integration tests: POST /classify-reply endpoint ─────────────────────────

class TestClassifyReplyEndpoint:

    def test_endpoint_returns_200_hot(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("hot", "Wants to connect", 91)
            resp = client.post("/classify-reply", json={
                "reply_text": "Yes this looks great, let's connect Thursday at 2pm?"
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "hot"
        assert data["routing"] == "human"
        assert 0 <= data["confidence"] <= 100
        assert isinstance(data["reason"], str)

    def test_endpoint_returns_200_ooo(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("out_of_office", "OOO message", 97)
            resp = client.post("/classify-reply", json={
                "reply_text": "I am out of office until June 15. For urgent matters contact support@company.com"
            })
        assert resp.status_code == 200
        assert resp.json()["label"] == "out_of_office"
        assert resp.json()["routing"] == "auto-reply"

    def test_endpoint_with_context(self):
        with patch("scorer.router._get_groq_opener") as mock_groq:
            mock_groq.return_value.chat.completions.create.return_value = \
                _mock_groq_response("not_now", "Q4 timing objection", 88)
            resp = client.post("/classify-reply", json={
                "reply_text": "Not the right time, maybe check back in Q4",
                "context": "Outreach for Instantly.ai cold email platform"
            })
        assert resp.status_code == 200
        assert resp.json()["label"] == "not_now"
        assert resp.json()["routing"] == "nurture"

    def test_endpoint_rejects_empty_reply(self):
        resp = client.post("/classify-reply", json={"reply_text": ""})
        assert resp.status_code == 422

    def test_endpoint_rejects_missing_reply(self):
        resp = client.post("/classify-reply", json={})
        assert resp.status_code == 422
