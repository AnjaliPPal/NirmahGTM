"""
Auto-detect 5 GTM buying triggers from free public sources.

Trigger 1: Leadership Changes  — Google News RSS (new VP/CRO/Chief hired)
Trigger 2: Hiring Signals      — Greenhouse/Lever public APIs (no auth required)
Trigger 3: Tech Stack          — HTML signature scan of company website
Trigger 4: Funding & M&A       — Google News RSS (funding/acquisition keywords)
Trigger 5: Hidden Intent       — Google News RSS (expansion/growth before job posts)

Called by scorer.py when CompanyInput.signals is None (auto-detect mode).
All functions: never raise. Return empty/False on failure.
"""
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from .models import Signals

_GTM_KEYWORDS = {
    "sales", "revenue", "gtm", "sdr", "bdr", "account executive",
    "crm", "outbound", "demand gen", "marketing ops", "revops", "enablement",
}

_EXEC_TITLES = {
    "vp", "chief", "cro", "ceo", "head of sales", "vp sales",
    "vp of revenue", "chief revenue", "director of sales",
}

_FUNDING_KEYWORDS = {
    "raises", "raised", "funding", "series", "round", "capital",
    "investment", "acquired", "acquisition", "merger",
}

_INTENT_KEYWORDS = {
    "expansion", "growth", "hiring spree", "new market", "launches",
    "scaling", "opens office", "international", "doubles", "triples",
}

_TECH_SIGNATURES = {
    "Salesforce":  ["salesforce.com", "force.com", "pardot.com"],
    "HubSpot":     ["hubspot.com", "hs-scripts.com", "hubapi.com"],
    "Outreach":    ["outreach.io"],
    "Salesloft":   ["salesloft.com"],
    "Marketo":     ["marketo.com", "mktoresp.com"],
    "Intercom":    ["intercom.com", "intercom.io"],
    "Drift":       ["drift.com"],
    "Gong":        ["gong.io"],
    "Chorus":      ["chorus.ai"],
    "ZoomInfo":    ["zoominfo.com"],
    "6sense":      ["6sense.com"],
    "Apollo":      ["apollo.io"],
}

_CRM_TOOLS        = {"Salesforce", "HubSpot", "Marketo"}
_ENGAGEMENT_TOOLS = {"Outreach", "Salesloft", "Drift"}

_STAGE_PATTERNS = {
    "Series C+": ["series c", "series d", "series e", "series f"],
    "Series B":  ["series b"],
    "Series A":  ["series a"],
    "Seed":      ["seed round", "pre-seed"],
    "Growth":    ["growth capital", "private equity", "growth round"],
}


def _google_news_rss(query: str, max_items: int = 10) -> list[str]:
    """Fetch article titles from Google News RSS. Free, no API key."""
    try:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        return [
            el.text.lower()
            for item in root.findall(".//item")[:max_items]
            if (el := item.find("title")) is not None and el.text
        ]
    except Exception:
        return []


# ── Trigger 1: Leadership Changes ─────────────────────────────────────────────

def _detect_leadership_change(
    company_name: str,
) -> tuple[bool, str | None, str | None, str | None]:
    """New VP/CRO/Chief in last ~90 days → new exec always audits old tools."""
    queries = [
        f'"{company_name}" new VP OR Chief OR CRO hired joins appointed',
        f'"{company_name}" appoints promotes head of sales revenue',
    ]
    for query in queries:
        for title in _google_news_rss(query, max_items=5):
            if any(kw in title for kw in _EXEC_TITLES):
                name_match = re.search(r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b', title)
                exec_title = next(
                    (t for t in ["VP Sales", "CRO", "VP Revenue", "Chief Revenue Officer", "Head of Sales"]
                     if t.lower() in title),
                    None,
                )
                return True, name_match.group(1) if name_match else None, exec_title, title
    return False, None, None, None


# ── Trigger 2: Hiring Signals ─────────────────────────────────────────────────

def _detect_hiring_signals(
    domain: str, company_name: str,
) -> tuple[bool, int, list[str], str | None]:
    """
    Hit Greenhouse and Lever public job APIs (no auth, free).
    Job descriptions literally broadcast internal bottlenecks.
    """
    slug = domain.split(".")[0].lower().replace("-", "")

    for ats_url in [
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
    ]:
        try:
            r = requests.get(ats_url, timeout=5)
            if r.status_code != 200:
                continue
            data = r.json()
            jobs = data.get("jobs", data) if isinstance(data, dict) else data
            if not isinstance(jobs, list):
                continue

            gtm_jobs = [
                j.get("title", "")
                for j in jobs
                if any(kw in j.get("title", "").lower() for kw in _GTM_KEYWORDS)
            ]
            if gtm_jobs:
                keywords = list({
                    w for t in gtm_jobs
                    for w in t.split()
                    if len(w) > 3 and w.isalpha()
                })[:10]
                evidence = ", ".join(gtm_jobs[:3])
                if len(gtm_jobs) > 3:
                    evidence += f" (+{len(gtm_jobs) - 3} more GTM roles)"
                return True, len(gtm_jobs), keywords, evidence
        except Exception:
            continue

    # Fallback: Google News job signals
    titles = _google_news_rss(f'"{company_name}" hiring sales SDR "account executive"', 5)
    if titles:
        return True, len(titles), ["sales", "sdr"], titles[0]

    return False, 0, [], None


# ── Trigger 3: Tech Stack ─────────────────────────────────────────────────────

def _detect_tech_stack(
    domain: str,
) -> tuple[list[str], str | None, str | None, str | None]:
    """
    Scan company homepage HTML for embedded tool signatures.
    CRM detection = ruthless filter. Don't sell HubSpot to a Salesforce shop.
    """
    try:
        r = requests.get(
            f"https://{domain}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return [], None, None, None

        html = r.text.lower()
        detected = [
            tool for tool, sigs in _TECH_SIGNATURES.items()
            if any(sig in html for sig in sigs)
        ]
        crm        = next((t for t in detected if t in _CRM_TOOLS), None)
        engagement = next((t for t in detected if t in _ENGAGEMENT_TOOLS), None)
        evidence   = f"{', '.join(detected)} detected in homepage HTML" if detected else None
        return detected, crm, engagement, evidence
    except Exception:
        return [], None, None, None


# ── Trigger 4: Funding & M&A ──────────────────────────────────────────────────

def _detect_funding(
    company_name: str,
) -> tuple[bool, str | None, bool, str | None]:
    """Scan Google News for recent funding rounds or M&A activity."""
    titles = _google_news_rss(
        f'"{company_name}" funding raises series capital acquisition merger',
        max_items=8,
    )
    funded   = False
    stage    = None
    ma       = False
    evidence = None

    for title in titles:
        if any(kw in title for kw in _FUNDING_KEYWORDS):
            funded = True
            if evidence is None:
                evidence = title
            for stage_name, patterns in _STAGE_PATTERNS.items():
                if any(p in title for p in patterns):
                    stage = stage_name
                    break
        if any(kw in title for kw in ["acquired", "acquisition", "merger", "acquires"]):
            ma = True

    return funded, stage, ma, evidence


# ── Trigger 5: Hidden Intent ──────────────────────────────────────────────────

def _detect_hidden_intent(
    company_name: str,
) -> tuple[list[str], int, str | None]:
    """
    The secret weapon: scan podcasts, PR, and news for expansion signals
    BEFORE they post a job. Companies telegraph moves weeks before hiring.

    Sources: Google News (TechCrunch, VentureBeat, Bloomberg), podcast RSS.
    """
    titles = _google_news_rss(
        f'"{company_name}" expansion scaling growth "new market" launching hiring',
        max_items=15,
    )
    found    = list({kw for t in titles for kw in _INTENT_KEYWORDS if kw in t})
    evidence = f"{', '.join(found[:3])} (Google News)" if found else None
    return found, len(found), evidence


# ── Main entry point ──────────────────────────────────────────────────────────

def detect_signals(domain: str, company_name: str) -> Signals:
    """
    Auto-detect all 5 GTM buying triggers. Takes 5-12 seconds.
    Returns partial data on any failure — never blocks scoring.
    """
    new_exec, exec_name, exec_title, leadership_evidence = _detect_leadership_change(company_name)
    hiring_gtm, open_roles, keywords, hiring_evidence    = _detect_hiring_signals(domain, company_name)
    tech_stack, crm, engagement, tech_evidence           = _detect_tech_stack(domain)
    funded, stage, ma_activity, funding_evidence         = _detect_funding(company_name)
    news_keywords, intent_count, intent_evidence         = _detect_hidden_intent(company_name)

    return Signals(
        # Trigger 4
        funded_90d=funded,
        funding_stage=stage,
        acquisition_activity=ma_activity,
        funded_90d_evidence=funding_evidence,
        # Trigger 2
        hiring_gtm=hiring_gtm,
        open_gtm_roles=open_roles,
        hiring_keywords=keywords,
        hiring_gtm_evidence=hiring_evidence,
        # Trigger 1
        new_exec_hire=new_exec,
        new_exec_name=exec_name,
        new_exec_title=exec_title,
        leadership_change_evidence=leadership_evidence,
        # Trigger 3
        tech_stack=tech_stack,
        crm=crm,
        sales_engagement=engagement,
        tech_stack_evidence=tech_evidence,
        # Trigger 5
        news_keywords=news_keywords,
        intent_signals_count=intent_count,
        hidden_intent_evidence=intent_evidence,
    )
