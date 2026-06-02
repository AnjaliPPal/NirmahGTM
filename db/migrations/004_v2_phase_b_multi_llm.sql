-- Migration 004: Phase B — Multi-LLM routing columns
-- Run in Supabase SQL editor if you have an existing signals table.
-- Safe to run multiple times (IF NOT EXISTS / DO NOTHING pattern).

ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS model_costs       jsonb,        -- per-model cost: {"gpt-4o-mini": 0.0001, "claude-sonnet-4-6": 0.003}
  ADD COLUMN IF NOT EXISTS pre_filter_passed boolean DEFAULT true,  -- false = pre-filter rejected, Claude not called
  ADD COLUMN IF NOT EXISTS pre_filter_reason text;         -- why pre-filter passed or failed
