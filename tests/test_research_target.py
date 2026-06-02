"""Tests for scorer/research_target.py"""
from unittest.mock import patch
import pytest

from scorer.research_target import (
    _clean_results,
    _deduplicate,
    _has_direct_source,
    _source_1_homepage,
    _source_2_customer_pages,
    _source_3_google_news,
    research_target,
)


# ── _clean_results ────────────────────────────────────────────────────────────

def test_clean_results_valid_record():
    raw = [{"name": "Brian Irving", "company": "Lyft", "title": "CMO"}]
    result = _clean_results(raw, "homepage")
    assert len(result) == 1
    assert result[0]["company"] == "Lyft"
    assert result[0]["source"] == "homepage"
    assert result[0]["name"] == "Brian Irving"


def test_clean_results_skips_empty_company():
    raw = [
        {"name": "Bob", "company": "", "title": "CEO"},
        {"name": "Alice", "company": "Acme", "title": ""},
    ]
    result = _clean_results(raw, "homepage")
    assert len(result) == 1
    assert result[0]["company"] == "Acme"


def test_clean_results_skips_placeholder_company():
    raw = [{"name": "John", "company": "Company Name", "title": "CEO"}]
    assert _clean_results(raw, "homepage") == []


def test_clean_results_skips_unknown():
    raw = [{"name": "", "company": "unknown", "title": ""}]
    assert _clean_results(raw, "homepage") == []


def test_clean_results_not_list():
    assert _clean_results("bad_input", "homepage") == []
    assert _clean_results(None, "homepage") == []


def test_clean_results_skips_non_dict_items():
    raw = ["not a dict", {"name": "Jane", "company": "ACME Corp", "title": "VP"}]
    result = _clean_results(raw, "homepage")
    assert len(result) == 1
    assert result[0]["company"] == "ACME Corp"


# ── _deduplicate ──────────────────────────────────────────────────────────────

def test_deduplicate_removes_case_insensitive_duplicates():
    customers = [
        {"company": "Lyft", "name": "Brian", "title": "CMO", "source": "homepage"},
        {"company": "lyft", "name": "Brian", "title": "CMO", "source": "page:/customers"},
        {"company": "Turo", "name": "David", "title": "CMO", "source": "homepage"},
    ]
    result = _deduplicate(customers)
    assert len(result) == 2
    assert result[0]["company"] == "Lyft"
    assert result[1]["company"] == "Turo"


def test_deduplicate_preserves_insertion_order():
    customers = [
        {"company": "Turo",  "name": "", "title": "", "source": "x"},
        {"company": "Lyft",  "name": "", "title": "", "source": "x"},
        {"company": "Groq",  "name": "", "title": "", "source": "x"},
    ]
    result = _deduplicate(customers)
    assert [r["company"] for r in result] == ["Turo", "Lyft", "Groq"]


def test_deduplicate_empty_list():
    assert _deduplicate([]) == []


# ── _source_1_homepage ────────────────────────────────────────────────────────

@patch("scorer.research_target._fetch_page")
@patch("scorer.research_target.groq_json_extract")
def test_source_1_homepage_returns_customers(mock_groq, mock_fetch):
    mock_fetch.return_value = "Brian Irving, CMO at Lyft, says brand.ai changed everything."
    mock_groq.return_value = [{"name": "Brian Irving", "company": "Lyft", "title": "CMO"}]
    result = _source_1_homepage("brand.ai")
    assert len(result) == 1
    assert result[0]["company"] == "Lyft"
    assert result[0]["source"] == "homepage"


@patch("scorer.research_target._fetch_page")
def test_source_1_homepage_returns_empty_when_page_unavailable(mock_fetch):
    mock_fetch.return_value = None
    assert _source_1_homepage("brand.ai") == []


@patch("scorer.research_target._fetch_page")
@patch("scorer.research_target.groq_json_extract")
def test_source_1_homepage_returns_empty_when_no_customers(mock_groq, mock_fetch):
    mock_fetch.return_value = "About us. We build brand tools."
    mock_groq.return_value = []
    assert _source_1_homepage("brand.ai") == []


# ── _source_2_customer_pages ─────────────────────────────────────────────────

@patch("scorer.research_target._fetch_page")
@patch("scorer.research_target.groq_json_extract")
def test_source_2_returns_first_path_with_customers(mock_groq, mock_fetch):
    long_content = "Turo and Groq use brand.ai for brand management. " * 5  # > 200 chars
    mock_fetch.side_effect = [
        None,          # /customers → no content
        long_content,  # /case-studies → has content
    ]
    mock_groq.return_value = [{"name": "", "company": "Turo", "title": ""}]
    result = _source_2_customer_pages("brand.ai")
    assert len(result) == 1
    assert result[0]["company"] == "Turo"
    assert result[0]["source"] == "page:/case-studies"


@patch("scorer.research_target._fetch_page")
def test_source_2_returns_empty_when_all_paths_fail(mock_fetch):
    mock_fetch.return_value = None
    assert _source_2_customer_pages("brand.ai") == []


@patch("scorer.research_target._fetch_page")
@patch("scorer.research_target.groq_json_extract")
def test_source_2_skips_tiny_pages(mock_groq, mock_fetch):
    mock_fetch.return_value = "404 not found"  # < 200 chars
    assert _source_2_customer_pages("brand.ai") == []
    mock_groq.assert_not_called()


# ── _source_3_google_news ─────────────────────────────────────────────────────

@patch("scorer.research_target._google_news_rss")
@patch("scorer.research_target.groq_json_extract")
def test_source_3_extracts_from_headlines(mock_groq, mock_rss):
    mock_rss.return_value = [
        "lyft selects brand.ai as ai brand platform",
        "groq case study: brand.ai powers brand consistency",
    ]
    mock_groq.return_value = [{"name": "", "company": "Lyft", "title": ""}]
    result = _source_3_google_news("brand.ai")
    assert len(result) == 1
    assert result[0]["source"] == "google_news"


@patch("scorer.research_target._google_news_rss")
def test_source_3_returns_empty_when_no_news(mock_rss):
    mock_rss.return_value = []
    assert _source_3_google_news("brand.ai") == []


# ── _has_direct_source ────────────────────────────────────────────────────────

def test_has_direct_source_true_for_homepage():
    customers = [{"company": "Lyft", "name": "", "title": "", "source": "homepage"}]
    assert _has_direct_source(customers) is True


def test_has_direct_source_true_for_customer_page():
    customers = [{"company": "Turo", "name": "", "title": "", "source": "page:/customers"}]
    assert _has_direct_source(customers) is True


def test_has_direct_source_false_for_google_news_only():
    customers = [
        {"company": "Adobe",    "name": "", "title": "", "source": "google_news"},
        {"company": "Alchemer", "name": "", "title": "", "source": "google_news"},
    ]
    assert _has_direct_source(customers) is False


def test_has_direct_source_true_when_mixed():
    customers = [
        {"company": "Adobe", "name": "", "title": "", "source": "google_news"},
        {"company": "Lyft",  "name": "", "title": "", "source": "homepage"},
    ]
    assert _has_direct_source(customers) is True


# ── research_target (integration) ─────────────────────────────────────────────

@patch("scorer.research_target._source_3_google_news")
@patch("scorer.research_target._source_2_customer_pages")
@patch("scorer.research_target._source_1_homepage")
def test_research_target_merges_and_deduplicates(mock_s1, mock_s2, mock_s3):
    mock_s1.return_value = [{"name": "Brian", "company": "Lyft",  "title": "CMO", "source": "homepage"}]
    mock_s2.return_value = [{"name": "David", "company": "Turo",  "title": "CMO", "source": "page:/customers"}]
    mock_s3.return_value = [{"name": "Brian", "company": "Lyft",  "title": "",    "source": "google_news"}]
    result = research_target("brand.ai", "brand.ai")
    companies = [r["company"] for r in result]
    assert "Lyft" in companies
    assert "Turo" in companies
    assert companies.count("Lyft") == 1   # deduplication works


@patch("scorer.research_target._source_3_google_news")
@patch("scorer.research_target._source_2_customer_pages")
@patch("scorer.research_target._source_1_homepage")
def test_research_target_returns_empty_when_all_sources_fail(mock_s1, mock_s2, mock_s3):
    mock_s1.return_value = []
    mock_s2.return_value = []
    mock_s3.return_value = []
    assert research_target("noresults.com", "NoResults") == []


@patch("scorer.research_target._source_3_google_news")
@patch("scorer.research_target._source_2_customer_pages")
@patch("scorer.research_target._source_1_homepage")
def test_research_target_returns_empty_when_only_google_news(mock_s1, mock_s2, mock_s3):
    # Simulates brand.ai: WebGL homepage = no direct source, Google News finds noise
    mock_s1.return_value = []
    mock_s2.return_value = []
    mock_s3.return_value = [
        {"name": "", "company": "Adobe",    "title": "", "source": "google_news"},
        {"name": "", "company": "Alchemer", "title": "", "source": "google_news"},
    ]
    # Should return [] — Google News only is too noisy, caller uses hardcoded fallback
    assert research_target("brand.ai", "brand.ai") == []


@patch("scorer.research_target._source_3_google_news")
@patch("scorer.research_target._source_2_customer_pages")
@patch("scorer.research_target._source_1_homepage")
def test_research_target_returns_list_of_dicts(mock_s1, mock_s2, mock_s3):
    mock_s1.return_value = [{"name": "Ann", "company": "Acme", "title": "CMO", "source": "homepage"}]
    mock_s2.return_value = []
    mock_s3.return_value = []
    result = research_target("acme.com", "Acme")
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)
    assert all(k in result[0] for k in ("name", "company", "title", "source"))
