# Annual Backfill Status

Updated: 2026-09-07

## Verified State

- The latest inspected workbook export contains 738 candidate companies.
- Exchange-universe reconciliation passed in that export; this is a listing
  coverage check, not proof of complete financial evidence.
- Main workbook views include all candidates. The reminder view contains 127
  priority-watch and 611 routine-watch entries in the inspected export.
- All reminders were blocked by financial or valuation evidence requirements.
- The WPS workbook was locked or changed during publication. The validated
  preview is `runtime/workbook-preview-20260907-181241.xlsx` and is not the
  canonical workbook. Later database updates are not included in that preview.

## Current Backfill Pipeline

`scripts/run_annual_batch.py` selects retained annual reports from the current
candidate pool, collects exact-period supplementary evidence, migrates
unpromoted PDF candidates, and runs automatic cross-source verification.

- Selection deduplicates successful parser migrations by symbol, report period,
  official file SHA-256, and parser version.
- A parser migration is NOT a declaration of complete financial verification.
- Original PDFs are hash-checked before parsing. Previously promoted candidates
  are not overwritten. Replaced candidate content is retained in task-run audit
  details.
- Supplemental records remain pending until official candidate matching passes.
- The batch is sequential, limited to 20 companies, and protected by a shared
  lock. Deployment invocations cap memory at 512 MiB and CPU at 0.5 core.
- Company-stage failures are recorded; successful preceding companies persist.
- The production secondary collector now performs network calls outside the
  write transaction and commits each issuer independently.

## Remaining Requirements

- Process remaining candidate annual reports, including failed/empty extraction
  cases; independently audit coverage rather than counting completed batches.
- Implement supported year-on-year evidence with explicit prior-period and
  restatement scope. Growth fields currently block complete general scoring.
- Expand supported statement layouts and specialized financial-sector evidence.
- Complete reliable fair-value inputs and current-period financial evidence
  before allowing buy/sell research suggestions.
- Integrate the new annual backfill into the maintained scheduled pipeline after
  operational validation. The new batch runner is currently invoked manually.
- Refresh calculations and export, then safely publish to the canonical WPS
  workbook when it is available. Preserve manual records and historical rows.
- Verify recurring operation, source provenance, reminder gates, and workbook
  publication end to end. No completion claim is justified yet.
