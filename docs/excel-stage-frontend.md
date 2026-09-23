# Staged Excel Frontend

User-directed presentation change, 2026-09-23. This does not graduate M1,
authorize new decisions, or replace the domain/application research contracts.

## User Workflow

| Sheet | User question | Current content |
| --- | --- | --- |
| 00_投资工作台 | What can I review now? | Three archived research cases, readiness, navigation |
| 00_研究看板 | Which company should I inspect? | Filterable sample table, reasons, counterevidence, gaps |
| 00_研究逻辑卡 | What is the argument and what would disprove it? | Thesis, return drivers, evidence, breakers, scenarios, dates |
| 00_决策复核 | Why buy/add/hold/reduce/exit? | Explicit unconnected state; decision and entry requirements |
| 00_组合与股息 | Is my portfolio and income sustainable? | Unverified personal context, separate cash-income definitions |
| 00_跟踪与数据 | What changed and how current is it? | Snapshot dates, unconnected event scan, per-capability status |

Existing workbook sheets remain intact. Historical decision experiments are
linked as historical, not promoted to the new decision workflow. Existing
template capital and example positions are not taken as the user's assets.
Missing monitoring means unknown, not zero alerts. Missing valuation is never
shown as zero fair value. Research samples are not a High Attention ranking.

## Publication Boundary

The six sheets consume SHA-verified frozen runtime research/valuation snapshots.
Financial amounts are copied from those results, not recalculated or inferred by
the frontend. Snapshot hashes verify bytes, not the correctness of original
filings. Each page displays its publication date separately from source dates.

This is a staged presentation delivery, not automatic daily refresh. The existing
publisher preserves the new tabs when present but does not refresh their content.
M1 must subsequently connect the shared Application read model with one guarded
publisher. Do not append another set of company-specific worksheets/pipelines or
make these archived values the domain's source of truth. Retain the six separate
readiness axes and all fail-closed boundaries when replacing the snapshot input.

M3 decision cards need versioned research, valuation, price, entry and rationale.
M4 personal guidance needs confirmed private portfolio inputs and capacity.
M5 changes need actual completed scans, evidence and notification watermarks.
Do not replace their current unconnected states merely because pages exist.

## Safety And Verification

- Build six donor sheets with the bundled artifact-tool runtime.
- Append into a candidate using `scripts/stage_frontend_package.py`; do not
  reserialize the large retained evidence sheets.
- Compare all 30 original worksheet XML parts byte for byte, along with every
  retained package part except workbook metadata, relationships and styles.
- Verify cached formulas, internal hyperlinks, leading-zero symbols, native
  table filters, frozen navigation and missing-value states.
- Render every changed page; inspect the candidate in actual WPS before replacing
  the canonical workbook. A minimized/inaccessible window is not a passed check.
- Back up, require unchanged source SHA, and atomically replace only after checks.
  Never close the user's workbook forcibly or overwrite concurrent edits.
- `test_excel_report.py` covers old workbooks and preservation/order of new tabs
  under repeated frontdoor refresh. This does not prove investment validity.

The first delivery is intentionally append-only. Re-running the packager against
an already-upgraded workbook fails closed. Future refresh belongs to the shared
publisher, with explicit replacement of derived pages and preserved manual data.

## Build Runtime Limitation

The bundled Windows Node 24.14.0 renderer/exporter produced the files and all
requested renders, then exited with native code `-1073740791`. Do not report the
builder command as a clean pass or use it for unattended publishing. Independent
ZIP/XML validation and actual WPS read-only open/calculation checks are required
for this manually reviewed delivery. The future shared publisher must have a
clean process exit; this task does not authorize changing the bundled runtime.
