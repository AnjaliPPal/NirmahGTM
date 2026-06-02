-- =============================================================================
-- Migration 002 — SignalOS v2.0 Phase 1 + Phase 2
-- Applied: 2026-05-21
-- Requires: 001_initial_schema.sql
-- =============================================================================
-- Run this if your signals table was created by migration 001.
-- Safe to re-run (IF NOT EXISTS / IF column does not already exist pattern).
-- =============================================================================

-- Phase 1: prompt versioning + cooldown suppression
ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS suppressed         boolean     DEFAULT false,
  ADD COLUMN IF NOT EXISTS suppression_reason text,
  ADD COLUMN IF NOT EXISTS prompt_version     text;

-- Phase 1: pitch block + signal score breakdown
ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS pitch_block        text,
  ADD COLUMN IF NOT EXISTS signal_scores      jsonb;

-- Phase 1: auto-detection flag + stable company UUID
ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS auto_detected      boolean     DEFAULT false,
  ADD COLUMN IF NOT EXISTS company_id         uuid        UNIQUE;

-- Phase 2: domain validation produces error rows with score=NULL
-- (error column already existed in 001)

-- Indexes (45-day cooldown + prompt version eval)
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
