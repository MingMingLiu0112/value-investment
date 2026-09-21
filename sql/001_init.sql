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
  archive_status TEXT NOT NULL DEFAULT 'server_resident' CHECK (archive_status IN ('server_resident', 'cold_archived')),
  archive_uri TEXT,
  archived_at TIMESTAMPTZ,
  archive_manifest_sha256 TEXT,
  report_assurance TEXT NOT NULL DEFAULT 'statutory_report_assurance_not_classified',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'verified', 'rejected')),
  UNIQUE (symbol, sha256)
);
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_status TEXT NOT NULL DEFAULT 'server_resident';
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_uri TEXT;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_manifest_sha256 TEXT;
ALTER TABLE official_disclosures DROP CONSTRAINT IF EXISTS official_disclosures_archive_status_check;
ALTER TABLE official_disclosures ADD CONSTRAINT official_disclosures_archive_status_check
  CHECK (archive_status IN ('server_resident', 'cold_archived'));
CREATE INDEX IF NOT EXISTS official_disclosures_residency_lookup
  ON official_disclosures (archive_status, extraction_status, fetched_at);
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS report_assurance TEXT NOT NULL DEFAULT 'statutory_report_assurance_not_classified';
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'pending'
  CHECK (extraction_status IN ('pending', 'processing', 'extracted', 'no_candidates', 'failed'));
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_claimed_at TIMESTAMPTZ;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_error TEXT;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS extraction_parser_version TEXT NOT NULL DEFAULT 'filing-extract-v2';
CREATE INDEX IF NOT EXISTS official_disclosures_lookup
  ON official_disclosures (symbol, report_period, report_kind, published_at DESC);
CREATE INDEX IF NOT EXISTS official_disclosures_extraction_queue
  ON official_disclosures (extraction_status, extraction_claimed_at, extraction_attempts, published_at DESC);

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
  status TEXT NOT NULL CHECK (status IN ('candidate_pending_automated_verification', 'automatically_verified', 'superseded_by_parser')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (disclosure_id, field_name, page_number, source_label)
);
CREATE TABLE IF NOT EXISTS institution_extractions (
  disclosure_id UUID NOT NULL REFERENCES official_disclosures(disclosure_id),
  parser_version TEXT NOT NULL,
  candidate_count INTEGER NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (disclosure_id, parser_version)
);
ALTER TABLE filing_candidates DROP CONSTRAINT IF EXISTS filing_candidates_status_check;
UPDATE filing_candidates SET status = 'candidate_pending_automated_verification'
  WHERE status = 'candidate_requires_human_review';
ALTER TABLE filing_candidates ADD CONSTRAINT filing_candidates_status_check
  CHECK (status IN ('candidate_pending_automated_verification', 'automatically_verified', 'superseded_by_parser'));
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
-- Older deployments marked repeated transport failures for human review. Keep
-- their audit history, but put them back into the automated source-retry loop.
UPDATE financial_enrichment_queue
   SET status = 'retry', updated_at = now()
 WHERE status = 'manual_review_required';
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

CREATE TABLE IF NOT EXISTS financial_quality_results (
  symbol TEXT PRIMARY KEY REFERENCES instruments(symbol),
  model_type TEXT NOT NULL,
  quality_status TEXT NOT NULL,
  total_score NUMERIC,
  coverage_ratio NUMERIC NOT NULL,
  profitability_score NUMERIC,
  cash_flow_score NUMERIC,
  balance_sheet_score NUMERIC,
  growth_score NUMERIC,
  reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  calculation_details JSONB NOT NULL DEFAULT '{}'::jsonb,
  calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS financial_quality_results_status
  ON financial_quality_results (quality_status, total_score DESC NULLS LAST);

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

CREATE TABLE IF NOT EXISTS virtual_accounts (
  account_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL REFERENCES instruments(symbol),
  state JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS virtual_account_journal (
  account_id TEXT NOT NULL REFERENCES virtual_accounts(account_id),
  session_date DATE NOT NULL,
  entry JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, session_date)
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
CREATE INDEX IF NOT EXISTS candidate_tracking_latest
  ON candidate_tracking_observations(symbol, quote_as_of DESC, created_at DESC);
