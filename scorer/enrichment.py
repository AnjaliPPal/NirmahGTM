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
import requests
from .models import EnrichmentData

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
FIRECRAWL_API_URL = os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002")

_GTM_TITLES = {"vp", "director", "head", "chief", "cro", "ceo", "coo", "president", "revenue", "sales"}


def _hunter_lookup(domain: str) -> tuple[str | None, str | None, str | None]:
    if not HUNTER_API_KEY:
        return None, None, None
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=5,
        )
        if r.status_code != 200:
            return None, None, None
        emails = r.json().get("data", {}).get("emails", [])
        for contact in emails:
            title = (contact.get("position") or "").lower()
            if any(t in title for t in _GTM_TITLES):
                name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                return name or None, contact.get("position"), contact.get("value")
        if emails:
            c = emails[0]
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            return name or None, c.get("position"), c.get("value")
    except Exception:
        pass
    return None, None, None


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
        if r.status_code != 200:
            return None, None
        org = r.json().get("organization") or {}
        return org.get("estimated_num_employees"), org.get("industry")
    except Exception:
        pass
    return None, None


def _firecrawl_scrape(domain: str) -> EnrichmentData:
    """Tier 3: self-hosted Firecrawl scraper. Never raises."""
    try:
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_url=FIRECRAWL_API_URL)
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
    except Exception:
        return EnrichmentData(enriched=False)


def enrich_company(domain: str) -> EnrichmentData:
    """
    Waterfall: Hunter → Apollo → Firecrawl → empty.
    Each tier is tried only if the previous returned no data.
    """
    name, title, email = _hunter_lookup(domain)
    employee_count, industry = _apollo_lookup(domain)

    # Both paid tiers returned nothing — try Firecrawl
    if not name and not employee_count:
        scraped = _firecrawl_scrape(domain)
        if scraped.enriched:
            return EnrichmentData(
                decision_maker_name=name,
                decision_maker_title=title,
                decision_maker_email=email,
                employee_count=scraped.employee_count,
                industry=scraped.industry,
                enriched=True,
            )

    enriched = any([name, email, employee_count, industry])
    return EnrichmentData(
        decision_maker_name=name,
        decision_maker_title=title,
        decision_maker_email=email,
        employee_count=employee_count,
        industry=industry,
        enriched=enriched,
    )
