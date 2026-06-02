-- SignalOS v2.0 Phase C — pgvector RAG

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_signals_embedding
  ON signals USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE OR REPLACE FUNCTION match_signals(
  query_embedding  vector(1536),
  match_client_id  text,
  match_count      int DEFAULT 5
)
RETURNS TABLE (
  company_name  text,
  domain        text,
  score         integer,
  top_signal    text,
  outcome       text,
  similarity    float
)
LANGUAGE sql STABLE AS $$
  SELECT
    s.company_name,
    s.domain,
    s.score,
    s.top_signal,
    COALESCE(eo.outcome, 'no_reply') AS outcome,
    1 - (s.embedding <=> query_embedding) AS similarity
  FROM signals s
  LEFT JOIN eval_outcomes eo
         ON eo.signal_id = s.id AND eo.client_id = s.client_id
  WHERE s.client_id = match_client_id
    AND s.scored    = true
    AND s.embedding IS NOT NULL
  ORDER BY s.embedding <=> query_embedding
  LIMIT match_count;
$$;
