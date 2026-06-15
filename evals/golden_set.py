"""
Golden dataset for the SignalOS offline eval.

Each case ships with hand-authored `Signals` (NOT auto-detected) so the eval is
deterministic and offline — it measures the *reasoning layer* (does the LLM score
the right companies high and the wrong ones low?), not the flaky live scrapers.

Why this design: live signal detection hits Google News / ATS APIs that change
daily → non-deterministic, slow, and it conflates scraper bugs with scoring
quality. Fixing the signals isolates exactly what we want to regression-test.

Labels are bands, not exact scores, because Groq scoring runs at temperature 0.2
and jitters ±1 between runs. Band matching absorbs that jitter.

    high   → expect score 7-10   (multiple converging buying signals)
    medium → expect score 4-6    (one or two moderate signals)
    low    → expect score 1-3    (no / weak signals — not in-market)

`expected_top_signal` is only set where one signal clearly dominates; it is
matched leniently (case-insensitive substring) in metrics.py.
"""
from dataclasses import dataclass, field
from typing import Optional

from scorer.models import Signals

BAND_RANGES = {
    "high":   (7, 10),
    "medium": (4, 6),
    "low":    (1, 3),
}


@dataclass
class EvalCase:
    company_name: str
    domain: str
    signals: Signals
    expected_band: str                       # "high" | "medium" | "low"
    note: str                                # why this case has this label
    expected_top_signal: Optional[str] = None  # leniently matched, optional


# ── HIGH band — multiple converging signals, clearly in-market ────────────────
_HIGH = [
    EvalCase(
        "Northbeam", "northbeam.io",
        Signals(
            funded_90d=True, funding_stage="Series B",
            funded_90d_headline="Northbeam raises $40M Series B led by Insight Partners",
            hiring_gtm=True, open_gtm_roles=6, hiring_keywords=["SDR", "AE", "RevOps"],
            new_exec_hire=True, new_exec_name="Dana Reyes", new_exec_title="CRO",
            crm="Salesforce",  # no sales_engagement → stack gap
        ),
        "high", "Fresh Series B + 6 GTM roles + new CRO + Salesforce with no engagement tool — textbook outbound rebuild.",
        expected_top_signal="fund",
    ),
    EvalCase(
        "Mintlify", "mintlify.com",
        Signals(
            funded_90d=True, funding_stage="Series A",
            funded_90d_headline="Mintlify closes $18M Series A",
            new_exec_hire=True, new_exec_title="VP Sales",
            hiring_gtm=True, open_gtm_roles=4, hiring_keywords=["SDR", "AE"],
        ),
        "high", "Series A + new VP Sales + 4 sales hires firing together.",
        expected_top_signal="fund",
    ),
    EvalCase(
        "Vanta", "vanta.com",
        Signals(
            new_exec_hire=True, new_exec_name="Marcus Lee", new_exec_title="CRO",
            crm="Salesforce", hiring_gtm=True, open_gtm_roles=5,
            hiring_keywords=["AE", "Sales Manager", "RevOps"],
        ),
        "high", "New CRO + Salesforce with no engagement tool + 5 open AE/RevOps roles — new leader will pick the stack now.",
        expected_top_signal="exec",
    ),
    EvalCase(
        "Ramp", "ramp.com",
        Signals(
            funded_90d=True, funding_stage="Series C",
            funded_90d_headline="Ramp raises $150M Series C",
            acquisition_activity=True,
            hiring_gtm=True, open_gtm_roles=9, hiring_keywords=["SDR", "AE", "Enterprise AE"],
            news_keywords=["expansion", "international"], intent_signals_count=2,
        ),
        "high", "Late-stage raise + acquisition + 9 GTM roles + expansion intent — heavy convergence.",
    ),
    EvalCase(
        "Cribl", "cribl.io",
        Signals(
            hiring_gtm=True, open_gtm_roles=8, hiring_keywords=["SDR", "AE", "Sales Engineer"],
            new_exec_hire=True, new_exec_title="VP Revenue",
            news_keywords=["scaling", "growth"], intent_signals_count=2,
        ),
        "high", "8 GTM roles + new VP Revenue + scaling news — building a sales engine fast.",
    ),
    EvalCase(
        "Hex", "hex.tech",
        Signals(
            funded_90d=True, funding_stage="Series B",
            funded_90d_headline="Hex raises $28M Series B",
            crm="HubSpot",  # no engagement tool → gap
            hiring_gtm=True, open_gtm_roles=4, hiring_keywords=["RevOps", "AE"],
            new_exec_hire=True, new_exec_title="Head of Revenue Operations",
        ),
        "high", "Series B + HubSpot-no-engagement gap + RevOps hire — operationalizing GTM post-raise.",
    ),
    EvalCase(
        "Baseten", "baseten.co",
        Signals(
            new_exec_hire=True, new_exec_name="Priya Nair", new_exec_title="CRO",
            funded_90d=True, funding_stage="Series B",
            funded_90d_headline="Baseten raises $40M to scale AI infra",
            hiring_gtm=True, open_gtm_roles=3, hiring_keywords=["AE", "SDR"],
        ),
        "high", "New CRO + recent Series B + 3 sales hires — classic 90-day vendor-selection window.",
    ),
    EvalCase(
        "Census", "getcensus.com",
        Signals(
            crm="Salesforce", hiring_gtm=True, open_gtm_roles=6,
            hiring_keywords=["SDR", "AE", "Sales Ops"],
            funded_90d=True, funding_stage="Series B",
            funded_90d_headline="Census raises $60M Series B",
        ),
        "high", "Series B + Salesforce-no-engagement + 6 sales roles — outbound buildout underway.",
    ),
    EvalCase(
        "Clay", "clay.com",
        Signals(
            funded_90d=True, funding_stage="Series B",
            funded_90d_headline="Clay raises $46M Series B at $1.5B valuation",
            hiring_gtm=True, open_gtm_roles=7, hiring_keywords=["GTM Engineer", "AE", "SDR"],
            news_keywords=["hypergrowth", "expansion"], intent_signals_count=3,
        ),
        "high", "Big raise + 7 GTM roles + hypergrowth intent — in-market across the board.",
        expected_top_signal="fund",
    ),
    EvalCase(
        "Sardine", "sardine.ai",
        Signals(
            new_exec_hire=True, new_exec_title="VP Sales",
            hiring_gtm=True, open_gtm_roles=5, hiring_keywords=["AE", "SDR", "RevOps"],
            crm="Salesforce",
        ),
        "high", "New VP Sales + 5 GTM roles + Salesforce-no-engagement gap.",
    ),
    EvalCase(
        "Tecton", "tecton.ai",
        Signals(
            funded_90d=True, funding_stage="Series C",
            funded_90d_headline="Tecton raises $100M Series C",
            hiring_gtm=True, open_gtm_roles=6, hiring_keywords=["Enterprise AE", "SDR"],
            new_exec_hire=True, new_exec_title="Chief Revenue Officer",
        ),
        "high", "Series C + new CRO + 6 enterprise GTM roles.",
    ),
    EvalCase(
        "Pylon", "usepylon.com",
        Signals(
            funded_90d=True, funding_stage="Series A",
            funded_90d_headline="Pylon raises $17M Series A led by a16z",
            hiring_gtm=True, open_gtm_roles=4, hiring_keywords=["AE", "SDR"],
            news_keywords=["expansion"], intent_signals_count=1,
        ),
        "high", "Series A + 4 sales roles + expansion intent — clear post-raise outbound push.",
    ),
]

# ── MEDIUM band — one or two moderate signals, worth a look but not urgent ─────
_MEDIUM = [
    EvalCase(
        "Linear", "linear.app",
        Signals(hiring_gtm=True, open_gtm_roles=2, hiring_keywords=["AE"]),
        "medium", "Light hiring only (2 roles), no funding/exec/stack gap.",
    ),
    EvalCase(
        "Retool", "retool.com",
        Signals(
            funded_90d=True, funding_stage="Series A",
            funded_90d_headline="Retool raises $20M Series A",
        ),
        "medium", "Funding only — no hiring, exec, or stack signal to compound it.",
    ),
    EvalCase(
        "Webflow", "webflow.com",
        Signals(new_exec_hire=True, new_exec_title="VP Marketing"),
        "medium", "Single adjacent exec hire (Marketing, not Sales) — weak GTM urgency.",
    ),
    EvalCase(
        "Amplitude", "amplitude.com",
        Signals(crm="Salesforce", sales_engagement="Outreach", hiring_gtm=True, open_gtm_roles=1),
        "medium", "Complete stack (no gap) + one open role — established motion, low urgency.",
    ),
    EvalCase(
        "Notion", "notion.so",
        Signals(news_keywords=["expansion", "new market"], intent_signals_count=1),
        "medium", "Expansion intent news only — directional but unconfirmed.",
    ),
    EvalCase(
        "Airtable", "airtable.com",
        Signals(
            hiring_gtm=True, open_gtm_roles=3, hiring_keywords=["AE", "SDR"],
            crm="Salesforce", sales_engagement="Salesloft",
        ),
        "medium", "Three roles but complete stack already — expanding, not rebuilding.",
    ),
    EvalCase(
        "Loom", "loom.com",
        Signals(funded_90d=True, funding_stage="Seed", news_keywords=["growth"], intent_signals_count=1),
        "medium", "Seed-stage raise + soft growth intent — early, small budget.",
    ),
    EvalCase(
        "Calendly", "calendly.com",
        Signals(new_exec_hire=True, new_exec_title="VP Sales", crm="HubSpot", sales_engagement="Salesloft"),
        "medium", "New VP Sales but stack already complete — leader may not re-buy tooling.",
    ),
]

# ── LOW band — no or non-buying signals, not in-market ────────────────────────
_LOW = [
    EvalCase(
        "Wikipedia", "wikipedia.org",
        Signals(),
        "low", "No signals at all — must score at the floor.",
    ),
    EvalCase(
        "Basecamp", "basecamp.com",
        Signals(tech_stack=["Ruby on Rails", "Postgres"]),
        "low", "Engineering tech stack only, no CRM / no buying intent.",
    ),
    EvalCase(
        "Craigslist", "craigslist.org",
        Signals(crm="HubSpot", sales_engagement="Outreach"),
        "low", "Complete stack, zero change signals — nothing to act on.",
    ),
    EvalCase(
        "Hey", "hey.com",
        Signals(news_keywords=["product update"], intent_signals_count=0),
        "low", "A single non-buying news keyword — not a GTM trigger.",
    ),
    EvalCase(
        "Arc", "arc.net",
        Signals(tech_stack=["Swift", "WebKit"]),
        "low", "Consumer product tech stack, no sales motion signal.",
    ),
    EvalCase(
        "Signal", "signal.org",
        Signals(),
        "low", "Nonprofit, no signals — floor score.",
    ),
    EvalCase(
        "Obsidian", "obsidian.md",
        Signals(tech_stack=["Electron"], intent_signals_count=0),
        "low", "Solo/indie tool, tech stack only, no buying intent.",
    ),
    EvalCase(
        "Fastmail", "fastmail.com",
        Signals(crm="HubSpot"),
        "low", "CRM detected but no change/intent signal to make it timely.",
    ),
    EvalCase(
        "Ghost", "ghost.org",
        Signals(news_keywords=["open source release"], intent_signals_count=0),
        "low", "Open-source release news — not a commercial buying signal.",
    ),
    EvalCase(
        "DuckDuckGo", "duckduckgo.com",
        Signals(),
        "low", "No signals — floor score.",
    ),
]


GOLDEN_SET: list[EvalCase] = _HIGH + _MEDIUM + _LOW


def load_golden_set() -> list[EvalCase]:
    """Return the full golden set."""
    return list(GOLDEN_SET)
