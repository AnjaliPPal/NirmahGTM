"""
Tests for scorer/rag.py — embedding, retrieval, and RAG context formatting.
"""
from unittest.mock import patch, MagicMock
from scorer.rag import embed, store_embedding, retrieve_similar, format_rag_context
from scorer.models import ScoreResult, Signals


def _scored_result() -> ScoreResult:
    return ScoreResult(
        company_name="Vercel",
        domain="vercel.com",
        client_id="test",
        signals=Signals(hiring_gtm=True, funded_90d=True),
        score=8,
        top_signal="funded_90d",
        reasoning="Series B + GTM hiring",
        contact_window="now",
        scored=True,
    )


# ── embed ─────────────────────────────────────────────────────────────────────

def test_embed_returns_none_without_openai_key():
    with patch("scorer.rag._get_openai", return_value=None):
        result = embed("Vercel | score:8 | top_signal:funded_90d")
    assert result is None


def test_embed_returns_vector_when_openai_available():
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536)]
    )
    with patch("scorer.rag._get_openai", return_value=mock_client):
        result = embed("some company text")
    assert result is not None
    assert len(result) == 1536


def test_embed_returns_none_on_api_error():
    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = Exception("rate limit")
    with patch("scorer.rag._get_openai", return_value=mock_client):
        result = embed("some text")
    assert result is None


# ── store_embedding ───────────────────────────────────────────────────────────

def test_store_embedding_skips_unscored_result():
    result = ScoreResult(
        company_name="X", domain="x.com", client_id="test",
        signals=Signals(), scored=False,
    )
    mock_sb = MagicMock()
    with patch("scorer.rag.embed", return_value=[0.1] * 1536):
        store_embedding(result, mock_sb)
    mock_sb.table.assert_not_called()


def test_store_embedding_skips_when_embed_returns_none():
    mock_sb = MagicMock()
    with patch("scorer.rag.embed", return_value=None):
        store_embedding(_scored_result(), mock_sb)
    mock_sb.table.assert_not_called()


def test_store_embedding_calls_supabase_update():
    mock_sb = MagicMock()
    mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    with patch("scorer.rag.embed", return_value=[0.1] * 1536):
        store_embedding(_scored_result(), mock_sb)
    mock_sb.table.assert_called_with("signals")


# ── retrieve_similar ──────────────────────────────────────────────────────────

def test_retrieve_similar_returns_empty_without_openai():
    signals = Signals(hiring_gtm=True)
    mock_sb = MagicMock()
    with patch("scorer.rag.embed", return_value=None):
        result = retrieve_similar("Vercel", "vercel.com", signals, "test", mock_sb)
    assert result == []


def test_retrieve_similar_calls_rpc_and_returns_data():
    signals = Signals(hiring_gtm=True, funded_90d=True)
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value = MagicMock(data=[
        {"company_name": "Linear", "domain": "linear.app", "score": 9, "top_signal": "funded_90d", "outcome": "replied"},
    ])
    with patch("scorer.rag.embed", return_value=[0.1] * 1536):
        result = retrieve_similar("Vercel", "vercel.com", signals, "test", mock_sb)
    assert len(result) == 1
    assert result[0]["company_name"] == "Linear"
    mock_sb.rpc.assert_called_once_with("match_signals", {
        "query_embedding": [0.1] * 1536,
        "match_client_id": "test",
        "match_count": 5,
    })


def test_retrieve_similar_returns_empty_on_rpc_error():
    signals = Signals(hiring_gtm=True)
    mock_sb = MagicMock()
    mock_sb.rpc.side_effect = Exception("relation does not exist")
    with patch("scorer.rag.embed", return_value=[0.1] * 1536):
        result = retrieve_similar("X", "x.com", signals, "test", mock_sb)
    assert result == []


# ── format_rag_context ────────────────────────────────────────────────────────

def test_format_rag_context_empty_on_no_similar():
    assert format_rag_context([]) == ""


def test_format_rag_context_formats_similar_companies():
    similar = [
        {"company_name": "Linear", "domain": "linear.app", "score": 9, "top_signal": "funded_90d", "outcome": "replied"},
        {"company_name": "Notion", "domain": "notion.so", "score": 7, "top_signal": "hiring_gtm", "outcome": "closed"},
    ]
    context = format_rag_context(similar)
    assert "Linear" in context
    assert "replied" in context
    assert "Notion" in context
    assert "closed" in context
    assert "PAST SIMILAR ACCOUNTS" in context
