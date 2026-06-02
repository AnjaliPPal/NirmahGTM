"""
Auto-detect a target company's confirmed customers from public sources.
Used by outbound skills to discover ICP seeds without hardcoding.

Sources (in order):
  1. Firecrawl scrape homepage → Groq JSON extraction
  2. Firecrawl scrape customer pages (/customers, /case-studies, etc.)
  3. Google News RSS → article title parsing via Groq

All sources: never raise. Graceful degradation to [].
"""
import os
import re
import logging
import requests

from .router import groq_json_extract
from .signal_detector import _google_news_rss

logger = logging.getLogger(__name__)

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_API_URL = os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002")

_firecrawl_warned    = False  # print the warning once, not once per URL
_firecrawl_available = True   # set False after first failure — skip all subsequent attempts

_CUSTOMER_PATHS = [
    "/customers",
    "/case-studies",
    "/success-stories",
    "/clients",
    "/about/customers",
    "/customer-stories",
]

_EXTRACT_PROMPT = (
    "From the text below, extract every person or company explicitly mentioned as a customer, "
    "in a testimonial, or in a case study. "
    "DO NOT include employees, investors, partners, or news sources. "
    "ONLY confirmed paying customers with a quote, testimonial, or case study. "
    "Return JSON array only — no explanation, no markdown:\n"
    '[{{"name":"First Last","company":"Company Name","title":"their job title"}}]\n'
    "If no confirmed customers, return exactly: []\n\n"
    "Text:\n{content}"
)

_NEWS_EXTRACT_PROMPT = (
    "From these news headlines about {company}, extract company names that appear to be "
    "customers or clients.\n"
    'Return JSON array only: [{{"name":"","company":"Company Name","title":""}}]\n'
    "If none, return: []\n\n"
    "Headlines:\n{headlines}"
)


def _build_firecrawl_app():
    """
    Build a Firecrawl client. Tries v2 API (Firecrawl class) first, falls back to v1 (FirecrawlApp).
    Cloud (FIRECRAWL_API_KEY set) takes priority over self-hosted (FIRECRAWL_API_URL).
    """
    kwargs = {"api_key": FIRECRAWL_API_KEY} if FIRECRAWL_API_KEY else {"api_url": FIRECRAWL_API_URL}
    try:
        from firecrawl import Firecrawl  # v2 SDK
        return Firecrawl(**kwargs), "v2"
    except (ImportError, TypeError):
        from firecrawl import FirecrawlApp  # v1 SDK
        return FirecrawlApp(**kwargs), "v1"


def _fetch_markdown_firecrawl(url: str) -> str | None:
    """
    Scrape URL via Firecrawl (cloud or self-hosted). Returns markdown or None.
    Priority: FIRECRAWL_API_KEY (cloud, no Docker) → FIRECRAWL_API_URL (local Docker).
    Handles both firecrawl-py v1 (FirecrawlApp / scrape_url) and v2 (Firecrawl / scrape).
    """
    global _firecrawl_warned, _firecrawl_available
    if not _firecrawl_available:
        return None  # already failed once — skip to avoid hanging on every URL
    try:
        app, api_version = _build_firecrawl_app()
        result = app.scrape(url, formats=["markdown"]) if api_version == "v2" \
            else app.scrape_url(url, formats=["markdown"])
        content = (
            getattr(result, "markdown", None)
            or (result.get("markdown", "") if isinstance(result, dict) else "")
            or ""
        )
        return content or None
    except Exception as e:
        _firecrawl_available = False  # don't try again for any subsequent URL
        if not _firecrawl_warned:
            if FIRECRAWL_API_KEY:
                print(
                    f"  ⚠ Firecrawl cloud failed — check your FIRECRAWL_API_KEY is valid. "
                    f"Error: {e}"
                )
            else:
                print(
                    f"  ⚠ Firecrawl not reachable at {FIRECRAWL_API_URL} — "
                    f"falling back to direct HTTP scrape (JS-rendered pages may miss content). "
                    f"Fix: add FIRECRAWL_API_KEY=fc-xxx to .env (free at firecrawl.dev) "
                    f"OR start Docker: docker-compose up -d"
                )
            _firecrawl_warned = True
        logger.debug("Firecrawl failed for %s: %s", url, e)
        return None


def _fetch_text_requests(url: str) -> str | None:
    """Fallback: direct HTTP fetch + strip HTML tags. Same pattern as fetch_article_excerpt."""
    try:
        r = requests.get(
            url, timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None
        html = r.text
        html = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000] if text else None
    except Exception as e:
        logger.debug("requests fetch failed for %s: %s", url, e)
        return None


def _fetch_page(url: str) -> str | None:
    """Try Firecrawl first (richer markdown), fall back to direct requests."""
    content = _fetch_markdown_firecrawl(url)
    return content if content else _fetch_text_requests(url)


def _clean_results(raw: list, source: str) -> list[dict]:
    """Validate and tag extracted customer records."""
    if not isinstance(raw, list):
        return []
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        company = (r.get("company") or "").strip()
        if not company or company.lower() in ("", "unknown", "n/a", "company name"):
            continue
        out.append({
            "name":    (r.get("name")  or "").strip(),
            "company": company,
            "title":   (r.get("title") or "").strip(),
            "source":  source,
        })
    return out


def _source_1_homepage(domain: str) -> list[dict]:
    content = _fetch_page(f"https://{domain}")
    if not content:
        return []
    raw = groq_json_extract(_EXTRACT_PROMPT.format(content=content[:4000]), max_tokens=600)
    return _clean_results(raw, "homepage")


def _source_2_customer_pages(domain: str) -> list[dict]:
    for path in _CUSTOMER_PATHS:
        content = _fetch_page(f"https://{domain}{path}")
        if content and len(content) > 200:
            raw = groq_json_extract(_EXTRACT_PROMPT.format(content=content[:4000]), max_tokens=600)
            results = _clean_results(raw, f"page:{path}")
            if results:
                return results
    return []


def _source_3_google_news(company_name: str) -> list[dict]:
    titles = _google_news_rss(
        f'"{company_name}" customer OR "case study" OR testimonial',
        max_items=8,
    )
    if not titles:
        return []
    headlines = "\n".join(f"- {t}" for t in titles[:8])
    raw = groq_json_extract(
        _NEWS_EXTRACT_PROMPT.format(company=company_name, headlines=headlines),
        max_tokens=300,
    )
    return _clean_results(raw, "google_news")


def _deduplicate(customers: list[dict]) -> list[dict]:
    """Deduplicate by company name (case-insensitive). First occurrence wins."""
    seen: set[str] = set()
    out = []
    for c in customers:
        key = c["company"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _has_direct_source(customers: list[dict]) -> bool:
    """True if at least one customer came from homepage or a customer page (not Google News only)."""
    return any(
        c["source"] == "homepage" or c["source"].startswith("page:")
        for c in customers
    )


def research_target(domain: str, company_name: str) -> list[dict]:
    """
    Find confirmed customers of a target company from public sources.
    Returns [{name, company, title, source}]. Never raises. Returns [] on total failure.
    Typical runtime: 5–15 seconds.

    Returns [] if only Google News results are found — Google News mentions are too noisy
    to use as ICP seeds. Callers should fall back to verified hardcoded data in that case.
    Direct sources (homepage, /customers page) are required for confident results.
    """
    results: list[dict] = []
    results.extend(_source_1_homepage(domain))
    results.extend(_source_2_customer_pages(domain))
    results.extend(_source_3_google_news(company_name))
    deduped = _deduplicate(results)

    if deduped and not _has_direct_source(deduped):
        logger.info(
            "research_target: only Google News results for %s — "
            "too noisy for ICP seeds, returning [] to trigger hardcoded fallback",
            domain,
        )
        return []

    return deduped
