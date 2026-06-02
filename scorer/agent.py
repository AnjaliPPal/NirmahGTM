"""
LangGraph batch scoring agent — fan-out / fan-in pattern.

Orchestrates: receive list of companies → score each in parallel → rank by score →
Claude synthesizes an executive brief → return ranked leads + summary.

This is the "agentic orchestration" story for FDE interviews:
"I built an agent that doesn't just score one company — it scores 50 accounts,
runs them in parallel, and briefs the VP of Sales in one call."
"""
import operator
from typing import TypedDict, Annotated, Optional

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Send
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .models import CompanyInput, ScoreResult
from .scorer import score_company, _get_client, MODEL


_SUMMARY_PROMPT = """You are a GTM intelligence analyst briefing a VP of Sales.

Top accounts by buying intent this week:
{companies_text}

Write a 2-3 sentence executive brief. What pattern do you see? What should the team prioritize first and why?
Return ONLY the brief. No preamble."""


# ── State schemas ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    companies: list[CompanyInput]
    results: Annotated[list[ScoreResult], operator.add]   # accumulated from fan-out
    ranked: list[ScoreResult]
    summary: str
    min_score: int


class SingleScoreState(TypedDict):
    company: CompanyInput
    results: Annotated[list[ScoreResult], operator.add]


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _route_to_scorers(state: AgentState) -> list:
    """Fan out: spawn one score_one node per company."""
    return [Send("score_one", {"company": c, "results": []}) for c in state["companies"]]


def _score_one(state: SingleScoreState) -> dict:
    """Score a single company. Runs concurrently across all fan-out branches."""
    result = score_company(state["company"])
    return {"results": [result]}


def _rank_results(state: AgentState) -> dict:
    """Collect accumulated results and sort by score descending."""
    sorted_results = sorted(
        [r for r in state["results"] if r.score is not None and not r.suppressed],
        key=lambda r: r.score or 0,
        reverse=True,
    )
    return {"ranked": sorted_results}


def _generate_summary(state: AgentState) -> dict:
    """Use Claude to synthesize an executive brief across the top leads."""
    min_score = state.get("min_score", 6)
    hot = [r for r in state["ranked"] if (r.score or 0) >= min_score]

    if not hot:
        return {"summary": "No companies scored at or above threshold in this batch."}

    companies_text = "\n".join(
        f"- {r.company_name} ({r.domain}): {r.score}/10 — {r.aha_moment or r.reasoning or 'no reasoning'}"
        for r in hot[:5]
    )
    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=150,
            temperature=0.3,
            messages=[{"role": "user", "content": _SUMMARY_PROMPT.format(companies_text=companies_text)}],
        )
        return {"summary": response.choices[0].message.content.strip()}
    except Exception as e:
        return {"summary": f"Summary unavailable: {e}"}


# ── Graph assembly ─────────────────────────────────────────────────────────────

def _build_graph():
    if not _LANGGRAPH_AVAILABLE:
        return None

    builder = StateGraph(AgentState)
    builder.add_node("score_one", _score_one)
    builder.add_node("rank_results", _rank_results)
    builder.add_node("generate_summary", _generate_summary)

    # Fan out from START — one score_one branch per company
    builder.add_conditional_edges(START, _route_to_scorers)
    # All branches reconverge at rank_results (results merged via operator.add)
    builder.add_edge("score_one", "rank_results")
    builder.add_edge("rank_results", "generate_summary")
    builder.add_edge("generate_summary", END)

    return builder.compile()


batch_agent = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def run_batch(companies: list[CompanyInput], min_score: int = 6) -> dict:
    """
    Score a batch of companies and return ranked results + an executive brief.

    Uses LangGraph fan-out agent when installed (parallel, production path).
    Falls back to sequential loop when LangGraph is not available (dev/test).

    Returns:
        total_scored: how many companies were scored
        hot_leads_count: how many scored >= min_score
        ranked: all results sorted by score desc
        summary: Claude's executive brief on the top leads
    """
    if _LANGGRAPH_AVAILABLE and batch_agent is not None:
        # ── LangGraph path: parallel fan-out ─────────────────────────────────
        state = batch_agent.invoke({
            "companies": companies,
            "results": [],
            "ranked": [],
            "summary": "",
            "min_score": min_score,
        })
        hot = [r for r in state["ranked"] if (r.score or 0) >= min_score]
        return {
            "total_scored": len(state["results"]),
            "hot_leads_count": len(hot),
            "ranked": state["ranked"],
            "summary": state["summary"],
        }

    # ── Sequential fallback (no langgraph installed) ──────────────────────────
    results = [score_company(c) for c in companies]
    ranked_state: dict = {
        "results": results,
        "ranked": [],
        "min_score": min_score,
    }
    ranked_state.update(_rank_results(ranked_state))  # type: ignore[arg-type]
    ranked_state.update(_generate_summary(ranked_state))  # type: ignore[arg-type]

    hot = [r for r in ranked_state["ranked"] if (r.score or 0) >= min_score]
    return {
        "total_scored": len(results),
        "hot_leads_count": len(hot),
        "ranked": ranked_state["ranked"],
        "summary": ranked_state["summary"],
    }
