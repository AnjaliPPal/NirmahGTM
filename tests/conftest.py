import os
import pytest

# Set required env vars before any module-level clients are created
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SLACK_WEBHOOK_URL", "")
os.environ.setdefault("SCORE_THRESHOLD", "6")
