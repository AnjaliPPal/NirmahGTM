"""
Tests for the offline eval harness.

The metric math is tested deterministically with synthetic predictions — no LLM,
no network. The golden set is checked for integrity. The dry_run side-effect gate
is tested with the same mocking pattern as test_scorer.py. The live LLM run
(run_eval.py) is intentionally NOT exercised here — it is a manual script.
"""
from unittest.mock import patch, MagicMock

from scorer.models import CompanyInput, Signals, EnrichmentData
from scorer.scorer import score_company
from evals import metrics
from evals.golden_set import load_golden_set, BAND_RANGES


# ── metric math (pure, no LLM) ────────────────────────────────────────────────

def _pred(band, score, confidence=80, top_signal=None, expected_top_signal=None, error=None):
    return {
        "company_name": "X", "domain": "x.com",
        "expected_band": band, "score": score, "confidence": confidence,
        "top_signal": top_signal, "expected_top_signal": expected_top_signal, "error": error,
    }


def test_band_of_score():
    assert metrics.band_of_score(9) == "high"
    assert metrics.band_of_score(5) == "medium"
    assert metrics.band_of_score(2) == "low"
    assert metrics.band_of_score(None) is None


def test_band_accuracy_all_correct():
    preds = [_pred("high", 8), _pred("low", 2), _pred("medium", 5)]
    ba = metrics.band_accuracy(preds)
    assert ba["correct"] == 3
    assert ba["total"] == 3
    assert ba["accuracy"] == 1.0


def test_band_accuracy_partial():
    preds = [_pred("high", 8), _pred("high", 3), _pred("low", 2), _pred("low", 9)]
    ba = metrics.band_accuracy(preds)
    assert ba["correct"] == 2
    assert ba["accuracy"] == 0.5


def test_separation_pass():
    preds = [_pred("high", 8), _pred("high", 7), _pred("low", 2), _pred("low", 3)]
    sep = metrics.separation(preds)
    assert sep["pass"] is True
    assert sep["min_high"] == 7
    assert sep["max_low"] == 3


def test_separation_fail_on_overlap():
    preds = [_pred("high", 6), _pred("low", 6)]
    sep = metrics.separation(preds)
    assert sep["pass"] is False


def test_separation_missing_band():
    preds = [_pred("high", 8)]
    sep = metrics.separation(preds)
    assert sep["pass"] is False
    assert "missing" in sep["reason"]


def test_top_signal_agreement_substring_match():
    preds = [
        _pred("high", 8, top_signal="Funding & M&A", expected_top_signal="fund"),
        _pred("high", 9, top_signal="Hiring", expected_top_signal="exec"),
    ]
    tsa = metrics.top_signal_agreement(preds)
    assert tsa["labeled"] == 2
    assert tsa["matches"] == 1
    assert tsa["agreement"] == 0.5


def test_top_signal_agreement_none_labeled():
    preds = [_pred("high", 8), _pred("low", 2)]
    tsa = metrics.top_signal_agreement(preds)
    assert tsa["agreement"] is None


def test_confidence_calibration():
    preds = [_pred("high", 8, confidence=90), _pred("low", 9, confidence=50)]  # 1 correct, 1 wrong
    cal = metrics.confidence_calibration(preds)
    assert cal["avg_confidence_correct"] == 90.0
    assert cal["avg_confidence_incorrect"] == 50.0
    assert cal["n_correct"] == 1
    assert cal["n_incorrect"] == 1


def test_failures_lists_only_wrong():
    preds = [_pred("high", 8), _pred("low", 9)]
    fails = metrics.failures(preds)
    assert len(fails) == 1
    assert fails[0]["expected_band"] == "low"
    assert fails[0]["got_band"] == "high"


def test_summarize_shape():
    preds = [_pred("high", 8), _pred("low", 2)]
    report = metrics.summarize(preds, prompt_version="v2.0")
    assert report["prompt_version"] == "v2.0"
    assert report["cases"] == 2
    assert report["band_accuracy"]["accuracy"] == 1.0
    assert "separation" in report
    assert "confidence_calibration" in report


def test_scored_error_case_counts_as_failure():
    """A case that errored (score=None) is not in any band → a failure."""
    preds = [_pred("high", None, confidence=None, error="boom")]
    assert metrics.is_correct(preds[0]) is False
    assert metrics.band_accuracy(preds)["accuracy"] == 0.0


# ── golden set integrity ──────────────────────────────────────────────────────

def test_golden_set_loads_and_is_nonempty():
    cases = load_golden_set()
    assert len(cases) >= 20


def test_golden_set_bands_are_valid():
    for c in load_golden_set():
        assert c.expected_band in BAND_RANGES, f"{c.company_name} has bad band {c.expected_band}"


def test_golden_set_signals_are_signals_instances():
    for c in load_golden_set():
        assert isinstance(c.signals, Signals), f"{c.company_name} signals not a Signals model"


def test_golden_set_no_duplicate_domains():
    domains = [c.domain for c in load_golden_set()]
    assert len(domains) == len(set(domains)), "duplicate domain in golden set"


def test_golden_set_covers_all_three_bands():
    bands = {c.expected_band for c in load_golden_set()}
    assert bands == {"high", "medium", "low"}


# ── dry_run side-effect gate ──────────────────────────────────────────────────

_SCORE_JSON_HIGH = (
    '{"score": 8, "confidence": 90, "reasoning": "convergence", "top_signal": "funded_90d", '
    '"contact_window": "now", "aha_moment": "now", "signal_scores": {"funding": 9}, "pitch_block": "x"}'
)


def _mock_groq(text):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


def _company():
    return CompanyInput(
        company_name="Acme", domain="acme.com", client_id="eval",
        signals=Signals(funded_90d=True, hiring_gtm=True, open_gtm_roles=4),
    )


@patch("scorer.scorer.push_to_hubspot", return_value=MagicMock(pushed=True, contact_id="c", deal_id="d"))
@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=EnrichmentData(enriched=False))
@patch("scorer.scorer.generate_opener_gemini", return_value=("opener", 0.0))
@patch("scorer.scorer._get_client")
def test_dry_run_suppresses_slack_and_crm(mock_client_fn, mock_opener, mock_enrich, mock_slack, mock_crm):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(_SCORE_JSON_HIGH)

    result = score_company(_company(), supabase=None, dry_run=True)

    assert result.score == 8          # full pipeline still ran
    mock_slack.assert_not_called()    # but no outward side effects
    mock_crm.assert_not_called()
    assert result.alerted_slack is False
    assert result.pushed_to_crm is False


@patch("scorer.scorer.push_to_hubspot", return_value=MagicMock(pushed=True, contact_id="c", deal_id="d"))
@patch("scorer.scorer.send_slack_alert", return_value=True)
@patch("scorer.scorer.enrich_company", return_value=EnrichmentData(enriched=False))
@patch("scorer.scorer.generate_opener_gemini", return_value=("opener", 0.0))
@patch("scorer.scorer._get_client")
def test_non_dry_run_still_fires_slack_and_crm(mock_client_fn, mock_opener, mock_enrich, mock_slack, mock_crm):
    """Default dry_run=False preserves existing behavior — no regression."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_groq(_SCORE_JSON_HIGH)

    result = score_company(_company(), supabase=None, dry_run=False)

    assert result.score == 8
    mock_slack.assert_called_once()
    mock_crm.assert_called_once()
