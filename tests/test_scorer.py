import pytest
from unittest.mock import patch, MagicMock
from scorer.models import CompanyInput, Signals, EnrichmentData
from scorer.scorer import score_company, _estimate_acv, _contact_window_from_date


def _make_company(**overrides) -> CompanyInput:
    defaults = dict(
        company_name="Acme Corp",
        domain="acme.com",
        client_id="test-client",
        signals=Signals(
            funded_90d=True,
            hiring_gtm=True,
            growth_pct=45.0,
            tech_stack=["Salesforce", "Outreach"],
        ),
    )
    defaults.update(overrides)
    return CompanyInput(**defaults)


def _mock_groq(text: str):
    """Groq-style response: choices[0].message.content holds the text."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


_NO_ENRICHMENT = EnrichmentData(enriched=False)
_ENRICHED = EnrichmentData(
    decision_maker_name="Jane Smith",
    decision_maker_title="VP Sales",
    decision_maker_email="jane@acme.com",
    employee_count=150,
    industry="Software",
    enriched=True,
)

SCORE_JSON = '{"score": 8, "confidence": 85, "reasoning": "Funding + GTM hiring fire simultaneously", "top_signal": "funded_90d", "contact_window": "now", "aha_moment": "Just closed funding and actively hiring 3+ GTM roles. Window is NOW.", "signal_scores": {"leadership_change": 0, "hiring": 8, "tech_stack": 6, "funding": 9, "hidden_intent": 2}, "pitch_block": "Acme closed a Series B 3 weeks ago and is rebuilding their entire GTM motion. Three open SDR roles and Outreach in the stack signal an outbound overhaul in progress. The new VP Sales will lock in their vendor stack in the first 90 days — that window is right now."}'
SCORE_JSON_LOW = '{"score": 3, "confidence": 60, "reasoning": "Single weak signal", "top_signal": "hiring_gtm", "contact_window": "not yet", "aha_moment": "Only hiring in general — not yet showing GTM urgency.", "signal_scores": {"leadership_change": 0, "hiring": 3, "tech_stack": 0, "funding": 0, "hidden_intent": 0}, "pitch_block": "Early signals only — not enough convergence yet to justify outreach."}'
OPENER_TEXT = "Acme closed a round — your SDR team is about to triple and needs a system."

_OPENER_COST = 0.000144


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_ENRICHED)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_high_score_fires_slack_with_enrichment(mock_client_fn, mock_opener, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON)

    result = score_company(_make_company())

    assert result.score == 8
    assert result.scored is True
    assert result.alerted_slack is True
    assert result.email_opener == OPENER_TEXT
    assert result.enrichment.decision_maker_email == "jane@acme.com"
    mock_slack.assert_called_once()


@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_low_score_no_slack_no_opener(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON_LOW)

    result = score_company(_make_company())

    assert result.score == 3
    assert result.alerted_slack is False
    assert result.email_opener is None
    assert result.aha_moment is not None  # even low scores get aha_moment
    mock_slack.assert_not_called()


@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_json_parse_failure_returns_error(mock_client_fn, mock_enrich):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq("not valid json")

    result = score_company(_make_company())

    assert result.scored is False
    assert "JSON parse failed" in result.error


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, _OPENER_COST))
@patch("scorer.scorer._get_client")
def test_cost_includes_opener_cost(mock_client_fn, mock_opener, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON)

    result = score_company(_make_company())

    # Groq scoring: 0.0 cost. Opener: mocked at _OPENER_COST
    assert result.cost_usd == pytest.approx(_OPENER_COST)


@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_uses_system_role_in_messages(mock_client_fn, mock_enrich):
    """Verify system role is present in messages list sent to Groq."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(
        '{"score": 3, "reasoning": "weak", "top_signal": "hiring_gtm", "contact_window": "not yet"}'
    )

    score_company(_make_company())

    # call_args_list[0] = scoring call (has system role); [1] = situation generation (user only)
    call_kwargs = mock_client.chat.completions.create.call_args_list[0].kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 50  # non-empty system prompt


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_pitch_block_populated_for_high_score(mock_client_fn, mock_opener, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON)

    result = score_company(_make_company())

    assert result.pitch_block is not None
    assert len(result.pitch_block) > 20
    assert result.signal_scores.get("funding") == 9
    assert result.signal_scores.get("hiring") == 8


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_ENRICHED)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_situation_built_from_signals(mock_client_fn, mock_opener, mock_enrich, mock_slack):
    """situation field is a non-empty paragraph combining all 5 signals."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    situation_text = (
        "Acme raised funding recently. Their CRM is Salesforce with no sales engagement tool. "
        "Three open GTM roles show they are actively building sales capacity into a gap."
    )
    talking_pts_text = "Salesforce in the stack but no Outreach means every sequence is manual.\nThree open SDR roles with no engagement tool signals a broken outbound motion."
    # Calls: (1) main scoring, (2) situation generation, (3) talking points
    mock_client.chat.completions.create.side_effect = [
        _mock_groq(SCORE_JSON),
        _mock_groq(situation_text),
        _mock_groq(talking_pts_text),
    ]

    result = score_company(_make_company())

    assert result.situation == situation_text
    assert len(result.situation) > 30


@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_signal_scores_present_even_for_low_score(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON_LOW)

    result = score_company(_make_company())

    assert result.score == 3
    assert result.signal_scores.get("hiring") == 3
    assert result.signal_scores.get("funding") == 0
    assert result.pitch_block is not None


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_talking_points_generated_for_high_score(mock_client_fn, mock_opener, mock_enrich, mock_slack):
    """High-score leads get 3-5 BDR talking point hooks in result.talking_points."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    talking_pts_text = (
        "Salesforce in the stack but no Outreach means every sequence is manual.\n"
        "Three open SDR roles with no engagement tool signals a broken outbound motion.\n"
        "Series B closed with board pressure to show pipeline in 90 days."
    )
    # Calls: (1) main scoring, (2) situation generation, (3) talking points
    mock_client.chat.completions.create.side_effect = [
        _mock_groq(SCORE_JSON),
        _mock_groq("Acme raised funding and is hiring GTM. Stack gap detected."),
        _mock_groq(talking_pts_text),
    ]

    result = score_company(_make_company())

    assert len(result.talking_points) >= 3
    assert all(isinstance(tp, str) and len(tp) > 10 for tp in result.talking_points)


@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_talking_points_empty_for_low_score(mock_client_fn, mock_enrich, mock_slack):
    """Low-score leads do not get talking points — no wasted LLM calls."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON_LOW)

    result = score_company(_make_company())

    assert result.talking_points == []


@patch("scorer.scorer.push_to_hubspot", return_value=MagicMock(pushed=False))
@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_scoring_context_appended_to_prompt(mock_client_fn, mock_opener, mock_enrich, mock_slack, mock_crm):
    """scoring_context from Clay enrichment is injected into the scoring prompt."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON)

    clay_context = "CMO hire date: 2026-01. Brand tool: Frontify. Rebrand: YES (Mar 2026)."
    company = _make_company(scoring_context=clay_context)
    score_company(company)

    # First call to Groq is the scoring call (system + user messages)
    # Later calls are _build_situation and _build_talking_points (user-only, 1 message each)
    first_call = mock_client.chat.completions.create.call_args_list[0]
    user_message = first_call[1]["messages"][1]["content"]
    assert "<clay_context>" in user_message
    assert "Frontify" in user_message


@patch("scorer.scorer.push_to_hubspot", return_value=MagicMock(pushed=False))
@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer.generate_opener_gemini", return_value=(OPENER_TEXT, 0.0))
@patch("scorer.scorer._get_client")
def test_scoring_context_none_does_not_crash(mock_client_fn, mock_opener, mock_enrich, mock_slack, mock_crm):
    """scoring_context=None (default) works exactly as before — no regression."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(SCORE_JSON)

    result = score_company(_make_company(scoring_context=None))

    assert result.score == 8
    assert result.error is None


# ── _estimate_acv ─────────────────────────────────────────────────────────────

def test_estimate_acv_no_stage_small():
    assert _estimate_acv(30, None) == 12_000


def test_estimate_acv_no_stage_mid():
    assert _estimate_acv(100, None) == 25_000


def test_estimate_acv_no_stage_large():
    assert _estimate_acv(200, None) == 45_000


def test_estimate_acv_seed_small():
    assert _estimate_acv(40, "Seed") == 12_000


def test_estimate_acv_series_b():
    assert _estimate_acv(150, "Series B") == 40_000


def test_estimate_acv_series_c_plus():
    assert _estimate_acv(300, "Series C") == 60_000


# ── _contact_window_from_date ─────────────────────────────────────────────────

def test_contact_window_recent_is_now():
    from datetime import datetime, timedelta
    # RFC 2822 date 10 days ago
    recent = (datetime.now() - timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    assert _contact_window_from_date(recent) == "now"


def test_contact_window_45_days_is_soon():
    from datetime import datetime, timedelta
    mid = (datetime.now() - timedelta(days=45)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    assert _contact_window_from_date(mid) == "2-4 weeks"


def test_contact_window_old_hire_is_not_yet():
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=90)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    assert _contact_window_from_date(old) == "not yet"


def test_contact_window_invalid_date_returns_none():
    assert _contact_window_from_date("not-a-date") is None
