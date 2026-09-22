# Excel MVP Baseline - 2026-09-21

## Purpose

This is the auditable starting point for the Excel MVP delivery. It distinguishes
what is visible in the workbook from what has passed the research evidence gate.

## Canonical Workbook

- Workbook: `C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx`
- SHA-256: `A9F9BC91AF801F26E45B21CD3CEAA2840B67110F9FCFD2F8034FB5DAD6F298D5`
- Published backup and receipt: `runtime/workbook-backups/frontdoor-20260921T124307037961Z/`

## Stage A Snapshot

| Company | Research card | Evidence gate | Financial gate | Valuation gate | Trading state |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | Present | Pass | Pass | Conditional | Not eligible; same-date price bridge ready, confidence low |
| 000333 美的集团 | Present | Partial | Pending | Pending | Not eligible; business thesis gate passed |
| 601088 中国神华 | Present | Pass | Partial | Pending | Not eligible; cycle facts are not normalized valuation inputs |

The workbook view is therefore a research workbench, not an approved stock list.
No buy, sell, position, or order instruction is produced by this baseline.

## Verified Implementation State

- Three unified company research cards are rendered in `00_公司总览`.
- `00_首页Dashboard` contains a three-company worktable and internal navigation.
- Moutai has a conditional same-date valuation result with a verified 1,252.57 CNY
  price bridge. It is not a formal fair value or an investability conclusion.
- Invalid or intraday quote data is rejected by the scheduled after-close task and
  cannot rebuild the model or change the canonical workbook.
- The latest focused Stage A regression run recorded `16 passed`.

## Remaining Stage A Acceptance Work

- Stage A research-card acceptance is recorded in
  `docs/excel-mvp-stage-a-acceptance-20260921.md`. Stage B remains separately
  gated by each model's evidence, scope, validity and price-bridge checks.
