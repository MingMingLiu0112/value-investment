# 920174 Annual Report Diagnosis

Read-only diagnosis completed on 2026-09-07. No financial facts promoted.

- Official report: https://static.cninfo.com.cn/finalpage/2026-04-28/1225237333.PDF
- SHA-256: `ca95eb7a3987b86a0cbfe2bfc44dde55b6e45f0d877f3296ebe0f9d8c117c302`
- Issuer code on cover: 920174. Fiscal year: 2025.
- PDF pages: 256. Extracted text characters: 210077.
- Retained file hash matched the database hash; this is not an empty/scanned-only PDF.

## Evidence And Constraints

Page 12 uses a section heading for accounting data and financial indicators
without the prefix required by the current summary parser. This is a confirmed
summary-heading coverage gap, not yet a complete explanation for the absence
of statement candidates.

Page 14 explicitly describes a major asset reorganization and retrospective
restatement of 2023 and 2024 financial data. It also distinguishes the reporting
scope of the balance sheet from income data after an acquisition. Growth must
not be verified by combining historical original reports with the current
restated comparative figures.

Page 9 explains why registered year-end shares (90008718) differ from accounting
share capital (216904891): accounting recognition and share registration occurred
at different times. Do not substitute one for the other in per-share valuation.

## Remaining Work

Inspect the actual consolidated statement pages and unit declarations; add
heading/layout fixtures, including restatement rejection tests; re-extract as
pending candidates; corroborate same-period, same-scope amounts before promotion.
The zero-extraction run does not establish financial completeness.

Reproduce text diagnosis with `scripts/diagnose_annual_text.py 920174` in the
configured server container with the persistent evidence mount read-only.
