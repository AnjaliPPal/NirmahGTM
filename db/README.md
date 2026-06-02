# Database

## How migrations work (Supabase CLI — 2026 standard)

No copy-pasting SQL. The CLI tracks which migrations have been applied and pushes only the new ones.

```
supabase/migrations/
  20260515000000_initial_schema.sql   ← v1 baseline
  20260521000000_v2_signals.sql       ← Phase 1+2: new columns + indexes
  20260522000000_v2_evals.sql         ← Phase 3: eval_outcomes table
```

## Setup (one-time)

```bash
# 1. Install Supabase CLI
npm install -g supabase

# 2. Link to your Supabase project
#    Find your ref: Supabase dashboard → Settings → General → Reference ID
supabase link --project-ref <your-project-ref>
```

## Daily workflow

```bash
# Apply all pending migrations to remote Supabase
supabase db push

# Add a new migration (e.g. for a new feature)
supabase migration new add_rag_embeddings
# → creates supabase/migrations/TIMESTAMP_add_rag_embeddings.sql
# → edit the file, then run supabase db push
```

## Drop everything and start fresh

```bash
supabase db reset
```

This drops all tables and re-applies every migration from scratch. Equivalent of "drop all + re-run schema.sql" — one command.

## Reference

`db/schema.sql` — the complete current state in one file. Read this to understand the full schema. Never run it directly if you already have data — use migrations instead.

## Rule

**`db/schema.sql` and `supabase/migrations/` must stay in sync with `scorer/models.py`.**
Every field added to `ScoreResult` needs a column in the next migration file.
