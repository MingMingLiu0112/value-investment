CREATE TABLE IF NOT EXISTS candidate_tracking_observations (
  run_id UUID NOT NULL REFERENCES task_runs(run_id),
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  source_id UUID NOT NULL REFERENCES raw_documents(document_id),
  quote_as_of TIMESTAMPTZ NOT NULL,
  quote_status TEXT NOT NULL CHECK (quote_status IN
    ('matched','missing_quote','invalid_price','price_conflict','cross_check_missing','stale_quote')),
  signal_blocked BOOLEAN NOT NULL,
  observation JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, symbol)
);
