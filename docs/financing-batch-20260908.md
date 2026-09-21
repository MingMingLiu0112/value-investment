# Candidate financing coverage audit

Date: 2026-09-08. Research only; no debt fact promotion or strategy approval.

## Reproducible Evidence

- Input: `runtime/server-export-payload.json`.
- Download and identity audit: `runtime/candidate-financing-batch-20260908-01/manifest.json`.
- Cross-page audit: `runtime/candidate-financing-continuation-20260908.json`.
- All five original PDF hashes matched the exported archive hashes. This is an
  archive identity check, not independent confirmation of financial accuracy.
- Selection: current candidates missing interest-bearing debt, ascending number
  of missing quality fields then symbol, unique 2025 annual report only, limit 5.
  Export coverage is bounded; this is not a census of all archived annual reports.

## Actual Results

| Symbol | Physical page | Result | Remaining work |
| --- | --- | --- | --- |
| 000429 | 154 | Six-column table extracted | Dividends excluded; other payables and long-term payables require scope evidence; blank bond closing is not automatically zero |
| 000581 | 148 | Explicitly not applicable | Use balance sheet and debt notes; not-applicable table does not establish zero debt |
| 000651 | 178-179 | Heading-only page followed by financing table | Different header arrangement; no local explicit unit; bank borrowings and other balances have unresolved scope |
| 000700 | 169 | Table found, amount fragments unsupported | Amount integer and decimal portions wrap; preserve column alignment before reconciliation |
| 000758 | 144 | Six-column table extracted; opening/closing component sums match | Table includes borrowings, not proof that leases or other financing liabilities do not exist |

The Gree continuation is captured only when no intervening content except the
page number follows the title. Capture stops at the next numbered note. The
original adjacent-page text and physical page remain in the audit result.
No missing currency unit is invented and no debt value is approved by capture.

Gree page 179 reports closing bank borrowings and other of 86,220,113,796.03,
dividends payable of 5,591,546,379.65 and leases of 739,878,353.06, with a total of
92,551,538,528.74. These are literal table amounts with currency scope not yet
approved by this audit. The total must not be used as interest-bearing debt.

Molding Technology page 169 splits e.g. the short borrowing closing amount into
`1,223,317,43` and `6.86`. A future parser must retain both line and column
evidence; whitespace removal across the whole table is unsafe. Its financing
table also includes dividends, so successful numerical parsing alone would not
complete debt verification.

## Operational Boundaries

No server code, database facts, scheduler, holdings, or Excel cells changed in
this audit. Production parsing remains unchanged. Backtesting still requires
point-in-time valuation inputs and audited corporate actions/execution rules.

## Ruled-Cell Follow-up

`runtime/candidate-financing-cells-20260908.json` reruns the same five original
PDFs with the research-only `pdfplumber==0.11.9` fallback. Three tables now parse
(000429, 000700, 000758), up from two. The dependency is in the optional research
extra and was not installed on the server.

For 000700, the library preserves the actual ruled cells and their wrapped text.
The parser joins fragments only inside a single cell, preserving merged-cell
placeholders, actual blank cells, the table bounding box and raw strings.
It requires the financing heading, explicit CNY unit, both header rows, six
amount columns and an arithmetically reconciled total. It does not stitch whole
text rows or infer missing zeros.

Extracted closing amounts (CNY): short borrowings 1,223,317,436.86; dividends
payable 300,138,641.70; leases 135,508,711.65; total 1,658,964,790.21.
Long borrowings and long-term payables have blank closing cells, retained as
null. Consequently complete opening/closing component reconciliation and full
component movements remain false, even though the total roll-forward matches.
No `interest_bearing_debt` value was promoted.

## Second Batch and a Scope Counterexample

`runtime/candidate-financing-batch-20260908-02/manifest.json` records offset 5,
limit 10 against the same payload hash, so the batch can be reproduced without
silently restarting from the first five issuers. All ten PDF hashes matched.

| Symbol | Physical page | Result |
| --- | --- | --- |
| 000885 | 153 | Explicitly not applicable; not zero debt |
| 000928 | 158 | Explicitly not applicable; not zero debt |
| 002091 | 231 | Ruled-cell parser; opening/closing sums match, incomplete movements |
| 002249 | 184 | Existing layout parser; incomplete component reconciliation |
| 002440 | 119 | Title found; components unsupported |
| 002452 | 182 | Explicitly not applicable; not zero debt |
| 002572 | 182 | Ruled-cell parser; balances and all movements reconcile |
| 002668 | 150 | Explicitly not applicable; not zero debt |
| 002701 | 190 | Title found; components unsupported |
| 002756 | 153 | Title found; components unsupported |

For 002572, page 182 financing-table closing total is CNY 2,632,536,369.96,
comprising short borrowings 2,170,259,157.14, noncurrent long borrowings
92,500,000.00, and current long borrowings 369,777,212.82. Every movement and
component sum reconciles, but this is still NOT complete financing debt.

PDFium extraction of the same original report, physical pages 170-171, identifies
lease liabilities of 46,948,470.68, less the current portion 19,999,236.03, leaving
noncurrent 26,949,234.65. Page 97 also reports the noncurrent lease balance.
The complete lease balance is absent from the page 182 financing-table total.
Current and noncurrent lease balances must not be added to the gross lease
balance a second time. Remaining financing scope still needs investigation.

This real counterexample rules out promoting a reconciled financing table total
directly to `interest_bearing_debt`. It does not invalidate the table or issuer
report; it shows the table and the project's required metric have different
scopes. No production values or Excel cells were updated from these findings.

### Additional 002572 Scope Checks

Read original PDFium text, physical pages 168-171. Other payables include
external-party balances of CNY 65,353,314.15 and an "other" category of
5,183,114.97, whose financing nature is not established here. Other current
liabilities include "other" of 12,992,203.09. The short-term bond movement note
states not applicable, while long-term payables total explicitly reads 0.00
and consists of a government research project special payable. These findings
do not establish the financing nature of the unresolved payable categories.

Local scoring now rejects `interest_bearing_debt` when metadata explicitly
contains `complete_debt_verified` with any value other than boolean true.
All three financing table parsers emit false for this field. That flag is a
negative safeguard, not a sufficient approval contract: true does not override
cross-source checks, quarantine, or the existing incomplete-proxy rejection.
Legacy points without the flag retain their existing behavior and still need
a future scope-evidence migration. No server deployment was performed.

## Third Batch

`runtime/candidate-financing-batch-20260908-03/manifest.json`: offset 15, limit
10, all original hashes matched. No newly parsed component tables. Titles were
found for 002833 (p168), 002928 (p158), 300888 (p249), 002033 (p163), 002061
(p202), 000088 (p208), 000089 (p172), 000400 (p170), 000551 (p176), and 000568
(p152). The tables for 002033 and 000400 explicitly state not applicable.
The other eight are unsupported, not absent debt.

Direct pypdf layout inspection of 000089 p172 shows a rearranged and wrapped
header with a blank total movement column. Its reported total includes dividends.
The current parser requires a fully populated total roll-forward, so this format
must not be forced through by inserting zeros.

Direct inspection of 000568 p152 shows component rows but no total on that page.
The existing heading-only continuation capture does not handle tables split
mid-body. Adjacent-page scope and any total still require inspection before a
multi-page table parser can approve an extraction.

Three batches now contain 25 distinct candidate reports, not 25 verified debt
metrics. Using the latest rerun for the first batch, six component tables parse
across those reports; no complete debt value has been promoted by these audits.
