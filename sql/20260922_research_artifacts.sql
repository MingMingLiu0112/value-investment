-- C3 Research Artifact persistence.
--
-- This migration is append-only and creates no relationship to the legacy
-- valuation_results table. Old valuation_results keeps its historical
-- current_price/fair_value/safety_margin/build_signal/target_weight semantics.
--
-- Intended execution environments: local, disposable test, and GitHub CI
-- PostgreSQL. This file must not be run against the production database by an
-- automated C3 command.

CREATE TABLE IF NOT EXISTS research_artifacts (
  artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type TEXT NOT NULL
    CHECK (scope_type IN ('security', 'batch', 'review')),
  scope_key TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  as_of DATE,
  available_at TIMESTAMPTZ NOT NULL,
  payload_sha256 TEXT NOT NULL
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  canonical_payload BYTEA NOT NULL,
  evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(evidence_refs) = 'array'),
  run_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  natural_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS research_artifacts_scope_lookup
  ON research_artifacts (scope_type, scope_key, artifact_type, as_of DESC, available_at DESC);

CREATE INDEX IF NOT EXISTS research_artifacts_hash_lookup
  ON research_artifacts (payload_sha256);

CREATE TABLE IF NOT EXISTS research_artifact_heads (
  scope_type TEXT NOT NULL
    CHECK (scope_type IN ('security', 'batch', 'review')),
  scope_key TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  artifact_id UUID NOT NULL,
  schema_version TEXT NOT NULL,
  as_of DATE,
  available_at TIMESTAMPTZ NOT NULL,
  payload_sha256 TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (scope_type, scope_key, artifact_type)
);

CREATE INDEX IF NOT EXISTS research_artifact_heads_artifact
  ON research_artifact_heads (artifact_id);

CREATE TABLE IF NOT EXISTS research_artifact_references (
  artifact_id UUID NOT NULL REFERENCES research_artifacts(artifact_id),
  reference_id TEXT NOT NULL,
  reference_kind TEXT,
  referenced_artifact_id UUID REFERENCES research_artifacts(artifact_id),
  external_uri TEXT,
  external_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (artifact_id, reference_id)
);
