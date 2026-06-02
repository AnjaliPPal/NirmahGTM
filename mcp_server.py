"""
SignalOS MCP Server — exposes 3 tools to Claude Desktop.

Setup (add to ~/Library/Application Support/Claude/claude_desktop_config.json):

  {
    "mcpServers": {
      "signalos": {
        "command": "python",
        "args": ["/path/to/signalos-v1/mcp_server.py"],
        "env": {
          "ANTHROPIC_API_KEY": "sk-ant-...",
          "NEXT_PUBLIC_SUPABASE_URL": "https://xxx.supabase.co",
          "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_..."
        }
      }
    }
  }

Then in Claude Desktop, type naturally:
  "Score Vercel for me"
  "Show hot leads for client acme_demo"
  "Get the pitch for linear.app"
"""
import os
import sys
import json
from pathlib import Path

# Load .env if present (for local dev)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Ensure scorer package is importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "mcp package not installed.\n"
        "Run: pip install mcp>=1.0.0\n"
        "Docs: https://github.com/modelcontextprotocol/python-sdk",
        file=sys.stderr,
    )
    sys.exit(1)

from scorer.models import CompanyInput
from scorer.scorer import score_company
from api.deps import get_supabase

mcp = FastMCP(
    "SignalOS",
    instructions=(
        "You are connected to SignalOS, a B2B GTM signal intelligence engine. "
        "Use score_company to analyze buying intent for any domain. "
        "Use get_hot_leads to see which accounts are ready now. "
        "Use get_pitch to retrieve the sales pitch for a domain you've already scored."
    ),
)


@mcp.tool()
def score_company_tool(
    company_name: str,
    domain: str,
    client_id: str = "mcp_demo",
) -> str:
    """
    Score a B2B company's buying intent using 5 GTM signals and Claude reasoning.

    Auto-detects signals from public sources (Google News, Greenhouse, website scan).
    Returns: score 1-10, confidence, contact window, aha moment, pitch block, email opener.

    Args:
        company_name: Full company name, e.g. "Linear" or "Vercel"
        domain: Company domain, e.g. "linear.app" or "vercel.com"
        client_id: Your client identifier for tracking (default: mcp_demo)
    """
    company = CompanyInput(
        company_name=company_name,
        domain=domain,
        client_id=client_id,
        signals=None,  # auto-detect all 5 triggers
    )
    result = score_company(company)

    output: dict = {
        "score": result.score,
        "confidence": result.confidence,
        "contact_window": result.contact_window,
        "top_signal": result.top_signal,
        "aha_moment": result.aha_moment,
        "pitch_block": result.pitch_block,
        "email_opener": result.email_opener,
        "requires_human_review": result.requires_human_review,
        "cost_usd": result.cost_usd,
        "prompt_version": result.prompt_version,
    }
    if result.error:
        output["error"] = result.error
    if result.suppressed:
        output["suppressed"] = True
        output["suppression_reason"] = result.suppression_reason
    if result.enrichment and result.enrichment.enriched:
        output["decision_maker"] = {
            "name": result.enrichment.decision_maker_name,
            "title": result.enrichment.decision_maker_title,
            "email": result.enrichment.decision_maker_email,
        }

    return json.dumps(output, indent=2)


@mcp.tool()
def get_hot_leads(client_id: str, min_score: int = 6, limit: int = 10) -> str:
    """
    Fetch the highest-scoring companies for a client from Supabase.

    Returns accounts ready for outreach sorted by score descending.
    Only returns leads that passed governance (confidence >= threshold).

    Args:
        client_id: Your client identifier
        min_score: Minimum score to include (default: 6)
        limit: Max number of leads to return (default: 10)
    """
    try:
        supabase = get_supabase()
        response = (
            supabase.table("signals")
            .select(
                "company_name, domain, score, confidence, contact_window, "
                "aha_moment, pitch_block, email_opener, top_signal, created_at"
            )
            .eq("client_id", client_id)
            .gte("score", min_score)
            .eq("requires_human_review", False)
            .eq("suppressed", False)
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )
        return json.dumps(
            {"client_id": client_id, "leads": response.data, "count": len(response.data)},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_pitch(domain: str, client_id: str = "mcp_demo") -> str:
    """
    Retrieve the sales pitch and email opener for a previously scored company.

    Looks up the most recent scored result from Supabase.
    Use this when you've already scored a domain and want to quickly
    retrieve the pitch block without running the full pipeline again.

    Args:
        domain: Company domain, e.g. "vercel.com"
        client_id: Your client identifier (default: mcp_demo)
    """
    try:
        supabase = get_supabase()
        response = (
            supabase.table("signals")
            .select(
                "company_name, domain, score, confidence, pitch_block, "
                "email_opener, aha_moment, top_signal, contact_window, "
                "signal_scores, created_at"
            )
            .eq("domain", domain)
            .eq("client_id", client_id)
            .eq("scored", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return json.dumps({"error": f"No scored data found for {domain} / {client_id}. Run score_company first."})
        return json.dumps(response.data[0], indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
