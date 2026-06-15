import os
from pathlib import Path
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

_supabase: Client | None = None

# Markers that mean "this is still a placeholder, not a real value"
_PLACEHOLDER_MARKERS = ("...", "paste", "your_", "<", "xxxx")


def _real(value: str | None) -> str | None:
    """Return the value only if it looks like a real credential, not a placeholder."""
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    low = v.lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        return None
    return v


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
        # Prefer service-role (bypasses RLS for writes), but fall back to the
        # publishable key when the service-role slot still holds a placeholder.
        key = _real(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")) or os.environ["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
        _supabase = create_client(url, key)
    return _supabase
