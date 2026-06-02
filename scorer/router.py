"""
Multi-LLM router — routes each task to the cheapest capable model.

  Pre-filter  → GPT-4o-mini ($0.15/1M in) or rule-based fallback (free)
  Scoring     → Groq llama-3.3-70b-versatile (free tier) — handled in scorer.py
  Opener      → Groq llama-3.1-8b-instant (free tier — fast, lower quota cost)
"""
import os
import json
import logging
import re

logger = logging.getLogger(__name__)
from groq import Groq
from .models import Signals

_openai_client = None
_groq_opener_client = None

GEMINI_OPENER_MODEL = "llama-3.1-8b-instant"

_PRE_FILTER_PROMPT = """You are a B2B sales signal analyst. Does this company have any GTM buying signals worth a detailed AI score?

Signals detected:
{signals_summary}

Reply with exactly one word: YES or NO."""


def _get_openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    try:
        from openai import OpenAI
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return None
        _openai_client = OpenAI(api_key=key)
        return _openai_client
    except ImportError:
        return None


def _get_groq_opener() -> Groq:
    global _groq_opener_client
    if _groq_opener_client is None:
        _groq_opener_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_opener_client


def _summarize_signals(signals: Signals) -> str:
    parts = []
    if signals.hiring_gtm:
        parts.append(f"hiring GTM ({signals.open_gtm_roles} open roles)")
    if signals.funded_90d:
        parts.append(f"funded recently ({signals.funding_stage or 'unknown stage'})")
    if signals.new_exec_hire:
        parts.append(f"new exec hired: {signals.new_exec_title or 'unknown title'}")
    if signals.tech_stack:
        parts.append(f"tech stack: {', '.join(signals.tech_stack[:3])}")
    if signals.news_keywords:
        parts.append(f"news signals: {', '.join(signals.news_keywords[:3])}")
    if signals.intent_signals_count > 0:
        parts.append(f"{signals.intent_signals_count} intent signal(s)")
    return "\n".join(f"- {p}" for p in parts) if parts else "- No signals detected"


def pre_filter(signals: Signals) -> tuple[bool, str, float]:
    """
    Decide whether the company is worth scoring.

    Returns (should_score, reason, cost_usd).
    Uses GPT-4o-mini when OPENAI_API_KEY is set; rule-based fallback otherwise.
    Always fails open on API error so accounts are never silently dropped.
    """
    client = _get_openai()

    if client is None:
        active = sum([
            bool(signals.hiring_gtm),
            bool(signals.funded_90d),
            bool(signals.new_exec_hire),
            bool(signals.tech_stack),
            bool(signals.news_keywords),
            signals.intent_signals_count > 0,
        ])
        if active == 0:
            return False, "rule-based: no signals detected", 0.0
        return True, f"rule-based: {active} signal(s) detected", 0.0

    summary = _summarize_signals(signals)
    prompt = _PRE_FILTER_PROMPT.format(signals_summary=summary)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=5,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.choices[0].message.content.strip().upper()
        cost = (
            resp.usage.prompt_tokens * 0.00000015 +
            resp.usage.completion_tokens * 0.0000006
        )
        if "YES" in answer:
            return True, "gpt-4o-mini: signals detected", cost
        return False, "gpt-4o-mini: insufficient signals", cost
    except Exception as e:
        return True, f"pre-filter error (fail open): {e}", 0.0


def generate_opener_gemini(opener_prompt: str) -> tuple[str | None, float]:
    """Generate email opener using Groq llama-3.1-8b-instant — free, fast."""
    try:
        resp = _get_groq_opener().chat.completions.create(
            model=GEMINI_OPENER_MODEL,
            max_tokens=80,
            temperature=0.7,
            messages=[{"role": "user", "content": opener_prompt}],
        )
        return resp.choices[0].message.content.strip(), 0.0
    except Exception as e:
        logger.warning("generate_opener_gemini failed: %s", e)
        return None, 0.0


def groq_json_extract(prompt: str, max_tokens: int = 500) -> list[dict]:
    """Call llama-3.1-8b-instant and parse the JSON response. Returns [] on any failure."""
    try:
        resp = _get_groq_opener().chat.completions.create(
            model=GEMINI_OPENER_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.warning("groq_json_extract failed: %s", e)
        return []
