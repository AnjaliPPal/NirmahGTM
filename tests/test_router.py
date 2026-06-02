"""
Tests for scorer/router.py — pre-filter and multi-LLM routing logic.
"""
from unittest.mock import patch, MagicMock
from scorer.router import pre_filter, generate_opener_gemini
from scorer.models import Signals


def _no_signals() -> Signals:
    return Signals()


def _rich_signals() -> Signals:
    return Signals(
        hiring_gtm=True,
        open_gtm_roles=5,
        funded_90d=True,
        funding_stage="Series B",
        new_exec_hire=True,
        new_exec_title="VP Sales",
        tech_stack=["Salesforce", "Outreach"],
        news_keywords=["expansion", "IPO"],
        intent_signals_count=3,
    )


# ── Rule-based path (no OpenAI key) ──────────────────────────────────────────

def test_pre_filter_no_signals_returns_false():
    with patch("scorer.router._get_openai", return_value=None):
        passed, reason, cost = pre_filter(_no_signals())
    assert passed is False
    assert "no signals" in reason
    assert cost == 0.0


def test_pre_filter_rich_signals_returns_true():
    with patch("scorer.router._get_openai", return_value=None):
        passed, reason, cost = pre_filter(_rich_signals())
    assert passed is True
    assert "signal" in reason
    assert cost == 0.0


def test_pre_filter_single_signal_returns_true():
    signals = Signals(hiring_gtm=True, open_gtm_roles=2)
    with patch("scorer.router._get_openai", return_value=None):
        passed, reason, cost = pre_filter(signals)
    assert passed is True


# ── GPT-4o-mini path ──────────────────────────────────────────────────────────

def test_pre_filter_gpt_yes():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="YES"))],
        usage=MagicMock(prompt_tokens=50, completion_tokens=1),
    )
    with patch("scorer.router._get_openai", return_value=mock_client):
        passed, reason, cost = pre_filter(_rich_signals())
    assert passed is True
    assert "gpt-4o-mini" in reason
    assert cost > 0


def test_pre_filter_gpt_no():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="NO"))],
        usage=MagicMock(prompt_tokens=30, completion_tokens=1),
    )
    with patch("scorer.router._get_openai", return_value=mock_client):
        passed, reason, cost = pre_filter(_no_signals())
    assert passed is False
    assert "gpt-4o-mini" in reason
    assert cost > 0


def test_pre_filter_fails_open_on_api_error():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("connection timeout")
    with patch("scorer.router._get_openai", return_value=mock_client):
        passed, reason, cost = pre_filter(_rich_signals())
    assert passed is True
    assert "fail open" in reason
    assert cost == 0.0


# ── Haiku opener ──────────────────────────────────────────────────────────────

def test_generate_opener_gemini_returns_text_and_cost():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="  Saw you hired a VP Sales — congrats!  "))]

    with patch("scorer.router._get_groq_opener") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        text, cost = generate_opener_gemini("Write a 1-line opener for Vercel")

    assert text == "Saw you hired a VP Sales — congrats!"
    assert cost == 0.0


def test_generate_opener_gemini_returns_none_on_error():
    with patch("scorer.router._get_groq_opener") as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = Exception("API error")
        text, cost = generate_opener_gemini("Write an opener")

    assert text is None
    assert cost == 0.0
