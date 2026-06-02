"""
Waterfall enrichment: free APIs first, Firecrawl scraper as last resort.

Tier 1 (free, instant):  Hunter.io   — 50 credits/month per account
Tier 2 (free, instant):  Apollo.io   — 50 data credits/month per account
Tier 3 (self-hosted):    Firecrawl   — scrapes company website (Docker or Render/Railway free tier)
Tier 4:                  Graceful empty return

Apollo free tier: 50 DATA credits/month per account (not email sending credits). Each company org
lookup uses 1-2 data credits, so roughly 25-50 companies per account per month. Across 10 accounts:
approximately 250-500 companies per month realistic.

Hunter.io free tier: 50 credits/month per account, renewing monthly. Across 10 accounts:
approximately 500 domain lookups per month.

This waterfall cuts API spend by 60%+ vs hitting paid APIs on every lead.
"""
import os
import re
import logging
import requests
from .models import EnrichmentData

logger = logging.getLogger(__name__)

HUNTER_API_KEY    = os.environ.get("HUNTER_API_KEY", "")
APOLLO_API_KEY    = os.environ.get("APOLLO_API_KEY", "")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_API_URL = os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002")

_GTM_TITLES = {"vp", "director", "head", "chief", "cro", "ceo", "coo", "president", "revenue", "sales"}


def _hunter_lookup(domain: str) -> tuple[str | None, str | None, str | None, list[dict]]:
    """Returns primary contact (name, title, email) + up to 3 contacts list. One API call."""
    if not HUNTER_API_KEY:
        return None, None, None, []
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=5,
        )
        if r.status_code != 200:
            return None, None, None, []
        emails = r.json().get("data", {}).get("emails", [])
        # GTM-title contacts first, then others — build up to 3
        gtm = [c for c in emails if any(t in (c.get("position") or "").lower() for t in _GTM_TITLES)]
        other = [c for c in emails if c not in gtm]
        contacts = [
            {
                "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                "title": c.get("position") or "",
                "email": c.get("value") or "",
            }
            for c in (gtm + other)[:3]
        ]
        # Primary = first GTM contact, fall back to first contact
        primary = next(
            (c for c in emails if any(t in (c.get("position") or "").lower() for t in _GTM_TITLES)),
            emails[0] if emails else None,
        )
        if primary:
            name = f"{primary.get('first_name', '')} {primary.get('last_name', '')}".strip()
            return name or None, primary.get("position"), primary.get("value"), contacts
    except Exception as e:
        logger.warning("Hunter lookup failed for %s: %s", domain, e)
    return None, None, None, []


def _apollo_lookup(domain: str) -> tuple[int | None, str | None]:
    if not APOLLO_API_KEY:
        return None, None
    try:
        r = requests.post(
            "https://api.apollo.io/v1/organizations/enrich",
            json={"domain": domain},
            headers={"X-Api-Key": APOLLO_API_KEY, "Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code == 429:
            logger.warning("Apollo rate limit hit for %s", domain)
            return None, None
        if r.status_code != 200:
            logger.warning("Apollo returned %s for %s", r.status_code, domain)
            return None, None
        org = r.json().get("organization") or {}
        return org.get("estimated_num_employees"), org.get("industry")
    except Exception as e:
        logger.warning("Apollo lookup failed for %s: %s", domain, e)
    return None, None


def _firecrawl_scrape(domain: str) -> EnrichmentData:
    """Tier 3: Firecrawl scraper (cloud or self-hosted). Never raises."""
    try:
        kwargs = {"api_key": FIRECRAWL_API_KEY} if FIRECRAWL_API_KEY else {"api_url": FIRECRAWL_API_URL}
        try:
            from firecrawl import Firecrawl
            app = Firecrawl(**kwargs)
            result = app.scrape(f"https://{domain}", formats=["markdown"])
        except (ImportError, TypeError):
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(**kwargs)
            result = app.scrape_url(f"https://{domain}", formats=["markdown"])
        content = (
            getattr(result, "markdown", None)
            or (result.get("markdown", "") if isinstance(result, dict) else "")
            or ""
        )
        if not content:
            return EnrichmentData(enriched=False)
        m_emp = re.search(r'(\d[\d,]+)\s+employees', content, re.IGNORECASE)
        m_ind = re.search(r'(?:Industry|Sector)[:\s]+([^\n.]{3,40})', content, re.IGNORECASE)
        employee_count = int(m_emp.group(1).replace(",", "")) if m_emp else None
        industry = m_ind.group(1).strip() if m_ind else None
        return EnrichmentData(
            employee_count=employee_count,
            industry=industry,
            enriched=bool(employee_count or industry),
        )
    except Exception as e:
        logger.error("Firecrawl scrape failed for %s: %s", domain, e)
        return EnrichmentData(enriched=False)


def enrich_company(domain: str) -> EnrichmentData:
    """
    Waterfall: Hunter → Apollo → Firecrawl → empty.
    Each tier is tried only if the previous returned no data.
    """
    name, title, email, contacts = _hunter_lookup(domain)
    employee_count, industry = _apollo_lookup(domain)

    # Fall back to Firecrawl when org data (headcount/industry) is missing
    if not employee_count and not industry:
        scraped = _firecrawl_scrape(domain)
        if scraped.enriched:
            employee_count = scraped.employee_count
            industry = scraped.industry

    enriched = any([name, email, employee_count, industry])
    return EnrichmentData(
        decision_maker_name=name,
        decision_maker_title=title,
        decision_maker_email=email,
        employee_count=employee_count,
        industry=industry,
        contacts=contacts,
        enriched=enriched,
    )
