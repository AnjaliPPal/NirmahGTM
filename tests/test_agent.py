import pytest
from unittest.mock import patch, MagicMock
from scorer.models import CompanyInput, ScoreResult, Signals


def _make_result(company_name: str, score: int, suppressed: bool = False) -> ScoreResult:
    return ScoreResult(
        company_name=company_name,
        domain=f"{company_name.lower().replace(' ', '')}.com",
        client_id="test",
        signals=Signals(),
        score=score,
        confidence=85,
        reasoning="Funding + hiring firing simultaneously",
        top_signal="funded_90d",
        contact_window="now",
        aha_moment=f"{company_name} just closed funding and hired GTM leadership.",
        scored=True,
        suppressed=suppressed,
        cost_usd=0.001,
    )


@patch("scorer.agent._get_client")
@patch("scorer.agent.score_company")
def test_batch_ranks_by_score_descending(mock_score, mock_client):
    """Highest-scoring company should be ranked first."""
    companies = [
        CompanyInput(company_name="Acme", domain="acme.com", client_id="test"),
        CompanyInput(company_name="Beta", domain="beta.com", client_id="test"),
        CompanyInput(company_name="Gamma", domain="gamma.com", client_id="test"),
    ]
    mock_score.side_effect = [
        _make_result("Acme", 8),
        _make_result("Beta", 4),
        _make_result("Gamma", 9),
    ]
    mock_client.return_value.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Gamma and Acme are hot this week."))]
    )

    from scorer.agent import run_batch
    result = run_batch(companies, min_score=6)

    assert result["total_scored"] == 3
    assert result["hot_leads_count"] == 2
    # Gamma (9) should be first, Acme (8) second
    names = [r.company_name for r in result["ranked"]]
    assert names.index("Gamma") < names.index("Acme")
    assert "Beta" not in [r.company_name for r in result["ranked"] if (r.score or 0) >= 6]


@patch("scorer.agent._get_client")
@patch("scorer.agent.score_company")
def test_batch_no_hot_leads_skips_claude_summary(mock_score, mock_client):
    """When nothing scores above threshold, return the no-hot-leads message without Claude call."""
    companies = [
        CompanyInput(company_name="Quiet", domain="quiet.com", client_id="test"),
    ]
    mock_score.return_value = _make_result("Quiet", 3)

    from scorer.agent import run_batch
    result = run_batch(companies, min_score=6)

    assert result["hot_leads_count"] == 0
    assert "No companies scored" in result["summary"]
    # Groq should NOT be called for the summary when there are no hot leads
    mock_client.return_value.chat.completions.create.assert_not_called()


@patch("scorer.agent._get_client")
@patch("scorer.agent.score_company")
def test_batch_excludes_suppressed_results(mock_score, mock_client):
    """Suppressed companies (cooldown) should not appear in ranked output."""
    companies = [
        CompanyInput(company_name="Hot", domain="hot.com", client_id="test"),
        CompanyInput(company_name="Suppressed", domain="suppressed.com", client_id="test"),
    ]
    mock_score.side_effect = [
        _make_result("Hot", 9),
        _make_result("Suppressed", 9, suppressed=True),
    ]
    mock_client.return_value.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Hot is the priority this week."))]
    )

    from scorer.agent import run_batch
    result = run_batch(companies, min_score=6)

    ranked_names = [r.company_name for r in result["ranked"]]
    assert "Hot" in ranked_names
    assert "Suppressed" not in ranked_names
    assert result["hot_leads_count"] == 1


@patch("scorer.agent._get_client")
@patch("scorer.agent.score_company")
def test_batch_summary_calls_claude_with_top_leads(mock_score, mock_client):
    """Summary generation should call Claude with the top companies' aha moments."""
    companies = [
        CompanyInput(company_name="Alpha", domain="alpha.com", client_id="test"),
    ]
    mock_score.return_value = _make_result("Alpha", 8)
    summary_text = "Alpha is ready for outreach immediately."
    mock_client.return_value.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=summary_text))]
    )

    from scorer.agent import run_batch
    result = run_batch(companies, min_score=6)

    assert result["summary"] == summary_text
    mock_client.return_value.chat.completions.create.assert_called_once()
