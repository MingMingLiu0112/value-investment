# Current maturity geometry and units v3

2026-09-09. Local research only. No production or canonical Excel changes.

## Completed evidence

Replayed all 46 pinned originals. Output:
`runtime/archived-current-maturity-46-v3-20260909.json`.
Parsed notes increased 29 -> 31; exact aggregate matches 27 -> 29;
unsupported/nonunique notes decreased 17 -> 15. No execution failures.
Original 29 note rows, totals, reconciliation flags, context and physical-page
fields were explicitly compared and remain unchanged.

- 300888, physical PDF page 229: ruled header with unruled same-page body.
  Closing total CNY 185,546,235.07 matches the retained verified balance.
  Prior total is 396,768,243.67. Current borrowing/payable cells are blank,
  so complete closing-component reconciliation remains false. Prior-only
  borrowing 175,108,600.02 and payables 6,017,646.86 were not shifted into
  current columns. Current leases are 184,899,235.07 and employee compensation
  647,000.00; no zero facts were created for the blanks.
- 600188, physical PDF page 263: applicable marker and explicit
  `单位：千元 币种：人民币`. Closing total 32,074,029 thousand yuan normalizes
  to CNY 32,074,029,000, matching the retained verified balance. Both period
  component sums reconcile. Employee benefits, provisions and current payables
  remain separate classification questions, not automatically borrowing.

## Correction to earlier diagnosis

002440 page 111 and 002452 page 170 have blank current totals in the original
notes, not a known numeric current total awaiting database insertion. Only prior
totals are printed: 400,286,666.67 and 20,640,000.00 respectively. Earlier
reports called these missing database facts, which did not describe the primary
evidence gap adequately. The bridge now emits
`financing_closing_unknown_or_invalid` before looking for a numeric database
match. No zero is inferred; a data collection retry alone cannot resolve this.

## Implementation and validation

Borderless extraction uses actual three-cell header geometry, assigns words
only wholly within one column, retains word coordinates and stops at the first
total. Missing totals, intervening labels, crossing columns and reversed headers
reject extraction. This does not support arbitrary borderless or nested tables.

Unit handling accepts only explicit yuan/thousand-yuan suffixes with optional
RMB currency and an optional checked-applicable marker. Wrong currency,
multiple units and checked-not-applicable markers reject parsing. Original cells
and the multiplier remain in each result.

59 focused tests passed; full suite 1141 passed, 18 existing Backtrader datetime
deprecation warnings. All 46 outputs retain complete debt unverified. These are
original-file extraction and arithmetic checks, not historical strategy returns.

Next: remaining 15 formats include global unit statements, year/datetime headers,
nested detail rows and alternate titles. Complete borrowing scope, financial
classification, historical backtests and portfolio guidance remain outstanding.
