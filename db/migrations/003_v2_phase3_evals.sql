-- =============================================================================
-- Migration 003 — SignalOS v2.0 Phase 3: Eval Outcomes
-- Applied: 2026-05-22
-- Requires: 002_v2_phase1_phase2.sql
-- =============================================================================
-- Adds the closed-loop eval pipeline:
--   eval_outcomes table ← populated by POST /webhook/hubspot-reply
--   Drives GET /eval-report/{client_id} reply/close rate reporting
-- =============================================================================

CREATE TABLE IF NOT EXISTS eval_outcomes (

  id                    uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  signal_id             uuid          REFERENCES signals (id) ON DELETE SET NULL,

  domain                text          NOT NULL,
  client_id             text          NOT NULL,

  -- Denormalised snapshot so reports work even if signal row is deleted
  prompt_version        text,
  score                 integer,
  confidence            integer,

  outcome               text          NOT NULL CHECK (outcome IN ('replied', 'closed', 'no_reply', 'bounced')),
  days_to_outcome       integer,
  hubspot_deal_id       text,

  outcome_recorded_at   timestamptz   DEFAULT now(),
  created_at            timestamptz   DEFAULT now()

);

CREATE INDEX IF NOT EXISTS idx_eval_prompt_outcome
  ON eval_outcomes (prompt_version, outcome);

CREATE INDEX IF NOT EXISTS idx_eval_score_outcome
  ON eval_outcomes (score, outcome);

CREATE INDEX IF NOT EXISTS idx_eval_client_created
  ON eval_outcomes (client_id, created_at DESC);
