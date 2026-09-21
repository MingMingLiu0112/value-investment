-- Add cold-archive state without modifying any evidence file or queue status.
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_status TEXT NOT NULL DEFAULT 'server_resident';
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_uri TEXT;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE official_disclosures ADD COLUMN IF NOT EXISTS archive_manifest_sha256 TEXT;
ALTER TABLE official_disclosures DROP CONSTRAINT IF EXISTS official_disclosures_archive_status_check;
ALTER TABLE official_disclosures ADD CONSTRAINT official_disclosures_archive_status_check
  CHECK (archive_status IN ('server_resident', 'cold_archived'));
CREATE INDEX IF NOT EXISTS official_disclosures_residency_lookup
  ON official_disclosures (archive_status, extraction_status, fetched_at);
