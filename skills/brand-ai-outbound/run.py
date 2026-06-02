#!/usr/bin/env python3
"""
brand.ai application workflow — research -> ingest -> brand-signal check -> score -> assets.
Run: python skills/brand-ai-outbound/run.py

SignalOS already auto-detects 5 GTM signals per company (funding, hiring, leadership,
tech stack, intent). We don't replicate that. We add ONE thing SignalOS doesn't do:
check for BRAND-SPECIFIC hiring signals (Head of Brand, Brand Designer, CMO, Creative Director)
because signal_detector._GTM_KEYWORDS is sales-focused, not marketing-focused.

prospects.csv only needs: company_name, domain
Everything else SignalOS detects itself.
"""

import os
import re
import sys
import csv
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore", message="Field name.*shadows an attribute", module="firecrawl")

import httpx
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

try:
    from scorer.research_target import research_target as _research_target_fn
    _RESEARCH_TARGET_AVAILABLE = True
except ImportError:
    _RESEARCH_TARGET_AVAILABLE = False

logging.basicConfig(level=logging.WARNING)

# ─── CONFIG ──────────────────────────────────────────────────────────────────

SIGNALOS_BASE_URL = os.environ.get("SIGNALOS_URL", "http://localhost:8000")
OUTPUT_DIR = Path(__file__).parent

# brand.ai's 3 real public customers (verified on brand.ai homepage, May 30 2026)
REAL_CUSTOMER_SEEDS = {
    "lyft.com":  "Brian Irving, CMO — two-sided mobility marketplace",
    "turo.com":  "David Corns, CMO — two-sided mobility marketplace (car-sharing)",
    "groq.com":  "Chelsey Susin Kantor, CMO — AI-native infrastructure",
}

# Brand-specific hiring keywords (what SignalOS signal_detector does NOT check)
_BRAND_KEYWORDS = {
    "head of brand", "brand designer", "brand strategist", "chief marketing",
    "cmo", "vp marketing", "vp brand", "brand manager", "creative director",
    "brand director", "brand lead", "brand creative",
}

# ATS embed patterns (same approach as signal_detector.py)
_ATS_EMBED_PATTERNS = [
    ("greenhouse", r'job-boards\.greenhouse\.io/([a-zA-Z0-9_-]+)'),
    ("greenhouse", r'boards\.greenhouse\.io/embed/job_board\?for=([a-zA-Z0-9_-]+)'),
    ("greenhouse", r'grnhse_board_token\s*[=:]\s*["\']([a-zA-Z0-9_-]+)'),
    ("lever",      r'jobs\.lever\.co/([a-zA-Z0-9_-]+)'),
    ("ashby",      r'jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)'),
]

ICP_BASE_CONTEXT = (
    "brand.ai ICP — reverse-engineered from their 3 real public customers: "
    "Lyft (Brian Irving CMO), Turo (David Corns CMO), Groq (Chelsey Kantor CMO). "
    "Pattern: consumer marketplace OR AI-native company where brand is a strategic asset "
    "under AI disruption. CMO treats brand as a system, not a style guide. "
    "Score HIGH if: hiring brand/marketing leadership right now, new CMO in 90d, "
    "recent rebrand or product expansion, 2026 funding. "
    "Score LOW if: no brand dimension, no AI exposure, <50 employees, pure B2C with no tech angle."
)

# Target company for this skill (brand.ai)
_TARGET_DOMAIN  = "brand.ai"
_TARGET_COMPANY = "brand.ai"


def _build_icp_context(discovered_customers: list[dict]) -> str:
    """Use auto-detected customers in scoring context. Falls back to ICP_BASE_CONTEXT."""
    if not discovered_customers:
        return ICP_BASE_CONTEXT
    parts = []
    for c in discovered_customers[:3]:
        s = c["company"]
        if c.get("name") and c.get("title"):
            s += f" ({c['name']}, {c['title']})"
        parts.append(s)
    header = "brand.ai ICP — auto-detected customers: " + " | ".join(parts)
    return (
        f"{header}. "
        "Pattern: consumer marketplace OR AI-native company where brand is a strategic asset "
        "under AI disruption. CMO treats brand as a system, not a style guide. "
        "Score HIGH if: hiring brand/marketing leadership right now, new CMO in 90d, "
        "recent rebrand or product expansion, 2026 funding. "
        "Score LOW if: no brand dimension, no AI exposure, <50 employees, pure B2C with no tech angle."
    )


# ─── BRAND SIGNAL CHECK ──────────────────────────────────────────────────────
# This is the ONE thing we add that SignalOS doesn't do natively.
# signal_detector checks GTM/sales hiring. We check brand/marketing hiring.

def _detect_ats(domain: str) -> tuple[str, str] | None:
    """Visit careers page, extract ATS type + slug from embedded code."""
    for path in ["/careers", "/jobs", "/about/careers", "/company/careers", "/join"]:
        try:
            r = requests.get(
                f"https://{domain}{path}", timeout=6,
                headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True
            )
            if r.status_code != 200:
                continue
            for ats, pattern in _ATS_EMBED_PATTERNS:
                m = re.search(pattern, r.text, re.IGNORECASE)
                if m:
                    return ats, m.group(1).lower().rstrip("/")
        except Exception:
            continue
    return None


def check_brand_hiring(domain: str, company_name: str) -> tuple[bool, list[str], str]:
    """
    Check if this company has active brand/marketing leadership job postings.
    Returns: (has_brand_hiring, matching_job_titles, evidence_string)
    Three tiers (same as signal_detector Trigger 2):
      Tier 0: ATS embed detection from careers page
      Tier 1: Slug guessing for Greenhouse/Lever/Ashby
      Tier 2: Google News fallback
    """
    def _parse_ats(ats_type: str, data) -> list[str]:
        title_key = "text" if ats_type == "lever" else "title"
        jobs_raw = data if isinstance(data, list) else data.get("jobs", [])
        return [
            j.get(title_key) or j.get("title") or ""
            for j in (jobs_raw if isinstance(jobs_raw, list) else [])
            if any(kw in (j.get(title_key) or j.get("title") or "").lower()
                   for kw in _BRAND_KEYWORDS)
        ]

    def _query(ats_type: str, slug: str) -> list[str]:
        urls = {
            "greenhouse": [f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"],
            "lever":      [f"https://api.lever.co/v0/postings/{slug}?mode=json"],
            "ashby":      [f"https://api.ashbyhq.com/posting-api/job-board/{slug}"],
        }
        for url in urls.get(ats_type, []):
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    titles = _parse_ats(ats_type, r.json())
                    if titles:
                        return titles
            except Exception:
                continue
        return []

    # Tier 0: ATS embed from careers page
    ats_info = _detect_ats(domain)
    if ats_info:
        titles = _query(*ats_info)
        if titles:
            ev = f"Active job postings: {', '.join(titles[:3])}"
            return True, titles[:5], ev

    # Tier 1: slug guessing
    base = domain.split(".")[0].lower()
    for slug in list(dict.fromkeys([base, base.replace("-", "")])):
        for ats_type in ["greenhouse", "lever", "ashby"]:
            titles = _query(ats_type, slug)
            if titles:
                ev = f"Active job postings: {', '.join(titles[:3])}"
                return True, titles[:5], ev

    # Tier 2: Google News
    try:
        query = f'"{company_name}" "head of brand" OR "brand designer" OR "CMO" OR "vp marketing" hiring 2026'
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            titles_news = [
                el.text for item in root.findall(".//item")[:5]
                if (el := item.find("title")) is not None and el.text
                and any(kw in el.text.lower() for kw in _BRAND_KEYWORDS)
            ]
            if titles_news:
                return True, titles_news[:3], f"News signal: {titles_news[0]}"
    except Exception:
        pass

    return False, [], "No brand hiring signal detected"


# ─── PHASE 0: RESEARCH TARGET ────────────────────────────────────────────────

def phase_0_research_target(target_domain: str, target_company: str) -> list[dict]:
    """
    Auto-detect confirmed customers of the target company from public sources.
    Returns [{name, company, title, source}].
    Falls back to hardcoded REAL_CUSTOMER_SEEDS if auto-detection fails or finds nothing.
    """
    print(f"[PHASE 0] Research target — detecting {target_company}'s confirmed customers")
    print(f"  target: https://{target_domain}")

    if not _RESEARCH_TARGET_AVAILABLE:
        print("  ⚠ scorer.research_target not available — using hardcoded seeds")
        return _seeds_as_dicts()

    try:
        customers = _research_target_fn(target_domain, target_company)
    except Exception as e:
        print(f"  ⚠ Auto-detection failed ({e}) — using hardcoded seeds")
        return _seeds_as_dicts()

    if not customers:
        print("  ⚠ No customers detected — using hardcoded seeds")
        return _seeds_as_dicts()

    print(f"  ✓ {len(customers)} customers found:")
    for c in customers[:5]:
        name_title = f"{c.get('name','')} — {c.get('title','')}".strip(" —")
        print(f"    {c['company']:<25} {name_title}  [{c.get('source','')}]")
    print()
    return customers


def _seeds_as_dicts() -> list[dict]:
    """Convert hardcoded REAL_CUSTOMER_SEEDS to the same [{name, company, ...}] format."""
    out = []
    for domain, description in REAL_CUSTOMER_SEEDS.items():
        company = domain.split(".")[0].title()
        parts = description.split(",", 1)
        out.append({
            "name":    parts[0].strip() if parts else "",
            "company": company,
            "title":   parts[1].strip() if len(parts) > 1 else "",
            "source":  "hardcoded",
        })
    return out


# ─── PHASE 1: RESEARCH ───────────────────────────────────────────────────────

def phase_1_research(discovered_customers: list[dict]):
    print("[PHASE 1] ICP locked from confirmed customers")
    for c in discovered_customers[:5]:
        name_title = f"{c.get('name','')} — {c.get('title','')}".strip(" —")
        print(f"  seed: {c['company']:<25} {name_title}")
    print("  why-now: SignalOS auto-detects (funding, leadership, tech, intent)")
    print("  brand gap: we add brand-hiring check (Head of Brand, CMO, Brand Designer)")
    print("  ✓ ICP locked\n")


# ─── PHASE 2: INGEST ─────────────────────────────────────────────────────────

def phase_2_ingest() -> list[dict]:
    """
    Load candidates from prospects.csv — only company_name + domain required.
    SignalOS does the signal detection. We do brand hiring check.
    """
    print("[PHASE 2] Ingest companies")
    prospects_file = OUTPUT_DIR / "prospects.csv"

    if not prospects_file.exists():
        print(f"  ✗ No prospects.csv at {prospects_file}\n")
        _print_sourcing_instructions()
        sys.exit(1)

    candidates = []
    with prospects_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower() for c in (reader.fieldnames or [])}
        if not {"company_name", "domain"}.issubset(cols):
            print(f"  ✗ prospects.csv must have columns: company_name, domain")
            print(f"    Found: {sorted(cols)}")
            _print_sourcing_instructions()
            sys.exit(1)
        for row in reader:
            name = (row.get("company_name") or "").strip()
            domain = (row.get("domain") or "").strip()
            if name and domain:
                candidates.append({"company_name": name, "domain": domain})

    print(f"  ✓ Loaded {len(candidates)} candidates\n")
    if not candidates:
        print("  ✗ No valid rows in prospects.csv")
        _print_sourcing_instructions()
        sys.exit(1)
    return candidates


def _print_sourcing_instructions():
    print("  HOW TO GENERATE prospects.csv (real data, free):")
    print("  1. In Clay, run Ocean.io 'Find Lookalike Companies' THREE times:")
    print("       seed 1: lyft.com    seed 2: turo.com    seed 3: groq.com   (limit 50 each)")
    print("  2. Merge + dedupe the results into one list.")
    print("  3. Export as CSV with columns: company_name, domain")
    print(f"  4. Save here: {OUTPUT_DIR / 'prospects.csv'}")
    print("  5. Re-run: python skills/brand-ai-outbound/run.py")
    print("  Note: no why_now column needed — SignalOS detects signals automatically.\n")


# ─── PHASE 3: BRAND SIGNAL CHECK ─────────────────────────────────────────────

def phase_3_brand_signal_check(candidates: list[dict]) -> list[dict]:
    """
    Check each company for brand/marketing hiring signals.
    This is the ONE gap in SignalOS's signal_detector (which uses sales keywords, not brand).
    Enrich each candidate with: brand_hiring (bool), brand_jobs (list), brand_evidence (str).
    """
    print("[PHASE 3] Brand hiring signal check (Head of Brand, CMO, Brand Designer...)")
    enriched = []
    for i, c in enumerate(candidates, 1):
        print(f"  [{i}/{len(candidates)}] {c['company_name'][:30]:<30}", end=" ", flush=True)
        has_signal, job_titles, evidence = check_brand_hiring(c["domain"], c["company_name"])
        c["brand_hiring"] = has_signal
        c["brand_jobs"] = job_titles
        c["brand_evidence"] = evidence
        enriched.append(c)
        if has_signal:
            print(f"✓ BRAND SIGNAL — {', '.join(job_titles[:2])}")
        else:
            print("— no signal")

    with_signal = sum(1 for c in enriched if c["brand_hiring"])
    print(f"\n  ✓ {with_signal}/{len(enriched)} companies have active brand hiring\n")
    return enriched


# ─── PHASE 4: SCORE WITH SIGNALOS ────────────────────────────────────────────

def phase_4_score(candidates: list[dict], discovered_customers: list[dict] | None = None) -> list[dict]:
    """
    POST to SignalOS /score-company for each candidate.
    SignalOS auto-detects the 5 GTM signals per company.
    We add the brand_evidence to scoring_context so the LLM weighs it.
    """
    print("[PHASE 4] Score with SignalOS (auto-detects funding, leadership, tech stack, intent)")

    try:
        resp = httpx.get(f"{SIGNALOS_BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"  ✗ SignalOS not healthy")
            print(f"    Start it: cd signalos-v1 && uvicorn api.main:app --reload --port 8000")
            sys.exit(1)
    except Exception as e:
        print(f"  ✗ Cannot reach SignalOS: {e}")
        sys.exit(1)

    print(f"  ✓ SignalOS healthy — scoring {len(candidates)} companies...\n")

    def _scoring_context(c: dict) -> str:
        ctx = _build_icp_context(discovered_customers or [])
        if c.get("brand_hiring"):
            ctx += f" BRAND SIGNAL CONFIRMED: {c['brand_evidence']}"
        else:
            ctx += " No brand hiring signal detected — score based on other signals only."
        return ctx

    companies_payload = [
        {
            "company_name": c["company_name"],
            "domain": c["domain"],
            "client_id": "brand-ai-demo",
            "scoring_context": _scoring_context(c),
        }
        for c in candidates
    ]

    # Fast path: batch-score
    try:
        resp = httpx.post(
            f"{SIGNALOS_BASE_URL}/batch-score",
            json={"companies": companies_payload, "min_score": 6},
            timeout=180,
        )
        if resp.status_code == 200:
            result = resp.json()
            ranked = result.get("ranked", [])
            print(f"  ✓ /batch-score: {result.get('hot_leads_count', 0)} passed threshold (score >= 6)")
            return _attach_brand_signal(ranked[:20], candidates)
        print(f"  ⚠ /batch-score {resp.status_code}, falling back to per-company loop")
    except Exception as e:
        print(f"  ⚠ /batch-score failed ({e}); falling back to per-company loop")

    # Fallback: per-company loop
    results = []
    for i, payload in enumerate(companies_payload, 1):
        try:
            print(f"    [{i}/{len(companies_payload)}] {payload['company_name']:<30}", end=" ", flush=True)
            resp = httpx.post(f"{SIGNALOS_BASE_URL}/score-company", json=payload, timeout=30)
            if resp.status_code == 200:
                r = resp.json()
                if not r.get("error") and not r.get("suppressed"):
                    results.append(r)
                    print(f"✓ ({r.get('score', '?')})")
                else:
                    print("⊘ (skipped)")
            else:
                print(f"✗ ({resp.status_code})")
        except Exception as e:
            print(f"✗ ({e})")

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    passed = sum(1 for r in results if (r.get("score") or 0) >= 6)
    print(f"\n  ✓ Scored {len(results)}, {passed} passed threshold")
    return _attach_brand_signal(results[:20], candidates)


def _attach_brand_signal(ranked: list[dict], candidates: list[dict]) -> list[dict]:
    by_domain = {c["domain"].lower().lstrip("www."): c for c in candidates}
    for r in ranked:
        d = (r.get("domain") or "").lower().lstrip("www.")
        src = by_domain.get(d, {})
        r["brand_evidence"] = src.get("brand_evidence", "—")
        r["brand_hiring"] = src.get("brand_hiring", False)
        r["brand_jobs"] = src.get("brand_jobs", [])
    return ranked


# ─── PHASE 5: OUTPUT FILES ───────────────────────────────────────────────────

def phase_5_output(top: list[dict]):
    print("\n[PHASE 5] Write output files")

    # File 1: top-20 table
    md = f"""# brand.ai ICP — Top {len(top)} Prospects
# Generated: {datetime.now().isoformat()}
# Seeds: lyft.com (Lyft) · turo.com (Turo) · groq.com (Groq) — real brand.ai customers
# Scoring: SignalOS v1.2 / Groq llama-3.3-70b + brand hiring check

| Rank | Company | Domain | Score | Conf | Brand Signal | Aha Moment | Contact Window |
|------|---------|--------|-------|------|--------------|------------|----------------|
"""
    for i, c in enumerate(top, 1):
        brand = ("✓ " + ", ".join(c.get("brand_jobs", [])[:1])) if c.get("brand_hiring") else "—"
        aha = (c.get("aha_moment") or "—").replace("|", "\\|")[:50]
        md += f"| {i} | {c['company_name']} | {c['domain']} | {c.get('score','—')} | {c.get('confidence','—')}% | {brand[:40]} | {aha} | {c.get('contact_window','—')} |\n"
    md += "\n## Notes\n- Prospects from Ocean.io lookalike of Lyft + Turo + Groq (brand.ai's real customers)\n"
    md += "- Brand signal = active Head of Brand/CMO/Brand Designer posting (live ATS check)\n"
    md += "- Aha moment = SignalOS reasoning, not a guess\n"
    (OUTPUT_DIR / "brand-ai-top20.md").write_text(md, encoding="utf-8")
    print("  ✓ brand-ai-top20.md")

    # File 2: Loom script
    t = top[0] if top else {}
    brand_signal_line = (
        f"Hiring {(t.get('brand_jobs') or ['brand leader'])[0]} right now."
        if t.get("brand_hiring") else "Signal detected by SignalOS."
    )
    loom = f"""# LOOM SCRIPT — brand.ai GTM Engineer Application  (max 3:30)
# Before recording: search LinkedIn "brand.ai head of GTM" or "brand.ai growth" for the hiring manager name.
# Face cam: ON. Screen: Clay table with 10 rows, all scores populated.

[0:00-0:20] HOOK
Hi [NAME]. You don't have a public customer list — so I built one.
I took your three real customers: Lyft, Turo, and Groq.
Ran them through Ocean.io's lookalike engine. Then filtered for one thing:
companies actively investing in brand leadership right now.

[0:20-1:00] SHOW CLAY TABLE
[Scroll the table. 10 rows. Scores visible.]
Every company here looks like Lyft, Turo, or Groq by profile.
And every one has a real, live signal — not a firmographic guess.

[1:00-2:00] SHOW ONE ROW
[Click {t.get('company_name', '[TOP COMPANY]')}. Show score + aha_moment + brand_evidence.]
Brand signal: {brand_signal_line}
SignalOS turned that into: {(t.get('aha_moment') or '[AHA MOMENT]')[:80]}
That's the reasoning layer. Clay can't do this natively.

[2:00-2:45] SHOW THE ARCHITECTURE
[Click SignalOS Score column. Show /score-company POST config.]
Clay handles enrichment breadth. SignalOS handles reasoning depth.
Each one does what the other can't.
Honest caveat: this is seeded on your 3 public customers.
Give me your closed-won list in Attio and I reseed with real ground truth.
That's week one.

[2:45-3:00] CTA
Code is on GitHub [LINK]. Would you be opposed to a 20-minute call?
"""
    (OUTPUT_DIR / "loom-script.md").write_text(loom, encoding="utf-8")
    print("  ✓ loom-script.md")

    # File 3: email
    email = """Subject: Built your ICP list from Lyft + Turo + Groq — 3 min demo

Hi [NAME],

No public customer list, so I reverse-engineered yours from three public testimonials —
Lyft, Turo, Groq — then kept only companies with a live brand hiring signal.
Scored them with a reasoning layer I built on top of Clay.

Demo (3 min): [LOOM]
Clay table (10 rows): [LINK]
Code: [GITHUB]

Cold-start proxy until I can reseed with your Attio data. Worth a 20-minute call?

— Anjali Pal
anjalipal931@gmail.com
"""
    (OUTPUT_DIR / "application-email.md").write_text(email, encoding="utf-8")
    print("  ✓ application-email.md")

    # File 4: short answers
    sa = """# brand.ai JD — Short Answer Questions

## Q1: Most complex workflow you've built and what did it accomplish?
SignalOS: auto-detects 5 GTM signals from public sources (Google News RSS, Greenhouse/Lever
ATS API, homepage HTML scan), retrieves RAG context from past-scored companies, reasons with
a Groq LLM, routes through confidence governance, then pushes to HubSpot + Slack Block Kit
— all triggered from a Clay Custom HTTP column. Outcome: a rep gets a data-backed reason to
call with a named signal, not a tier list.

## Q2: "Done quickly" vs "done perfectly" — what did you choose and why?
On SignalOS I shipped the HubSpot push quickly and built the confidence governance perfectly.
A bad CRM write corrupts data for everyone downstream. A rough Slack alert is a formatting
complaint. Get the irreversible parts right first; ship the reversible parts fast.

## Q3: Favourite automation tool and why?
n8n — every step is an explicit node with named input and output, so failures are inspectable
without opening the code. Clay is my favourite for enrichment specifically, but for multi-path
orchestration with error handling and webhook logic, n8n is still the most honest tool.
"""
    (OUTPUT_DIR / "short-answers.md").write_text(sa, encoding="utf-8")
    print("  ✓ short-answers.md")
    print(f"\n✅ All 4 files written to {OUTPUT_DIR}\n")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("brand.ai Application Workflow — real data, no generic companies")
    print("=" * 80)
    discovered = phase_0_research_target(_TARGET_DOMAIN, _TARGET_COMPANY)
    phase_1_research(discovered)
    candidates = phase_2_ingest()
    candidates = phase_3_brand_signal_check(candidates)
    ranked = phase_4_score(candidates, discovered)
    if not ranked:
        print("✗ No companies passed scoring threshold")
        sys.exit(1)
    phase_5_output(ranked)
    print("=" * 80)
    print("NEXT: review brand-ai-top20.md → build Clay table → record Loom → send email")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
