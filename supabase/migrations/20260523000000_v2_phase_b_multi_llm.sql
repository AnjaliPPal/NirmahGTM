-- SignalOS v2.0 Phase B — Multi-LLM routing columns

ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS model_costs        jsonb,
  ADD COLUMN IF NOT EXISTS pre_filter_passed  boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS pre_filter_reason  text;
