# Database Schema Snapshot

The production database structure is recorded in [server-schema-20260921.sql](../sql/server-schema-20260921.sql). It was generated with `pg_dump --schema-only --no-owner --no-privileges` from the value-investment PostgreSQL container.

The snapshot contains definitions, constraints and indexes for 14 public tables:

- `backup_audits`
- `candidate_tracking_observations`
- `data_points`
- `filing_candidates`
- `financial_enrichment_queue`
- `financial_quality_results`
- `institution_extractions`
- `instruments`
- `market_screen_results`
- `monthly_snapshots`
- `official_disclosures`
- `raw_documents`
- `task_runs`
- `valuation_results`

No table rows, database dumps, credentials, server address, backups, or raw filing files are included. Recreate this metadata with `scripts/export_server_schema.ps1`; it requires an authorized SSH key and writes only a schema-only SQL file.
