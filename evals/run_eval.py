"""
SignalOS offline eval runner.

Runs the full scoring pipeline against the hand-labeled golden set and prints a
scorecard: band accuracy, high/low separation, top-signal agreement, confidence
calibration, and a failure table. Writes a JSON report for trend tracking, and
exits non-zero when quality drops below --min-accuracy (a CI/regression gate).

Usage:
    python evals/run_eval.py
    python evals/run_eval.py --limit 8 --min-accuracy 0.80
    python evals/run_eval.py --json evals/last_report.json

Requires GROQ_API_KEY (real Groq scoring call per case — free tier). All other
integrations are disabled for determinism (see _isolate_env below).
"""
import argparse
import json
import os
import sys
from pathlib import Path

# ── Isolate the environment BEFORE importing scorer modules ───────────────────
# enrichment.py captures its API keys at import time, so the keys must be cleared
# first. We keep GROQ_API_KEY (needed to score) and drop everything that would
# add network non-determinism or fire a real side effect. dry_run=True also gates
# Slack/CRM at call time as belt-and-suspenders.
_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

for _k in (
    "HUNTER_API_KEY", "APOLLO_API_KEY", "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL",
    "OPENAI_API_KEY",            # force rule-based pre-filter (deterministic)
    "SLACK_WEBHOOK_URL", "SLACK_REVIEW_WEBHOOK_URL",
    "HUBSPOT_ACCESS_TOKEN",
    "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY",
):
    os.environ.pop(_k, None)

sys.path.insert(0, str(_ROOT))

from scorer.models import CompanyInput, EnrichmentData  # noqa: E402  (after env isolation)
import scorer.scorer as _scorer_mod                # noqa: E402
from scorer.scorer import score_company            # noqa: E402
from scorer.prompts import PROMPT_VERSION          # noqa: E402
from evals.golden_set import load_golden_set       # noqa: E402
from evals import metrics                           # noqa: E402

# Fully disable enrichment for the eval: clearing the API keys is not enough
# because enrichment.py defaults FIRECRAWL_API_URL to localhost:3002 and still
# attempts a scrape. We isolate the reasoning layer by stubbing enrichment to an
# empty result — the only remaining network call is the Groq scoring itself.
_scorer_mod.enrich_company = lambda domain: EnrichmentData(enriched=False)


def _run_case(case) -> dict:
    """Score one golden case offline and flatten the result into a prediction dict."""
    company = CompanyInput(
        company_name=case.company_name,
        domain=case.domain,
        client_id="eval",
        signals=case.signals,            # fixed signals → no live detection
    )
    try:
        result = score_company(company, supabase=None, dry_run=True)
        return {
            "company_name":        case.company_name,
            "domain":              case.domain,
            "expected_band":       case.expected_band,
            "expected_top_signal": case.expected_top_signal,
            "score":               result.score,
            "confidence":          result.confidence,
            "top_signal":          result.top_signal,
            "error":               result.error,
        }
    except Exception as e:  # never let one case abort the whole run
        return {
            "company_name":        case.company_name,
            "domain":              case.domain,
            "expected_band":       case.expected_band,
            "expected_top_signal": case.expected_top_signal,
            "score":               None,
            "confidence":          None,
            "top_signal":          None,
            "error":               f"{type(e).__name__}: {e}",
        }


def _print_scorecard(report: dict) -> None:
    ba   = report["band_accuracy"]
    sep  = report["separation"]
    tsa  = report["top_signal_agreement"]
    cal  = report["confidence_calibration"]

    print()
    print("=" * 60)
    print(f"  SignalOS Offline Eval - prompt {report['prompt_version']} - {report['cases']} cases")
    print("=" * 60)
    print(f"  Band accuracy:        {ba['accuracy']:.1%}  ({ba['correct']}/{ba['total']})")
    if sep["min_high"] is not None:
        verdict = "PASS" if sep["pass"] else "FAIL"
        print(f"  High/low separation:  {verdict}  (min high {sep['min_high']} vs max low {sep['max_low']})")
    else:
        print(f"  High/low separation:  n/a  ({sep.get('reason', '')})")
    if tsa["agreement"] is not None:
        print(f"  Top-signal agreement: {tsa['agreement']:.1%}  ({tsa['matches']}/{tsa['labeled']} labeled)")
    print(f"  Confidence (correct):   {cal['avg_confidence_correct']}  avg   (n={cal['n_correct']})")
    print(f"  Confidence (incorrect): {cal['avg_confidence_incorrect']}  avg   (n={cal['n_incorrect']})")

    fails = report["failures"]
    if fails:
        print("-" * 60)
        print(f"  Failures ({len(fails)}):")
        for f in fails:
            got = f["got_score"] if f["got_score"] is not None else "ERR"
            line = f"   - {f['company_name']:<14} expected {f['expected_band']:<6} got {got} ({f['got_band']})"
            if f["error"]:
                line += f"  [{f['error'][:60]}]"
            print(line)
    print("=" * 60)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SignalOS offline eval.")
    parser.add_argument("--limit", type=int, default=0, help="Only run the first N cases (0 = all).")
    parser.add_argument("--min-accuracy", type=float, default=0.75,
                        help="Exit non-zero if band accuracy drops below this (regression gate).")
    parser.add_argument("--json", type=str, default=str(Path(__file__).parent / "last_report.json"),
                        help="Where to write the JSON report.")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY is not set — the eval needs it to score. Add it to .env.", file=sys.stderr)
        return 2

    cases = load_golden_set()
    if args.limit > 0:
        cases = cases[:args.limit]

    print(f"Running {len(cases)} cases through score_company (dry_run, offline)...")
    preds = []
    for i, case in enumerate(cases, 1):
        pred = _run_case(case)
        got = pred["score"] if pred["score"] is not None else "ERR"
        print(f"  [{i:>2}/{len(cases)}] {case.company_name:<14} expect {case.expected_band:<6} -> {got}")
        preds.append(pred)

    report = metrics.summarize(preds, prompt_version=PROMPT_VERSION)
    _print_scorecard(report)

    try:
        Path(args.json).write_text(json.dumps(report, indent=2))
        print(f"Report written to {args.json}")
    except Exception as e:
        print(f"WARN: could not write report: {e}", file=sys.stderr)

    acc = report["band_accuracy"]["accuracy"]
    sep_ok = report["separation"]["pass"]
    if acc < args.min_accuracy:
        print(f"GATE FAILED: band accuracy {acc:.1%} < required {args.min_accuracy:.1%}", file=sys.stderr)
        return 1
    if not sep_ok:
        print("GATE FAILED: high-band cases do not cleanly out-score low-band cases.", file=sys.stderr)
        return 1
    print(f"GATE PASSED: band accuracy {acc:.1%} >= {args.min_accuracy:.1%}, separation clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
