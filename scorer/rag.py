"""
RAG layer — embeds scored companies and retrieves similar past results for context.

Embedding model: OpenAI text-embedding-3-small (1536 dims, $0.02/1M tokens)
Storage:         Supabase pgvector column on signals table
Retrieval:       match_signals() RPC — cosine similarity, top-5 neighbors
Injection:       rag_context block injected into SCORING_PROMPT_V2

Degrades gracefully: if OPENAI_API_KEY not set or pgvector not enabled, returns
empty strings/lists — scoring continues without RAG, no exception raised.
"""
import logging
import os
from typing import Optional
from .models import ScoreResult

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIMS  = 1536

_openai_client = None


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


def embed(text: str) -> Optional[list[float]]:
    """Embed text via OpenAI. Returns None when key not set or call fails."""
    client = _get_openai()
    if client is None:
        return None
    try:
        resp = client.embeddings.create(model=_EMBED_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception:
        return None


def _result_to_text(result: ScoreResult) -> str:
    """Compact text representation of a scored company — what gets embedded."""
    parts = [
        result.company_name,
        result.domain,
        f"score:{result.score}",
        f"top_signal:{result.top_signal or 'none'}",
        f"contact_window:{result.contact_window or 'unknown'}",
    ]
    if result.reasoning:
        parts.append(result.reasoning[:150])
    return " | ".join(parts)


def _signals_to_text(company_name: str, domain: str, signals) -> str:
    """Compact text for embedding the query (before scoring)."""
    parts = [company_name, domain]
    if signals.hiring_gtm:
        parts.append(f"hiring_gtm:{signals.open_gtm_roles}_roles")
    if signals.funded_90d:
        parts.append(f"funded:{signals.funding_stage or 'unknown'}")
    if signals.new_exec_hire:
        parts.append(f"new_exec:{signals.new_exec_title or 'unknown'}")
    if signals.tech_stack:
        parts.append(f"stack:{','.join(signals.tech_stack[:3])}")
    if signals.news_keywords:
        parts.append(f"news:{','.join(signals.news_keywords[:3])}")
    return " | ".join(parts)


def store_embedding(result: ScoreResult, supabase) -> None:
    """
    Embed a scored company and persist the vector to Supabase.
    No-op if embedding unavailable or Supabase call fails.
    """
    if not result.scored or result.score is None:
        return
    vector = embed(_result_to_text(result))
    if vector is None:
        return
    try:
        supabase.table("signals").update(
            {"embedding": vector}
        ).eq("domain", result.domain).eq("client_id", result.client_id).execute()
    except Exception as e:
        logger.warning("store_embedding failed for %s: %s", result.domain, e)


def retrieve_similar(
    company_name: str,
    domain: str,
    signals,
    client_id: str,
    supabase,
    limit: int = 5,
) -> list[dict]:
    """
    Find the most similar past scored companies using pgvector cosine similarity.
    Calls the match_signals() SQL function (created in migration 005).
    Returns [] when pgvector not enabled or no similar results exist.
    """
    query_text = _signals_to_text(company_name, domain, signals)
    vector = embed(query_text)
    if vector is None:
        return []
    try:
        resp = supabase.rpc(
            "match_signals",
            {
                "query_embedding": vector,
                "match_client_id": client_id,
                "match_count": limit,
            },
        ).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("retrieve_similar failed for %s: %s", domain, e)
        return []


def format_rag_context(similar: list[dict]) -> str:
    """
    Format retrieved companies into a prompt block for Claude.
    Returns empty string when no similar companies found.
    """
    if not similar:
        return ""
    lines = [
        "\nPAST SIMILAR ACCOUNTS — use as calibration (real outcomes from your scoring history):"
    ]
    for s in similar:
        outcome = s.get("outcome") or "no_reply"
        lines.append(
            f"- {s.get('company_name', 'Unknown')} ({s.get('domain', '')}): "
            f"score {s.get('score', '?')}/10, outcome={outcome}, "
            f"top_signal={s.get('top_signal') or 'unknown'}"
        )
    return "\n".join(lines)
