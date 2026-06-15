"""
Pure metric functions for the SignalOS offline eval.

These take already-computed predictions (plain dicts) and return numbers — no LLM,
no network, no I/O. That keeps them fully unit-testable in `tests/test_evals.py`
with synthetic data, while the slow live LLM run lives in `run_eval.py`.

A prediction dict has the shape:
    {
        "company_name": str,
        "domain": str,
        "expected_band": "high" | "medium" | "low",
        "score": int | None,            # model score 1-10 (None if scoring errored)
        "confidence": int | None,
        "top_signal": str | None,
        "expected_top_signal": str | None,
        "error": str | None,
    }
"""
from typing import Optional

from .golden_set import BAND_RANGES


def band_of_score(score: Optional[int]) -> Optional[str]:
    """Which band does a raw score fall into? None if score is None/out of range."""
    if score is None:
        return None
    for band, (lo, hi) in BAND_RANGES.items():
        if lo <= score <= hi:
            return band
    return None


def is_correct(pred: dict) -> bool:
    """A prediction is correct when its score lands in the expected band."""
    return band_of_score(pred.get("score")) == pred.get("expected_band")


def band_accuracy(preds: list[dict]) -> dict:
    """Fraction of cases whose score lands in the expected band. The headline metric."""
    total = len(preds)
    correct = sum(1 for p in preds if is_correct(p))
    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total else 0.0,
    }


def separation(preds: list[dict]) -> dict:
    """
    Do high-band cases out-score low-band cases?

    PASS when the lowest score among 'high' cases is strictly greater than the
    highest score among 'low' cases — i.e. the model cleanly separates in-market
    from not-in-market. This is robust to medium-band jitter.
    """
    high_scores = [p["score"] for p in preds if p.get("expected_band") == "high" and p.get("score") is not None]
    low_scores  = [p["score"] for p in preds if p.get("expected_band") == "low"  and p.get("score") is not None]
    if not high_scores or not low_scores:
        return {"pass": False, "min_high": None, "max_low": None, "reason": "missing high or low cases"}
    min_high = min(high_scores)
    max_low  = max(low_scores)
    return {"pass": min_high > max_low, "min_high": min_high, "max_low": max_low}


def top_signal_agreement(preds: list[dict]) -> dict:
    """
    Among cases that declare an expected_top_signal, how often does the model's
    top_signal contain it (case-insensitive substring)? Lenient on purpose — the
    model returns free-text like 'Funding & M&A' vs a label like 'fund'.
    """
    labeled = [p for p in preds if p.get("expected_top_signal")]
    if not labeled:
        return {"matches": 0, "labeled": 0, "agreement": None}
    matches = 0
    for p in labeled:
        expected = (p.get("expected_top_signal") or "").lower()
        got = (p.get("top_signal") or "").lower()
        if expected and expected in got:
            matches += 1
    return {
        "matches": matches,
        "labeled": len(labeled),
        "agreement": round(matches / len(labeled), 3),
    }


def confidence_calibration(preds: list[dict]) -> dict:
    """
    Average reported confidence on band-correct vs band-incorrect cases.
    A well-calibrated model is more confident when it is right.
    """
    correct_conf   = [p["confidence"] for p in preds if is_correct(p) and p.get("confidence") is not None]
    incorrect_conf = [p["confidence"] for p in preds if not is_correct(p) and p.get("confidence") is not None]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {
        "avg_confidence_correct":   avg(correct_conf),
        "avg_confidence_incorrect": avg(incorrect_conf),
        "n_correct":   len(correct_conf),
        "n_incorrect": len(incorrect_conf),
    }


def failures(preds: list[dict]) -> list[dict]:
    """Every case the model got wrong, for the scorecard's failure table."""
    out = []
    for p in preds:
        if not is_correct(p):
            out.append({
                "company_name":   p.get("company_name"),
                "domain":         p.get("domain"),
                "expected_band":  p.get("expected_band"),
                "got_score":      p.get("score"),
                "got_band":       band_of_score(p.get("score")),
                "error":          p.get("error"),
            })
    return out


def summarize(preds: list[dict], prompt_version: Optional[str] = None) -> dict:
    """Roll all metrics into one report dict (also what gets written to JSON)."""
    return {
        "prompt_version":         prompt_version,
        "cases":                  len(preds),
        "band_accuracy":          band_accuracy(preds),
        "separation":             separation(preds),
        "top_signal_agreement":   top_signal_agreement(preds),
        "confidence_calibration": confidence_calibration(preds),
        "failures":               failures(preds),
    }
