"""
Run all SignalOS database migrations against the linked Supabase project.

Usage:
    python scripts/migrate.py              # run all pending migrations
    python scripts/migrate.py --dry-run    # print what would run, don't execute
"""
import subprocess
import sys
from pathlib import Path
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_REF = "bijwyohqpurgnonfyhcs"

MIGRATIONS = [
    "db/migrations/001_initial_schema.sql",
    "db/migrations/002_v2_phase1_phase2.sql",
    "db/migrations/003_v2_phase3_evals.sql",
    "db/migrations/004_v2_phase_b_multi_llm.sql",
    "db/migrations/005_v2_phase_c_pgvector.sql",
]

ROOT = Path(__file__).parent.parent
DRY_RUN = "--dry-run" in sys.argv


def run_sql(sql: str, label: str) -> bool:
    if DRY_RUN:
        print(f"[dry-run] would execute: {label}")
        return True
    result = subprocess.run(
        ["supabase", "db", "execute", "--project-ref", PROJECT_REF],
        input=sql,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr.strip()}")
        return False
    return True


def main():
    print(f"Target project: {PROJECT_REF} (NirmahGTM)\n")

    # Step 1: enable pgvector
    print("→ Enabling pgvector extension...")
    ok = run_sql("CREATE EXTENSION IF NOT EXISTS vector;", "CREATE EXTENSION vector")
    if not ok:
        print("  pgvector enable failed — continuing (may already exist)")
    else:
        print("  done")

    # Step 2: run each migration file
    for rel_path in MIGRATIONS:
        path = ROOT / rel_path
        if not path.exists():
            print(f"  SKIP {rel_path} (file not found)")
            continue
        sql = path.read_text(encoding="utf-8")
        print(f"→ {rel_path}")
        ok = run_sql(sql, rel_path)
        print("  done" if ok else "  FAILED — stopping")
        if not ok:
            sys.exit(1)

    print("\nAll migrations complete.")


if __name__ == "__main__":
    main()
