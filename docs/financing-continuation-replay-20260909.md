# Financing evidence replay, 2026-09-09

## Scope

Local research only. No production deployment, database promotion, Excel update,
trading signal approval or historical performance result.

Input: six official filings already archived under
`runtime/nearcomplete-financing-20260909/manifest.json`. The replay matched each
PDF SHA-256 to the manifest. This verifies local archive identity, not independent
financial scope approval.

Output: `runtime/nearcomplete-financing-20260909/continuation-sign-replay.json`.

## Changes and actual evidence

- `audit_local_financing_tables.py` accepts a heading-only prior page, immediately
  followed by the first ruled table with an explicit applicable marker, CNY unit
  and full financing header. Only an optional annual-report running header can
  precede these markers. Intervening prose, sections and unrelated first tables
  are rejected. Both physical pages, raw prefix, bounded layout and cells remain
  in the audit.
- `financing_cells.py` v3 preserves a minus sign wrapped onto a separate line
  within the same cell. A lone dash stays unknown; double signs and multiple
  complete amounts remain rejected. No adjacent-column number concatenation.
- 301376: physical pages 202-203. Closing bank borrowings including current
  maturities: CNY 1,335,291,619.88. Leases including current maturities:
  CNY 1,081,869,589.21. Restricted-share repurchase obligation: CNY 14,149,410.00.
  Detail closing amounts sum to the disclosed CNY 2,431,310,619.09 total.
  Lease noncash decrease remains -97,673,323.55. Blank opening/movement cells
  remain null, so complete balance/movement checks remain false.
- 002444: physical page 156. Closing short-term borrowings:
  CNY 1,280,065,456.36; leases including current maturities: CNY 318,102,200.09;
  disclosed total: CNY 1,598,167,656.45. Noncash decrease is -7,415,342.21,
  not positive. Opening and closing detail totals reconcile; complete movement
  reconciliation remains false because of blank cells.
- Parsed coverage increased from four to six of these six explicitly selected
  reports. The previous four results have identical total, rows and reconciliation
  flags. This is not a whole-market coverage statistic.

## Validation

18 focused financing-cell/continuation tests passed. Full suite: 1072 passed,
18 existing Backtrader datetime deprecation warnings. Actual six-PDF replay
completed, followed by explicit amount and prior-result equality assertions.

## Remaining decision gate

Every result retains `complete_debt_verified=false`. A financing-liability table
can include non-interest-bearing obligations and omit other financing forms.
Current maturities already included in row labels must not be added again.
Next work is reconciliation to balance-sheet notes, financing bills, factoring,
guarantees and other-payables scope before deriving an approved debt metric.
No missing amount was replaced by zero. Historical strategy validation remains
separate and incomplete.
