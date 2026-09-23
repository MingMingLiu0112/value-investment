# M1 Gree Dividend Lifecycle Receipt

Updated: 2026-09-23. Scope: `M1-FIXED-SAMPLE-RESEARCH-WORKBENCH`,
`action=no_order`. This receipt records the completed Gree `000651` lifecycle
evidence segment; it does not graduate M1.

## Statutory evidence

The collector `scripts/collect_m1_dividend_lifecycle.py` now archives two
official CNINFO implementation notices for Gree:

- FY2024 final: `https://static.cninfo.com.cn/finalpage/2025-08-22/1224534765.PDF`
  - SHA-256 `8d4b488560f9d3ec81c9349757cda9d9bdee4cdbbecb97911761e2f6a93b4b64`
- FY2025 interim: `https://static.cninfo.com.cn/finalpage/2026-01-16/1224936369.PDF`
  - SHA-256 `89ab10370d6601c698426eb6a37dba664687ca03ee59a46208e104068d62d3dd`

Evidence run: `runtime/company-research/m1-dividend-lifecycles/20260923T055500Z/`.
Each PDF has an extracted-text receipt with a parser version and its own
SHA-256.

## Verified facts

- FY2024 final ordinary DPS `2.00`: approved `2025-06-30`, ex-date
  `2025-08-29`, payment date `2025-08-29`.
- FY2025 interim ordinary DPS `1.00`: approved `2025-11-24`, ex-date
  `2026-01-23`, payment date `2026-01-23`.
- FY2025 final ordinary DPS `2.00` remains `proposed`.
- No special dividend and no forward payout forecast are claimed.

## Package and presentation

`config/m1-distribution-packages-v1/000651-mature-manufacturing.json` now
verifies five sources: two annual filings, the two implementation notices, and
the dual-source `2026-09-22` close manifest. The close is `38.18`.

Yield snapshots are separated by layer:

- trailing paid `3.00` / `38.18` = `0.07857517024620220010476689366`, `READY`
- declared FY2025-final proposal `2.00` / `38.18` =
  `0.05238344683080146673651126244`, `READY`
- normalized scenario, `NOT_READY`, because the normalized dividend basis is
  not assessed

The integrated workbook was rebuilt, verified in WPS, and atomically published
to the user's WPS workbook after the source hash, lock state, and all 36
retained worksheet XML parts were rechecked.

- Pre-publication original SHA-256:
  `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea`
- Published SHA-256:
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- Candidate:
  `runtime/m1-integrated-dividend-20260923T055026Z/M1-integrated-candidate.xlsx`
- Backup:
  `runtime/workbook-backups/stage-frontend-19fcc1b85491496eb0bb706d0dd11bcc/before.xlsx`

WPS pre-publication and published read-only receipts:

- `runtime/m1-integrated-dividend-20260923T055026Z/wps-integrated-receipt.json`
- `runtime/m1-integrated-dividend-20260923T055026Z/wps-published-receipt.json`

## Verification

- Focused distribution, valuation, workbook, application, replay, quote,
  event-scan, and staging tests: `96 passed, 1 skipped`.
- `compileall` passed.
- `git diff --check` passed.

Remaining blockers are unchanged: formal G3 human valuation approval,
treasury/finance-company and legal-entity distributable-cash mapping, and the
unassessed normalized dividend basis.
