# Debt note research published to canonical workbook

Published 2026-09-09 08:47:54 +08:00 and independently reopened afterward.

Canonical file: `C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx`.
Receipt: `runtime/excel-sync-status.json`.
Payload generated: `2026-09-09T00:30:05.221917+00:00`.
Payload SHA-256: `7d2c309947e5de8444b788aef259a6584d0d1bacb2eae8e8a688df4e351e08bc`.

## User-facing result

- Existing `21_决策验证` column Z now contains debt-note research status for the
  46 audited companies. Others state that they are not in this research batch.
- Parsed-note entries link directly to their first research row in
  `18_指标证据`. No new worksheet: total remains 26, with 16 visible.
- Added 114 research records for 31 companies, using separate `research_` field
  IDs. Each retains original units/amounts, report period, original URL/hash,
  physical pages, parser, raw cells and audit lineage. They are display-only,
  not financial inputs and not append-only production audit facts.
- Blank closing amounts remain blank. For 600188, the original total is
  32,074,029 with unit `CNY thousand`, not 32,074,029,000 mislabeled as an
  original thousand-yuan amount. Normalized CNY remains in retained context.

## Snapshot distinction

The research audit was based on an earlier payload. The actual server export
downloaded during this sync is newer. All 114 displayed rows therefore say
historical research extraction, not verified financial indicators. Company
summaries with known amounts state that the current export needs a new
reconciliation; 002440/002452 explicitly state that original closing totals are
blank and were not filled with zero. No old match is presented as a current match.

Configuration `debt-research.json` pins the local audit's path and SHA-256.
`load_debt_research` verifies the audit and original file hashes and matches
original identity against the current export before displaying numeric evidence.
Missing/changed originals or unmatched source identity disable numeric display.
A changed audit hash aborts publication instead of accepting unpinned content.

## Actual checks

Full suite: 1147 passed, 18 existing Backtrader datetime warnings. Focused
workbook tests compare with/without research and prove unchanged score, valuation,
reminder and portfolio values, unchanged first 25 decision columns and no new tabs.

Canonical sync completed through the existing backup, generation, validation,
lock/change detection and atomic replacement flow. Publication validator checked
all research values, units, statuses, hashes and links, plus manual and historical
record preservation. Main pages have 738 companies; company research retains 744
including history. Annual numeric input cells: 4107. Specialized values: 196
across 65 companies. These are measured counts, not complete data coverage.

Independent reopen confirmed 114 research rows across 31 companies, exact links
for 600188/300888/002440/002452, original thousand-unit total, preserved blank
002440 total, 26 sheets and all 738 strategy statuses still historical backtest
incomplete. Only a readback shell quoting attempt failed initially; the corrected
readback succeeded without modifying the workbook.

Next: reconcile the pinned original-note research to the newer export and extend
remaining unsupported notes. Complete debt classification, genuine historical
backtests, approved valuation and portfolio guidance remain outstanding.

## Automatic current-export recheck follow-up

Published again at 2026-09-09 08:58:20 +08:00, using the same 08:30 export and
payload SHA-256 above. `load_debt_research` now re-executes the amount bridge
against current `points` and `annual_points` on every sync, after pinned audit,
original file and source-identity checks. It no longer reads the old audit's
matched-row flag to decide the current display, even when payload hashes agree.

The old PDF extraction audit is unchanged (SHA-256 remains
`8faa34504a86f4564d6deec7efd249deb19ef8fd111ba826178979bba5f22828`).
Each displayed research record retains `current_export_recheck` with method
version, current payload hash/date, point ID, source ID, secondary point/source
IDs, difference and deterministic recheck ID. The workbook sync receipt supplies
publication time; the original audit timestamp is not relabeled as a new parse.

Actual results: 29 company totals match current accepted export evidence;
2 original current totals are blank. The other 15 audited companies still lack
uniquely parsed notes. 114 display records remain research-only, now with 31
distinct company-level recheck IDs. Missing facts, conflicts, duplicate candidates
and rejected evidence produce distinct nonmatching states rather than falling
back to cached agreement. Component scope and full debt remain unapproved.

39 focused tests and 1152 full-suite tests passed, with 18 existing Backtrader
warnings. Original-workbook generation and validation completed, preserving
738-company main views, 744 historical/current research rows, manual records
and history. Independent read-only reopen verified the 29/2 company states,
114 research records, their current payload hashes/recheck IDs, 26 tabs and all
738 historical-backtest-incomplete statuses. No server code or trading-rule
change. This is automatic when the existing Excel sync runs; it does not create
a new timer or claim a newly verified unattended scheduled run.
