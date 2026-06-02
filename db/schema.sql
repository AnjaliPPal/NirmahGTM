-- =============================================================================
-- SignalOS — Canonical Database Schema
-- Version: v2.0  |  Updated: 2026-05-22
-- =============================================================================
--
-- USAGE
--   Fresh setup  → run this entire file once in Supabase SQL editor
--   Existing DB  → run db/migrations/ files in order instead (see db/README.md)
--
-- This file is always kept in sync with scorer/models.py.
-- Every field in ScoreResult maps to a column here. No exceptions.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. SIGNALS  — one row per company scored
--    Maps 1:1 to scorer/models.py :: ScoreResult
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS signals (

  -- Identity
  id                    uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  company_id            uuid          UNIQUE,                               -- ScoreResult.company_id (Python-generated UUID)
  company_name          text          NOT NULL,
  domain                text          NOT NULL,
  client_id             text          NOT NULL,

  -- Raw signal data (nested Pydantic models serialised as JSONB)
  signals               jsonb         NOT NULL,                             -- scorer/models.py :: Signals
  enrichment            jsonb,                                              -- scorer/models.py :: EnrichmentData

  -- Scoring output
  score                 integer       CHECK (score >= 1 AND score <= 10),
  confidence            integer       CHECK (confidence >= 50 AND confidence <= 100),
  reasoning             text,
  top_signal            text,
  contact_window        text          CHECK (contact_window IN ('now', '2-4 weeks', 'not yet')),
  aha_moment            text,
  pitch_block           text,                                               -- domain-specific sales pitch
  signal_scores         jsonb,                                              -- {"funded_90d": 3, "hiring_gtm": 2, ...}

  -- Governance
  requires_human_review boolean       DEFAULT false,                        -- true when confidence < CONFIDENCE_THRESHOLD

  -- Outreach output
  email_opener          text,
  pipeline_value_usd    numeric(12,2),

  -- CRM / Slack state
  alerted_slack         boolean       DEFAULT false,
  pushed_to_crm         boolean       DEFAULT false,
  hubspot_contact_id    text,
  hubspot_deal_id       text,

  -- RAG embedding (pgvector — requires CREATE EXTENSION vector)
  embedding             vector(1536),                                          -- text-embedding-3-small, stored after scoring

  -- Cost tracking
  cost_usd              numeric(10,6),
  model_costs           jsonb,                                              -- per-model breakdown: {"gpt-4o-mini": 0.0001, "claude-sonnet-4-6": 0.003}

  -- Multi-LLM routing
  pre_filter_passed     boolean       DEFAULT true,                        -- false when pre-filter rejected (no signals, Claude not called)
  pre_filter_reason     text,                                              -- why pre-filter passed or failed

  -- Lifecycle flags
  scored                boolean       DEFAULT false,
  auto_detected         boolean       DEFAULT false,                        -- true if signals were auto-detected (not manually provided)
  cached                boolean       DEFAULT false,                        -- true if returned from 14-day cache
  suppressed            boolean       DEFAULT false,                        -- true if 45-day cooldown blocked re-alert
  suppression_reason    text,

  -- Eval
  prompt_version        text,                                               -- e.g. "v2.0" — links to eval_outcomes

  -- Error tracking
  error                 text,

  created_at            timestamptz   DEFAULT now()

);

-- 45-day cooldown lookup — fastest path for "has this domain been alerted recently?"
CREATE INDEX IF NOT EXISTS idx_signals_cooldown
  ON signals (domain, client_id, created_at DESC)
  WHERE alerted_slack = true;

-- Hot leads dashboard — client's scored leads above threshold, no quarantine
CREATE INDEX IF NOT EXISTS idx_signals_hot_leads
  ON signals (client_id, score DESC)
  WHERE scored = true AND requires_human_review = false;

-- Human review queue — low-confidence leads awaiting manual triage
CREATE INDEX IF NOT EXISTS idx_signals_review_queue
  ON signals (client_id, created_at DESC)
  WHERE requires_human_review = true;

-- 14-day cache lookup — skip re-scoring recently processed domains
CREATE INDEX IF NOT EXISTS idx_signals_cache_lookup
  ON signals (domain, client_id, created_at DESC)
  WHERE scored = true;

-- Prompt version analytics — "v2.0 had X% false positives"
CREATE INDEX IF NOT EXISTS idx_signals_prompt_version
  ON signals (prompt_version, score DESC)
  WHERE scored = true;


-- ---------------------------------------------------------------------------
-- 2. EVAL_OUTCOMES  — closed-loop feedback: what happened after scoring?
--    Populated by POST /webhook/hubspot-reply
--    Drives GET /eval-report/{client_id}
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS eval_outcomes (

  id                    uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  signal_id             uuid          REFERENCES signals (id) ON DELETE SET NULL,

  domain                text          NOT NULL,
  client_id             text          NOT NULL,

  -- Snapshot of the score that generated this lead (denormalised for fast reporting)
  prompt_version        text,
  score                 integer,
  confidence            integer,

  -- Outcome recorded by rep / HubSpot workflow
  outcome               text          NOT NULL CHECK (outcome IN ('replied', 'closed', 'no_reply', 'bounced')),
  days_to_outcome       integer,                                            -- days from scored → outcome
  hubspot_deal_id       text,

  outcome_recorded_at   timestamptz   DEFAULT now(),
  created_at            timestamptz   DEFAULT now()

);

-- "v2.0 prompts had 78% reply rate, v2.1 had 85%" — main eval story
CREATE INDEX IF NOT EXISTS idx_eval_prompt_outcome
  ON eval_outcomes (prompt_version, outcome);

-- "Leads scored 8-10 close at 45%, scored 6-7 at 12%" — score calibration proof
CREATE INDEX IF NOT EXISTS idx_eval_score_outcome
  ON eval_outcomes (score, outcome);

-- Fast per-client reporting
CREATE INDEX IF NOT EXISTS idx_eval_client_created
  ON eval_outcomes (client_id, created_at DESC);


-- ---------------------------------------------------------------------------
-- 3. COSTS  — daily API spend tracker per client
--    Enables: "you spent $2.40 yesterday scoring 12 companies"
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS costs (

  id          uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id   text          NOT NULL,
  date        date          NOT NULL DEFAULT CURRENT_DATE,
  calls       integer       DEFAULT 0,
  total_usd   numeric(10,6) DEFAULT 0,
  created_at  timestamptz   DEFAULT now(),

  UNIQUE (client_id, date)

);
