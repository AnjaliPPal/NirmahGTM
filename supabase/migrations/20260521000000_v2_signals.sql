-- SignalOS v2.0 Phase 1+2 — new columns + indexes

-- Cooldown suppression (45-day engine)
ALTER TABLE signals ADD COLUMN IF NOT EXISTS suppressed         boolean DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS suppression_reason text;

-- Prompt versioning (eval story: "v2.0 had 12% false positives")
ALTER TABLE signals ADD COLUMN IF NOT EXISTS prompt_version     text;

-- Pitch block + per-signal score breakdown
ALTER TABLE signals ADD COLUMN IF NOT EXISTS pitch_block        text;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_scores      jsonb;

-- Auto-detection flag + stable company UUID
ALTER TABLE signals ADD COLUMN IF NOT EXISTS auto_detected      boolean DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS company_id         uuid UNIQUE;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_cooldown
  ON signals (domain, client_id, created_at DESC)
  WHERE alerted_slack = true;

CREATE INDEX IF NOT EXISTS idx_signals_hot_leads
  ON signals (client_id, score DESC)
  WHERE scored = true AND requires_human_review = false;

CREATE INDEX IF NOT EXISTS idx_signals_review_queue
  ON signals (client_id, created_at DESC)
  WHERE requires_human_review = true;

CREATE INDEX IF NOT EXISTS idx_signals_cache_lookup
  ON signals (domain, client_id, created_at DESC)
  WHERE scored = true;

CREATE INDEX IF NOT EXISTS idx_signals_prompt_version
  ON signals (prompt_version, score DESC)
  WHERE scored = true;
