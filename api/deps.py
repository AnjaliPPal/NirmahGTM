import os
from pathlib import Path
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
        _supabase = create_client(url, key)
    return _supabase
