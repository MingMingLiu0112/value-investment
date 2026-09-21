# Tied financial inputs: production investigation

Date: 2026-09-09. Read-only production SQL; no database or service changes.

## Confirmed cause of unstable input selection

`latest_points` uses DISTINCT ON (symbol, field_name), ordered by period_label
DESC and created_at DESC. Production contains conflicting values with identical
periods and creation timestamps. This order does not uniquely select a row.
The derivative and export may therefore select different inputs without any
new financial information arriving. Adding UUID order alone would conceal the
conflict, not establish the correct financial fact.

All six investigated inputs remain `verified`, without supersession metadata.
Each pair references the same official document and secondary data point:

| Symbol | Field | Values (CNY) | PDF pages | Shared created_at (UTC) |
| --- | --- | --- | --- | --- |
| 000612 | operating_cost | 5038014974.44 / 5040616835.68 | 81 / 83 | 2026-09-07 12:32:26.046659 |
| 002125 | bonds_payable | 450138600.00 / 450138560.42 | 161 / 80 | 2026-09-07 17:29:46.801058 |
| 300014 | short_term_borrowings | 706335000.01 / 706335000.00 | 86 / 198 | 2026-09-07 14:05:38.138771 |

Production derivation v4 already compares retained input facts. Its refresh
caller processes current and annual views separately. Missing v5 deployment
does not by itself explain these discrepancies.

## Required remediation

1. Surface latest-timestamp conflicting values/units as unresolved, retaining
   all IDs; do not mark an arbitrary selected input accepted.
2. Invalidate or block downstream cached derivatives using unresolved inputs.
3. Check original pages for consolidated versus parent-only scope, rounding,
   and note-table interpretation before choosing a canonical fact. Page
   differences alone do not prove any of those explanations.
4. Audit the full database for this collision pattern, then correct promotion
   rules and add database-level selection tests.
5. Refresh derived outputs, quality scores and canonical Excel after evidence
   resolution. Preserve historical evidence rather than deleting alternatives.

The current export replay report is
`runtime/derivation-input-lineage-audit-20260909.json`. It covers 738 candidates,
not the entire historical database. No claim of issuer restatement, verified
strategy performance, or completed remediation is made.

## Full production collision census

Read-only transaction with 20-second statement timeout completed successfully.
Initial current-view raw value/unit comparison found 373 cash pairs; sampled
000028, 000030 and 000060 are exact CNY/CNY 100M equivalents, all pending.
The resolver now normalizes the three supported CNY units for comparison only,
retains original selected units, and does not promote pending data.

After exact numeric currency normalization, the full production database has:

| Field | Current view | Annual view |
| --- | ---: | ---: |
| cash | 1 | 2 |
| short_term_borrowings | 4 | 2 |
| operating_cash_flow | 2 | 7 |
| operating_cost | 1 | 1 |
| revenue | 1 | 2 |
| bonds_payable | 0 | 1 |
| long_term_borrowings | 0 | 1 |
| net_income | 0 | 1 |
| Total company-field groups | 9 | 17 |

Views overlap; these are not distinct company counts. Census compares value,
normalized unit, validation status, quarantine and automatic verification.
It establishes unresolved record ambiguity, not which source is correct.
The local query/resolver change is not yet deployed. Targeted tests: 8 passed,
including currency equivalence, unsupported units, evidence status disagreement,
dependency propagation and permutation invariance.

## Original PDF findings

All three CNINFO downloads match the pre-existing database SHA-256 values.
Local reproducible extraction: `scripts/check_tied_input_pdf_pages.py`;
artifacts: `runtime/tied-input-original-pages-20260909/`.

- 000612: page 80 introduces the consolidated income statement; page 81
  reports operating cost 5,038,014,974.44 CNY. Page 83 explicitly introduces
  the parent-only income statement and reports 5,040,616,835.68 CNY. The
  latter must not be paired with consolidated revenue. The earlier derived
  gross margin 22.4321% used the consolidated cost; the replay's 22.3920%
  mixed scopes. Therefore blindly applying replay proposals would be wrong.
- 002125: consolidated balance sheet page 80 reports bonds payable
  450,138,560.42 CNY. Page 161 is explicitly denominated in CNY 10K and
  displays 45,013.86, equivalent to 450,138,600 after rounding. This is
  consistent rounded disclosure, not a new precise amount. Use the detailed
  statement precision for this fact, not the rounded liquidity note.
- 300014: page 86 reports short-term borrowings 706,335,000.01 CNY.
  Page 198 uses CNY 10K and displays 70,633.50, equivalent to
  706,335,000.00 after rounding. The 0.01 difference does not establish an
  issuer revision. Preserve precise statement value and annotate rounded
  corroboration instead of treating the note as another precise revision.

These findings resolve the interpretation of three known differences, not
all 26 overlapping collision groups. They have not yet been applied to
production facts. Promotion must encode statement scope and display precision
so that repeated extraction cannot reintroduce these alternatives as equally
eligible canonical facts. Never solve this by a global loose tolerance: scope
errors can fall within a numerical tolerance too.

## Remaining annual evidence queue

Read-only production detail query returned 35 records in 17 company-field
groups. Three groups are the previously reviewed cases. Remaining groups:

| Symbol | Field | Conflicting PDF pages |
| --- | --- | --- |
| 002588 | long_term_borrowings; short_term_borrowings | 96 / 207 |
| 600150 | net_income | 7 / 92 |
| 600233 | operating_cash_flow | 8 / 115 |
| 600323 | revenue | 7 / 25 |
| 600425 | operating_cash_flow | 6 / 62 |
| 600458 | operating_cash_flow | 6 / 90 |
| 600585 | operating_cash_flow | 9 / 98 |
| 600817 | operating_cash_flow | 5 / 72 |
| 600970 | operating_cash_flow | 6 / 108 |
| 601555 | cash | 103 / 195 / 203 |
| 601688 | cash | 313 / 347 |
| 601808 | operating_cash_flow | 7 / 86 |
| 688087 | revenue | 14 (failed) / 15 (verified) |

The queue is not an automatic correction list. In particular brokerage cash
must be checked for interest, client-fund and consolidation scope; differences
alone cannot establish the correct balance. Summary rounding is a hypothesis
until the page's disclosed unit and scope are inspected.
Reproducible current-and-annual census: `sql/audit_latest_input_conflicts.sql`.
