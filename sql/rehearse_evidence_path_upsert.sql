-- Isolated PostgreSQL behavior test; no persistent tables are changed.
BEGIN;
SET LOCAL statement_timeout = '10s';
CREATE TEMP TABLE evidence_path_probe (sha256 text PRIMARY KEY, local_path text) ON COMMIT DROP;
INSERT INTO evidence_path_probe VALUES ('same-hash', NULL);
INSERT INTO evidence_path_probe VALUES ('same-hash', '/app/evidence/financial_snapshots/same-hash.json')
ON CONFLICT (sha256) DO UPDATE SET
local_path = COALESCE(NULLIF(EXCLUDED.local_path, ''), evidence_path_probe.local_path);
DO $$ BEGIN
    IF (SELECT local_path FROM evidence_path_probe WHERE sha256='same-hash')
       IS DISTINCT FROM '/app/evidence/financial_snapshots/same-hash.json' THEN
        RAISE EXCEPTION 'Backfilled evidence path missing';
    END IF;
END $$;
INSERT INTO evidence_path_probe VALUES ('same-hash', NULL)
ON CONFLICT (sha256) DO UPDATE SET
local_path = COALESCE(NULLIF(EXCLUDED.local_path, ''), evidence_path_probe.local_path);
INSERT INTO evidence_path_probe VALUES ('same-hash', '')
ON CONFLICT (sha256) DO UPDATE SET
local_path = COALESCE(NULLIF(EXCLUDED.local_path, ''), evidence_path_probe.local_path);
DO $$ BEGIN
    IF (SELECT local_path FROM evidence_path_probe WHERE sha256='same-hash')
       IS DISTINCT FROM '/app/evidence/financial_snapshots/same-hash.json' THEN
        RAISE EXCEPTION 'Unarchived collection erased evidence path';
    END IF;
    IF (SELECT count(*) FROM evidence_path_probe) <> 1 THEN
        RAISE EXCEPTION 'Duplicate evidence document';
    END IF;
END $$;
SELECT 'path backfill, preservation and deduplication passed' AS result;
ROLLBACK;
