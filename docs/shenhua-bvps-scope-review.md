# Shenhua historical BVPS scope review

Research date: 2026-09-08. Not production approval or strategy validation.

## Evidence inspected

Source manifest: `runtime/historical-filing-index/20260908T041326996681Z/pdfs/manifest-20260908T042044684445Z.json`.
Each manifest entry retains its original announcement metadata and URL.

- 2014 annual report, SHA-256 `45dba6cb163a2dc4fd1c3be5d1b4430fd2cf54820185d5acac2a1e68d574c1eb`: PDF page 18 reports current BVPS 14.67 and prior 13.69. Its footnote directs readers to definitions. Pages 3-6 were inspected; definitions include EPS and return on equity, but no explicit BVPS formula. That reference alone does not prove the BVPS numerator or denominator.
- 2015 annual report, SHA-256 `a8b83a21c7e50ddff4d5e8e90d01f570fb2238d8f0bfcee41eaddff53f4e59c7`: PDF page 8 reports current 14.72, prior restated 14.84 and originally reported 14.67. Page 17 repeats 14.72 and the restated comparative 14.84.
- 2016 annual report, SHA-256 `564fcaab934004549537add2b76f95f2e5fa9f91d47d628e1a60c5b6fcb5bc5a`: PDF pages 8 and 17 report current 15.70 and prior 14.72.
- 2024 annual report, SHA-256 `4b3a8db26ae2fb07083966fadea0f92535cfbe6d0791c3318c6511113b138e8f`: PDF page 8 reports 21.48, 20.57 and 2022 comparative 19.82. Its accounting-policy note refers to a 2023-04-29 announcement, which is not verified by this review.

## Extraction result

`runtime/shenhua-historical-bvps-v5.json` contains candidates for all 11 reports, 2014-2024. PDFium and pypdf agree for all 11. This is same-source decoder agreement, not independent financial verification. The focused parser suite passed 24 tests.

## Consequences for validation

### Completed 2014 arithmetic reconciliation

Original URL: https://static.cninfo.com.cn/finalpage/2015-03-21/1200725016.PDF

PDF page 119 explicitly labels the consolidated balance sheet in RMB millions, at 2014-12-31. Parent shareholders' equity is 291,789; minority interests are 63,838; total equity is 355,627. PDF page 73 gives total shares of 19,889,620,455, comprising A shares 16,491,037,955 and H shares 3,398,582,500. It states no preferred shares were issued and no change in total shares during the reporting year.

Decimal arithmetic: `291789000000 / 19889620455 = 14.67041569044360127786058349`, rounding to the reported 14.67. Using total equity instead would yield 17.88002947590685938003737538, which is not the disclosed BVPS. Both PDFium and pypdf contain the cited amounts on the cited pages. This verifies this specific numerical reconciliation, not independent-source verification or the entire historical series.

The announcement index supplies 2015-03-21 with date-only precision. Exact publication availability and the applicable first executable market session remain unverified. No `backtest_ready` flag is promoted by this arithmetic check.

1. Preserve both the original 2014 value 14.67 and later comparative 14.84 with separate disclosure availability. Never overwrite a historical decision input with a later restatement.
2. Reconcile each current value against consolidated equity attributable to parent common shareholders divided by matching period-end shares, with consistent units and disclosed rounding. Do not substitute total equity including non-controlling interests, floating shares, or EPS weighted-average shares.
3. Verify preferred/perpetual-equity deductions where applicable before calling the result common-equity BVPS.
4. Keep `equity_scope_verified` and `backtest_ready` false until that reconciliation and disclosure timing checks pass. No Excel signal or server configuration was changed in this review.
