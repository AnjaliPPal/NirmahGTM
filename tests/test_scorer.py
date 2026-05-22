import pytest
from unittest.mock import patch, MagicMock
from scorer.models import CompanyInput, Signals, EnrichmentData
from scorer.scorer import score_company


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


def _mock_usage(input_tokens=100, output_tokens=50, cache_read=0, cache_write=0):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_write
    return u


def _mock_claude(text: str, **usage_kwargs):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage = _mock_usage(**usage_kwargs)
    return msg


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


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_ENRICHED)
@patch("scorer.scorer._get_client")
def test_high_score_fires_slack_with_enrichment(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_claude(SCORE_JSON),
        _mock_claude(OPENER_TEXT),
    ]

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
    mock_client.messages.create.return_value = _mock_claude(SCORE_JSON_LOW)

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
    mock_client.messages.create.return_value = _mock_claude("not valid json")

    result = score_company(_make_company())

    assert result.scored is False
    assert "JSON parse failed" in result.error


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_cost_includes_cache_read_tokens(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_claude(SCORE_JSON, cache_write=500, input_tokens=20, output_tokens=80),
        _mock_claude(OPENER_TEXT, cache_read=500, input_tokens=10, output_tokens=30),
    ]

    result = score_company(_make_company())

    # cache_write=500@$3.75/1M + input=20@$3/1M + output=80@$15/1M
    # + cache_read=500@$0.30/1M + input=10@$3/1M + output=30@$15/1M
    expected = (
        500 * 0.00000375 + 20 * 0.000003 + 80 * 0.000015 +
        500 * 0.0000003  + 10 * 0.000003 + 30 * 0.000015
    )
    assert result.cost_usd == pytest.approx(round(expected, 6))


@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_uses_system_prompt_for_caching(mock_client_fn, mock_enrich):
    """Verify system param is passed (enables prompt caching)."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_claude(
        '{"score": 3, "reasoning": "weak", "top_signal": "hiring_gtm", "contact_window": "not yet"}'
    )

    score_company(_make_company())

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" in call_kwargs
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_pitch_block_populated_for_high_score(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _mock_claude(SCORE_JSON),
        _mock_claude(OPENER_TEXT),
    ]

    result = score_company(_make_company())

    assert result.pitch_block is not None
    assert len(result.pitch_block) > 20
    assert result.signal_scores.get("funding") == 9
    assert result.signal_scores.get("hiring") == 8


@patch("scorer.scorer.send_slack_alert", return_value=False)
@patch("scorer.scorer.enrich_company", return_value=_NO_ENRICHMENT)
@patch("scorer.scorer._get_client")
def test_signal_scores_present_even_for_low_score(mock_client_fn, mock_enrich, mock_slack):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_claude(SCORE_JSON_LOW)

    result = score_company(_make_company())

    assert result.score == 3
    assert result.signal_scores.get("hiring") == 3
    assert result.signal_scores.get("funding") == 0
    assert result.pitch_block is not None
