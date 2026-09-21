# Current maturity note reconciliation

Date: 2026-09-09. Local research; no production or canonical workbook changes.

## Actual original evidence

Six original PDFs from `runtime/nearcomplete-financing-20260909/manifest.json`
were rehashed before reading. Output:
`runtime/nearcomplete-financing-20260909/current-maturity-bridge-grid.json`.
The earlier `current-maturity-bridge.json` preserves the first four-note result.

New `current_maturities.py` reads an explicit numbered note, an explicit CNY
unit and ordered closing/opening columns. It handles the observed three-column
and nine-grid merged-cell forms without deleting real missing cells. Unknown
categories remain unknown; derivatives are not silently classified as borrowing.
Raw cells, section context, physical PDF pages, original hashes and URLs remain
in the audit. A reconciliation failure is recorded rather than corrected.

| Symbol | Physical PDF page | Current borrowing CNY | Current lease CNY | Other current maturity CNY | Note total CNY |
| --- | ---: | ---: | ---: | --- | ---: |
| 001233 | 203 | 26,341,866.63 | 3,248,904.67 | Not separately listed | 29,590,771.30 |
| 001386 | 191 | 293,633,910.04 | 15,480,543.10 | Not separately listed | 309,114,453.14 |
| 002011 | 175 | 6,886,329.16 | 7,299,371.72 | Not separately listed | 14,185,700.88 |
| 002043 | 154 | Not listed | 6,435,413.04 | Not separately listed | 6,435,413.04 |
| 002444 | 145 | Not listed | 71,554,757.51 | Not separately listed | 71,554,757.51 |
| 301376 | 190 | Not listed | 170,877,999.26 | Forward FX contracts 9,405,722.54 | 180,283,721.80 |

Not listed is not a synthesized zero fact. For every report the closing detail
sum matches the note total; that total independently matches an accepted
same-report current-maturity balance in the exported database evidence.

## Current-inclusive lease bridge

The audit subtracts only the explicit current-lease component from the financing
table's current-inclusive lease row, then compares the difference with the
retained independently corroborated noncurrent-lease balance. It does not
subtract the whole current-maturity aggregate.

| Symbol | Current leases | Noncurrent leases matched in database | Financing inclusive leases |
| --- | ---: | ---: | ---: |
| 002011 | 7,299,371.72 | 5,423,185.87 | 12,722,557.59 |
| 002043 | 6,435,413.04 | 19,880,999.99 | 26,316,413.03 |
| 002444 | 71,554,757.51 | 246,547,442.58 | 318,102,200.09 |
| 301376 | 170,877,999.26 | 910,991,589.95 | 1,081,869,589.21 |

All amounts CNY. All four equations reconcile exactly. The first two companies
use separate current-maturity and noncurrent-lease financing rows, so this
specific inclusive-row check does not apply to them.

For 301376, including all current maturities as borrowing/leases would incorrectly
add the CNY 9,405,722.54 forward FX balance to this subtotal. Whether and how
derivatives affect equity valuation requires a separate policy, not exclusion
from all risk analysis.

## Verification and remaining scope

44 focused tests passed before the nine-grid extension. Final full suite:
1123 passed, 18 existing Backtrader datetime warnings. Six real-PDF replay
completed; six aggregate and four inclusive-lease matches were independently
read back and asserted. This is not historical strategy performance evidence.

All reports and bridges retain `complete_debt_verified=false`. Note-total
corroboration does not independently verify each split or resolve other financing,
recourse, contractual payables, dividends or share-repurchase obligations.
Snapshot date remains 2026-09-08T23:15:40.333435+00:00, not a live DB query.

Next: use these explicit components to reconcile borrowing-inclusive rows and
inspect financing bills/other-payables terms, without duplicate current maturities.
No Excel cell or production debt record has been approved by this research audit.
