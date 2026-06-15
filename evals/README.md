# SignalOS Offline Eval Harness

A labeled benchmark for the scoring engine. Answers two questions a Forward
Deployed / AI Engineer must answer about any LLM system:

1. **Is it good?** — does it score the right companies high and the wrong ones low?
2. **Did my change break it?** — run it before/after a prompt edit; if accuracy
   drops, the gate fails.

This is the *offline* counterpart to the *online* eval (`/eval-report`, which
tracks real reply/close outcomes from live campaigns). This one needs no live
campaign data — you can run it in ~3 minutes today.

## Run it

```bash
python evals/run_eval.py                       # full golden set
python evals/run_eval.py --limit 8             # quick subset
python evals/run_eval.py --min-accuracy 0.80   # stricter regression gate
```

Requires `GROQ_API_KEY` (real scoring call per case — Groq free tier). Every
other integration is disabled for determinism: enrichment is stubbed, the
pre-filter falls back to rule-based, and Slack/HubSpot are gated off via
`dry_run=True`. The only network call is the Groq scoring itself.

Exit code is `0` when band accuracy ≥ `--min-accuracy` **and** high-band cases
cleanly out-score low-band cases — so it drops straight into CI.

## What it measures

| Metric | Meaning |
|--------|---------|
| **Band accuracy** | % of cases whose score lands in the expected band (high 7-10 / medium 4-6 / low 1-3). The headline number. |
| **High/low separation** | Does the lowest "high" score beat the highest "low" score? Proves the model cleanly separates in-market from not-in-market. |
| **Top-signal agreement** | Where a case names the dominant signal, does the model agree? (lenient substring match) |
| **Confidence calibration** | Avg reported confidence on correct vs incorrect cases — is the model more confident when it's right? |

Bands, not exact scores, are used because Groq scores at `temperature=0.2` and
jitter ±1 between runs. Band matching absorbs that.

## The golden set

`golden_set.py` holds ~30 hand-labeled cases, each with **fixed `Signals`** (not
auto-detected) so the eval isolates the *reasoning layer*, not the live scrapers.
Cases span three bands; each carries a one-line `note` explaining its label.

**Honest caveat:** the cases are authored to be clearly separated (strong-signal
"high", no-signal "low"), so a high band accuracy is expected — its real value is
as a **regression tripwire** and a demoable artifact, not a hard external
benchmark. To make it a tougher test, add ambiguous boundary cases.

## Add a case

Append an `EvalCase` to the right band list in `golden_set.py`:

```python
EvalCase(
    "Acme", "acme.com",
    Signals(funded_90d=True, funding_stage="Series B", hiring_gtm=True, open_gtm_roles=5),
    "high", "Series B + 5 GTM roles — why this is in-market.",
    expected_top_signal="fund",   # optional, leniently matched
)
```

`tests/test_evals.py` checks golden-set integrity (valid bands, no duplicate
domains, all three bands covered) and the metric math — run `pytest tests/test_evals.py`.
