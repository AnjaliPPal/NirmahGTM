-- Run once in Supabase SQL editor

CREATE TABLE IF NOT EXISTS signals (
  id                   uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  company_name         text NOT NULL,
  domain               text NOT NULL,
  client_id            text NOT NULL,
  signals              jsonb NOT NULL,
  enrichment           jsonb,
  score                integer CHECK (score >= 1 AND score <= 10),
  confidence           integer CHECK (confidence >= 50 AND confidence <= 100),
  reasoning            text,
  top_signal           text,
  contact_window       text CHECK (contact_window IN ('now', '2-4 weeks', 'not yet')),
  aha_moment           text,
  requires_human_review boolean DEFAULT false,
  email_opener         text,
  pipeline_value_usd   numeric(12, 2),
  alerted_slack        boolean DEFAULT false,
  pushed_to_crm        boolean DEFAULT false,
  hubspot_contact_id   text,
  hubspot_deal_id      text,
  cost_usd             numeric(10, 6),
  scored               boolean DEFAULT false,
  cached               boolean DEFAULT false,
  suppressed           boolean DEFAULT false,
  suppression_reason   text,
  prompt_version       text,
  error                text,
  created_at           timestamptz DEFAULT now()
);

-- 45-day cooldown lookup (domain already alerted recently)
CREATE INDEX idx_signals_cooldown
  ON signals(domain, client_id, alerted_slack, created_at DESC)
  WHERE alerted_slack = true;

-- Eval queries: score accuracy by prompt version (e.g. "v2.0 had X% false positives")
CREATE INDEX idx_signals_prompt_version
  ON signals(prompt_version, score DESC)
  WHERE scored = true;

-- Hot lead queries (excludes quarantined leads)
CREATE INDEX idx_signals_client_score
  ON signals(client_id, score DESC)
  WHERE scored = true AND requires_human_review = false;

-- Human review queue
CREATE INDEX idx_signals_review_queue
  ON signals(client_id, created_at DESC)
  WHERE requires_human_review = true;

-- 14-day cache lookup (domain + client)
CREATE INDEX idx_signals_cache_lookup
  ON signals(domain, client_id, created_at DESC)
  WHERE scored = true;

CREATE TABLE IF NOT EXISTS costs (
  id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id   text NOT NULL,
  date        date NOT NULL DEFAULT CURRENT_DATE,
  calls       integer DEFAULT 0,
  total_usd   numeric(10, 6) DEFAULT 0,
  created_at  timestamptz DEFAULT now(),
  UNIQUE(client_id, date)
);
