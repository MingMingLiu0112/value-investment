# v33 controlled production release

Date: 2026-09-09. Production parser is now
`filing-extract-v33-cross-page-current-debt`.

Only filing_extract.py changed in content. Its SHA-256 changed from
83f5536327378d7d2214fbec33654c0363efc6ba008c7bfb645222df00a7e963 to
5e2d6462ed419d6a620e3e1e3aaa3ca88d0850d0389d55291e571bc99dfd5606.
The other three files were copied from the hash-checked installed v32 bundle,
not from the dirty local working tree.

## Evidence

- Builder: scripts/build_parser_v33_bundle.py.
- Bundle: runtime/parser-release-v33-20260909.
- Existing 20-report replay: 275 candidate signatures unchanged, including
  12 cross-page report-unit evidence records.
- Additional real-PDF regression: 600496 annual report, SHA-256
  7063bee136b03667ca138335ce8ac0950406762e64b707f5771483b239d4fa03.
  Exactly one current_portion_long_term_debt candidate: 468249668.22 CNY,
  page 80, with page 81 continuation citation retained through the database
  excerpt helper. The PDF was already present; no new PDF download occurred.
- Both staged and installed-path server replays passed the 20-report set
  plus the separate 600496 case. Installed replay checked actual loaded hashes.
- Local suite: 1038 passed, 18 existing Backtrader deprecation warnings.
- Installer tests cover mismatched production and failed-probe rollback.
- Installation returned installed=true, installed_replay_passed=true,
  database_written=false.
- Server backup: /opt/value-investment-agent/deploy-staging/parser-v33-backup-20260909.
- Local receipt: runtime/parser-v33-installed-receipt-20260909.json.

The shared market-screen lock and 0.5 CPU / 384 MiB memory / 512 MiB total
memory-plus-swap limits were retained. No PTA, gateway, or database restart
was performed. The already tested installer was staged within the v33 bundle
because there was no installer at the staging-root path.

## Remaining work

This release changes extraction capability, not financial approval. The
600496 candidate still needs controlled registration and independent-source
verification before a downstream refresh and Excel publication. Four debt
components do not certify complete interest-bearing debt. No new workbook
publication or historical strategy-performance result occurred in this release.
The previous 06:07 workbook publication remains the last confirmed publication.

The older v33 diagnosis document describes pre-release state; this dated
installation record supersedes its statement that production remains v32.
