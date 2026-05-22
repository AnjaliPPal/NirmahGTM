import pytest
from unittest.mock import patch, MagicMock
from scorer.enrichment import enrich_company, _hunter_lookup, _apollo_lookup


def _mock_response(status: int, json_data: dict):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    return r


HUNTER_RESPONSE = {
    "data": {
        "emails": [
            {"first_name": "Jane", "last_name": "Smith", "position": "VP Sales", "value": "jane@acme.com"},
            {"first_name": "Bob", "last_name": "Jones", "position": "Engineer", "value": "bob@acme.com"},
        ]
    }
}

APOLLO_RESPONSE = {
    "organization": {
        "estimated_num_employees": 150,
        "industry": "Software",
    }
}


@patch("scorer.enrichment.HUNTER_API_KEY", "test-hunter-key")
@patch("scorer.enrichment.requests.get")
def test_hunter_prefers_gtm_title(mock_get):
    mock_get.return_value = _mock_response(200, HUNTER_RESPONSE)
    name, title, email = _hunter_lookup("acme.com")
    assert title == "VP Sales"
    assert email == "jane@acme.com"
    assert name == "Jane Smith"


@patch("scorer.enrichment.APOLLO_API_KEY", "test-apollo-key")
@patch("scorer.enrichment.requests.post")
def test_apollo_returns_firmographics(mock_post):
    mock_post.return_value = _mock_response(200, APOLLO_RESPONSE)
    count, industry = _apollo_lookup("acme.com")
    assert count == 150
    assert industry == "Software"


@patch("scorer.enrichment.HUNTER_API_KEY", "test-hunter-key")
@patch("scorer.enrichment.APOLLO_API_KEY", "test-apollo-key")
@patch("scorer.enrichment.requests.get")
@patch("scorer.enrichment.requests.post")
def test_enrich_company_combines_both(mock_post, mock_get):
    mock_get.return_value = _mock_response(200, HUNTER_RESPONSE)
    mock_post.return_value = _mock_response(200, APOLLO_RESPONSE)

    result = enrich_company("acme.com")

    assert result.enriched is True
    assert result.decision_maker_email == "jane@acme.com"
    assert result.employee_count == 150
    assert result.industry == "Software"


def test_enrich_returns_empty_without_keys():
    result = enrich_company("acme.com")
    assert result.enriched is False
    assert result.decision_maker_email is None


@patch("scorer.enrichment.HUNTER_API_KEY", "test-key")
@patch("scorer.enrichment.requests.get", side_effect=Exception("timeout"))
def test_hunter_failure_never_raises(mock_get):
    name, title, email = _hunter_lookup("acme.com")
    assert name is None and title is None and email is None


@patch("scorer.enrichment.APOLLO_API_KEY", "test-key")
@patch("scorer.enrichment.requests.post")
def test_apollo_non_200_returns_none(mock_post):
    mock_post.return_value = _mock_response(429, {})
    count, industry = _apollo_lookup("acme.com")
    assert count is None and industry is None
