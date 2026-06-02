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
import logging
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from .models import Signals

logger = logging.getLogger(__name__)

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
            logger.warning("Google News RSS returned %s for query: %s", r.status_code, query[:80])
            return []
        root = ET.fromstring(r.text)
        return [
            el.text.lower()
            for item in root.findall(".//item")[:max_items]
            if (el := item.find("title")) is not None and el.text
        ]
    except Exception as e:
        logger.warning("Google News RSS failed for query '%s': %s", query[:80], e)
        return []


def _google_news_rss_with_meta(query: str, max_items: int = 5) -> list[dict]:
    """
    Fetch Google News RSS and return title + pubDate + google_link + source_domain per article.
    Uses regex parsing — ElementTree mishandles <link> in RSS.
    """
    try:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        results = []
        for raw_item in re.findall(r"<item>(.*?)</item>", r.text, re.DOTALL)[:max_items]:
            title_m  = re.search(r"<title>(.*?)</title>", raw_item, re.DOTALL)
            link_m   = re.search(r"<link>(.*?)</link>", raw_item, re.DOTALL)
            date_m   = re.search(r"<pubDate>(.*?)</pubDate>", raw_item, re.DOTALL)
            source_m = re.search(r'<source[^>]+url="([^"]+)"', raw_item)
            if not title_m:
                continue
            clean = lambda s: re.sub(r"<!\[CDATA\[|\]\]>", "", s).strip()
            results.append({
                "title":         clean(title_m.group(1)),
                "google_link":   clean(link_m.group(1)) if link_m else None,
                "date":          clean(date_m.group(1)) if date_m else None,
                "source_domain": clean(source_m.group(1)) if source_m else None,
            })
        return results
    except Exception as e:
        logger.warning("Google News RSS (with meta) failed for query '%s': %s", query[:80], e)
        return []


def _resolve_article_url(google_link: str | None, source_domain: str | None) -> str | None:
    """
    Follow Google News redirect to get the real article URL.
    Falls back to source_domain if redirect stays on Google.
    """
    if not google_link:
        return source_domain
    try:
        r = requests.get(
            google_link,
            timeout=8,
            allow_redirects=True,
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )},
        )
        final_url = r.url
        if "google.com" not in final_url:
            return final_url
    except Exception:
        pass
    return source_domain


# ── Article fetcher — used to ground aha_moment in real facts ────────────────

def fetch_article_excerpt(url: str, max_chars: int = 600) -> str | None:
    """
    Fetch a news article URL and return plain-text excerpt of the body.
    Strips HTML tags, scripts, and nav noise. Returns None on failure.
    """
    if not url or not url.startswith("http"):
        return None
    try:
        r = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None
        html = r.text

        # Remove scripts, styles, nav, footer blocks
        html = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Find the meaty part — skip past short nav lines by looking for a sentence
        # with a capital letter and at least 80 chars
        sentences = re.split(r"(?<=[.!?])\s+", text)
        body_parts = []
        total = 0
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 40:
                continue
            body_parts.append(sent)
            total += len(sent)
            if total >= max_chars:
                break

        excerpt = " ".join(body_parts)
        return excerpt[:max_chars] if excerpt else None
    except Exception:
        return None


# ── Trigger 1: Leadership Changes ─────────────────────────────────────────────

def _detect_leadership_change(
    company_name: str,
) -> tuple[bool, str | None, str | None, str | None, str | None]:
    """New VP/CRO/Chief in last ~90 days → new exec always audits old tools.
    Returns: hired, exec_name, exec_title, evidence_headline, hire_date (RFC 2822 pubDate)
    """
    queries = [
        f'"{company_name}" new VP OR Chief OR CRO hired joins appointed',
        f'"{company_name}" appoints promotes head of sales revenue',
    ]
    for query in queries:
        for art in _google_news_rss_with_meta(query, max_items=5):
            title = art["title"].lower()
            if any(kw in title for kw in _EXEC_TITLES):
                name_match = re.search(r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b', art["title"])
                exec_title = next(
                    (t for t in ["VP Sales", "CRO", "VP Revenue", "Chief Revenue Officer", "Head of Sales"]
                     if t.lower() in title),
                    None,
                )
                hire_date = art.get("date")
                if hire_date:
                    hire_date = " ".join(hire_date.split()[:4])  # "Mon, 12 May 2026"
                return True, name_match.group(1) if name_match else None, exec_title, art["title"], hire_date
    return False, None, None, None, None


# ── Trigger 2: Hiring Signals ─────────────────────────────────────────────────

# Patterns to extract ATS slug from a company's careers page HTML embed code.
# Order matters — more specific patterns first.
_ATS_EMBED_PATTERNS: list[tuple[str, str]] = [
    ("greenhouse", r'job-boards\.greenhouse\.io/([a-zA-Z0-9_-]+)'),
    ("greenhouse", r'boards\.greenhouse\.io/embed/job_board\?for=([a-zA-Z0-9_-]+)'),
    ("greenhouse", r'boards[-.]greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)'),
    ("greenhouse", r'grnhse_board_token\s*[=:]\s*["\']([a-zA-Z0-9_-]+)'),
    ("lever",      r'jobs\.lever\.co/([a-zA-Z0-9_-]+)'),
    ("ashby",      r'jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)'),
]


def _detect_ats_from_careers_page(domain: str) -> tuple[str, str] | None:
    """
    Visit the company careers page and extract the ATS type + exact slug from
    the embedded job board code. Far more reliable than guessing the slug from
    the domain name — the embed always contains the real slug.
    """
    for path in ["/careers", "/jobs", "/about/careers", "/company/careers", "/join-us", "/join"]:
        try:
            r = requests.get(
                f"https://{domain}{path}",
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            if r.status_code != 200:
                continue
            html = r.text
            for ats, pattern in _ATS_EMBED_PATTERNS:
                m = re.search(pattern, html, re.IGNORECASE)
                if m:
                    slug = m.group(1).lower().rstrip("/")
                    logger.info("ATS detected on %s%s: %s / slug=%s", domain, path, ats, slug)
                    return ats, slug
        except Exception:
            continue
    return None


def _parse_ats_jobs(ats_type: str, data) -> tuple[bool, int, list[str], str | None]:
    """Extract GTM job titles from an ATS API response."""
    # Lever returns a plain list; Greenhouse/Ashby wrap under "jobs" key
    title_key = "text" if ats_type == "lever" else "title"
    jobs_raw = data if isinstance(data, list) else data.get("jobs", [])
    if not isinstance(jobs_raw, list):
        return False, 0, [], None

    gtm_jobs = [
        j.get(title_key, "") or j.get("title", "") or j.get("text", "")
        for j in jobs_raw
        if any(kw in (j.get(title_key, "") or j.get("title", "") or j.get("text", "")).lower()
               for kw in _GTM_KEYWORDS)
    ]
    if not gtm_jobs:
        return False, 0, [], None

    evidence = ", ".join(gtm_jobs[:3])
    if len(gtm_jobs) > 3:
        evidence += f" (+{len(gtm_jobs) - 3} more GTM roles)"
    return True, len(gtm_jobs), [t for t in gtm_jobs[:10] if t], evidence


def _query_ats(ats_type: str, slug: str) -> tuple[bool, int, list[str], str | None]:
    """Call the public ATS API for a known slug."""
    urls = {
        "greenhouse": [
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            f"https://job-boards.greenhouse.io/v1/boards/{slug}/jobs",  # newer URL
        ],
        "lever": [f"https://api.lever.co/v0/postings/{slug}?mode=json"],
        "ashby": [f"https://api.ashbyhq.com/posting-api/job-board/{slug}"],
    }
    for url in urls.get(ats_type, []):
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return _parse_ats_jobs(ats_type, r.json())
        except Exception:
            continue
    return False, 0, [], None


def _detect_hiring_signals(
    domain: str, company_name: str,
) -> tuple[bool, int, list[str], str | None]:
    """
    Three-tier hiring detection:
    Tier 0 — ATS embed detection (exact slug from careers page HTML)
    Tier 1 — Slug guessing for the 3 ATS with free public APIs
    Tier 2 — Google News fallback
    """
    # Tier 0: detect ATS from careers page — finds exact slug, no guessing
    ats_info = _detect_ats_from_careers_page(domain)
    if ats_info:
        ats_type, slug = ats_info
        result = _query_ats(ats_type, slug)
        if result[0]:
            return result

    # Tier 1: slug guessing — Greenhouse, Lever, Ashby have free public APIs
    base = domain.split(".")[0].lower()
    for slug in list(dict.fromkeys([base, base.replace("-", "")])):
        for ats_type, url in [
            ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
            ("lever",      f"https://api.lever.co/v0/postings/{slug}?mode=json"),
            ("ashby",      f"https://api.ashbyhq.com/posting-api/job-board/{slug}"),
        ]:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code != 200:
                    continue
                result = _parse_ats_jobs(ats_type, r.json())
                if result[0]:
                    return result
            except Exception:
                continue

    # Tier 2: Google News — can confirm hiring signal but can't count open roles
    titles = _google_news_rss(f'"{company_name}" hiring sales SDR "account executive"', 5)
    if titles:
        return True, 0, ["sales", "sdr"], titles[0]

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
) -> tuple[bool, str | None, bool, str | None, str | None, str | None, str | None]:
    """
    Scan Google News for recent funding/M&A.
    Returns: funded, stage, ma_activity, evidence, article_url, article_date, headline
    """
    articles = _google_news_rss_with_meta(
        f'"{company_name}" raises OR raised funding OR "series a" OR "series b" OR "series c" OR million',
        max_items=8,
    )
    funded       = False
    stage        = None
    ma           = False
    evidence     = None
    article_url  = None
    article_date = None
    headline     = None

    for art in articles:
        title = art["title"].lower()
        name  = company_name.lower()
        # Company must be the one raising — not just mentioned as an investor or in a list
        # Guard: "Notion Capital", "Salesforce Ventures" etc. leading a round for someone else
        _is_vc_modifier = bool(re.match(
            rf"^{re.escape(name)}\s+(?:capital|ventures|venture|partners|partner|fund|equity|vc)\b", title
        ))
        is_subject = not _is_vc_modifier and (
            bool(re.match(rf"^{re.escape(name)}\b", title)) or
            f"{name} raise" in title or
            f"{name} secured" in title or
            f"{name} closed" in title or
            f"{name} announce" in title or
            f"'s {name} raise" in title or  # "Bret Taylor's Sierra raises"
            re.search(rf"\b{re.escape(name)}\b.{{0,30}}(raise|raised|secures|secured|closes|closed)", title) is not None
        )
        if not is_subject:
            continue
        if any(kw in title for kw in _FUNDING_KEYWORDS):
            funded = True
            if evidence is None:
                # Strip the " - Source Name" suffix from Google News titles
                clean_headline = re.sub(r"\s+-\s+\w[\w\s]+$", "", art["title"]).strip()
                headline     = clean_headline
                evidence     = clean_headline
                article_date = art.get("date", "")
                # Trim date to "Mon, 12 May 2026" format
                if article_date:
                    article_date = " ".join(article_date.split()[:4])
                # Resolve real article URL in background
                article_url = _resolve_article_url(
                    art.get("google_link"), art.get("source_domain")
                )
            for stage_name, patterns in _STAGE_PATTERNS.items():
                if any(p in title for p in patterns):
                    stage = stage_name
                    break
        if any(kw in title for kw in ["acquired", "acquisition", "merger", "acquires"]):
            ma = True

    return funded, stage, ma, evidence, article_url, article_date, headline


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
    new_exec, exec_name, exec_title, leadership_evidence, leadership_hire_date = _detect_leadership_change(company_name)
    hiring_gtm, open_roles, keywords, hiring_evidence           = _detect_hiring_signals(domain, company_name)
    tech_stack, crm, engagement, tech_evidence                  = _detect_tech_stack(domain)
    funded, stage, ma_activity, funding_evidence, fund_url, fund_date, fund_headline = _detect_funding(company_name)
    news_keywords, intent_count, intent_evidence                = _detect_hidden_intent(company_name)

    return Signals(
        # Trigger 4
        funded_90d=funded,
        funding_stage=stage,
        acquisition_activity=ma_activity,
        funded_90d_evidence=funding_evidence,
        funded_90d_url=fund_url,
        funded_90d_date=fund_date,
        funded_90d_headline=fund_headline,
        # Trigger 2
        hiring_gtm=hiring_gtm,
        open_gtm_roles=open_roles,
        hiring_keywords=keywords,
        hiring_gtm_evidence=hiring_evidence,
        # Trigger 1
        new_exec_hire=new_exec,
        new_exec_name=exec_name,
        new_exec_title=exec_title,
        leadership_hire_date=leadership_hire_date,
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
