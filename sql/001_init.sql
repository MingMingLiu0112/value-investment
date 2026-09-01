CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  strategy_type TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_documents (
  document_id UUID PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL,
  parser_version TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  local_path TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS data_points (
  data_point_id UUID PRIMARY KEY,
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  field_name TEXT NOT NULL,
  period_label TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT NOT NULL,
  source_id UUID NOT NULL REFERENCES raw_documents(document_id),
  validation_status TEXT NOT NULL CHECK (validation_status IN ('pending','verified','conflict','failed')),
  human_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS data_points_lookup ON data_points (symbol, field_name, period_label, created_at DESC);

CREATE TABLE IF NOT EXISTS valuation_results (
  symbol TEXT PRIMARY KEY REFERENCES instruments(symbol),
  current_price NUMERIC,
  fair_value NUMERIC,
  safety_margin NUMERIC,
  valuation_status TEXT NOT NULL,
  build_signal TEXT NOT NULL,
  target_weight NUMERIC NOT NULL DEFAULT 0,
  data_status TEXT NOT NULL,
  calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_runs (
  run_id UUID PRIMARY KEY,
  task_name TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS backup_audits (
  backup_id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL,
  backup_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  manifest JSONB NOT NULL,
  restore_status TEXT NOT NULL CHECK (restore_status IN ('created','passed','failed')),
  rto_seconds NUMERIC,
  rpo_seconds NUMERIC,
  verified_at TIMESTAMPTZ
);
