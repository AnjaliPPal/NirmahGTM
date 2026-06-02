import pytest
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET
from scorer.signal_detector import (
    detect_signals,
    _detect_leadership_change,
    _detect_hiring_signals,
    _detect_ats_from_careers_page,
    _detect_tech_stack,
    _detect_funding,
    _detect_hidden_intent,
    _google_news_rss,
)

_GREENHOUSE_RESPONSE = {
    "jobs": [
        {"title": "Account Executive - Mid Market", "id": 1},
        {"title": "SDR Manager", "id": 2},
        {"title": "Software Engineer", "id": 3},
        {"title": "Revenue Operations Analyst", "id": 4},
    ]
}

_FUNDING_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Acme Corp raises $50M Series B to expand sales team</title></item>
  <item><title>Some other news item</title></item>
</channel></rss>"""

_LEADERSHIP_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Jane Smith joins Acme Corp as new VP Sales to lead growth</title></item>
</channel></rss>"""

_INTENT_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Acme Corp announces expansion into European markets</title></item>
  <item><title>Acme Corp scaling operations with 200 new hires</title></item>
</channel></rss>"""


@patch("scorer.signal_detector.requests.get")
def test_greenhouse_detects_gtm_jobs(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: _GREENHOUSE_RESPONSE)
    hiring, count, keywords, evidence = _detect_hiring_signals("acme.com", "Acme Corp")
    assert hiring is True
    assert count == 3  # AE, SDR Manager, RevOps — not Engineer
    assert any("account" in k.lower() or "sdr" in k.lower() or "revenue" in k.lower()
               for k in [k.lower() for k in keywords])
    assert evidence is not None


@patch("scorer.signal_detector.requests.get")
def test_funding_detected_from_news(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        text=_FUNDING_RSS,
    )
    funded, stage, ma, evidence, url, date, headline = _detect_funding("Acme Corp")
    assert funded is True
    assert stage == "Series B"
    assert ma is False
    assert evidence is not None


@patch("scorer.signal_detector.requests.get")
def test_leadership_change_detected(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        text=_LEADERSHIP_RSS,
    )
    new_exec, name, title, evidence, hire_date = _detect_leadership_change("Acme Corp")
    assert new_exec is True
    assert evidence is not None


@patch("scorer.signal_detector.requests.get")
def test_intent_keywords_from_news(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        text=_INTENT_RSS,
    )
    keywords, count, evidence = _detect_hidden_intent("Acme Corp")
    assert "expansion" in keywords or count > 0


@patch("scorer.signal_detector.requests.get")
def test_tech_stack_detects_salesforce(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        text='<html><script src="https://salesforce.com/something.js"></script></html>',
    )
    tech, crm, engagement, evidence = _detect_tech_stack("acme.com")
    assert "Salesforce" in tech
    assert crm == "Salesforce"
    assert evidence is not None


@patch("scorer.signal_detector._detect_leadership_change", return_value=(True, "Jane Smith", "VP Sales", "jane smith joins acme as vp sales", None))
@patch("scorer.signal_detector._detect_hiring_signals", return_value=(True, 3, ["SDR", "CRM"], "Account Executive, SDR Manager, Revenue Ops"))
@patch("scorer.signal_detector._detect_tech_stack", return_value=(["Salesforce"], "Salesforce", None, "Salesforce detected in homepage HTML"))
@patch("scorer.signal_detector._detect_funding", return_value=(True, "Series B", False, "acme corp raises $50m series b", None, None, None))
@patch("scorer.signal_detector._detect_hidden_intent", return_value=(["expansion"], 1, "expansion (Google News)"))
def test_detect_signals_combines_all_triggers(m1, m2, m3, m4, m5):
    signals = detect_signals("acme.com", "Acme Corp")
    assert signals.funded_90d is True
    assert signals.funding_stage == "Series B"
    assert signals.hiring_gtm is True
    assert signals.new_exec_hire is True
    assert signals.crm == "Salesforce"
    assert "expansion" in signals.news_keywords
    assert signals.funded_90d_evidence == "acme corp raises $50m series b"
    assert signals.hiring_gtm_evidence == "Account Executive, SDR Manager, Revenue Ops"
    assert signals.leadership_change_evidence == "jane smith joins acme as vp sales"


@patch("scorer.signal_detector.requests.get", side_effect=Exception("network error"))
def test_detector_never_raises_on_network_failure(mock_get):
    signals = detect_signals("acme.com", "Acme Corp")
    assert signals is not None
    assert signals.funded_90d is False


# ── ATS embed detection ───────────────────────────────────────────────────────

@patch("scorer.signal_detector.requests.get")
def test_ats_detection_greenhouse_embed(mock_get):
    """Tier 0: extract exact Greenhouse slug from careers page HTML."""
    careers_html = MagicMock(status_code=200, text=(
        '<html><script src="https://boards.greenhouse.io/embed/job_board?for=acmecorp"></script></html>'
    ))
    mock_get.return_value = careers_html
    result = _detect_ats_from_careers_page("acme.com")
    assert result is not None
    ats_type, slug = result
    assert ats_type == "greenhouse"
    assert slug == "acmecorp"


@patch("scorer.signal_detector.requests.get")
def test_ats_detection_lever_embed(mock_get):
    """Tier 0: extract exact Lever slug from careers page HTML."""
    careers_html = MagicMock(status_code=200, text=(
        '<html><a href="https://jobs.lever.co/outreach">View openings</a></html>'
    ))
    mock_get.return_value = careers_html
    result = _detect_ats_from_careers_page("outreach.io")
    assert result is not None
    ats_type, slug = result
    assert ats_type == "lever"
    assert slug == "outreach"


@patch("scorer.signal_detector.requests.get")
def test_ats_detection_ashby_embed(mock_get):
    """Tier 0: extract exact Ashby slug from careers page HTML."""
    careers_html = MagicMock(status_code=200, text=(
        '<html><script src="https://jobs.ashbyhq.com/notion/embed?version=2"></script></html>'
    ))
    mock_get.return_value = careers_html
    result = _detect_ats_from_careers_page("notion.so")
    assert result is not None
    ats_type, slug = result
    assert ats_type == "ashby"
    assert slug == "notion"


@patch("scorer.signal_detector.requests.get")
def test_ats_detection_returns_none_when_no_embed(mock_get):
    """Returns None when careers page exists but uses unknown ATS (Workday, BambooHR etc)."""
    mock_get.return_value = MagicMock(status_code=200, text=(
        '<html><a href="https://company.workday.com/careers">Jobs</a></html>'
    ))
    result = _detect_ats_from_careers_page("bigcorp.com")
    assert result is None
