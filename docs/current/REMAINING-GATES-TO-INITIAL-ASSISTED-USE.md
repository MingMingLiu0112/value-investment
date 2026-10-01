# Remaining Gates to Initial Assisted Use

Reviewed: 2026-09-30. Goal: VALUE-INVESTMENT-TRADING-ASSISTANT-V1.
This is a handoff inventory, not a new roadmap or an acceptance receipt.
All outputs remain `action=no_order`. Synthetic inputs never graduate a real-data gate.

## Canonical frontend publication

CURRENT (supersedes the historical synthetic/staging entries below): the same
WORKBOOK_PATH now contains real-only conditional 600887 research and valuation
presentation. Latest SHA-256:
`d9865ad6d51864e1c6cdf89810cfd518daba0c19368593157888b4b48a5a4c6e`.
Publication receipt `runtime/publication-receipts/canonical-reviewed-research-20260930T165045Z-1447ce4a.json`;
actual post-publication WPS receipt `runtime/pending-bridge-publication-20261001/canonical-native-review/receipt.json`.
Published on October 1 China time through the supported reviewed-research CLI.
The retained observation remains September 30, not a fabricated October 1 quote.
The opportunity row includes scenario/date/confidence and current blockers;
the company card distinguishes dated original gate assessment from current admission.
Seven product pages and all 55 retained sheets passed preservation; original path
unchanged. Publication is no longer awaiting staging authorization. Final user
comprehension/acceptance and updated remote CI remain pending. This is not current
investment eligibility: one valuation step is CONDITIONAL, seven remain BLOCKED,
strict PIT NOT_PROVEN and no admitted current PriceBridge.

The following observations are HISTORY, not current blockers or instructions.

LATEST: user authorized the C-volume staging exception and closed WPS. The exact
full-preservation-verified synthetic integration was atomically published to
WORKBOOK_PATH; WPS read-only verification passed. There are now 62 sheets:
seven managed product pages plus 55 retained pages. Published SHA-256:
`53128c2775759297c1592400d131bd1b15017370f3513353a2cec69e98fefaf5`.
Current pointer metadata now declares simulation-only/unverified real quote
coverage and references the matching publication and WPS receipts. The opener,
navigation and CLI tests passed (9 tests). User comprehension and updated remote
CI remain pending. The publication/staging-pending observations below are historical.

Direct read-only canonical inspection on 2026-09-30 found 61 sheets, six visible
product sheets and 55 hidden retained sheets. The `决策过程` sheet is absent.
Current SHA-256: `99adbfbab0453ac42b05ffc804c8cd95b64162c9382feab3d8dbd8b05ae7983a`.
Hash before and after inspection matched. Therefore the seven-page preview is
not integrated into the actual user workbook. The 55 retained sheets include
manual transactions, portfolio, research and large evidence tables: publishing
a fresh seven-sheet workbook over this file would destroy retained content and
is not an acceptable shortcut. Publish only through preservation-aware integration.

Actual project-local integration rehearsal of that canonical source returned
`FAIL_CLOSED`: protected drawing/media/chart/worksheet relationship fingerprints
changed after openpyxl integration/save. Receipt:
`runtime/simulated-product-flow-20260930/canonical-integration-rehearsal.json`.
The canonical source hash remained unchanged. The rehearsal XLSX is explicitly
historical, synthetic and NOT publishable; it is not a current user entrypoint.
This adds a real publication blocker independent of the staging authorization:
even an authorized C-volume staging directory is insufficient until retained
OOXML relationships/objects are proven preserved. Diagnose the changed parts
before another publication attempt; do not weaken the fingerprint comparison.

Follow-up resolves that initial fingerprint failure: retained relationship keys
now follow sheet identity, not numeric worksheet part position, while bytes remain
hash-checked. A changed hyperlink is rejected by the new regression test. Full
snapshot/retention comparison of the original source and the saved integration
preview passed; receipt `canonical-integration-full-preservation.json` in the
same runtime directory, 55 retained sheets, canonical source unchanged. The
earlier FAIL_CLOSED receipt remains historical evidence. Staging authorization
and canonical publication are still pending; this rehearsal does not admit
the synthetic investment results or pass user acceptance.

- DAG_NODE: STAGE_1_CANONICAL_PUBLICATION
- CURRENT_STATUS: PARTIAL
- WHY_REQUIRED: The user must see the seven-page workbench in the existing WORKBOOK_PATH, not a competing preview.
- WHAT_IS_ALREADY_DONE: Unique canonical seven-page frontend published with real conditional research content; 55 retained sheets preserved, WPS verified, pointer/hash aligned. C-volume staging exception already authorized.
- EXACT_EXTERNAL_INPUT: User comprehension and final product acceptance; no further staging-path decision is required. Engineering CI passed for `dad6eb3109f7e8393fc7a8d2a11cdbfe441b8b0f` in GitHub run `36751736846`; this is not user acceptance.
- REOPEN_CONDITION: Complete user acceptance; subsequent code changes still need updated CI, and future publications require fresh source guard, preservation, backup, atomic replacement and WPS checks.
- WHAT_CAN_CONTINUE_IN_PARALLEL: Shared application projection of actual assessments, isolated tests and replay. Do not modify WORKBOOK_PATH or create another current workbook.

## Single-company evidence and price bridge

- DAG_NODE: STAGE_2_REAL_RESEARCH_CLOSURE
- CURRENT_STATUS: PARTIAL
- WHY_REQUIRED: Display and simulated results cannot establish a usable current investment conclusion.
- WHAT_IS_ALREADY_DONE: Existing Yili shared-model replay, nine-original hash verification, shared Application reader, typed research/valuation presentation and canonical integration. October 1 retained H1 review reconciles six existing atomic facts plus the cash bridge, with explicit dividend/FCFF scope limits (`docs/current/600887-financial-quality-review-20261001.md`). None establishes full financial approval, current ModelValidity/PriceBridge or strict PIT. Other cases retain explicit evidence stops.
- EXACT_EXTERNAL_INPUT: New official, hash-bound evidence meeting each registered case-specific reopen trigger; verified quote and complete applicable event coverage for the intended cutoff.
- REOPEN_CONDITION: Admitted facts/assumptions and applicable model produce a reproducible result; issuer identity, available_at, model validity and price basis checks pass. Missing data stays NOT_READY/WATCH.
- WHAT_CAN_CONTINUE_IN_PARALLEL: Consolidate reusable real-artifact projection, reconcile dated research with successor facts, test independent gate behavior and prepare legitimate replay inputs; no repeated search of stopped evidence scopes.

## Historical decision replay and three-company reuse

Current code/artifact scope check (2026-09-30):

- `scripts/run_three_company_research_replay.py` compares frozen shared-runner
  semantics; it is not a multi-session historical execution replay.
- `runtime/m3-historical-research-replay-20260924-v1/replay.json`
  (SHA-256 `2822dd786a40433ed03eac1e741a82a219cc9c76196b267e3a76290e53a141b9`)
  is symbol 600519, replay date 2024-06-21, with a retrospective 2025 rule
  extension and `relative_pe_research_only` valuation scope. It does not
  satisfy the selected 600887/000333 applicable-model requirement.
- A fresh read-only PIT v2 audit of that subject, without an independent input
  manifest, returns NOT_PROVEN and strict_pit_admissible=false. This invocation
  does not establish whether an admissible manifest exists elsewhere; a
  subject's own source manifest is not automatically independent PIT evidence.
- Do not retrofit September 2026 research/assumptions into historical dates or
  promote legacy PE experiment returns to current strategy validation. Preserve
  the frozen legacy module/artifacts. Real single-stock replay needs its own
  dated input and rule chain, then the existing independent verifier and
  execution-cost/constraint checks. Zero eligible decisions is valid but is
  not proof that buy/add/reduce/exit transitions were historically validated.

- DAG_NODE: STAGE_3_AND_4_VALIDATION
- CURRENT_STATUS: PARTIAL
- WHY_REQUIRED: Engineering replay alone does not prove point-in-time decisions or applicable models across economic structures.
- WHAT_IS_ALREADY_DONE: Shared infrastructure and historical tests exist; this review does not certify strict PIT, a complete historical trading replay or three usable valuation results.
- EXACT_EXTERNAL_INPUT: Historically available official inputs and market execution constraints, with publication cutoffs, dividends, suspensions, price limits, fees and slippage.
- REOPEN_CONDITION: Reproducible replay with no future leakage, explained state changes and reusable shared flow; model applicability established separately per company.
- WHAT_CAN_CONTINUE_IN_PARALLEL: Offline contracts and adversarial replay tests. Do not optimize thresholds to manufacture trades.

## Operational shadow observation

- DAG_NODE: STAGE_5_REAL_TRADING_SESSIONS
- CURRENT_STATUS: NOT_STARTED
- WHY_REQUIRED: Twenty consecutive real trading sessions cannot be substituted by synthetic days or repeated executions.
- WHAT_IS_ALREADY_DONE: Offline-chain engineering is retained, not operational acceptance.
- EXACT_EXTERNAL_INPUT: Scoped production scheduling authorization and a valid admitted daily input chain; actual passage of trading sessions.
- REOPEN_CONDITION: Save one auditable daily input/output/evidence snapshot per session and assess missed events, false alerts and state changes over the required window.
- WHAT_CAN_CONTINUE_IN_PARALLEL: Offline monitoring/recovery validation. Protect the server PTA project; no scheduler changes without authorization.

## Real restore and user acceptance

- DAG_NODE: REAL_RESTORE_AND_STAGE_6_USER_ACCEPTANCE
- CURRENT_STATUS: PARTIAL
- WHY_REQUIRED: Test fixtures and WPS open receipts cannot prove recoverability of actual assets or user comprehension.
- WHAT_IS_ALREADY_DONE: User-authorized October 1 local isolated restoration of the real September 30 PostgreSQL dump verified all fourteen table row counts/content hashes and twenty official PDF hashes. PostgreSQL 16 source restored into local PostgreSQL 18.6; same-major recovery remains unproved. Both temporary local clusters are stopped; no server restore container or production change. A real pre-publication workbook backup separately passed byte-hash, 55 protected-sheet checks and read-only WPS opening. That workbook predates the newest product explanation. Complete current workbook/runtime/config coverage, encrypted offsite recovery and user acceptance remain missing.
- ENCRYPTED_RECOVERY_FOLLOWUP: User authorized WPS project subfolder and separate local key generation. Actual encrypted package covers server dump/PDFs, current canonical workbook, existing tracked files and selected Yili research inputs. All 1,926 archive file hashes verified; decrypted-only database restore matched all fourteen table checks, current workbook bytes/navigation matched publication. Application restart and complete runtime/private configuration coverage remain unproved; no same-major or full-system RTO/RPO claim.
- EXACT_EXTERNAL_INPUT: Confirmation that the recovery key has an independently stored copy and WPS remotely synchronized the package; complete runtime/private configuration recovery arrangements; user review of the canonical workbook and explicit comprehension/acceptance confirmation. Private portfolio/IPS inputs are required before personalized position guidance. Isolated recovery, WPS target and separate key-generation authorization have been received; do not request them again.
- REOPEN_CONDITION: Restore with verified hashes/table checks and measured RTO/RPO; user traces a financial fact and explains a decision, risk blocker and state change. Final investment decisions remain human.
- WHAT_CAN_CONTINUE_IN_PARALLEL: Synthetic recovery tests and nonpersonalized product flow; missing private inputs remain explicitly unprovided.

## Completion boundary

INITIAL_ASSISTED_USE = NOT_REACHED.
TOTAL_GOAL_STATUS = IN_PROGRESS.
No gate above is waived by passing unit tests, displaying a valuation, or opening Excel.

## Current worktree validation follow-up

Latest rerun, 2026-09-30: all 144 workflow-selected offline modules completed:
1224 passed, 34 skipped, 3 deprecation warnings, zero failures.
Receipt: `.tmp/trading-assistant-offline-core-fixed-20260930.xml`.
The synthetic CLI and pinned-artifact tests are included in this run.
The earlier three architecture failures are resolved without raising growth
thresholds: new documents moved into `docs/current/`, pinned artifact loading
extracted into infrastructure, and the existing hardcoded quote writer registered
as a HIGH-risk DELETE_CANDIDATE with no current consumer. Registration does not
authorize running it or make its publication behavior acceptable.
This is uncommitted local-worktree validation, not remote GitHub CI, live PostgreSQL
integration, canonical publication, real PIT acceptance or investment effectiveness.
The current canonical workbook was observed with modification time 2026-09-30
17:49:26; a future publisher must take a fresh source hash and preservation baseline.

Latest synthetic preview UX verification: `runtime/simulated-product-flow-20260930/decision-blockers-preview.xlsx`,
SHA-256 `887bfadc8c655af9f45561876753dec014aa4319d711eb08fcdb461853500536`.
The seven-sheet readability audit found no clipped rows. Native WPS opened the
preview read-only, verified seven-sheet navigation and all 24 BLOCKED assessment
rows, exported the first company's eight-step decision page, and closed the preview
without saving; the workbook hash remained unchanged. The exported first-company
page was visually inspected and readable. This is not a full seven-page rendered
visual review or user acceptance. Receipts: `decision-blockers-readability.json`
and `decision-blockers-wps-receipt.json` in the same runtime directory.
Canonical touched: false. Real research and decision gates remain unpassed.

The workflow-selected local offline run on 2026-09-30 selected 142 modules:
1204 passed, 34 skipped, 3 failed. Receipt:
`.tmp/trading-assistant-offline-core-20260930.xml`.
Failures are architecture-boundary checks: unregistered existing
`scripts/current/update_canonical_quote_display.py`, docs root file count
177 versus 175, and growth of `scripts/build_m7_daily_workbench.py`.
These are worktree failures, not a new remote GitHub CI result. Do not raise
baselines or run the unregistered quote writer merely to pass checks.
The synthetic CLI tests were subsequently added to the workflow list; the
142-module receipt predates that addition. Their focused run passed, but the
new combined workflow and remote CI have not yet been validated.
