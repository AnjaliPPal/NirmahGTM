"""
SignalOS setup preflight — tells you exactly what's configured and what YOU still
need to do (fill an env key, enable a Supabase extension, create a webhook).

    python scripts/check_setup.py

Reads .env, classifies every credential as SET / PLACEHOLDER / MISSING, then makes
live checks against Supabase (table exists? pgvector RAG ready?). ASCII-only output
so it runs clean on Windows. Read-only — changes nothing.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(_ROOT))

_PLACEHOLDER_MARKERS = ("...", "paste", "your_", "<", "xxxx", "sk-ant-", "pat-na1-", "sk-lf-", "pk-lf-")


def classify(value):
    """SET / PLACEHOLDER / MISSING for an env value."""
    if value is None or not value.strip():
        return "MISSING"
    low = value.strip().lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        return "PLACEHOLDER"
    return "SET"


def line(label, status, note=""):
    mark = {"SET": "[OK ]", "PLACEHOLDER": "[!! ]", "MISSING": "[-- ]"}[status]
    suffix = f"  -> {note}" if note else ""
    print(f"  {mark} {label:<28} {status}{suffix}")


def main():
    print("\n" + "=" * 68)
    print("  SignalOS setup check")
    print("=" * 68)

    # ── Required ──────────────────────────────────────────────────────────────
    print("\nREQUIRED (engine will not run without these):")
    g = classify(os.environ.get("GROQ_API_KEY"))
    line("GROQ_API_KEY", g, "scoring + opener + reply-classify" if g != "SET" else "")
    line("NEXT_PUBLIC_SUPABASE_URL", classify(os.environ.get("NEXT_PUBLIC_SUPABASE_URL")))
    line("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", classify(os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")))

    # ── Recommended ───────────────────────────────────────────────────────────
    print("\nRECOMMENDED (DB writes / RLS):")
    sr = classify(os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    line("SUPABASE_SERVICE_ROLE_KEY", sr,
         "placeholder ignored; falls back to publishable key (writes may hit RLS)" if sr != "SET" else "bypasses RLS")

    # ── Feature-unlocking optionals ───────────────────────────────────────────
    print("\nOPTIONAL (each unlocks a feature; engine degrades gracefully without):")
    o = classify(os.environ.get("OPENAI_API_KEY"))
    line("OPENAI_API_KEY", o, "RAG embeddings + GPT-4o-mini pre-filter are OFF until set" if o != "SET" else "RAG + pre-filter on")
    line("HUNTER_API_KEY", classify(os.environ.get("HUNTER_API_KEY")), "enrichment tier 1")
    line("APOLLO_API_KEY", classify(os.environ.get("APOLLO_API_KEY")), "enrichment tier 2")
    line("FIRECRAWL_API_KEY", classify(os.environ.get("FIRECRAWL_API_KEY")), "enrichment tier 3")
    line("HUBSPOT_ACCESS_TOKEN", classify(os.environ.get("HUBSPOT_ACCESS_TOKEN")), "CRM push OFF until set")
    line("HUBSPOT_PORTAL_ID", classify(os.environ.get("HUBSPOT_PORTAL_ID")))
    line("LANGFUSE_SECRET_KEY", classify(os.environ.get("LANGFUSE_SECRET_KEY")), "tracing OFF until set")
    line("WEBHOOK_SECRET", classify(os.environ.get("WEBHOOK_SECRET")), "auth for /webhook/hubspot-reply")
    line("ADMIN_API_KEY", classify(os.environ.get("ADMIN_API_KEY")), "auth for /admin/failed-inserts")

    # ── Slack ─────────────────────────────────────────────────────────────────
    print("\nSLACK:")
    main_url = os.environ.get("SLACK_WEBHOOK_URL")
    rev_url = os.environ.get("SLACK_REVIEW_WEBHOOK_URL")
    line("SLACK_WEBHOOK_URL", classify(main_url), "main sales channel")
    rev_status = classify(rev_url)
    rev_note = "review channel"
    if main_url and rev_url and main_url.strip() == rev_url.strip():
        rev_note = "SAME as main -> quarantined leads land in main channel; make a separate webhook"
    line("SLACK_REVIEW_WEBHOOK_URL", rev_status, rev_note)

    # ── Live Supabase checks ──────────────────────────────────────────────────
    print("\nLIVE SUPABASE CHECKS:")
    try:
        from api.deps import get_supabase
        sb = get_supabase()
        try:
            sb.table("signals").select("id").limit(1).execute()
            print("  [OK ] signals table reachable")
        except Exception as e:
            print(f"  [!! ] signals table NOT reachable -> run db/schema.sql + db/migrations/ in Supabase SQL editor")
            print(f"        ({str(e)[:90]})")
        # pgvector RAG readiness
        try:
            sb.rpc("match_signals", {"query_embedding": [0.0] * 1536, "match_client_id": "preflight", "match_count": 1}).execute()
            print("  [OK ] match_signals() RPC present (pgvector RAG ready)")
        except Exception as e:
            print("  [!! ] match_signals() RPC missing -> for RAG: enable pgvector + run db/migrations/005")
            print(f"        ({str(e)[:90]})")
    except Exception as e:
        print(f"  [-- ] could not init Supabase client: {str(e)[:90]}")

    print("\n" + "=" * 68)
    print("  [OK ]=ready   [!! ]=placeholder/needs action   [-- ]=missing/optional")
    print("=" * 68 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
