# Explicit debt-scope gate installed

Date: 2026-09-09. Production change completed and independently read back.

## Exact release

Target: `/opt/value-investment-agent/src/value_investment_agent/financial_quality.py`.

- Before SHA-256: `6b01ea1b85a61ef1b9259e51f5a56bd4d19731c0b4b968caf645b6f6ebe3c02c`.
- After SHA-256: `d575fe137005a6a673351fb02909759feb13552ad244916be3632b00d32235f4`.
- Only change: require `metadata.get('complete_debt_verified') is True` for
  interest-bearing debt. An absent marker no longer implicitly passes.
- Local financial-quality code has other differences from production. These
  were not deployed. The installed file was derived from the downloaded,
  hash-pinned production original, not copied from local source wholesale.

Stage: `/opt/value-investment-agent/deploy-staging/debt-scope-20260909`.
Original: `original/financial_quality.py` within that stage.
Receipt: `receipt.json`; local copy:
`runtime/debt-scope-installed-receipt-20260909.json`.
Read-only baseline copy: `runtime/production-financial-quality-before-scope-20260909.py`.

Installer: `scripts/install_debt_scope_gate.py`.
Probe: `scripts/probe_debt_scope_gate.py`.

## Verification actually performed

- Shared `exports/market-screen.lock` acquired nonblocking before replacement.
- Original backed up and syntax compiled; atomic replace uses the existing
  release helper. Probe failures restore the original and verify rollback hash.
- Existing image only (`--pull=never`), network disabled, 0.5 CPU,
  384 MiB memory, 512 MiB combined memory/swap, source mounted read-only.
  No image build, downloads, database credentials or database writes.
- Actual imported production module hash checked. Synthetic cases reject missing,
  false and malformed scope markers, quarantined evidence, unverified evidence,
  and the known four-line debt proxy; valid explicit scope passes the acceptance
  gate and ordinary ratios remain unaffected. This is not full debt certification.
- Independent SSH readback confirmed installed hash, PTA active and unchanged
  MainPID 236577. Available memory was about 1850 MiB before and 1853 MiB after;
  root free space remained 1959 MiB at the displayed precision.
- Inspected actual systemd daily-tracking override and its
  `/opt/value-investment-agent/deploy/server/run_candidate_tracking.sh` entry.
  It mounts `$root/src:/app/src:ro,Z` with `PYTHONPATH=/app/src`, so subsequent
  launches load this change. No claim that a complete scheduled run occurred
  during this release.
- 42 focused tests passed before deployment. Final local suite: 1107 passed,
  18 existing Backtrader datetime deprecation warnings.

## Boundaries

No service restart, PTA modification, Hermes modification, PostgreSQL change,
financial-data promotion, canonical Excel rewrite or real historical backtest.
The prior snapshot audit found no debt record accepted by the strict gate;
that snapshot is not a new live-database audit.

The small code-backup preflight is separate from database backup admission.
The 2-GiB database-backup reserve was not lowered; disk remains 95% used.
Large evidence collection and recoverable offsite backup still need adequate
storage and actual restore verification.

For any rollback, first acquire the shared lock, confirm current hash equals
the installed hash above, atomically restore the pinned original, then verify
the original hash. Do not rerun the installer blindly: it rejects a changed
baseline and an existing backup directory.

Remaining: financing-scope completeness and current-maturity classification,
historical point-in-time strategy tests, validated valuation and portfolio rules,
and end-to-end scheduled updates and backup recovery evidence.
