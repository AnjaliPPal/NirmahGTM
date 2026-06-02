-- =============================================================================
-- Migration 001 — Initial Schema (SignalOS v1)
-- Applied: 2026-05-15
-- =============================================================================
-- Reference only. If you are setting up fresh, run db/schema.sql instead.
-- This file documents what the v1 baseline looked like.
-- =============================================================================

CREATE TABLE IF NOT EXISTS signals (
  id                    uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  company_name          text          NOT NULL,
  domain                text          NOT NULL,
  client_id             text          NOT NULL,
  signals               jsonb         NOT NULL,
  enrichment            jsonb,
  score                 integer       CHECK (score >= 1 AND score <= 10),
  confidence            integer       CHECK (confidence >= 50 AND confidence <= 100),
  reasoning             text,
  top_signal            text,
  contact_window        text          CHECK (contact_window IN ('now', '2-4 weeks', 'not yet')),
  aha_moment            text,
  requires_human_review boolean       DEFAULT false,
  email_opener          text,
  pipeline_value_usd    numeric(12,2),
  alerted_slack         boolean       DEFAULT false,
  pushed_to_crm         boolean       DEFAULT false,
  hubspot_contact_id    text,
  hubspot_deal_id       text,
  cost_usd              numeric(10,6),
  scored                boolean       DEFAULT false,
  cached                boolean       DEFAULT false,
  error                 text,
  created_at            timestamptz   DEFAULT now()
);

CREATE TABLE IF NOT EXISTS costs (
  id          uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id   text          NOT NULL,
  date        date          NOT NULL DEFAULT CURRENT_DATE,
  calls       integer       DEFAULT 0,
  total_usd   numeric(10,6) DEFAULT 0,
  created_at  timestamptz   DEFAULT now(),
  UNIQUE (client_id, date)
);
