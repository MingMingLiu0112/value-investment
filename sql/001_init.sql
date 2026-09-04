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
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE data_points ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS data_points_lookup ON data_points (symbol, field_name, period_label, created_at DESC);

CREATE TABLE IF NOT EXISTS official_disclosures (
  disclosure_id UUID PRIMARY KEY,
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  report_period TEXT NOT NULL,
  report_kind TEXT NOT NULL,
  title TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  sha256 TEXT NOT NULL,
  local_path TEXT NOT NULL,
  report_assurance TEXT NOT NULL DEFAULT 'statutory_report_assurance_not_classified',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'verified', 'rejected')),
  UNIQUE (symbol, sha256)
);
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS report_assurance TEXT NOT NULL DEFAULT 'statutory_report_assurance_not_classified';
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'pending'
  CHECK (extraction_status IN ('pending', 'processing', 'extracted', 'no_candidates', 'failed'));
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_claimed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS official_disclosures_lookup
  ON official_disclosures (symbol, report_period, report_kind, published_at DESC);
CREATE INDEX IF NOT EXISTS official_disclosures_extraction_queue
  ON official_disclosures (extraction_status, extraction_claimed_at, published_at DESC);

CREATE TABLE IF NOT EXISTS filing_candidates (
  candidate_id UUID PRIMARY KEY,
  disclosure_id UUID NOT NULL REFERENCES official_disclosures(disclosure_id),
  field_name TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  source_label TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('candidate_pending_automated_verification', 'automatically_verified')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (disclosure_id, field_name, page_number, source_label)
);
ALTER TABLE filing_candidates DROP CONSTRAINT IF EXISTS filing_candidates_status_check;
ALTER TABLE filing_candidates ADD CONSTRAINT filing_candidates_status_check
  CHECK (status IN ('candidate_pending_automated_verification', 'automatically_verified'));
UPDATE filing_candidates SET status = 'candidate_pending_automated_verification'
  WHERE status = 'candidate_requires_human_review';
CREATE INDEX IF NOT EXISTS filing_candidates_review ON filing_candidates (created_at DESC, disclosure_id);

CREATE TABLE IF NOT EXISTS market_screen_results (
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  screen_date DATE NOT NULL,
  sector TEXT NOT NULL,
  board TEXT NOT NULL DEFAULT '待板块映射',
  current_price NUMERIC NOT NULL,
  pe NUMERIC NOT NULL,
  pb NUMERIC,
  market_cap NUMERIC NOT NULL,
  initial_score NUMERIC NOT NULL,
  status TEXT NOT NULL,
  source_id UUID NOT NULL REFERENCES raw_documents(document_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, screen_date)
);
ALTER TABLE market_screen_results ALTER COLUMN pb DROP NOT NULL;
ALTER TABLE market_screen_results ADD COLUMN IF NOT EXISTS board TEXT NOT NULL DEFAULT '待板块映射';
UPDATE market_screen_results
   SET board = sector, sector = '待行业映射'
 WHERE board = '待板块映射'
   AND sector IN ('主板', '创业板', '科创板', '北交所', '待板块映射');
CREATE INDEX IF NOT EXISTS market_screen_results_lookup
  ON market_screen_results (screen_date DESC, initial_score DESC);

CREATE TABLE IF NOT EXISTS financial_enrichment_queue (
  symbol TEXT PRIMARY KEY REFERENCES instruments(symbol),
  screen_date DATE NOT NULL,
  priority_score NUMERIC NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending_official_filings', 'processing', 'official_filings_archived', 'retry', 'manual_review_required')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE financial_enrichment_queue DROP CONSTRAINT IF EXISTS financial_enrichment_queue_status_check;
ALTER TABLE financial_enrichment_queue ADD CONSTRAINT financial_enrichment_queue_status_check
  CHECK (status IN ('pending_official_filings', 'processing', 'official_filings_archived', 'retry', 'manual_review_required'));
CREATE INDEX IF NOT EXISTS financial_enrichment_queue_next
  ON financial_enrichment_queue (status, priority_score DESC, updated_at);

CREATE TABLE IF NOT EXISTS valuation_results (
  symbol TEXT PRIMARY KEY REFERENCES instruments(symbol),
  current_price NUMERIC,
  fair_value NUMERIC,
  safety_margin NUMERIC,
  valuation_status TEXT NOT NULL,
  build_signal TEXT NOT NULL,
  target_weight NUMERIC NOT NULL DEFAULT 0,
  data_status TEXT NOT NULL,
  calculation_details JSONB NOT NULL DEFAULT '{}'::jsonb,
  calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE valuation_results ADD COLUMN IF NOT EXISTS calculation_details JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS monthly_snapshots (
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  snapshot_month TEXT NOT NULL CHECK (snapshot_month ~ '^[0-9]{4}-[0-9]{2}$'),
  current_price NUMERIC NOT NULL,
  fair_value NUMERIC,
  safety_margin NUMERIC,
  valuation_status TEXT NOT NULL,
  build_signal TEXT NOT NULL,
  target_weight NUMERIC NOT NULL DEFAULT 0,
  revenue_yoy NUMERIC,
  net_income_yoy NUMERIC,
  roe NUMERIC,
  data_status TEXT NOT NULL,
  snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, snapshot_month)
);
ALTER TABLE monthly_snapshots DROP CONSTRAINT IF EXISTS monthly_snapshots_snapshot_month_check;
ALTER TABLE monthly_snapshots ADD CONSTRAINT monthly_snapshots_snapshot_month_check
  CHECK (snapshot_month ~ '^[0-9]{4}-[0-9]{2}$');

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
