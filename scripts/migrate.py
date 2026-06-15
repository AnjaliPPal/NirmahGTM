"""
Run all SignalOS database migrations against the linked Supabase project.

Usage:
    python scripts/migrate.py              # run all pending migrations
    python scripts/migrate.py --dry-run    # print what would run, don't execute
"""
import subprocess
import sys
import tempfile
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


def run_query_file(path, label) -> bool:
    if DRY_RUN:
        print(f"[dry-run] would execute: {label}")
        return True
    result = subprocess.run(
        ["supabase", "db", "query", "--file", str(path), "--linked"],
        text=True,
        capture_output=True,
        shell=True,
    )
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr.strip()}")
        return False
    return True


def main():
    print(f"Target project: {PROJECT_REF} (NirmahGTM)\n")

    # Step 1: enable pgvector -- via a temp file, not an inline CLI arg
    # (avoids cmd.exe / npm .cmd-shim quoting issues with semicolons/spaces)
    print("-> Enabling pgvector extension...")
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8")
    tmp.write("CREATE EXTENSION IF NOT EXISTS vector;")
    tmp.close()
    ok = run_query_file(tmp.name, "CREATE EXTENSION vector")
    Path(tmp.name).unlink(missing_ok=True)
    if not ok:
        print("  pgvector enable failed -- continuing (may already exist)")
    else:
        print("  done")

    # Step 2: run each migration file
    for rel_path in MIGRATIONS:
        path = ROOT / rel_path
        if not path.exists():
            print(f"  SKIP {rel_path} (file not found)")
            continue
        print(f"-> {rel_path}")
        ok = run_query_file(path, rel_path)
        print("  done" if ok else "  FAILED -- stopping")
        if not ok:
            sys.exit(1)

    print("\nAll migrations complete.")


if __name__ == "__main__":
    main()
