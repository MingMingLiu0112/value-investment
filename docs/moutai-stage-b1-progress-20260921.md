# Moutai Stage B1 Progress

Date: 2026-09-21

## Implemented

- Added the reusable `ValuationResult` contract and bounded one-variable
  reverse-valuation utility.
- Exported the pinned 2026-09-20 parent-equity residual-income / distribution
  model as `runtime/valuation-results/600519-current-equity-stage-b/evidence.json`.
- Preserved the model's conditional per-share scenarios: bear 403.33, base
  478.32, bull 571.13 CNY/share. These are not formal fair values.
- Preserved the 2026-09-14 bounded reverse valuation: its 1,277.96 CNY/share
  archived quote was above all registered -5% to +5% growth envelopes for 0,
  5 and 10 year franchise fade. This states only that at least one assumption
  would need to be stronger; it does not identify a unique market forecast.
- Synced this constrained output to the Moutai Excel MVP card and published it
  with a hash-guarded backup and successful WPS COM verification.

## Current Limitation

The 2026-09-21 two-source quote collection ran successfully but produced only
an `intraday_quote` observation (1252.50 CNY) outside the expected 2026-09-18
session. The quote gate rejected it. It is retained as evidence but is not used
as current price, margin of safety or reverse-valuation target.

Therefore B1 has **not** passed as an approved valuation result: confidence is
`低`, both margin fields remain null, and status is
`conditional_research_only`. The project must not advance to Midea B2 merely
because scenario arithmetic exists.

### Archived Replay Finding

The 2026-09-14 package does contain a verified same-session close of 1,277.96
CNY and a model frozen later that evening. However, that model pins policy hash
`ce8c7...`, while the current policy is `b3c20...`; the exact earlier policy is
not retained in Git or the evidence archive. The archived model therefore
cannot be re-executed or exported as a reproducible same-day valuation result.
This is intentionally fail-closed: visible archived arithmetic is not promoted
to a current price comparison, margin, formal fair value or trade action.

## Required Next Evidence

1. At a subsequent market close, collect and verify a two-source close.
2. Rebuild or explicitly time-bridge the model using only facts and capital
   actions available at that quote's session; do not relabel the 2026-09-20
   model as earlier market-session information.
3. Recompute margins and bounded reverse valuation using that matched pair.
4. Reassess confidence after documented evidence on advantage duration,
   distributable cash and discount-rate policy. A low-confidence result cannot
   be promoted to research attractiveness.

## Scheduled Evidence Control

`ValueInvestmentAgent-DailyUpdate` was migrated to run
`scripts/run_moutai_b1_after_close.ps1` at 17:05 on weekdays. It now collects
one two-source quote package, rejects invalid/intraday sessions without
rebuilding the model, and never writes the canonical WPS workbook. With an
accepted close it can rebuild the P1 evidence chain after the close and stage a
bounded reverse-valuation diagnostic plus a same-date `ValuationResult`; this
still has no order or trade effect. The export refuses to attach a diagnostic
whose model path, SHA-256 or valuation date differs from the current model.

The post-close refresh distinguishes B1 evidence staging from P1 simulation
admission. When capital, model and review artifacts are valid but a P1 gate
remains unmet, it returns `model_staged_simulation_blocked` with the blocking
gate IDs instead of failing the entire B1 chain. It still returns
`trade_approved: false` and `live_eligible: false`; only a fully admitted P1
chain returns `p1_simulation_admitted`.

The parent daily task parses that receipt and accepts only those two declared
states. Missing, malformed or unexpected child output fails the task rather
than allowing a diagnostic or Excel publication to proceed from an ambiguous
state.

### Excel Publication Readiness

The controlled MVP publication route was exercised without replacing the WPS
canonical workbook. Candidate
`runtime/workbook-backups/frontdoor-20260921T050830878883Z/ready.xlsx` passed
non-derived-sheet preservation, 6,236 internal-link checks and actual WPS
read-only navigation/formula verification. Its verification receipt is in the
same directory. A later B1 result with a valid same-date price may use this
candidate-first route; it must be re-verified against the then-current source
hash before atomic publication, and is never published from an ambiguous or
cross-date result.

`scripts/run_excel_mvp_publication.ps1` is the single publication entry point.
Its default mode builds and WPS-verifies a candidate only; `-Publish` is an
explicit opt-in that checks the canonical source hash again, creates a backup
and performs the atomic replacement. A default-mode end-to-end run on
2026-09-21 produced `frontdoor-20260921T051617347110Z/` with a passing WPS
receipt and did not replace the canonical workbook.

`ValueInvestmentAgent-MoutaiB1ExcelPublish` is registered for 17:30 on trading
weekdays, after the 17:05 B1 evidence task. Its date-bound gate accepts only a
current `conditional_research_only` result with low confidence, a same-date
reverse-valuation quote, non-null current price and both research margins.
It then invokes the candidate-first publisher with explicit `-Publish`. A
manual negative test against the current no-price artifact returned
`not_published`; it did not touch the workbook. The task never publishes an
order, a position, a formal fair value or trade approval.

The MVP dashboard was republished on 2026-09-21 after a separate WPS read-only
verification of `frontdoor-20260921T053427237287Z/ready.xlsx`. The published
hash was `567c2d973c41a7a6f824936558f2b9deb7618ac6f0dbdefdc087c6a6a6f48ea3`;
the pre-publication canonical backup is under that candidate directory. This
presentation-only publication maps internal research and evidence status codes
to Chinese display text. It did not alter non-derived sheets, formal-value
status, margin inputs, simulation admission or trade approval.

The published canonical workbook itself was then opened read-only in WPS and
passed the same 12 navigation checks plus the retained `=SUM(G10:G100)`
position-summary formula check. The post-publication WPS receipt is
`frontdoor-20260921T053427237287Z/published-wps-verification.json`.

The former task action used `run_server_excel_sync.ps1`, whose older workbook
sync path could have overwritten the newly published MVP pages. That path is no
longer scheduled. The duplicate 16:40 postclose policy task was disabled so a
single after-close task owns the next-cycle evidence chain.

Manual dry run on 2026-09-21 returned
`quote_rejected_no_model_rebuild` with `intraday_quote`, exit code zero and
`workbook_changed: false`. This proves the task's fail-closed branch, not a
successful close or valuation result.

### 2026-09-21 Pre-close Receipt

The pre-close CNINFO capital-event refresh was first exercised manually at
12:40 Shanghai time, then executed through the registered Windows scheduled
task at 12:52 Shanghai time. The scheduled invocation returned `0` and
produced
`runtime/company-research/600519-preclose-capital-receipt-20260921T045237Z/`
with `preclose_complete: true` and `trade_approved: false`. Its CNINFO index
and capital-refresh records have SHA-256 references. The repair retains the
Windows process environment for nested collection and pins the project Python
executable, preventing the former system-resolver failure. This receipt is
only a pre-close input; it does not replace the scheduled later refresh, valid
close, same-date model, reverse valuation, Excel publication or any trade
approval.
