import json
from unittest.mock import patch, MagicMock

from scorer.models import ScoreResult, Signals


def _make_result(**kwargs) -> ScoreResult:
    defaults = dict(
        company_name="Linear",
        domain="linear.app",
        client_id="mcp_demo",
        signals=Signals(hiring_gtm=True),
        score=8,
        reasoning="Hiring GTM roles",
        top_signal="hiring_gtm",
        contact_window="now",
        aha_moment="Scaling GTM team — ideal window.",
        email_opener="Saw Linear is scaling the GTM team.",
        alerted_slack=False,
        cost_usd=0.001,
        scored=True,
    )
    defaults.update(kwargs)
    return ScoreResult(**defaults)


# ── score_company_tool ────────────────────────────────────────────────────────

@patch("mcp_server.score_company")
def test_score_company_tool_happy_path(mock_score):
    from mcp_server import score_company_tool
    mock_score.return_value = _make_result()
    data = json.loads(score_company_tool("Linear", "linear.app"))
    assert data["score"] == 8
    assert data["contact_window"] == "now"
    assert "error" not in data
    assert "suppressed" not in data


@patch("mcp_server.score_company")
def test_score_company_tool_includes_error_field(mock_score):
    from mcp_server import score_company_tool
    mock_score.return_value = _make_result(error="domain unreachable: bad.xyz")
    data = json.loads(score_company_tool("Badco", "bad.xyz"))
    assert data["error"] == "domain unreachable: bad.xyz"


@patch("mcp_server.score_company")
def test_score_company_tool_includes_suppressed_flag(mock_score):
    from mcp_server import score_company_tool
    mock_score.return_value = _make_result(suppressed=True, suppression_reason="Alerted within 45 days")
    data = json.loads(score_company_tool("Linear", "linear.app"))
    assert data["suppressed"] is True
    assert "45 days" in data["suppression_reason"]


# ── get_hot_leads ─────────────────────────────────────────────────────────────

def _sb_with_leads(leads: list) -> MagicMock:
    """Build a Supabase mock that returns `leads` for the chained query used by get_hot_leads.

    Actual chain: table().select().eq(client_id).gte(score).eq(requires_human_review).eq(suppressed).order().limit().execute()
    """
    mock_resp = MagicMock()
    mock_resp.data = leads
    mock_sb = MagicMock()
    chain = mock_sb.table.return_value.select.return_value
    chain = chain.eq.return_value    # .eq("client_id", ...)
    chain = chain.gte.return_value   # .gte("score", min_score)
    chain = chain.eq.return_value    # .eq("requires_human_review", False)
    chain = chain.eq.return_value    # .eq("suppressed", False)
    chain.order.return_value.limit.return_value.execute.return_value = mock_resp
    return mock_sb


@patch("mcp_server.get_supabase")
def test_get_hot_leads_returns_count_and_leads(mock_get_supabase):
    from mcp_server import get_hot_leads
    mock_get_supabase.return_value = _sb_with_leads([
        {"company_name": "Acme", "domain": "acme.com", "score": 9},
        {"company_name": "Beta", "domain": "beta.com", "score": 7},
    ])
    data = json.loads(get_hot_leads("test-client"))
    assert data["count"] == 2
    assert data["leads"][0]["score"] == 9


@patch("mcp_server.get_supabase")
def test_get_hot_leads_empty_returns_zero(mock_get_supabase):
    from mcp_server import get_hot_leads
    mock_get_supabase.return_value = _sb_with_leads([])
    data = json.loads(get_hot_leads("test-client"))
    assert data["count"] == 0
    assert data["leads"] == []


@patch("mcp_server.get_supabase")
def test_get_hot_leads_supabase_error_returns_error_json(mock_get_supabase):
    from mcp_server import get_hot_leads
    mock_get_supabase.side_effect = Exception("Supabase unavailable")
    data = json.loads(get_hot_leads("test-client"))
    assert "error" in data


# ── get_pitch ─────────────────────────────────────────────────────────────────

def _sb_with_pitch(row: dict | None) -> MagicMock:
    """Build a Supabase mock that returns `row` for the chained query used by get_pitch."""
    mock_resp = MagicMock()
    mock_resp.data = [row] if row else []
    mock_sb = MagicMock()
    # Chain: table().select().eq().eq().eq().order().limit().execute()
    chain = mock_sb.table.return_value.select.return_value
    for _ in range(3):
        chain = chain.eq.return_value
    chain.order.return_value.limit.return_value.execute.return_value = mock_resp
    return mock_sb


@patch("mcp_server.get_supabase")
def test_get_pitch_returns_pitch_block(mock_get_supabase):
    from mcp_server import get_pitch
    mock_get_supabase.return_value = _sb_with_pitch(
        {"domain": "vercel.com", "pitch_block": "Vercel is scaling fast.", "score": 8}
    )
    data = json.loads(get_pitch("vercel.com"))
    assert data["pitch_block"] == "Vercel is scaling fast."


@patch("mcp_server.get_supabase")
def test_get_pitch_not_found_returns_error(mock_get_supabase):
    from mcp_server import get_pitch
    mock_get_supabase.return_value = _sb_with_pitch(None)
    data = json.loads(get_pitch("notscored.com"))
    assert "error" in data
    assert "Run score_company first" in data["error"]


@patch("mcp_server.get_supabase")
def test_get_pitch_supabase_error_returns_error_json(mock_get_supabase):
    from mcp_server import get_pitch
    mock_get_supabase.side_effect = Exception("DB down")
    data = json.loads(get_pitch("vercel.com"))
    assert "error" in data
