# Current maturity format coverage v2

Date: 2026-09-09. Local research replay only; no server or canonical Excel edit.

## Actual results

Replayed the same 46 archived reports, verifying original hashes before reading.
Output: `runtime/archived-current-maturity-46-v2-20260909.json`.
Elapsed: 81.19 seconds. Previous output remains unchanged.

- Parsed notes: 25 -> 29.
- Exact aggregate matches to accepted same-period/same-original database facts:
  23 -> 27.
- Unsupported or nonunique notes: 21 -> 17.
- Two parsed notes still lack corresponding snapshot facts: 002440 and 002452.
- No per-company execution exception. No complete-debt approvals.
- Explicit comparison confirmed all previous 25 note rows, totals, reconciliation
  flags, context, physical pages and downstream bridges are unchanged.

## New original evidence

| Symbol | Physical PDF pages | Closing current maturity total CNY | Components |
| --- | --- | ---: | --- |
| 002249 | 170-171 | 293,755,184.08 | Borrowings 17,033,604.38; leases 199,236,797.72; provisions 77,484,781.98 |
| 002572 | 169-170 | 389,776,448.85 | Borrowings 369,777,212.82; leases 19,999,236.03 |
| 002668 | 141 | 126,706,680.23 | Borrowings 43,850,790.96; leases 82,855,889.27; employee compensation explicitly 0.00 |
| 002701 | 177 | 1,338,232,451 | Borrowings 768,112,839; long-term payables 490,024,031; leases 80,095,581 |

All four closing component sums reconcile. Original URLs, SHA-256, raw cells,
database IDs and secondary-source references are retained in the JSON output.

002249's provisions are not automatically borrowing. 002701's current long-term
payables require contractual financing classification. Neither whole current
maturity total can be used as unqualified interest-bearing debt merely because
its arithmetic matches. Unknown prior-period cells are not filled with zero.

## Implementation boundaries

- Only the observed three-column adjacent-page table form is joined. The first
  page must carry the exact numbered note, CNY unit and ordered columns, have
  no total yet, and end with only a page number after the partial table.
- The following page must start with one annual-report company header and the
  first ruled table, with either identical repeated headers or directly a
  current-maturity row. Intervening text/sections and completed prior tables
  reject the join. Both page numbers, tables and boundary text are retained.
- Added the observed eight-grid layout and long labels spanning the first
  three subcells of the nine-grid layout. Actual blanks are never filtered away.
- Integer amounts are accepted only within the explicit CNY note context; no
  implicit thousand or ten-thousand multiplier is used.
- Parser identifiers now distinguish explicit grid v2 and adjacent continuation v2.

## Verification and remaining work

28 focused tests passed. Full suite: 1135 passed, 18 existing Backtrader datetime
deprecation warnings. Real 46-PDF replay and original-25 equality assertions
completed. These are extraction/reconciliation checks, not strategy backtests.

Remaining formats include borderless tables, globally stated rather than local
units, dated/year-end headings, nested subcomponents and alternate note titles.
For example 300888 has a ruled header but borderless body on the same page;
the nonempty tail correctly prevents attaching the next unrelated table.
001872 has nested borrowing subcomponents that must not be double-counted.
These cases remain unparsed until their structure and unit provenance are handled.

Follow-up: v3 handles 300888's same-page body and 600188's explicit thousand-yuan
unit. It also corrects the 002440/002452 diagnosis: their current totals are
blank in the original notes. See `maturity-geometry-v3-20260909.md`.
