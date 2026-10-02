# CURRENT STATUS

## 2026-10-02 Unmocked Six-Node Daily Assembly Evidence

Completed an unmocked E2E test of the isolated producer, shared scheduled entry,
descriptor/review adapters, research/model/decision and existing portfolio
precondition gates, packet persistence and daily consumer. It uses pytest-local
synthetic scope/issuer/event/review inputs and a correctly dated synthetic
historical quote, not a current production quote. Real ledger/package bytes are
unchanged. All six nodes execute, decision is INSUFFICIENT_RESEARCH, daily
consumption is NOT_ADMITTED and zero real sessions are credited. This removes
the earlier uncertainty caused by mocking the shared research result in full-DAG
tests, without claiming actual company approval, strict PIT or real startup.

Reproduce: pytest tests/test_m6_start_criteria_matrix.py -k full_daily_dag.
Clearly labelled readable artifact:
`.tmp/unmocked-dag-final/test_full_daily_dag_runs_actua0/runtime/full-chain/synthetic-e2e-review.md`.
Related integration suites: 61 passed, 1 skipped. Offline Core evidence:
`.tmp/unmocked-dag-core.xml`: 1551 passed, 32 skipped, 38 warnings in 60.36
seconds; not all legacy tests or investment effectiveness. Inspection of the official bounded
scanner confirms retrieval-time capture is explicitly not full-day completeness;
no new scan or speculative completeness promotion was performed.
No business feature, valuation threshold, Excel, server/PTA, scheduler, database
or signed admission was changed. Actual session inputs and authorized dispatch
remain external/unverified, total Goal remains in progress, action=no_order.

## 2026-10-02 Independent Missing-Portfolio Gate Execution

The daily producer no longer labels absent private portfolio inputs as an
upstream research execution skip. It actually constructs the existing
MinimalPortfolioPreconditions.missing(), evaluates allows_positive_review(),
and seals the negative result: BLOCKED_PRIVATE_INPUT, provided=false,
personal_capacity_confirmed=false, portfolio_input_missing, position_guidance=null.
No portfolio quantity, account risk assessment or private confirmation is inferred.
The existing simulated risk path is unchanged and remains simulation-only.

This closes an independent node execution gap, not investment/Shadow admission.
The daily audit parses this typed missing-input result and rejects claimed capacity,
position or blocker contradictions. Synthetic full-DAG tests can now execute all
nodes without inventing a personal portfolio; the operational consumer still
requires its unchanged official inputs, actual execution and signed M6 admission.
Self-authored or synthetic runs remain zero real-session credit.

Actual source-bound run: `runtime/shadow-private-input-gate-20261002/input.json`,
SHA256 `e1d51312b5fabbd25a79b910eea4f3753ceae33807d42def34bd7319aead9075`.
Research remains stopped, quote absent, event coverage incomplete; only research,
portfolio preconditions and product nodes ran. DAG incomplete, NOT_ADMITTED,
zero verified real sessions, no_order. This is not a completed trading session.
Related tests: 55 passed, including a rehashed packet attempting false capacity
which still fails the semantic audit. Full Core evidence:
`.tmp/portfolio-refusal-core.xml`: 1550 passed, 32 skipped, 38 warnings in
61.80 seconds; not all legacy tests or investment-effectiveness proof.
Canonical workbook/server/PTA/
database/scheduler unchanged; full Goal remains in progress.

## 2026-10-02 Formal Preflight Consumes Explicit Daily Manifest

The existing `scripts/audit_m6_preflight.py` now accepts paired `--daily-input`
and `--daily-input-sha256`, with optional paired `--daily-operational-inputs`
and `--daily-operational-inputs-sha256`. An Operations adapter consumes the
existing daily manifest/operational proof contract and then calls the unchanged
legacy M6 readiness builder. The receipt embeds daily consumption separately;
incomplete daily input adds its blockers and never grants legacy readiness.
No daily arguments preserves existing readiness behavior; it is not proof that
current daily inputs were checked. Both gates retain their original requirements.

Actual read-only CLI execution consumed the existing source-follow-up/simulated
risk attempt with manifest SHA256
`d1b5cbb9038d3201920f3b4c6c1525e017ff04eba42cd51def0bc46992602d07`:
`engineering_status=PARTIAL`, `operational_acceptance_status=NOT_STARTED`,
`daily_consumer_status=NOT_ADMITTED`, no_order, zero newly admitted sessions.
Receipt: `runtime/m6-operational-preflight-20261002T074359Z/receipt.json`, SHA256
`0f8e86910325749cad53ed35b86d88176f31cc8e1fa62ae9c07f468d32178610`.
This run supplied no restore/authorization/calendar evidence, so its legacy
missing-input messages do not revoke prior independently verified backup or
restore evidence; no production scope was inferred from that historical work.

Reproduce:
`py -3 scripts/audit_m6_preflight.py --daily-input runtime/shadow-existing-risk-dag-20261002/input.json --daily-input-sha256 d1b5cbb9038d3201920f3b4c6c1525e017ff04eba42cd51def0bc46992602d07`.
Tests exercise the real CLI adapter and real daily audit/consumer with only the
legacy readiness builder stubbed, confirming absence of proof remains NOT_ADMITTED,
original blockers survive and artifact drift prevents receipt publication.
Related preflight/daily/readiness tests: 48 passed. Offline Core evidence:
`.tmp/daily-preflight-core.xml`: 1550 passed, 32 skipped, 38 warnings in
69.76 seconds; this selected offline suite is not investment-effectiveness proof.
No scheduler/server/PTA/DB/Excel
mutation; only isolated local readiness artifacts were written. Full Goal remains
in progress; production adoption and actual sessions require their existing gates.

## 2026-10-02 Reviewed Package Through Actual Shared Entry

The scoped scheduling gate, real M1 descriptor builder, typed review attachment,
registered research service, calculation, serialization and readable projection
now have an unmocked shared-entry integration case. It uses only a pytest-local
copy with a synthetic empty stop ledger and explicit synthetic fresh scope;
real Evidence Stops and research receipts are unchanged. It supplies a rejected
review bound to the computed valuation and exact canonical case/facts/assumptions.
The rejection reaches output and the test-readable card, not a buy/add signal.

This exposed and repaired two actual gaps: detailed resolved review blockers
were absent from aggregate research output, and receipt digests were recomputed
after execution rather than pinned to consumed package/ledger bytes. The entry
now verifies package, ledger and explicit inputs before consumption and after
calculation, before publishing; emits the consumed descriptor digest; and records
the original verified digests. Three integration branches mutate package,
ledger or review packet during the real service call and verify publication is
refused. Financial formulas, valuation assumptions and gate thresholds unchanged.

Reproduction: pytest tests/test_evidence_stop_schedule.py. Related integration
suites passed 72 tests with 1 skip. Readable synthetic output:
`.tmp/shared-entry-final/test_reviewed_package_runs_act0/synthetic-entry-card.md`.
The output prominently states SYNTHETIC TEST ONLY; copied historical numbers,
synthetic issuer metadata and review are not actual-company research approval,
strict PIT, strategy evidence or a current market snapshot.
Full offline Core evidence: `.tmp/shared-entry-core.xml`: 1546 passed, 32 skipped,
38 warnings in 58.23 seconds. Not all legacy tests or investment effectiveness.

Remaining production dependencies are unchanged: acquired current quote/event
coverage, actual research/event reviews or valid refusal evidence under existing
M6 rules, production authorization/signed intake and the twenty real sessions.
No production scheduler, Excel, PostgreSQL or PTA change. Goal in progress,
Shadow start readiness PARTIAL, zero newly counted real sessions, action=no_order.

## 2026-10-02 Materiality Attachment Through Shared Research Service

Code inspection found that the explicit review adapter removed the original
EventScanResult after checking only its digest, allowing incomplete coverage
or omitted announcements to disappear from ModelValidity inputs. Attachment now
requires a complete typed acquired scan, exact scan window and issuer, review
after acquisition, every acquired announcement, matching publication times and
source identity/hash. Existing scan blockers and evidence survive the conversion
to the mutually-exclusive materiality-review input. No review is inferred.

An integration fixture executes the real ResearchApplicationService, registered
residual-income model, ModelValidity, PriceBridge, serialization and renderer:
requires-recalculation preserves conditional valuation but yields STALE /
STALE_MODEL and NOT_READY. No human approval was provided; pre-decision remains
absent, not admitted. The fixture descriptor/issuer/facts are synthetic; this is
not an actual-company approval or evidence of strict PIT/Shadow admission.
Reproduce with pytest tests/test_event_materiality.py; the readable test artifact
is `.tmp/review-service-target5/test_attached_materiality_reac0/synthetic-review-card.md`.
Targeted materiality/approval/daily suites: 45 passed. Full offline Core receipt:
`.tmp/review-service-core.xml`: 1542 passed, 32 skipped, 38 warnings in
58.87 seconds. This selected offline suite does not establish all legacy tests
or investment effectiveness.

Current real-company evidence stops and official settlement follow-up remain
unchanged. No user workbook, production scheduler, database, PTA service or
private input was modified. Total Goal remains in progress, Shadow readiness
PARTIAL and action=no_order. Direct descriptor-to-review-to-shared-entry tests
and production consumer wiring remain separate from this service-level evidence.

## 2026-10-02 Isolated DAG Completion and Output Observation Repair

The isolated daily producer now derives `dag_execution_complete` from exact
execution of the existing six-node sequence, rather than a constant false flag.
Missing research/model/decision/portfolio execution still records false; this
does not permit a refused research run to count as a completed session. Consumer
audit requires the flag to be explicitly true, not absent or false.
Output `generated_at` is captured after decision and risk calculations, before
hash-bound persistence. Original source observation and availability are unchanged.

Four synthetic integration cases cover full execution and missing PriceBridge,
decision or portfolio nodes. Shared research is mocked explicitly; the existing
typed decision parser, decision engine, simulated risk engine, artifact writer,
consumer audit and readable renderer run. These are not proof of real approved
research or a production session. The target suite passed 29 tests.
Full offline Core evidence is `.tmp/shadow-completion-core.xml`: 1541 passed,
32 skipped and 38 warnings (57.51 seconds). This is the selected offline Core
suite, not proof that all legacy tests pass or investment logic is validated.
Server/PTA, canonical workbook, scheduler,
signatures, private portfolio and the 20-session requirement are unchanged.
Production readiness remains PARTIAL, verified real sessions remain zero and
`action=no_order` remains permanent.

## 2026-10-01 Canonical Entry Reconciliation After Shared-Session Integration

Default entry is again `WORKBOOK_PATH` / `CANONICAL_WORKBOOK`. Runtime v3 and
its visual/source receipts remain historical evidence, accessible only with
explicit `--historical-preview PATH --preview-sha256 SHA256`. Earlier sections
claiming PRODUCT_UX_RUNTIME as the current entry are superseded, not deleted.
Actual resolver verified canonical SHA256
`74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`;
no workbook bytes were written and no WPS launch was performed in this run.
Six test-local pointer cases passed without reading the user's WPS file.
Final user/production admission remains NOT_PASSED / NOT_REACHED; action=no_order.
These are uncommitted shared-worktree changes, not remote CI acceptance.

## 2026-10-01 Reviewed-Research Publication Boundary Hardened

- The canonical-reviewed-research publisher now requires the candidate source-binding receipt, rehashes every declared local source, transits through the historical closure and execution-replay nested source sets, makes visual review mandatory, and rejects any proof that elevates `strict_pit` or `current_price_bridge`.
- Preserved-sheet OOXML protection now includes reachable `xl/tables/` and `xl/comments/` parts, ignores external relationships, and fails closed on missing internal relationship targets. Negative tests cover missing visual review, missing/drifted source receipts, boundary elevation, nested closure drift, missing internal OOXML targets, and table/comment preservation.
- Fresh verification of the existing 62-sheet preview passed with 52 unique bound sources, source-set SHA-256 `1d626787c3feeb416f5f9573fa8d85e61a3e5e2f83c28f1a358556479cfe9aea`, and receipt `runtime/publication-receipts/canonical-reviewed-research-verification-20261001-hardened.json` (SHA-256 `cb951cf402ba10039a2eb9f6777be66826cc625c7e91cdf0096095689759ad63`).
- This is verification-only. `canonical_written=false`; canonical SHA remains `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`. No production publication, scheduler, database or PTA change occurred. `action=no_order`.

## 2026-10-01 M7 Product UX v3 User-Visible Trial Reconfirmed

- Current pointer is restored to the five-page product trial `runtime/m7-product-ux-candidate-v3-20261001.xlsx` (`7437a155c41d73882d9b5a1c751f690c9d9bd62e6ef484188d04a711793ca769`). `python scripts/open_current_trial_workbook.py --open` was actually launched and WPS opened the workbook read-only; this is not legacy v16 and not the canonical workbook.
- Fresh WPS native export and visual review receipts are `runtime/m7-product-ux-candidate-v3-20261001-delivery-wps.json` and `runtime/m7-product-ux-candidate-v3-20261001-delivery-visual.json`. All 274 string cells checked across the five primary pages plus the supporting decision page were present in WPS PDF output; 70 evidence hyperlinks, `B4` freeze panes, six-column width and no internal user-page tokens were verified.
- The review found no P0/P1 reading defect requiring a workbook edit, so no v4 was created. The 62-sheet canonical integration preview remains historical audit evidence only. `canonical_written=false`; canonical SHA remains `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`.
- `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`, M6 operational status remains `NOT_STARTED`, and `action=no_order`.

## 2026-10-01 真实输入历史执行回放接入共享产品数据包

- 工程交付：`scripts/current/build_historical_execution_replay.py` 产出的真实输入历史执行回放（600519 / upper-30pct，2674 个交易日、4 次成交、期末 NAV 1076905.53 元、研究性总回报 7.6906%）已通过 `scripts/current/build_product_workbench_candidate.py --historical-execution-replay` 接入共享产品数据包，只出现在次级 `06_系统与审计` 的“历史执行回放审计（非当前建议）”区，不进入今日/机会/公司/组合/事件五个产品页。
- 可复现产物：`runtime/historical-replay-shared-product-20261001/product-workbench.xlsx`（SHA-256 `d3c57a622ea2ce2438021e99f336ffe472908a1b26177c02b77b03a761029d91`）、manifest `e31c3b7cc9f7de6a392091ce3a19419deaf624c05a198f64943d7425b3a9249b`（counts 含 `historical_execution_replays=1`、`historical_reviews=1`、`evidence_records=33`）、来源收据 `product-workbench.source-bindings.json`（`b9e3a45fdcf7cf927964996b7a830ca282e9e6228d194cb5300f5133ae58c972`，其 `output_manifest_sha256`/`workbook_sha256` 与上述两个文件一致）、同源 JSON `read-model.json`（`2c28ee81fde56c2ff9a02ae638ae6c15b6a8b2e50b51498051cded671275bc51`）与可读报告 `company-card.md`（`203137b35c2f38075e9a2127b9f5201c0913b76bff1826f3231dab39bf91c18c`）。
- WPS Office 只读打开该候选并逐页导出七个工作表，用户页内部词元扫描全部通过，导出前后工作簿 hash 不变：`runtime/historical-replay-shared-product-20261001/product-workbench-wps-open-receipt.json`（`adfa7509400110a03cedf5c758768670578189fbfcc6cbb61c5860df2c4f1e4d`）。Canonical 工作簿未被替换，仍为 `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`。
- 本轮修正两处会影响后续返工的工程债：脚本清单按生成器重建（644 条、`current_entrypoint_count=43`）并把此前被手工改成 45 的断言恢复为生成值，同时把回放 CLI 登记进 `config/current-cli-entrypoints-v2.json` 工程层（engineering 41 / total 60）；`tests/test_existing_valuation.py` 中仍指向旧十列机会卡的 `D5/F5/J5` 断言改为按标签定位当前两列卡片的取值单元格，并保留“用户页不出现 BLOCKED”的边界。
- 验证范围：完整离线 Core Gates（workflow 内 169 个模块）`1433 passed, 39 skipped`，证据 `.tmp/offline-core-replay-20261001.xml`；`tests/test_historical_execution_replay.py` 新增投影/拒绝用例覆盖 action、schema、符号、来源角色、对照计数、未来生成时间与 6 个准入标志。测试通过只证明共享路径与失败关闭行为，不证明历史可成交或策略有效。
- 边界：`engineering_delivery=DELIVERED`、`current_research_admission=NOT_READY`、`strict_pit_admitted=false`、`historical_execution_validated=false`、`investment_rule_validated=false`、`performance_claim_allowed=false`、`validation_classification=NOT_PIT_SAFE`、`validation_admission_status=NOT_ADMITTED`、`action=no_order`。

## 2026-10-01 M7 Product UX User-Visible Trial Delivery

- Final read-only product trial: `runtime/m7-product-ux-candidate-v3-20261001.xlsx`, SHA-256 `7437a155c41d73882d9b5a1c751f690c9d9bd62e6ef484188d04a711793ca769`. The v2 candidate remains historical provenance and is not the current entry.
- WPS Office actually opened the v3 workbook read-only, exported every sheet natively, and preserved the workbook hash. Receipt: `runtime/m7-product-ux-candidate-v3-20261001-wps-open-receipt.json`. Visual/layout receipt: `runtime/m7-product-ux-candidate-v3-20261001-visual-review.json`. Readability receipt: `runtime/m7-product-ux-candidate-v3-20261001-readability.json`. The earlier receipt pair is preserved provenance; the pointer now names `runtime/m7-product-ux-candidate-v3-20261001-wps-delivery-recheck.json` and `runtime/m7-product-ux-candidate-v3-20261001-visual-review-delivery.json`.
- Independent delivery recheck: WPS reopened the same hash-bound workbook read-only, exported all seven sheets, and a per-cell comparison confirmed every workbook cell string appears in full in the native PDF export, so no line is clipped. Frozen `B4` panes, 70 evidence hyperlinks, empty formula-error set and a clean internal-token scan on the six user pages all held; `python scripts/open_current_trial_workbook.py --open` verified the pointer and opened the five-page Product UX workbench rather than legacy v16 or the canonical workbook. 33 focused pointer/workbook tests passed. Residual P2 (non-blocking): the `03_公司` appendix still prints three hash-suffixed labels such as `财报原件入口（600887-disclosed-rows-6b9d62552ff0）`; it wraps without clipping, so it is polish for the next M7 UX pass rather than a reading blocker.
- User pages now hide internal engineering tokens; the opportunity card header is visible; the five primary pages are `01_今日`, `02_机会`, `03_公司`, `04_我的组合`, `05_事件`; `决策过程` remains supporting product explanation and `06_系统与审计` remains secondary.
- `config/current-trial-workbook.json` now points to the Product UX runtime trial. Running `python scripts/open_current_trial_workbook.py --open` actually opened `m7-product-ux-candidate-v3-20261001.xlsx` in WPS, not legacy v16 and not the canonical workbook.
- The canonical WPS workbook was not replaced or modified. Canonical SHA-256 remains `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`.
- Status: `M7_PRODUCT_UX = USER_VISIBLE_TRIAL_READY`; `CURRENT_TRIAL_POINTER = PRODUCT_UX`; `M7_FINAL_USER_ACCEPTANCE = NOT_PASSED`; `INITIAL_ASSISTED_USE = NOT_REACHED`; `action = no_order`.

## 2026-10-01 600519 Historical Closure Engineering Delivery

- `scripts/current/build_historical_company_closure.py` now reproduces one readable 600519 historical research closure from hash-pinned M3 replay, no-decision execution clock and nine range-diagnostic scenarios. Report: `runtime/historical-company-closure-600519-20261001/company-historical-closure.md`, file SHA-256 `13f4ecd399bc6521a941417132fe94b04676f6101bf78de45a0d5b0080be2092`.
- A fresh no-overwrite run against the pinned recipe produced the same result after excluding only `generated_at`; the Markdown was byte-identical. The readable report distinguishes the no-decision execution clock from retrospective range diagnostics and translates blockers into Chinese while the JSON retains raw blocker codes.
- This is engineering delivery only: `current_research_admission=NOT_READY`, `strict_pit_admitted=false`, `historical_execution_validated=false`, `performance_claim_allowed=false`, `action=no_order`.

## 2026-10-01 Shared Historical Integration And Conditional Expectations

- Engineering delivery: shared cutoff CLI now supports original event integrity/recovery, page-level original-source review, explicitly synthetic bounded virtual execution and conditional price-implied terminal ROE. These reuse existing quote, validity, bridge, PDF and account engines; no copied company pipeline or investment threshold changes.
- Original index recovery: sealed hash f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93c9f383349388bbc2d815ceea was found in the earlier 600887 scan archive. The mismatched old path and failed audit remain preserved. Recovery is content verification, not research approval.
- Actual readable evidence: runtime/historical-bridge-recovery-reviewed-20261001/, runtime/historical-event-source-review-20261001/ (19 original announcements), runtime/shared-execution-scenario-20261001/ (synthetic only), runtime/shared-reverse-equity-expectations-20261001/ (historical price with retrospective pinned assumptions). No historical decision is backdated to these later-created results.
- Conditional inverse reconciles the September 22 price CNY26.77 with the existing forward model by varying terminal ROE only. Implied ROE approximately 23.7%-28.9% is not a forecast, proof of mispricing or sell recommendation. Pre-model event incorporation, forecast justification, real decision/execution inputs and strict PIT remain unapproved.
- Offline Core Gates: 1349 passed / 32 skipped / 28 warnings; evidence .tmp/reverse-core-20261001.xml. Whole-repository test invocation earlier was interrupted after prolonged no-output and failures; whole-repository success is not established. Remote CI for this new inverse change is not yet verified.
- Canonical SHA-256 rechecked: 74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582; no workbook publication in this work package, no server/database/scheduler changes. Existing user-reading/key-custody/WPS-visibility confirmations are inherited.
- CURRENT_RESEARCH_ADMISSION=NOT_READY; STRICT_PIT=NOT_PROVEN; HISTORICAL_EXECUTION_VALIDATED=false; INITIAL_ASSISTED_USE=NOT_REACHED; TOTAL_GOAL_STATUS=IN_PROGRESS; action=no_order.

## 2026-10-01 User Reviewed Canonical Workbook And Authorized Continuation

- User explicitly reports reviewing the WPS project workbook modified around 01:00 and authorizes continuation. USER_WORKBOOK_REVIEW=CONFIRMED; CONTINUATION=AUTHORIZED. Lack of initial workbook reading is no longer a blocker; do not request that same confirmation again.
- Current canonical file observed at 2026-10-01 01:46:15 local host timestamp; SHA-256 719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9 matches the verified publication. No workbook write performed. Timestamp alone is not a new publication or new research evidence.
- This confirmation does not attest all final acceptance tasks, fact tracing, state-change review, strict PIT, current model validity or investment readiness. Continue the authorized single-stock research closure without weakening evidence stops. INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order.

## 2026-10-01 User Confirmed Independent Key Custody And Remote WPS Visibility

- Direct user confirmation: recovery key independently backed up and encrypted package visible remotely in WPS. KEY_INDEPENDENT_COPY=USER_CONFIRMED; WPS_REMOTE_VISIBILITY=USER_CONFIRMED. These two pending human confirmations are closed; do not ask for them again without a new material change.
- Confirmation does not prove an independently downloaded remote package hash, restored secondary key usability, complete runtime/config reconstruction, full-system RTO/RPO, Excel comprehension or investment readiness. Original machine receipts remain unchanged and describe their observation-time scope. FULL_SYSTEM_REAL_RESTORE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order.

## 2026-10-01 Restored Research Application Command Verified

- Ran the actual backed-up `scripts/current/run_company_research.py` from the decrypted `source/code` root, using its backed-up existing-original manifest and primary-bound arithmetic input. No current repository source import, new research request, server access or workbook publication. Existing evidence hashes and shared arithmetic checks passed; the command exited successfully.
- Output `.tmp/actual-encrypted-backup-20261001-verified/source/code/runtime/backup-recovery-application-20261001/result.json`, SHA-256 `b0b27d43ef327945230c65382562ee823f89f408f85eb19adba51d62c992af87`. Retains 600887 Bear/Base/Bull CNY 8.05/11.02/13.13, `EXISTING_RESEARCH_ONLY`, `suggested_state=NOT_READY`, `model_validity=NOT_ESTABLISHED`, pending PriceBridge with no current price and `action=no_order`.
- This proves the selected recovered research read command works using local installed Python dependencies, not a fully reconstructed runtime, scheduled production app, personalized portfolio, same-major PostgreSQL environment or operational investment readiness. Full-system RTO/RPO and final acceptance remain unproved. The run-created result is outside the immutable original package; archived files were not overwritten.

## 2026-10-01 Actual Decrypted Package Database And Current Workbook Recovery

- Used only files extracted from the actual encrypted package: no SSH, network fallback, original-dump fallback or production access. Restored its database into another fresh local SCRAM-authenticated loopback cluster and compared all fourteen public table counts/content hashes with the decrypted manifest. Database creation/restore/validation took about 33.527 seconds; cluster stopped afterward. Receipt `runtime/decrypted-package-database-restore-20261001/receipt.json`, SHA-256 `3d3a0e0d791b9c4d3006a9e24ad7ea89e09d62fe3fc69e12bc85f02aaef1cd9f`.
- Decrypted current workbook byte hash equals canonical publication `719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9`; read-only parser confirms exactly seven visible user pages and 55 retained sheets. No canonical replacement or native WPS visual verification was performed. Chain receipt `runtime/decrypted-package-database-restore-20261001/chain-verification.json`, SHA-256 `f3fffc376034416091aca64dba4988f4b0a460a884704ed172abafbf1903c57b` clarifies actual decrypted-only scope; generic component receipt limitations are not the current combined-package inventory.
- ENCRYPTED_PACKAGE_DATABASE_COMPONENT_RECOVERY=PASS; CURRENT_WORKBOOK_BYTE_RECOVERY=PASS. Application restart/configuration reconstruction, same-major database recovery, remote WPS sync and independent key-copy custody are not proven. FULL_SYSTEM_REAL_RESTORE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order.

## 2026-10-01 Actual Encrypted Backup Published To Authorized WPS Folder

- User authorized a dedicated WPS project backup directory and generation of a separately stored recovery key. Created an AES-256-GCM package at the authorized `价投跟踪/加密备份/value-investment-20261001.viabackup` with a separate SHA-256 sidecar. The durable key is outside Git and WPS in a restricted local recovery-key directory; its contents were never printed. An independently stored key copy is not yet confirmed.
- Decrypted the actual package into a restricted, isolated project `.tmp` directory and verified all 1,926 archived file sizes/hashes. The cloud-sync-folder copy matches the local encrypted package hash. Receipt `runtime/actual-encrypted-backup-20261001/receipt.json`, SHA-256 `624eee2ead34155f075ac915a4c86a10aca3c15020c99db5103a8042d5762c85`. Remote WPS upload/sync was not independently verified.
- Coverage includes the real server dump and twenty PDFs, current canonical workbook, existing tracked files and explicitly selected Yili research/publication evidence. Unselected runtime, private portfolio data and live environment/server secrets are excluded. This is actual encryption/decryption/hash verification, not a database/application restart from the decrypted package, complete configuration reconstruction or full-system RTO/RPO proof. FULL_SYSTEM_REAL_RESTORE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order.

## 2026-10-01 Authorized Real Database Backup Restored Locally

- User explicitly authorized isolated recovery and a local server-backup folder. Created `backups/server-backup/3d660af6-9ca5-4948-b87d-7659c8e234ee/` inside the canonical code workspace, outside WPS cloud sync. All 22 files (dump, manifest and twenty official PDFs; 103,432,792 bytes) are ignored by Git and the backup directory has restrictive inherited access for the current user, SYSTEM and Administrators. This is a local plaintext recovery copy, not an encrypted offsite backup.
- Restored the actual PostgreSQL 16 dump using the existing local PostgreSQL 18.6 binaries into a fresh SCRAM-authenticated, loopback-only cluster under `.tmp/real-server-database-restore-20261001-v2/`. Single-job restore and the existing bounded-memory `table_checks`/`compare_checks` verified all fourteen public tables, primary-key requirements, row counts and content hashes against the real manifest. All twenty downloaded evidence hashes also match. No Docker Desktop or server restore container was started.
- Receipt `runtime/real-server-database-restore-20261001/receipt.json`, SHA-256 `73412aba3cd7432efe10b65c295ebdaeb8643c6e06467b2727d870d11f43a376`. Successful retry database creation, restore and table validation took about 35.179 seconds. Its download timing is a cached-file verification step, not the original transfer time. The initial Windows startup output-pipe timeout and its log remain separately retained; that cluster was explicitly stopped before retry. Both local clusters are stopped. These timings are not full-system RTO/RPO.
- Read-only server follow-up shows only the existing value-investment PostgreSQL container and the running `web_app_integrated.py` process. No production database, scheduler, service or PTA changes occurred. Server available memory was approximately 779 MiB before and 786 MiB afterward; recovery computation was moved entirely to the local machine to avoid competing for server RAM.
- DATABASE_COMPONENT_LOGICAL_RESTORE=PASS; SAME_MAJOR_RESTORE=NOT_PROVEN. The current canonical Excel, local research runtime and configuration are not covered by this server manifest; encrypted offsite recovery and complete application restart remain unverified. FULL_SYSTEM_REAL_RESTORE=NOT_PASSED, INITIAL_ASSISTED_USE=NOT_REACHED, action=no_order. Latest prior code/document CI run `36790776567` for `c17e749` passed both jobs; this new evidence does not approve investment or user gates.

## 2026-10-01 Actual Workbook Component Restored In Isolation

- Restored the real pre-publication canonical backup into ignored `.tmp/real-workbook-restore-20261001/restored.xlsx`, never into WORKBOOK_PATH. Restored bytes match backup SHA-256 `d9865ad6d51864e1c6cdf89810cfd518daba0c19368593157888b4b48a5a4c6e`; all 55 non-product sheets and their protected content/object checks match the current canonical workbook. Canonical hash remains `719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9`.
- Component receipt `runtime/real-workbook-restore-20261001/receipt.json`, SHA-256 `9d78b16995f7b05fe72e88a114c339223c781f3eb164785ef0bbd18731db79a7`. Measured byte-copy/hash step about 0.029 seconds; restore plus preservation validation about 35.819 seconds. These are component timings, not full-system RTO/RPO.
- Subsequently opened that isolated restored workbook read-only in actual WPS and exported all seven visible pages without changing its hash: `runtime/real-workbook-restore-20261001/native-review/receipt.json`. This is a later verification; the earlier immutable component receipt's no-WPS limitation describes its creation-time scope. User visual/comprehension acceptance remains separate.
- The source backup predates the newest financial explanation; current product-sheet recovery is NOT_PROVEN. No actual database/config/runtime restore or offsite recovery occurred. FULL_SYSTEM_REAL_RESTORE=NOT_PASSED, INITIAL_ASSISTED_USE=NOT_REACHED, action=no_order. Temporary restored copy is not a current user entry and remains outside Git. Server restore authorization question remains pending.

## 2026-10-01 Real Server Backup Inventory Verified Read Only

- SSH access succeeded in batch/key mode. Located the September 30 backup `3d660af6-9ca5-4948-b87d-7659c8e234ee` under the existing server backup root. Dump SHA-256 `548c04fa803c8e94b0f63f501431554b4d4dde516a7813a363ceeb292dceff59` and manifest SHA-256 `58836554b088293e09c1d55b2752a1e7cc176fb2188c6c0ee01c158fcb253f04` were independently read and matched. All twenty declared official PDF hashes also matched.
- Immutable local inventory: `runtime/server-backup-readonly-20261001/verified-evidence-inventory.json`, SHA-256 `98dd6109459393d6f8d92dc5d4a27a575d153eaf68d62b8a6dc48ba66ca157e6`. The manifest declares fourteen table checks, but none was verified against a restored database. Evidence paths refer to shared current files, not independent immutable backup objects. The server backup does not inventory the current canonical Excel, local research runtime or configuration release; full-system recoverability is still unproved.
- Only read-only listing, hashing, container inventory and memory inspection were performed. No database, service, container, scheduling or PTA change. Observed server available RAM approximately 1012 MiB, with existing swap use; no restore launched. A scoped question was presented for a temporary isolated 256 MiB PostgreSQL restore target, conditioned on a fresh memory check and no external port. Authorization remains pending, not inferred from the question's preselected choice. Actual RTO/RPO remain unmeasured.
- Backup-source repair commit `02c80cb` passed GitHub run `36789263986`: offline-core and postgres-integration both SUCCESS. REAL_RESTORE remains NOT_STARTED; strict PIT and current investment admission remain incomplete; `action=no_order`.

## 2026-10-01 Backup Release Source Follows The Canonical Workbook

- Found the package CLI's default release inventory still resolving the canonical filename under the code root, although the user workbook lives at WORKBOOK_PATH. Fixed this existing entry to resolve both the legacy canonical filename and explicit WORKBOOK_PATH inventory marker through configured WORKBOOK_PATH (environment or the selected project .env), without a silent root-copy fallback. Existing generic release inventories and explicit release-file inputs remain compatible. The retained policy file itself is unchanged.
- Actual read-only resolution selected one workbook with SHA-256 `719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9`, matching the current publication. No workbook write, key read, package creation, database connection, server/PTA or scheduler operation was performed by that check.
- 28 backup/readiness tests passed, including temporary-directory CLI orchestration: canonical selection from the selected project .env, rejection when configuration is absent, and no packaging call after rejection. Receipt `.tmp/canonical-backup-cli-20261001.xml`. Prior full offline run before the additional CLI test: 1310 passed, 34 skipped, 21 existing deprecation warnings, `.tmp/canonical-backup-full-core-20261001.xml`.
- This repairs a real backup-input defect but does not establish an actual encrypted database backup, offsite delivery or isolated restore. REAL_RESTORE remains NOT_STARTED and INITIAL_ASSISTED_USE NOT_REACHED. Investment status and `action=no_order` unchanged. No new security subsystem or financial rule was introduced.

## 2026-10-01 H1 Financial Explanation Published In Canonical Company Card

- Published the reviewed 600887 H1 financial explanation through the existing protected publisher, not a new current workbook. Company financial-quality text now shows the six numerical facts, comparison periods, physical PDF pages and incomplete-admission boundary. Added the cash/dividend scope counterevidence and a source-bound audit link. Existing decision-step statuses, valuation scenarios, pending PriceBridge, unknown model validity and portfolio state were retained.
- Publication receipt: `runtime/publication-receipts/canonical-reviewed-research-20260930T174926Z-0d064c7a.json`. Before and backup SHA-256 `d9865ad6d51864e1c6cdf89810cfd518daba0c19368593157888b4b48a5a4c6e`; after `719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9`. WORKBOOK_PATH unchanged; 55 protected sheets preserved; native preview/export and seven-page readability passed before publication.
- Actual post-publication WPS read-only seven-page export completed with the after hash unchanged: `runtime/financial-review-publication-20261001/canonical-native-review/receipt.json`. Company page visually inspected with the financial text present and readable. Publication receipt's PENDING_WPS marker is immutable historical state; this entry records the subsequent verification. Current pointer now references the same canonical file and new hash/receipts.
- This is research explanation delivery, not full FinancialFacts/current admission, strict PIT, dividend sustainability approval or personalized trading advice. User acceptance NOT_PASSED; INITIAL_ASSISTED_USE NOT_REACHED; `action=no_order`. Runtime preview remains historical-only. No server/PTA, database, scheduler, thresholds or core business code changed.
- Pointer/preservation/Excel regression: 57 passed, 21 existing named-range deprecation warnings; `.tmp/financial-publication-regression-20261001.xml`. Actual source hash, protected publication and WPS receipts provide the workbook evidence beyond these temporary-file tests.

## 2026-10-01 Retained H1 Financial Quality Numbers Reconciled

- Reviewed the actual pinned 600887 H1 statement against the six existing atomic facts and frozen v13 snapshot: 6/6 shared item-verifier passes, 6/6 comparative-column substitutions rejected. Added eight source-row checks for gross capital purchases and the consolidated cash bridge; both cash-flow summation and opening-to-closing reconciliation match exactly.
- Receipt `runtime/financial-quality-review-20261001/review.json`, SHA-256 `22613674337cee28d96bb5de9822958ab0ad1715c2495879fe894e42bffb740c`; human-readable analysis `docs/current/600887-financial-quality-review-20261001.md`. Revenue +4.13% and parent profit -20.02% YoY; operating cash flow +229.23% YoY, short borrowing +41.74% and contract liabilities -53.15% versus year-end. Net consolidated cash/equivalent movement is negative CNY 3.763bn despite positive operating cash flow.
- This changes the concrete financial explanation, not admission: CFO-minus-capital-purchases is not admitted FCFF/FCFE or ordinary-share cash; the combined dividends/profit/interest cash line is not dividend-only cash. H1 arithmetic does not prove September maturity settlement, current liquidity, full business quality or strict PIT. Registered stop not reopened; current NOT_READY/no_order and canonical workbook unchanged.
- Latest committed engineering baseline `dad6eb3109f7e8393fc7a8d2a11cdbfe441b8b0f` also passed GitHub run `36751736846` (both offline-core and postgres-integration). This new financial review is separate local evidence pending commit, not covered by that CI as an investment conclusion.
- Reader/shared-valuation regression: 37 passed, `.tmp/financial-review-regression-20261001.xml`. These tests protect existing binding and no-order behavior; they do not certify the new research interpretation, investment returns, current event coverage or complete financial quality.

## 2026-10-01 Canonical Engineering CI Closure

- Commit `bdf7aa2bdc6682df2a505e6a43bd97deb57747dd` was pushed through the configured proxy. GitHub Core Research Gates run `36751414792` completed successfully: `offline-core` and disposable `postgres-integration` both SUCCESS. Evidence: https://github.com/MingMingLiu0112/value-investment/actions/runs/36751414792 . This confirms the committed engineering baseline, not investment readiness.
- Canonical workbook SHA-256 was rechecked unchanged: `d9865ad6d51864e1c6cdf89810cfd518daba0c19368593157888b4b48a5a4c6e`. Existing publication preservation, native seven-page WPS and readability receipts remain applicable. `SINGLE_CANONICAL_EXCEL=PASS`, `M7_PRODUCT_UX_IN_CANONICAL=PASS`, `COMPETING_CURRENT_WORKBOOKS=0`. No workbook was republished for this status update.
- `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`, current admission NOT_READY and `action=no_order` remain unchanged. Next work stays on the real single-company evidence/validity loop; no new feature stage or automatic order path is authorized.

## 2026-10-01 Independent Git Snapshot Regression

- Projected staged tree `8bae21ac341122db862835d0a2bf4cc47906bf74` was archived into `.tmp/public-ci-fixed-tree-20261001` and tested with its own Git index, without the user WPS workbook. Offline Core Research Gates: 1288 passed, 51 skipped, 21 existing named-range deprecation warnings; receipt `.tmp/public-ci-fixed-tests-20261001.xml`.
- The first projected snapshot exposed archive-byte preservation and script-inventory issues. Exact hash-bound registry/archive bytes are now protected by scoped `-text` attributes. The legacy direct quote rewrite entry fails closed before workbook access; original bytes are retained in ignored runtime, and its guard is tested. No frozen evidence hashes or investment thresholds were rewritten.
- This is local independent-snapshot evidence, not GitHub CI confirmation. Updated remote CI remains pending. Canonical publication and seven-page WPS proofs remain unchanged; user acceptance, strict PIT, current production admission, twenty real sessions and isolated restore remain incomplete. `action=no_order`; initial assisted use NOT_REACHED.

## 2026-10-01 Supported Reader Carries Validated Primary Numeric Metadata

- The existing arithmetic reader now consumes an optional, explicitly source-bound primary numeric review. It requires exactly the equity/share basis facts, matching symbol, units, period, input values and source hashes; current-only review scope, explicit non-admission and timezone-aware non-future observation are checked. It returns the original URL/page/excerpt metadata under `arithmetic_replay.primary_numeric_review`, separate from the retained historical observation.
- Actual existing 600887 command completed with the immutable primary-bound input: `runtime/primary-equity-basis-20261001/research-read-with-validated-primary-facts.json`. Both basis facts matched, and all three full-precision valuation scenarios still match. The original review/source/input/result files were not changed.
- 72 focused reader/valuation/bridge tests passed; `.tmp/primary-facts-reader-20261001.xml`. New tests cover changed value/unit/period/source, missing fact, missing excerpt, future/timezone-free observation and attempted current admission. No default model, formula or investment threshold changed.
- Metadata/value/source binding is verified by the application; PDF excerpt interpretation remains the separately recorded numeric source review, not an automated semantic fact verifier. Financial gate remains unapproved, strict PIT NOT_PROVEN, current validity NOT_ESTABLISHED and final NOT_READY/no_order. Canonical Excel unchanged. Updated full regression is pending at entry creation.
- Updated complete offline regression: 1304 passed, 34 skipped and 21 existing named-range deprecation-warning instances in 64.17 seconds; `.tmp/primary-facts-full-offline-20261001.xml`. This is local dirty-worktree verification, not updated remote CI or investment readiness.

## 2026-10-01 Primary Report Numeric Input Trace Completed

- Independently inspected the retained, hash-pinned 600887 H1 report (CNINFO 1225511409). Physical page 6 reports parent-attributable net assets CNY 53,711,364,981.99 at June 30; physical page 49 cross-checks consolidated parent equity and distinguishes total equity including minorities CNY 57,276,380,631.47. Physical page 159, note 53, reports opening/closing shares 6,325,360,667. These exactly match the two disclosed inputs used by the retained conditional residual-income calculation.
- Sealed two structured numeric source-review records with symbol, value, unit, report period, URL, source-file hash, page/excerpt, parser version and actual current observation: `runtime/primary-equity-basis-20261001/facts.json`. Publication time is null, interim report is unaudited, verification is NUMERIC_SOURCE_REVIEW_ONLY, historical availability is unproved and financial/current admission remains false. No acquisition or publication time was backdated.
- Added a new immutable reconstructed arithmetic input binding both the primary report and this review alongside the prior review, without changing the old input/result: `runtime/primary-equity-basis-20261001/primary-bound-arithmetic-input.json`, SHA-256 `da108054f7479fed52de5c96cd160f845d41486abb75dd7c7542450ed5b17d80`. Existing supported company command verified source-binding hashes and reproduced all three exact scenarios: `runtime/primary-equity-basis-20261001/research-read-with-primary-bound-input.json`.
- The current reader validates arithmetic and source bytes, not the review's PDF excerpt semantics or a complete FinancialFacts admission. Future ROE, retention, capital cost and growth remain analyst assumptions. This strengthens numeric traceability, not full business-quality approval, original-run descriptor reconstruction, strict PIT, current share denominator or post-maturity liquidity verification. Final NOT_READY/no_order and canonical workbook remain unchanged.

## 2026-10-01 Canonical Pending-Bridge Research Display Published

- The supported canonical CLI completed fresh verify-only and actual reviewed-research publication. Before/backup SHA-256 `3ee8d4527f4407f61de8982799e1e6189a1b922b33e9204b48de8c6844e55bae`; after SHA-256 `d9865ad6d51864e1c6cdf89810cfd518daba0c19368593157888b4b48a5a4c6e`. Receipt `runtime/publication-receipts/canonical-reviewed-research-20260930T165045Z-1447ce4a.json`; timestamp is UTC (October 1 China time).
- WORKBOOK_PATH unchanged, seven product pages present, all 55 retained sheets and protected OOXML passed fresh checks. Durable backup is recorded in the publication receipt. Preview WPS seven-sheet export and readability checks passed; visually inspected changed opportunity/decision pages and company scenario/research page. Actual post-publication WPS read-only seven-sheet export succeeded with unchanged canonical hash: `runtime/pending-bridge-publication-20261001/canonical-native-review/receipt.json`.
- The opportunity and decision pages now explicitly show shared pending PriceBridge/UNKNOWN validity, absent current price/date/margins and actionable missing-input explanation. Bear/Base/Bull stays 8.05/11.02/13.13, low confidence, June 30 valuation basis; original research remains September 22 and source observation September 30. No current price, completed debt settlement, business-quality approval, strict PIT, private portfolio or trade decision was inferred.
- Current pointer updated to this canonical receipt/hash only; simulation_only=false, one conditional valuation step and seven blocked steps, NOT_READY/no_order. Updated remote CI and actual user comprehension/sign-off remain unpassed. SINGLE_CANONICAL_EXCEL remains PARTIAL_PENDING_UPDATED_CI; M7_FINAL_USER_ACCEPTANCE=NOT_PASSED and INITIAL_ASSISTED_USE=NOT_REACHED.
- Preview preparation still uses a project-local verification harness; supported repeatable preview generation from the application output remains unfinished. No server/PTA, scheduler, broker, model formula or evidence-stop change occurred.
- Post-publication focused regression: 82 passed; `.tmp/published-pending-bridge-20261001.xml`. Existing named-range fixture emits 21 deprecation-warning instances. The current-entry resolver confirms the same WPS canonical path, new hash and no_order, without opening another workbook. These local checks do not replace remote CI or user acceptance.

## 2026-10-01 Official SCP011 Attachment Acquired and Scope Verified

- Retrieved the exact ChinaMoney primary attachment after resolving the download base from the page's observed cm-basic.js resource, not by guessing endpoints. Sealed article HTML, JS and PDF with acquisition receipt under `runtime/official-settlement-lead-20261001`. PDF SHA-256 `1196ef8e9841e8e06b40158d59865e5e45ab5be94a5d3627c759d0d8d59846cc`.
- The PDF is scanned (text extraction empty); rendered and visually inspected all three pages. It is issuer-stamped 2026-09-21 payment-arrangement notice for SCP011 / 012681643: principal CNY 10bn, scheduled payment 2026-09-29, scheduled principal/interest CNY 10,031,454,794.52. Page 2 describes funding/remittance mechanics; no actual completed remittance or post-maturity cash/debt bridge is confirmed. It does not cover issue 10. Structured scope assessment is retained alongside the originals.
- Thus original attachment acquisition is now complete, superseding the previous unresolved-download statement, but the notice is not eligible to reopen the registered settlement-outcome stop. UNKNOWN ModelValidity/unadmitted PriceBridge/NOT_READY remain unchanged. No default or payment-completion inference is made.
- Browser tab creation timed out but inventory confirmed the tab existed; binding also timed out. Used direct public-resource retrieval instead, with no access-control bypass or browser security override. No production code, canonical workbook, server, stop ledger or approval state changed. Source acquisition time is now, not an invented historical observation.

## 2026-10-01 Bounded New Official Settlement Lead Review

- Re-read the exact 600887 SCP010/011 stop: it concerns the 2026-09-29 maturity outcome and requires later eligible official settlement/refinancing or cash/debt evidence. No stop entry or approval state was changed.
- Bounded official-source web queries located a ChinaMoney primary page for the eleventh issue: `https://www.chinamoney.com.cn/chinese/fxdf/20260921/3421487.html`, published 2026-09-21 09:57, before maturity. The title says redemption announcement; title/date alone do not establish payment completion or the post-maturity liquidity bridge. Search also returned old/different-issue material, not an eligible new completion disclosure.
- Direct page fetch succeeded (HTTP 200). The attachment is a JavaScript download action keyed by contentId 3421487; the fetched document does not provide a resolved fileDownUrl. No PDF was acquired or hash-verified and no attachment content was treated as fact. This page is a navigation lead, not admitted evidence. Absence from these bounded results is not proof of non-payment, default or universal disclosure absence.
- Preserve UNKNOWN ModelValidity, unadmitted PriceBridge and NOT_READY/no_order. No repeat re-analysis of the retained SSE/CNINFO files, canonical write, broker/server operation or new trading signal occurred. New evidence work must satisfy the explicit outcome/bridge requirement; an advance payment notice alone cannot reopen the gate.

## 2026-10-01 Supported Arithmetic Version Check and Full Offline Regression

- Tightened the supported arithmetic replay to require the retained ValuationResult model version to equal the installed shared residual-income model version, not just the packet version/model type. A cross-version result cannot silently be described as the same replay. Added a negative version-mismatch regression without changing formulas or research rules.
- Complete workflow-selected offline Core regression after the CLI, dependency view and final layout changes: 1276 passed, 34 skipped, three existing deprecation warnings in 52.08s. Receipt `.tmp/arithmetic-supported-full-offline-20260930.xml` retains the filename from the run started before the local-date transition. Results cover the dirty local worktree only, not a new remote CI/committed-state certification.
- Re-executed the supported real 600887 pinned-input command after the version check, without creating an output file. Three full-precision scenarios still match; input remains the explicitly reconstructed pinned review, original descriptor not verified, strict PIT NOT_PROVEN/current admission false. The September research/observation dates were not rolled forward to October 1.
- Actual canonical SHA-256 remains `3ee8d4527f4407f61de8982799e1e6189a1b922b33e9204b48de8c6844e55bae`; no workbook/server/scheduler write occurred. Current ModelValidity and PriceBridge still require new eligible event evidence and properly admitted inputs. No twenty-session, recovery or human-acceptance gate passed; full goal remains in progress.

## 2026-09-30 Supported Pinned Arithmetic Replay Command

- Existing-read CLI now accepts paired explicit arithmetic-input path/hash. Application validates reconstructed-input schema, no_order, symbol, applicable residual-income model version, exact retained valuation hash/date, original source bytes and three complete scenarios; invokes the existing shared scenario function and rejects any numerical mismatch before writing the result. This is a model-specific replay adapter, not all-company FCFF/DCF routing.
- Sealed actual reconstructed input at `runtime/real-research-card-flow-20260930/reconstructed-arithmetic-input.json`, SHA-256 `a727d7ba1275af9391b86d4dce8729cbb7bdd551434d71b9cee71080f5c9b04c`. Source is the pinned reviewed assumption record, not an assertion that the old original descriptor was recovered. Supported CLI run saved `runtime/real-research-card-flow-20260930/supported-arithmetic-replay-result.json`: all three full-precision scenarios match; original_run_input_descriptor_verified=false, strict_pit NOT_PROVEN, current_admission=false and final NOT_READY/no_order.
- 58 reader/architecture/CLI tests passed; `.tmp/reconstructed-arithmetic-command-20260930.xml`. Added negatives cover changed input/source hash, altered scenario, wrong symbol and basis date. Initial test setup omitted Decimal and used an incompatible generic fixture model; corrected those fixture errors, not the production model applicability requirement. Updated complete offline/remote CI remains pending.
- No canonical publication, research approval, historical date reconstruction, source-stop reopening or server operation occurred. The real single-stock arithmetic is now repeatable through a supported command rather than only a one-off script, but current ModelValidity/PriceBridge, complete substantive research and historical decision replay remain unpassed.

## 2026-09-30 Independent Replay of Bound Existing Valuation Arithmetic

- Independently replayed the real 600887 review's explicit equity/share basis, ROE paths, retention and cost/growth sensitivity through the shared residual-income scenario function. Review file was verified against its original-source hash. All three full-precision retained scenario values match; all eighteen sensitivity cells match within their published ten-decimal rounding. Receipt `runtime/real-research-card-flow-20260930/independent-bound-arithmetic-replay.json`.
- The original package differs materially from the reviewed successor: old opening equity 54,655,690,475.89 and original scenario assumptions are not the later 53,711,364,981.99 equity/9% cost/25% retention review inputs. Reading the source package alone is not a reproduction of the follow-up. The reviewed June 30 ordinary-share basis is 6,325,360,667. The shared scenario function's legacy output-key wording says 2025 issued shares; this replay supplies the explicit June 30 basis and records that naming limitation without changing frozen formulas.
- This proves arithmetic consistency from the pinned review inputs, not reconstruction/hash verification of the complete original run input descriptor. Original descriptor verification remains false, strict PIT NOT_PROVEN and all current admission flags false. Initial one-off verifier used the wrong review JSON key; corrected to the existing `model` object without modifying source evidence.
- Next engineering dependency: preserve an explicitly versioned replay-input artifact and bind its exact bytes to an arithmetic replay receipt through the shared application, rather than relying on reconstructing a hidden temporary input from a hash. Such a new replay must be labelled new/reconstructed and must not claim to match the historical descriptor unless its hash is actually verified. No canonical workbook, server or investment gate changed; no new company work was started.

## 2026-09-30 Original Research and Follow-Up Dependency Binding

- Supported existing-read command now returns an explicit dependency view: exact ValuationResult hash/basis date, follow-up run/date, original ResearchCase version/date/content hash, pinned source package path/hash, observation basis and original-source count. Current research/price admission remain false; portfolio snapshot remains absent. This distinguishes the 2026-09-22 original research from the 2026-09-30 conditional follow-up instead of inheriting historical approval.
- Artifact-declared available_at/computed_at must be timezone-aware and no later than the receipt observation; future follow-up research dates fail closed before output. This prevents a later result being read as already available at an earlier observation, but does not establish historical PIT or contemporaneous source capture.
- Actual nine-original 600887 command succeeded and saved `runtime/real-research-card-flow-20260930/lineage-bound-research-read.json`. Original ResearchCase hash `9a330f3118f30543d9c849357d3d80b07015db1619ef3b64a2f25fab04304f9b`, valuation hash `f107e9df73794f74a3b7c49867cd45d13f56235fce32162d3cb6fe21920a8f18`; dates remain distinct. No facts or assumptions were reclassified as approved.
- 46 reader/architecture tests passed; `.tmp/research-dependency-read-20260930.xml`. Four negative cases reject future availability/computation/research date and timezone-free availability, with no output file created. No canonical write, model formula/threshold change, historical data reconstruction or server operation occurred. Current single-stock result remains NOT_READY/no_order and the full goal is incomplete.

## 2026-09-30 Historical Replay Scope Verified Against the Current Goal

- Inspected the supported three-company replay implementation: it compares frozen research-runner semantics, not multi-session historical execution. Inspected the retained M3 decision subject: symbol 600519, 2024-06-21, retrospective 2025 rule extension, relative_pe_research_only. Neither proves the selected 600887/000333 applicable-model decision replay.
- Actual read-only independent PIT v2 verification with no input manifest returned NOT_PROVEN, strict_pit_admissible=false, performance_claim_allowed=false. Retained subject SHA-256 `2822dd786a40433ed03eac1e741a82a219cc9c76196b267e3a76290e53a141b9`; receipt `runtime/real-research-card-flow-20260930/retained-replay-scope-audit.json`. This does not assert absence of a manifest elsewhere or change any frozen receipt.
- Updated remaining-gates current canonical publication hash/receipts and documented the exact legacy replay limitation. No threshold tuning, backfilled historical assumptions, historical module edits, scheduler/server changes or canonical writes occurred. A replay gate must be proved with a dated applicable-model input/rule chain; the current 2026-09-30 observed-source loader cannot prove retrospective availability.
- Next single-stock work should connect versioned actual research/facts and decision dependencies, preserving strict PIT not proven where chronology is insufficient. Keep existing retrospective experiments as historical diagnostics, never current-stage graduation evidence. Goal remains active and incomplete.

## 2026-09-30 Opportunity Comparison and Historical Assessment Published

- Latest canonical publication now includes the opportunity row's same-source scenario/date/confidence, unavailable current-price explanation and explicit decision reason, plus dated historical G0-G3 assessment/disclaimer in the company card. Moved Bear/Base/Bull before detailed decision review; inspected native company page 2 confirming the valuation block is no longer isolated on page 3. Historical limitations remain present; no research or trade gate was elevated.
- Preview readability passed all seven pages with no detected clipped rows; actual WPS native seven-page export and retained-sheet snapshot passed. Publication receipt `runtime/publication-receipts/canonical-real-research-20260930T153741Z.json`: before/backup SHA-256 `098bcc375eb4d5566054f36396af8d46e6d3b4356b6dd28b371ad345670615e7`, after `3ee8d4527f4407f61de8982799e1e6189a1b922b33e9204b48de8c6844e55bae`. WORKBOOK_PATH unchanged, 55 retained sheets preserved, no competing current Excel.
- Actual canonical WPS read-only receipt `runtime/publication-receipts/canonical-opportunity-layout-wps-20260930.json` passed with unchanged published bytes and seven BLOCKED assessments. Current pointer now binds this publication/hash/readability evidence. WPS receipt canonical_touched=false describes verification only, not the preceding publication.
- Post-publication pointer/preservation/renderer/reader regressions: 53 passed, three existing warnings; `.tmp/opportunity-canonical-published-20260930.xml`. Earlier full offline 1265-pass run predates the final layout reorder; not a claim of updated remote CI. Canonical PASS flags remain pending updated CI.
- Current suggestion NOT_READY, valuation CONDITIONAL, action=no_order; ModelValidity, current PriceBridge, strict PIT, real portfolio, twenty real sessions, isolated restore and human comprehension/final acceptance remain unpassed. Previous paragraphs describing these rows as unpublished are historical and superseded by this dated record. Continue the real single-stock research/application dependencies, not another navigation/layout expansion.

## 2026-09-30 Supported Read-Existing Research Command

- Existing `scripts/current/run_company_research.py` now supports explicit `--existing-manifest` plus `--existing-manifest-sha256`. The read mode excludes package/schedule-request rerun inputs; all financial decoding, original verification and no-overwrite output belong to the shared Application layer. Normal research behavior and Evidence Stop scheduling are unchanged.
- Actual invocation for 600887 succeeded, verifying the pinned nine-source manifest and artifact. Output `runtime/real-research-card-flow-20260930/existing-research-command-result.json` contains typed valuation/source metadata, `READ_EXISTING_ONLY`, NOT_READY, no portfolio guidance/price bridge, strict PIT NOT_PROVEN, no research rerun and no canonical write. Manifest SHA-256 `032dc2823dcd3e475221e45c8876be1af309b80bcbd8df705b40b33446ebe740`; expected hashes must come from the reviewed provenance record, not be silently computed inside the read command.
- This provides a supported reproducible entry point for the existing research display inputs, not a replacement for fresh research or investment approval. Service checks reject hash/symbol conflict, output overwrite and path escape; CLI checks reject ambiguous modes. Current Excel/hash unchanged.

## 2026-09-30 Current Model-Validity Dependency Recheck

- Inspected actual ModelValidity/PriceBridge implementations and the exact `600887-scp010-011-quote-day-liquidity` Evidence Stop. The missing settlement/refinancing and cash/debt bridge is not cured by a newer price or by three different issues being repaid. Existing conditional valuation remains intact; the affected current conclusion stays NOT_READY.
- Re-read local primary issuance document 1225412264 (SHA-256 `f8c529139b7f49d73f355ecd41c8dea44e68ff35765379538dd090ccba5f6a2d`) and redemption document 1225584526 (`4ef69c200e7b3d0cde3e1b667bcbb4304d15dd6aa406585ca796aa2c3ab4a270`). The former schedules issues 10/11; the latter explicitly reports completion for issues 12/13/14 only. Verified scale: issues 10/11 are CNY 100 hundred-million each (CNY 20bn combined); issues 12/13/14 CNY 25bn combined. No unit correction or assumption of payment/default is justified.
- This bounded read tests the stated blocker and original units, not another disclosure search or evidence-stop reopening. No network fetch, current quote admission, model-validity override or canonical write occurred.
- Updated the remaining-gates handoff to supersede its outdated synthetic-publication/staging-wait state with the actual current canonical hash and receipts. Staging authorization is no longer requested; human acceptance, remote CI, real PIT and current decision dependencies remain unpassed.
- PriceBridge, existing-artifact reader and architecture focused regression: 56 passed; `.tmp/current-validity-dependency-20260930.xml`. These exercise price/validity separation and fail-closed contracts; they do not establish actual issue-10/11 settlement or a current valid model.

## 2026-09-30 Existing-Result Reader Connected to Product Flow

- Real projection harness now consumes the shared existing-result Application function rather than duplicating ValuationResult decoding and original-file verification. Presentation explicitly maps plain source metadata into its typed audit records; Application remains independent of presentation.
- Added Application-to-workbench-to-XLSX regression: verifies all three scenario values render, seven pages exist, valuation remains CONDITIONAL and other gates BLOCKED. 35 loader/architecture tests passed; `.tmp/existing-valuation-e2e-20260930.xml`. A read-only real model check used all nine actual originals and the shared projector without rewriting preview or canonical files.
- Current goal document distinguishes historical synthetic publication from the latest real conditional presentation and permits related single-stock engineering while stage-1 human acceptance remains pending. No acceptance requirement, investment threshold or total objective was relaxed.
- Complete workflow-selected offline Core run passed: 1253 passed, 34 skipped, 3 existing warnings in 58.40s; `.tmp/existing-valuation-full-offline-20260930.xml`. This validates the dirty local working state, not committed HEAD or remote CI. Portfolio/live shadow/restore/human acceptance remain separate missing evidence.

## 2026-09-30 Shared Existing-Result Application Read

- Added application-layer read of an explicitly hash-pinned existing valuation artifact and originals. Returns typed ValuationResult plus source metadata with observation timestamp/basis; never reruns research, collects evidence, admits a model/price gate or imports presentation. Corrupt artifact/result/original bindings, missing/escaped original paths, future valuation basis and timezone-free observations fail closed.
- 49 existing-loader/architecture/projection tests passed; `.tmp/existing-valuation-application-20260930.xml`. The initial attempt imported a presentation EvidenceRecord from Application and was rejected by architecture tests; corrected to presentation-independent source metadata, keeping the dependency rule unchanged.
- Actual nine-file 600887 read verified using the shared function; `runtime/real-research-card-flow-20260930/application-existing-result-check.json`. This proves the reusable loader works against real local artifacts, not only fixtures. No Excel, scheduler, server or frozen artifact was changed.
- Reconciliation of the existing follow-up: ordinary-share basis has a successor resolution; future ROE remains a low-confidence assumption range; ROIC is not required for this arithmetic but remains a business-research limitation; dividend sustainability UNKNOWN, strict PIT NOT_PROVEN and current PriceBridge not admitted. Do not reclassify these distinctions as approved financial/business or trade gates.

## 2026-09-30 Research Thesis and Counterevidence in Canonical Company Card

- Shared typed ResearchCase presentation now exposes the original research thesis, return drivers, unproven mispricing hypothesis, positives, counterevidence, hypothesis-labelled thesis breakers, next events and recorded limitations. Hash/issuer mismatch fails closed; price, valuation, all eight gate states and the user's original Entry Thesis remain unchanged. No company-specific branch or new investment judgment is introduced.
- Used the follow-up's pinned source package and remapped source IDs by verified source hashes; an additional existing cost-of-equity artifact was read and verified. Research content remains explicitly dated 2026-09-22, not a claim of fully updated current research. Some historical gaps may have successor resolutions: this display does not re-evaluate them or treat old collection tasks as authorization to bypass Evidence Stop.
- 39 research/read-model/Excel tests passed; `.tmp/research-case-card-20260930.xml`. Integrated preview passed all seven-page readability checks, retained-sheet preservation and WPS opening. Visually inspected both native-exported company-card PDF pages: explanations and scenarios are readable without clipped content.
- Published to the same canonical workbook: before/backup SHA-256 `184ea671d6c2752cb875b1d4cc3e83b41ae9965382fb2a8b18031f5f1d46ed04`; after `098bcc375eb4d5566054f36396af8d46e6d3b4356b6dd28b371ad345670615e7`. Receipt `runtime/publication-receipts/canonical-real-research-20260930T141646Z.json`; 55 retained sheets preserved. Actual canonical WPS read-only verification also passed with unchanged hash; `runtime/publication-receipts/canonical-real-research-card-wps-20260930.json`. Current pointer updated accordingly.
- Existing gates stay CONDITIONAL valuation / seven BLOCKED, NOT_READY/no_order; Strict PIT, current PriceBridge, personalized portfolio and user acceptance are not passed. Remote CI and whole-product live validation remain outstanding. Next: reconcile the dated ResearchCase and successor facts through the shared application, not by marking presentation text as an approved gate.

## 2026-09-30 Real Research Published to Canonical Excel

- Published the existing 600887 conditional research result into the unchanged WORKBOOK_PATH. Replaced synthetic product content with a real-only single-company projection; retained all 55 non-product sheets. No personal holdings, current quote, safety margin or trade suggestions were fabricated. Seven decision blockers now explain evidence/PIT, business review, current model validity, price bridge, research approval, private portfolio and final NOT_READY conditions.
- Before/backup SHA-256 `53128c2775759297c1592400d131bd1b15017370f3513353a2cec69e98fefaf5`; after `184ea671d6c2752cb875b1d4cc3e83b41ae9965382fb2a8b18031f5f1d46ed04`. Full retained-sheet snapshot PASS; seven-page readability audit passed without clipped rows; integrated WPS preview and actual canonical read-only open both PASS with unchanged published bytes.
- Publication receipt `runtime/publication-receipts/canonical-real-research-20260930T140408Z.json`; backup `runtime/workbook-backups/canonical-before-real-research-20260930T140408Z.xlsx`; actual canonical WPS receipt `runtime/publication-receipts/canonical-real-research-wps-20260930.json`. WPS receipt's `canonical_touched=false` describes the verification operation (read-only), not the preceding publication.
- Current pointer now binds this publication/hash with `simulation_only=false`, observation date 2026-09-30, valuation basis 2026-06-30, no admitted current quote or event coverage. Preserves `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`, `action=no_order`, canonical PASS flags pending updated remote CI. This is real conditional research presentation, NOT a complete single-stock investment decision loop. Whole-workbook native visual review and detailed business/thesis connection remain pending.
- Post-publication tests: 34 pointer/preservation/projection tests passed after replacing the old fixed simulation expectation with two explicit temporary-pointer cases (simulation and real research). Actual opener resolves the same canonical file and published hash. Full offline Core rerun: 1241 passed, 34 skipped, 3 existing deprecation warnings in 50.70s; `.tmp/real-canonical-offline-core-20260930.xml`. GitHub CI has not been rerun for this dirty worktree; no remote GREEN or final canonical PASS assertion.

## 2026-09-30 Real-Only Valuation Workbench Preview

- Constructed a real-only, current-observation read model for the existing 600887 follow-up without importing synthetic company explanations, fake portfolio metrics or test fixtures. All nine original files were rehashed before rendering; full ValuationResult hash and audit bindings passed the shared projection. Availability is conservatively today's observation, not a historical publication claim.
- Rendered seven-page historical preview under `runtime/real-product-flow-20260930/`, not a current pointer. SHA-256 `608e3d2a55af6e5d0a9f2c31b3b4b0147ca68d010182343391735daaee4a2412`. Company and opportunity valuation status agree; Bear/Base/Bull displays CNY 8.05/11.02/13.13, low confidence, basis 2026-06-30. One valuation step is CONDITIONAL; the other seven are BLOCKED and final suggestion remains NOT_READY/no_order.
- Actual WPS read-only open passed with seven-page navigation and unchanged bytes; receipt `runtime/real-product-flow-20260930/wps-verification.json`. Exported decision-page PDF and visually inspected its rendered PNG: scenario text, risk boundary, next actions and nine-source evidence link are readable without overlap. This visual check covers the decision page, not all pages or final user acceptance.
- No protected canonical publication occurred. Real business-quality/financial/thesis evaluations remain not connected to this preview; placeholders explicitly say missing evaluation, rather than imply completed research. Next: replace generic blockers with bound application outcomes, verify all user pages and preservation, then publish to the same canonical workbook. Strict PIT/current ModelValidity/PriceBridge remain unpassed.

## 2026-09-30 Real 600887 Original-File Verification

- Located and read the nine actual files referenced by the prospective follow-up: five CNINFO financial reports and four registration/snapshot/review artifacts. Each original-file SHA-256 matches its valuation evidence reference (9/9 PASS). File paths stayed inside the project; no network fetch, research rerun, evidence-stop reopening or workbook write occurred.
- Receipt: `runtime/publication-receipts/600887-existing-valuation-originals-20260930.json`, observed at 2026-09-30T21:12:28+08:00. Follow-up artifact SHA-256 `ad3e3296832daf107e44b17f545282505c6a8053dbf9108359cb783279821685`; recorded valuation-result binding `f107e9df73794f74a3b7c49867cd45d13f56235fce32162d3cb6fe21920a8f18`.
- Verification proves byte agreement with existing references, not original historical publication availability, issuer authenticity independently of prior review, or strict PIT. The receipt explicitly retains `strict_pit=NOT_PROVEN`, `model_validity=NOT_ESTABLISHED`, `price_bridge=NOT_ADMITTED`, `action=no_order`. A current observed-only projection can use this observation conservatively; it must not backdate availability from URL or filesystem timestamps.
- Next product step: construct a real-only, explicitly dated workbench from the verified follow-up (not synthetic company explanations), bind these audit originals and preserve unpassed price/research/portfolio gates; render and test before protected canonical publication.

## 2026-09-30 Whole-Workbench Valuation Evidence Binding

- Shared `workbench_with_bound_valuation` requires an existing company, matching audit IDs, source hashes and (where present) official URLs. Undated or future evidence and a valuation basis after the workbench cutoff fail closed. This checks admitted presentation bindings; it does not claim that dates alone prove strict PIT, and it does not replace Application-layer original-file verification.
- Updates company scenarios and opportunity valuation status together, preserving all nonvaluation gates, quote, portfolio, events, overview and audit records. No company-specific branch, trade state or order was added.
- Focused regression: 50 passed, `.tmp/bound-valuation-workbench-20260930.xml`. Canonical workbook remains synthetic and unchanged. Real artifact ingestion, original-file checks, an explicitly dated real workbench and protected publication remain pending.
- Full workflow-selected offline Core rerun: 1240 passed, 34 skipped, 3 existing deprecation warnings, zero failures (45.68s); `.tmp/trading-assistant-offline-bound-valuation-20260930.xml`. No claim of remote CI or production readiness. Inspected the real follow-up's nine references: five CNINFO reports and four registered snapshot/review artifacts; all nine must be admitted with original-file hash and availability verification before real projection publication.

## 2026-09-30 Bound Valuation Company-Card Projection

- Added shared presentation projection `company_with_bound_valuation`: verifies symbol and full typed ValuationResult hash, then updates scenario cards, valuation summary, valuation section and the valuation decision step together. All other research, price, margin, dividend, decision-review and gate states are preserved; no calculations or gate admission are inferred.
- Complete bound scenarios remain conditional research, even when the upstream result says ready. Missing scenarios remain unavailable across all three scenario cards. Cross-company results and changed hash bindings are rejected. Evidence references are retained for the enclosing workbench audit validation.
- Focused read-model/Excel regression run: 43 passed; `.tmp/bound-valuation-card-20260930.xml`. Added the projection tests to the offline CI selection. An initial shell quoting failure prevented fixture setup; the corrected explicit PS7 command used project-local temp and completed successfully. This is local validation, not remote CI.
- Real 600887 artifact admission and whole-workbench evidence binding still need integration before publishing this projection. Canonical workbook was not changed; it remains the explicitly simulated frontend. Current PriceBridge, strict PIT, portfolio and user-acceptance requirements are not passed by this work.

## 2026-09-30 Real Single-Company Follow-up Revalidation

- Re-executed `tests/test_600887_prospective_case_followup.py` and `tests/test_600887_shared_valuation_binding.py`: 2 passed. Receipt `.tmp/yili-real-followup-revalidation-20260930.xml`. These tests bind registration, immutable baseline, reviewed inputs and the shared residual-income application replay; they are not merely artifact-existence checks.
- Existing follow-up result remains CNY 8.047594 / 11.023375 / 13.133453 per share, valuation basis 2026-06-30, low confidence and conditional research only. This is an existing result revalidated, not a new current valuation or a trade recommendation. Strict PIT remains NOT_PROVEN and no admitted current PriceBridge exists.
- The generic research application exposes exact-scope Evidence Stop scheduling; it must not rerun the stopped case just to republish a previously admitted follow-up. Next engineering step is read-only projection of a verified existing result into the shared product contract with independent BLOCKED price/decision/portfolio gates. Do not reinterpret a missing quote as missing intrinsic-value arithmetic, or a conditional valuation as a passed investment gate.
- Canonical frontend remains the explicitly synthetic published workbench pending a separately verified real-result projection; no workbook or scheduling write was made in this revalidation.

## 2026-09-30 Canonical Seven-Page Synthetic Publication

- User confirmed the narrowly scoped C-volume atomic publication staging exception and then closed WPS. Native write guard confirmed unlocked before publishing. The AppData path resolves through the verified Codex MSIX cache mapping; only that fixed mapping or the exact unredirected approved path is accepted.
- Canonical source/backup SHA-256: `99adbfbab0453ac42b05ffc804c8cd95b64162c9382feab3d8dbd8b05ae7983a`; published SHA-256: `53128c2775759297c1592400d131bd1b15017370f3513353a2cec69e98fefaf5`. WORKBOOK_PATH unchanged. Seven managed sheets plus 55 retained sheets: 62 total.
- Publication uses the exact candidate and source hashes bound by the full preservation receipt; protected atomic replacement and backup comparison succeeded. Receipt: `runtime/publication-receipts/canonical-seven-page-simulation-20260930T124708Z.json`. WPS opened the actual canonical workbook read-only, verified seven-page navigation and explicit simulation/no_order banner, and closed without saving; file hash unchanged. WPS receipt: `runtime/publication-receipts/canonical-seven-page-wps-verification-20260930.json`.
- `CANONICAL_UPDATED=YES`, `WPS_CANONICAL_OPEN=PASS`, `simulation_only=true`, `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`, `action=no_order`. This publishes the user-authorized simulated product flow, NOT verified current research or trading advice. Earlier blocked/publication-pending entries below are historical.

## 2026-09-30 Canonical Integration Preservation Recheck

- Final local rerun including the sheet-identity relationship repair: 144 workflow-selected modules, `1225 passed / 34 skipped / 3 warnings / 0 failures`; receipt `.tmp/trading-assistant-offline-core-preservation-final-20260930.xml`. This supersedes the earlier pre-repair local run, not remote CI.
- Publication authorization remains outstanding across repeated goal continuations. Project-only staging and C-volume atomic replacement cannot both hold for the existing D/C layout. Prepared preview, full preservation and local test work are complete for this increment; no further preview duplication or threshold relaxation is justified. Await the user's narrow staging exception decision before publishing. Overall product acceptance and the full objective remain unfulfilled.

- Actual current canonical source SHA-256: `99adbfbab0453ac42b05ffc804c8cd95b64162c9382feab3d8dbd8b05ae7983a`. It has 61 sheets, six visible product sheets and 55 hidden retained sheets; `决策过程` has not been published into it.
- A project-local, explicitly synthetic historical integration preview has seven managed pages plus all 55 retained sheets. Initial raw-part comparison failed because inserting the page renumbered worksheet XML paths. The corrected relationship fingerprint binds retained relationship content to worksheet identity while still hashing the full relationship bytes. A regression test accepts sheet-position changes and rejects changed hyperlink targets.
- Full `_snapshot` / `_assert_retained` comparison on the actual canonical source and the saved integration preview passed. Receipt: `runtime/simulated-product-flow-20260930/canonical-integration-full-preservation.json`; preview SHA-256: `53128c2775759297c1592400d131bd1b15017370f3513353a2cec69e98fefaf5`. All 55 retained sheets passed the current cell/structure/relationship contract. The canonical source hash remained unchanged. This is not publication or user acceptance.
- Latest complete local offline workflow selection before the relationship-key repair: 144 modules, `1224 passed / 34 skipped / 3 warnings`. The relationship repair subsequently passed 16 focused preservation tests; full offline and remote CI must be rerun for that newer state. No commit or push is claimed.
- `CANONICAL_UPDATED=NO`, `INITIAL_ASSISTED_USE=NOT_REACHED`, `action=no_order`. Same-volume atomic staging remains incompatible with the D-project/C-canonical layout under the current project-local policy; a narrowly scoped publication staging exception has been requested but not confirmed. No competing current workbook or WORKBOOK_PATH change.

## 2026-09-30 Trading Assistant Decision Process — Current Increment

- Stage 1 now has a seven-page renderer: existing product sheet names retained, `决策过程` inserted between opportunities and companies, home links to all seven. The added page displays the eight checks required by the active objective, their upstream status, reason, next action and audit evidence links. No evaluation is computed in the renderer. Missing formal evaluations remain `BLOCKED`; the final missing decision is `NOT_READY`.
- `DecisionStepView` requires the complete ordered eight-step contract. `PASS` / `CONDITIONAL` display records require assessment IDs and evidence references; unknown evidence IDs reject the read model. IDs stay in the audit page. These structural checks do not establish correctness of the upstream investment evaluations. The application still needs to project actual evaluator results rather than leaving placeholders.
- A focused suite covering models, rendering, simulation CLI and canonical protection passed **84 tests**, with three existing named-range deprecation warnings. The affected navigation, M4 and M5/prospective consumers passed **43 tests, 2 skipped**. The skips are the existing M4 private-root/temp conflict, not successful onboarding. Full offline CI and remote GitHub CI were not rerun for this uncommitted increment.
- Publication testing found the pre-existing uncommitted cross-volume fallback could create staging under external `LOCALAPPDATA`. A project-containment guard now rejects that fallback before creating files; the regression test supplies an isolated mock `LOCALAPPDATA` and verifies it remains absent. No production workbook was published. D:-contained atomic staging and a C: canonical still cannot satisfy the existing same-volume boundary simultaneously.
- Actual synthetic CLI output: `runtime/simulated-product-flow-20260930/decision-process-final-preview.xlsx`, SHA-256 `281ae13394fad2a7014ffe4f7f41be7ae58a2a0288a4fb51bed89752e482dc47`. The sample cutoff remains 2026-09-25. There are three company cards and 24 blocked missing assessments; no personal portfolio inputs or investment decisions were created.
- WPS read-only verification opened this preview, checked exact seven-page order and 24 blocked assessments, exported the first company's decision page, and verified the XLSX hash did not change. Receipt: `runtime/simulated-product-flow-20260930/decision-process-final-wps-receipt.json`. Rendered first-company PDF was visually inspected after title contrast and simulation-banner repairs. All seven sheets passed the structural row-height/freeze audit in `decision-process-final-readability.json`; this is not a visual inspection of every sheet or user acceptance.
- Canonical file/pointer unchanged by this increment. Source changes remain uncommitted. Stage 1 is `PARTIAL`; real gate projection, canonical publication, valuation/PriceBridge, PIT, historical decision replay, real-session shadow observation, actual recovery and final user acceptance remain open. `INITIAL_ASSISTED_USE=NOT_REACHED`; `action=no_order`.

## 2026-09-30 Trading Assistant Synthetic CLI — Current Increment

- Re-read the active `VALUE-INVESTMENT-TRADING-ASSISTANT-V1` objective. The previous turn produced a synthetic presentation preview; it did not complete the research-to-decision, portfolio, canonical publication or live-observation requirements.
- The existing simulated trial CLI now accepts paired `--synthetic-packet` / `--evidence-root` inputs under project `runtime/`. It requires `simulation_only=true` and `action=no_order`, and delegates evidence/hash validation and presentation to the existing application/read-model/publisher contracts. This route does not read the unavailable pinned M3 production manifests.
- Actual CLI execution succeeded using `runtime/simulated-product-flow-20260930/packet.json` and its 13 synthetic evidence files, producing `runtime/simulated-product-flow-20260930/cli-product-workbench.xlsx` plus the publisher manifest. The input is the committed synthetic test fixture serialized for this local run. Its declared sample cutoff is 2026-09-25; it is not current-market evidence. Output: 18 opportunities, three incomplete-research company cards, six daily items, one synthetic event and no personal portfolio positions.
- Focused verification: `tests/test_simulated_product_user_trial.py` plus `tests/test_product_workbench_candidate.py`: **20 passed**. Coverage includes generation without production artifacts, workbook reopen, undeclared simulation rejection, changed-evidence rejection, external evidence-root rejection and order-action rejection. Pytest temporary data stayed under project `.tmp/`. No visual/WPS acceptance or remote CI was claimed.
- Source edits remain uncommitted. The configured canonical workbook and current pointer were not published or changed by this increment. M4 onboarding remains incomplete due its existing scratch/private-root constraint conflict. Dedicated decision-process UI, validated valuation/PriceBridge decisions, strict PIT, real-session shadow observation, actual recovery and final user acceptance remain open. `INITIAL_ASSISTED_USE=NOT_REACHED`; `action=no_order`.

## 2026-09-30 Project Closeout — Current

- The failure in prior run `36665479304` was confirmed from its GitHub job log: `test_midea_unified_result_pins_its_research_and_applicability_snapshot` and `test_midea_unified_result_remains_fail_closed_after_provenance_repair` read runtime JSON absent from a clean checkout. Their provenance checks now use self-contained synthetic inputs; no runtime bundle was added and no assertion was removed. Commit `0a70f20775c1da7928418ff0e1c0ae3c65b50723` passed both Actions jobs in run `36673042770`. A follow-up workflow fix added `include-hidden-files: true` so JUnit XML under `.tmp/` is retained; commit `8c1d14e8c84796d2aa23754d82abc4b762bc5d39` passed both jobs in run `36673521898`, and the Core JUnit artifact (27 KB) plus PostgreSQL restore artifact were confirmed present.
- The exact workflow offline-core selection contains 141 test modules. After the backup-security hardening below, the full local PowerShell 7 run passed `1198 passed, 32 skipped, 3 warnings` in 65.73s. The latest focused backup/M6/M4/Evidence Stop run passed `44 passed, 3 skipped`; `tests/test_backup_security.py` passed `9`. JUnit and pytest temp output were directed under project `.tmp/`; both CI jobs now create `.tmp/` before dependency installation. These are local results; no new GitHub Actions run was started for the uncommitted patch.
- M4 synthetic scratch audit found the key directory relied on `tempfile`'s default root while the data directory was explicit. Both now use the verified project temp root; a focused test confirms both paths and cleanup. The two full synthetic onboarding tests remain skipped when pytest's temp root is inside the repository because `private_portfolio_intake` intentionally requires its private root to remain outside the repository. No boundary was weakened.
- Initial P4 review correctly rejected placing plaintext directly in the shared `.tmp/` root because it grants `Authenticated Users: Modify`. The implementation uses a separate `.tmp/backup-restore-plaintext` directory with a protected Windows DACL limited to the current process user, SYSTEM and Administrators. After ACL review found the project parent and `.tmp` ancestors also grant `Authenticated Users: Modify`, Windows restore now holds no-delete-share directory handles from the mutable parent through project root, `.tmp`, and each output path component; each component is opened with `OPEN_REPARSE_POINT` and reparse points fail closed. `icacls.exe` is invoked from the system directory, and owner read-back converts the owner account string to SID. POSIX scratch permissions remain `0700`. Decryption output is a separate empty child of project `.tmp/`; a failed extraction or manifest/hash validation clears partial plaintext while the protected handle chain is held, while success retains the output for isolated restore verification. No real backup, key or restore was used; no concurrent adversarial stress test was run.
- The latest focused backup-security suite passed `9` tests. The latest run covering backup security, M6 operational readiness, M4 synthetic onboarding and Evidence Stop scheduling passed `44 passed, 3 skipped`; the skips remain the private-root/platform-gated cases. The full 141-module workflow offline-core selection passed `1198 passed, 32 skipped, 3 warnings`. A prior owner verification bug was caught by the Windows integration test (`Get-Acl.Owner` is a string, not a security principal) and fixed by explicit `NTAccount` to SID translation.
- The focused `tests/test_evidence_stop_schedule.py` rerun passed `19 passed, 1 skipped`. Its first invocation set pytest `--basetemp` under `.tmp/` without aligning Python `TMP/TEMP/TMPDIR`; all 20 cases failed in fixture setup before test bodies. Aligning both roots under project `.tmp/` resolved the invocation issue; no test or trust-boundary change was needed.
- Evidence Stop scheduling now treats a Fresh ResearchCase without a matching stop as `ALLOW_NORMAL_RESEARCH`; a matching stop remains a negative gate until explicit reopen criteria and new issuer/hash-verified evidence pass. `recover_admitted_schedule` validates a pre-existing admission and records a recovery receipt only; it neither adds evidence nor executes/retries research. Current-state check found the ledger but no `runtime/research-evidence-stop-consumptions` admission receipt or recovery receipt, so P3 has no eligible schedule and no recovery API was called. Repeated stops remain blocked. No new company research ran; `600519` remains outside this stage's authorization.
- Current research states are unchanged: `600887=CONDITIONAL_VALUATION_READY` (low confidence; no current `PriceBridge`), `000333/601088=INSUFFICIENT_PUBLIC_EVIDENCE`; Strict PIT is not proven, M6 is not started, M7 final user acceptance is not passed, and `action=no_order`.
- The separate legacy server timer still runs `track-candidates` followed by `refresh-valuations` for screen candidates. It is not the ResearchCase scheduler; switching that production flow to quote-only/event-triggered refresh remains unapplied because R3 production authorization is not granted. No server schedule or M6 operation was started.
- The WPS Canonical remains unchanged at SHA-256 `849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`; no workbook or candidate was created. The workspace dependency loader was rerun and its approved runtime still lacks `@oai/artifact-tool`. The user permits building on D: and copying to C:, but the existing same-volume atomic publication contract remains in force; the publisher fails closed before file creation. No alternate workbook library, C:-side staging, or lock bypass was used. The canonical quote pointer remains 2026-09-28.
- Read-only P4 inventory enumerated all 55 root `.pytest-tmp*` directories: 23,916 files totaling 2,320,206,911 bytes; no file- or directory-level reparse points were observed. SHA-256 succeeded for all 23,916 files, producing 3,336 unique hashes, 1,006 duplicate-content groups and 20,580 extra copies. Git-tracked text contains 636 hash-reference occurrences matching 61 unique temp-file hashes across 3,886 file instances; no exact reference to any of the 55 full directory names was found. Runtime contains 109,093 files / 17,652,610,339 bytes and `git ls-files runtime` returns 0. A text-only scan of JSON/Python/Markdown/TXT/CSV/YAML/TOML found 596,414 64-hex tokens; 80,626 occurrences matched 224 unique temp-file hashes across 10,020 file instances. No exact root-temp directory names were found in that text scan. PDF, XLSX, database dump, certificate/key and other non-text runtime files were not read, and no persistent manifest was written. Types in root temp include JSON/PDF/XLSX evidence, `.key`/`.pem`, database `.dump`/`.lock`, PKI/timestamp `.bin`/`.tsq`/`.tsr`, and Python files. Some contain files written on 2026-09-30. All 55 remain `KEEP`: duplicate content and lack of exact directory-name references do not establish safe deletion, and non-text/unscanned references remain possible. `ARCHIVE=0`, `SAFE_DELETE=0`. This is not deletion authorization. The prior `.tmp/` count was 2,560 directories plus 5 files; current test output remains project-local. Earlier OS Temp residue with project test prefixes totals 145,001 directories; two Midea groups (29 files/9,291,709 bytes and 6 files/1,395,789 bytes) were copied into `runtime/company-research/` and verified, but external originals remain. Cleanup calls were refused by the execution policy; this run did not use another tool to bypass it.
- A bounded P4 metadata-only follow-up found the generic basename `.pytest-tmp` at `runtime/.pytest-tmp`: 12 directory entries and 14 JSON/XLSX files. This is a basename collision, not a match to any randomized temp-root ID. None of the 14 files has a same-relative-path counterpart under the project-root `.pytest-tmp`, and no root-temp candidate shares both extension and byte length, so no direct byte-identical copy is possible. ZIP central-directory member names were checked for 1,708 root-temp and 5,933 runtime XLSX files: 6,632 were readable with zero temp-directory-name matches; 1,009 could not be read as ZIP directories and remain unverified. No archive was decompressed; no XML, cell, PDF, dump, key/certificate body was read. P4 remains content-unverified; all 55 roots stay `KEEP`, `ARCHIVE=0`, `SAFE_DELETE=0`.
- The current working tree still contains 35 user-deleted tracked workbook/manifest files. They were neither restored, staged, nor included in this audit's source edits. No project-created test artifact was written outside the repository root in this run.
- `action=no_order`; M4 remains parked for R2, M6 not started, Strict PIT not proven, and M7 user acceptance not passed.

## 2026-09-30 Scoped Evidence-stop Adjudication — Current

This read-only adjudication supersedes earlier current-status paragraphs in this file for blocker classification only. It does not rewrite the immutable v13 baseline, valuation diagnostics, source artifacts, event watermarks, or product workbook. Reviewers audited only the retained, hash-bound public-source set and stopped repeat searches; this is not a claim that no other public material exists.

Current research classifications for `000333 / 600887 / 601088` are respectively `A0/B6/C0/D4`, `A0/B5/C2/D1`, and `A0/B3/C3/D1`. Research A blockers are now `0/3`: Yili remains low-confidence `CONDITIONAL_VALUATION_READY`; Midea and Shenhua current cases are `INSUFFICIENT_PUBLIC_EVIDENCE`, not valued. Their v13 baseline cards remain `BASELINE_PARTIAL / VALUATION_NOT_READY`.

## 2026-09-30 Earlier GitHub CI and Canonical Workbook Handoff (Superseded)

Commit `36c187ff0519e3d75a541908473c693895452862` is on `main`. GitHub Actions run `36655599773` passed both `offline-core` and `postgres-integration`. The preceding run exposed three tests that reached the Windows-only file-sharing guard on Ubuntu. One test is now explicitly Windows-only; two mocked partial-replacement recovery tests inject a no-op guard and remain runnable cross-platform. The focused Windows publisher test file passed `12` tests locally.

The exact 139-module CI list was also attempted in the current Windows checkout: `1154 passed, 30 skipped, 6 failed`. Five failures require root-level workbook/manifest files that are currently absent as 35 uncommitted tracked deletions in this local checkout; the sixth is a local subprocess GBK decoding failure. Those deletions were not restored or included in the commit. The pushed GitHub run, against the committed repository contents, is green.

The WPS canonical workbook still has SHA-256 `849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`, size `13,297,154` bytes, and local last-write time `2026-09-29 02:32:32`; its current quote pointer remains `2026-09-28`. It was not opened for writing. Research state changed, but the configured workspace dependency tree does not contain the required `@oai/artifact-tool`; spreadsheet policy prohibits substituting another workbook library. Consequently the new Yili conditional research valuation and 2026-09-29 quote are not yet visible in Excel. Quote-day `ModelValidity` remains unestablished because SCP010/011's CNY 20bn maturity outcome is evidence-stopped; no current `PriceBridge` or actionable Decision Review exists. No replacement workbook was created. `action=no_order`.

- **Midea:** the 2026-06-30 ordinary-share denominator is a scoped `D1 / EVIDENCE_STOP`. CNINFO H1 filing `1225531404` discloses 7,613,438,907 issued shares and treasury-stock book value, but not the complete share count by treasury/employee-plan use. A single disclosed 68,679,031-share repurchase cannot bound all treasury shares; weighted-average EPS shares and the verified 2026-09-29 denominator cannot be substituted. Reopen only on a new official date-matched disclosure of all relevant share counts and definitions. The existing applicability-v3 artifact retains its earlier A1 diagnostic and is not rewritten.
- **Shenhua:** the current acquisition-perimeter through-cycle attributable-profit input is a scoped `D1 / EVIDENCE_STOP`. Reorganization report `1224979750` confirms recent acquired earnings but does not bridge final scope, associate interests, eliminations, tax, minority interests and financing to a comparable through-cycle parent-profit range. A bounded CNINFO query for the exact 2026-09-30 date returned zero records through about 07:11 +08; the SSE page returned only a generic shell with an old generation date, and the issuer site could not be checked because TLS failed. This delta did not observe a reopen trigger and does not establish full-day coverage. Stop rereading the same acquisition and cycle files; reopen only on new official evidence capable of completing that bridge and calibration. The shared-model `NOT_READY` diagnostic is preserved as historical input validation, not promoted to an estimate.
- **Yili quote date:** SCP010/011's CNY 20bn maturity outcome is a separate quote-day `EVIDENCE_STOP`. CNINFO returned zero rows for exact-issuer/date queries at 01:00 and 07:12 +08; an exact-date SSE issuer query returned zero records at 07:11 +08. Retrieval clocks are local and these bounded snapshots do not establish full-day or cross-channel coverage, nor payment, rollover, default, or post-maturity cash/debt. Therefore quote-day `ModelValidity` remains unestablished, `PriceBridge=null`, and `Decision Review=NOT_ASSESSABLE`; only a later eligible official settlement/refinancing or balance disclosure reopens it. Yili's 2026-06-30 conditional research valuation is unchanged.

Canonical Excel remains unchanged: `@oai/artifact-tool` is unavailable and no current 2026-09-29 workbook candidate exists. An adversarial review found a time-of-check/time-of-use window after the publisher's source-hash check. The publisher now acquires a Windows file handle that denies write sharing before replacement, revalidates the source hash under that guard, and holds write-denying guards while verifying the installed candidate and cleaning the displaced source. Partial `ReplaceFileW` failure restores a displaced original when possible; rollback failure preserves the actual recovery artifacts and reports their paths. The focused publisher, preservation, quote-binding, and monotonic-publication regression set passed `36` tests with three existing openpyxl named-range deprecation warnings. The exact 139-file offline-core suite passed `1167 passed, 23 skipped, 3 warnings` under the system Python 3.13 environment with UTF-8 I/O and a short unique pytest temporary path. No canonical write or publication was attempted. Do not substitute another workbook library or touch the eight historical staging files. `STRICT_PIT=NOT_PROVEN`, M6 remains preflight-only, M7 acceptance is pending, total Goal remains in progress, and `action=no_order`.

## 2026-09-30 Yili Prospective Case Follow-up — current

The registered case `prospective-600887-20260927-v2` now has a distinct,
post-registration shared-application research run. Its new input descriptor
binds the v13 registration receipt and immutable baseline snapshot, the
existing Yili readiness review and prior shared result, and hash-bound official
issuer sources. The descriptor SHA-256 is
`545c52ae909e842dc2d4aca55d091dfaa3c087c4a96937525cf0f767b0933b76`; issuer
identity was `VERIFIED`. The shared residual-income model was executed again
for this follow-up, producing low-confidence research-only Bear/Base/Bull
values of CNY 8.0476 / 11.0234 / 13.1335 per share.

This is a follow-up valuation state, not a rewrite of the baseline: the v13
snapshot remains `BASELINE_PARTIAL / VALUATION_NOT_READY`, and
`STRICT_PIT=NOT_PROVEN`. The run has no quote. Quote-date `ModelValidity` is
`NOT_ESTABLISHED`; the service diagnostic bridge is `PENDING_EXTERNAL_DATA`
with no current price, so there is no admitted `PriceBridge` and
`Decision Review=NOT_ASSESSABLE`. Dividend sustainability remains
`DATA_INCOMPLETE / UNKNOWN`; the cash range is a haircut proxy, not certified
distributable cash. The artifact and replay test are
`docs/current/600887-prospective-case-followup-20260930.json` and
`tests/test_600887_prospective_case_followup.py`. No workbook was changed;
`action=no_order`.

The replay audit corrected one inherited arithmetic field without rewriting
the pinned 2026-09-29 readiness review: exact Base proxy cash is CNY 7.9149bn,
so headroom after the CNY 7.71694001374bn policy-floor stress amount is CNY
0.19795998626bn. The prior artifact used the rounded display value CNY 7.915bn
and overstated headroom by CNY 0.0001bn; valuation results and readiness are
unchanged.

Validation on 2026-09-30: the CI-defined offline Core Research Gates list plus
the Yili follow-up and prior shared-valuation binding tests passed with
`1156 passed, 23 skipped, 2 warnings` across 141 test files. The focused
follow-up/shared-binding/issuer-identity set passed `37` tests. The two
warnings are existing openpyxl `create_named_range` deprecations in workbook
preservation tests.

Latest continuation verification after the 2026-09-30 model-route correction:
the exact 139-file offline-core list passed `1158 passed, 23 skipped, 3
warnings`; the focused routing/applicability/identity/architecture set passed
`66` tests. The three warnings are existing openpyxl named-range deprecations.

## 2026-09-30 Midea Post-Period Denominator and June Valuation Blocker — historical review, superseded for current classification by the 2026-09-30 scoped Evidence-stop adjudication

The latest target-date share denominator is verified from official HKEX
disclosures and source hashes in
`docs/current/track-b-midea-share-denominator-review-20260928.md`: as of
2026-09-29, 7,629,915,859 A/H shares were issued, 184,532,963 were issuer-held
treasury shares, and 7,445,382,896 ordinary shares were outstanding excluding
treasury. The source became available after the 2026-09-29 close and verifies
that later date only; it cannot close the 2026-06-30 denominator blocker or be
backdated into the 2026-09-29 quote decision or baseline v13.

Midea's 2026-09-29 denominator is verified, but it cannot be backdated to the
2026-06-30 equity basis. The overall classification remains `A1/B6/C0/D3`:
the single A blocker is the unbounded 2026-06-30 ordinary-share denominator,
not model authorization. The registered FCFF route is
`FCFF_NOT_APPLICABLE_FOR_CURRENT_PUBLIC_SCOPE`; the generic profile now
explicitly authorizes the shared residual-income alternative while keeping
FCFF as default. No Midea valuation was run because the date-matched per-share
denominator is unresolved. The three public-scope stops remain limited to the
FCFF path; do not repeat those disclosure searches for residual income. The
route change applies only to new prospective runs and does not rewrite v13.
The current applicability output is `runtime/company-research/midea-valuation-applicability-20260930-v3/evidence.json`, SHA-256 `aebcaf46591cc6814e2e40e117665edb8d58fe3fd9ff6423db949a3a5d750973`.

## 2026-09-30 Yili Official Exchange-Index Recheck — current

The first three pages of the official SSE issuer-disclosure index contain 30
records dated 2026-06-17..2026-09-29. Hashes and the bounded search result are
recorded in `docs/current/track-c-yili-short-term-financing-redemption-20260929.md`.
The index shows the July issuance of SCP010/011 and SCP012-014, followed by a
September 29 redemption notice for SCP012-014 only. It contains no settlement,
rollover or default notice for SCP010/011. This does not prove non-payment or
default and does not establish complete event coverage. The CNY 20bn outcome
and post-maturity cash/debt bridge remain unverified; Yili's quote-day
`ModelValidity` is not established, `PriceBridge=null`, and
`Decision Review=NOT_ASSESSABLE`. No valuation or workbook state changed;
`action=no_order`.

## 2026-09-30 Midea Official Post-Period A-Share Movement — partial, superseded

A targeted CNINFO exact-issuer query for 2026-08-30..2026-09-29 returned four
announcements on one complete page. Two new official originals bind distinct
A-share movements: `1225544482` reports 15,772,385 existing shares transferred
on 2026-09-03 from the issuer's repurchase account to the 2026 A-share employee
plan account; `1225544342` reports 99,797,967 shares cumulatively bought under
the separate 2026 capital-reduction program through 2026-08-31. Original PDF
hashes, exact page references, official URLs, the complete query-window
receipt and limitations are recorded in
`docs/current/track-b-midea-share-denominator-review-20260928.md`.

These counts have different source programs, uses and dates. They cannot be
netted with one another or with the 7,448,597,984 interim-dividend base
(7,628,798,092 total shares less 180,200,108 repurchase-account shares on
2026-08-29). A target-date 2026-09-29 A/H issued-share and all-use treasury
share bridge was still not admitted at this intermediate review; September
repurchases after 2026-08-31, other plan-held share counts and target-date
H-share movements remained open. Those gaps were subsequently closed for the
2026-09-29 share-count basis by the full A/H reconciliation above. This partial
review remains historical evidence; `action=no_order`.

## 2026-09-29 Shenhua Scenario Envelope and Shared Model Gate — historical review, superseded for current classification by the 2026-09-30 scoped Evidence-stop adjudication

The execution-correction review now has a source-bounded operating-driver
envelope for 601088 rather than another search of the same acquisition filing.
Bear endpoints, 2017-2025 medians (with 2024 restated as disclosed in the 2025
annual report), and Bull endpoints are recorded per variable in
`docs/current/track-b-execution-correction-20260929.md`. They are independent
period anchors, not jointly observed cases or a normalized-profit forecast.
2019-2020 power-price observations are excluded for the documented scope break;
2026H1 post-acquisition segment results remain a separate current-period anchor.
The 2014-2025 source series is hash-pinned but remains period evidence only,
`financial_scope_approved=false`.

A read-only call to `CyclicalNormalizedValuationModel` used the June 30 share
count (21,689,434,304) and three self-produced unit-cost sensitivity anchors.
It returned `not_ready` with Bear/Base/Bull values all `null`. The exact
6 missing model fields are retained in the stage memo; the three normalized
parent-profit inputs and trough-profit input trace to one research A root cause:
no comparable acquisition-adjusted, pre-tax parent-attributable operating-profit
bridge across the cycle. B-class tax, working-capital, discount/growth,
resource-life and cost uncertainties have explicit scenario anchors and are not
additional A blockers. Maintenance CapEx and current attributable net cash
remain unadmitted model inputs. No normalized-profit, maintenance-capex or
attributable-net-cash input was inferred from segment profit, cash-flow proxies
or target-company aggregates.

The shared model now preserves supplied scenario assumptions and the exact
missing-input list on its early fail-closed path, so a blocked run remains
diagnosable. It also rejects inverted Bear/Base/Bull per-share values while
preserving their arithmetic diagnostics. `tests/test_cyclical_normalized_valuation.py`: 10 passed. The exact
139-file `offline-core` selection in `.github/workflows/core-research-gates.yml`
passed with an isolated pytest temp directory: 1,154 passed, 23 skipped, 2
existing deprecation warnings. An initial repeat without `--basetemp` failed in
test setup because Windows denied access to the shared pytest temp root; it is
not counted as a test failure. Full-repository tests and PostgreSQL integration
were not run in this update.

No share-price bridge or decision review was produced for Shenhua. The three
case readiness states remain unchanged; canonical Excel, baseline v13, event
watermarks, PIT registration, production and `action=no_order` are unchanged.

## 2026-09-29 Bounded Issuer/Event Evidence Review — current

Four additional Yili filings were obtained from CNINFO as official PDF originals,
signature-checked and SHA-256 verified under
`runtime/company-research/yili-official-event-review-20260929/`. They resolve
three distinct event groups: the employee plan bought existing shares on-market
(no new issuance; the filing does not establish the plan's funding source); an approved CNY 1-2bn buyback
with 0.40%-0.80% estimated cancellation is a bounded future scenario, not an
executed capital change; and a new EUR 30m subsidiary guarantee is a contingent
credit/liquidity scenario, not a realized loss or automatic equity deduction.
The creditor notice duplicates the same buyback event and is not counted twice.

The quote-day hard gate remains open: no official evidence found for settlement
or rollover of the CNY 20bn short-term notes due 2026-09-29 or a post-settlement
cash/debt bridge. The separate 2026-09-29-dated CNY 25bn redemption notice
concerns the 2026-09-24 maturities; under the date-only availability rule it is
not used for the 2026-09-29 close. The 2026-09-29 close of CNY 27.24 is verified,
but quote-day `ModelValidity` is not established, `PriceBridge` is null and the
price review remains `NOT_ASSESSABLE`. No event watermark or canonical workbook
was advanced.

For Shenhua, the retained CNINFO restructuring report's physical pages
1281-1322 contain audited simulated financial statements for 12 target
companies for 2023, 2024 and 2025 January-July. This corrects any claim that
target-company historical statements are absent. The company-level periods
cannot be mechanically aggregated to current listed-company attributable
earnings because of disposal/pro forma adjustments, differing acquisition
stakes and consolidation/equity-method treatment, non-recurring-profit
definition differences, and absent through-cycle current-perimeter attribution.
The A blocker remains one narrowly defined current-perimeter mid-cycle
attributable-earnings bridge; no spurious scenario valuation was emitted.

This review did not change the three-case valuation statuses: 000333 remains
`VALUATION_NOT_READY` (A1), 600887 remains low-confidence
`CONDITIONAL_VALUATION_READY` for its 2026-06-30 research basis (A0), and 601088
remains `VALUATION_NOT_READY` (A1). The separate 600887 quote-day gate remains
open. Canonical Excel remains unchanged because no valid quote-day review was
produced and the approved spreadsheet runtime is unavailable. `action=no_order`.

## 2026-09-29 Issuer Identity Gate Scope Correction — current

Independent review found that the shared gate did not bind ResearchCase next_events
references to the case issuer, and the run input allowed facts_payload.symbol to
replace rather than independently agree with typed FinancialFacts.symbol. Both are
corrected. ResearchCase.symbol, run symbol, typed facts symbol, and any supplied
payload symbol must agree; source id + SHA-256 must resolve to an official issuer
descriptor whose CNINFO/HKEX identity matches the committed registry; an explicitly
mismatched issuer on a hash-bound event source is rejected before model execution.
Existing RunSpec case/facts constructor guards remain fail-closed and identify the
REJECTED_ISSUER_MISMATCH classification.

The targeted identity/shared-valuation/PriceBridge/RunSpec set passed 57 tests. The
exact offline test selection from the GitHub workflow passed locally with UTF-8
process settings: 1147 passed, 23 skipped, 2 warnings. An unfiltered repository
run exposed four legacy M1 package tests whose local filing descriptors lack
official issuer identity metadata; they remain fail-closed and are outside the
Core Research Gates selection. The full unfiltered suite was not rerun after the
test-harness encoding and constructor-boundary corrections.

This gate validates issuer identity metadata against the committed registry and
binds it to the evidence reference hash. It does not independently parse original
PDF bytes or prove that the caller-provided descriptor's identity fields were
truthfully extracted. It establishes consistency of declared metadata, not
authenticity of the original issuer document; source-byte identity extraction
remains an upstream trust boundary. No research baseline, PIT registration, canonical
workbook, quote pointer, watermark, or valuation result changed.

## 2026-09-29 Post-Close Public Evidence Update — current

The latest completed official exchange session is now 2026-09-29. The bounded
collector retained Tencent/Sina quote responses and the applicable exchange
calendar. All three registered cases replayed as `matched_close`: 000333 CNY
81.66, 600887 CNY 27.24 and 601088 CNY 47.30. Bundle SHA-256 is
`c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395` at
`runtime/quote-sessions/20260929T080056442563Z/bundle.json`. The read-only
canonical product publisher verified the same bundle with frozen baseline v13
and returned `VERIFIED_IN_MEMORY_ONLY`, all three prospective symbols,
`quote_as_of=2026-09-29`, and `workbook_modified=false`. Capture process time
is not independently attested; this does not establish strict PIT.

Bounded CNINFO snapshots around 16:02-16:03 +08 returned the already-known
Midea notice `1225582141` (one row), Yili notice `1225584526` (one row), and
zero rows for Shenhua. No new announcement ID was found. These are query-time
snapshots, not proof of full-day or multi-channel coverage, and they did not
advance formal watermarks. Midea remains `INCOMPLETE`; Yili and Shenhua's
formal coverage remains through 2026-09-27. Yili `1225584526` has date-only
availability and remains conservatively unavailable until 2026-09-30; it is
not applied to a 2026-09-29 conclusion. Parallel bounded scans created
duplicate runtime receipts; they are preserved and are not counted as
independent new events. Representative receipt bindings are:

| Case | Runtime scan receipt | SHA-256 |
| --- | --- | --- |
| 000333 | `runtime/prospective-public-event-2026-09-29/gapfill-000333-20260929T080238767578Z/scan-receipt.json` | `56fcd8add54b82cfff62128cc5afe24188e3e8e9f1ba64d5071b1221b2285b5c` |
| 600887 | `runtime/prospective-public-event-2026-09-29/gapfill-600887-20260929T080255204325Z/scan-receipt.json` | `afe6dcb41be2941ded45e7eb9d7526bf8d29739771f4fdcabf856669804ae25a` |
| 601088 | `runtime/prospective-public-event-2026-09-29/gapfill-601088-20260929T080309644951Z/scan-receipt.json` | `91263463ee0bdb042dd08a06523e06957d72064cb261bee1605f4855b2d3b549` |

A final bounded 600887 query at 23:59:36 +08 for the 2026-09-29 announcement
date returned the same single notice `1225584526`; no additional CNINFO item
was present in that retrieval snapshot. Its index SHA-256 is
`e811ea059ce561aaff22e3e4e60ab6645d42b729d2e7f14d70aaec733ce1747d`, and its
receipt SHA-256 is
`0a32b0fed3862239f452c2685cda99b2492cf957d7cd09c38872215247b19d69`. The
receipt and raw page are retained under
`runtime/prospective-public-event-2026-09-29/gapfill-600887-20260929T155936776833Z/`.
This remains a single-channel, retrieval-time snapshot with an unattested
process clock; it neither proves note settlement nor advances event coverage.

The bounded Midea ordinary-share denominator review retains its single A
blocker. The 2026H1 report states 7,613,438,907 issued shares as of June 30
(6,962,590,407 A shares and 650,848,500 H shares), but does not disclose the
employee-incentive treasury-share count. The 7,448,597,984 share figure in
2026-08-29 announcement `1225531407` is a dividend calculation base, not the
2026-09-29 valuation denominator; the announced total share count does not
prove a target-date upper bound. Report SHA-256 is
`576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`, and
announcement SHA-256 is
`669fcc91ff5c791d7d71d860a2153324d81c8fb59af01e0d47574a818d0e0feb`.
No defensible low/base/high denominator range can be formed from these
materials. This review closed the evidence available through 2026-08-29; the
new 2026-09-03 CNINFO share-transfer and buyback notices are separately
reviewed in the 2026-09-30 update above and the dedicated denominator review.
Do not repeat the 2026-08-29 filing set; continue only with new official
issuer/exchange evidence that reconciles target-date A/H issued shares, all
treasury-stock uses, and subsequent issuance/cancellation/buyback/vesting.

Yili remains `CONDITIONAL_VALUATION_READY` at low confidence, with central
Bear/Base/Bull CNY 8.05/11.02/13.13 per share and full sensitivity CNY
7.10-15.03. No hash-bound, source-complete event review through the 2026-09-29
quote date has resolved all candidate and channel-coverage conditions, so no
valid `ModelValidity` or current `PriceBridge` was produced. `PriceAttractiveness`
and `Decision Review` remain `NOT_ASSESSABLE`; the scenario/price arithmetic is
not a valid current `WAIT` or a buy/sell conclusion.

The in-memory product validation did not change the canonical workbook. Its
physical SHA-256 remains
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`, and the
workbook pointer remains at quote date 2026-09-28. The approved
`@oai/artifact-tool` is unavailable in this workspace; no alternate spreadsheet
library or replacement workbook was used. The verified 2026-09-29 quote is
therefore not yet visible in Excel.

```text
LATEST_VERIFIED_SESSION = 2026-09-29 / 000333=81.66; 600887=27.24; 601088=47.30
QUOTE_BUNDLE_SHA256 = c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395
PRODUCT_VERIFY_ONLY = PASS / THREE_PROSPECTIVE_CASES / WORKBOOK_UNMODIFIED
EVENT_SNAPSHOTS = CNINFO_ONLY / NO_NEW_IDS / NO_FORMAL_WATERMARK_ADVANCE
600887_MODEL_VALIDITY = NOT_ESTABLISHED_THROUGH_2026-09-29
600887_PRICE_BRIDGE = NOT_PRODUCED / DECISION_REVIEW_NOT_ASSESSABLE
CANONICAL_EXCEL_UPDATED = NO / APPROVED_SPREADSHEET_DEPENDENCY_MISSING
action = no_order
```

## 2026-09-29 22:09 +08 PriceBridge review blocker propagation

Corrected `bridge_with_quote` so `ModelValidity.blockers` are retained alongside
caller blockers for READY, PENDING_EXTERNAL_DATA, INVALID and STALE_MODEL
results. `VALID` may still carry explicit risk-monitor/follow-up review items;
the bridge must not erase them. A regression builds an actual
`MATERIAL_RISK_MONITOR` review, confirms the model remains VALID, then verifies
the review blocker survives in the READY bridge. READY means the model and quote
can be compared, not that decision review, human approval or trading admission
has passed.

Verification: `tests/test_price_bridge.py` plus
`tests/test_event_materiality.py`: 28 passed. The offline-core test list from
`.github/workflows/core-research-gates.yml` passed locally with an isolated
pytest base directory and UTF-8 process settings: 1148 passed, 23 skipped, 2
existing openpyxl warnings. The full repository suite was not completed: its
initial run stopped making progress near 89%; a fail-fast attempt exposed
`PermissionError` on the user-level `pytest-of-Ming` temp root. No company
valuation state, quote-day validity, workbook, PIT record, event watermark,
production state, or `action=no_order` changed.

## 2026-09-29 Execution-Correction Continuation — current research state

The execution-correction stage is the active priority. It does not change the
frozen prospective baseline v13, formal event watermarks, strict-PIT status,
or the M2-M7 graduation gates. Independent R1 reviews cover all three cases.

| Symbol | Current A/B/C/D | Valuation disposition | Actual remaining A blocker |
|---|---:|---|---|
| 600887 | 0 / 5 / 2 / 1 | `CONDITIONAL_VALUATION_READY`, low-confidence research-only; shared residual-income scenarios CNY 8.05 / 11.02 / 13.13, full sensitivity CNY 7.10-15.03 | None for the 2026-06-30 research valuation. A separate quote-date event/`ModelValidity` gate remains open; no `PriceBridge`, `PriceAttractiveness`, or assessable `Decision Review`. |
| 000333 | 1 / 6 / 0 / 3 | Registered FCFF scope `MODEL_NOT_APPLICABLE`; shared residual-income is explicitly profile-authorized but the case remains `VALUATION_NOT_READY` | Exact 2026-06-30 share denominator is not bounded; verified 2026-09-29 shares are not backdated. No per-share valuation was run. |
| 601088 | 1 / 3 / 3 / 0 | No valuation result; normalized cyclical model remains not ready | Acquired assets' current-perimeter mid-cycle attributable earnings contribution is unbounded. Legacy coal/electricity/transport ranges and disclosed H1 facts remain scenario inputs, not standalone company valuation blockers. |

Yili's bounded CNINFO window yielded 10/10 candidate dispositions
(`A=1/B=2/C=7/D=0` for the **2026-09-29 quote-validity review only**). This
does not advance a formal watermark or establish issuer-IR/exchange-channel
completeness. Announcement `1225584526` is unavailable for the September 29
close under the conservative date-only rule; the CNY 20bn note due that day
still lacks a verified redemption/rollover and post-payment cash/debt bridge.
The readiness JSON separates the research scenario from arithmetic-only price
comparison and has `price_bridge=null`.

Midea's 2026-09-29 A/H denominator is verified but does not close the
2026-06-30 model-date share denominator A blocker. The explicit residual-income
alternative is profile-authorized; its three D items remain stops for the inapplicable FCFF scope,
not reasons to keep searching the same filings. Reopen those only if a new
official disclosure supplies a finance-business carve-out, a material
consolidation bridge, or project-level CapEx facts relevant to a newly admitted
model.
Shenhua's old D stop for lacking a named transaction report is superseded by
the retained CNINFO `1224979750` restructuring report, SHA-256
`533bc24a80aeb1fbf2357218c5c19825cb0ab23176eb7d25d8ecd2d1f1256703`; the
runtime file has no retained manifest and is not in a public clone. Its one
full-year plus seven-month pro forma evidence does not close the cycle A
blocker; do not annualize or merge target aggregate profit into attributable
group profit.

The issuer identity gate is already integrated and fails closed on
symbol/source-issuer mismatches; regression coverage is in
`tests/test_issuer_identity_gate.py` and the shared Yili binding test. The WPS
canonical workbook remains SHA-256
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`, with the
quote pointer at 2026-09-28. The approved `@oai/artifact-tool` package is
unavailable; no alternative spreadsheet library or competing workbook was
used.

```text
CURRENT_STAGE = STAGE-EXECUTION-CORRECTION-CONTINUATION
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
INITIAL_ASSISTED_USE = NOT_REACHED
BASELINE_V13 = FROZEN / 0_OF_3_FORMAL_BASELINE_PASSES
STRICT_PIT = NOT_PROVEN
BLOCKER_COUNTS = 000333_A1_B6_C0_D3; 600887_A0_B5_C2_D1; 601088_A1_B3_C3_D0
VALUATION_READY = 0/3
CONDITIONAL_VALUATION_READY = 1/3 / 600887 / LOW_CONFIDENCE
ISSUER_IDENTITY_GATE = FAIL_CLOSED / RUN_CASE_FACTS_PAYLOAD_SOURCE_EVENT_SCOPE / SOURCE_IDENTITY_METADATA_UPSTREAM_BOUND
IDENTITY_FOCUSED_REGRESSION = 57_PASSED / prior identity and shared-binding selection
PRICE_BRIDGE_MATERIALITY_REGRESSION = 28_PASSED
OFFLINE_CORE_RESEARCH_GATES = 1148_PASSED / 23_SKIPPED / 2_WARNINGS
FULL_REPOSITORY_TESTS = INCOMPLETE / local pytest temp-root permission and stall
CANONICAL_EXCEL_UPDATED = NO / SPREADSHEET_DEPENDENCY_UNAVAILABLE
NEW_EXCEL = 0
action = no_order
```

### Historical Continuous Public Research Snapshot — superseded

The following dated snapshot predates and is superseded by the execution-correction continuation above. It remains historical context only and does not authorize the former continuous public-research task queue. It does not rewrite any frozen research baseline or evidence receipt.

#### Repository and verification

The local checkout is `main` at `a25f58a7230752d7a485b74f6acdb5b4ee16e0b7`, with a clean worktree before this documentation update. Direct `git fetch` and `git pull --ff-only` could not connect to GitHub on port 443. GitHub REST independently returned the same `origin/main` SHA, and its check-runs for this SHA report `offline-core=success` and `postgres-integration=success` (run `36542831846`). No remote change was omitted at this SHA; no force update or branch change was made.

#### Track status

```text
CURRENT_STAGE = STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH
STAGE_STATUS = STAGE_ACTIVE
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
PROSPECTIVE_REGISTRATION = v2 / receipt 8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5
PROSPECTIVE_BASELINE = snapshot-v13 / ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5 / FROZEN
BASELINE_COMPLETE = 0/3 / all published cards BASELINE_PARTIAL; do not rewrite v13
STRICT_PIT = NOT_PROVEN / registration and snapshot build times are unattested
DESCRIPTIVE_RESEARCH_CARD_FIELDS = 3/3 / R1 reviewed; Yili cash-coverage supplement linked below
DESCRIPTIVE_RESEARCH_CARDS != FORMAL_PROSPECTIVE_BASELINE_OR_STRICT_PIT_PASS
LATEST_VERIFIED_SESSION = 2026-09-29 / 000333=81.66; 600887=27.24; 601088=47.30 / matched close
QUOTE_BUNDLE = runtime/quote-sessions/20260929T080056442563Z/bundle.json / c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395
NEW_EVENTS_PROCESSED = 0 / 2026-09-29 bounded CNINFO snapshots only; formal watermarks unchanged
CANONICAL_UPDATED = NO / pointer remains 2026-09-28; approved @oai/artifact-tool unavailable
NEW_EXCEL_CREATED = 0
SAFE_PUBLIC_RESEARCH_REMAINING = YES
M4_R2 = PARKED_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED
M7_R5 = NOT_PASSED
action = no_order
```

Track B remains open without upgrading any valuation or decision state:

- `000333`: six verified FY2025/2026H1 facts are in frozen v13. The ordinary-share denominator remains an A blocker; the company-level FCFF scope is `NOT_APPLICABLE_FOR_CURRENT_PUBLIC_SCOPE` because financial-service perimeter, industrial cash/debt, CapEx split and equity bridge are not bounded. This blocks FCFF valuation, not descriptive research. The September 28 EGM notice is a meeting notice, not evidence that a share cancellation or distribution occurred.
- `600887`: six 2026H1 facts remain bound to CNINFO `1225511409`. Its 2026-06-30 ordinary-share basis of `6,325,360,667` is supported by that report; it does not establish later share changes or payment-date shares. The shared residual-income result remains low-confidence `CONDITIONAL_VALUATION_READY` (`8.05/11.02/13.13` CNY Bear/Base/Bull), while dividend sustainability is `DATA_INCOMPLETE / UNKNOWN`. `ModelValidity` through the 2026-09-29 close is not established, so current price review remains `NOT_ASSESSABLE`. Notice `1225584526` is conservatively usable no earlier than 2026-09-30 and says nothing about the September 29 CNY 20bn maturity outcome. A separate post-cutoff review ([cash-coverage review](docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md), SHA-256 `7264384c47239cb0607dab5b0496734409718e55692f5af4100b69dc905d474c`) records FY2021-FY2025 payout and cash-coverage history: FY2022 coverage after reported long-lived-asset purchases was `1.023x`, while the 2025 parent-level partial-cash proxy covered calendar-year shareholder payments by `1.074x` before omitted uses. These are limited historical proxies, not sustainable distributable cash. The v13 phrase “no interim distribution” is scoped to the reviewed 2026 interim period; it does not negate the FY2025 interim `CNY 0.48/share` payment in December 2025 or the `CNY 0.90/share` final payment in June 2026. This supplement remains a dated follow-on, not a v13 baseline rewrite or strict-PIT evidence.
- `601088`: six admitted FY2025/2026H1 facts remain in v13. Normalized earnings across the current acquisition perimeter remain the valuation A blocker. The bounded target-level public-document path is `EVIDENCE_STOP`; reopen only on a new named official report. Minor accounting residuals are not promoted to hard blockers.

Track C found no new announcement ID in the retained September 29 bounded snapshots; they do not establish complete cross-channel coverage and did not advance formal watermarks. The existing Yili price-validity gap is not closed. An auxiliary read-only reviewer reported an unreceipted query attempt for an older Yili window; it is not admitted as a source-complete event scan or a basis to advance a watermark. Do not repeat that query merely to recreate the same result; any future gap-fill must bind the exact query, issuer identity, response, source originals and candidate dispositions.

Track A has already processed the September 29 completed session. Do not rerun that daily update. Track D did not publish the new quote to Excel: the sole pointer and workbook hash still refer to September 28. The dependency loader returned bundled runtimes, but `@oai/artifact-tool` is absent from the available package set; under spreadsheet-tooling rules, no alternate workbook library, candidate workbook or in-place write was used. This is a product publication gap, not a reason to stop public research.

#### Interruption audit

```text
A active prospective case can be researched: YES
B legal public-evidence gap remains: YES (Yili price-validity coverage and descriptive baseline gaps)
C new material public event accepted this run: NO
D new completed session after 2026-09-29: NO (the 2026-09-29 session was already processed)
E formal prospective baseline remains incomplete: YES (0/3; immutable v13 retained)
F PIT/decision-consistency work can continue: YES, forward-only; no historical timestamp repair
G product projection can use new public facts: YES, but Excel publication is tool-gated
H all active cases at Evidence Stop: NO
```

At the time of this historical snapshot, `STAGE_STATUS=STAGE_ACTIVE`, not idle and not blocked by R2/R3/R5/R6. Its next-work sentence was contemporary guidance then, not the current task queue. The active execution-correction scope and latest dispositions are documented above. The canonical workbook and all human records remained untouched in that snapshot.

## 2026-09-29 Execution Correction — prior closeout snapshot

This phase reclassified the registered 000333, 600887 and 601088 research cases
into A/B/C/D blocker groups and produced a bounded blocker burn-down. The audit
baseline at entry was `main@24ec94bff754b4139169cf79f9bbc1f356c0c71b`, matching
`origin/main`.

600887's retrospectively reconstructed A blockers moved from 2 to 0: the
2026-06-30 share denominator is supported by the retained CNINFO half-year
report, while the dated denominator-to-quote difference is disclosed as a
scenario/caveat. The shared `residual-income-equity-shared-v1` model was run
with explicit low-confidence Bear/Base/Bull assumptions. It yields CNY
8.05/11.02/13.13 per share at the central sensitivity point and a full grid
range of CNY 7.10-15.03, versus the verified 2026-09-28 close of CNY 27.03.
Research disposition is `CONDITIONAL_VALUATION_READY`. The current price
Decision Review is `NOT_ASSESSABLE`: valid-through-quote `ModelValidity` is not
established, so the earlier `WAIT` is not a valid current-price decision. This
is not a forecast, unique fair-value conclusion, sell signal or order.
Dividend sustainability remains `DATA_INCOMPLETE / UNKNOWN`; strict PIT
remains `NOT_PROVEN`.

000333 remains A=1, B=6, C=0, D=3: the ordinary-share denominator is the A
blocker; normalized ROE is a B scenario input based on a non-admitted proxy.
Its original consolidated FCFF is not applicable and no evidence-supported
substitute is ready. 601088 remains A=1, B=4, C=3, D=1; its current-perimeter
mid-cycle attributable earnings are not established and the bounded review of
identified target materials ended in `EVIDENCE_STOP`. The Shenhua CNY 2.577bn acquisition figure is a difference
between disclosures with different perimeters, not a reconciled cash shortfall.
Its three C-class items are non-blocking only for consolidated valuation.
Prior A/B/C/D counts for Midea and Shenhua were not recorded and are not
invented.

Issuer identity admission is integrated on local `main` at `24f4de3`. The
registered CNINFO/HKEX identity data is shipped as a package JSON resource,
keeping symbol-specific literals out of domain/application Python. Missing
hash-bound official issuer evidence blocks model execution; the frozen replay
now asserts that its unbound Moutai evidence produces no valuation. Focused
identity, architecture-boundary and replay tests passed (34 passed). The exact
workflow `offline-core` selection across 139 test files passed locally:
1,142 passed, 23 skipped, 2 openpyxl deprecation warnings. ACTUAL replay tests
that require ignored local evidence were skipped under the workflow's default
environment; this is not a successful ACTUAL evidence replay. The full
repository suite was not run. GitHub Core Research Gates run `36524898780`
passed both `offline-core` and `postgres-integration` for code commit
`8bf11cdba1b8cec1feb11c481855d69d6fb049ad`.

Canonical Excel state changed but was not published because the approved
workspace dependency `@oai/artifact-tool` is absent. The one WPS
workbook was not modified and no substitute workbook was created. The machine-
readable review and burn-down are indexed in `docs/current/README.md`.

```text
BASELINE_COMPLETE = 0/3 / frozen v13 unchanged
BLOCKER_CLASSIFICATION = 3/3
VALUATION_READY = 0/3
CONDITIONAL_VALUATION_READY = 1/3 / 600887
ISSUER_IDENTITY_GATE = INTEGRATED_LOCAL_MAIN_24f4de3 / FAIL_CLOSED / FOCUSED_34_PASS
CORE_RESEARCH_GATES_LOCAL = OFFLINE_CORE_1142_PASS_23_SKIP / 139_FILES
CORE_RESEARCH_GATES_GITHUB = 36524898780 / SUCCESS / BOTH_JOBS / FOR_8bf11cd
CANONICAL_EXCEL_UPDATED = NO / APPROVED_SPREADSHEET_DEPENDENCY_MISSING
NEW_EXCEL_CREATED = 0
STRICT_PIT = NOT_PROVEN
M6 = PREFLIGHT_ONLY / OPERATIONAL_NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-29 execution-correction follow-up (18:00 +08)

This entry supersedes only the quote-date, bounded Yili event-scan, and
Shenhua acquisition-report facts in the immediately preceding historical
handoff. It does not change baseline v13, any registered observation, formal
event watermark, valuation artifact, workbook, or total-goal status.

For Yili `600887`, the 2026-09-29 matched close is CNY 27.24 in the verified
three-symbol quote bundle
`runtime/quote-sessions/20260929T080056442563Z/bundle.json` (SHA-256
`c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395`). The
retained exact-issuer CNINFO gapfill for 2026-06-30..2026-08-26 returned 10/10
rows on one terminal page. Its index SHA-256 is
`4f2d018f82e0b9c23b1963b099264f847278dd407dc9622f388bf818b88ed81e`; its
scan-receipt SHA-256 is
`ca54e80b473a2fcb7dca88c5888c5485957e3c46fe08af8c98982bd9d2422332`. This
is a bounded CNINFO-only retrieval snapshot, not cross-channel completeness,
formal watermark advancement, or completed materiality disposition for every
candidate. Notice `1225584526` remains conservatively available on 2026-09-30,
so it is not used for the Sep 29 quote review. It verifies repayment of CNY
25bn of notes on Sep 24; the separate CNY 20bn notes scheduled to mature Sep
29 have no retained repayment/refinancing or post-redemption cash confirmation.
Consequently Yili remains `CONDITIONAL_VALUATION_READY`, but quote-date
`ModelValidity` is not established, `PriceBridge` is not emitted, and Decision
Review stays `NOT_ASSESSABLE`.

For Shenhua `601088`, the retained official restructuring report CNINFO
`1224979750` at
`runtime/company-research/shenhua-acquisition-2026-02/1224979750.pdf` has
SHA-256
`533bc24a80aeb1fbf2357218c5c19825cb0ab23176eb7d25d8ecd2d1f1256703`. Page
20 reports 2024 target-company adjusted attributable profit of CNY 9.428bn
(CNY 10.570bn excluding long-lived-asset impairment); page 555 gives
transaction pro-forma adjusted attributable-profit increments of CNY 7.889bn
for 2024 and CNY 3.382bn for Jan-Jul 2025. This supersedes the earlier
absence-of-a-named-transaction-report `EVIDENCE_STOP`. It does not close the
A blocker: this recent period does not establish current-scope mid-cycle
earnings, and must not be annualized or spliced onto the pre-acquisition
2014-2025 operating series as a cycle range. No Shenhua valuation is emitted.

Independent read-only reviews reconfirmed Midea `000333` share denominator
`A=1`: June 30 issued shares, the August dividend calculation base and
weighted-average EPS shares do not determine a Sep 29 ordinary-share
denominator or a defensible range. Do not substitute any of those values.

```text
BLOCKER_CLASSIFICATION = 3/3
A_BLOCKERS = 000333:1; 600887:0; 601088:1
CURRENT_VALUATION_READY = 0/3
CONDITIONAL_VALUATION_READY = 1/3 / 600887 / LOW_CONFIDENCE
601088_PRIOR_ABSENCE_OF_REPORT_D_STOP = SUPERSEDED / CURRENT_D_COUNT=0
600887_QUOTE_DATE_MODEL_VALIDITY = NOT_ESTABLISHED
BASELINE_V13 = UNCHANGED / FROZEN
FORMAL_WATERMARKS = UNCHANGED
CANONICAL_EXCEL_UPDATED = NO / NEW_EXCEL=0
STRICT_PIT = NOT_PROVEN
M4 = PARKED_NONBLOCKING
M6 = NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-29 Shared-Model Binding and Blocker Closeout

The Yili `600887` conditional valuation now replays through the registered
`quality_compounder` / shared `residual_income_or_equity_value` route with
issuer identity `VERIFIED`. The replay input is restricted to five issuer
CNINFO sources for security `600887`; the prior Moutai discount-rate evidence
and file-alias citations are excluded. The model's dividend-path check is now
described accurately as an algebraic cross-check under assumed retention, not
independent evidence of issuer distributable cash or dividend sustainability.

```text
valuation_basis = 2026-06-30
shares = 6325360667
bear_base_bull_cny_per_share = 8.047594 / 11.023375 / 13.133453
confidence = LOW / conditional_research_only
source_package_sha256 = e0387d58d45e728d6576a3e44bce66b14c03253491bcf733ce8e6942f492e803
input_descriptor_sha256 = 8ee8e489c002c06413d5c06002aff10d87ddbf55860bf3221a5ead7c3c0e5c04
valuation_result_sha256 = 51eafc6f61bb4f69a24bf5d921417e2748401ef2ddb4c85485c0926e07bc02e6
result_artifact_sha256 = 0ee6b27b220b136b709dd413c5d1d415f1152c1e99df6c12d90e71154306fdce
price_review = NOT_ASSESSABLE / quote-date ModelValidity not established
```

The Yili dividend check compares the CNY 1.22/share policy value against a
June 30 share-count proxy of about CNY 7.717bn and against model dividends.
With 25% retention, bear/base first-two-year modeled dividends are about
CNY 0.764/0.722 and CNY 1.146/1.131 per share, below the policy value. This
does not show the policy will fail; the model does not force that floor, and
the proxy cash amounts omit material cash uses. Dividend sustainability
remains `DATA_INCOMPLETE / UNKNOWN`.

Midea's 11 retained 2014-2024 report hashes match their source files. A
parent-profit / adjacent-year-end-equity average is retained only as an
unadmitted ROE proxy; it is downgraded from A to B scenario input. Midea's sole
remaining A blocker is the current ordinary-share denominator. Shenhua's
bounded review of company-level acquisition-scope disclosure and the existing
evidence index found no named, retained target-level audit/transaction report
that can attribute earnings to the acquired perimeter. The current-scope
mid-cycle earnings blocker remains; that public-evidence path is now
`EVIDENCE_STOP`, reopening only on a newly named official target-level report
with sufficient comparable financial detail.

No Canonical Excel was changed: its current price review remains
`NOT_ASSESSABLE`, ModelValidity is absent, and the approved
`@oai/artifact-tool` dependency is unavailable. No replacement workbook was
created. Total Goal and operational states remain unchanged; `action=no_order`.

Verification after these changes: focused binding, residual-income, issuer,
application, input, registry and architecture tests passed (`92 passed`). The
exact `offline-core` selection from `core-research-gates.yml` passed locally
(`1142 passed, 23 skipped`, two existing named-range deprecation warnings).
The PostgreSQL integration job was not run locally because no local PostgreSQL
service or client is available; the older GitHub run above is for its recorded
older commit, not this working tree.

## 2026-09-29 08:54 +08 Continuous Public Research Continuation — latest

Audit baseline is `main@56354774972dccf15f9a1897a5446c6467dbda4c` and was
clean/equal to `origin/main` at the start of this continuation. GitHub Core
Research Gates run `36491639226` passed for that exact SHA. This snapshot adds
forward-only TSA revocation-evidence engineering and updates research/status
Markdown. It does not change a frozen baseline, valuation, canonical workbook
or order state.

The prospective `timestamp-chain-v2` verifier now binds the CMS signer to a
unique path ending at a configured trust anchor, validates complete CRLs for
each non-anchor path certificate at the token `genTime`, and fails closed on
unsupported critical extensions on the matching CRL entry. TSA and CRL HTTP
requests resolve DNS once, reject non-public addresses, connect to the selected
IP while preserving TLS hostname validation, ignore proxy environment settings,
and reject redirects. Existing v1 receipts retain their legacy validation
path. No real TSA request or runtime receipt was created or modified.

The CRL hashes are recorded in a JSON receipt written after the signed token is
received; that receipt/CRL manifest is not itself covered by the RFC 3161 token.
Verification therefore detects isolated file drift but cannot prove the receipt
and CRLs were not modified together. Validation is bounded to a single-signer
test token and direct, full-scope CRLs; this work does not establish general PKI
interoperability or strict PIT evidence.

Focused tests for timestamp-chain, prospective baseline and registration passed
**72 tests**. The exact CI `offline-core` selection passed **1112 tests**, with
**23 skipped**, under `PYTHONUTF8=1`; its first local run without that setting
had one unrelated child-process GBK decoding failure. A full repository test
run was interrupted at 87% after it stopped making progress; it is not counted
as passing. `git diff --check` passed. Strict PIT remains unproven.

Re-bound the registered v2 plan, runtime receipt, baseline inputs, supplemental
facts and frozen v13 snapshot against verification v9. V13 still has
`strict_pit_admissible=false`; all three cases remain
`BASELINE_PARTIAL / VALUATION_NOT_READY`.

The Midea PIT-anchor adversarial review confirms GitHub PushEvent `22282999048`
reports the exact registered v2 plan commit public on `main` at
`2026-09-27T00:24:06Z`, but does not timestamp the runtime receipt, source
capture, or evaluation. The receipt self-reports `00:24:16.082830Z`, about
20m44s before the plan's declared `registered_at=00:45Z`; its timestamp is
explicitly unattested and the verifier does not enforce that ordering. This
semantic ambiguity is left unresolved: no timestamp or registration field is
reinterpreted. V13 self-reports build time `2026-09-27T09:22:55Z` (17:22 +08),
after its cutoff. The later RFC 3161 tokens bind the plan bytes and a workbook
publication receipt, respectively; neither retroactively attests the full
baseline/source closure. Strict PIT remains unproven.

R1 independently checked China Shenhua's retained CNINFO 2026H1 report
`1225531759` (SHA-256
`ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`);
Root re-extracted the cited report pages. Printed p. 91 reports consolidated
cash paid for long-lived assets of CNY 29,579m in 2026H1 versus restated
CNY 32,163m in 2025H1, while p. 210 reports segment capex of CNY 23,290m
versus CNY 22,076m. These measures move in opposite directions and remain
unreconciled; neither identifies maintenance versus growth capex. Printed
p. 93's company-only statement reports CNY 90,942m cash paid to acquire
subsidiaries, matching the p. 178 cash component for 11 controlled entities.
It narrows the accounting-perimeter question, not the target-level residual
or source-of-funds bridge. A bounded R1 review of the transaction and target
audit package is now in progress. No normalized earnings, valuation input,
dividend readiness or baseline admission follows from these facts.

At 08:54 +08 the exchange session had not opened; latest verified close remains
2026-09-28. Yili notice `1225584526` is dated 2026-09-29 and reports the
2026-09-24 CNY 25bn redemption; date-only policy conservatively makes it
available 2026-09-30. It does not verify the separate CNY 20bn note due
2026-09-29. The Midea meeting notice remains a bounded monitor candidate, not
a newly applied formal ChangeEvent. No quote or duplicate event scan was run.
The canonical workbook remains SHA-256
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL
WAITING_FOR_PUBLIC_EVIDENCE = Midea financial business/equity bridge; Yili normalized distributable cash, dividend classification and 2026-09-29 maturity outcome; Shenhua target-level acquisition earnings/cash residual and maintenance-growth capex; future T0/T1/T2 validation
NEW_EVENTS_PROCESSED = 0_FORMALLY_APPLIED
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED_THIS_TURN = false
SAFE_PUBLIC_RESEARCH_REMAINING = YES / Shenhua target audit-package review in progress; Midea PIT-anchor review complete with no strict-PIT upgrade
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN / GITHUB_EVENT_ANCHORS_PLAN_PUBLICATION_ONLY
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPT_AUDIT

| Check | Result | Disposition |
|---|---|---|
| Active prospective cases can still be researched | YES | Shenhua target-level audited history is under bounded R1 review. |
| Public evidence gap can change a named case state | YES | Shenhua acquisition-adjusted earnings/capex bridge and Midea model inputs remain incomplete. |
| New public event is eligible to apply now | NO | Yili notice remains date-conservatively available 2026-09-30; the Midea notice remains monitor-only with no decision-changing result. |
| New completed market session exists | NO | The 2026-09-29 session had not opened at audit time. |
| A baseline or strict prospective decision chain is complete | NO | V13 is partial and the runtime registration/evaluation timestamps remain unattested. |
| PIT/method validation can continue safely | YES | The adversarial review is complete; retain its ordering ambiguity and do not mutate registered dates or v13. |
| Product projection changed from admitted evidence | NO | No newly admitted quote, event or ResearchCase state change. |
| All active cases are at evidence stop | NO | Bounded Shenhua and Midea research remains available. |

## 2026-09-29 06:32 +08 Continuous Public Research Continuation — previous snapshot

Audit base is public `main@56354774972dccf15f9a1897a5446c6467dbda4c`, clean
and equal to `origin/main`. GitHub Core Research Gates run `36491639226`
completed successfully for that exact SHA. The commit publishes seven
research/status Markdown files only; it did not include the workbook, runtime
PDFs, database, server files, or credentials.

The v2 plan SHA-256 (`f98304dbfb73276073d57537e90aee37b6233821d8b0200df944718bf23a2c7a`),
registration receipt SHA-256 (`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`),
baseline-input SHA-256 (`e39386945fa67e653b2424f3c761c6c206f46a73cc522a0af35a8016b2453c6c`),
supplemental-facts SHA-256 (`0bbc21f26fd5be480745f2e1624496930863945bd29cea4da8791f27532a5628`),
and frozen v13 snapshot SHA-256 (`ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`)
match the verification configuration. V13 remains `strict_pit_admissible=false`;
all three cases remain `BASELINE_PARTIAL / VALUATION_NOT_READY`.

A GitHub public repository `PushEvent` (`22282999048`) reports `main` moving
from `269f93f1f7cd107f82de55ed795b476ab56b492f` to
`fc1e8116c50d62a0cbd71ded6bc81a1a195bc94e` at
`2026-09-27T00:24:06Z`. That commit's tree contains the exact v2 plan bytes
(SHA-256 above). This supports the plan's public availability before its
declared 08:45 +08 observation start; it does not independently timestamp the
runtime registration receipt, data capture, or evaluation. The receipt claims
`receipt_created_at=2026-09-27T00:24:16.082830Z` on the local process clock,
while its embedded plan declares 08:45 +08; the receipt itself still says
`declared_time_independently_proven=false`. The GitHub event is provider event
metadata, not a cryptographically signed receipt. Raw API page 1 is retained
locally at `runtime/prospective-timing-audit-20260929/github-repository-events-page1.json`
(SHA-256 `0690a327f54204628cc9c4124662bcbd2be47e7d59b81db6be109f9e13bcc867`);
it is ignored runtime evidence and is not part of public Git. Do not alter the
registered start, receipt, v13, or strict-PIT status from this finding alone.

At 06:32 +08 the exchange session had not opened; the latest verified close
remains 2026-09-28 for all three cases. Yili's CNY 20bn notes had a scheduled
2026-09-29 maturity date, but payment/refinancing completion is not verified.
No new quote or event run was performed. The canonical workbook pointer and
`action=no_order` remain unchanged.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL
WAITING_FOR_PUBLIC_EVIDENCE = Midea finance/capex/share/equity bridge; Yili normalized distributable cash, dividend classification and 2026-09-29 maturity outcome; Shenhua acquisition-adjusted earnings/capex split; future T0/T1/T2 validation
NEW_EVENTS_PROCESSED = 0_FORMALLY_APPLIED
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED_THIS_TURN = false
SAFE_PUBLIC_RESEARCH_REMAINING = YES / 3 bounded company R1 reviews and PIT-anchor adversarial review in progress
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN / GITHUB_EVENT_ONLY_NARROWS_PLAN_PUBLICATION_TIME
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPT_AUDIT

| Check | Result | Disposition |
|---|---|---|
| Active prospective cases can still be researched | YES | Three company-specific R1 reviews are in progress. |
| Public evidence gap can change a named case state | YES | Midea, Yili and Shenhua each retain independent research gaps. |
| New public event is eligible to apply now | NO | Yili's 2026-09-29 scheduled maturity outcome is not verified and its notice remains conservatively future-available. |
| New completed market session exists | NO | The 2026-09-29 session had not opened at audit time. |
| A baseline or strict prospective decision chain is complete | NO | V13 is partial; plan publication time is better bounded, but receipt/capture/evaluation timestamps are not independently bound. |
| PIT/method validation can continue safely | YES | Adversarially review GitHub event's timing scope; preserve registered dates and fail-closed status. |
| Product projection changed from admitted evidence | NO | No baseline/event/quote input was newly admitted. |
| All active cases are at evidence stop | NO | Bounded public research remains in progress. |

## 2026-09-29 06:13 +08 Continuous Public Research Continuation — previous snapshot

This was a time/status refresh of the substantive 05:15 research snapshot
below. The audit base was `ddcaee886a94189458f0a77f4f73492f00e808be`;
that review did not change the frozen baseline, valuation, or decision state.

At 06:13 +08 the exchange session had not opened; the latest verified close
remains 2026-09-28 for 000333, 600887 and 601088. Yili's CNY 20bn notes had a
scheduled 2026-09-29 maturity date, but payment or refinancing completion has
not been verified; no outcome is inferred. Notice `1225584526` retains
conservative `available_at=2026-09-30T00:00:00+08:00` and remains unapplied.

The canonical workbook remains recorded at SHA-256
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`. No
workbook bytes were changed. A read-only content inspection could not be
completed because `@oai/artifact-tool` is unavailable in the configured
workspace dependency environment; no alternate spreadsheet library was used.

```text
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
YILI_2026-09-29_MATURITY_OUTCOME = NOT_VERIFIED / NO_INFERENCE
FORMAL_EVENT_WATERMARK = 2026-09-27 / v9 bounded snapshots do not advance it
STRICT_PIT = NOT_PROVEN
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M7_R5 = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-29 05:15 +08 Continuous Public Research Continuation — previous snapshot

Audit base `ddcaee886a94189458f0a77f4f73492f00e808be` is clean `main` and
matches `origin/main`. Its GitHub Core Research Gates run `36483946481`
completed successfully for that exact SHA. The earlier note below is the
04:58 +08 snapshot, not a newer observation.

The v2 prospective plan, v2 registration receipt, and v9 baseline-verification
configuration were re-bound locally. Plan SHA-256
`f98304dbfb73276073d57537e90aee37b6233821d8b0200df944718bf23a2c7a` matches
the receipt; receipt SHA-256
`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5` matches
v9; the supplemental-facts SHA matches `0bbc21f26fd5be480745f2e1624496930863945bd29cea4da8791f27532a5628`.
The receipt binds 000333, 600887 and 601088 and preserves `action=no_order`,
with no outcomes observed, valuation executed, decision signal, or portfolio
data. Registration time remains process-clock-only and unattested. A focused
rerun using an isolated project `runtime/` pytest base passed **48 tests**;
the default Windows pytest temp root remains inaccessible and its setup
errors did not reproduce with the isolated base. Snapshot v13 remains frozen;
strict PIT remains `NOT_PROVEN`.

A source-bound Shenhua supplement was added at
`docs/current/track-b-shenhua-h1-acquisition-segment-capex-supplement-20260929.md`.
The retained CNINFO H1 report `1225531759` SHA-256 was rechecked as
`ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`; pages
16, 23, 56-57, 65, 178 and 210 were rendered and checked. The supplemental
acquisition and segment bridge distinguishes contractual terms from the
common-control accounting table, separates consolidated investing cash flow
from acquisition cash consideration, and keeps exploration/development spend
separate from segment capex. The segment totals cross-foot to profit CNY
45,494m / CNY 43,171m and capex CNY 23,290m / CNY 22,076m (2025H1 restated).
These are not normalized earnings, owner cash flow, or maintenance-capex
inputs; Shenhua remains `CYCLICAL_MODEL_NOT_READY / VALUATION_NOT_READY` and
dividend sustainability remains `NOT_READY`.

The Yili financing note record now includes the issuer's earlier July 7
issuance-results notice `1225412264`, locally retained at
`runtime/company-research/yili-financing-results-20260707/1225412264.pdf` and
verified against SHA-256
`f8c529139b7f49d73f355ecd41c8dea44e68ff35765379538dd090ccba5f6a2d`. It
reports CNY 25bn principal scheduled for 2026-09-24 and another CNY 20bn
scheduled for 2026-09-29. It does not identify the CNY 25.073bn redemption's
funding source or reconcile post-redemption cash/debt. At this audit time,
2026-09-29 05:15 +08, completion of the CNY 20bn due-date obligation is not
known; no non-payment is inferred. Notice `1225584526` keeps conservative
`available_at=2026-09-30T00:00:00+08:00` and remains unapplied. Yili's
FY2025 distribution proposal and 2025-2027 shareholder-return plan were
confirmed approved at the 2026-05-20 meeting by CNINFO `1225321219`; the
current research card is corrected accordingly. Ordinary/special dividend
classification remains unknown, as do normalized distributable cash and the
FY2025 interim dividend's repeatability. These facts do not change the
dividend-sustainability state.

An independent Midea source review rendered H1 report p. 60 and confirmed the
report-date base for the proposed 2026 interim dividend: 7,628,798,092 total
shares less 180,200,108 repurchase-account shares equals 7,448,597,984 shares;
CNY 0.50/share implies CNY 3,724,298,992. This narrows the dividend-proposal
denominator at the report-disclosure date only; the 2026-09-29 valuation share
denominator remains `UNKNOWN / NOT_ADMITTED`. No model input or valuation is
updated. The same review found the current Midea CapEx memo SHA-256
`b2d14f93f46806948d42c07dcf6f74b70380371d036242f373fbdb7023849e51` differs
from the SHA-256 `bf732e55b77eea455da71a6c82491a6a9fc324f3d7c27afb556f30a2c2dc5bee`
recorded in its machine receipt. The source PDF hashes match, but the current
narrative bytes are not bound by that earlier receipt; this is recorded in
`docs/current/track-b-midea-capex-receipt-binding-audit-20260929.md`.
Midea remains `MODEL_NOT_READY / VALUATION_NOT_READY`.

As of 05:15 +08 the exchange session had not opened; latest verified close
remains 2026-09-28 for all three registered cases. Formal event watermark is
still 2026-09-27; v9 contains only bounded later snapshots, not a continuous
advance. No duplicate quote or event run was made. The single canonical
workbook remains at SHA-256
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`; this
late source review did not alter admitted baseline inputs, decision state, or
the product read model, so Excel was not republished.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL / V2_BYTES_FROZEN
WAITING_FOR_PUBLIC_EVIDENCE = Midea finance/capex/equity bridge, current share denominator and CapEx memo successor receipt; Yili source of redemption funding, post-maturity liquidity and dividend classification; Shenhua acquisition-adjusted earnings and capex split; future contemporaneous PIT
NEW_EVENTS_PROCESSED = 0_FORMALLY_APPLIED / Yili 1225584526 remains future-available and unapplied
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED_THIS_TURN = false / NO_ADMITTED_INPUT_OR_PRODUCT_STATE_CHANGE
SAFE_PUBLIC_RESEARCH_REMAINING = YES
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPT_AUDIT

| Check | Result | Disposition |
|---|---|---|
| Active prospective case can still be researched | YES | Three registered cases remain partial. |
| Public evidence gap can change model applicability or financial interpretation | YES | The three case-specific gaps above remain open; Yili's ordinary/special type remains unknown, while Midea's H1 dividend-base denominator narrows only that dated proposal and its current CapEx memo receipt binding remains unresolved. |
| New public event is eligible to apply now | NO | Yili redemption notice remains unavailable until 2026-09-30; no formal event is applied. |
| New completed market session exists | NO | At 05:15 +08 the exchange had not opened. |
| Baseline or strict prospective decision chain is complete | NO | Baselines remain partial; registration/capture clocks do not prove strict PIT. |
| PIT/method validation can continue safely | YES | Preserve v2; do not backdate or retrofit PIT. |
| Product projection changed from newly admitted evidence | NO | No admitted input or product-state change; preserve the existing canonical workbook. |
| All active cases are at evidence stop | NO | Safe bounded public research remains. |

## 2026-09-29 04:58 +08 Continuous Public Research Continuation — previous snapshot

The current Goal and stage remain `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`
and `STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH`. This
continuation audited `main` at `1405cd770dedbe41668a8e43c0b442754913f1ea`,
verified equal to `origin/main` after `fetch` and `pull --ff-only`. That base's
Core Research Gates run `36476116732` completed successfully:
`offline-core=success` and `postgres-integration=success`. The earlier run
`36467280788` had an anonymous API read failure (HTTP 403); it did not recur
in the later successful runs, though its root cause remains unconfirmed.
The v6 projection and WPS/readability receipts are local `runtime/` evidence
excluded from public Git. The published pointer records their paths and hashes,
but a public clone cannot independently verify those local receipts.

The v2 registration plan, runtime receipt and v9 baseline-verification
configuration were re-bound locally: plan SHA-256
`f98304dbfb73276073d57537e90aee37b6233821d8b0200df944718bf23a2c7a`, receipt
SHA-256 `8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`,
baseline input SHA-256
`e39386945fa67e653b2424f3c761c6c206f46a73cc522a0af35a8016b2453c6c`. The
focused registration and baseline tests passed `48`; the default Windows
pytest temp root was inaccessible, so the passing run used a newly verified
isolated directory under ignored `runtime/`. Registration time remains
process-clock-only and unattested; snapshot v13 remains frozen and strict PIT
is still `NOT_PROVEN`.

The formal prospective event watermarks remain bounded through 2026-09-27.
Successor `config/prospective-public-event-watermarks-v9.json` preserves that
boundary and appends three exact-issuer CNINFO snapshots for 2026-09-28..29;
all retrieval times are local process time and unattested, so no continuous
watermark advances and strict PIT remains `NOT_PROVEN`.

| Symbol | Scan receipt | Result |
| --- | --- | --- |
| 000333 | `runtime/prospective-public-event-2026-09-29/gapfill-000333-20260928T164617774820Z/scan-receipt.json` / `c3462ea1cff9a06daf4d69918c5e7efc4f40c30c18ddb8ed2f830a9c4906a137` | Re-observed known notice `1225582141` after its conservative 2026-09-29 availability; no new event. |
| 600887 | `runtime/prospective-public-event-2026-09-29/gapfill-600887-20260928T163118110265Z/scan-receipt.json` / `afa5db545de95f43415e5aa2eebfc281a002ae8fc4661d9f4916b00455976c1c` | New notice `1225584526`: three super-short-term notes with CNY 25bn principal were paid on 2026-09-24; reported total cash settlement is CNY 25,073,335,616.44. |
| 601088 | `runtime/prospective-public-event-2026-09-29/gapfill-601088-20260928T164633324133Z/scan-receipt.json` / `7757bf32eee2a186783b510d92eb451c704cd3c12b8e962fe6a2cf9bdab798a9` | Zero announcements in this retrieval snapshot. |

The Yili original was downloaded and hash-verified against CNINFO PDF SHA-256
`4ef69c200e7b3d0cde3e1b667bcbb4304d15dd6aa406585ca796aa2c3ab4a270`. Since
the notice is date-only, conservative `available_at` is 2026-09-30. It is a
`MATERIAL_RISK_MONITOR_CANDIDATE`, not a formal applied M5 event decision. It
confirms redemption of these notes but does not disclose the funding source or
post-redemption cash/debt balance. Reopen only the affected post-H1 debt,
liquidity, net-debt and dividend-capacity dependencies; do not infer a
directional change to dividend sustainability, valuation or decision status.
The canonical workbook was updated in place and WPS-read-only verified at
SHA-256 `849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`.
Quote as-of remains 2026-09-28. Projection v6 is only a single-day bounded
observation through 2026-09-29; the formal event watermark remains 2026-09-27,
strict PIT remains unproven, and the Yili notice remains excluded until its
conservative 2026-09-30 availability. The WPS read-only and readability
receipts passed; final user acceptance has not passed.

The Yili redemption note was corrected after independent report-level review:
its previous CNY 74.614244bn cash-equivalent and CNY 47.305038bn short-term
borrowing figures were Midea H1 values, not Yili values. The corrected note
uses Yili H1 cash and cash equivalents of CNY 13.91427757164bn and short-term
borrowings of CNY 64.67719303415bn. The resulting 179.67% and 38.65% are
cross-date scale comparisons only; no post-redemption liquidity direction is
inferred.
See `docs/current/track-c-yili-short-term-financing-redemption-20260929.md`.

An independent source review found that the old Midea FY2025 evidence package
misnamed CNY 85.24715bn of monetary funds as cash and cash equivalents. The
versioned v3 package now separates monetary funds (CNY 85.24715bn) from cash
and cash equivalents (CNY 68.50867bn), with the annual-report pages bound by
SHA. The official 2026H1 report also supports consolidated cash and cash
equivalents of CNY 74.614244bn and short-term borrowings of CNY 47.305038bn,
among the separately scoped facts recorded in the current research note.
Financial-business cash/debt attribution remains unresolved; `net_debt=null`,
`MODEL_NOT_READY`, and `VALUATION_NOT_READY` remain in force. Frozen baseline
v13 was not rewritten. See
`docs/current/track-b-midea-cash-scope-correction-20260929.md`.

The same Midea H1 report's segment and consolidated income statements were
cross-checked from rendered primary-source pages. Segment external revenue
matches consolidated `营业总收入` after adding separately presented interest
and commission revenue; there is no revenue discrepancy. The report places
financial services within `other segments`, combines that group with
unallocated amounts, and allocates indirect expenses by revenue. It therefore
does not establish finance-only earnings, cash or debt. The segment profit
bridge is descriptive only and contributes no FCFF input; v13 and
`financial_scope_approved=false` remain unchanged. This is late-researched
pre-start evidence, not strict PIT evidence.

The Shenhua interim-distribution record is now summarized consistently in
`docs/current/track-c-public-event-gapfill-20260927.md`: gross CNY 0.98/share,
estimated CNY 21.256bn, approved at the 2026-09-23 meeting, but implementation
and payment are unverified. The estimate is 74.0% of H1 consolidated
parent-attributable profit and 38.9% of H1 operating cash flow; neither ratio
proves normalized dividend capacity. These are pre-start public facts and do
not change the frozen baseline or valuation state.

At the verification time 2026-09-29 04:58 +08, the exchange had not opened;
the latest verified market session therefore remains 2026-09-28. The canonical
workbook remains at the previously verified v6 publication and 2026-09-28
quote snapshot. This turn changed research documentation only; no new fact
changed the product read-model state, so the workbook was not republished.
`action=no_order`.

Targeted regressions after the as-of guard, test-fixture correction,
cross-platform UTF-8 child-process setting, and Midea v3 fact correction passed:
`26 passed`. The full suite then completed with `3227 passed, 29 skipped,
0 failed` in 354.89s. The 20 warnings are existing Backtrader UTC and
openpyxl named-range deprecations.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL / V2_BYTES_FROZEN
WAITING_FOR_PUBLIC_EVIDENCE = Midea industrial/financial scope and valuation inputs; Yili post-redemption liquidity and normalized distributable cash; Shenhua segment/cost bridge; future PIT evidence
NEW_EVENTS_PROCESSED = 0_FORMALLY_APPLIED / Yili 1225584526 REVIEWED_AS_MATERIAL_RISK_MONITOR_CANDIDATE
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED = true / V6_EVENT_VIEW / QUOTE_AS_OF_2026-09-28 / SHA256_849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb
SAFE_PUBLIC_RESEARCH_REMAINING = YES / Midea, Yili, Shenhua evidence gaps remain
RESEARCH_SUPPLEMENT = MIDEA_H1_SEGMENT_SCOPE / SHENHUA_INTERIM_DIVIDEND_STATUS / V13_UNCHANGED
CANONICAL_UPDATED_THIS_TURN = false / NO_PRODUCT_STATE_CHANGE
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPTION_AUDIT

| Check | Result | Disposition |
| --- | --- | --- |
| Active prospective research remains | YES | Three registered company cases remain partial. |
| A public evidence gap can change model applicability, confidence, or distribution status | YES | Midea scope/valuation inputs, Yili liquidity/cash capacity and Shenhua operating bridges remain open. |
| A new available public event needs disposition | YES | Midea notice 1225582141 remains a monitor candidate without a formal materiality decision; Yili notice is not available until 2026-09-30. Neither changes valuation state. |
| A new completed market session is pending | NO | At 2026-09-29 04:58 +08 the exchange had not opened. |
| A baseline or strict prospective decision chain is complete | NO | Baselines remain partial; timestamps are not independently attested. |
| PIT/method validation can continue safely | YES | Preserve v2; do not backdate or retrofit strict PIT. |
| A product projection changed from cutoff-eligible event evidence | YES | Midea notice 1225582141 is visible; Yili notice remains excluded until 2026-09-30; quote snapshot is unchanged. |
| All active cases are at evidence stop | NO | Safe public research remains. |

## 2026-09-28 Continuation — Yili Payment-Lifecycle Successor

An R1 read-only review found that the retained CNINFO implementation notice
`1225335436` proves the FY2025 final Yili distribution was approved on
2026-05-20 and paid on 2026-06-05, for CNY 5,692,824,600.30 (CNY 0.90 per
share). The earlier dividend package, whose research date was 2026-09-22,
still represented that distribution as proposed because the implementation
notice had not yet been bound to the package. The old package bytes remain
recoverable from Git history at the prior committed revision.

The current local successor package is
`config/m1-distribution-packages-v1/600887-quality-compounder.json`, version
`20260928.1`, with the implementation PDF bound by SHA-256
`c8cd69e0a195ec9daa702306a2ba1ebf7cb8b53b1f5cae5d872cd590b0ba3c70` and
`dividend_type=unknown`. Its trailing paid dividend is now CNY 1.38 per share
(FY2025 interim CNY 0.48 plus FY2025 final CNY 0.90) for the quote window
2025-09-22 through 2026-09-22, yielding 5.1550% against the retained CNY
26.77 quote. The declared proposal snapshot remains separately labeled; the
normalized scenario remains `NOT_READY`.

The correction does not change the registered prospective baseline, valuation,
model applicability, dividend sustainability (`DATA_INCOMPLETE / UNKNOWN`),
strict PIT, canonical Excel, or `action=no_order`. The parent-level cash bridge
is still only a bounded proxy and is not normalized distributable cash. Targeted
package, distribution, income-projection, and workbook regressions passed:
`28 passed`.

GitHub synchronization remains unverified: the local `main` contains the
prior committed Yili classification correction `867488e`, while the last
locally verified `origin/main` remains `a43dd35`; `git fetch origin` timed out.

## 2026-09-28 Continuous Public Research Continuation — current

This continuation began from a clean `main` at
`a43dd35533bb0f848bd0e68e2d0afd556f8a0165`, matching `origin/main`.
GitHub Core Research Gates run `36428450403` completed successfully for that
exact HEAD. The long-term Goal and current-stage contract were read from the
latest checkout; the three registered cases and M6/M7 gates remain unchanged.

The canonical prospective v2 registration receipt at
`runtime/prospective-v2-fc1e811/receipt.json` was re-hashed to
`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`, matching
the value bound by the v13 baseline and publication contracts. Its process
clock remains unattested. This resolves the apparent path mismatch raised by
an independent reviewer; it does not prove historical registration time.

The retained Midea FY2025 official annual-report PDF was re-hashed to
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`.
Two research notes had one extra `b` in the printed hash; both citations were
corrected. The report bytes and all underlying research values are unchanged.
The exact point-in-time ordinary-share denominator, maintenance/growth CapEx,
industrial operating-scope bridge and WACC remain separate blockers; Midea
stays `MODEL_NOT_READY / VALUATION_NOT_READY`.

An independent R1 review of Yili's retained official dividend lifecycle found
no issuer wording that explicitly classifies the reviewed FY2024 final,
FY2025 interim, or FY2025 final proposal as ordinary or special. The typed
package had incorrectly labeled them `ordinary`; its three records now say
`unknown` with blockers. The shared domain accepts unknown historical
classification but rejects it for forward/normalized estimates. Paid/proposed
amounts, dates, yields, the registered baseline and workbook are unchanged.
Normalized distributable cash remains unestablished. The correction-focused
dividend regression run passed: `13 passed`.

After the prior 2026-09-28 16:13 +08 snapshot, one additional exact-issuer
CNINFO date-window query was run per registered issuer. The local process
clock reports 21:36:51 through 21:38:40 +08 and is not independently attested.
The bounded receipts are:

| Symbol | Receipt | SHA-256 | Result |
| --- | --- | --- | --- |
| 000333 | `runtime/prospective-public-event-2026-09-28/gapfill-000333-20260928T133651400346Z/scan-receipt.json` | `695082f4c4db4d981fd696dae71a6d97d5b1bf5a8786b5ae3f4bd48123273a45` | One previously known notice `1225582141`; conservative `available_at=2026-09-29`; no new event |
| 600887 | `runtime/prospective-public-event-2026-09-28/gapfill-600887-20260928T133816904422Z/scan-receipt.json` | `d150108dbd2b7a71708c96a1a5555898746ded37337fc64e3728dd0ea97639a6` | Zero announcements |
| 601088 | `runtime/prospective-public-event-2026-09-28/gapfill-601088-20260928T133840001626Z/scan-receipt.json` | `37b682cfd0e6a200fb404d0fcc46686fe54f90ad8888c829aae98ac20457d6cd` | Zero announcements |

The Yili and Shenhua queries used identity indexes whose path and SHA were
retained by earlier exact-issuer CNINFO scans. A first Yili attempt without
that binding was rejected by the scanner's guessed-ID guard and was not used.
These later same-day retrieval snapshots do not advance formal watermark v8,
prove multi-channel/day-complete coverage, or establish strict PIT. No event
disposition, valuation, baseline, or canonical workbook changed.

The existing WPS Canonical workbook remains
`2f72dc76bcf6a74449dec5a336cc41540ae84bb1e7935badb7248a4b8a6c1bcf`; a
read-only hash check matches its entry in
`artifacts/current/artifact-registry-v2.json` (registry SHA-256
`80e81d35279dac1a44fbae13982d2445806f2979dc78e3d6a7bcb191d894ae25`). The
2026-09-28 market session was already verified and published; no duplicate
quote run or Excel publication was warranted.

Focused regression tests for prospective timestamps, baselines, observations,
event scans, watermarks, and as-of projection passed: `113 passed` before the
Yili classification correction. The correction-focused dividend tests passed
separately: `13 passed`. No baseline, valuation, event projection, or workbook
content changed.

After the Yili correction, the expanded dividend, income projection, M1
workbook, and fixed-sample regression set passed: `38 passed` across five test
modules.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL
WAITING_FOR_PUBLIC_EVIDENCE = specific research gaps only; nonblocking to other tracks
NEW_EVENTS_PROCESSED = 0 / known Midea notice repeated; Yili and Shenhua zero
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED = false / physical workbook hash matches pointer
SAFE_PUBLIC_RESEARCH_REMAINING = Midea denominator/CapEx/equity bridge; Yili dividend classification/cash normalization; Shenhua scope/segment/cost bridge; strict future T0/T1/T2 evidence
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPTION_AUDIT

| Check | Result | Disposition |
| --- | --- | --- |
| Active prospective company research remains | YES | Three baselines are partial; bounded company-specific public evidence work remains. |
| A public evidence gap can change model applicability, confidence, or distribution status | YES | Keep the separate Midea, Yili, and Shenhua blockers open. |
| A new available public event needs disposition | NO | The only Midea notice remains conservatively available 2026-09-29. |
| A new completed market session is pending | NO | The 2026-09-28 close was already processed once. |
| A baseline or strict prospective decision chain is complete | NO | All three baseline cards are partial; strict `T0<T1<T2` is unproven. |
| PIT/method validation can continue safely | YES | Preserve forward-only timestamps; do not repair historical time claims. |
| A product projection should change from new facts | NO | No newly available fact or disposition; do not republish the workbook. |
| All active cases are at evidence stop | NO | R1 evidence reviews remain in progress; no broad company expansion is authorized. |

The Goal remains active. R2, R3, R5 and R6 park only their own DAG nodes.

## 2026-09-28 Continuous Public Research Checkpoint — prior continuation

The active Goal remains `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`,
stage `STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH`. At
continuation start the local `main` and `origin/main` were clean at
`4de728c18b1ee7ce7d9c07eef571fce7a49d84cf`. GitHub Core Research Gates run
`36421866347` completed successfully for that exact HEAD. The RFC 3161 helper
and tests are now part of that commit; this is engineering evidence, not PIT
admission.

The v2 registration receipt
`runtime/prospective-v2-fc1e811/receipt.json` has SHA-256
`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5` and
still declares its process-clock time unattested. The registered plan's exact
bytes (SHA-256
`f98304dbfb73276073d57537e90aee37b6233821d8b0200df944718bf23a2c7a`) were
submitted to DigiCert and independently re-verified from
`runtime/prospective-timestamp-chains/workbench-review-20260928/`; receipt
SHA-256 is
`2006de88f0bc226d7191f5ee8fa5727a37b48cbb7373b252d9abf2c6fa981e18`, with
signed `genTime=2026-09-28T12:01:56Z`. The chain verifies the SHA-256 imprint,
nonce, policy, signature and certificate path at signed time. Its claim is
only that the plan bytes existed no later than that signed time. It does not
prove the claimed 2026-09-27 registration time, timestamp the v13 baseline or
observation ledger, establish complete model-input closure, or prove strict
`T0<T1<T2`; `strict_pit_admissible=false` remains mandatory.

A separate DigiCert RFC 3161 timestamp was then obtained for the existing
canonical public-workbench publication receipt, not for the historical
registration or baseline. The independently re-verified chain is retained at
`runtime/prospective-timestamp-chains/canonical-public-workbench-20260928/`;
receipt SHA-256 is
`9fe94fd0b8219e7729264bbb7789ffd3290c634114024d900274e51ed7670da3`, with
signed `genTime=2026-09-28T13:17:06Z`. Its payload SHA-256 is
`1568cc2404b9ad32a42230c7ba00b9342684785f7ff52a9ff5c63c686db33ec4` and
binds the canonical publication receipt, including the quote bundle, v13
baseline, event projection, observation ledger and `action=no_order`. Imprint,
nonce and signature-chain verification passed. This proves only that those
receipt bytes existed no later than the signed time; it does not complete
model-input closure or future observations, and `strict_pit_admissible=false`
remains unchanged.

The current immutable baseline file remains
`runtime/prospective-baseline-20260927/snapshot-v13-midea-h1-verified.json`,
SHA-256
`ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`. It
contains three `BASELINE_PARTIAL` cards and all three valuations remain
`VALUATION_NOT_READY`. Their bounded open inputs remain distinct: Midea's
point-in-time ordinary-share denominator, maintenance/growth CapEx and
enterprise-to-equity bridge; Yili's ordinary/special distribution
classification and normalized distributable cash; Shenhua's matched-period
acquisition/perimeter, product-segment, unit-cost and maintenance-CapEx
bridges. Existing research cards and source hashes remain the evidence; no
baseline was rewritten from later information.

An independent R1 provenance review flagged a transcription mismatch in the
FY2025 Midea report hash in the share-denominator and related-party research
notes. The retained PDF was re-hashed as
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`; both
notes now match the file. Separately, the exact registered v2 receipt at
`runtime/prospective-v2-fc1e811/receipt.json` hashes to
`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`, matching
the baseline and publication bindings. This closes a transcription/custody
check only; it does not independently attest the receipt's process-clock
creation time or change any baseline, valuation, or PIT status.

Track A already processed the 2026-09-28 close for the three registered
companies in bundle
`runtime/quote-sessions/20260928T080412445154Z/bundle.json`, SHA-256
`08d8dce83ba552ec77c4f6db0f95c7ec348b2b27b76dbc00dfbed86ec35088ea`:
000333 CNY 82.00, 600887 CNY 27.03 and 601088 CNY 48.39. The same canonical
WPS workbook is bound to that completed session and had already passed
read-only and all-page readability checks. No later completed session exists
on 2026-09-28; do not duplicate the daily market run.

The post-close bounded CNINFO snapshots at 2026-09-28 16:13 +08 are retained
under `runtime/prospective-public-event-2026-09-28/`. Their scan-receipt hashes
are `2a2f34d5a96162211aaa1b05f46197fdbf4e6dd426d4208072181f6ba4f0e8c1`
(000333), `b4ea0c6ced0ace760f650b49070b240252f7709ea68df4df42ac03696174f121`
(600887), and
`e2a0bc27d9fd298efbf7e178700df504e0dcbdb21fb9cfe1e206b125c377ec54`
(601088). They return only the already-known Midea meeting notice
`1225582141` (conservative availability 2026-09-29) and zero Yili/Shenhua
rows. These are retrieval-time snapshots, not full-day coverage; their process
clock is unattested, they do not advance the formal v8 watermarks, and the
future-available Midea notice remains outside the 2026-09-28 canonical view.
No new event disposition or workbook publication is warranted.

The actual configured Canonical WPS workbook was read-only hashed and matches
the pointer at
`2f72dc76bcf6a74449dec5a336cc41540ae84bb1e7935badb7248a4b8a6c1bcf`.
`artifacts/current/artifact-registry-v2.json` had still described the prior
`b47141...` workbook; the registry was regenerated without changing the
workbook and now hashes to
`80e81d35279dac1a44fbae13982d2445806f2979dc78e3d6a7bcb191d894ae25`.
Seven hidden `.m7-staging` files were observed in the WPS directory and left
untouched; no evidence authorized deleting or relocating them. Artifact
registry regressions passed `9` tests.

Focused local regressions passed: `119` registration/baseline/observation/
event-watermark/quote/product-projection tests, plus `37` timestamp and
architecture tests. GitHub Core Research Gates passed. A prior attempted
full local suite was not a valid completion signal: its external pytest temp
root caused an unrelated repository-path test to fail, and a later run stalled
near its end and was interrupted. No full-suite pass is claimed.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / ALL_BASELINE_PARTIAL
WAITING_FOR_PUBLIC_EVIDENCE = specific research gaps only; nonblocking to other tracks
NEW_EVENTS_PROCESSED = 0 / only previously known future-available Midea notice in post-close snapshot
LATEST_VERIFIED_SESSION = 2026-09-28 / COMPLETE / 000333_600887_601088
CANONICAL_UPDATED = false in this continuation / hash matches current pointer
SAFE_PUBLIC_RESEARCH_REMAINING = Midea denominator/CapEx/equity bridge; Yili distribution classification/cash normalization; Shenhua scope/segment/cost bridge; prospective strict timestamped observation evidence
M4_R2 = PARKED_WAITING_R2_NONBLOCKING
M6_R3 = PARKED / OPERATIONAL_NOT_STARTED
M7_R5 = NOT_PASSED
STRICT_PIT = NOT_PROVEN
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

### INTERRUPTION_AUDIT

| Check | Result | Disposition |
| --- | --- | --- |
| Active prospective company research remains | YES | Three baselines are partial; continue only decision-relevant, bounded evidence work. |
| A public evidence gap can still change applicability or confidence | YES | Keep the listed per-company gaps open; do not fill them with assumptions or stop unrelated tracks. |
| A new public event requires disposition | NO | The 16:13 snapshots found no new available event; the Midea notice is future-available and already excluded. |
| A new completed market session is pending | NO | 2026-09-28 was already processed and published once. |
| A baseline or prospective decision chain is complete | NO | All three baseline cards are partial; no strict T0/T1/T2 chain exists. |
| PIT/method validation can continue safely | YES | Preserve the verified forward timestamp boundary and use future facts only after a valid prior anchor. |
| A product projection should change from new facts | NO | No new admitted fact or state change; only the stale artifact-registry hash was corrected. |
| All active cases are at evidence stop | NO | Several bounded company-research gaps remain open. |

The Goal remains active. R2, R3, R5 and R6 park only their own DAG nodes; none
is a total-Goal stop reason.

## 2026-09-28 GitHub Review Checkpoint

At the start of this documentation update, local `main` and GitHub `main`
were both `1afa3b12f66594d5cfd72517cfe08890b892f090`. GitHub REST API
confirmed Core Research Gates run `36412160361` completed successfully for
that commit. The tracked worktree was clean; four untracked RFC 3161 timestamp
experiment files were deliberately excluded because their targeted tests are
not all passing and the CLI is not registered. The Yili annual-report source
locator is bound in the [cash-coverage review](current/track-b-yili-dividend-cash-coverage-review-20260928.md);
copy-specific Shenhua page references and segment/profit bridges are corrected
in its [operating-series corrigendum](current/track-b-shenhua-operating-series-corrigendum-20260928.md).
None of these documentation corrections changes a baseline, valuation,
workbook, readiness gate, or `action=no_order`.

The focused registration, baseline, observation-ledger, event-scan, watermark,
and as-of projection regression set passed: `112 passed` across seven test
files. The incomplete prospective timestamp experiment was not included.

```text
CURRENT_STAGE = STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH
M2 = DONE / CHECKPOINT_A_HUMAN_PASS
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN / R6
M4 = NONPERSONALIZED_ENGINEERING_DONE / PERSONALIZED_PARKED_WAITING_R2_NONBLOCKING
M5_600519 = NEED_MORE_EVIDENCE / STILL_NOT_READY / NO_NEW_VALUATION
M6 = PREFLIGHT_ONLY / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M6_REAL_RESTORE_ACCEPTANCE = NOT_PASSED
M7 = DISPLAY_ENGINEERING_AVAILABLE / WPS_AND_ALL_PRODUCT_PAGE_READABILITY_PASS / FINAL_USER_ACCEPTANCE_NOT_PASSED
CHECKPOINT_D = NOT_PASSED
R0_AUDIT_SNAPSHOT = HISTORICAL / R0-A_NOT_PROVEN / R0-B_PARTIAL
R0-C_RESOURCE_CAPACITY = CLOSED_AS_R3_INFRASTRUCTURE_DECISION
R0_OPEN_NODES = 2 / NONBLOCKING_TO_PUBLIC_RESEARCH / REQUIRED_ARTIFACTS_UNAVAILABLE
SAFE_R0_REMAINING = 0_AFTER_CURRENT_PRODUCT_FIXES_AND_POINTER_REBUILD
SAFE_R1_REMAINING = OPEN / YILI_DIVIDEND_CLASSIFICATION_AND_NORMALIZED_DISTRIBUTABLE_CASH; SHENHUA_PRODUCT_SEGMENT_AND_ACQUISITION_BRIDGES; FORWARD_ONLY_TSA_CHAIN_ENGINEERING
EXTERNAL_GATE_HANDOFF = DAG_SCOPED_NOT_TOTAL_GOAL_STOP
M4_PRIVATE_INPUT = PARKED_WAITING_R2_NONBLOCKING
PUBLIC_RESEARCH = ACTIVE
PROSPECTIVE_PIT = ACTIVE
PUBLIC_EVENT_RESEARCH = ACTIVE_BOUNDED
CANONICAL_WORKBOOK = ACTIVE / SAME_CANONICAL_PUBLISHED_AND_WPS_VERIFIED
M6_OPERATIONAL = NOT_STARTED
PROSPECTIVE_BASELINE = 000333_6_ADMITTED / 600887_6_ADMITTED_1_UNADMITTED / 601088_6_ADMITTED_1_UNADMITTED
VALUATION = NOT_READY
STRICT_PIT = NOT_PROVEN / PROCESS_CLOCK_ONLY_UNATTESTED
REGISTRATION_RECEIPT_VALIDATION = FUTURE_TIME_AND_FALSE_ATTESTATION_CLAIMS_FAIL_CLOSED / PROCESS_CLOCK_ONLY_UNATTESTED
CURRENT_EVENT_WATERMARKS = config/prospective-public-event-watermarks-v8.json / 000333_BOUNDED_DATE_WINDOWS_COMPLETE_BUT_FORMAL_INCOMPLETE; 600887_WINDOW_COMPLETE_TO_2026-09-27; 601088_CNINFO_DATE_CHAIN_COMPLETE_TO_2026-09-27; 2026-09-28_SINGLE_DAY_SNAPSHOTS_ONLY
PROSPECTIVE_OBSERVATION_LEDGER = ACTIVE / 000333_CNINFO_1225582141_APPENDED / AVAILABLE_AT_2026-09-29T00:00+08:00 / PROCESS_CLOCK_UNATTESTED
CANONICAL_WORKBOOK_SHA256 = 2f72dc76bcf6a74449dec5a336cc41540ae84bb1e7935badb7248a4b8a6c1bcf
M5_EVENT_PROJECTION = runtime/prospective-public-event-20260928/registered-public-event-projection-v5.json / 5e543f50690a71254a97ff5c39136cd2bb74d81d1e3c4d3600f023dc948487d6
M7_WPS_READONLY = PASS / runtime/publication-receipts/wps-m7-price-display-20260928.json / FINAL_USER_ACCEPTANCE_NOT_PASSED
M7_ALL_PRODUCT_PAGE_READABILITY = PASS / runtime/publication-receipts/readability-m7-product-opportunity-quote-20260928.json
QUOTE_AS_OF = 2026-09-28 / COMPLETE / 000333_600887_601088
PUBLIC_EVENT_PROJECTION = 8_VERIFIED_BOUNDED_EVENTS / 000333_600887_601088 / FUTURE_AVAILABLE_NOTICE_ABSENT_FROM_WORKBOOK
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

## 2026-09-28 Midea Share-Denominator Research Reconciliation

Rechecked the FY2025 audited report and 2026 H1 report against their retained PDF hashes and physical pages. The H1 report confirms 7,613,438,907 total issued shares at 2026-06-30 and a separate 68,679,031-share buyback for cancellation; its 7,470,497,000 basic-EPS denominator is a period-weighted average. The treasury-stock note reports carrying values in RMB thousands, not the complete units held for share-payment plans. The current point-in-time ordinary-share denominator therefore remains `UNKNOWN / NOT_ADMITTED`; no per-share valuation input, baseline, or Excel value was changed. This is later research over pre-cutoff filings and does not establish contemporaneous PIT. Detailed page/hash reconciliation and reopen condition: `docs/current/track-b-midea-share-denominator-review-20260928.md`. Midea remains `MODEL_NOT_READY / VALUATION_NOT_READY`; its CapEx and enterprise-to-listed-equity bridge blockers remain independent. `action=no_order`.

## 2026-09-28 Yili Cash-Distribution Counter-Evidence Review

Read-only R1 adversarial review of Yili's retained 2026H1 report was
independently page-checked (SHA-256
`423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`;
physical pp. 49, 55, 57, 113-116 and 148). It confirms the receivable build,
an individually assessed CNY 881.4m receivable balance with collection
difficulty cited, increased short-term bill-discount borrowings, and a sharp
parent-only CFO/supplier-payment swing not mirrored by consolidated supplier
payments. These qualify cash-conversion interpretation but do not establish
normalized distributable cash or a decision-state transition. The evidence is
appended to
`docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md`; no
baseline, product projection, or canonical Excel change was made. Dividend
sustainability remains `DATA_INCOMPLETE / UNKNOWN`; `action=no_order`.

## Verified Opportunity Quote Display — 2026-09-28

The adversarial product review found a mismatch: the current publication was
bound to complete, dual-source matched closes for all three prospective cases,
but the opportunity projection still rendered each price as unavailable. The
projection now uses the bound quote context to show the symbol-specific close
and date, labels quote availability separately from valuation/attractiveness,
and adds the quote-bundle evidence reference. It does not infer fair value,
price attractiveness, a buy/sell state, or position size.

The original WPS workbook was updated in place; no candidate/latest/final copy
was created. Current SHA-256 is
`2f72dc76bcf6a74449dec5a336cc41540ae84bb1e7935badb7248a4b8a6c1bcf` and its
pre-publication backup is
`runtime/workbook-backups/canonical-before-m7-product-ux-20260928T085546Z.xlsx`.
Publisher receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260928T085546Z.json`.
WPS read-only receipt:
`runtime/publication-receipts/wps-m7-price-display-20260928.json` (`passed`).
All-page readability receipt:
`runtime/publication-receipts/readability-m7-product-opportunity-quote-20260928.json`
(`passed`, no clipped rows).

The focused product regression set passed `51 tests`. M3 strict PIT remains
unproven, all three valuations remain `NOT_READY`, M4 remains parked, M6
operations remain `NOT_STARTED`, M7 final user acceptance remains
`NOT_PASSED`, and `action=no_order`.

## Quote Publication Update — 2026-09-28

The retained dual-source quote bundle
`runtime/quote-sessions/20260928T080412445154Z/bundle.json` (SHA-256
`08d8dce83ba552ec77c4f6db0f95c7ec348b2b27b76dbc00dfbed86ec35088ea`) was
validated in memory with the current hash-bound prospective snapshot, event
projection and observation ledger before publication. It binds the completed
2026-09-28 closes `000333=82.00`, `600887=27.03`, and `601088=48.39`.

The existing `WORKBOOK_PATH` workbook was then published in place, preserving
all user-managed sheets and the pre-publication bytes in
`runtime/workbook-backups/canonical-before-m7-product-ux-20260928T081737Z.xlsx`.
The canonical SHA-256 is now
`0bfc9fae2b4c8e093493faaca1d6ba4f8294671db6c518c468f5ea67d24ea295`.
Publication receipt
`runtime/publication-receipts/canonical-m7-product-publication-20260928T081737Z.json`
is `PUBLISHED_WPS_READONLY_AND_READABILITY_VERIFIED`; the WPS and readability
receipts are respectively `wps-m7-product-asof-v5-quote-20260928.json` and
`readability-m7-product-asof-v5-quote-20260928.json`. All six product pages
passed, with no clipped rows, and the Midea date-only 2026-09-28 notice remains
excluded because its conservative availability is 2026-09-29.

One bounded post-close CNINFO scan per registered issuer returned only the
already-known Midea notice `1225582141` and no Yili or Shenhua notices. These
are retained snapshot evidence only; there is no new event disposition, formal
watermark advance, strict PIT claim, valuation change, or additional workbook
publication. `M4` remains `PARKED_WAITING_R2_NONBLOCKING`, `M6_OPERATIONAL`
remains `NOT_STARTED`, `M7_FINAL_USER_ACCEPTANCE` remains `NOT_PASSED`, and
`action=no_order`.

### INTERRUPTION_AUDIT — quote-publication successor

| Check | Result | Disposition |
| --- | --- | --- |
| Active prospective cases can still be researched | YES | All three remain baseline-partial and valuation-not-ready. |
| A bounded public evidence gap can change research | YES | Continue only documented Yili distribution, Shenhua scope/normalization and Midea reconciliation gaps; unavailable public eliminations remain evidence-stop items. |
| New announcement, dividend or repurchase needs disposition | NO | The post-close window found no new ID. |
| New completed exchange session remains unprocessed | NO | The verified 2026-09-28 session was published exactly once. |
| A ResearchCase baseline is incomplete | YES | `000333`, `600887` and `601088` remain partial. |
| PIT/decision-consistency validation can be progressed now | PARTIAL | Contract checks continue; independently attested forward timestamps remain a natural-time evidence requirement. |
| A product projection remains to publish | NO | The quote change is already published; no event or state change remains. |
| All active cases have reached evidence stop | NO | Only specific unavailable sub-gaps are stopped. |

`CURRENT_STAGE` remains
`STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH` and total
Goal status remains `IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`, rather than
being blocked by R2, R3, R5, or R6.

## Continuous Research Update — 2026-09-28

The active authorization is `STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH`.
`git fetch origin` confirmed local `main` and `origin/main` are both
`c9449a4fe8881a0cec9ce2f992622b48693c413a`; the existing research worktree is
dirty and was preserved. No pull or branch switch was needed.

Track A checked the latest completed session using the existing collector:

```text
bundle = runtime/quote-sessions/20260928T005610106765Z/bundle.json
bundle_sha256 = a57147ff0f96d4e60fe3fb24b80f30248d6fe1c192b2a4ad087d04ae122ca20e
report = runtime/quote-sessions/20260928T005610106765Z/report.json
status = collected_not_verified
600887 = matched_close / 2026-09-24
601088 = matched_close / 2026-09-24
000333 = invalid_evidence
new completed exchange session = none; session 2026-09-25 was closed
```

The collection is not promoted as a verified three-symbol quote package and
does not change `config/current-trial-workbook.json` or the canonical Excel.
The latest verified workbook quote remains `2026-09-24 / PARTIAL / missing
600887`; the failed 000333 evidence remains excluded.

R1 review of the latest Yili baseline snapshot found that
`yili-2026h1-financial-quality` is a report-level `financial_report` placeholder
with no numeric value, unit, label or page. It is correctly not admitted. Six
specific Yili H1 facts are already admitted from CNINFO `1225511409`; no new
financial field is missing from that filing solely because of this placeholder.
Do not backfill it or upgrade the baseline on that basis. The case remains
`BASELINE_PARTIAL`, and its model/valuation remain `MODEL_NOT_READY` /
`VALUATION_NOT_READY`.

The Shenhua R1 scope bridge added two field-level original/restated pairs to
`docs/current/track-b-shenhua-operating-series-classification-20260928.md`:
2023 group coal sales `450.0 / 454.6 Mt` and 2024 average coal price
`564 / 563 CNY/t`. Both versions retain their distinct original annual-report
and 2025 comparative sources, physical pages, hashes and report-date markers.
The latter markers are not independently authenticated timestamps. The pairs
do not identify acquisition contribution, earnings, cash flow or normalized
profit; the wider Shenhua scope/restatement bridge remains open and
`CYCLICAL_MODEL_NOT_READY`.

The same canonical publisher's `--verify-only` path also passed with the
hash-bound prospective snapshot, event projection and observation ledger at
evaluation cutoff `2026-09-28T01:08:46+00:00`. It selected one observation
(`prospective-cd9d6cc7382f67d1565132787949682b`, Yili / CNINFO `1225578520`)
and resolved all three registered symbols in memory. That source was already
public before the registration cutoff and its materiality remains unassessed;
the run is product-contract verification, not new-event admission. The
canonical workbook was not modified.

The adversarial product review also verified that ledger readers fail closed
on future observations and keep observations as research changes, not events.
This turn clarified the user-visible and receipt contract: observation research
changes explicitly state that the process clock is not independently attested
and therefore is not strict contemporaneous PIT proof; publisher outputs now
distinguish `BOUND` from `NOT_BOUND` observation-ledger input; publisher rejects
a quote session earlier than the canonical quote pointer. These changes do not
upgrade PIT, valuation, event materiality or investment state and no Excel
publication was run.

Focused verification after these changes:

```text
tests/test_canonical_m5_projection_binding.py
tests/test_product_workbench_candidate.py
tests/test_daily_quote_binding.py
26 passed
```

```text
STRICT_PIT = NOT_PROVEN / PROCESS_CLOCK_ONLY_UNATTESTED
VALUATION = NOT_READY
M6_OPERATIONAL = NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

## Verification Update — 2026-09-28

The focused public-research regression suite was rerun with an isolated
repository-local pytest temporary directory because the default Windows temp
root was access-denied. The isolated run passed:

```text
95 passed
scope = prospective registration, observation ledger, baseline admission,
        public event scanning, and event watermark v7
```

This verifies implementation contracts only. It does not prove strict
contemporaneous PIT, valuation readiness, M6 operations, or M7 final user
acceptance.

The R1 observation-ledger maintenance from this continuation is now covered
without rewriting historical v2 records:

```text
new observation records = receipt_created_at + record_created_at compatibility
future process/observation timestamps = fail closed
reviewed-notice supersession = SHA-bound and fork-checked
legacy v1 observations = still readable
```

The focused suite after these changes is `97 passed`. This closes the
observation-ledger engineering gap, but does not close the remaining Shenhua
restatement/scope bridge. `SAFE_R1_REMAINING` therefore remains open and
bounded; `601088 = CYCLICAL_MODEL_NOT_READY` and `VALUATION = NOT_READY`.

The subsequent compatibility correction keeps verified v1 observations
visible at later evaluation cutoffs; a predecessor remains visible until a
valid hash-bound successor supersedes it. The current cross-module regression after
that correction is `122 passed`.

The observation ledger is now an explicit, hash-pinned application input when
the caller supplies `prospective-observation-ledger-v1` plus its evaluation
cutoff. The Candidate layer validates only manifest-listed records and
projects them into audit evidence and `RESEARCH_CHANGE` today items; it does
not infer materiality, valuation, events, or trading actions. Runtime files
are never globbed implicitly. Canonical Publisher `verify-only` and `publish`
now accept the same three bound inputs and write the manifest SHA, evaluation
cutoff, selected observation IDs and count into their output/receipt. No
publication was run in this continuation: the current Midea observation has
`source_available_at=2026-09-29T00:00:00+08:00`, beyond the current evaluation
cutoff, so the canonical Excel remains unchanged.

The repository manifest is `config/prospective-observation-ledger-v1.json`
with SHA-256
`857c7be610244039e4df7b3f98fa986e0ff253c763b2535f5db4c7523635ebe7`.
Its 2026-09-28 replay selects only the superseding Yili observation; the
Midea observation is excluded by its 2026-09-29 availability. The reader also
preserves an explicitly SHA-bound legacy v1-to-v1 supersession chain without
inventing an unattested creation timestamp.

## Interruption Audit — 2026-09-28

The current continuation was audited against the active Goal boundary and the
canonical workbook evidence. No new exchange session, valuation input, or
material public event was admitted in this audit.

The M7 publication lifecycle had one stale label: the canonical publication
receipt still said `PUBLISHED_PENDING_WPS_VISUAL_REVIEW`, while the subsequent
WPS read-only receipt and all-product-page readability receipt both passed for
the same canonical workbook SHA. The receipt was corrected to
`PUBLISHED_WPS_READONLY_AND_READABILITY_VERIFIED`; this does not pass final
user acceptance.

The independent baseline audit confirms:

```text
000333 = BASELINE_PARTIAL / MODEL_NOT_READY / VALUATION_NOT_READY
600887 = BASELINE_PARTIAL / MODEL_NOT_READY / VALUATION_NOT_READY
601088 = BASELINE_PARTIAL / CYCLICAL_MODEL_NOT_READY / VALUATION_NOT_READY
```

Remaining R1 evidence work is bounded to the Shenhua restatement and scope
bridge, plus unavailable Midea consolidation/elimination and financial-product
reconciliation evidence. Missing public evidence remains `UNAVAILABLE`; it is
not inferred and does not authorize a valuation or order. Dividend sub-field
presentation is a documentation/read-model refinement only.

```text
SAFE_R0_REMAINING = 0_AFTER_RECEIPT_LIFECYCLE_CORRECTION
SAFE_R1_REMAINING = OPEN / BOUNDED_PUBLIC_EVIDENCE_GAPS
VALUATION = NOT_READY
M6_OPERATIONAL = NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

## Current Public Research Update — 2026-09-28

The public research stage continues under the existing bounded authorization;
the repository working tree remains uncommitted. `git fetch origin` succeeded
and confirmed both HEAD and live `origin/main` at
`c9449a4fe8881a0cec9ce2f992622b48693c413a`. The public GitHub Actions API
reports Core Research Gates run `36282732643` successful on that commit. This
CI result predates and does not include the present local changes. No
checkout/pull was performed because the worktree contains extensive research
changes. No push, production, Shadow, scheduler, notification,
private-portfolio access, or order occurred. `action=no_order`.

The registration-receipt verifier now rejects future `receipt_created_at`,
any claim that process-clock time was independently proven, a different PIT
anchor, or outcome/valuation/signal/private-portfolio flags set true. The
registration, baseline and observation suites passed `62` tests. These checks
do not attest old machine-clock timestamps or change
`PROCESS_CLOCK_ONLY_UNATTESTED` / `STRICT_PIT=NOT_PROVEN`.

### 2026-09-28 Midea prospective observation and watermark successor

CNINFO `1225582141` was captured in the exact-issuer 2026-09-28 single-day
scan, independently page-reviewed, and appended to
`runtime/prospective-observations/000333/prospective-676926f96e284002045c12b9a7142b56.json`.
The record SHA-256 is
`379046d99cb5b1f6a7353397b63ec4133a58125c38bbc3180728e8eb4bc82f8f`.
It binds registration, scan receipt, index/raw response, review record and PDF
bytes. `observed_at` is the recorded review time; `record_created_at` is
writer-generated; both remain `PROCESS_CLOCK_ONLY_UNATTESTED`. Because CNINFO
publishes a date-only marker, `source_available_at` is conservatively
2026-09-29 00:00 +08:00. It is not eligible in an evaluation cutoff before that
time, and this observation does not establish strict M3 PIT.

Append-only watermark successor
`config/prospective-public-event-watermarks-v5.json` SHA-256
`950078fa30652b8acb8a0d7d2161408580dd21bf45194f77d3fbfc142b243c05`
preserves v4 and adds the 2026-09-28 Midea single-day index plus latest
document/hash. The formal 000333 watermark remains `INCOMPLETE` with its
continuous `coverage_through` unchanged; the new date is explicitly
`COMPLETE_WINDOW_ONLY_NOT_CONTINUOUS_WATERMARK`. The existing canonical Excel
already displays the same notice event; no decision state changed, so no
publication was made. `tests/test_prospective_event_watermarks_v5.py` and the
prospective observation suite cover the successor and PIT cutoff behavior.

Watermark v6 is an append-only successor adding the 600887 and 601088
2026-09-28 exact-issuer CNINFO snapshots retrieved at about 01:27 +08:00. Each
query returned zero announcements on one page with HTTP 200 and terminal
`has_more=false`. Its focused tests bind both indexes, receipts and raw pages
by SHA-256 and assert the v5 records are otherwise unchanged. Formal
`coverage_through` and `coverage_status` do not advance; these snapshots do not
represent full-day or multi-channel coverage.

At the preceding v7 checkpoint, the append-only successor added the 2026-09-28
05:14–05:15 +08:00 single-day CNINFO snapshots for 000333/600887/601088,
returning 1/0/0 results. The Midea result is the already-recorded notice
`1225582141`; no new material event or product state was found. Formal
`coverage_through` and `coverage_status` remain unchanged. V7 tests bind every
index, receipt and raw-page hash and preserve v6 history; each record's
`latest_bounded_observation` points at the newest scan and its predecessor is
retained explicitly. An earlier Yili attempt left only a 165-byte empty raw
response with no index/receipt; it is preserved but excluded as incomplete
evidence. The v7 plus v6 tests passed 4 cases; scanner tests passed 33 cases;
`git diff --check` passed. There was no workbook write or republish.

The full local regression after these changes completed with
`3160 passed, 30 skipped, 20 warnings`; warnings are existing Backtrader UTC
and openpyxl named-range deprecations. `git diff --check` passed. A later
same-workbook publication parked M4 personalized analysis; its publication and
WPS read-only receipts bind the current canonical SHA-256
`b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`. The 61
worksheets are preserved, with six product pages visible and 55 legacy pages
hidden. M7 final user acceptance remains `NOT_PASSED`; `action=no_order`.
Live GitHub fetch/CI could not be checked because the latest fetch connection
was reset; local `origin/main` is cached only. No commit or push was made.

```text
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
PUBLIC_RESEARCH_OPEN_NODES = baseline assumptions/unadmitted facts remain for all three cases; valuations NOT_READY
PUBLIC_EVENT_OPEN_NODES = 000333 continuous CNINFO watermark INCOMPLETE; 600887 bounded only through 2026-09-27; 601088 retained CNINFO windows through 2026-09-27, not multi-channel
CURRENT_DATA_OPEN_NODES = quote bundle as of 2026-09-24 PARTIAL / 600887 missing; no newer completed close is evidenced
PRODUCT_OPEN_NODES = no verified product-state change requiring publication; final M7 acceptance remains R5
R2_PARKED_NODES = M4 personalized portfolio only
R3_PARKED_NODES = M6 production, restore and infrastructure authorization
R5_PARKED_NODES = M7 final user acceptance
R6_PARKED_NODES = strict contemporaneous M3 PIT; future real M6 sessions/events
M6_OPERATIONAL = NOT_STARTED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

### Current INTERRUPTION_AUDIT — 2026-09-28 (v8)

1. R2 private data required now: **NO**; only personalized M4 is parked.
2. R2 blocks only M4: **YES**; public research, event monitoring and the canonical workbench continue independently.
3. Track A public market data can continue: **YES**, after a new completed exchange session. At the 2026-09-28 12:00 +08:00 audit time, the market had not closed; latest verified quote remains 2026-09-24, partial and missing 600887. Do not promote the incomplete 2026-09-28 collection.
4. Track B prospective research can continue: **YES**. The Shenhua restatement/scope bridge remains open. Midea parent-only public matching is complete, while exact internal eliminations and bank-product reconciliation are unavailable in retained public disclosures. Yili's H1 cash-quality supplement now quantifies revenue/profit divergence and the CFO bridge, but multi-year ordinary-dividend sustainability and normalized cash coverage remain open.
5. Track C public event research can continue: **YES**. Watermark v8 verifies the Midea adjacent CNINFO date windows through 2026-09-27 but keeps its formal status `INCOMPLETE`; Yili is bounded to 2026-09-23..09-27 and Shenhua to 2026-03-31..09-27. The three 2026-09-28 observations are single-day snapshots only (1/0/0), not full-day or multi-channel coverage and not strict PIT.
6. Track D product/Excel can continue: **YES**, but the v8 review found no new event, valuation, decision state or other product-state change requiring publication. The existing canonical workbook remains unchanged.
7. Unprocessed public evidence: **NO new item identified** in the retained v8 chains and 2026-09-28 snapshots as of this audit; coverage limits and the unattested process clock remain explicit.
8. ResearchCase baseline incomplete: **YES**; 000333 and 600887 remain `BASELINE_PARTIAL / MODEL_NOT_READY / VALUATION_NOT_READY`; 601088 remains `BASELINE_PARTIAL / CYCLICAL_MODEL_NOT_READY / VALUATION_NOT_READY`.
9. Current public announcement requiring a new disposition: **NO**; Midea `1225582141` is already registered and no new 2026-09-28 filing was found in the bounded snapshots.
10. Safe R0/R1 work: current product/pointer R0 repairs are closed (`SAFE_R0_REMAINING=0`). The bounded Yili H1 cash-quality review is recorded, but the multi-year ordinary-dividend/cash-coverage question and Shenhua restatement/scope bridge remain open; exact Midea consolidation eliminations and bank-product reconciliation remain unavailable external evidence, not an invitation to infer values.
11. Prospective v2 registration receipt: **MACHINE_VERIFIED** against `config/prospective-baseline-verification-v9.json`; `runtime/prospective-v2-fc1e811/receipt.json` matches SHA-256 `8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`, its committed plan bytes and Git ancestry validate, and it binds 000333/600887/601088 with `action=no_order`. Its `receipt_created_at` remains process-clock-only (`declared_time_independently_proven=false`), so this does not establish strict PIT.
12. Live repository source: this audit's `git fetch origin` failed to connect to GitHub port 443. HEAD remains `c9449a4fe8881a0cec9ce2f992622b48693c413a` on `main`; no checkout/pull was performed with the dirty worktree, and cached `origin/main` is not represented as a current live check.

Strict contemporaneous PIT remains `NOT_PROVEN`: registration and retrieval times are process-clock-only and unattested. All three valuations remain not ready. The total Goal remains active; R2, R3, R5 and R6 nodes remain scoped or future-gated. No private input, production authorization, Shadow run, Excel publication, or order is requested. Reopen market/event/product work only on the next completed session or a genuinely new, evidenced public fact. `action=no_order`.

## 2026-09-28 Yili H1 cash-quality reconciliation

Read-only Root review and independent SubAgent cross-check used the retained
CNINFO 2026H1 PDF `1225511409` (SHA-256
`423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`). The
new supplement is `docs/current/track-b-yili-h1-cash-quality-review-20260928.md`.
It matches revenue, consolidated net profit and operating cash flow by scope
and period; 2026H1 revenue grew 4.13%, consolidated net profit fell 23.66%,
and operating cash flow / consolidated net profit was 176.68% versus 40.97% in
2025H1. The two largest operating cash lines explain a +CNY 7.033bn arithmetic
change against a +CNY 6.795bn net CFO change, with the other operating lines
netting -CNY 0.238bn. No causal attribution is claimed.

The balance-sheet movements are 2026-06-30 versus 2025-12-31, not year-over-year;
the note marks this explicitly. CapEx less CFO is labeled a limited proxy, and
the equity distribution lines are not treated as proof of cash dividend paid
or sustainable payout. This narrows the financial-quality description but
does not change `BASELINE_PARTIAL`, `MODEL_NOT_READY`, `VALUATION_NOT_READY`, or
dividend `DATA_INCOMPLETE / UNKNOWN`. The registered baseline, receipt, event
ledger and canonical Excel remain unchanged; no event was admitted and no
workbook was published. `action=no_order`.

### Delegated R1 reviews — 2026-09-28

Two independent read-only SubAgent reviews were completed within the current
public-research scope:

- Yili 2026H1 liquidity bridge (`docs/current/track-b-yili-liquidity-bridge-review-20260928.md`): no material issue. The reviewer rechecked the cited CNINFO PDF hash and page offsets, recalculated the borrowing increase and bill-discount share (60.5%), and confirmed the note does not net deposits against debt or infer that liquidity risk is cleared. Research and valuation states remain unchanged.
- Midea notice `1225582141` (`docs/current/track-c-midea-egm-notice-20260928.md`): no broken source lineage. The official PDF at `runtime/prospective-public-event-20260927/gapfill-000333-20260927T172744007289Z/1225582141.PDF` hashes to `94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686`; the scan/review records and current projections bind that source. A conflicting `ee125e...` value found by text search is synthetic rejection-test content, not another official PDF. The reviewer confirmed the notice remains a bounded 2026-09-28 snapshot, with no inference of vote or implementation.

These are delegated research reviews, not user approvals, signed ACTUAL event
authorization, strict-PIT evidence, valuation approval, or trade decisions. No
files were changed by reviewers; no canonical workbook publication was needed.
`action=no_order`.

### Shenhua FY2025 source and admission-contract review — 2026-09-28

Two bounded read-only SubAgent reviews were completed for registered case
`601088`:

- Source review verified the retained CNINFO annual-report PDF at
  `runtime/prospective-baseline-20260927/shenhua-index-20260927T044701251789Z/shenhua-2025-annual.pdf`
  against SHA-256 `7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2`.
  It supported FY2025 coal sales of 4.309 hundred-million tonnes (430.9 million
  tonnes), average coal price CNY 495/t excluding tax (physical/printed p.30),
  self-produced coal unit cost CNY 171.6/t and self-produced-coal sales gross
  margin 40.0% (p.32), and power sales 207.00bn kWh at CNY 386/MWh (pp.33-34).
  The reviewer confirmed 2024 comparative figures are marked restated and the
  operating statistics are issuer disclosures, not each independently audited
  financial-statement facts. Coal sales include internal sales; 495/t is a
  group average, not an external-customer-only price. This supports the cited
  bounded observations only, not a normalized cycle, valuation, or dividend
  sustainability conclusion.
- Admission-contract review confirmed the existing item-level allowlist has no
  additional FY2025 operating metric types; current admitted headline facts
  (revenue, parent-attributable profit, and operating cash flow) are already
  present. The cycle metrics remain supplemental source observations, not
  admitted baseline/model inputs. No allowlist or verifier change was made.

The research card remains `BASELINE_PARTIAL`,
`CYCLICAL_MODEL_NOT_READY` / `VALUATION_NOT_READY`; the unadmitted generic
`shenhua-2025-operating-facts` placeholder is not promoted to a financial fact.
No Excel publication or research-state change was warranted. `action=no_order`.

### Track C: Shenhua CNINFO Watermark and Events

Append-only `config/prospective-public-event-watermarks-v4.json` preserves the
v3 history and records a gapless chain of seven retained exact-issuer CNINFO
query windows for 601088 from 2026-03-31 through the 2026-09-27 19:22:35 +08:00
retrieval point. Independent review and focused tests bind the query indexes,
raw response pages, page counts, `hasMore` termination, and referenced hashes.
The local v3 SHA-256 is
`f7f00ac96efab81c631c543d8ecb9ba98ff03a1d89c4371a8cd546d1cb9e7119` and v4
SHA-256 is
`a7dbb1f35a157a80daf202ed91537e7c8ae8b9c135c828ed4108c3cb39063cb8`. Both
files are currently untracked; v4 preserves the v3 records semantically, but
Git history does not establish v3 byte immutability.
The status is bounded to those retained CNINFO windows: it does not cover
issuer IR, exchange-site material, later corrections, or disclosures after the
last query time. These disclosures predate the prospective observation start;
the result is not strict contemporaneous PIT evidence.

R1 disposition for the four recovered 2026-09-01..22 indexed originals:

| CNINFO ID | Disposition | Evidence boundary |
| --- | --- | --- |
| `1225546779` | `MATERIAL_SUPPORTING_EVIDENCE` | Meeting materials propose a pre-tax CNY 0.98/share interim distribution, about CNY 21.256bn in total. |
| `1225565223` | `MATERIAL_RISK_MONITOR` | Issuer-reported August operating statistics; comparison period restated and scope includes assets consolidated from April. Monitoring only. |
| `1225567741` | `NONMATERIAL` | Registered office address change; no investment-relevant economic event identified. |
| `1225546775` | `AUDIT_ONLY` | Meeting procedure notice; no independent economic event beyond the meeting materials. |

The 2026-09-23 shareholder resolution `1225579981` separately confirms that
the interim-distribution proposal passed on September 23. The A-share
implementation, record date, ex-date, payment date, cash coverage and
sustainability remain unestablished. R1 confirmed the proposal is about 74.0%
of H1 parent-attributable profit under the stated accounting basis; this ratio
is context, not a dividend-sustainability conclusion, yield or valuation input.

Projection `runtime/prospective-public-event-20260927/shenhua-event-projection-v2.json`
has SHA-256 `1c88dd83902b766ac0c208f2b837fa157b91d40189a91a4ddb79bd33cf82a971`.
It projects the approved-but-not-yet-implemented interim distribution and the
restated issuer-reported August operations only. Publisher verification
recomputed evidence hashes and confirmed same-path publication with all
user-managed and frozen sheets preserved. Publication receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T161223Z.json`.
Backup and final canonical workbook share SHA-256
`522f6b11a01c2d87024c45496a4a6a3f3d101dba315274d34cb88167e7d3f6d6`.
WPS read-only receipt `runtime/publication-receipts/m7-shenhua-event-wps-readonly-20260927-v2.json`
passed; event evidence links target audit rows 34 and 36, and each evidence
title links to its CNINFO original PDF. Quote data remains the existing
partial bundle as of 2026-09-24; no 2026-09-28 close was inferred.

These changes do not alter any valuation, price assessment, trade state, strict
PIT status, M6 operation, M7 user acceptance, or total Goal completion:

```text
VALUATION = NOT_READY
STRICT_PIT = NOT_PROVEN
M6_OPERATIONAL = NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

### Track D: Registered-Company Events and Canonical Workbook

The quote binding now carries the pinned registration receipt SHA-256,
registration fingerprint, plan SHA-256, explicit bundle-finished PIT cutoff,
and per-symbol Tencent/Sina/calendar source URLs, fetch times, and raw SHA-256s.
It rejects evidence fetched after the bundle cutoff and future cutoffs. These
checks improve reproducibility; the machine clock is not an independent
timestamp authority and strict contemporaneous PIT remains NOT_PROVEN.

The append-only composite projection
runtime/prospective-public-event-20260927/registered-public-event-projection-v1.json
has SHA-256
ecdce96a4a63a72b191942896b751cbae0da3a4087b9f5ef871aea7b0333f3a0. Its eight
visible event cards cover Midea (3), Yili (1 evidence-gap card), and Shenhua
(4). Shenhua's added cards include the finance-company risk monitor (issuer
self-assessment only) and 2026-10-08 restricted-share unlock (existing shares,
not a new issuance or sell signal). Yili's materiality remains undetermined;
the CNY 21,801.09 difference, funding mix, accounting period, and share-right
treatment remain open. All cards retain evidence paths and SHA-256s, and every
projection action is no_order. Existing Shenhua v1/v2 projections were not
overwritten.

The same WORKBOOK_PATH file was updated in place. Publication receipt:
runtime/publication-receipts/canonical-m7-product-publication-20260927T170814Z.json.
WPS read-only receipt:
runtime/publication-receipts/wps-m7-product-readonly-20260928.json.
Workbook SHA-256 changed from 522f6b11…e7d3f6d6 to
f4b7a2721f2947a1e7b65087289c8660b48d6a423e32f22afabadd4edc748970.
WPS confirmed all six product sheets readable, no formula errors, allowed
decision wording, user/frozen sheets preserved, and workbook hash stability.
The workbook includes the three registered research companies alongside the
legacy two-company watchlist. Quote coverage remains partial at 2026-09-24;
600887 is missing from the admitted quote bundle, so no current quote or
decision is asserted for it.

A quote collection attempt at 2026-09-27T16:59:06Z returned the same
2026-09-24 close. The official 2026 SSE closure calendar marks 2026-09-25..27
closed, so this did not establish a new completed session and was not used for
publication. The non-advancing raw bundle is retained for audit; it does not
advance Track A.

Focused verification: registration/observation/quote and M5 product regression
sets passed (74, 44, and 37 tests in their respective runs); WPS read-only
verification passed. verify-only and final read-only WPS checks did not modify
the canonical file.
The final combined registration, PIT, quote, event-projection, product-model,
and workbook regression run passed: 104 tests.

### 2026-09-28 Single-Day Midea Notice and Product Consistency Successor

CNINFO exact-issuer scan for 2026-09-28 returned one Midea announcement
(`1225582141`), zero Yili announcements, and zero Shenhua announcements. The
Midea source PDF SHA-256 is
`94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686`; the
single-day scan, index, raw response and document-review JSON are hash-bound.
The notice schedules a 2026-10-13 shareholder meeting and lists restricted-
share cancellation and interim-dividend agenda items. Those are proposals;
this notice establishes no vote result, cancellation quantity/completion,
dividend amount, approval or implementation. It creates a bounded monitoring
trigger only. See `docs/current/track-c-midea-egm-notice-20260928.md`.

An immutable Midea notice projection successor and registered composite v2
were built from the pinned sources. Composite hash:
`f5938dc5b381230efd686078c923b8b4d0aab3562148f33ccbfa6c4749a12609`;
it contains nine event cards. The notice observation is strictly one exact-
issuer CNINFO snapshot; Midea's formal watermark remains `INCOMPLETE` and was
not advanced. Continuous, full-day, multi-channel and strict-PIT coverage are
not claimed. Valuation, dividend sustainability, share-count inputs and
decision state did not change; `action=no_order`.

Product review findings were fixed in code/tests: opportunities and company
pages now share exactly the three registered companies when a verified
prospective snapshot is present; legacy items are labeled as historical/old
source; evidence groups expose every referenced source, hash and URL; Midea
source URLs flow to audit rows; an unavailable Yili official URL remains null
rather than being guessed. A duplicate-input check also caught and corrected a
legacy company-card leak before publication.

Publisher verify-only passed with the existing 2026-09-24 quote bundle and
2026H1 baseline. The same WPS canonical workbook was updated in place, with
user-managed and frozen sheets unchanged. Publication receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T180756Z.json`.
Canonical hash changed from `f4b7a272...c748970` to
`b1c52fde...f6f1883d`. WPS opened the file read-only, calculated all six
product sheets, found no formula errors, and confirmed hash stability; receipt:
`runtime/publication-receipts/wps-m7-product-readonly-20260928-event-v2.json`.
Independent openpyxl read-back located the new event at `05_事件!42`, linking
to audit row `06_系统与审计!A44`; that row contains the official CNINFO URL,
announcement ID, original SHA-256 and available date. No quote refresh was
claimed; 600887 remains missing from the 2026-09-24 bundle.

The current-trial pointer now names the composite-v2 observation separately
from `public_event_as_of=2026-09-27`, preserves the formal watermark boundary,
and records `public_event_observation_as_of=2026-09-28` with
`SINGLE_DAY_SNAPSHOT_ONLY`. The current artifact navigation registry is v2;
it resolves local `WORKBOOK_PATH` by hash without recording the user's absolute
path, while the tracked root workbook is only a repository reference snapshot.
Registry SHA-256 is `41561a2338a74073607773f8d90d22f7fa8dba7fc326feed7c73eee48cb4159b`;
rebuilding twice produced the same hash, and the v1 historical snapshot hash
remains `ce31a4b673f51101c43b89388a11653d1ad17f0564b32f95af7f557f345752d1`.

Midea's FY2025 / 2026H1 CapEx and fixed-assets review found no basis to split
maintenance from growth CapEx or produce normalized CapEx; those remain
`UNKNOWN`, and FCFF/model applicability and valuation remain `NOT_READY`. See
`docs/current/track-b-midea-capex-fixed-assets-review-20260928.md`.
Strict PIT remains `NOT_PROVEN`, M6 operational validation has not started,
M7 final user acceptance has not passed, and `action=no_order`.

## 2026-09-28 SubAgent-Assisted Continuation Audit

### Completed bounded R1 follow-ups and PIT record-time hardening

- Track B R1 independently checked Yili 2026H1 liquidity disclosures against retained CNINFO PDF `1225511409` (SHA-256 `423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`). The supplemental note `docs/current/track-b-yili-liquidity-bridge-review-20260928.md` records statement/notes page mapping and arithmetic: short-term borrowing rose CNY 19.0466bn; bill-discount borrowing rose CNY 11.5264bn (~60.5% of the increase); cash fell CNY 2.8782bn; the two identified deposit balances fell by about CNY 2.4794bn combined. It does not net deposits against debt because entity, currency, maturity, restriction, and transferability matching is missing. Valuation remains `NOT_READY`; dividend capacity `UNKNOWN`.
- Track C R1 independently confirmed CNINFO `1225531407` is second support for the existing Midea interim-dividend proposal, not a new event. The supplemental disposition is in `docs/current/track-c-public-event-gapfill-20260927.md`; shareholder approval, implementation, payment, and cash sustainability remain unproven. The existing canonical event card still links to `1225531406` and correctly labels the proposal as pending. No workbook publication was made because this evidence adds no changed product decision/state; a later event-card evidence consolidation must be an append-only projection successor and go through the canonical publisher.
- PIT observation writing now emits `prospective-public-observation-v2`, separating source `observed_at` from writer-generated UTC `record_created_at`. Historical readers require both record creation and source availability to be at or before cutoff; v1 observations without record-creation evidence are retained byte-for-byte but never admitted to PIT output. A successor may hide its predecessor only when that successor itself is visible by cutoff; source-observation times may be equal, while v2 record-creation times must be strictly ordered. Deterministic IDs and immutable replay behavior are retained. This does not retroactively establish M3 strict PIT; legacy chain status remains unproven.
- Focused observation regression: `11 passed` using a repository-local pytest basetemp. This validates bounded writer/reader behavior only, not M3 or the real-world trustworthiness of the local clock.

Three bounded independent reviews were used for Tracks B, C and D; the root
thread reconciled their findings against retained sources and current
artifacts. No agent edited files or published the workbook.

- **Track B:** CNINFO `1225578520` was page-checked against the retained PDF
  (`runtime/prospective-public-event-20260927/20260927T004835372Z/600887-1225578520.pdf`,
  SHA-256 `7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`)
  and board resolution `1225259570` (SHA-256
  `7369a05f737a7c786b226237a5149d59b0a243619bc005a5a94e660bae94f697`). The
  completion notice states 8,476,357 existing shares bought at an average
  CNY 26.5441 per share for CNY 224,997,098.71 excluding fees, with a
  12-month lockup. The board resolution states CNY 225,018,899.80 of after-tax
  award funds transferred to the plan account. The CNY 21,801.09 difference
  remains unexplained; these records do not establish the actual funding mix,
  gross expense/recognition period, or share-voting/dividend rights. This
  purchase is not a new issuance and does not change the ordinary-share
  denominator by itself.
  **Integration check:** all of these facts and limitations are already in
  `docs/current/track-c-public-event-scan-20260927.md`,
  `docs/current/track-b-yili-impairment-and-proceeds-review-20260927.md`, and
  the 600887 `EVIDENCE_GAP` card in the current composite projection. The
  delegated scan therefore adds no state change; do not create a duplicate
  observation, revise valuation, or republish Excel. Reopen only on a formal
  settlement disclosure or a financial report covering the post-purchase
  period.
- **Track C:** no immediately executable non-duplicate event task was found.
  Midea notice `1225582141` awaits the 2026-10-13 meeting result and separate
  implementation disclosures; Shenhua's planned 2026-10-08 share unlock
  awaits actual listing/capital evidence. The existing 600887 evidence gap
  waits for a settlement or subsequent report. No watermark is advanced.
- **Track D:** read-only review found the Midea notice card at `05_事件!A42`
  links through `F42` to `06_系统与审计!A44`, where the official URL, document
  ID and source SHA-256 are present. The canonical file/config/publish/WPS
  receipts agree at SHA-256
  `b1c52fde10ba228c84c476411c8aaf6397dcd6f67beb0280bc3af388f6f1883d`.
  No product defect or verified data-state change was found; no republish.
- **Track A:** no new completed exchange session was established at this
  checkpoint. Retain quote-as-of `2026-09-24`, partial coverage, and missing
  `600887`; do not represent the old bundle as fresh.
- **Interruption audit:** current work does not require R2; R2 remains parked
  only for personalized M4. Tracks B-D remain active as future public evidence
  and event triggers arrive. Track A reopens after a completed session.
  Registered ResearchCase scaffolds exist, but unresolved facts/assumptions
  keep all three valuations `NOT_READY`. No current local safe R0/R1 action was
  identified. R3 production, R5 final acceptance, and R6 natural-time nodes
  remain separately parked; M6 operational stays `NOT_STARTED`, strict PIT
  stays `NOT_PROVEN`, and `action=no_order`.

The requested objective commit `269f93f1f7cd107f82de55ed795b476ab56b492f`
is an ancestor of the locally cached `origin/main` (`c9449a4`). A fresh fetch
attempt failed because GitHub port 443 was unreachable in this continuation;
the local worktree contains 83 changed paths. No checkout, pull, reset, or
push was performed, and all uncommitted work was preserved.

## 2026-09-27 Prospective Stage Interruption Audit (Historical)

At the 2026-09-27 checkpoint, the interruption audit concluded that R2 parked
only M4 and was not a total Goal or public-research blocker. This snapshot is
superseded by the 2026-09-28 current header and evidence update above. The
M4 private-input boundary remains closed:
no IPS, holdings, cash, cost basis, account information, risk preference,
private key, or private root was requested or inspected.

| # | Question | Current answer | Evidence / action |
| --- | --- | --- | --- |
| 1 | Does current work require R2 private data? | `NO` | Public filing review and public-product integration only. |
| 2 | Does missing R2 block only M4? | `YES` | `M4_PERSONALIZED=PARKED_WAITING_R2`; M4 synthetic/nonpersonalized work remains separate. |
| 3 | Can Track A continue? | `YES, CONDITIONALLY` | Quote bundle remains raw-revalidated but partial as of 2026-09-24; 600887 is missing. 2026-09-27 is Sunday and no new completed exchange session is available; do not duplicate or relabel the old bundle. |
| 4 | Can Track B prospective research continue? | `YES` | Three registered baselines and observation ledgers exist. Strict contemporaneous PIT remains `NOT_PROVEN`; 600887's 1225578520 is pre-start material and not a new prospective fact. Unresolved model inputs keep all three valuations not ready. |
| 5 | Can Track C public-event research continue? | `YES` | 600887's v3 query covers 2026-09-23..27; 000333 has adjacent bounded coverage from 2026-03-31..09-27; 601088 remains `INCOMPLETE`, with unfilled intervals 2026-04-01..06-25 and 2026-09-01..09-22. Four indexed 601088 records in the latter interval have not been matched to local originals/review records. Do not rescan covered windows or advance its formal watermark. |
| 6 | Can Track D Product / Excel continue? | `YES` | A verified 601088 historical risk-monitor projection was published to the same canonical workbook. The initial WPS check found an evidence link pointing to a blank row; the shared-layout mapping and source-URL display were fixed, tested, and republished. Final digest `01af2106d8e1a656750790b0d1f7ee79fd8264c9f24d5bd1d28899aa90eefee1` passed WPS read-only checks and exact link-target verification. |
| 7 | Is there unprocessed public evidence? | `YES` | The four existing 601088 index rows remain without local originals/document-level dispositions. CNINFO 1225185584 has now been source-hash checked and boundedly reviewed; it is not a new observation. |
| 8 | Is a ResearchCase baseline incomplete? | `NO` for baseline scaffold | Each of 000333, 600887 and 601088 has a versioned baseline and explicit admitted/unadmitted facts. Company valuation and unresolved assumptions remain explicitly `NOT_READY`, not filled with defaults. |
| 9 | Is there a current public announcement to research? | `NO newly disclosed after the last bounded scans` | Existing available records include pre-start historical material; next research should process uncovered indexed evidence, not duplicate completed queries. |
| 10 | Is any safe R0/R1 work executable? | `NO ADDITIONAL LOCAL ACTIONABLE ITEM IDENTIFIED` | The bounded evidence-row/source-URL product repair is complete. R0-A still requires original M5 dependency/recalculation inputs; R0-B requires CI artifact bytes and privacy-boundary evidence that are unavailable locally. Those missing inputs do not stop Tracks A-D. |

### Current Public Evidence Disposition

The R1-reviewed CNINFO `1225185584` is dated 2026-04-24 (conservative
available date 2026-04-25), before the observation start. Its PDF SHA-256 is
`6fce900be4fa9ea2a169513f01911d4bb47bb4f4dff9914873601a8f0d1f02af`; the
scan-evidence SHA-256 is
`4754e360349f74640412a12f5fffc5ddb1af81dc0e22e84c5b28caf98c71dfb4`. It
identifies a related finance company and group-member deposits/services; the
issuer's report says no non-performing loans as of 2025-12-31, which is
self-assessment rather than independent credit assurance. It is classified
`MATERIAL_RISK_MONITOR` with no allegation of loss, no valuation change, no
baseline admission, and `action=no_order`. Detailed findings are in
`docs/current/track-b-shenhua-operations-and-capital-allocation-20260927.md`.

The 601088 projection is
`runtime/prospective-public-event-20260927/shenhua-finance-risk-projection-v1.json`
(SHA-256 `8368f16f59aac209005effb001ce017233dc57742952cb53fff6c9282b5ed12f`).
Publisher receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T153228Z.json`.
It replaced the provisional 2026-09-27 15:12 publication only on the same
canonical path. Backup SHA-256 is
`6ca2dfdff1cfe68f63c9e2bdc191587b060c968b216b76d7ef00b20952faa224`; final
canonical SHA-256 is
`01af2106d8e1a656750790b0d1f7ee79fd8264c9f24d5bd1d28899aa90eefee1`.
The final WPS read-only receipt is
`runtime/publication-receipts/m7-shenhua-risk-wps-readonly-20260927-final.json`
(`status=passed`). It opened the workbook read-only, checked the six product
pages, freeze panes, formula-error and forbidden-decision tokens, required
valuation/portfolio states, and workbook hash stability. A separate read-only
cell/link check confirmed the 05_事件 link points to
`06_系统与审计!A34`, whose first evidence ID is `scan-1225185584`; the
`pdf-1225185584` audit title has a clickable HTTPS link to the original CNINFO
PDF. The publisher reports `user_managed_sheets_preserved=true` and
`frozen_sheets_unchanged=true`. No personal/manual cells were read or changed.

The focused regression suite passed `64 tests` across workbook rendering,
read-model, event projection, canonical binding, and product-candidate layers.
The first local run hit `PermissionError` in an existing shared pytest temp
directory; rerunning with an isolated temp directory inside `runtime/` passed.

`M6_OPERATIONAL=NOT_STARTED`, `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`,
`INITIAL_ASSISTED_USE=NOT_REACHED`, and `action=no_order` remain unchanged.

## Historical R0 Audit Metadata (NON_CURRENT)

```text
R0-A_REAL_M5_RECEIPT_BINDING = NOT_PROVEN
R0-B_CONTENT_LEVEL_PRIVACY = PARTIAL
R0-C_RESOURCE_CAPACITY = CLOSED_AS_R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 2
SAFE_R1_REMAINING = 0
EXTERNAL_GATE_HANDOFF = NOT_READY
LATEST_HEAD = c9449a4fe8881a0cec9ce2f992622b48693c413a
LATEST_CORE_RESEARCH_GATES = 36282732643 / success / HEAD_ONLY
```

## Historical R0 Interruption Audit Snapshot — 2026-09-27 (NON_CURRENT)

At that prior checkpoint, the user re-authorized `STAGE-FINAL-R0-EVIDENCE-CLOSURE-AND-EXTERNAL-GATE-HANDOFF`.
`git fetch origin` completed; `HEAD` and `origin/main` both remain
`c9449a4fe8881a0cec9ce2f992622b48693c413a`. The dirty worktree was preserved;
no checkout, pull, commit, or push was performed. Current stage is not complete.

### R0-A — Real M5 Receipt Binding: NOT_PROVEN

The ACTUAL run receipt exists at
`runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json`
with recomputed file SHA-256
`b93ea107489c3ddecca4eb876547a45e44dac8e379f86de9f740db4b16a31b56`. Its two
referenced 600519 source PDFs rehash to
`24e51c43dfc6da7d3a19c67b88081715a3a3b4a26c2d83ec51a557e3e5692873` and
`0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6`.
This proves archived bytes, not an admissible current Product lineage. The
current canonical publication receipt binds M5 projection bytes
`2fd02d763b75e078073a6c0739cb52745bdccb5b3d92c3c25ed1520566ad1cac`, which
are the 000333 historical public projection, not this 600519 ACTUAL run.

The ACTUAL application used the legacy offline-authorization path, which is
now limited to read-only historical replay; the current production trust-root
pin registry is empty. The original verified-facts/dependency/recalculation
inputs needed to revalidate the run are not all present. Current product code
still accepts a caller-supplied projection. Synthetic projection and durable
replay tests do not bridge that gap. Two independent reviews therefore keep
R0-A open. Exact reopen condition: an admissible verified M5 event input with
all original graph/plan/verified-facts/bounded-recalculation and review bytes;
then rehash receipt/source/review/evidence bytes and prove issuer/event identity
through an issuer-neutral adapter, product read model and Excel with tamper
negative cases. Do not recreate missing originals or use legacy replay as a
current event.

### R0-B — Content-Level Privacy: PARTIAL

The redacted context report
`runtime/privacy-context-classification-20260927-exact.json` has SHA-256
`41f96e1cabb7700d2692ac6152f46b1e7660ae4188b02ea78d58aad2292d18f9`. It scans
34 tracked workbooks and reconciles 162 raw-only fingerprints: 154 are only
rule-labeled potential public values, 5 have private-context hits, and 3 are
unknown. Independent review blocks all 8 unresolved fingerprints; no raw
candidate values were disclosed or accepted as public.

For successful Core Research Gates run `36282732643` on HEAD, GitHub exposed
one 3,368-byte synthetic restore artifact by metadata, but log download returned
403 and artifact-byte download returned 401 in the independent check. Their
contents remain unverified. M4 separation is verified only at the code/rule
level; no real private package was inspected. The current `WORKBOOK_PATH` was
resolved without disclosing it: it exists under the WPS Drive and outside the
repository, is not Git-tracked, and its current bytes hash to
`8bd50bd832802d00b73c12fdc6ac0ea04843d0f8f6cd59f36913e47b9f9eafb3`, matching
the publication receipt. The WPS read-only receipt says `passed`, but does not
record that exact workbook digest; user-managed content's exclusion from
runtime/CI/public receipts is not fully proven. Do not inspect or disclose
private cell contents to close this gap.

Exact reopen conditions: independently substantiate each of the 8 redacted
candidate classifications without exposing source values; obtain accessible
CI log and artifact bytes and scan them without logging content; prove the M4
private root/key boundary without opening private values; and bind the exact
current WPS workbook digest/read-only check while proving user-managed regions
are excluded from Git, CI artifacts, runtime publication and public receipts.

### Verification and Remaining DAG

Focused offline regression in an isolated project-local temp directory:
`88 passed, 12 skipped`. The skipped cases require unavailable original M5
verified-facts/recalculation inputs and are not passes. The committed HEAD's
Core Research Gates run `36282732643` is green; it does not cover the dirty
worktree. No Excel publication occurred. Current machine and reviewer evidence
leaves exactly `SAFE_R0_REMAINING=2` (R0-A, R0-B) and
`SAFE_R1_REMAINING=0`; R0-C remains closed as an R3 resource decision. No new
External Gate Handoff is generated while either safe R0 remains. Preserve
`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`,
`INITIAL_ASSISTED_USE=NOT_REACHED`, and `action=no_order`.

| DAG_NODE | CURRENT_STATUS | WHY_REQUIRED | WHAT_IS_ALREADY_DONE | EXACT_EXTERNAL_INPUT | REOPEN_CONDITION | WHAT_CAN_CONTINUE_IN_PARALLEL |
| --- | --- | --- | --- | --- | --- | --- |
| R0-A real M5 receipt binding | `NOT_PROVEN` | Product must not accept caller-authored event state or historical replay as a current verified M5 event. | Archived ACTUAL receipt and its two source PDFs rehash correctly; existing durable replay and synthetic projection regressions pass. | A provenance-eligible M5 event artifact set with original graph, plan, verified facts, bounded recalculation and review bytes; no private data or production authorization is requested here. | All referenced bytes verify, issuer/event/state bindings are replayable from upstream evidence, and positive plus tamper-negative tests pass through Excel. | R0-B may proceed independently; keep investment conclusions and Excel bytes unchanged. |
| R0-B content privacy and boundary | `PARTIAL` | Public Git/CI/runtime must not carry private values, and unresolved numeric candidates cannot be presumed public. | Tracked text/OOXML scan and redacted context classification exist; canonical path is confirmed under WPS and outside the repository; current file hash matches its publication receipt. | Accessible CI log and artifact bytes; evidence for the 8 redacted candidate classifications; exact-digest WPS read-only receipt and proof that user-managed content is excluded from Git/CI/runtime/public receipts. Do not supply raw personal values. | Independent bounded review accepts each candidate or records only explicitly bounded safe unknowns, CI content passes, and M4/WPS boundaries are hash-bound and independently verified. | R0-A may proceed independently; do not read private cells or republish the canonical workbook. |

## Prior stage evidence — 2026-09-27 prospective PIT, event-watermark and Midea related-party audit

Three bounded independent SubAgent reviews plus a local original-document
review advanced the active public-research DAG. This is a research/evidence
checkpoint only; it does not complete the total Goal or alter the canonical
workbook.

- **PIT audit:** v2 registration receipt SHA-256
  `8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`
  records process-clock `receipt_created_at=2026-09-27T00:24:16.082830Z`
  (08:24:16 China time), while `declared_registered_at` and the three cases'
  observation starts say 08:45. The declared time is not independently
  attested. v13's 18 report facts have source publication dates before cutoff,
  but their retrieval/ledger observation times are after cutoff. Only Yili has
  two observation JSONs; both bind the same pre-start CNINFO `1225578520` and
  the successor corrects its classification to a re-observed preexisting
  document. It is not two new prospective facts. No new valid post-start
  observation was found. Strict contemporaneous PIT remains `NOT_PROVEN`.
- **Midea investor event:** within the exact issuer CNINFO archive for
  2026-08-29..09-27 (8 records, complete pagination) and the issuer IR pages
  reviewed, no post-event Q&A/meeting record or transcript was located for the
  2026-09-15 event. The search did not include the event organizer's platforms,
  social media or inaccessible/unpublished video, so this is a bounded search
  result, not proof of global nonexistence. The 09-11 notice `1225557650` is a
  scheduling notice only and is not treated as Q&A evidence.
- **CNINFO watermark audit:** 000333 verified indexes cover the bounded,
  contiguous interval 2026-03-31..09-27, but do not establish coverage before
  03-31 or connect to the old watermark whose evidence was a registration
  receipt, not a query receipt. 601088 verified indexes only support separate
  windows 03-31, 06-26..08-31, and 09-23..09-27; gaps remain 04-01..06-25 and
  09-01..09-22. Both formal watermarks remain `INCOMPLETE`; no coverage is
  inferred for issuer IR, exchange sources or corrections. Details and hashes
  are recorded in `docs/current/track-c-public-event-scan-20260927.md`.
- **Midea related-party originals:** CNINFO `1225058114` (2025 related-party
  balances; SHA-256 `d1cec190f2507099b45ebdc17f3d0a7f692463888a25d9e6ca78ce5519a45e5e`)
  and `1225058125` (2026 ordinary related-transaction estimate; SHA-256
  `2d3c2172110a70e34d104015f1b9ff3facde5fbd88f0c54c648aa64ce34ece17`) were
  downloaded and visually reviewed. The former's CNY 34.521bn balance total
  includes subsidiary receivables; a separately listed CNY 6.294bn
  related-bank financial-asset balance is not proven unrestricted industrial
  cash. The latter estimates up to CNY 2.15bn of 2026 component/smart-home
  procurement, versus CNY 1.547bn actual in 2025. Neither reconciles
  finance-company standalone accounts,
  consolidation eliminations, encumbrance/maturity, or industrial/financial
  debt allocation. The source disclosures predate the registered cutoff but
  were re-retrieved after it; they were not backfilled into v13 or counted as
  post-start observations. Midea remains `MODEL_NOT_READY` /
  `VALUATION_NOT_READY`.

No watermark, baseline, observation, valuation or workbook was changed.
`STRICT_PIT=NOT_PROVEN`, `000333_WATERMARK=INCOMPLETE`,
`601088_WATERMARK=INCOMPLETE`, `M6_OPERATIONAL=NOT_STARTED`,
`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`,
`action=no_order`.

### M5 product projection binding and source correction — 2026-09-27

Independent original-PDF review corrected one factual transcription in
`docs/current/track-c-public-event-gapfill-20260927.md`: CNINFO `1225544342`
reports CNY 87.71 as the highest and CNY 73.66 as the lowest repurchase price;
73.66 is not the average. The other reviewed event descriptions remain bounded
and unchanged. A targeted search found no other occurrence of that incorrect
average-price claim.

The canonical product publisher now accepts an optional M5 event projection
only when its JSON is under `runtime/`, its exact SHA-256 is supplied, and its
top-level action is `no_order`. The exact same loaded projection is passed into
both `--verify-only` and `--publish`; the existing candidate layer continues
to validate each referenced evidence file and hash. This is projection wiring,
not M5 ACTUAL authorization, prospective-observation registration, production,
or an investment conclusion. Targeted projection/publisher tests passed
(`21 passed`). The projection was also built from the retained CNINFO files and
passed the publisher's in-memory verification. An initial publication without
the v13 snapshot was rejected by the WPS content assertions; the previous
canonical file was preserved in the publisher backup. The corrected publication
included both the unchanged v13 snapshot and event projection. Receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T124434Z.json`.
Final canonical SHA-256 is
`65dc6770cf6c2e0895aba348025940696cb64bfe2f897c985f9254704be137ac`;
backup SHA-256 is `6e895d4a11baf8e272f49c25548cbedaa7625281d42bb491efe2e78e4323d269`.
WPS read-only verification passed and its receipt is
`runtime/publication-receipts/m7-midea-event-wps-readonly-20260927.json`.
The product event page now includes the three historical, pre-registration
items, and the audit page retains local source paths and hashes; it still has
no direct source-URL field. This does not alter the prospective ledger.
All three valuation states remain `VALUATION_NOT_READY`; strict PIT remains
unproven; M6 remains `NOT_STARTED`; M7 final user acceptance remains
`NOT_PASSED`; `action=no_order`.

### Midea R1 dispositions and canonical publication — 2026-09-27

An independent research reviewer confirmed the source-supported classifications:
CNINFO `1225531406` is `MATERIAL_SUPPORTING_EVIDENCE` (proposal only);
`1225544342` and `1225544482` are `MATERIAL_RISK_MONITOR`. None justifies an
immediate valuation recalculation, changed share-count/expense input, or trade.
The product read model now distinguishes these dispositions and presents them
as `MONITOR` with document-specific reopen triggers, rather than implying a
pending human review. The detailed bounded rationale is in
`docs/current/track-c-public-event-gapfill-20260927.md`.

The new immutable projection is
`runtime/midea-public-event-projection-v2-20260927.json` (SHA-256
`2fd02d763b75e078073a6c0739cb52745bdccb5b3d92c3c25ed1520566ad1cac`). It
remains explicitly pre-registration historical evidence and does not write the
prospective ledger. Canonical publication receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T131204Z.json`.
The publisher preserved all non-product/manual sheets. Final workbook SHA-256:
`8bd50bd832802d00b73c12fdc6ac0ea04843d0f8f6cd59f36913e47b9f9eafb3`;
the verified source baseline snapshot remains v13 SHA-256
`ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`.
WPS read-only validation passed at
`runtime/publication-receipts/m7-midea-r1-dispositions-wps-readonly-20260927.json`.
The Excel evidence audit still has no direct URL field; it retains local paths
and source hashes, while official URLs are preserved in the projection report.
No research valuation, price assessment, decision, portfolio state, or order
was changed; `action=no_order`.

### Prospective research follow-up — 2026-09-27

The Midea supplemental baseline card now records a bounded consolidated
cash/financial-asset bridge from the audited FY2025 and unaudited 2026H1
reports. It separates balance-sheet monetary funds, cash-flow-statement cash
and equivalents, interbank deposits, restricted monetary funds, total
restricted assets, fair-value-measured financial assets, and current portions
of non-current assets. Parent-company and consolidated balances are explicitly
not added together. This narrows interpretation risk but does not establish an
industrial net-cash/net-debt amount: finance-company standalone statements,
business allocation, consolidation eliminations, maturity/encumbrance and
industrial-versus-financial debt remain unresolved. No amounts were admitted
to the baseline; Midea remains `MODEL_NOT_READY` / `VALUATION_NOT_READY`.

A complete exact-issuer CNINFO calendar-year query for Yili 600887 returned 132
records across five pages (retrieval index SHA-256
`25be88f33af9e9bbe110d506efab95e3d0eec9d3a1959d1c521d88f143c455e2`). It
identified the 2025-04-30 project-extension notice, board resolution and
sponsor verification, plus the 2025-05-21 annual-shareholders' resolution.
The retained originals corroborate the disclosed governance path for the
December 2027 expected-use date. The same 2025 notice table and the 2026H1
report table both say `不适用`; the mismatch remains unresolved, and there is
no evidence of actual project completion. This is pre-registration historical
evidence only. The report-level Yili claim remains unadmitted, baseline v13 and
observation ledger are unchanged, and Yili remains
`BASELINE_PARTIAL` / `VALUATION_NOT_READY`.

An independent read-only review of Shenhua 601088 confirmed that the current
2014-2025 evidence supports cycle description but not a comparable
cycle-normalized profit series. BSPI/NCEI are distinct index series; operating
prices, costs, volumes, power-segment breaks, 2024 restatements, maintenance
capex and parent-available cash are not fully reconciled. No normalized
earnings or valuation was generated; `VALUATION_NOT_READY` remains correct.

Targeted prospective registration, observation, baseline, event-watermark,
public-event, product-projection and quote-binding regressions returned
`106 passed`. `git diff --check` passed before these documentation-only
follow-ups; final check is recorded with this change. There was no new
completed exchange session and no new verified event requiring a canonical
workbook publication. The canonical workbook hash and all three valuation
states remain unchanged; `action=no_order`.

Historical R0 checkpoint (not the current stage):
R0-A_REAL_M5_RECEIPT_BINDING = NOT_PROVEN
R0-B_CONTENT_LEVEL_PRIVACY = PARTIAL
R0-C_RESOURCE_CAPACITY = CLOSED_AS_R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 2
SAFE_R1_REMAINING = 0
EXTERNAL_GATE_HANDOFF = NOT_READY

R2 parks only M4 and is not a global blocker. Public research, prospective PIT,
bounded public-event research and the canonical workbook are active under the
current stage authorization. R0-A/R0-B remain unresolved DAG nodes; they must
not be represented as passed, but do not stop independent public work.

## Current Public-Research Increment — 2026-09-27

Bounded exact-issuer CNINFO queries for 2026-09-27 were repeated once later in
the same day to check for late-day filings. All three returned HTTP 200,
complete pagination and zero announcements; this adds no event, does not repair
the earlier continuity gaps for 000333/601088, and does not advance the
registered watermarks. Raw page SHA-256 is
`c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114` for each
empty response. The per-run indexes are:

- 000333: `runtime/prospective-public-event-20260927/gapfill-000333-20260927T112218728018Z/index.json`, SHA-256 `65cfb6fc268bf07fbc11462ae5cdb51f31fa1d59ce4bcfea7ef9122b865b066c`.
- 600887: `runtime/prospective-public-event-20260927/gapfill-600887-20260927T112225298646Z/index.json`, SHA-256 `4ad9a1190190322d339d9b8f2ee88e7728ede73055a0af54f68e9fc7b1c00b67`.
- 601088: `runtime/prospective-public-event-20260927/gapfill-601088-20260927T112235104724Z/index.json`, SHA-256 `e2c3b27cc18386024e27e349790df0478852271cca720647308a43dd22ceb9cc`.

The Midea and Yili cards now explicitly enumerate known facts, assumptions,
unknowns and reopen triggers alongside quality, counterevidence and model
readiness. Shenhua's separate cyclical card remains authoritative for its
normalization gaps. No new facts changed the v13 baseline or canonical workbook;
no publication was warranted. Regression for registration, baseline admission,
observation PIT, bounded event scans/watermarks and product projection returned
`80 passed` using isolated basetemp `runtime/pytest-goal-20260927-a`.

### Midea bounded filing review — 2026-09-27

An exact-issuer CNINFO gap fill for 000333 over 2026-08-29..2026-09-27
returned 8 records with complete pagination. Three follow-up originals were
downloaded, SHA-256 recorded, and visually reviewed; text extraction was not
used because embedded-font decoding was garbled. The 2026 buyback progress
notice reports 99,797,967 shares / 1.31% through 2026-08-31 for CNY
8,019,722,850 excluding fees; its disclosed purpose is cancellation/reduction
of registered capital, but final cancellation is not evidenced. A separate
2025 buyback supplied 15,772,385 existing shares / 0.21% to the employee plan,
locked through 2028-09-02; future share-based-compensation expense is
unquantified. The investor-reception notice establishes only the scheduled
event; Q&A content remains unreviewed. The interim dividend remains a
proposal; this bounded result contains no later approval or payment notice.
The 2026H1 related-party schedule (CNY 10,000 units) totals CNY 35.271bn at
period end, including a CNY 24.980bn subsidiary balance and a separate
related-bank financial-product line with CNY 6.294bn opening and CNY 2.644bn
ending balances. Entity/consolidation
scope and accounting must be reconciled; neither figure alone proves external
receivable exposure, misappropriation or stress. Source IDs, hashes, event
dispositions and limitations are recorded in
`docs/current/track-c-public-event-gapfill-20260927.md`.

These documents were public before the registered observation start and are
not new prospective observations. The 000333 watermark remains `INCOMPLETE`;
no baseline/valuation/decision input changed and no canonical publication was
warranted. A later direct disk hash and current WPS read-only verification are
recorded below; neither constitutes final user acceptance. `action=no_order`.

### Canonical registration identity note — 2026-09-27

The three-case baseline/publication chain uses
`runtime/prospective-v2-fc1e811/receipt.json` (SHA-256
`8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5`),
as confirmed by publication-v7 and verification-v9 bindings. Its
`receipt_created_at` is process-clock evidence only, not an independent
timestamp attestation; strict contemporaneous PIT remains `NOT_PROVEN`. The
separate `runtime/prospective-research-registration-20260927/receipt.json`
(SHA-256 `e8f8f8cdab90c7cc020683b54f0901d342eff2329923242c0ac6f9a686e6d039`)
is a v1 receipt with a declared 09:30 China-time cutoff and is not referenced
by the current v13 publication chain. Do not treat it as the active cases'
registration or time anchor. Both immutable receipts are preserved unchanged.

### Earlier verification snapshot — 2026-09-27 (superseded by later publications)

At the time of this earlier checkpoint, the canonical workbook matched the then-latest publication receipt
`runtime/publication-receipts/canonical-m7-product-publication-20260927T093345Z.json`
at SHA-256
`68b218ed233973e0151fee747f822a485ca9a79f6a1bef69240f4361c66dc867`.
The repository's read-only WPS UX verifier passed against these exact bytes;
receipt is
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T-current.json`
and records the same SHA, 61 sheets, required six leading product sheets,
formula/layout/wording checks and `final_user_acceptance=NOT_PASSED`. The current
workbook was unchanged at that checkpoint. This snapshot is superseded by the
13:12 publication record below; it remains here only as historical evidence.

Current-data check: the official SZSE September 2026 monthly calendar response
(`runtime/exchange-calendar-probes/20260909T020102864128Z/2026-09.bin`, SHA-256
`8c8482e9cdbbab6177af9b19cdbd38f2affa7e6a8d441df67b082b20f8698bc0`;
`https://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=2026-09`)
marks 2026-09-25 closed (`jybz=0`). SSE's official 2026 closure notice also
states 2026-09-25..27 closed. Thus the retained 2026-09-24 quote is still the
last completed exchange session; no duplicate or stale quote refresh was run.
The next scheduled session is 2026-09-28, subject to its actual completion.

Focused regression at that earlier checkpoint: `79 passed` across prospective
registration, baseline admission, observation/PIT, public-event scan,
watermark-manifest and product projection tests. `git diff --check` passed.
Later in this Goal continuation, `git fetch origin` succeeded and confirmed
local `main` and `origin/main` both at `c9449a4fe8881a0cec9ce2f992622b48693c413a`.
The working tree still contains extensive pre-existing modifications, so no
checkout, pull, commit or push was performed.

```text
PUBLIC_RESEARCH_OPEN_NODES = reconcile Midea related-party/financial-asset schedule to consolidated notes and eliminations; resolve the existing Yili project completion-date discrepancy and one unadmitted report-level claim; strengthen Shenhua cycle comparability/normalization or retain explicit NOT_READY
PUBLIC_EVENT_OPEN_NODES = 000333 and 601088 CNINFO watermarks remain INCOMPLETE; 600887 is contiguous only for the recorded CNINFO window; future Midea cancellation, dividend implementation, employee-plan expense and investor-meeting Q&A remain event triggers
CURRENT_DATA_OPEN_NODES = next planned session is 2026-09-28; latest matched quote remains 2026-09-24 and must not be duplicated before a new completed session
PRODUCT_OPEN_NODES = Midea pre-registration event dispositions are published and WPS-verified; Excel audit page still lacks direct source-URL hyperlinks/column and relies on local path plus SHA-256
R2_PARKED_NODES = M4 personalized portfolio only; no private input requested
R3_PARKED_NODES = M6 production/infrastructure only; no deployment, shadow or schedule
R6_PARKED_NODES = M3 strict contemporaneous PIT; future evidence; M6 real sessions/events and 20 consecutive-session gate
R5_PARKED_NODES = M7 final user acceptance; user trial not passed
SAFE_R0_REMAINING = 2; R0-A real M5 receipt lineage and R0-B privacy/artifact review remain open
SAFE_R1_REMAINING = 0; this increment independently closed the three Midea event materiality/research dispositions
M4_PERSONALIZED = PARKED_WAITING_R2
M6_OPERATIONAL = NOT_STARTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

Historical R0 checkpoint details follow:
R0-A remains open because no verified real M5 receipt-to-Product-to-Excel chain
is bound; M5 actual replay cases skip when required graph/plan/facts/recalculation
artifacts are absent. R0-B remains open because 8 of the 162 raw-only OOXML
fingerprints remain unclassified for release (5 private-context hits, 3 unknown),
and latest CI/WPS/current-worktree privacy boundaries are not fully evidenced.
The current handoff is therefore
NOT_READY; the 2026-09-26 handoff below is historical, not an authorization.
R2, R3, R5 and R6 continue to park only their respective DAG nodes. No private
input, production authorization, Shadow, schedule, notification or order is
requested or enabled.

### R0 Evidence Recount — 2026-09-27

`HEAD` and fetched `origin/main` both resolve to `c9449a4fe8881a0cec9ce2f992622b48693c413a`;
the worktree has unrelated uncommitted changes, so no checkout, merge, commit or
push was performed. GitHub Core Research Gates run `36282732643` for this HEAD is
green, but does not cover the dirty worktree. Focused local regression across M5,
Product Workbench, privacy, canonical preservation, M6 start criteria,
authorization and backup security returned **117 passed, 12 skipped**. The
skipped M5 actual replay cases require graph, plan, verified-facts and bounded
recalculation artifacts absent from this checkout; they are not passes.

R0-A remains `NOT_PROVEN`. The self-consistent ACTUAL run artifact exists at
`runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json`
(file SHA-256 `b93ea107489c3ddecca4eb876547a45e44dac8e379f86de9f740db4b16a31b56`),
and the historical M5 read model exists (SHA-256
`701cbaa9822d4ba17ba4edc47af2f6b1fef3636001338bf924693223a997b858`). These do
not establish Product lineage: the current event projection still accepts a
caller-supplied mapping, M7 publication evidence does not bind either artifact,
and complete replay inputs are unavailable. Independent read-only review also
confirmed the current tests exercise synthetic projection rather than a real
receipt-to-Excel path. Exact reopen condition: restore the missing original
M5 graph/plan/verified-facts/bounded-recalculation artifacts, bind the available
review bytes and verify source bytes plus issuer/event identity, then implement and test an issuer-neutral fail-closed adapter through
the product event sheet. Do not synthesize replacements. An independent
read-only subagent review confirmed the Product→Excel E2E currently uses
synthetic event inputs and that the product entry point accepts a caller-built
projection; it found no real receipt-bound path in either HEAD or the worktree.

R0-B remains `PARTIAL`; no confirmed real private data was found, which is not
equivalent to a pass. The new redacted context report
`runtime/privacy-context-classification-20260927-exact.json` has SHA-256
`41f96e1cabb7700d2692ac6152f46b1e7660ae4188b02ea78d58aad2292d18f9`. It scans
34 tracked workbooks and exactly reconciles the prior raw-only set: 10,798 raw
OOXML occurrences / 293 fingerprints, of which the same 162 are absent from the
openpyxl-visible fingerprint set. Per-occurrence context classification groups
those 162 as 154 rule-labeled potential public financial/market values, 5
fingerprints with private-context hits, and 3 unknown. This is a classification
result, not a privacy pass. Independent read-only review is complete and
concluded all 8 unresolved fingerprints must remain blocked; public-context
labels do not independently establish that values are public. The report
contains only fingerprints, sheet/cell/part
locations, classifications and categorical signals; no source candidate value
or context label is emitted. Latest Core Research Gates run `36282732643`
exposes one 3,368-byte synthetic restore artifact; the GitHub artifact API
returned 403 on byte download, so its content was not re-scanned. Latest CI logs
were not re-downloaded. M4 checks establish code-level path/key separation only;
no real private package was inspected. The canonical publication receipt and WPS
read-only receipt agree on workbook SHA-256
`68b218ed233973e0151fee747f822a485ca9a79f6a1bef69240f4361c66dc867` and manual
sheet preservation, but do not prove the WPS user-managed/private boundary or
bind M5 receipt inputs.

`INTERRUPTION_AUDIT`: machine verification is green for committed HEAD;
independent reviews found no basis to close R0-A or R0-B; security/product
regressions pass in the focused set but contain no real M5 Product E2E; privacy
remains open; canonical publication integrity matches its receipts; no new R1
public evidence task is authorized in this stage. Therefore exactly two
safe R0 DAG nodes remain (A and B), and safe R1 remaining is zero. Existing
`docs/current/external-gate-handoff.md` is explicitly superseded and must not be
used as a current handoff. No new handoff is generated until both R0 nodes are
actually closed. `TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`;
`INITIAL_ASSISTED_USE=NOT_REACHED`; permanent `action=no_order`.

The 2025FY A-share dividend evidence gap is now closed at the public-document
level: CNINFO shareholder resolution `1225393356` reports the proposal passed;
the issuer's 2026-07-06 implementation notice `1225410284` states CNY 1.03
gross per A-share and 2026-07-13 as the payment date. This confirms disclosed
approval and implementation terms, not account-level receipt or future
sustainability. The bounded 2026-06-26..2026-08-27 CNINFO query and source hashes
are in `docs/current/track-c-shenhua-dividend-followup-20260927.md`. This is
re-observed pre-registration material, does not advance the incomplete event
watermark, and does not alter valuation or the canonical workbook.

The prospective CNINFO scanner rejects missing, invalid or out-of-window
announcement timestamps before writing a `COMPLETE` index. Its evidence builder
revalidates every raw-page timestamp, requires the separately supplied expected
window and full unfiltered exact-issuer query contract, and requires parsed
index rows to exactly match the archived response rows. Regression result: 60
passed, 4 legacy v3 fixture cases deselected because their historical evidence
hashes remain stale; no historical pin was changed. The caller-supplied window
and index-bound organization ID are local scope constraints, not independent
signature/TSA-attested proof of the request parameters received by CNINFO.

## 2026-09-27 Midea H1 source admission and canonical publication

Midea's 2026H1 official CNINFO report `1225531404` was re-observed from the
bounded exact-issuer query and three summary-row facts were admitted from
physical PDF page 7. The PDF SHA-256 is
`576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`; values
are CNY thousands: revenue `260042490`, parent-attributable profit `26446037`,
and operating cash flow `37552090`. The report is unaudited and the
conservative date-level availability is `2026-08-30`; these are pre-registration
public facts, not a post-registration disclosure. The source memo is
`docs/current/track-b-midea-2026h1-admission-20260927.md`.

Append-only source facts `config/prospective-baseline-facts-public-v7.json`
(SHA-256 `0bbc21f26fd5be480745f2e1624496930863945bd29cea4da8791f27532a5628`)
passed verification config v9 (SHA-256
`5c23fb2038efd6697066dc4839cb0b675ed1d00265608d6317652077c9759710`) and
produced snapshot v13 (SHA-256
`ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`). New
publication pin v7 (SHA-256
`39746e4c54194b1acf51ca2d7306e57b7840011097218900f1e4cce128cd3bd2`)
preserves v6 and binds the exact v13 bytes plus unchanged registration and
baseline-input fingerprints. Product projection and baseline tests: `46
passed`; in-memory publisher verification returned `VERIFIED_IN_MEMORY_ONLY`
and `workbook_modified=false` before publication.

The same configured WPS canonical workbook was updated in place. Publication
receipt `runtime/publication-receipts/canonical-m7-product-publication-20260927T093345Z.json`
SHA-256 `5ee8c727c3f590a73d00abdb41594fc4f267ede7804a1033427903607d2e54cd`;
the preserved pre-publication backup has SHA-256
`7bfaa5531bce0a1809afda8f011d62f5d551631251980298e3eb2e325e0a34e5`, matching
the prior canonical. Published workbook SHA-256 is
`68b218ed233973e0151fee747f822a485ca9a79f6a1bef69240f4361c66dc867`. WPS
read-only verification receipt
`runtime/publication-receipts/wps-readonly-verification-midea-h1-v13-final-20260927.json`
SHA-256 `7007fedf063e499027eb44645a8e41b18b53faaebad6f7cbb7b5bee5aad04b6b`
records all six product sheets readable/calculated, formula checks, product
wording gates, required Midea and Shenhua facts, and unchanged workbook hash.
The quote bundle remains the prior partial 2026-09-24 session (000333 and
601088 only; 600887 missing); this publication does not claim a new quote.
`strict_pit_admissible=false`, all three valuations remain not ready, M7 final
user acceptance is not passed, and `action=no_order`.

## 2026-09-27 Yili contiguous CNINFO watermark successor

The malformed initial post-start scan receipt remains immutable and was not
used to advance coverage. A fresh exact-issuer unfiltered query covers the
contiguous window 2026-09-23..27 after the prior 2026-09-22 boundary. Its index
SHA-256 is `7231cfb60764ee91a3446a77a63569f31ece34d2b4264af47e398e781ac482cd`;
the raw page, full query contract, one-page completion (`hasMore=false`), and
official filing scan evidence are hash-bound in the v3 watermark manifest.
Only existing announcement `1225578520` was returned. The current CNINFO
watermark for 600887 now ends at `2026-09-27T10:00:05.035069+00:00`; the
document was public before registration and its materiality remains
`UNDETERMINED / INSUFFICIENT_EVIDENCE`. The 000333 and 601088 watermarks remain
`INCOMPLETE`; this does not establish issuer-IR, exchange-site, or later-
correction coverage. No valuation, PIT status, decision, or workbook changed;
`action=no_order`.

## 2026-09-27 Shenhua H1 admitted and published

The append-only facts input is `config/prospective-baseline-facts-public-v6.json`
(SHA-256 `94e481589554613d4eafd22ef5606aeb59296545af8b7f4d39f399467e7b5f24`),
validated by `config/prospective-baseline-verification-v8.json` and snapshot
`runtime/prospective-baseline-20260927/snapshot-v12-h1-column-bound.json` (SHA-256
`7de4c67f00f1096795b684d7cb1510f0c80418ae92f2ea677c1589e4d8dd988f`). The
three admitted values are 2026H1 revenue CNY 189,338m, parent-attributable
profit CNY 28,715m, and operating cash flow CNY 54,664m. CNINFO ID `1225531759`
is bound to the archived index, scan evidence, and PDF bytes (PDF SHA-256
`ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`). The
verifier uses pypdfium2 character coordinates to bind the current value to the
2026H1 column group and the comparisons to the 2025H1 group; missing or
misaligned coordinates fail closed. The report's 2025H1 comparison is restated;
the interim statements are unaudited
and have a limited-assurance review report, not an audit opinion. The
availability date is conservatively `2026-08-30T00:00:00+08:00` from CNINFO's
date-level marker.

Current product pin `config/prospective-baseline-publication-v6.json` binds
this successor snapshot. The in-memory product gate passed without workbook
write. Canonical publication receipt is
`runtime/publication-receipts/canonical-m7-product-publication-20260927T074231Z.json`;
the before/backup hash was `6ba73b62…ad8eb2`, the final canonical hash is
`7bfaa553…0a34e5`, and all user-managed/frozen worksheets were preserved. The
read-only WPS verification receipt is
`runtime/publication-receipts/wps-readonly-verification-shenhua-h1-v12-20260927.json`;
it checked all six product sheets, formula errors, freeze panes, forbidden
decision wording, and the three values plus their assurance/date disclosure;
the receipt records the exact passed company-content assertions.
Quote coverage remains partial (000333 and 601088 present; 600887 missing),
and its observation date remains 2026-09-24. This research update does not
change valuation, strict PIT, operational readiness, or user acceptance:
`VALUATION_NOT_READY`, `strict_pit_admissible=false`,
`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`, `INITIAL_ASSISTED_USE=NOT_REACHED`,
`action=no_order`.

Remote freshness note: `git fetch origin` completed successfully in this
continuation (exit code 0). Local `HEAD` and refreshed `origin/main` both remain
`c9449a4fe8881a0cec9ce2f992622b48693c413a`; no checkout, pull, commit, or push
occurred. The working tree remains dirty, so no branch-changing operation was
performed.

## 2026-09-27 prospective observation time-order hardening

Independent SubAgent review identified that the append-only observation writer
bound the scan receipt and PDF bytes but did not cross-check receipt creation,
index request/response, and PDF request/response ordering. It now requires the
receipt observation start to equal the registered start, validates timezone-
aware index and PDF times and HTTP success, requires each index response to
precede the PDF request, and requires receipt creation to follow the PDF
response. This is a local consistency check only: all timestamps remain
process-clock claims without independent TSA/signature attestation, so
`STRICT_PIT=NOT_PROVEN` is unchanged. Classification now treats a source whose
conservative availability equals the observation start as pre-existing public
material, not a post-registration disclosure.

Focused verification across observation, registration, and baseline suites:
`47 passed, 4 deselected`. The unfiltered run was `47 passed, 4 failed`; the four
failures stop at stale historical v1 scan-evidence hashes before reaching their
intended assertions. No historical hash or receipt was re-signed. No event
watermark, baseline, valuation, canonical workbook, or product status changed;
`action=no_order`.

## Previous 2026-09-27 public baseline and canonical WPS verification (v10; superseded)

At that earlier checkpoint, the immutable baseline was
`runtime/prospective-baseline-20260927/snapshot-v10-fresh-source-facts.json`,
SHA-256 `e9b55a4ecbbe095bcb3489e5d22e48490f53e9cbcfc09d68ac7729baa64ec1dc`.
It binds fresh complete CNINFO report-category scans and original PDF evidence:
000333 has 3 admitted facts and no unadmitted facts; 600887 has 6 admitted and
1 explicitly unadmitted report-level fact; 601088 has 3 admitted and 1
explicitly unadmitted operating-facts item. All three remain
`VALUATION_NOT_READY`; strict PIT remains false because registration timing is
only process-clock-attested. No value in this snapshot is a trade instruction.

At that earlier checkpoint, the canonical WPS workbook was published in place using
`config/prospective-baseline-publication-v4.json` and quote coverage remains
partial (000333 and 601088 present, 600887 missing; 600519 excluded). Publisher
receipt `runtime/publication-receipts/canonical-m7-product-publication-20260927T052648Z.json`
binds before/backup and final hash; the distinct read-only WPS verification
receipt is
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T052648Z.json`.
WPS opened the canonical workbook read-only, checked all six product worksheets,
41 visible/20 hidden sheets, frozen panes, formula errors, user-page decision
wording and valuation/portfolio empty states. It passed without changing the
canonical SHA-256 `4ce9ec6ce6b207c861459bd5f8c60ae0c99b201dda3da494694d19aaea357d90`.
This is engineering UX verification only; `M7_FINAL_USER_ACCEPTANCE` remains
`NOT_PASSED` and `action=no_order`.

The independent read-only SubAgent audit found the workbook's admitted,
unadmitted and citation counts consistent with snapshot v10 and found no
decision-control mismatch. Its WPS inspection was not repeated; the primary
session separately completed and retained the WPS read-only receipt above.

Event watermark reconciliation is recorded in the append-only successor
`config/prospective-public-event-watermarks-v2.json`; v1 remains unchanged.
The later CNINFO window evidence is retained there but does not advance the
formal watermarks: 000333 and 601088 remain `INCOMPLETE` because local
2026-09-23..26 and 2026-09-27 windows do not establish their missing earlier
continuous coverage; 600887 remains at its prior 2026-09-22 watermark because
the later raw scan's receipt summary required a separate interpretation and a
validated continuous successor receipt has not been produced. The 600887
announcement `1225578520` remains in bounded review with broader funding and
accounting materiality `UNDETERMINED / INSUFFICIENT_EVIDENCE`. Do not advance a
watermark from these partial observations alone.

The local 600887 event ledger contains 19 indexed announcements; 13 remain
`PENDING_HUMAN_REVIEW`. All 13 linked PDF files currently match their recorded
SHA-256 values. This is a bounded research queue, not evidence that all 13 are
material; the queue remains open until document-level facts and dependencies
are classified. The completed read-only SubAgent cross-check found that many
already have scoped dispositions in
`docs/m1-post-review-decision-gate-20260923.md`; queue status is not a claim
that those documents were never analyzed. It identified the impairment
announcement `1225511493` and proceeds report `1225511474` as open research
dependencies, while actual buyback completion and guarantee utilization still
require future issuer filings. Their linked sources were cross-checked into
`docs/current/track-b-yili-impairment-and-proceeds-review-20260927.md` with
original PDF hashes and printed/physical pages. Impairment remains
`MATERIAL_REQUIRES_RECALCULATION`; proceeds remain `REQUIRES_DECOMPOSITION`.
The review does not close either disposition or alter any current valuation.

Targeted tests were run with a project-local pytest temporary directory after
the default Windows temp location denied directory enumeration. Result:
42 passed and 4 failed in the combined run. The four failures are legacy
baseline fixture tests whose pinned 2026-09-23 Yili scan evidence bytes no
longer match the file at that historical path; verification correctly fails
closed before reaching their individual assertions. Do not re-sign or rewrite
that historical pin. Subsequent focused tests that rely on pytest's default
temp path also failed during fixture setup due to the same Windows temp access
denial. The newly added v10 projection and public scan tests passed in the
combined run. `git diff --check` reported no whitespace errors (only existing
CRLF normalization notices).

In the subsequent continuation, the focused current-path suite including the
watermark-manifest regression test passed 24/24 using a unique project-local
pytest temp root. The legacy v3 baseline fixture was not rewritten to conceal
its historical receipt drift.

The post-registration Yili document review used PyMuPDF text extraction after
`pypdf` produced garbled Chinese glyphs. The impairment notice, proceeds report
and H1 report were cross-checked by exact PDF hashes and page-level text. This
produced a bounded memo only; no baseline, prospective observation, model input,
event watermark, workbook, or valuation artifact was changed.

The full focused rerun including baseline, product, event, observation,
registration, quote-binding and watermark tests completed with 44 passed and
4 failed. All four fail at the legacy v3 fixture's stale 2026-09-23 scan
evidence hash before reaching their intended assertions; no historical pin was
rewritten. The 24-test current-path subset remains green.

### 2026-09-27 Legacy v3 fixture isolation retest

The exact historical fixture bytes were recovered from retained pytest-isolated
projects, not from the formal runtime path or Git history. Their SHA-256 values
match the existing v3 pins: `evidence.json` is
`a6a2dffac4a14726968979c3e401ce7e3b9f65a8d5c9c58a1f9dec1625f05a90`, and
`cninfo-index.json` is
`f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93f9c383349388bbc2d815ceea`.

Using the retained isolated fixture project as the test input root and a fresh
pytest `basetemp` outside the repository, the four stale-fixture failures were
rerun with five adjacent `_project()` boundary tests: 9 passed. The run excluded
the test that verifies real Git registration ancestry and tests that directly
read the canonical `ROOT`; this result is only an isolated fixture regression
check, not a Git/PIT attestation. The formal runtime files remain unchanged and
do not match the old v3 hashes; the verifier must continue to fail closed on
those bytes. No pin, source evidence, workbook, or prior test record was
rewritten. `action=no_order` remains in force.

## 2026-09-27 Midea item-level baseline and canonical refresh

The exact CNINFO annual-report-category query for code `000333`, date
`2026-03-31`, returned 2 of 2 rows with unique announcement IDs; the target is
`1225065145` (`2025年年度报告`). This is a narrow annual-category listing, not
a full event-coverage scan. The HTTP response bytes are retained at
`runtime/prospective-baseline-20260927/midea-index-20260927T041631898534Z/response.raw.json`,
SHA-256 `3c6b95775cfe940191bd928ba822f68a7e75569a860cb74912a5caf5c5e44543`;
the parsed index and scan evidence bind their query and retrieval time. The
official PDF is `runtime/midea-2025-official.pdf`, SHA-256
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`.

The versioned v5 verification input admits three report-summary values from
physical page 9 / printed page 8, all in CNY thousand: revenue 456,451,731;
parent-attributable net profit 43,945,411; and operating cash flow
53,345,930. `published_at` records CNINFO's date marker 2026-03-31; because it
does not establish an intraday release time, snapshot v8 conservatively sets
`available_at=2026-04-01T00:00:00+08:00`. Yili's six H1 facts retain the
parallel date-only treatment with availability 2026-08-28. This resolves the
prior input-field ambiguity by separating `published_at` and `available_at`;
v2/v4 inputs and v7 snapshot remain immutable history.

Current snapshot:
`runtime/prospective-baseline-20260927/snapshot-v8-public-item-facts.json`,
SHA-256 `860e4daeabd44006fb9664ff076d7e54ee9a8b2ea451ecc56269aa25991004b5`.
Midea and Yili are `BASELINE_PARTIAL`; Shenhua remains
`BASELINE_EXPLICIT_NOT_READY`. All three remain `VALUATION_NOT_READY`;
`registration_time_assurance=PROCESS_CLOCK_ONLY_UNATTESTED`,
`strict_pit_admissible=false`, and `action=no_order`.

The canonical WPS workbook was updated in place from the prior canonical hash
`e2144c22721f614960b9696f1066acf480e1c90ba505f2ed54e2352a98b2d600` using
publication pin v3 and snapshot v8. The publisher receipt is
`runtime/publication-receipts/canonical-m7-product-publication-20260927T043343Z.json`,
SHA-256 `4e1fed4aaf364cee6dcd508e2f81e55a634ad90fe28171ae431bdc9cd8ba7e15`;
it binds the before/backup hash and final canonical hash
`eecb864741d22e0573c4e28f844a8199f63bb846c59ad4d37117fa839a44299b`.
The distinct WPS read-only receipt is
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T043900Z.json`,
SHA-256 `2f924eba483e30f63faadc26fa8674e56ca20ed1ef40e88554d84eff08937253`;
it passed on 61 sheets and reported no hash change. An independent review
noticed the earlier 04:33 receipt labeled the COM compatibility name as
`Microsoft Excel` despite the WPS application path; the verifier now records
`application=WPS Office` and retains the COM name separately. The 04:39 check
passed with the corrected identity fields. This remains engineering
verification, not `M7_FINAL_USER_ACCEPTANCE`.

Audit note: during the earlier 04:23 v7 publication, the WPS verification
command was mistakenly given the publisher receipt path. The publisher output
was captured, but its original JSON bytes were overwritten. That path now
contains an explicitly labeled recovery record
(`canonical-m7-product-publication-20260927T042335Z.json`); it is not claimed
to be the original receipt and has no original receipt hash. Its WPS receipt
was rerun into a distinct path. The later 04:33 v8 publication and WPS
verification use separate receipt paths and retain their original files.

## 2026-09-27 Yili item-level facts and PIT time boundary (historical checkpoint; superseded by v8)

An immutable fact supplement was added without modifying the previous baseline
input or v2/v3/v5 snapshots. The current snapshot is
`runtime/prospective-baseline-20260927/snapshot-v6-yili-item-facts.json`, SHA-256
`0d455623c71fd675666ef8aba21aa98d2bbf6de45480031775d707a092176d53`. It admits
six 600887 2026H1 consolidated report rows from CNINFO PDF
`cninfo:1225511409`: revenue CNY 64,330,936,547.38 (physical/printed pages
52/49), parent-attributable profit CNY 5,758,628,097.79 (53/50), operating cash
flow CNY 9,759,147,483.18 (55/52), asset impairment loss CNY
-2,455,875,173.02 (52/49), short-term borrowing CNY 64,677,193,034.15 and
contract liabilities CNY 4,948,856,599.18 (both 49/46). Each ledger entry binds
the source PDF SHA-256 and conservative date-only availability
`2026-08-28T00:00:00+08:00`; the report-level placeholder remains explicitly
unadmitted. These facts do not alone establish ROIC, maintenance capex,
distributable cash, dividend sustainability or valuation. 000333 and 601088
remain `BASELINE_EXPLICIT_NOT_READY`; every valuation remains `VALUATION_NOT_READY`.

The line verifier now parses the uniquely matching table row, strips the annual
statement account-reference marker, requires at least two numeric period
columns, converts values to `Decimal`, and compares against the first (current)
period cell. Tests reject a comparative-period value and a short numeric
substring while accepting all six independently page-cited reported values.

The separate registration-time audit remains open: the receipt's
`receipt_created_at` is generated by the process clock but is not protected by
an independent trusted timestamp/signature. RFC 3161 endpoint probing was
blocked with HTTP 403 in this environment. Therefore snapshot explicitly sets
`registration_time_assurance=PROCESS_CLOCK_ONLY_UNATTESTED` and
`strict_pit_admissible=false`; this build must not be counted as M3 strict PIT
evidence. The product company page displays this limitation. A later verifiable
timestamp may support future checkpoints, but cannot retroactively authenticate
this registration time.

The final 2026-09-27 adversarial follow-up found no bypass in the two P2 fixes:
baseline company name must equal the registered issuer name, and the complete
source document ID must equal `cninfo:{announcement_id}`. Rehashed wrong-name
and wrong-namespace regressions cover both paths. The focused local test run
passed 37 tests across quote binding, registration, baseline projection,
item-level baseline admission and observation ledger suites. The first test
attempt could not create pytest temporary directories under the user Temp
ACL; rerunning with a repository-local `runtime/pytest-prospective-20260927`
base directory passed. `git diff --check` passed. This is engineering and
admission validation only; it does not upgrade strict PIT, valuation, M6, M7
user acceptance, or total-goal status.

The canonical WPS workbook was republished in place after final builder guards.
Publication receipt
`runtime/publication-receipts/canonical-m7-product-publication-20260927T031937Z.json`
SHA-256 `d318854a980fb4bbf015faaf5f53f77b7815bb05445519306e1ab6cd342badf0`;
backup SHA-256 was the prior canonical
`326bf4248889111624a684f87166bd9fd74c129cfff3868fbb78ec012d1d300b`.
New canonical SHA-256 is
`63bddf29e7ab68196335261b72b73510dcecf3d3196bc94eed6dfe8c477f99fb`.
WPS read-only receipt
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T031937Z.json`
SHA-256 `66803006471518a36a32b395514935b9351b5064fe9fcb53147979d3171e7365`;
61 sheets and all six product pages passed; final user acceptance remains
`NOT_PASSED`. Focused regression is `73 passed`; the 2026-09-24 quote remains
partial and no new market session is claimed. `action=no_order`.

## 2026-09-27 PIT admission correction and canonical refresh (historical checkpoint; superseded by v8)

An adversarial review found that the prior baseline validator admitted a
report-level placeholder from PDF identity/hash alone, and the observation
writer did not independently re-verify the registration receipt or reject
supersession forks. Those paths are now fail-closed. Registration verification
is shared by baseline admission and observation append and checks the canonical
registration fingerprint, receipt bytes, exact plan bytes, ancestor commit and
its plan blob, receipt timestamp, and plan/receipt semantic equality. Baseline
case IDs must be unique. Item facts additionally require a whitelisted type and
page-bound value, label, unit, report period, consolidation scope, and matching
physical/printed page in the original PDF. Observation append and read reject
forked supersession lineage.

The new immutable successor is
`runtime/prospective-baseline-20260927/snapshot-v3-item-verified.json`,
SHA-256 `c7dbf885ee5c849ab1a3d741553d20e34c091e2c1773e24e9f079a356552cd51`.
No current case has item-level facts that pass this admission contract:
600887's source remains report-level only, and the current Midea/Shenhua claims
still lack independently bound official listing evidence. All three baselines
are therefore `BASELINE_EXPLICIT_NOT_READY`, all valuations remain
`VALUATION_NOT_READY`, and `action=no_order`. The previous v2 snapshot and
receipt remain unchanged historical artifacts. The unique current pin is
`config/prospective-baseline-publication-v1.json`.

The canonical WPS workbook at the configured `WORKBOOK_PATH` was refreshed
in place after an in-memory verify-only pass. Publication receipt:
`runtime/publication-receipts/canonical-m7-product-publication-20260927T024232Z.json`,
SHA-256 `df0adf3a4f0e162b2772db85c18544bcc66a25d9c294320fedc089401cdd7cf9`;
backup preserves the immediately prior workbook. Canonical workbook SHA-256 is
`780c5214f678343659036adf30bc5bc2c7fd1b32fe6d03a41e04fea34dc8a9e1`.
WPS read-only UX verification passed with a separate receipt at
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T024232Z.json`,
SHA-256 `c3fb18d837461ec6864a4c24a61ea89ab67a5426cf9c53c651cd38dce9b85dd5`;
61 sheets were read/calculated, the six product pages passed layout/wording/
formula checks, and the workbook hash remained stable. This is engineering
verification only: `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`,
`INITIAL_ASSISTED_USE=NOT_REACHED`.

Focused regression: `69 passed` across product projection, prospective baseline, observation,
registration and daily quote binding suites; `git diff --check` passed. The
canonical product verify-only pass returned `workbook_modified=false` before
publication. The quote observation remains 2026-09-24 with partial registered
coverage (600887 missing); no quote refresh or new trading session is claimed.

## 2026-09-27 Prospective public research checkpoint (historical checkpoint; superseded by v8)

`runtime/prospective-v2-fc1e811/receipt.json` is the v2 registration time anchor:
`receipt_created_at=2026-09-27T00:24:16.082830+00:00`, before the registered
`observation_start_at=2026-09-27T08:45:00+08:00`. Its declared registration
time is not independent proof. The current baseline successor is
`runtime/prospective-baseline-20260927/snapshot-v2-date-safe.json`; SHA-256
`06196121d0df57aa252ce9dc6ac0b879fb0f890b0dcfb5bd90fc3dc3f7cef9d4`.
It binds the registration receipt, its ancestor Git commit and committed plan
bytes, the baseline input, archived CNINFO index/scan evidence and original PDF
bytes. One 600887 2026H1 report fact is admitted. 000333 has no admitted fact;
the existing 601088 source claim is unadmitted pending an independently bound
publication record. All three retain `VALUATION_NOT_READY`, `action=no_order`.
The preceding `snapshot-v2.json` is superseded. The older v1 snapshot remains
historical and is not a strict PIT admission.

The canonical product projection was republished in place under
`runtime/publication-receipts/canonical-m7-product-publication-20260927T020659Z.json`;
receipt SHA-256 `919e688b88326da206d79cf4be158bb9988c0460d8720b110bc3c8f8849af89e`.
Its pre-publication backup hash is
`c7fe7222ec17034f07e1ded71ad462b30e2d82cfc101b6a3baba2488b2985a7f` and the
published canonical workbook hash is
`1a6e0d1cdf31d76efc984ef3112283101c3865e34f60c0927c68d9bf7276bb83`. WPS
read-only UX verification passed under
`runtime/publication-receipts/canonical-m7-product-wps-ux-20260927T020659Z.json`;
receipt SHA-256 `427464466af950c9395991aab6a2672f1b2c399099394f4c611962f37fca6eea`,
at `2026-09-27T02:09:07.3740763+00:00`, with no workbook hash change. It checks
61 sheets, the six product sheets, protected first-column panes, formula errors,
blocked/empty states and forbidden decision wording; it does not constitute
final user acceptance. The canonical workbook remains
`INITIAL_ASSISTED_USE=NOT_REACHED`.

```text
PUBLIC_RESEARCH_OPEN_NODES = 000333 official listing-response bytes and baseline fact extraction; 600887 report-level source admitted but model applicability and line-item fact extraction remain open; 601088 cycle normalization and model inputs remain open
PUBLIC_EVENT_OPEN_NODES = 000333/601088 watermarks remain INCOMPLETE; 600887 2026-09-24 employee-plan share purchase materiality UNDETERMINED pending funding/accounting trace; post-start refetch is not a new event
CURRENT_DATA_OPEN_NODES = quote bundle is revalidated from retained Tencent/Sina source bytes and official venue-calendar evidence for 2026-09-24, but only 000333 and 601088 are registered observations; 600887 is missing and excluded 600519 is present in the source bundle. Display coverage remains PARTIAL; after the next completed official session collect exactly 000333, 600887 and 601088. Provider cross-check is not exchange-source authentication.
PRODUCT_OPEN_NODES = none for current projection; M7 final user acceptance remains the separate R5 node
R2_PARKED_NODES = M4 personalized portfolio only
R3_PARKED_NODES = M6 production/infrastructure only
R6_PARKED_NODES = M3 strict contemporaneous decision proof; M6 real sessions/events
M4_PERSONALIZED = PARKED_WAITING_R2
M6_OPERATIONAL = NOT_STARTED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

The 2026-09-27 corrective canonical publication includes only registered quote
symbols in the visible quote list and labels missing `600887` and excluded
`600519`; registered quote coverage remains partial. The quote-binding gate now
re-runs the existing raw Tencent/Sina parser and venue-calendar evaluator,
comparing parsed prices, times, identity, matched-close state and session with
the report. Hash and URL checks prove consistency with retained response bytes,
not that a provider is exchange-authorized. Regression tests use synthetic
protocol-shaped data. No new market session was collected in this correction.

Independent read-only review: Track B confirmed the Midea PDF byte identity but
not an independently archived CNINFO listing response; for Shenhua, the
reported HKEX minute-level release time is described in the research note but
the official listing row bytes are not archived in the baseline evidence, so
neither new company fact is admitted by this checkpoint. Yili's admitted item
is report-level only; it does not admit unextracted financial line items.
Track C confirmed that the latest public quote bundle contains 000333, 600519
and 601088: registered 600887 is omitted and excluded 600519 is extra. Official
SSE/SZSE calendars show 2026-09-25 through 2026-09-27 were closed; the next
quote refresh is eligible only after a new official completed session and must
cover exactly 000333, 600887 and 601088. The 000333/601088 watermarks remain
`INCOMPLETE`; the 600887 registered watermark still ends 2026-09-22. These
review findings do not change valuation, model applicability, or
`action=no_order`.

Track C's additional read-only event review found the 2026-09-17 Yili buyback
proposal (`1225568022`) already has a scoped decision `MATERIAL_RISK_MONITOR`;
the related creditor notice (`1225568017`) is `DUPLICATE_OR_DERIVED` within
that event. Neither proves completed repurchases or cancellation. The
2026-09-24 employee-plan purchase notice (`1225578520`) was already seen before
the prospective observation start; its later fetch is not a new event, and its
materiality remains `UNDETERMINED`. These findings do not promote research or
valuation readiness and do not alter any model input.

These open public nodes are independent of R2/R3. No private portfolio input is
requested. The 600887 filing review recorded before 08:45 is background
evidence, not a newly disclosed prospective event; its post-start refetch record
is append-only and supersedes the earlier ambiguous observation classification.
Its pre-start raw scan response was not retained, so the exact first-sighting
claim remains non-reproducible. The canonical workbook is the configured WPS
file; the latest publication/WPS receipts are listed above. The bound quote
bundle contains 000333, 600519 and 601088, not the full registered case set;
therefore its quote coverage is partial and must not be presented as a
three-case current quote refresh. Pages for cases without admitted facts
suppress the underlying unadmitted report assertions. This is M7 display
engineering evidence only; final user acceptance remains `NOT_PASSED` and
`INITIAL_ASSISTED_USE=NOT_REACHED`.

# 历史快照：当前执行状态

## 2026-09-27 Yili employee-plan funding/accounting boundary

Official plan and board disclosures now quantify CNY 225,018,899.80 of
third-phase after-tax award transferred to the employee plan account; the
completion notice reports CNY 224,997,098.71 spent on existing shares. Scale
ratios versus audited 2025 adjusted attributable net profit and operating cash
flow are approximately 2.03% and 1.57%, respectively. These comparisons do
not measure annual recognized expense or prove broader immateriality. Both
the audited 2025 annual report (physical PDF page 239) and unaudited 2026H1
report (physical PDF page 199) mark Note XV share-based-payment disclosures,
including current-period expense, not applicable. This narrows that specific
accounting path but does not exclude other employee-benefit/bonus recognition
or establish zero total award cost; the H1 cutoff also precedes the September
purchase completion. Current M5 remains
`PENDING_HUMAN_REVIEW`, broader dependency materiality `UNDETERMINED`, and no
valuation inputs changed. Evidence and limitations are detailed in
`docs/current/track-c-public-event-scan-20260927.md`. Existing employee-plan
watermark and prospective ledger remain unchanged; no Excel publication was
warranted. `action=no_order`.

## 2026-09-26 Synthetic Product Demonstration

```text
M4_SYNTHETIC_PRODUCT_DEMONSTRATION = COMPLETED
M4_SYNTHETIC_DEMO_RUN = product-demo-20260926
M4_REAL_PRIVATE_INPUT = NOT_PROVIDED
M4_PERSONALIZED_ACCEPTANCE = WAITING_R2
CANONICAL_WORKBOOK = OPENED_AS_READONLY_TRIAL
PRODUCT_DEMO_ACTION = no_order
```

The existing synthetic-only onboarding application path completed its full
draft, validation, encryption, reconciliation, confirmation, portfolio-risk,
position-guidance, dividend-projection and product-read-model exercise. The
runtime receipt is explicitly classified `SYNTHETIC_REHEARSAL_ONLY`; it is not
personalized guidance and did not write simulated holdings to the canonical
workbook. The configured canonical workbook was contract-verified and opened
as the single product trial entry. Product regression coverage passed locally
with 35 tests.

## 2026-09-26 R2 Private Portfolio Onboarding: Waiting for User Input

```text
STAGE_STATUS = WAITING_R2_PRIVATE_INPUT
M4_REAL_PRIVATE_INPUT = NOT_PROVIDED
M4_RECONCILIATION = NOT_STARTED
M4_PERSONALIZED_READINESS = NOT_READY
PRIVATE_DATA_BOUNDARY = PASS_FOR_NO_INPUT_STATE
PERSONALIZED_GUIDANCE = NOT_GENERATED
M6_PRODUCTION_AUTHORIZATION = NOT_REQUESTED
SHADOW_START_ALLOWED = false
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

The private onboarding entry point was re-verified without creating or reading
any private artifact. It requires an explicit `--private-root` and has no
default location, so no repository, WPSDrive, sync folder, home directory or
other user path was scanned. No legal R2 private-input location was supplied.
The next permitted action is only user provision of an explicit private root
outside the repository and sync folders; then the existing validation path may
be used. Until then, no private data, key, draft, Excel workbook, synthetic
input, CI fixture or guidance artifact is created.

## 2026-09-26 Final R0 Classification and External Handoff

```text
M5_PRODUCT_EVENT_PROJECTION_ENGINEERING = PASS
M5_REAL_CURRENT_OPERATIONAL_OBSERVATION = WAITING_R3_R6
CONTENT_LEVEL_PRIVACY = PASS
CI_LOG_PRIVACY = BOUNDED_LIMITATION_LATEST_SUCCESSFUL_RUN_ONLY
CI_ARTIFACT_PRIVACY = BOUNDED_LIMITATION_LATEST_SUCCESSFUL_RUN_ONLY
M6_RESOURCE_CAPACITY = FAIL_OBSERVED / R3_INFRASTRUCTURE_DECISION
M6_DISK_CAPACITY = NOT_READY_FOR_CURRENT_DEPLOYMENT / R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 0
SAFE_R1_REMAINING = 0
EXTERNAL_GATE_HANDOFF = READY
M6_PRODUCTION_AUTHORIZATION = NOT_REQUESTED
M6_OPERATIONAL = NOT_STARTED
SHADOW_START_ALLOWED = false
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

R0-A classification: the product projection has seven-state E2E coverage,
Hash-bound evidence, duplicate/correction preservation and fail-closed negative
tests. A new current operational M5 receipt additionally requires a controlled
production trust root and operator/intake identity (R3), plus a naturally
occurring source event (R6). It is therefore not safe R0. The existing 600519
`NEED_MORE_EVIDENCE` state remains an issuer-specific research stop, not a
system blocker.

R0-B classification: `runtime/privacy-final-20260926.json` scanned all 34
tracked workbooks without emitting a source token. Visible-cell results are
6,241 candidates / 132 fingerprints: 6,031 are hash-or-receipt fragments and
210 are public financial/market/source-audit values; there are no remaining
private-context or unresolved visible fingerprints. The two earlier
private-keyword-context fingerprints were independently adjudicated as SHA-256
fragments in public broker research/announcement-source rows, not account data.
Raw OOXML has 10,798 candidates / 293 fingerprints because it includes 9,461
worksheet raw values plus 1,337 comments/other XML serializations; 162 are
raw-only, but raw private-context fingerprints are zero. This is a bounded
OOXML serialization difference, not evidence of private data. No confirmed
private data was found in tracked Git content.

The latest successful Core Research Gates run is `36241330080` on `bb53559`.
CI log/artifact privacy coverage is deliberately limited to that latest
accessible successful candidate run and its synthetic/disposable restore
artifacts; it is not a claim about every historical CI run. The M4 private
package boundary still keeps real inputs outside Git, public runtime, CI
artifacts and canonical Excel. Resource observations remain a future R3 choice,
not an engineering loop. See [external gate handoff](current/external-gate-handoff.md).

## 2026-09-26 STAGE-FINAL-R0-EVIDENCE-CLOSURE 复核

```text
R0-A_REAL_M5_RECEIPT_BINDING = NOT_PROVEN
R0-B_CONTENT_LEVEL_PRIVACY = PARTIAL
R0-C_RESOURCE_CAPACITY = CLOSED_AS_R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 2
SAFE_R1_REMAINING = 0
EXTERNAL_GATE_HANDOFF = NOT_READY
M6_OPERATIONAL = NOT_STARTED
SHADOW_START_ALLOWED = false
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

R0-A：当前非测试的 600519 ACTUAL 请求仅有 2026-09-25 旧式离线授权链；`actual-valid-application-20260925/request.json` 的授权对象没有当前签名能力所需的 `valid_until`/受信任签名绑定，`config/authorization-trust-roots-v1.json` 的生产 pin 列表为空。当前规则只允许旧授权对既存同指纹批次作只读历史重放，不允许它进入 current 产品事件正例。仓库未发现另一条非测试的新版签名 ACTUAL 请求。既有七态合成映射与历史重放测试通过，但无法在不伪造真实授权的情况下证明“真实已验证 M5 收据 -> current Product -> Excel”；R0-A 保持开放。重开条件为出现经当前授权/信任根规则验证的真实 M5 收据及对应原件/复核字节链，然后完成 issuer-neutral adapter 和篡改反例；不以 600519 个股研究缺口替代此系统门。

R0-B：对 34 个 Git 跟踪工作簿的 `openpyxl` 可见单元格做脱敏分类，发现 6,241 次长数字命中、132 个唯一指纹；其中 56 次、2 个指纹落在私人关键词上下文，尚未判定为真实私人数据，必须独立复核。2,804 次仍属未知类别。此前原始 OOXML 扫描有 9,461 次、292 个唯一值，两个扫描口径差异尚未解释；不能用较小的可见单元格覆盖量宣称内容安全。M4 私有根/密钥分离已有代码门禁，WPS 用户管理区的未来发布边界与最新 CI 可访问日志/附件本轮尚未全部复核。审计工具只输出类别、单元格坐标及指纹，不输出候选原值。未发现可确认的真实私人数据，也没有证据足以关闭 R0-B。重开条件为私有上下文命中和 OOXML 差异的有界分类、CI/发布边界核验及独立脱敏复核；如确认 Git 跟踪制品含真实私人数据，应停止公开变更并单独处理，不自行改写历史。

`INTERRUPTION_AUDIT`：本轮可安全推进的 R0 已做取证，但 A 缺当前可信真实收据，B 缺足够分类与独立复核。R1 没有新的可用研究证据；M3 严格同时点 PIT 等 R6，M4 真实私有输入等 R2，M6 生产和资源方案等 R3/真实会话等 R6，M7 最终使用签收等 R5。两项 R0 均未达验收，因此不生成 external-gate handoff、不请求生产授权、不启动 Shadow；`action=no_order`。

## 2026-09-26 STAGE-R0-CLOSURE 有界复核（历史快照；后续 CI 已通过）

```text
R0-A_M5_PRODUCT_PROJECTION = SYNTHETIC_SEVEN_STATE_E2E_PASS; REAL_M5_RECEIPT_BINDING_NOT_PROVEN
R0-B_CONTENT_LEVEL_PRIVACY = PARTIAL; TRACKED_XLSX_NUMERIC_CANDIDATES_UNCLASSIFIED
R0-C_M6_RESOURCE_CHARACTERIZATION = DONE_WITH_FAIL_OBSERVED; FUTURE_R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 2
SAFE_R1_REMAINING = 0
EXTERNAL_GATE_HANDOFF = NOT_READY
SHADOW_START_ALLOWED = false
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

R0-A：新增七态显式上游判定到 Product Read Model、Excel 事件页和系统审计页的合成 E2E；重复事件被抑制，晚到、更正、证据不足及模型不可运行各有独立呈现/审计语义，证据文件 Hash 改动会拒绝候选构建。当前入口仍由调用者传入 `m5_event_projection`，没有证明它来自真实已验证 M5 收据，也未接入每日 canonical 发布。因此不将合成 E2E 简写为真实 M5 产品验收；剩余 R0 是真实收据到投影的身份、状态与证据绑定及负例验证，不涉及扩大公司研究。

R0-B：对当前 Git 跟踪文本、34 个 Excel OOXML、workflow 与可访问的最新成功 CI 日志和附件做内容级扫描。CI run `36233929385` 的四项合成恢复附件 ZIP SHA-256 为 `a543801e37de0046b564df336ffed6c5ba4e58bae658bfcafc4a50eba7d26c59`；日志 ZIP SHA-256 为 `22798bdfad0f31d857eb600b785f41a63660aed62659ddb4913edc05c7e5c9a5`。附件含 synthetic/disposable 标识，扫描未命中高风险密钥特征。Excel OOXML 未命中高风险密钥特征，但发现 9461 个 16–19 位数字候选（292 个唯一值），尚无法可靠区分公开财务/Hash 数据与私人账号。仅靠正则不能给 `TRACKED_CONTENT=PASS`；公开 Git 中的私人输入缺席也不能仅凭命名推断。候选细节不得写入日志或公开文档。内容级隐私审计仍为 `PARTIAL`，需要有界上下文分类与独立复核。

R0-C：有限只读重复采样的 `MemAvailable` 约 728–760 MiB，低于既定 1228 MiB；Swap 已用约 530 MiB，根盘可用约 5992 MiB，`web-app-pta` 为 active。该多次失败不是通过代码可关闭的容量缺口，归未来 R3 基础设施决策；不调整阈值、不修改 PTA。根盘扣除 2048 MiB 保留量后约 3944 MiB；按现有证据约 2231 MiB、备份约 242 MiB、数据库与隔离恢复卷各约 315/310 MiB、journal 约 353 MiB，完整备份/隔离恢复/临时 dump/日志的额外写入有界估计约 2.8–5.0 GiB。上界超过可用余量，磁盘准入不能判 PASS。此为授权前观察与容量估算，不是生产健康或恢复验收。未来 R3 必须先独立决定资源方案并复测内存与峰值磁盘余量。

`INTERRUPTION_AUDIT`：剩余安全 R0 仅为 A 的真实收据绑定、B 的疑似私人数字候选分类；R1 当前无可安全推进的新证据。M3 同时点 PIT 仍等 R6，M4 真实私有输入等 R2，M6 生产操作等 R3 与 R6，M7 最终用户签收等 R5。R0 未归零，不生成 external-gate handoff，不请求生产授权或启动 Shadow。

## 2026-09-26 STAGE-REAL-USE-READINESS-PRE-EXTERNAL-GATES 核验

预检基线提交 `ac58ab184b28945760b99da9eb1a48eb3f10b598` 的 [Core Research Gates 36230557757](https://github.com/MingMingLiu0112/value-investment/actions/runs/36230557757) 两项通过。最新合法已完成交易会话为 2026-09-24（9 月 25 日 SSE 休市，9 月 26 日非交易日）。既有真实采集包 `runtime/quote-sessions/20260926T081028140946Z/bundle.json` 的 SHA-256 为 `d161c6ed8acf2034544aa63fb101922d0ec22f537cdf2c69268243aaecb82974`；三只样例的腾讯/新浪报价日期均为 2026-09-24，且各自 `matched_close`，不存在跨日双源。采集完成于 2026-09-26T08:10:28Z；抓取时间不是报价时点。来源为 `qt.gtimg.cn` 与 `hq.sinajs.cn`；官方日历文档随包归档。覆盖仅 3 只样例，不代表全市场。

该包已于 2026-09-26 原位发布到唯一 `WORKBOOK_PATH`，发布回执 `runtime/publication-receipts/canonical-m7-product-publication-20260926T083623Z.json` 绑定原工作簿、备份、staging 和发布后 Hash；非产品页保全通过。之后的 WPS 只读打开/计算回执 `runtime/publication-receipts/canonical-m7-wps-readonly-20260926.json` 为 `passed`，仍是同一文件，SHA-256 `ee99fd866d63a23317953f2bc00fdb8d360f1793f2a077b2e5213d5c73d77eff`。六个产品页可见、无公式错误，`04_我的组合` 显示尚未接入真实组合。本轮未重复发布同一交易日数据。

```text
CANONICAL_DAILY_RUN = VERIFIED_FOR_THREE_SYMBOL_QUOTE_AND_READ_MODEL_PATH
CURRENT_DATA = PARTIAL
PRICE_BRIDGE = MATCHED_CLOSE_FOR_2026-09-24_ONLY
FINANCIAL_AS_OF = FROZEN_RESEARCH_INPUTS; NOT_REFRESHED_BY_DAILY_RUN
EVENT_SCAN_WATERMARK = FROZEN_M5_2026-09-24_PACKET; NOT_CURRENTLY_RESCANNED
SOURCE_FAILURES = 0_IN_RETAINED_QUOTE_BUNDLE; NOT_A_FULL_SYSTEM_HEALTH_CLAIM
CONFLICTS = 0_IN_THREE_MATCHED_QUOTE_OBSERVATIONS; OTHER_DOMAINS_NOT_RECHECKED
STALE_INPUTS = M2/M3/M5_RESEARCH_AND_EVENT_PACKET
UNSUPPORTED_INPUTS = REAL_PRIVATE_IPS_AND_PORTFOLIO_NOT_PROVIDED
SINGLE_CANONICAL_EXCEL = PASS
M7_STABLE_USER_TRIAL = READY_FOR_BOUNDED_READ_ONLY_USE
```

`generated_at` 是本次展示生成时间，不使旧财务、估值或事件证据变新。现有产品构建器仍消费固定的 M2/M3/M5 包；`05_事件` 目前只承载 M6 系统事件，未证明真实 M5 的重复、晚到、更正、非重大、重大、证据不足和模型不可运行七类状态逐一进入产品页。因此 M5 产品链保持 `PARTIAL_WITH_VALIDATED_NOT_READY`；600519 的 `NEED_MORE_EVIDENCE` / `STILL_NOT_READY` 只属个股研究，不是系统级阻断。

```text
M5_ENGINEERING = ACTUAL_EVENT_OFFLINE_CHAIN_VALIDATED; BOUNDED_NOT_READY_ENGINEERING_DONE
M5_PRODUCT = PARTIAL; SEVEN_STATE_EVENT_TO_EXCEL_ACCEPTANCE_NOT_PROVEN
M5_PRODUCTION = NOT_STARTED; FUTURE_SCOPED_R3_ONLY
```

该基线提交的只读 M6 预检 `runtime/m6-operational-preflight-20260926T093554Z/receipt.json`（SHA-256 `9e981527852d3f02e730fbaf9a779346acafa424b01bdb0ad96a250acbf975ec`）把 `m6c2_repository_and_privacy` 与 `m6c3_isolated_restore_mechanism` 判为工程 `DONE`，并绑定该次预检所用提交的 CI 合成隔离恢复工件；真实恢复 RPO/RTO 未通过。SSE 官方日历原文重新 HTTPS 核对通过，`m6c7` 仍因未来授权 venue scope 不明而 `PARTIAL`。服务器只读观察：内存 3563 MiB，总 available 886 MiB；Swap 4095 MiB、已用 558 MiB；根盘剩余 5.9 GiB（使用率 85%）；`web-app-pta` active，最大 python RSS 约 1969 MiB。现有生产授权包要求可用内存至少 1228 MiB，因此**本次资源观察不通过**；磁盘虽高于 2 GiB 保留线，但尚无预计写入量，不能判定磁盘准入通过。该瞬时观测不是生产健康准入收据；未启动或修改任何服务。

### Current Readiness Matrix

| Area | Engineering | Product | Current Data | R0 | R1 | R2 | R3 | R5 | R6 | Current Status | Reopen Condition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M2 | DONE | Checkpoint A HUMAN_PASS | 历史固定样本，非当日全市场扫描 | 无 | 无 | 无 | 无 | 无 | 新扫描另立证据 | DONE | 当前市场漏斗另有证据时更新 |
| M3 | 历史复核可重放 | Checkpoint B PARTIAL | 严格同时点规则未证明 | 不增加历史 verifier | 新证据才复核 | 无 | 无 | 非本阶段 | 同时点规则先于决策自然形成 | WAITING_FOR_REAL_CONTEMPORANEOUS_EVIDENCE | 新规则及全部输入在决策截止前登记 |
| M4 | 合成接入链完成 | 个性化未验收 | 无真实 IPS/持仓/现金 | 接入路径已演练 | 无 | 真实私有包与用户确认 | 不授权账户导入 | 非本阶段 | 无 | READY_FOR_REAL_R2_INPUT | 用户安全提供并确认私有输入 |
| M5 | ACTUAL 事件离线链与 bounded NOT_READY 已验证 | 系统级事件到产品页七态尚未验收 | 600519 新估值 null；每日事件未重扫 | 七态端到端证明待做 | 新研究证据到达再复核 | 无 | 真实生产采集待授权 | 非本阶段 | 新公告/财务证据 | PRODUCT_PARTIAL；ENGINEERING_BOUNDED_DONE；PRODUCTION_NOT_STARTED | 七态产品链通过且真实研究证据满足对应公司门 |
| M6 | m6c2/m6c3 于 `ac58ab1` 预检 DONE，m6c7 PARTIAL | 运营未开始 | 真实会话/事件 0；真实恢复未通过；资源读数低于 1228 MiB | 资源阈值、隐私内容与证据锚仍需收敛 | 无现成新材料 | 外部密钥身份另行受控 | 未请求/未授予，Shadow 禁止 | 非本阶段 | 至少 20 连续真实会话及真实事件 | PREFLIGHT_ONLY；RESOURCE_OBSERVATION_FAIL | 产品前置门、资源、授权与真实观察逐项通过 |
| M7 | 五页工作台集成，唯一 Excel 保全及 WPS 打开通过 | 稳定只读试用；最终签收未开始 | 行情 3 只当前，研究与事件部分冻结 | 修真实 P0/P1 才重开 | 无 | 组合页待 M4 | 无 | 用户最终独立验收/Checkpoint D | 依赖 M6 | STABLE_USER_TRIAL_READY；INITIAL_ASSISTED_USE_NOT_REACHED | M6 通过后用户实际完成最终验收 |

当前 `config/m6-start-criteria-matrix-v1.json` 的 `m6c2/m6c3=false` 是生成预检之前的静态清单，不能取代上面当前 HEAD 回执；其授权字段仍全部 false。按 R0-R6 分类：`m6c2/m6c3` 为 R0 工程已验；`m6c7` 的来源证据属 R0、授权 venue 绑定属 R3；资源/磁盘/健康读数属 R0 观察、生产准入属 R3；真实恢复、调度、备份、停启、密钥托管和生产运行属 R3；真实连续会话与事件属 R6；M3 属 R6 后触发 R1，M4 私有输入属 R2，M7 最终签收属 R5，真实资金决定永远属 R4。

```text
SAFE_R0_REMAINING = 3
SAFE_R1_REMAINING = 0
```

三项安全 R0：① 用产品页端到端测试证明 M5 七类事件状态及来源/更正关系，缺任何状态就保留产品 PARTIAL；② 对 Git 跟踪内容、GitHub 合成工件和日志做内容级隐私复核（当前 m6c2 的文件名扫描不足以证明完全无私人内容）；③ 将服务器只读资源/磁盘/健康观察绑定候选部署写入量和明确阈值，同时设计仓库外生产身份/不可回填接收锚的验收合同，不启用它。R1 暂无可用新研究证据；到达后只重开对应研究。由于 R0 非零，不生成 `EXTERNAL-GATE-HANDOFF`，也不请求 R3。

M5 产品范围合成回归新增 8 项：重大事件卡片可携证据链接进入读模型与 Excel；重复、晚到、更正、非重大、证据不足、模型不可运行六种原始 M5 状态目前因无产品映射而拒绝，空事件页有明确空态。它们只证明当前边界，不是七态 E2E 通过。Git 跟踪路径的初筛只有 SQL 迁移/查询脚本命中扩展名，`.env` 被忽略，高风险密钥特征扫描未命中；这些启发式检查不足以关闭内容级隐私 R0。CI 恢复附件由一次性合成测试生成，不应包含真实备份；仍需核验实际附件和日志的暴露边界。

`INTERRUPTION_AUDIT`：M3 等未来严格 PIT（R6），M4 等真实私有输入（R2），M5 个股研究等未来证据（R6→R1），M6 生产授权/真实隔离恢复（R3）、真实会话与事件（R6），M7 等最终用户签收（R5）。独立安全 R0 仍在，继续限定范围处理；不得把 `WORK_PACKAGE_DONE`、`SPECIALIZED_GOAL_DONE` 或里程碑工程完成写成总 Goal 完成。`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，`INITIAL_ASSISTED_USE=NOT_REACHED`，永久 `action=no_order`；最终投资决定由用户完成。

## 2026-09-26 Real-Use Readiness Pre-Gate Closure

```text
LATEST_COMPLETED_OFFICIAL_SESSION = 2026-09-24
CURRENT_QUOTE_COLLECTION = 600519 / 000333 / 601088 dual-source matched_close
QUOTE_BUNDLE_SHA256 = d161c6ed8acf2034544aa63fb101922d0ec22f537cdf2c69268243aaecb82974
CURRENT_MARKET_DATA_STATUS = MATCHED_CLOSE_FOR_2026-09-24
CURRENT_RESEARCH_DATA_STATUS = FROZEN_RESEARCH_EVIDENCE
CANONICAL_DAILY_RUN = PUBLISHED_PENDING_WPS_VISUAL_REVIEW
M6C2_REPOSITORY_AND_PRIVACY = DONE
M6C3_ISOLATED_RESTORE_MECHANISM = DONE
M6C7_OFFICIAL_EXCHANGE_CALENDAR = PARTIAL
M4_SYNTHETIC_ONBOARDING = COMPLETED_SYNTHETIC_ONLY
M4_PERSONALIZED_ACCEPTANCE = WAITING_R2
M3_STRICT_CONTEMPORANEOUS_RULE_PIT = NOT_PROVEN
M5_PRODUCT = PARTIAL_WITH_VALIDATED_NOT_READY
M5_600519_EVENT_BOUND_VALUATION = STILL_NOT_READY
M6_VERIFIED_ACTUAL_SESSIONS = 0
M6_REAL_EVENTS = 0
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

`runtime/quote-sessions/20260926T081028140946Z/` contains retained raw quote and
calendar evidence. The daily quote binding verifies report/bundle Hashes, raw
provider response Hashes, per-symbol `matched_close`, aligned completed session
and `action=no_order`, then adds a presentation-only market-data item without
altering intrinsic value, research state or decision status. The canonical
workbook was published from that binding with receipt
`runtime/publication-receipts/canonical-m7-product-publication-20260926T083623Z.json`:
before SHA-256 `78d556b5a71b5f1c72d144e1aa37da5fab6869a4a73dd83db4569b131e0f580e`,
after SHA-256 `ee99fd866d63a23317953f2bc00fdb8d360f1793f2a077b2e5213d5c73d77eff`.
The receipt confirms preserved sheets and user-managed content are unchanged.
This is not a valuation refresh, an approved signal, or user acceptance; WPS
visual review remains pending. The
preflight receipt `runtime/m6-operational-preflight-20260926T081452Z/receipt.json`
binds `m6c2` and `m6c3` to clean commit `0ce39a7ddc900ce6830d94304b094b430b268112`
and its successful disposable-PostgreSQL CI run. Its SSE calendar source was
independently refetched and hash-matched, but `m6c7` remains `PARTIAL` until an
authorized venue scope is defined. The synthetic M4 receipt did not read a
private input or elevate product acceptance.

No server, scheduler, Shadow mode, notification, real account data, production
database, or order path was accessed.

### Current Readiness Matrix

| Area | Engineering | Product / data fact | Gate class | Current status | Reopen condition |
| --- | --- | --- | --- | --- | --- |
| M2 funnel fixed sample | DONE | Historical fixed-sample evidence is accepted; it is not a current-market scan | — | DONE | A separately scoped current-market funnel run |
| M3 decision / PIT | PARTIAL | Retrospective replay is inspectable, but strict contemporaneous-rule PIT is not proven | R6 | PARTIAL | A future, evidence-bound contemporaneous rule and session chain |
| M4 portfolio intake | Synthetic chain exercised end-to-end | No personal IPS, holdings, or account input was read | R2 | READY_FOR_REAL_R2_INPUT | User supplies the deliberately scoped private input package |
| M5 event research | `ACTUAL_EVENT_OFFLINE_CHAIN_VALIDATED` | 600519 has reviewed evidence, but no approved event-bound valuation inputs; no new valuation | R1 | PARTIAL_WITH_VALIDATED_NOT_READY | New material evidence triggers bounded human research reopening |
| M6 m6c2 repository/privacy | DONE | Current clean HEAD audited | R0 | DONE | Relevant code or tracked files change |
| M6 m6c3 isolated restore mechanism | DONE | Current HEAD is bound to successful disposable PostgreSQL CI evidence | R0 | DONE | Relevant restore code, workflow, or HEAD changes |
| M6 m6c7 calendar | Parser and SSE calendar provenance verified | SSE source proof is live-verified; authorized future venue scope is undefined | R0 | PARTIAL | Define authorized venue scope and verify its official source coverage |
| M6 real restore / resource / health / scheduler | Mechanisms exist where stated | No server, backup, scheduler, or production observations were touched | R3 | NOT_STARTED / REQUIRES_AUTHORIZATION | Explicitly scoped production authorization and independent observations |
| M6 real sessions and real event | Contracts exist | Verified actual sessions = 0; verified real events = 0 | R6 | NOT_STARTED | Authorized future no-order observations across time |
| M7 canonical Excel | DONE | `WORKBOOK_PATH` is the only user workbook; integrated product UX passed preservation and WPS-open checks | R5 | PRODUCT_READY_PENDING_USER_ACCEPTANCE | User acceptance of the canonical workbook |
| Initial assisted use | Daily quote binding and canonical publication DONE | Current market data is visible; research/valuation remains frozen and no user final acceptance exists | R5 | NOT_REACHED | WPS visual review and user acceptance |

The daily packet-to-canonical-publication binding is now evidence-bound. Any
future publication without `--quote-bundle`, with a changed raw document, a
coverage mismatch, a non-`matched_close` observation, or a changed protected
sheet fails closed.

## 2026-09-26 Canonical Excel 发布纠偏与验收收尾

```text
CANONICAL_WORKBOOK_SOURCE = WORKBOOK_PATH
CURRENT_TRIAL_POINTER = CANONICAL_WORKBOOK
M7_PRODUCT_UX = INTEGRATED
CANONICAL_FILE_BEFORE_SHA256 = 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911
BACKUP_SHA256 = 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911
CANONICAL_FILE_AFTER_SHA256 = 78d556b5a71b5f1c72d144e1aa37da5fab6869a4a73dd83db4569b131e0f580e
WORKBOOK_PATH_UNCHANGED = true
PRODUCT_SHEETS_PRESENT = true
PRESERVED_SHEETS_CONTENT_CHECK = PASS
WPS_CANONICAL_OPEN = PASS
SINGLE_CANONICAL_EXCEL = PASS
M7_PRODUCT_UX_IN_CANONICAL = PASS
COMPETING_CURRENT_WORKBOOKS = 0
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

发布回执在 `runtime/publication-receipts/canonical-m7-product-publication-20260926T054332Z.json`，
备份在 `runtime/workbook-backups/canonical-before-m7-product-ux-20260926T054332Z.xlsx`。WPS
只读打开与可读性回执均通过。后续发布对所有非 `PRODUCT_MANAGED` 工作表执行单元格、公式、
超链接、合并区域、行列尺寸、冻结窗格、保护、批注、数据验证、条件格式、命名范围以及
绘图/媒体/图表/关系 OOXML 部件的 fail-closed preservation audit。历史 runtime candidate
不是 current pointer，也不是用户入口。

提交 `122932e` 的 GitHub Core Research Gates 已通过 `offline-core` 与
`postgres-integration` 两个作业。以上 PASS 仅确认单一 Excel 前端的发布与保护合同，
不改变 `M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`、`INITIAL_ASSISTED_USE=NOT_REACHED` 或
`action=no_order`。

## 2026-09-26 M7 五页产品工作台候选历史记录

本轮唯一目标 `DELIVER-M7-PRODUCT-UX-V2-TO-USER`。五页产品工作台候选
`runtime/m7-product-ux-candidate-v2-20260926.xlsx`
SHA-256 `f3d29985f58f8a1e0925781c5161292cf5cf8c4643931cece64ed85fc4f452f3`
在 WPS 实际打开后暴露了一个真实可读性缺陷：行高只按显式换行计算，忽略软换行的
实际行数，导致 `01_今日`、`02_机会`、`03_公司`、`05_事件` 与审计页上的中文长句被
裁切（`01_今日` 第 4、11-16 行，`02_机会` 全部 18 行均受影响）。

修复仅限展示层：行高改为按列宽和东亚字宽计算真实换行行数，
冻结窗格由 `A4` 改为 `B4` 以在横向滚动时保留公司列。估值公式、研究门槛、
事件材料性、组合容量、M6 准入与 `action=no_order` 均未改动。

最终候选 `runtime/m7-product-ux-candidate-v3-20260926.xlsx`
SHA-256 `bb98c9670218be3abbfe9adf665c14337c06893af382e9f2be4068905c1aa18b`，
来源 packet SHA-256 与 v2 完全一致（`8328bf5dc0427ef7ce66e216ae7f20f32451e95bf70f63ac6bf1be2e9adc7a0d`）
证明只改了呈现。WPS 只读回执
`runtime/m7-product-ux-candidate-v3-wps-receipt.json` 为 `passed`
（6 页可见、每页冻结首列、无公式错误、用户页无阶段码与买卖指令）。
可读性审计 `runtime/m7-product-ux-candidate-v3-visual-review-receipt.json` 为
`passed`，同一审计在 v2 上为 `failed`，因此该门禁不是空跑。

`config/current-trial-workbook.json` 已从 legacy v16 切换到产品工作台：
`M7_PRODUCT_UX=USER_VISIBLE_TRIAL_READY`、`CURRENT_TRIAL_POINTER=PRODUCT_UX`、
`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`、`INITIAL_ASSISTED_USE=NOT_REACHED`、
`action=no_order`。v16 候选与其 WPS 回执保留为历史，正式 WPS 原表
SHA-256 仍为 `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`，
未替换、未发布。`python scripts/open_current_trial_workbook.py --open`
已实测打开的是五页产品工作台而非 v16。

## 2026-09-25 PIT Conformance Consumer Enforcement

`pit-conformance-verifier-v2` 的结果现在不能作为可持久复用的授权。严格的 M3
证据审计和 historical-validation receipt audit 都会在消费进程内重新运行 verifier，
要求 `PASS`、`strict_pit_admissible=true` 和永久 `action=no_order`，并把结果绑定到
subject 与 v2 manifest 的原始字节 Hash。验证期间文件被替换会失败关闭；非 strict 的
`NOT_PIT_SAFE / NOT_ADMITTED` 仍可审查，但不会升级成同期规则 PIT。

600519 admission builder 的 receipt-bound 字节保持不变，当前仍只生成
`NOT_PIT_SAFE / NOT_ADMITTED`；未来 strict writer 必须使用版本化 successor 并在发布前
取得同一 admission 字节的 fresh v2 PASS。M7 只读工作台不再把原始 replay 渲染成
`PIT=YES`，而是明确标记
`REPORTED_NOT_V2_VERIFIED`。这些改动不批准估值、绩效、订单或生产运行。

验证结果：PIT/M3/历史 receipt/M7 定向回归 `85 passed`；架构与 valuation-confidence
迁移回归 `49 passed`；本地全量离线回归 `2857 passed, 30 skipped, 18 warnings, 0 failed`。
被 receipt-bound 的 `build_moutai_historical_validation_admission.py` 和
`historical_validation.py` 均保持原始字节 Hash。

## 2026-09-25 PIT Conformance Verifier v2

新增只读 `pit-conformance-verifier-v2` 与薄 CLI `audit_pit_conformance_v2.py`。
它不读取生产数据库、不运行真实 replay、不修改 Excel 或 receipt，只对 subject 和独立
input manifest 做逐字节、逐时点和逐覆盖证明校验。缺失 policy/proof 返回
`NOT_PROVEN`；未来事实、未来 quote、路径逃逸、Hash 不符、重复身份、规则日期矛盾、
benchmark/universe/model-session 覆盖矛盾或版本不一致返回 `FAIL`；只有完整证明返回
`PASS`。`PASS` 仍不代表绩效、估值、买入、仓位或生产授权。

本轮新增 34 个 verifier 测试；replay/admission/receipt/architecture 联合回归
`89 passed`，本地全量离线回归 `2845 passed, 30 skipped, 18 warnings, 0 failed`。
frozen `historical_validation.py` 字节 Hash 未变。当前第一案例仍是
`NOT_PIT_SAFE / NOT_ADMITTED`、`approved_value_model_sessions=0`、
`walk_forward=NOT_RUN`、永久 `action=no_order`。

该历史入口已由上方 `PIT Conformance Consumer Enforcement` 取代：M3 strict evidence
与 historical-validation receipt 入口现已强制调用 verifier；旧段落中的
`PARTIAL_MITIGATION` 不再是当前状态。

## 2026-09-25 M6 P0 授权证明对象收口

`transition()` 不再接受裸 `authorization_id`。它现在只接受由签名授权验证器签发的
`OperationalAuthorizationProof`，证明绑定授权 Hash、授权模式、目标模式、操作者、交易所、
有效期、验证时间与 `action=no_order`；控制状态同时持久化当前授权 SHA-256。直接传字符串、
目标模式不符、操作者不符、过期、未来验证或从急停后复用旧授权都会失败关闭。
`LIMITED_USE` 继续没有任何可执行入口。

这只是离线 R0 领域合同，不构成生产授权，也没有运行 `advance`。当前
`M6_OPERATIONAL=NOT_STARTED`、`production_authorization_granted=false`、
`verified_actual_sessions=0`、`real_events=0`，永久 `action=no_order`。

## 2026-09-25 历史验证第一案例 admission

新增 `historical-validation-policy-v1`、`HistoricalValidationAdmission`、600519 admission
builder 与 receipt auditor。第一案例 2015-01-05 至 2015-01-30 的结论为：

```text
CLASSIFICATION = NOT_PIT_SAFE
ADMISSION_STATUS = NOT_ADMITTED
APPROVED_VALUE_MODEL_SESSIONS = 0
RULE_REGISTRATION = RETROSPECTIVE_RESEARCH_EXTENSION
WALK_FORWARD = NOT_RUN
action = no_order
```

2015-2025 range experiment 继续只能称为
`RETROSPECTIVE_RESEARCH_RANGE_EXPERIMENT`，不能称为 validated strategy backtest。
历史验证审计会重新计算证据文件 Hash，但通用 admission dataclass 的文件存在性检查仍是
下一批非阻断技术债。

## 2026-09-25 日结节点

本轮按原总 Goal 继续推进 M4/M6/M7，不以工程提交替代产品验收。今日新增并验证的关键节点为：

- M4 形成 `READY_FOR_PRIVATE_INPUT` 的单一路径，包括仓库外私有输入、独立密钥、加密、
  双密文对账与显式确认合同；未提供真实 IPS/组合前，个性化 M4 仍为 `WAITING_R2`，不生成
  个人化仓位结论。
- M7 只读试用入口固定到 Hash/WPS 回执约束的 v16 候选，正式 WPS 原表未替换；试用和最终
  用户验收仍未通过，`M7_USER_ACCEPTED=false`。
- M6 离线 R0 增加授权制品逐字节绑定、五方 Shadow 准入、独立 append-only intake、真实事件
  admission，以及只接受签名授权和包外批准 Hash 的本地模式转换门。它们都是未来运营门禁，
  没有启动生产 Shadow、没有 SSH、没有创建 OSS、没有改数据库或 PTA 任务。

当前事实状态保持不变：`M2=DONE`；M3 strict contemporaneous-rule PIT 为 `NOT_PROVEN`；
M4 为非个人化工程完成、个人化输入待 R2；M5 600519 已审 9 条公告、待审 0 条、已核 5 项 H1
事实和 2 条重大事件，但研究仍为 `HUMAN_REVIEWED_NEED_MORE_EVIDENCE`，重算
`STILL_NOT_READY` 且没有新估值；M6 为 `PREFLIGHT_DONE / operationally NOT_STARTED`，
生产授权 `NOT_YET`，已验真实 Shadow 会话和真实事件均为 0；M7 为只读候选可用，
`M7_USER_ACCEPTED=false`；`INITIAL_ASSISTED_USE=NOT_REACHED`。永久 `action=no_order`。

验证证据：M6 定向回归 `59 passed`；本地全量离线回归 `2761 passed, 30 skipped,
18 warnings, 0 failed`。全量回归只证明工程合同和离线行为一致，不证明历史策略有效性、
真实生产数据完整性或投资结果。

下次继续时的入口不变：用户可先运行 M7 只读试用并向系统反馈问题；私人 IPS/组合仍由用户
决定是否提供；M6 生产授权包只可审查，未经逐项批准不得执行。工程侧继续时仍优先补历史
PIT/验证证据和 600519 事件后研究证据，不用自然时间等待阻塞其他安全工作。

## 2026-09-25 M6 受验证授权的本地模式转换 R0

`m6_operational_control.py advance` 不再接受自报 `authorization_id`。它现在必须读取签名授权
及 scope/部署/配置原始制品，并使用仓库外提供的批准授权 Hash 与公钥验证签名、逐字节 Hash、
有效期和 `action=no_order`；验证所得授权 ID 才能驱动逐级本地状态转换。CLI 仍只写本地控制
状态，不连接 SSH/systemd、数据库或生产任务；仅开放 `STAGING`/`SHADOW`，`LIMITED_USE`
继续无入口。急停保持随时可用，停止后的重启仍需新授权并先回到离线工程模式。

这只是未来授权后的执行门禁代码，不构成用户生产授权，也没有运行该 `advance`。当前
`production_authorization_granted=false`、`shadow_start_allowed=false`、
`M6_OPERATIONAL=NOT_STARTED`，永久 `action=no_order`。

## 2026-09-25 M6 真实事件运营准入合同 R0

新增 `m6-event-admission-v1`，把现有事件候选、公告原件/CNINFO 索引、M5 review/receipt、
已准入 M6 会话、生产授权、运营 admission 与 intake 链头组合验证。第五方 admission
密钥需对每个具体事件另行签收，并由包外固定精确收据 Hash；完整重签但改变任一绑定
字段仍失败关闭。`assess_session_ledger` 只接受该组合结果，并要求账本同日明确声明事件且
会话收据 Hash 相同；普通布尔声明、离线候选、历史 600519 回放及仅有会话 admission
继续计 0。定向事件/会话回归 `89 passed`。

这完成的是未来真实事件的机器侧准入合同，不是已经观察到真实事件。当前未启动 Shadow，
`verified_actual_sessions=0`、`real_events=0`、`M6_OPERATIONAL=NOT_STARTED`、
`production_authorization_granted=false`，永久 `action=no_order`。

## 2026-09-25 M6 五方运营准入与 vFinal 授权提案

新增 `m6-shadow-admission-v1`：第五把独立 admission 公钥与包外批准收据 Hash 绑定
授权、scope/部署/配置实际制品、intake 链头、交易所、有效期、20 会话/1 事件门槛和
重置政策。`assess_session_ledger` 只有消费该完整运营包装器后才允许把候选会话记入
`verified_actual_sessions/latest_streak`；没有独立事件证明时事件仍为 0，整体继续
`NOT_STARTED`。包含 intake、会话、事件、日历、控制与授权包在内的 M6 定向回归
`84 passed`。

`config/m6-production-authorization-vfinal.json` 已把主机、数据库私网边界、现有调度、
local-outbox、资源限额、备份/OSS 异地策略、RPO/RTO、回退、紧急停止、SSE/SZSE、
五方签名及 20 会话规则全部固化为机器提案。用户只需审批五项明确 R3 选择；当前均为
`null`，`production_authorization_granted=false`、`shadow_start_allowed=false`。本轮未 SSH、
未创建 OSS、未运行真实恢复、未改 systemd/数据库/PTA，`M6_OPERATIONAL=NOT_STARTED`。

## 2026-09-25 M6 独立 append-only 接收链 R0

新增 `m6-independent-intake-v1`：每条独立接收记录绑定原始会话收据字节 Hash、服务端
接收时间、严格递增序号、密钥纪元、授权部署 Hash 和前序记录 Hash；包外 trust root
固定 intake 身份/公钥/纪元/部署，包外 pinned head 固定链头 Hash、序号与钉住时间。
Shadow 验证器现在要求授权、运行、见证、intake 四把公钥互异，并要求每份会话收据的
规范字节已进入该链。缺链、换字节、错纪元、错部署、倒序、回写时间或链头不符均失败
关闭。联合定向回归 `66 passed`，另有接收链/会话不匹配反例。

该合同仍不把本地生成的签名或时间升级为生产事实。真正计数必须由 R3 授权范围外的
受控 intake 服务和独立钉住链头支持；当前 `verified_actual_sessions=0`、真实事件 0、
`M6_OPERATIONAL=NOT_STARTED`、`action=no_order`。

## 2026-09-25 M6 授权制品实际字节绑定

Shadow 授权验证不再只检查三个 64 位字符串。证据包必须携带 scope manifest、部署
manifest 和运行配置的实际字节；验证器重算三个 SHA-256，与签名授权逐项核对，并要求
scope 中的授权 ID、模式、交易所、有效期及部署/配置交叉 Hash 完全一致。部署与配置均
固定 `action=no_order` 且必须有独立 ID。替换任一制品字节、Hash 或 scope 字段都会失败
关闭。M6 会话/事件/运营联合定向回归 `67 passed`。

这只关闭机器侧“声明 Hash 未绑定实际字节”的 R0 缺口。独立 append-only 接收时间锚、
生产信任根、R3 授权、真实恢复、连续 20 个真实交易会话及真实事件仍未形成；
`M6_OPERATIONAL=NOT_STARTED`、真实会话/事件均为 0、`action=no_order`。

## 2026-09-25 M4 私人输入包与 M7 唯一试用入口

M4 新增统一入口 `scripts/setup_private_portfolio.py`、最小草稿模板、明确标记为
`SYNTHETIC_EXAMPLE_ONLY` 的示例和极简说明。用户现在可以在仓库/WPS/同步盘之外完成
草稿校验、独立密钥生成、AES-256-GCM 加密、内存解密校验、双密文对账及显式人工确认。
未确认或未对账的合法 ACTUAL 包可以先安全加密，但回执固定为
`PRIVATE_ACTUAL_PENDING_REVIEW`，仍不能进入个性化仓位指引。对账已覆盖现金、成员、
交易所、数量、成本、市值及公司行为；缺市值为 `INCOMPLETE`，匹配也只到
`MATCH_PENDING_HUMAN_CONFIRMATION`。确认操作生成新的不可覆盖密文并绑定源密文 Hash，
不修改源包。真实 IPS/持仓尚未提供，`M4_PERSONALIZED=WAITING_R2`。

M7 新增 `config/current-trial-workbook.json` 与受 Hash 校验的单一打开入口，当前钉住
v16 候选、manifest 和 WPS passed 回执。该候选仍不是正式原表；M6 运营状态明确为
`NOT_STARTED`，`INITIAL_ASSISTED_USE=NOT_REACHED`，永久 `action=no_order`。M7 最终用户
验收尚未通过。M4/M7 定向回归 `17 passed`；Ruff 未安装，本批另执行 Python compileall。

## 2026-09-25 M6 公告覆盖与签名日历补审

离线候选索引现要求 600519 SSE 的完整无筛选查询参数，并要求选中公告日期落在 M5 review 扫描窗口内。反例覆盖重算 Hash 后的过滤查询、错误证券 ID 和越窗公告。独立签名会话已在推导的 2026-09-24 官方交易日上验证，并测试错误日历 Hash 必须拒绝。这仍不是 CNINFO 实时来源认证或生产独立见证；真实会话/事件均为 0，`M6_OPERATIONAL=NOT_STARTED`，`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，`INITIAL_ASSISTED_USE=NOT_REACHED`。永久 `action=no_order`；最终投资决定由用户作出。

## 2026-09-25 M6 候选来源索引与官方会话补强

离线事件候选现接受独立的 CNINFO 索引字节及期望 SHA-256，绑定 M5 review 的 `scan_sha256`/evidence ref、查询证券与窗口、唯一公告 ID、标题、官方毫秒时间戳和 PDF URL。交易日不再由调用方手填；从归档 SSE/SZSE 原文构建完整已收盘会话表，并核对包外提供的日历原文 Hash。2026-09-25 为 SSE 休市，合成正向样例改为 2026-09-24；600519 的旧公告继续不能算作新的运营事件。定向索引/候选测试 `26 passed`，含重算索引 Hash 后篡改 ID、标题、时间、URL、条数与重复行的反例。

这只证明归档材料与现有规则之间的离线一致性，不能证明索引在本次运行中由 CNINFO 实时返回；预期 Hash、密钥和日历文档仍可能同源自报。`operational_event_proven=false`、真实会话/事件 0、`M6_OPERATIONAL=NOT_STARTED` 均不变。生产受信任制品索引、公告来源独立认证和不可回填接收时间锚仍属 R0/R3/R6；总 Goal 未完成，`INITIAL_ASSISTED_USE=NOT_REACHED`，永久 `action=no_order`。

## 2026-09-25 M6 事件运营候选见证 R0

新增纯离线 `m6-shadow-event-observation-v1` 候选验证器，逐字节绑定归档 PDF、材料性 review、内部自洽的 ACTUAL M5 committed receipt、签名 Shadow 会话及其运行制品；review/receipt 期望 Hash 与允许来源主机为包外输入。上一官方会话收盘后到当前会话的时间窗口拒绝旧事件回放。返回永远是 `offline_candidate_valid`，`operational_event_proven=false`、`verified_real_event_count=0`；不接入 M6 实际事件计数或生产。

定向测试 `41 passed`，包括可移植合成合同和本机归档 600519 的历史事件拒绝。公开 CI 的合成测试模拟 M5 解析和签名核验接口，仅检查候选跨链约束；本机真实原件测试使用真实解析器/Ed25519，但因原件不入公开仓库，在 CI 中会跳过。不能把本轮标为真实运营事件见证完成。独立钉住的 M5 制品索引与公告来源记录、生产授权/部署身份、不可补写的到达时间锚及实际授权 Shadow 运行仍是 R0/R3/R6 缺口。

`M6_OPERATIONAL=NOT_STARTED`，真实会话/事件仍为 0，`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`；总 Goal 与 `INITIAL_ASSISTED_USE` 均未完成。永久 `action=no_order`，最终投资决定由用户作出。

## 2026-09-25 当前提交 CI、M6 收据与 M7 v16 候选

`4e45fbeb8ef205a6d26bfc173a15b3237046d11c` 的 [Core Research Gates 36127009539](https://github.com/MingMingLiu0112/value-investment/actions/runs/36127009539) 中 `offline-core`、`postgres-integration` 均为 `success`。在该干净提交上实时查询 GitHub run/job/step/附件元数据后的本地 M6 收据为 `runtime/m6-operational-preflight-20260925T110154Z/receipt.json`，SHA-256 `1b8f2e5aa8d7b82624b8c15da3c86c8de6b66d55f8da3d5bc21125efc374506c`。`m6c3` 恢复机制工程 `DONE`，`m6c4` 真实隔离恢复 `NOT_STARTED`；真实会话 0，真实事件观察 `NOT_STARTED`，运营准入 `NOT_STARTED`。GitHub 合成附件元数据不是生产备份内容或 RPO/RTO 证明。

600519 R1 追加只读核验：隔离工作树 graph 文件 SHA-256 与复核文档一致，graph policy SHA-256 与人工 receipt 的 `5254ad4e202e6af6e9258e0ed41bf149a393f81e508b4ee4b442052eede86c13` 一致，8 个 graph 输入制品均存在且逐件 SHA-256 匹配。两条事件与一手 PDF Hash 未见冲突。这只加强既有证据链核验，不批准任何新估值或历史事件的 M6 运营计数。

新的只读 M7 候选 `runtime/m7-actual-reviewed-candidate-v16-20260925.xlsx` SHA-256 `71d6674da29074df8211b423a0ea946c974e4c68a15b40f62683a9492308d197`，首页分列恢复机制与真实恢复状态；WPS 收据 `runtime/m7-actual-reviewed-candidate-v16-wps-receipt.json` 为 `passed`，10 可见/2 隐藏、`no_order`、无订单建议。正式 WPS 原表 SHA-256 仍为 `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`，未替换；M7 最终用户验收未开始。

`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`；`INITIAL_ASSISTED_USE=NOT_REACHED`。永久 `action=no_order`，最终投资决定由用户作出。

## 2026-09-25 M6 CI 绑定与 600519 独立 R1 复核

新增 `--verify-ci` 的只读工程入口：仅在干净 `HEAD` 的本仓库 `main` push、指定 workflow/job/恢复测试步骤成功且同 run 的合成附件未过期时，才允许将 M6 恢复**机制** `m6c3` 记为 `DONE`。缺证据时保持 `PARTIAL` 或失败关闭。定向回归 `23 passed`，包括旧提交、PR、rerun、失败步骤、过期/错绑附件、脏工作树及 workflow 不再运行恢复测试的反例。此时尚未对新提交执行 live CI 绑定；真实恢复 `m6c4` 仍为 `NOT_STARTED`，不能由合成 CI 附件替代。

独立 R1 复核核对了 600519 两条重大事件的 decision/event ID 与归档 CNINFO PDF SHA-256，未发现冲突。隔离工作树的 graph 文件 SHA-256 `9e14506c939b7359b86332515a89cc5d2e6c4e9c820b02986c1ad3531df9fa88` 与现有研究复核文档所列文件 Hash 一致；这不同于 receipt 中的 graph policy SHA。已定位 Hash 匹配的 verified-facts 文件和 complete-sources pending-input 文件。此复核不补足事件后 SKU、渠道、利润、分配与折现证据，`NEED_MORE_EVIDENCE` / `STILL_NOT_READY` 不变；历史 M5 事件不得计作 M6 真实运营观察。

总目标仍为 `IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，`INITIAL_ASSISTED_USE=NOT_REACHED`；永久 `action=no_order`，最终投资决定由用户作出。

## 2026-09-25 INTERRUPT 复核：253eddc 与剩余 DAG

以干净且与 `origin/main` 一致的 `253eddc6fb68a17138fa7c4ab240fea5e9c7f5b1` 为基线。该提交的 [Core Research Gates 36125635715](https://github.com/MingMingLiu0112/value-investment/actions/runs/36125635715) 已完成，`offline-core` 与 `postgres-integration` 均为 `success`；仅证明本提交的工程测试通过，不构成真实运营或投资有效性验收。

最新只读 M6 预检 `runtime/m6-operational-preflight-20260925T104504Z/receipt.json` 的 SHA-256 为 `215663f3ad4e6e164f51aa780894120d127147efcb791f331b8c94481120db67`。15 项准入中仅 `m6c2_repository_and_privacy=DONE`；恢复机制、日历、紧急停止等仍为 `PARTIAL`，真实隔离恢复、会话和事件均未开始/未通过。`engineering_status=DONE` 是预检生成器的局部工程声明，不是 M6 产品或运营完成。此收据为本地忽略文件，尚未形成可独立取得的发布证据。

`INTERRUPTION_AUDIT`：M2/Checkpoint A 为 `DONE/HUMAN_PASS`。M3 strict contemporaneous-rule PIT 未证明（R6）；M4 个性化验收等真实 IPS/Portfolio（R2）；M5 600519 九条已审、零待审、五项 H1 事实及两条重大事件已核，但 scenario=`NEED_MORE_EVIDENCE`、recalculation=`STILL_NOT_READY`、new valuation=`null`（R6）。M6 只处于 preflight，生产授权未授予（R3），已验真实 Shadow 会话/事件均为 0，连续至少 20 个真实交易会话及真实隔离恢复验收未满足。M7 仅展示工程候选，最终用户验收和 Checkpoint D 未开始/未通过（R5）。

剩余独立 R0 DAG：生产实例身份与仓库外信任根的绑定、不可事后补写的运行/见证时间锚、真实事件原件与 M5 review/event ID 和授权 M6 运行制品的端到端验证合同。现有签名会话只可列为 `signed_candidate_sessions`，不得记入真实会话；历史 M5 replay 不可充当真实运营事件。恢复机制的 CI 与代码 Hash 绑定、真实隔离恢复收据及 M7 最新预检只读投影仍可独立核验，但不能借此升级运营状态。由于安全 R0 尚未耗尽，不生成 `REMAINING-GATES-TO-INITIAL-ASSISTED-USE` 的“仅剩外部门”清单。

`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`；`INITIAL_ASSISTED_USE=NOT_REACHED`。任何 `WORK_PACKAGE_DONE`、`SPECIALIZED_GOAL_DONE` 或 `MILESTONE_ENGINEERING_DONE` 均不得简写为总 Goal 完成。永久 `action=no_order`，最终投资决定由用户作出；不启用生产 Shadow 或修改正式 WPS 表。

## 2026-09-25 M6 准入摘要逐项化 R0

预检现把备份、隔离恢复、资源、健康、紧急停止、官方日历、调度、通知、生产授权、真实会话、真实事件及总运营准入分项记录，逐项包含 `status/evidence_refs/evidence_sha256/verified_at/blockers/reopen_condition/review_class`。原先没有证据引用的恢复机制 `DONE` 改为 `PARTIAL`：可核对本地代码与测试文件 Hash，但当前提交的 CI 收据未绑定到预检；仓库/隐私 `DONE` 仅在必需文件 Hash 可列出时保留。日历来源已验证时，重开条件改为尚缺的授权交易所范围及覆盖。新增条目只展示真实缺口，不把合成代码测试升级为生产验收。`M6_OPERATIONAL=NOT_STARTED`，`action=no_order`。

## 2026-09-25 会话计数安全纠偏

独立对抗审计证明：三层签名只能验证收据之间的密码学关系，签名者可在事后填写历史 `received_at`；调用者也可同时提供自造密钥和所谓信任根。故 `signed_candidate_sessions` 仅供工程检查，不可增加 `verified_actual_sessions`、连续段或事件数。当前真实计数仍全部为 0，M6C5 保持 `NOT_STARTED`。后续必须先建立仓库外独立钉住的生产信任根、不可后补的接收时间锚和受授权部署运行证据，才可设计真实会话晋级路径。现有 CLI 仍禁用 `advance`，未开始 Shadow。

## 2026-09-25 Shadow 会话验证合同 R0

新增离线 `m6-shadow-receipt-v1` 验证器：授权/运行/独立见证三层 Ed25519 签名，仓库外批准的授权收据 Hash、互异密钥、官方日历来源、部署和配置 Hash、会话与见证前序链、及时接收窗口。失败会话留在证据链但打断成功连续段；事件计数仍为 0。预检只有在显式提供签名 bundle、受控信任根及官方日历实时核对时才可计算**签名验证**的会话数。现有 CLI 没有生产信任根入口，未签发授权或开始 Shadow；当前真实已验会话仍为 0。签名中的自报时间不能代替独立运营见证或自然交易日，见 [合同](m6-shadow-receipt-contract.md)。

## 2026-09-25 恢复链追加失败关闭检查

独立审计发现空原件目录可登记无法恢复的备份，以及校验后 `pg_restore` 重新打开原 dump 的替换窗口。已在数据库连接和 dump 前拒绝空原件目录；恢复先复制 dump 到私有临时目录并核验 Hash，只把该副本交给 `pg_restore`，源文件在执行期间变化则不写通过收据。离线 Core Gate 同款清单 `800 passed, 22 skipped`。真实 PostgreSQL 集群身份仍缺独立可信证明，M6C4 与运营验收保持未通过。

`INTERRUPTION_AUDIT`：会话账本目前只把普通 JSON 作为 `declared_*`，已验真实会话/事件仍为 0；授权后的真实运行收据验证合同尚未建立，属剩余 R0。R2 私人 IPS、R3 生产授权、R6 自然交易会话与新研究证据、R5 最终用户验收均未越门。不能生成“仅剩外部门”清单；永久 `action=no_order`。

## 2026-09-25 M7 双交易所预检只读候选

从现存 M5 隔离工作树取回逐文件 SHA 与 reviewed read model 完全匹配的 graph、plan、facts、outcome、scenario source 和 pending input；现有构建器重放通过，不更改 M5 研究结论。`runtime/m7-actual-reviewed-candidate-v14-20260925.xlsx` SHA-256 `f67ea05e3bab3ba87f9b3a15eadfa02c36bd6eea3dc97c90e8993464e061f915`，审计页绑定较新的双交易所 M6 预检收据 `runtime/m6-operational-preflight-20260925T091253Z/receipt.json`（SHA-256 `d5cfdf469c397454e483b436ce5ffa6472d0e961a19624fa24fa7f54a3dcb233`）。`runtime/m7-actual-reviewed-candidate-v14-wps-receipt.json` 只读 WPS 核验 `passed`：10 可见/2 隐藏、无订单、全可见页禁用建议扫描。正式 WPS 表 SHA-256 仍为 `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`，未发布或替换。M6 仍只预检、真实 Shadow 0；M7 用户验收未通过。

## 2026-09-25 原件备份快照与隔离恢复 R0

日常备份容器原先未挂载生产原件目录，manifest 仅枚举备份目录中已有 PDF；已修正为只读挂载 `evidence`，将 PDF 字节复制到备份根下内容寻址对象，记录原相对路径、大小及 SHA-256。隔离恢复校验从备份对象复制到全新临时目录并复核逐件内容；收据版本升级为 `isolated-restore-v2`，旧版不能冒充已完成原件恢复。复制失败、路径逃逸、缺原件及 Hash 不一致均失败关闭。隔离测试删除源 PDF 后仍能从备份对象验证原件；未操作远端或正式 WPS。

此为备份/恢复 **R0 工程**，不是生产备份、异地加密副本或真实恢复通过。实际 PostgreSQL 集群身份还缺独立可信绑定；仅凭 DSN、数据库 OID 或普通 SQL 观察不能证明实例不被替换。M6C4 真实验收、M6 运营及总 Goal 状态均保持未通过，`action=no_order`。
`18bc0ce` 已推送；[Core Research Gates 36121893819](https://github.com/MingMingLiu0112/value-investment/actions/runs/36121893819) 的离线和双 PostgreSQL 集成作业均为 `success`。本机同款离线清单 `798 passed, 22 skipped`；跳过项不能替代真实服务器演练。

## 2026-09-25 恢复及 M7 追加 R0 审计

恢复脚本现使用一次性隔离库数据卷，避免旧集群/旧密码残留；验证命令只使用显式隔离 DSN 的 `pg_restore`，无不一致目标的容器回退；历史证据烟测改为独立恢复密码、一次性卷，并拒绝所有非零恢复退出。M6C4 已验证收据超过 32 天的月度窗口时保持 `PARTIAL`，不能凭旧收据宣称当前恢复能力。定向 43 项通过；尚无真实隔离恢复验收。

M7 v13 是绑定较早 SSE-only 收据的**冻结候选**，并非当前双交易所预检投影；现有工作树缺少其 M5 原始重放输入，不以其他文件替代，也不覆盖正式 WPS。构建器后续将输入称为“指定收据”，授权包已区分 SSE/SZSE 来源核对和待定义的生产观察范围。M6 运营、M7 用户验收及总 Goal 状态均未升级；`action=no_order`。

恢复审计仍留下两个不能由现有离线测试冒充通过的验收点：DSN 标签尚未独立绑定实际 PostgreSQL 集群身份；原件只在备份目录核验，尚未证明从备份恢复到独立位置。M6C4 的真实恢复准入保持未通过，后续必须以隔离环境的实例身份、原件恢复路径和完整收据实测验证。当前不请求生产授权、不连接远端库。

## 2026-09-25 INTERRUPT 回查：隔离恢复配置 R0

总 Goal 仍为 `IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，`INITIAL_ASSISTED_USE=NOT_REACHED`。
本轮仅加固 M6 恢复工程：隔离库采用独立凭据；安装脚本对新旧配置均生成/接入该凭据；恢复 RTO 从容器启动前计时，另记录恢复命令耗时；systemd 演练限时 4h15m；恢复单测进入 CI。恢复专项 40 项通过。全仓本机测试在约 85% 后长时间无进展而中止，不记为通过。未操作生产服务器或正式 WPS 表格，也未取得真实备份恢复验收。

剩余 DAG 审计：M2/Checkpoint A 已通过；M3 strict contemporaneous PIT 尚未证明（R6）；M4 个性化 IPS/Portfolio 待私人输入（R2）；M5 两条 600519 事件仍为 `STILL_NOT_READY`，新估值为空，待未来真实研究证据（R6）；M6 生产授权未给（R3）、已验真实 Shadow 会话为 0、连续 20 会话及真实事件未满足、真实隔离恢复未通过（R6/R3）；M7 最终用户验收和 Checkpoint D 未通过（R5）。独立 R0 仍需检查 CI 与部署配置边界，故不生成“仅剩外部门”清单。永久 `action=no_order`；投资决定由用户作出。

## 2026-09-25 双交易所日历与真实会话计数纠偏

在 SSE 只读归档之外，000333 的 SZSE 月度日历 bundle 已归档于
`runtime/quote-sessions/20260925T091240840369Z/bundle.json`，SHA-256
`4a80318973e27449f182ceb9083e1ab36f81c4759f6c568de82952ed0c1a05fe`；
独立 HTTPS 重取和完整已收盘日历解析通过，最近已完成会话同为 2026-09-24。
SSE/SZSE 来源验证均为 R0 只读证据，不构成生产运行会话。生产授权运行范围仍
未确定，M6 全局日历准入保持 `PARTIAL`。

旧账本把自报 `actual/success` 列为候选 `latest_streak`，容易被误读为已验真实
会话；现把 `declared_*` 与已验 `latest_streak`/`real_events` 分开。没有授权后
运行收据时，已验真实会话、连续段和事件均为 **0**，M6 会话准入为
`NOT_STARTED`。这不取消未来 20 连续交易会话、真实事件和独立恢复验收。
当前提交前定向账本回归 `19 passed`，尚须新提交的 Core Gate 证明。

干净主线 `c8a0a43` 的 M6 SSE 官方来源预检收据 SHA-256
`77ded9f153a0235046adc4a18732fd9efb88cf834ede6bd5ec121e55b6fcd15f`，
engineering `DONE`、operational `NOT_STARTED`。绑定该收据的 M7 v13 只读候选
SHA-256 `a7b4d0deef5e41f474f45c20fb67aa7f3df377deb1c233fe416ee0af88083e3e`，
WPS 只读复验 `passed`（10 可见/2 隐藏、无订单、正式表 Hash 不变）。
[Core Research Gates 36117117710](https://github.com/MingMingLiu0112/value-investment/actions/runs/36117117710)
的离线与 PostgreSQL 集成作业均为 success；此状态仍非 M6/M7 产品验收。

## 2026-09-25 M6 SSE 官方日历与授权控制补充审计

只读 `collect_quote_sessions.py --symbols 600519` 将 SSE 2026 官方休市公告归档于
`runtime/quote-sessions/20260925T090141596768Z/bundle.json`，bundle SHA-256
`ebc4f2d3f90e2e495e8e5eadede6228fe5c754c56f3fb0f202f0a4b0d2307766`。
M6 日历解析确认最近已完成 SSE 会话为 2026-09-24，官方原件 SHA-256
`4e260b815ce1309175ed994e6490a4ccd51b998a5f92bcdc41cec00fc6823dc7`；
第二次独立 HTTPS 重取返回 HTTP 200 且原文字节 Hash 一致。新增预检入口核对
bundle/report Hash、明确引用和原件来源，live refetch 为显式选项。
这只覆盖 SSE 2026，不证明 SZSE 或未来已授权运行范围，M6 日历准入仍 `PARTIAL`；
真实 Shadow 会话 0，运营 `NOT_STARTED`。

本地 M6 控制 CLI 已禁用仅凭任意授权 ID 的 `advance`；`status` 和紧急 `stop`
保留。授权包列出尚缺部署/DB/网络、调度通知、凭据、CPU/RAM/磁盘、日志备份、
回退和 Shadow 启停范围。`INITIAL_ASSISTED_USE=NOT_REACHED`，`action=no_order`。

## 2026-09-25 M6 证据闭环工程与 M7 状态投影

基线 `0707add` 后完成本地 R0 工程：恢复前核对来源库登记的 manifest/dump，
校验原件与隔离库表行数/内容指纹，限定恢复命令超时，生成内容寻址且不覆盖的
恢复收据；M6 准入只在读取收据并重验 manifest、dump、原件及隔离库时才可将
恢复单项判为 `DONE`。手填摘要仍为 `PARTIAL`。新增 SSE 2026 官方休市公告及
SZSE 月度日历的已收盘会话合同，账本核对交易所、日期、来源 Hash、cutoff 和
缺失交易日；自报记录不能证明真实 Shadow，已验真实会话仍为 0。

M7 ACTUAL 只读候选构建器可按 Hash 固定最新 M6 预检收据，将恢复、日历、
授权、Shadow 分开投影并拒绝错误运营状态升级；尚未替换 WPS 正式表。
定向集成 `78 passed`，新增恢复成功路径合同测试 `16 passed`；工作流 Core Gate
`767 passed, 21 skipped`。全量本机回归首次 `2636 passed, 28 skipped, 5 failed`，
五项均因测试基目录在仓库外触发历史 fixture 的路径假设；在仓库内临时目录
逐项重跑 `5 passed`，不将其当业务失败。未执行真实隔离 PostgreSQL drill：
Docker 引擎未运行，本机无 `pg_restore`；无真实 RPO/RTO 或恢复验收收据。
官方抓取来源仍需独立认证；生产授权、真实事件运营观察、20 连续真实交易会话、
M7 用户验收均未通过。`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，
`INITIAL_ASSISTED_USE=NOT_REACHED`，永久 `action=no_order`。

后续推送 `0ba4f47` 的 [Core Research Gates 36115714671](https://github.com/MingMingLiu0112/value-investment/actions/runs/36115714671)
同样双作业成功，合成恢复制品 `m6-synthetic-restore-evidence` 已上传（3,213 字节，
14 天留存）；它含 CI 一次性测试数据，不是用户的真实备份。M6 本地运营控制 CLI
已拒绝仅凭非空授权 ID 升级模式；`status`/紧急 `stop` 仍可用，控制回归
`10 passed`。授权包已列明尚待确认的主机/端口暴露、调度、资源、日志、备份、
回退、私人数据与 Shadow 门。未经用户真实 R3 授权不得启用生产。

推送 `9c4ab6e` 后 [Core Research Gates 36115217469](https://github.com/MingMingLiu0112/value-investment/actions/runs/36115217469)
的 `offline-core` 与 `postgres-integration` 均为 success；后者包含一次性双库
合成备份、隔离恢复、内容指纹及收据二次验证测试。公开 API 的作业日志下载为
403，故不从该结果推断生产数据恢复通过；后续 CI 增加限期上传合成原件/收据。
M6 干净主线预检收据 `runtime/m6-operational-preflight-20260925T085227Z/receipt.json`
SHA-256 `e381c19e44c4ccc2ad5713fc7a8edcb2d88f044c9a9ab1407ad11fed4fef7a2e`：
engineering `DONE`、operational `NOT_STARTED`、真实恢复无记录、真实会话 0。
M7 v12 只读候选 `runtime/m7-actual-reviewed-candidate-v12-20260925.xlsx`
SHA-256 `1311f6444b88aeef8b972b81d61f0185465591262e96457b41a0447a0a39fc07`，
WPS 只读核验 `passed`（10 可见/2 隐藏、首页无订单、全可见页禁用指令扫描）；
正式 WPS 表 SHA-256 仍为 `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
这仅是候选展示工程，不是 M7 用户验收。

## 2026-09-25 总 Goal 状态纠偏与 INTERRUPTION_AUDIT

最新 `main` 基线 `21aaf156a29d34f8fff4d0663e2b22c0cea85e7f`：
`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`，
`INITIAL_ASSISTED_USE=NOT_REACHED`。此前
`SPECIALIZED_GOAL_STATUS=ENGINEERING_DONE_WITH_VALIDATED_NOT_READY` 仅指 M5
actual-event bounded NOT_READY 的 A1-A10 工程验收，不是 M5 产品完成，
也不是 M6 运营、M7 用户验收或总 Goal 完成。

INTERRUPTION_AUDIT：M2/Checkpoint A 已通过；M3 strict contemporaneous PIT
仍缺自然形成的证明（R6）；M4 个性化输入待用户私人 IPS/组合（R2）；
M5 600519 九条已审、零待审、五项已核 H1 事实及两条重大事件均不改变
`NEED_MORE_EVIDENCE`、`STILL_NOT_READY`、`new_valuation=null`（R6）。
M6 仅预检，生产授权未授予（R3），未独立证实任何真实 shadow 会话，
20 连续真实交易会话及真实事件观察未满足（R6）；隔离恢复也没有
manifest/dump/restore/verifier 完整绑定的通过收据。M7 仅展示工程可用，
最终用户验收及 Checkpoint D 未通过（R5）。独立 R0 工作仍存在：
恢复验证结果与 M6 准入摘要的证据绑定；故不能宣称所有安全工程已耗尽，
也不生成“仅剩外部门”清单。永久 `action=no_order`，最终投资决定由用户作出。

本轮 R0 安全修复：`verify_restore` 现拒绝 manifest 指向备份目录外的 dump/原件，
包括 `..`、根路径和符号链接逃逸；在读取外部文件或接触数据库前失败关闭。
恢复目标、M6 定向回归 `28 passed`。这只是路径边界修复，未执行真实恢复、
未绑定 M6 准入收据，不能升级恢复验收或运营状态。

## 2026-09-25 Review治理语义与M7状态完整性核验

以`origin/main`的`cbe543e`为基线，长期路线、阶段目标和仓库入口已区分R0-R6及局部等待；M2仍为DONE/Checkpoint A `HUMAN_PASS`，M3 Checkpoint B仍PARTIAL，M4私人输入、M5事件后证据、M6生产/真实会话及M7最终签收均未因此过门。M7清单不再在缺少Checkpoint A字段时推断`HUMAN_PASS`，M2声称DONE却缺少该字段时拒绝输出。定向测试`32 passed, 4 skipped`；离线Core Gate清单`684 passed, 40 skipped`，额外跳过主要因为此独立工作树没有Git忽略的冻结runtime证据，不可当作真实证据复验。未修改生产、私人账户或正式WPS工作簿。

M6会话账本的“最新连续会话”现从全部记录末端计算；最新一条失败或模拟会话会中断连续段，不再把更早的20条成功记录误作当前连续达标。M6定向测试`30 passed`；加入该反例后的离线Core Gate清单为`685 passed, 40 skipped`，仅为合成合同验证。账本仍缺可审计的交易所会话日历及真实运行收据，因此`M6_OPERATIONAL=NOT_STARTED`，未计入任何真实Shadow会话。

更新：2026-09-25。本文只记录事实，不制定新任务。唯一活动任务见 [current-stage-goal.md](current-stage-goal.md)。

## 2026-09-25 M5 专项主线集成与当前结果

`codex/m5-actual-event-closure` 的 36 个提交以 fast-forward 保留历史并入
`main`，远端 HEAD 为 `8db5994994670797ea5baf81c02ce31dcd818875`。
该 SHA 的 [GitHub Core Research Gates](https://github.com/MingMingLiu0112/value-investment/actions/runs/36095275207)
为 `success`。合并树在证据齐全的专项工作树中，M5/M7 定向测试为
`66 passed, 3 skipped`；主线本地离线 Core Gate 为 `702 passed, 21 skipped`，
其中额外跳过源于主工作树缺少 Git 忽略的冻结证据，不能把它写成真实证据验证。
v7 候选通过 WPS 只读复验；正式 WPS 文件 SHA-256 保持
`64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

当前 600519 为九条已审、零条待审、两条重大 ACTUAL 事件、五项已验证 H1
事实；两条有界结果均为 `STILL_NOT_READY`，未执行真实模型、无新估值。
缺的是事件绑定且经研究复核的情景输入，不是数据抓取或工程回归。
当前研究准备见 [事件绑定研究复核包](600519-event-bound-scenario-review-20260925.md)。
下文较早时点的待审、未应用和图缺口记录仅保留审计历史，不覆盖本节当前状态。
M3 strict PIT、M4 私人输入及 M6 生产授权状态互不改变；`action=no_order`。

## 2026-09-25 M5 600519 用户确认委托复核已接入

用户以 `USER_CONFIRMED_DELEGATED_REVIEW` 提供 600519 九条 CNINFO 公告的明确材料性结论。
新增 JSON intake 入口复用原有队列对象 Hash、完整逐条覆盖、北京时间复核时间、归档 PDF
字节 SHA-256 重验及 Materiality Bridge，避免改写空白人工工作簿或另建事件规则。实际运行形成
9 条 append-only Review/Decision：2 条 `MATERIAL_REQUIRES_RECALCULATION` 进入 ACTUAL
namespace 的事件桥接候选，7 条为静默的 NOT_MATERIAL / SUPPORTING / DUPLICATE 结论；事件
尚未应用、未运行生产调度或通知，`action=no_order`。当前队列已完成 reconciliation；后续有界
失效与事实重算必须以这两个桥接事件为输入，不能把“已失效”写成“已得到新估值结论”。

随后新增 `m5_research_artifact_graph.py`：它从被冻结的 runtime import candidates 建立每只证券的
实际依赖图，节点绑定制品 source SHA-256 与证据引用，缺任一必需上游制品即失败关闭。600519
已生成 7 节点的实际图收据（Research Case、Gate、Valuation、ModelValidity、PriceBridge、
Dividend Research、Current Status）；它是后续两个事件的 bounded invalidation 输入，不构成重估完成。

M5 state v3 现允许受控的离线 `ACTUAL` receipt，但必须内嵌 `USER_CONFIRMED_DELEGATED_REVIEW`
授权、Review/Queue/Graph SHA-256，且显式禁用 scheduler、notification 与 production database write。
历史 v1/v2 simulated state 保持可读。对本批 600519 事件的运行时钟检查发现队列水位只覆盖至
`2026-09-09`、抓取时间为 `2026-09-24T08:47:15Z`，早于 `2026-09-25` 人工复核；因此未写入
ACTUAL state，等待一次新的 CNINFO 完整扫描来证明复核后的公告覆盖。该水位限制不阻塞其他离线工程。

## 2026-09-25 M5 600519 真实离线事件收据

随后以新的 CNINFO 完整扫描解除上述**旧水位**限制：扫描覆盖至 `2026-09-25`，检索于
`2026-09-25T00:05:27.848712+00:00`，9 条候选的归档 PDF 字节 Hash 全部与用户已确认
复核一致。对账收据结果为 `9 CARRY_FORWARD_PRIOR_HUMAN_DECISION / 0 pending / 0 hash conflict`；
这只沿用相同原件的既有人工结论，不由机器重新判定材料性。

新增 `scripts/apply_m5_actual_offline_request.py`。它要求当前完整水位、零待人工/Hash 冲突的
对账、原 Review/Queue/Graph Hash 和 `USER_CONFIRMED_DELEGATED_REVIEW` 同时匹配；命令拒绝未来
`generated_at`，并始终禁用 scheduler、notification 与 production database write。

基于以上输入，本机生成一份 append-only `ACTUAL` 离线收据：接受 2 条
`MATERIAL_REQUIRES_RECALCULATION` 事件、形成 2 条有界 invalidation 与 2 条仅本地 `REVIEW_DUE`
outbox 项，状态为 `ATTENTION`，没有生成新事实、估值、价格结论、Decision Review、通知或订单。
收据路径为 `runtime/m5-600519-disclosure-rescan-20260925/actual-valid-application-20260925`，其
`receipt_id` 为 `m5-run-56f1d3a52fb26e69a04cbc735f8d451a`，`state_sha256` 为
`8315eeb043b77adddb0a4c3a3772e404539a80731d092dbb0b8aca1423fd63ea`。这证明事件失效链已经进入
真实离线状态，不证明重算完成，更不构成 M5 产品验收或 M6 生产授权。

一次本地试运行曾提供未来 `generated_at`，已在其 runtime 目录内显式标注为无效，未进入任何服务或
用户展示；新命令已增加未来时间拒绝。有效收据使用 `2026-09-25T08:10:00+08:00`，处于新水位的
15 分钟时钟约束内。

## 2026-09-25 M5 有界重算计划与图缺口

新增只读 `m5_recalculation_plan.py` 及其生成命令。它从冻结的 receipt、事件、图和原件引用
派生任务，不执行任何事实抽取、估值计算或决策更新。600519 的真实计划绑定上述 ACTUAL receipt，
明确产生 `financial_facts` 和 `valuation_result` 两个 `BLOCKED_GRAPH_GAP`：当前冻结图只含
估值输入制品而没有可替换的事实/结果节点。其余模型有效性、研究论点、估值输入和决策复核均保持
`REVIEW_REQUIRED`。因此系统下一步必须先建立带原件 Hash 的更新事实节点，不能把旧估值解释为
已重算。计划制品为 `runtime/m5-600519-disclosure-rescan-20260925/actual-valid-recalculation-plan-20260925.json`，
`action=no_order`。

## 2026-09-25 全量回归与私有测试隔离

跨平台 Git 工作树边界修复后，完整测试套件使用仓库内 disposable base temp 重放为
`2555 passed, 6 skipped`（Python 3.13）。私有输入测试不再把通用 `tmp_path` 当作私有根，
而是在仓库外创建并自动清理临时根目录；因此它同时验证“任意 Git worktree 必须拒绝”和
“有效的仓库外私有根可以加密/读取”。这只是测试夹具纠偏：生产路径仍 fail-closed，不读取
真实私人数据，不改变 M4/M5/M6/M7 状态，且保持 `action=no_order`。

提交 `28c3826` 的 GitHub Actions [Core Research Gates #99](https://github.com/MingMingLiu0112/value-investment/actions/runs/36071527041)
也已在 Linux / Python 3.12 成功；该 CI 是 workflow 覆盖范围内的独立验证，不替代上述全量本地回归。

## 2026-09-25 Core Research Gates 跨平台修复已验证

此前 GitHub `offline-core` 在 Linux / Python 3.12 发现私有根边界测试没有构造真实 Git
工作树。修复后，本地按 workflow 清单重放 `677 passed`，GitHub Actions 对提交
`bc60a5d` 的 [Core Research Gates #97](https://github.com/MingMingLiu0112/value-investment/actions/runs/36029512736)
结论为 `success`。该记录只证明工程/隐私合同回归通过；不改变 M4 个性化、M5 人工复核、
M6 授权或任何投资决策状态。

## 2026-09-25 M5 人工公告复核只读简报

新增 `m5_disclosure_briefing.py` 和
`scripts/build_m5_disclosure_review_briefing.py`。它在生成阅读辅助前逐条重算已归档
PDF 的 SHA-256；原件缺失、路径越界、Hash 不一致或 PDF 解析失败都会失败关闭。输出仅包含
公告身份、原件来源、页数、标题规则对应的阅读提示、文字命中页和受限片段，明确不含
`EventMaterialityDecision`、受影响领域或交易结论。

已对 600519 的 9 条待复核公告生成私有 runtime 简报；9 条仍全部为
`PENDING_HUMAN_REVIEW`，不创建 ChangeEvent、通知、仓位或订单，`action=no_order`。
模块及原有回填合同定向回归 `25 passed`；更广的 M4/M5/M6 边界回归 `197 passed`。

简报现可作为可选的 `04_阅读简报` 页嵌入新建的人工复核候选工作簿，显示经 Hash 验证
PDF 的页数、阅读提示、命中页与受限原文片段；原 `01_人工判定` 的结论列继续全部留空。
600519 的新候选包为 5 页、9 条待复核公告，未写入 WPS、未替换 v2 或正式 Excel。

## 2026-09-25 M7 冻结制品与 M6 可变指针隔离

全量离线回归发现 M7 的冻结工作台生成器错误依赖 M6 的
`m6-operational-preflight-latest.json`。一次新的预检运行会改变该指针，导致工作台固定
Hash 校验失败。现改为只读取已固定的 M6 receipt；后续 `latest` 预检不会改变冻结 M7
候选的事实集。修复不升级 M6/M7 状态、不触发生产动作，`action=no_order`。

同类审查随后确认 M3 audit 也曾保留 `latest` pointer 作为冻结工作台输入；现同样改为
固定 receipt。M3 strict contemporaneous-rule PIT 的未证明状态不因此变化。

## 2026-09-25 M4 私有输入 Git 工作树边界

GitHub Linux CI 暴露出一项跨平台测试缺口：CLI 只验证项目根目录，测试却把普通临时目录
误当作仓库。现在私有根还会拒绝位于任何 `.git` 目录或 linked-worktree `.git` 文件下的
路径；测试构造真实 Git marker，因此 Windows 与 Linux 都验证同一隐私边界。该变更不读取
实际组合，不打印私有字段，仍保持 `action=no_order`。

`test_m5_disclosure_briefing.py` 也已加入 `offline-core`，确保后续简报生成不会绕过
PDF Hash 复核或无结论边界。

## 2026-09-25 M6 未授权生产授权包

新增 [M6 生产授权包](m6-production-authorization-package-20260924.md)，把未来数据库
migration、调度、通知、私有数据、资源、备份和 Shadow 的授权范围、停止条件与回退要求
集中为显式清单。它明确记录 M3-M5 产品门、真实恢复、20 个真实交易会话和真实事件均未
满足，不能代替用户授权。预检配置和加密备份清单绑定该文件；M6 仍为
`PREFLIGHT_DONE / operationally NOT_STARTED / NOT_YET`，全程 `action=no_order`。

## 2026-09-25 M4 私有快照对账合同

新增 `portfolio_reconciliation.py`。该合同仅在私有内存中比较同账户、同日期的两个实际
组合快照，分别检查现金、证券存在性、交易所、数量和公司行为调整状态。完全一致仅产生
`MATCH_PENDING_HUMAN_CONFIRMATION`，不会自动将快照升级为已对账；现金缺失为
`INCOMPLETE`，差异为 `MISMATCH`。新增合成对账反例；M4 领域定向回归为 `59 passed`，
无真实账户读取、无公开持久化、无仓位或订单，M4 仍为 `PARTIAL`。

## 2026-09-25 M4 非个人化工程审计

经代码与反例回归核对，M4 的 IPS/快照合同、私有加密边界、快照对账、现金预算、集中度、
分层容量、股息投影、M3 决策绑定和 M5 失效投影均已具备非个人化实现。状态更新为
`M4 non-personalized engineering = COMPLETE`，但 `M4 personalized acceptance =
PENDING_USER_PRIVATE_INPUT` 不变。该结论不读取或猜测用户数据，不生成真实组合建议；
详细矩阵见 [M4 非个人化工程审计](m4-nonpersonal-engineering-audit-20260925.md)。

为使未来私有输入不必进入聊天、WPS 或 Git，新增
`scripts/encrypt_private_portfolio_input.py`：它只读取私有根内的 UTF-8 JSON、按原有
领域合同校验后写入不可覆盖的 AES-256-GCM 密文，并只输出脱敏回执。临时明文不会被命令
删除或写入 runtime；后续处理仍由用户的私有保留政策决定。M4 定向回归为 `75 passed`。

## 2026-09-24 M6 预检阶段状态对账

`config/m6-operational-preflight-v1.json` 曾保留旧的 `m2=PENDING_HUMAN_REVIEW`，
与当前 append-only Checkpoint A `HUMAN_PASS` 冲突。现已改为 `m2=DONE` 并增加直接读取
正式配置的回归测试。M3-M5 仍为 `PARTIAL`，所以 M6 前置条件、生产授权和运营验收均没有
升级；本变更只防止授权材料引用过期 M2 状态。

## 2026-09-24 M4 私有组合输入加密边界

新增 `private_portfolio_intake.py`，补足 M4 合同与未来真实私有输入之间的最小安全边界。

- 只接受人工确认、已对账且 `ACTUAL` 的 `PortfolioInputBundle`，以 AES-256-GCM
  写入新密文；文件不可覆盖，加载后重新执行原有领域验证。
- 私有根必须在仓库之外；`WPSDrive` 及额外配置的同步根、仓库路径、密钥与私有根同址
  均失败关闭。密钥必须是私有根外部的独立 32-byte hex 常规文件。
- 对抗复核发现密钥路径先前可位于仓库内；现已显式拒绝，防止未受版本控制的密钥被错误
  放在代码树中后再被提交。该反例已加入定向测试。
- 解密只在内存中进行；输出回执只有密文 SHA-256、密钥标识、创建时间和 `no_order`，
  不含 IPS、现金、持仓或账户数据。`.viportfolio` 已加入 Git 忽略。
- 新增 3 个合成 fixture 回归，覆盖往返、无敏感回执、仓库/WPS/密钥隔离、不可覆盖、
  错误密钥和篡改密文；相关 M4 合同和 M6 加密回归为 `16 passed`。
- 未读取真实账户、未做账户导入、未持久化明文、未产生个性化仓位/订单。M4 仍为
  `ENGINEERING_DONE_SIMULATED / PARTIAL / PENDING_PRIVATE_INPUT`。

## 2026-09-24 M6 历史 ingest 拒绝聚合视图

新增只读聚合入口 `scripts/audit_m6_historical_ingest_rejections.py`，解决后续完整扫描
返回 `HEALTHY` 后历史 ingest 拒绝从当前 run health 消失的问题。

- 从 durable M5 receipt 文件重新读取字节，严格解析 JSON，验证文件名/receipt id、
  `receipt_sha256`、`audit_fingerprint`、内嵌 state/checkpoint 和
  `no_order` 边界。
- 最新 state 的 `batch_records`/checkpoints 是链锚点；每个历史 revision 必须有且仅有
  一份 receipt，batch/run/namespace/time/checkpoint/request fingerprint 必须一致。
- 新增 batch record `receipt_audit_fingerprint`，默认保持旧状态序列化兼容；新 receipt
  必须与该字段一致。这样 rejected result 没有 event 时，单改 receipt 并重算内部 Hash
  也不能伪造历史拒绝。
- 损坏、重复、额外、缺失、跨 stream、state rollback 或绑定不符均失败关闭；后续
  `HEALTHY` 不能清除历史 `FUTURE_REJECTED / CONFLICT_REJECTED /
  OBSERVED_TIME_REGRESSION_REJECTED`，聚合状态保持 `ATTENTION`。
- 输出固定 `action=no_order`，明确 `SIMULATED_OFFLINE_ONLY`、真实运营计数 false 和
  `LOCAL_CONSISTENCY_ONLY` 真实性边界；读取入口不实例化可写 store，不接数据库、
  调度、通知、Excel 发布或订单。
- 新增定向回归 `10 passed`；M5/M6 联合回归 `132 passed`；全量离线回归
  `2541 passed, 5 skipped, 18 warnings, 0 failed`。M6 仍为
  `PREFLIGHT_DONE / operationally NOT_STARTED / PENDING_AUTHORIZATION`。

## 2026-09-24 M5 归档 PDF 字节复核与回填关系字段

M5 人工材料性入口不再把队列 JSON 中的 PDF Hash 当作信任根。

- 新增统一 `verify_archived_pdf()`：要求唯一归档 PDF 引用、canonical 公告路径、
  归档根目录边界、非链接路径和 `%PDF-` magic，并从文件字节重新计算 SHA-256。
- `build_disclosure_materiality_reviews()` 与 `reconcile_m5_human_reviews()` 共用该
  验证器；历史判定只有在当前原件字节和 prior decision Hash 一致时才能结转。
- 回填工作簿新增 `替代事件ID`、`事件簇ID`，旧 13 列工作簿保持可读；PDF Hash 单
  元格附加本地归档 PDF hyperlink，单元格值仍是 Hash 文本而非公式。
- 真实只读核对：既有 24 条候选全部 Hash 通过；600519 9 条候选全部 Hash 通过，
  9 个摘要互不重复。
- 生成 600519 空白 v2 人工复核包，9 条公告仍为 `PENDING_HUMAN_REVIEW`，判定和
  复核说明均为空；WPS 云盘同名副本与仓库文件逐字节一致。
- 归档 PDF/工作簿定向回归 `30 passed`，全部 M5 回归 `165 passed`，本地全量离线
  回归 `2531 passed, 5 skipped, 18 warnings, 0 failed`；`compileall` 和
  `git diff --check` 通过。
- 不生成事件、通知、Entry、仓位或订单；`action=no_order`，`M5=PARTIAL`。

## 2026-09-24 M5 fail-closed 加固

第二轮对抗审查针对事件身份、批次 replay、水位时钟、invalidation 投影和人工材料性
边界构造反例；本轮修复后，相关错误均失败关闭，但真实公告到 persisted state 的离线
产品链仍未收口。

- 事件身份升级为 `source-id-v3` 并把 PIT 时间规范化为 UTC；v2/v1/legacy 身份算法保持
  冻结兼容，v2 与 v3 不能在无显式 correction 时静默混合去重。
- 已接受批次现在从 checkpoint 的 pre-batch prefix 精确 replay，原 ingest verdict、
  invalidation 和 alert 与首次 receipt 一致；duplicate 新批次不会重复创建 alert。
- 运行时钟不得早于事件 observed time；未来水位被拒绝，默认 stale 超过 15 分钟的
  watermark 失败关闭，不再产生静默 `HEALTHY`。
- M4/M5 投影拒绝跨公司或跨 kind 的伪造 invalidation；`result_id` 绑定 receipt state、
  dependency graph 和最终 artifact states。
- materiality source hash 必须跨 decision/source ref/human evidence/current state 一致；
  review 扫描窗口不得覆盖未来，decision clock 不得晚于 review clock；所有身份版本的
  material announcement 都必须人工复核。
- M4/M5 及人工 review reconciliation 定向回归 `146 passed`；本地全量离线回归
  `2507 passed, 5 skipped, 18 warnings, 0 failed`；`compileall` 和 `git diff --check` 通过。
- 尚未实现可反序列化的 bridge/run request 和 durable receipt writer/reader，apply
  仍停在 bridge artifact；600519 的 9 条真实公告保持 `PENDING_HUMAN_REVIEW`。
  `M5=PARTIAL`，`action=no_order`。

## 2026-09-24 M5 Outbox 迁移展示候选 v2

冻结的 6 页 M5 事件候选之外新增独立 v2 展示候选，使提醒投递状态、身份版本和来源
字段可在原 Excel 中直接审计。v1 文件与 SHA-256 不变，M7 继续固定引用 v1。

- 新文件 `A股价值投资_M5事件监控候选_v2_20260924.xlsx`，7 页、17,652 bytes、
  SHA-256 `5c3f1e7aee518029a6cc5da10139a86aecd61a9acf5caf37a56dfe69d747d1bc`。
- `01_事件账` 新增身份版本、来源 ID，并把被 correction 取代的旧版本显示为
  `已被替代`；`05_Outbox迁移` 新增逐行来源事件 ID、来源 ID、身份版本和动作。
- 总览固定 7 个输入、5 个当前有效事件、6 个提醒、outbox revision 7、7 条迁移和
  `action=no_order`。v1 的 6 是冻结 receipt 快照计数，v2 的 5 是当前 active ledger
  计数，版本记录已明确区分。
- manifest 升级为 `m5-outbox-transition-candidate-v2`，绑定 base/迁移 fixture、
  workbook/state Hash、6 个提醒终态、冻结 v1 parent Hash 和 builder/module Hash。
- 对抗审查发现并修复：多版本 alert 解析歧义、未来迁移时间、receipt/current_state
  脱钩、发布竞态、迁移行来源缺失、终态清单不完整、被替代事件误标为已接受，以及
  等价时区的 transition ID 不幂等问题。v1 非 `PENDING` 且无迁移历史的旧状态仍作为
  非阻断兼容债记录，不伪造迁移历史。
- `tests/test_m5_outbox_transition_candidate.py` 8 passed；全部 M5 定向回归
  `120 passed`；本地全量离线回归 `2483 passed, 6 skipped, 18 warnings, 0 failed`。
- WPS 只读收据 `runtime/m5-outbox-transition-wps-v2-20260924/receipt.json` 为
  `passed`；WPS 云盘同名 v2 副本与仓库文件 SHA-256 一致。
- 公开工作簿 WPS 云盘全量字节审计更新为 `30/30 MATCH`。
- 未发送通知、未接生产源、未修改 PTA、数据库或调度；`M5=PARTIAL`。

## 2026-09-24 M5 Outbox 迁移日志与历史不可改写

M5 状态此前只能把 outbox 状态与事件批次 revision 绑在一起，提醒从 `PENDING` 到
`SENT/DELIVERED/ACKNOWLEDGED` 的过程没有独立、可重放的追加日志。本轮补齐离线
迁移日志，不接通知网络，也不改变 `M5=PARTIAL`。

- 新增 `outbox_revision` 与不可变 `outbox_transitions`；成功、失败、重试迁移可以
  在不伪造事件批次或 checkpoint 的情况下持久化。
- `M5EventRunStateStore` 允许同一事件批次 revision 追加一个合法 outbox successor，
  同时继续拒绝陈旧 writer 和无关摘要改写。
- event-batch successor 现在校验旧事件、checkpoint、watermark 和 outbox alert 的
  历史边界；旧事件只能逐字段不变，或由明确 correction/supersede 将
  `ACTIVE` 改为 `SUPERSEDED`。
- 对抗审查复现并修复了“伪造第三批次改写旧事件 `ingested_at`，同时保持日志外观”
  的高优先级反例，新增 store rejection 回归。
- 事件身份新增 canonical `source-id-v2`，并保留 v1/legacy 精确兼容；v1 批次
  fingerprint 不变，v2 绑定 PIT 时间，混合 v1 -> v2 correction 链按输入事件 ID
  精确重放，冻结 demo 继续复现历史事件 ID。
- 迁移/StateStore/事件/工作簿边界定向回归 `77 passed`，全部 M5 定向回归
  `115 passed`，本地全量离线回归 `2474 passed, 6 skipped, 18 warnings, 0 failed`。
- 未发送任何真实通知，未接生产源；外部单调/签名防回滚、掉电级耐久性、生产采集、
  通知投递、身份版本展示和真实恢复演练仍未完成。`action=no_order`。

## 2026-09-24 M5 事件与 canonical outbox 提醒绑定

运行状态此前只验证“outbox 中的提醒必须引用已有事件”，没有验证“已有事件必须有
自己的提醒”。删除提醒或把提醒类型改成 `SYSTEM_HEALTH` 后，状态仍可能显示健康。

- 事件到提醒类型的映射移到 outbox 领域，run 协调器与状态恢复共用同一个 canonical
  映射，避免后续重复维护后漂移。
- `M5EventRunState` 现在逐事件要求 canonical alert、规范 dedupe key、一致严重度和
  人工复核标志；缺失或伪造会失败关闭。
- 系统源扫描事件强制 `requires_human_review=true`，不能通过输入关闭源健康人工复核。
- 新增四项反向覆盖；全部 M5 定向回归 `97 passed`，本地全量离线回归
  `2456 passed, 6 skipped, 18 warnings, 0 failed`。`action=no_order`。

## 2026-09-24 M5 本地 StateStore 与 CAS 持久化

上一批 `expected_revision` 只能检查调用方快照；如果状态只留在内存，进程退出或并发
写入仍可能丢失批次结果。本轮在离线 M5 上新增独立本地状态存储层，不改变
`M5=PARTIAL`，也不接入生产调度或通知。

- 新增 `M5EventRunStateStore` 协议、`InMemoryM5EventRunStateStore` 和
  `JsonM5EventRunStateStore`；commit 同时绑定 `expected_revision` 与
  `expected_sha256`，同一 revision 只允许幂等写入同一状态摘要。
- JSON 存储按 state key 分文件，使用同目录临时文件、文件 `fsync`、`os.replace`
  和本地文件锁；损坏 JSON 失败关闭且不会被静默覆盖。
- 新增 `run_event_batch_persisted()`，重新加载当前状态，以 CAS 执行一个批次并提交；
  陈旧调用方快照在执行前失败关闭，竞争写入不会覆盖较新 revision。
- 新增 8 项存储回归，覆盖往返、重放、陈旧 revision、跨实例 CAS、损坏 JSON、
  陈旧 wrapper 快照和第二批次持久化。全部 M5 定向回归 `96 passed`。
- 本地全量离线回归 `2455 passed, 6 skipped, 18 warnings, 0 failed`。
- 该层只提供本地原子替换和进程内多实例 CAS；它不是外部单调/签名状态存储，不承诺
  完整掉电耐久性，也未完成真实通知投递、生产采集或恢复演练。`action=no_order`。

## 2026-09-24 M5 运行状态与批次重放收口

在 M5 离线事件基础设施上完成状态聚合、批次幂等和恢复边界收口。该工作不接生产源、
不发送通知、不创建常驻服务，也不改变 `M5=PARTIAL` 或人工/运营待办。

- 新增 `M5EventRunState`，把事件账、水位、checkpoint、outbox 与 batch record 作为
  单个可版本化状态导出并失败关闭恢复。
- 事件去重键加入 `source_id`；旧事件 ID 兼容只在缺少来源字段且人工复核/生效时间
  保持安全默认值时启用，禁止通过删除字段降级校验。
- run-once 协调器使用稳定 state lock、批次请求 fingerprint、原始
  `run_id/namespace/generated_at` 和 receipt/checkpoint 交叉绑定。
- 新增 `expected_revision` 以防陈旧快照被调用方误提交；完整原子 StateStore/CAS
  仍属后续工程，本批次不宣称具备生产级并发持久化。
- 新批次即使全部拒绝也保留审计 checkpoint；同 batch ID 仅原 run/原输入可重放；
  watermark 前进后仍可重放旧批次，不再错误拒绝或误报 no-op。
- checkpoint、outbox、watermark、event、batch record 和 receipt 的跨账本引用、
  时间、严重度与人工复核一致性均失败关闭。
- 新增 `tests/test_m5_event_run_state_boundaries.py` 13 项边界回归；M5 定向回归
  `88 passed`。
- 本地全量离线回归：`2447 passed, 6 skipped, 18 warnings, 0 failed`。
- 未接生产、未发送通知、未生成仓位或订单；`action=no_order`。

## 2026-09-24 M4 输入完整性与失败关闭收紧

人工审查 M4 非个人化合同时发现，JSON 加载器使用 `bool()` 会把字符串 `"false"`
解析为真值；组合中未进入候选映射的持仓也不会计入行业和周期暴露，可能高估未来
可加仓空间。

- 组合持仓、风险属性和仓位候选的布尔字段改为严格 JSON boolean，字符串假值失败关闭。
- 组合输入递归拒绝嵌套执行字段，避免 `target_weight` 等字段藏在持仓对象中被忽略。
- 对账组合中的每个持仓必须存在证券风险属性；缺失时仓位指引为 `INCOMPLETE`，不输出
  行业/周期可加仓空间。
- 指引日期必须不早于 IPS、持仓快照和 tier policy 日期。
- 新增五项反向回归；M4 合同/风险/仓位/股息/联合定向回归 `59 passed`。
- 未读取真实账户/IPS/持仓，未生成目标仓位或订单；`action=no_order`。

## 2026-09-24 M6 运营控制历史与恢复完整性

M6 预检的状态文件可导出 JSON，但恢复入口原来只校验当前 mode 与 permissions，
没有确认 history 是否连续、最后一步是否就是当前快照，也会把字符串 `"false"` 当成
真值。该缺口可让审计文件展示一个未经真实状态机产生的生产权限状态。

- `ModeChange` 与状态切换增加模式、方向、时区、原因、操作者和授权校验；时间必须
  严格向前，同一模式不得重复记录为切换。
- `from_dict` 要求 schema/action 精确匹配、permissions 必须是布尔值，并重放整条
  历史链验证 `OFFLINE_ENGINEERING -> STAGING -> SHADOW -> LIMITED_USE`、
  紧急停止和重置授权规则。
- 当前快照必须与历史最后一步的 mode、授权、时间、原因和操作者完全一致。
- 新增四项反向回归；`test_m6_operational_control.py` 为 `9 passed`，M6
  control + readiness 联合回归为 `18 passed`。
- 状态仍为 preflight engineering done / operational `NOT_STARTED`；
  未连接生产、未开启 shadow、`action=no_order`。

## 2026-09-24 M5 事件账重放完整性收紧

Checkpoint B 继续等待人工复核，本轮在 M5 离线事件基础设施上补做序列化重放审计。
原实现只在增量追加时依赖内存状态，没有在 `event_ledger_from_payload` 重放时完整
验证更正/替代链路。损坏或人工篡改的事件账可能带有缺失目标、跨来源更正、活动目标
或没有后继的 `SUPERSEDED` 事件。

- `correction_of_event_id` 现在必须指向相同证券且相同 `source_event_id` 的当前有效
  事件；跨来源变化若确需替代，只能使用语义独立的 `supersedes_event_id`。
- 序列化账本校验目标存在、目标先于后继、证券一致、每目标唯一后继，以及
  `SUPERSEDED` 与引用关系互相对应。
- 同一来源事件的历史版本不得保持活动；`ingested_at` 不得回退，
  `last_observed_at` 必须等于最后一条已接受事件的观察时间。
- 增加 checkpoint 与 outbox 的失败关闭恢复入口：检查点尝试不得重叠、序号不得
  回退；提醒的尝试次数、重试时间和投递时间必须与状态自洽。
- 租约要求 owner 与 token 同时匹配，并拒绝 release/renew 时间倒置。
- 新增八项反向/往返回归；定向回归 `32 passed`，全部 M5 定向回归 `70 passed`。
- 不改变事件类型、生产采集、通知投递、M5 人工材料性结论或冻结候选；
  `M5=PARTIAL`、`action=no_order`。

## 2026-09-24 M3 Checkpoint B 只读逐卡复核明细

在不改变三份冻结候选 Hash 的前提下，新增逐卡明细 v2，绑定基础复核包和二〇二六
年九月二十三日冻结的三家公司研究档案：

- 每家公司保留冻结档案中的反证、论点破坏条件、下一次事件和研究缺口。
- 明细仅作人工理解辅助，状态固定 `PENDING_HUMAN_REVIEW`、`action=no_order`。
- v1 因研究缺口 Markdown 渲染缺陷被 v2 替代；历史 v1 保留，不删除、不覆盖。
- 明细 JSON SHA-256
  `0d9f938b9fd2c3d003e8d035cd0912f7187ebed63f5f4e089103994b6d8c7a42`，Markdown
  SHA-256 `fab6040c893ec37752393b624fa07c22e918c08fc53e7e9b96e5f821a1ce9313`。
- 定向回归 `2 passed`；未生成 Entry、Journal、仓位、订单或人工收据。

## 2026-09-24 M3 公开历史链时序完整性续收

Checkpoint B 继续等待人工复核，不生成新候选或人工收据。在上一轮
Journal/Consistency ID 与 Entry 归属检查基础上，补上公开 `DecisionHistoryChain`
的剩余时序合同：

- 日志更正必须严格晚于被更正的前任；同一时间戳不再作为可排序更正接受。
- 任一日志时间不能早于冻结 Entry 的人工确认时间。
- 一致性复核日期不能早于冻结 Entry 的 Entry 日期。

新增四个反向测试，防止“更正与前任同刻”、日志倒置 Entry 和一致性复核穿越历史。
M3 相关定向回归 `86 passed`。本工作不重算 Checkpoint B 三份冻结候选，不改变其 Hash，
`action=no_order`。

## 2026-09-24 M3 决策日志链完整性收紧

在 Checkpoint B 等待人工签收期间，继续 M3 可独立完成的领域合同工作。复核发现
`DecisionJournalEntry` 尚未强制“人工决定”与“复核状态”同向，`DecisionHistoryChain`
也只检查更正前任 ID 是否存在，没有检查重复日志、Entry 归属和更正时间顺序。该缺口
可能让自相矛盾或错误链接的决策记录进入公开历史链。

- `CONFIRM_BUY/ADD/HOLD/REDUCE/EXIT` 现在必须匹配对应
  `MANUAL_BUY_REVIEW/MANUAL_ADD_REVIEW/HOLD/MANUAL_REDUCE_REVIEW/
  MANUAL_EXIT_REVIEW` 状态。
- 只有 BUY/ADD/REDUCE/EXIT 可以携带确认价；REJECT/DEFER/CANCEL/HOLD 不能再附带
  成交价。
- 公开 `DecisionHistoryChain` 拒绝重复 Journal/Consistency ID、日志绑定其他 Entry、
  未知前任和早于前任时间的更正。
- 新增五个反向测试；M3 定向回归 `53 passed`，GitHub Core Research Gate 同清单本地
  运行 `549 passed、4 skipped、0 failed`。
- 不重新生成 Checkpoint B 候选，不改变其冻结 Hash；`action=no_order`。

## 2026-09-24 M2 全量机器验收复算

在包含真实全量本地回归的隔离 basetemp 下重新执行 M2 AC1-AC12 验收器，结果不再
停留在“部分证据来自旧文本”的状态：

- 本地完整离线回归：`2369 passed、6 skipped、0 failed、18 warnings`，
  耗时约 323 秒。
- AC1-AC7、AC11 全部 `DONE`；AC8-AC10、AC12 保持
  `PENDING_HUMAN_REVIEW`，没有用机器结果代替用户复核。
- 收据：
  `runtime/m2-acceptance-audit-20260924T062704Z/receipt.json`
  SHA-256
  `2fb22e04f38c0ef5563429bf289804769c36c21eac394f13d0b38d992b11a878`。
- `action=no_order`；未修改冻结 M2 输入、原工作簿或生产服务。

## 2026-09-24 M3 strict PIT 证据检索结论

对仓库、`runtime/strategy-validation`、docs 与 config 检索后确认：最早 Git 提交
为 2026-09-01，600519 / 2024-06-21 重放所用 Median-PE 规则登记于 2026-09-12。
不存在可验证的当时已注册规则，因此 strict contemporaneous-rule Historical PIT
保持 `NOT_PROVEN`，人工审查验收标准第 11 条仍未满足。当前重放继续按
`RETROSPECTIVE_RESEARCH_EXTENSION`、`future_rule_version_used=true`、
`WAIT`、`action=no_order` 保存，不升级为 strict PIT。详细检索见
[m3-historical-pit-evidence-20260924.md](m3-historical-pit-evidence-20260924.md)。

同日进一步收紧同期规则合同：`CONTEMPORANEOUS_RULE` 现在必须绑定至少一条
早于 `registered_at` 的独立规则证据，并新增 strict-PIT 证据审计入口。对现有
2024-06-21 案例的真实审计仍为 `NOT_PROVEN`，收据
`runtime/m3-strict-pit-evidence-audit-20260924T080000Z/receipt.json`，
SHA-256
`9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c`。
该收据证明缺证据没有被机器状态美化，也未把追溯规则升级为同期规则。

## 2026-09-24 M3 三份机器验收复算

在同一个干净 HEAD 上分别重新执行 M3 决策卡、原工作簿候选、历史链叠加候选的
验收器，并内嵌对应定向回归证据：

- M3 决策卡：m3c1-m3c6 `DONE`，定向回归 `35 passed`；m3c7 人工。
- M3 原工作簿候选：owc1-owc6 `DONE`，定向回归 `7 passed`；owc7 人工。
- M3 历史链叠加候选：hoc1-hoc6 `DONE`，定向回归 `11 passed`；hoc7 人工。
- 三份收据均保持 `PENDING_HUMAN_REVIEW`、`action=no_order`，未生成 Entry、
  Journal、个人组合或订单。
- 收据目录：
  `runtime/m3-decision-acceptance-audit-20260924T062947Z`、
  `runtime/m3-original-workbook-audit-20260924T063010Z`、
  `runtime/m3-history-original-workbook-audit-20260924T063017Z`。

## 2026-09-24 M4 Decision Binding v2 Excel 候选

在 M4 正向容量绑定收紧后，重新生成并发布两个只读模拟候选，使 WPS 中的展示层与
当前领域合同一致。v1 文件保留，未覆盖。

- M4 v2：`A股价值投资_M4仓位与股息候选_v2_20260924.xlsx`
  - SHA-256 `2f17b4926d8634fd45c8a57335b99b477aa6c9559616e6bd5053dbb506e9a037`
  - 5 页、`BUDGET_CONFLICT`、`action=no_order`。
- M4/M5 v2：`A股价值投资_M4M5联合检查点候选_v2_20260924.xlsx`
  - SHA-256 `470c73209ee87b3855387eb47a890eb0187b3fc83d5cd15cf145d6e2eef9c10a`
  - 6 页、联合状态 `NEGATIVE`、`action=no_order`。
- WPS 云盘副本逐字节一致；两个 WPS 只读验证均 `passed`。
- 公开工作簿 WPS 云盘副本全量审计由 23/23 更新为 `25/25 MATCH`。
- 未修改 canonical、v1 候选、M1/M2 冻结证据、生产原表或生产服务。

## 2026-09-24 M4 BUY/ADD 决策绑定缺口收紧

复核 2026-09-24 人工审查手册第 22、23、41 节时发现，`PositionCandidateInput`
虽然已经提供 M3 binding 字段，但 `decision_binding_required=False` 时仍允许
`BUY_REVIEW` / `ADD_REVIEW` 在满足手工布尔前置后产生新增容量。该路径可以由错误
adapter 绕过真实 `InvestmentDecisionReview`，与 Workstream E 冲突。本轮收紧为
fail-closed：

- `BUY_REVIEW` 必须绑定 `MANUAL_BUY_REVIEW`，`ADD_REVIEW` 必须绑定
  `MANUAL_ADD_REVIEW`；未绑定的正向 intent 在领域对象构造阶段直接拒绝。
- 两个正向 intent 的价格状态必须是 `RESEARCH_ATTRACTIVE`；
  `WAITING_FOR_BETTER_PRICE`、`KEY_OBSERVATION`、`NOT_ASSESSABLE` 均不能进入
  M4 容量层。
- `decision_status` 只接受正式 `DECISION_STATUSES`，避免任意字符串绕过
  `POSITIVE_REVIEW_STATUSES`。
- `allows_new_buy_capacity()` 不再因 `decision_binding_required=False` 放行；
  模拟 M4 fixture 的正向候选同步改为显式 M3 binding，HOLD 仍可无绑定展示。
- 新增未绑定 BUY/ADD、状态不匹配、非 `RESEARCH_ATTRACTIVE` 价格三类反例测试。

定向回归 `51 passed`；仓库内隔离 basetemp 全量离线回归
`2369 passed、6 skipped、0 failed、18 warnings`。
`action=no_order`；未修改 canonical、冻结研究证据、M1/M2 历史产物或生产服务。

## 2026-09-24 M3 历史规则版本一致性加固

人工审查手册要求 Historical Research Replay 的规则、事实、报价和估值分别版本化，
且不得把追溯注册规则冒充严格同期 PIT。本轮在展示层已有 v2 纠偏之外，补上领域合同
级约束：

- `HistoricalRuleBinding` 只接受 `RETROSPECTIVE_RESEARCH_EXTENSION` 或
  `CONTEMPORANEOUS_RULE` 两种登记状态。
- 追溯规则必须显式标记 `future_rule_version_used=true`，同期规则不得误标为未来规则。
- 同期规则登记日不得晚于 replay 日期，日期统一按 UTC+8 折算，避免时区边界误判。
- 固定 Moutai 2024-06-21 输入重放仍为 `WAIT`、`future_rule_version_used=true`、
  `action=no_order`，不把该案例升级为 strict contemporaneous-rule PIT。
- 定向回归 `23 passed`；全量离线回归 `2365 passed、6 skipped、0 failed`。

## 2026-09-24 当前 HEAD 跨阶段复核与人工交接

按当前 HEAD 重新计算 M2/M3/M6 只读验收器。M2 仍为 AC1-AC7/AC11 `DONE`，
AC8-AC10/AC12 `PENDING_HUMAN_REVIEW`。M3 决策卡、原工作簿候选、历史链叠加
候选的机器门均 `DONE`，只保留对应人工复核项。M6 工程预检 `DONE`，运营验收仍
`NOT_STARTED`。

- 修复 M3 历史链审计固定 WPS 收据 Hash 过期问题：当前收据语义 `passed` 且绑定
  正确候选，但代码仍固定旧 Hash，导致 `hoc5` 误报 `PARTIAL`。本轮同步为
  `c446268c31cecbaff42c9589beec660bfe89b47883f385beeeb94ed80970d991`。
- 当前机器审计收据：M3 决策卡
  `runtime/m3-decision-acceptance-audit-20260924T050428Z/receipt.json`、
  原工作簿 `runtime/m3-original-workbook-audit-20260924T050431Z/receipt.json`、
  历史链 `runtime/m3-history-original-workbook-audit-20260924T050601Z/receipt.json`。
- M5 复核结果保持 23 条旧判断 carry-forward、1 条新公告待人工、0 Hash 冲突。
- 新增 [m2-m7-human-review-handoff-20260924.md](m2-m7-human-review-handoff-20260924.md)，
  汇总 Checkpoint A/B、私有组合输入、M5 新公告和 M6/M7 授权边界。
- 修正 README 中过时的单一 M2 目标描述，补齐当前 M2-M7 活动 Goal 与人工状态；
  自动运行章节明确生产调度、通知和服务器资源需单独授权，并保护 PTA 资源基线。
- Core Research Gates run
  [35958629202](https://github.com/MingMingLiu0112/value-investment/actions/runs/35958629202)
  的 `offline-core` 与 `postgres-integration` 均为 `success`。
- `action=no_order`；未修改 canonical、冻结研究证据或生产服务。

## 2026-09-24 M2 历史签名兼容与 M7 使用手册

复核发现，2026-09-24 人工审查纠偏扩展了 `ChannelEvaluation` 的 trigger/policy/rank
字段，但 2026-09-23 生成的真实 M2 冻结收据仍使用旧六字段 coverage signature。这使
`scripts/audit_m2_acceptance.py` 在解码真实 `m2-live-20260923-v3/receipt.json` 时误报
“证据被篡改”。本轮不改冻结收据，而是在 `discovery_receipt_from_payload` 中按原始
payload 是否包含扩展字段选择旧/新签名算法；旧格式继续可解码，未纳入旧签名的后补扩展
字段不会被绕过。

- 定向回归 `25 passed`；真实 M2 审计器已能解码固定 v3 收据并继续完成 AC2-AC12 检查。
- 最终审计：AC1-AC7/AC11 `DONE`，AC8-AC10/AC12 `PENDING_HUMAN_REVIEW`，
  `action=no_order`；收据
  `runtime/m2-acceptance-audit-20260924T045545Z/receipt.json` 的 SHA-256 为
  `327137c49d6c1122e96391cab1ada897cd4ff65c936981c7dab5cc28ea611638`。
- 完整离线回归 `2361 passed、6 skipped、0 failed、18 warnings`。
- 新增 `docs/m7-assisted-use-runbook-20260924.md`，记录 M7 Daily v2 查看顺序、
  Hash 核验、WPS 复核、故障回退、私有数据与授权边界。
- `verify_m7_daily_workbench_wps.ps1` 自动创建收据目录；按手册中的命令实跑为
  `passed`，10 个可见页、2 个隐藏页、canonical Hash 均通过。
- `action=no_order`；未修改 canonical、冻结运行收据或生产服务。
- GitHub Core Research Gates run
  [35957882562](https://github.com/MingMingLiu0112/value-investment/actions/runs/35957882562)
  的两个 job 均为 `success`。

## 2026-09-24 可重复执行 WPS 云盘副本审计

新增只读脚本 `scripts/audit_public_workbook_wps_copies.ps1`，对 Git 跟踪的全部公开
工作簿与 WPS 云盘同名副本逐项计算 SHA-256，并输出可复算 JSON 收据。当前实跑结果为
`23/23 MATCH`，缺失或 Hash 不一致会失败关闭；脚本不含 `Copy-Item / Move-Item /
Remove-Item`。新增 `tests/test_public_workbook_wps_audit.py` 进入 Core Research
Gates，防止脚本退化为写入型操作或丢失 Unicode Git 路径兼容。

- 定向测试：2 passed。
- 本地完整离线回归：2359 passed、6 skipped、0 failed、18 warnings。
- Core Research Gates run
  [35956322034](https://github.com/MingMingLiu0112/value-investment/actions/runs/35956322034)：
  `offline-core` 与 `postgres-integration` 均 `success`。
- 收据：`runtime/public-workbook-wps-audit-final-20260924/receipt.json`。
- `action=no_order`；未覆盖任何工作簿，也未执行生产迁移、计划任务、通知或真实账户导入。

## 2026-09-24 人工审查纠偏收口

本节记录按同日人工审查手册完成的安全门、验证门与 M7 Daily Workbench。全部动作
`action=no_order`，未执行生产迁移、计划任务、通知或真实账户导入。

- M3 正向决策门：`PreDecisionEligibility` 保存
  `positive_price_review_eligible`；只有正向价格状态可进入 BUY/ADD 人工复核。
  `NOT_ASSESSABLE / WAITING_FOR_BETTER_PRICE / KEY_OBSERVATION` 不能产生
  `MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW`。BUY/ADD 状态矩阵回归已覆盖。
- M4 容量门：`PositionGuidance` 强绑定 typed M3 Decision Review 与
  `decision_review_id + decision_review_sha256 + decision_status`；只有有效
  `MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW` 允许新增容量，缺绑定失败关闭。
- M2 二阶段验证：18 条预注册 LEAD 完成 resolution，3 条
  `VERIFIED_FOR_DEEP_RESEARCH`、13 条 `REJECTED_AFTER_VERIFICATION`、2 条
  `INSUFFICIENT_EVIDENCE`、0 条 `UNSUPPORTED`。Quality 覆盖 873/5568，
  状态 `COVERAGE_LIMITED`；Value 文案明确仅 PE/PB/隐含 ROE 初筛；预算外对象
  保留 trigger metrics 与原始触发逻辑。
- M3 Historical Research Replay：600519 / 2024-06-21。当时年报、派息公告与
  收盘价严格取当日可知，`future_facts_used=false`；但所用 Median-PE 规则是
  2026-09-12 注册的 `RETROSPECTIVE_RESEARCH_EXTENSION`，因此
  `future_rule_version_used=true`。最终状态 `WAIT`、
  `valuation_approved=false`、`trade_approved=false`。该制品证明事实/报价
  PIT 与 fail-closed 行为，不冒充估值、交易、历史策略收益或严格同时期规则
  PIT。
- M5 旧人工复核复用：24 条当前候选中 23 条按
  `symbol + announcement_id + source PDF SHA-256` 继承，1 条新公告待复核，
  Hash 冲突 0、被取代待处理 0。
- M7 Daily Workbench 候选：
  `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_20260924.xlsx`。
  10 个可见主页面（今日总览、全市场、候选、决策、持仓、股息、事件、研究、
  历史、审计）加 2 个隐藏技术页；90 页 v2 审计工作台继续保留。
- M7 候选 SHA-256
  `0230877890ad8f2e688e1218cd5707bb4c95b33a70a7da26e4c7afa8c3894409`。
  WPS 只读验证 `passed`：12 页、页签显隐、公式错误 0、fail-closed 状态与
  canonical Hash 通过，收据
  `runtime/m7-daily-wps-20260924/receipt.json`。
- M3/M4/M2/M5/M7 定向回归 84 passed；M3 历史读取器恢复兼容
  `m3-investment-decision-v1` 旧快照，且继续接受 v2 新字段。
- 全量离线回归 2356 passed、6 skipped、0 failed、18 warnings；skip 为既有的
  PostgreSQL/外部服务条件项，warning 来自 Backtrader `utcnow()` 弃用，不改变
  投资结论。
- CI 干净 checkout 不携带本地 `runtime/` 预注册制品，因此 M2 的 4 项真实制品
  复算在 CI 显式 skip；本地工作台仍完整执行并保持 `6 passed`，不把本机专属
  runtime 文件提交到公开仓库。
- M2 Checkpoint A 仅 `READY_FOR_HUMAN_RESUBMISSION`；M3 Checkpoint B、
  M4 个性化、M5 持续运营、M6 运营验收与 M7 用户签收均未批准。

## M7 Daily Workbench v2 时点表述纠偏：2026-09-24

在上一版人工审查收口后复核发现，M7 Daily Workbench 虽然引用的
`m3-historical-research-replay` 收据已正确记录
`future_rule_version_used=true`，但工作簿页签仍写成“真实 PIT 历史重放 /
当时规则”，会把追溯注册的 Median-PE 规则误读成同时期规则。

本轮只修正展示层表述，不改重放收据、研究结论、审批状态或 canonical：

- 生成
  `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx`。
- 统一表述为：财务事实、公告和收盘价为 point-in-time；
  Median-PE 规则为 `RETROSPECTIVE_RESEARCH_EXTENSION`，
  `future_rule_version_used=true`；不声称 strict contemporaneous-rule PIT。
- M7 v2 SHA-256：
  `8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6`。
- WPS 只读验证 `passed`：10 个可见页、2 个隐藏页、公式错误 0、canonical
  Hash 不变，收据 `runtime/m7-daily-wps-v2-20260924/receipt.json`。
- M7 定向回归 `8 passed`；全量离线回归留待提交后统一复算。
- WPS 校验脚本 `verify_m7_daily_workbench_wps.ps1` 增加历史回放边界断言，并
  改为读取契约单元格 `B11.Text`，避免 WPS COM 对 `UsedRange.Text` 返回空串。
- 提交 `b654897` 后复算：非神华离线回归
  `2245 passed、6 skipped、0 failed、18 warnings`；跳过项为既有
  PostgreSQL/外部服务条件，不接触神华 PDF 审计尾集。
- GitHub Core Research Gates
  [run 35953368838](https://github.com/MingMingLiu0112/value-investment/actions/runs/35953368838)
  为 `success`，`offline-core` 与 `postgres-integration` 均通过。
- 校验脚本提交 `6b4f335` 后，Core Research Gates
  [run 35953940241](https://github.com/MingMingLiu0112/value-investment/actions/runs/35953940241)
  两个 job 均再次为 `success`。

上一版 v1 候选继续保留，作为人工审查前的历史制品；当前用户验收对象使用 v2。

## WPS 验证器文本扫描加固：2026-09-24

实机复核发现 WPS COM 在本机对 `UsedRange.Text` 返回空串，导致三个统一工作台
验证器的禁止决策文案扫描实际成为 no-op。本轮不降低断言，改为从
`UsedRange.Value2` 物化单元格文本，并在物化结果为空时失败关闭：

- M7 Daily Workbench 改为扫描全部 10 个可见主页面；禁止
  `建议买入 / 建议加仓 / 目标仓位 / 下单`。
- 90 页 M7 工作台与 96 页 M7 v2 工作台总览恢复
  `买入 / 加仓 / 减仓 / 目标仓位 / BUY / ADD` 扫描。
- M3 历史链前 5 页恢复 `目标仓位 / 下单 / 自动卖出` 扫描。
- 新增静态回归 `tests/test_wps_verifier_text_scans.py` 并纳入 GitHub Core
  Research Gate，防止以后重新使用不可靠的 `UsedRange.Text`。
- 四个候选均完成实际 WPS 只读重验，工作簿 Hash 与 canonical Hash 前后不变。
- 本地完整离线回归 `2358 passed、6 skipped、0 failed、18 warnings`，包含神华
  PDF 尾集；warning 仍为 Backtrader `utcnow()` 弃用提示。
- 提交 `45219e9`、`3aab561`、`3bc6b20` 的 Core Research Gates 均通过；
  最后一个运行 [35954917146](https://github.com/MingMingLiu0112/value-investment/actions/runs/35954917146)
  的 `offline-core` 与 `postgres-integration` 均为 `success`。
- 公开工作簿 WPS 云盘副本全量复核：23/23 逐字节一致。本轮补上此前缺少云盘
  同名副本的 `M2候选_20260924`、`M7每日工作台候选_20260924` 和
  `M2通道验证人工复核包候选_20260924`，未覆盖任何已有文件。

## M7 统一工作台 v2 候选：2026-09-24

本节记录把 M4/M5 联合检查点候选接入 M7 只读统一入口的展示层准备。`M2` 保持
`PENDING_HUMAN_REVIEW`，`M3/M4/M5/M7` 保持 `PARTIAL`，`M6` 为
`NOT_STARTED`；全部动作 `action=no_order`。

- 新增 `scripts/build_m7_workbench_v2_candidate.py`，复用 v1 受保护 graft；
  新增 `m7-workbench-candidate-v2` manifest schema 和
  `scripts/verify_m7_workbench_v2_wps.ps1`。
- 新候选把 6 页 `M4M5联合_*` 作为第七层放在 M5 展示层与 M3 基底之间，形成
  96 页统一工作台；原 90 页 v1 候选、构建器和 Hash 保持不变。
- 候选文件
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx`，
  字节数 13,271,164，SHA-256
  `d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc`。
- WPS 只读验证为 `passed`；96 页、37 个展示页顺序、10 个导航入口和 canonical
  Hash 均通过。WPS 云盘同名副本与仓库候选逐字节一致。
- M7 v1/v2 定向回归 6 passed。
- 全量离线回归：2317 passed、6 skipped、0 failed；M2 机器门仍只等当前提交的
  CI 与用户 Checkpoint A，不因离线通过改变人工验收边界。
- GitHub Core Research Gates run `35941189851` 为 `success`；按该 commit 复算后，
  M2 机器门 AC1-AC7、AC11 为 `DONE`，AC8-AC10、AC12 为
  `PENDING_HUMAN_REVIEW`。最新 M2 收据
  `runtime/m2-acceptance-audit-20260924T010927Z/receipt.json`。
- 本候选不替代 Checkpoint C/D、真实组合、真实事件观察或 M6 运营验收。

## M4/M5 联合检查点候选：2026-09-24

本节记录 M4 组合域与 M5 事件失效的只读联合候选。`M2` 保持
`PENDING_HUMAN_REVIEW`，`M3/M4/M5` 保持 `PARTIAL`，全部动作
`action=no_order`。

- 新增 `src/value_investment_agent/m4_m5_integration.py`：把 M5 依赖失效精确
  投影到组合风险、共同仓位边界、分配/股息和财务/决策链。
- 模拟结果：仓位风险变化暂停组合风险与共同仓位边界；分红变化暂停分配、股息
  可持续性与共同仓位边界；无关公司财报不误伤组合产品；论点破坏进入 `NEGATIVE`。
- 新增 6 页只读工作簿
  `A股价值投资_M4M5联合检查点候选_20260924.xlsx`，SHA-256
  `353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`。
- WPS 只读收据 `runtime/m4m5-joint-wps-20260924/wps-verification.json` 为
  `passed`。
- 定向回归 4 passed；M4/M5 联合回归 72 passed，并已加入 GitHub Core Research
  Gate。
- 本候选不构成 Checkpoint C、真实事件观察或实盘准入；真实组合与生产通知仍待
  用户授权。

## M6 运营准入预检与运行控制：2026-09-24

本节记录 M6 的非生产前置审计。`M6` 保持 `NOT_STARTED`，所有动作
`action=no_order`。

- 新增 `src/value_investment_agent/m6_operational_readiness.py`、
  `scripts/audit_m6_preflight.py` 和
  `config/m6-operational-preflight-v1.json`。
- 新增 `src/value_investment_agent/backup_security.py`、
  `scripts/package_encrypted_backup.py` 和
  `config/m6-backup-security-v1.json`：离线 AES-256-GCM 分块封装、密钥
  分离、配置/发布 Hash 清单及 package/verify 命令。
- 工程检查确认隔离恢复目标、事务快照、表级 Hash、原件 SHA-256、磁盘预留、
  256 MiB / 0.5 CPU 演练上限和公开仓库敏感文件扫描均已实现。
- 干净工作树审计收据：
  `runtime/m6-operational-preflight-20260924T000810Z/receipt.json`，
  SHA-256
  `9dadc9bdf3b7dcfb319ce35b5d7003827799a32c9dd4fe67fca74fceaba07dc3`。
- 全量离线回归：2306 passed、6 skipped、0 failed。
- 当前状态：`engineering_status=DONE`，
  `operational_acceptance_status=NOT_STARTED`。
- 待完成：实际云端同步部署与密钥保管授权、真实隔离恢复与 RPO/RTO、20 个
  连续真实交易会话、至少一个真实财务或资本事件、生产迁移/调度/通知授权。
- 本预检未连接生产 PostgreSQL、未修改服务器项目或 PTA、未读取真实持仓，
  也不能把本地测试或 fixture 当作 M6 运营验收。
- 新增 `src/value_investment_agent/m6_operational_control.py` 和
  `scripts/m6_operational_control.py`：版本化
  `OFFLINE_ENGINEERING -> STAGING -> SHADOW -> LIMITED_USE` 授权推进、
  任意阶段紧急停止、从停止状态以新授权先回到离线工程。状态文件位于
  `runtime/`，不会进入公开仓库。
- 定向回归 `tests/test_m6_operational_control.py` 5 passed，并已加入
  GitHub Core Research Gate 的 `offline-core` 作业。

## M2 机器验收最新收据：2026-09-24

完整离线回归后，M2 AC1-AC7、AC11 机器门均为 `DONE`；AC8-AC10、AC12 保留
用户复核。当前 M2 状态仍为 `PENDING_HUMAN_REVIEW`，`action=no_order`。

- 收据：`runtime/m2-acceptance-audit-20260923T234143Z/receipt.json`
- SHA-256：`4d8f20a3c68f5f5424e667bbbb170183e1d56bf7da6cf5c84e77ffb428229f60`
- 用户复核范围：WPS 原工作簿的候选池、逐通道覆盖、AC8 研究报告/反证、
  AC9 分层抽样、证据链接和导航。
- 用户完成 Checkpoint A 评估前，M2 不标 DONE，也不发布个人化正向结论。

## M7 统一工作台展示候选：2026-09-24

本节记录在人工 Checkpoint 与真实 M6 数据尚未满足时，按总目标允许提前完成的
M7 只读展示层工程。M2 保持 `PENDING_HUMAN_REVIEW`，M3、M4、M5 保持
`PARTIAL`，M6 为 `NOT_STARTED`；全部动作 `action=no_order`。

- 新增 `scripts/build_m7_workbench_candidate.py`：绑定 M3 基底、canonical 和
  六个 M4/M5 候选的 SHA-256，先显式重命名附加工作表，再用 `graft` 逐层叠加；
  任何输入变化或重复页名均失败关闭。
- 扩展 `stage_frontend_package.py` 的 `rename_workbook_sheets`：只修改
  `xl/workbook.xml` 的标题，其余 ZIP 部件逐字节保留，并校验 Excel 标题长度和
  重复名。
- 新增 90 页候选
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx`：
  `00_M7总览` + 29 个重命名 M4/M5 页 + 60 页 M3 历史链叠加基底。
- 候选 SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`；
  字节数 13,262,051；89 个源页面和 145 个源 ZIP 部件在最后一层前保持不变。
- 新增 WPS 只读验证脚本和 4 项构建器回归并纳入 GitHub Core Research Gate。
  定向回归 11 passed；全量离线回归 2292 passed、6 skipped、0 failed；WPS 只读收据
  `runtime/m7-workbench-wps-20260924/wps-verification.json` 为 `passed`。
- WPS 云盘同名候选与仓库候选逐字节一致，canonical 未被覆盖。
- GitHub Core Research Gates 首次 M7 推送 `9e37435` 的 `offline-core` 因 Linux
  runner 上新增层 ZipInfo 时间戳导致确定性回归失败；`fa23f05` 将 `graft`
  新增层时间戳固定为 `1980-01-01T00:00:00`，随后 run `35933960701` 的
  `offline-core` 与 `postgres-integration` 均为 `success`。修复只改 ZIP 元数据，
  90 页工作表内容和已发布候选 SHA-256 未改变。
- 本候选不证明 Checkpoint D、M7 交付或实盘准入；真实 M7 仍需 M2/M3 用户复核、
  真实 IPS/组合授权、M5/M6 生产观察和 Checkpoint D。

## M3 论点连续性历史链叠加候选：2026-09-24

本节记录把五页显式模拟历史链追加到已受保护的 M3 决策复核候选。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `scripts/build_m3_history_original_workbook_candidate.py`，绑定 M3 决策复核
  候选、独立历史链候选和 `tests/fixtures/m3_history_demo.json` 三个 SHA-256。
- 扩展 `stage_frontend_package.graft`，附加页复用输入 ZipInfo 时间戳，使公开候选
  跨机器重建字节稳定，不再随本地构建时间变化。
- 新增 60 页候选 `A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`：
  前 5 页为历史链，后 55 页完整保留 M3 决策复核候选；55 个源页面和 111 个源 ZIP
  部件保持不变。
- 新增 WPS 只读验证、7 项审计门 `hoc1-hoc7` 和 4 项回归；`hoc1-hoc6` 机器验证
  `DONE`，`hoc7` 保持 `PENDING_HUMAN_REVIEW`。
- 候选 SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`；
  WPS 只读收据 `runtime/m3-history-overlay-wps-20260924/wps-verification.json`
  为 `passed`，WPS 云盘副本与仓库候选逐字节一致，canonical 未被覆盖。
- GitHub Core Research Gates 运行 `35931101091` 的两个 job 均为 `success`；
  公开提交为 `d614b5b`。
- 示例链仅使用 `600887` 的显式模拟 Entry、Journal 与 Consistency；不读取真实账户，
  不构成 Checkpoint B、投资结论或实盘准入。

## M5 真实披露待复核队列：2026-09-24

本节记录真实 CNINFO 公告索引到人工材料性复核之间的离线队列。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m5_disclosure_queue.py` 与 4 页候选工作簿：标题规则只形成候选，未知标题
  保留，未来/窗口外/重复记录失败关闭，候选 PDF 缺失保持 `SOURCE_UNAVAILABLE`。
- 真实扫描三家 M1 公司，覆盖 2026-08-27 至 2026-09-24：41 条公告、24 条待人工
  复核候选、24 份候选 PDF、0 个来源失败、3/3 覆盖完整。
- runtime queue SHA-256
  `378f5366f76faaf7d9407b321419a40305baccb6126a67a4302526428a75c6b4`；
  工作簿 SHA-256
  `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5`。
- WPS 云盘同名副本与仓库工作簿逐字节一致；WPS 只读收据为 `passed`。
- 新增 10 项定向回归并纳入 CI；M5 联合回归 58 passed；除 PostgreSQL 集成外全量
  离线回归 2262 passed、2 skipped、0 failed。
- 未执行自动材料性判定、事件入账、依赖失效、生产调度、通知或数据库变更；下一步
  由用户逐条给出 `EventMaterialityDecision` 后进入已有 M5 材料性桥。

## M5 真实披露人工复核回填：2026-09-24

本节记录从真实披露队列到人工 `EventMaterialityReview` 的回填入口。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m5_disclosure_review.py` 与 4 页回填工作簿：24 条候选必须覆盖且仅覆盖一次，
  判定和说明从空值开始，缺件、重复、未来审核时间均失败关闭。
- 回填表绑定 `queue_id`、队列语义 SHA-256 和候选 PDF SHA-256；候选 PDF 缺失时对应
  扫描保持不完整，不降级放行。
- 应用命令只输出 `EventMaterialityReview` 与 `MaterialityBridgeBatch`，不执行 M5
  事件账、依赖失效、outbox、通知、数据库变更、调度或订单。
- 工作簿字节数 13,885，SHA-256
  `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420`；
  队列语义 SHA-256
  `9ff56ebe8ab2902d4339fda881c0a0d4697a1066014f477053198dd00e4e905d`。
- WPS 只读收据
  `runtime/m5-disclosure-review-intake-20260924/wps-verification.json` 为
  `passed`；WPS 云盘同名副本与仓库工作簿逐字节一致。
- 新增定向回归 15 passed；M5 联合回归 56 passed。24 条材料性结论仍待用户逐条填写，
  之后才允许显式调用材料性桥。

## M3 决策复核原工作簿候选：2026-09-24

本节记录把三张真实 M3 负向决策卡接入现有 55 页工作簿派生页 `00_决策复核` 的
候选工程。M2 保持 `PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作
`action=no_order`。

- 新增 `m3_decision_review_sheet.py`：三张卡、缺失与阻断、来源 Hash、证据引用
  和人工复核要求集中投影到一个派生页，不新增个人化结论。
- 扩展 `stage_frontend_package.py` 的 `replace_sheet`：只替换 `00_决策复核`
  XML 部件，其余 54 个页面和 113 个未替换 ZIP 部件逐字节保留。
- 新增 `scripts/build_m3_original_workbook_candidate.py`，绑定 canonical、冻结
  M1 输入与 M1 预登记 Hash；候选不自动发布。
- 候选文件 `A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx`，
  字节数 13,200,586，SHA-256
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`。
- 实际 WPS 只读验证 `passed`：55 页、决策页可见、公式错误 0、禁止信号扫描通过、
  打开前后 Hash 不变；WPS 云盘同名候选与仓库候选逐字节一致。
- 新增 4 项定向回归并纳入 CI；M3 决策与发布层联合回归 18 passed。
- 本候选不证明 Checkpoint B；用户仍需在 WPS 中阅读三张卡并复述理由与反证。

## M3 原工作簿候选验收审计：2026-09-24

本节记录把上一批 M3 原工作簿候选纳入受保护、可重复执行的机器审计。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m3_original_workbook_acceptance_audit.py`：固定 canonical、候选、
  manifest、M1 输入、M1 预登记与 WPS 只读收据 Hash。
- 机器门 `owc1-owc6` 覆盖候选身份、三张负向卡重放、55 页/54 原页面/113 未替换
  ZIP 部件、决策页 fail-closed、WPS 云盘副本和生产 canonical 边界。
- 新增命令行 `scripts/audit_m3_original_workbook.py` 与 3 项审计回归，纳入
  GitHub Core Research Gate；M3 原工作簿定向回归 7 passed。
- 候选保持 `candidate_verified_not_published`；`owc7` 为
  `PENDING_HUMAN_REVIEW`，Checkpoint B 仍必须由用户完成。
- 最新收据：`runtime/m3-original-workbook-audit-20260923T223129Z/receipt.json`，
  SHA-256
  `2242450c9f5ee76ce7dc9b4c9bc231448ea55d07d7efea06e99ab5a95ceae0c9`。
- 对应提交 `d6e4179488c11d4833f27fe2f0edde37f4651a46`；GitHub Core Research
  Gates run 35928696898 两个作业均为 `success`。

## M5 人工材料性判定接入：2026-09-24

本节记录把已有人工 `EventMaterialityDecision` 接入 M5 事件管道的离线工程。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作 `action=no_order`。

- 新增 `m5_materiality_bridge.py`：静默判定不产生事件；需重算判定生成高严重度事件
  并按事实、估值输入、模型有效性、估值结果和决策复核精确失效；需拆分只失效决策
  复核与当前状态，风险监控只进入决策复核。
- 未注册领域和制品保留为 `unmapped_domains` / `unmapped_artifacts`，不猜测；
  公告发布时间与人工复核时间分离，复核早于公告失败关闭。
- 扩展依赖失效和 run-once 编排，支持按源事件 ID 应用自定义直接依赖类型，并把策略
  纳入确定性摘要。
- 独立候选 6 页、6 项人工材料性判定、3 项静默、3 个事件、3 条失效记录和 3 条
  outbox 提醒，固定 `action=no_order`；字节数 13,240，SHA-256
  `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df`。
- 材料性桥接定向回归 39 passed；CI 离线清单 405 passed；除 PostgreSQL 集成外的
  全量离线回归 2252 passed、2 skipped、0 failed。
- GitHub Core Research Gates run 37：`offline-core` 与 `postgres-integration`
  均为 `success`。
- WPS 只读收据 `runtime/m5-materiality-wps-20260924/receipt.json` 为 `passed`；
  WPS 云盘同名副本与仓库候选逐字节一致。
- 真实公告采集、生产调度、通知投递、数据库变更、Entry/组合复核和故障恢复尚未建设；
  本批不证明 M5 生产验收。

## M5 事件基础设施离线合同：2026-09-24

本节记录 M5 第一批纯领域与 run-once 离线工程。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作
`action=no_order`，未创建生产调度、通知投递、常驻服务或数据库改动。

- 新增 `m5_event_core.py`：区分 `detected_at`、`effective_at`、`available_at`，
  重复事件幂等，更正/取代显式引用前序事件，晚到事件保留 PIT 顺序，
  未来事件与观察时间回退失败关闭。
- 新增 `m5_event_watermark.py`、`m5_event_checkpoint.py`：扫描水位单调前进；
  单 scope 任务锁带租约、token、续约与释放；检查点支持崩溃后幂等续接。
- 新增 `m5_event_outbox.py`：PENDING/SENT/DELIVERED/ACKNOWLEDGED/retryable/
  terminal 状态机，关键提醒去重，实际投递不在此层执行。
- 新增 `m5_event_dependencies.py`：按事件类型有界失效依赖；价格事件只影响价格桥接
  与当前状态，不把内在价值标记为需要重算。
- 新增 `m5_event_run.py`：run-once 编排固定为 取锁 -> 检查点 -> 入账 ->
  有界失效 -> outbox -> 提交 -> 释放；公开入口只接受 `SIMULATED`。
- 独立候选 6 页、7 个输入、6 个当前有效事件、6 条失效记录、6 条 outbox 提醒，
  固定 `action=no_order`；字节数 14,989，SHA-256
  `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae`。
- M5 定向回归 24 passed；WPS 只读收据为 `passed`，WPS 云盘同名副本与仓库候选
  逐字节一致。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2244 passed、2 skipped、
  18 warnings、0 failed。
- 真实公告采集、材料性判定、生产调度、通知目标和故障恢复尚未建设；本批不证明
  M5 产品验收。

## M4 分层仓位与股息收入投影：2026-09-24

本节记录 M4 的第二批非个人化领域工程与模拟 Excel 候选。M2 仍为
`PENDING_HUMAN_REVIEW`，M3、M4 仍为 `PARTIAL`；所有动作保持 `no_order`。

- 新增 `position_guidance.py`：人工确认的 Starter/Normal/Max 上限、共同预算、
  行业/周期限制、停止加仓和减仓复核条件；不输出目标仓位、仓位大小或订单。
- 新增 `dividend_income_projection.py`：已到账、已宣告、Forward、Normalized
  四种口径，普通/特别分红分开，未结算税费保持未知，特别分红不自动年化。
- 新增 `m4_guidance_income_workbook.py`、模拟 fixture、构建脚本与 WPS 校验脚本，
  并纳入 GitHub Core Research Gate。
- 独立候选 5 页、4 个仓位候选、4 个股息口径，固定 `action=no_order`；字节数
  11,504，SHA-256
  `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e`。
- M4 合同/风险/仓位/股息/工作簿联合定向回归 36 passed；WPS 只读收据为
  `passed`，WPS 云盘同名副本与仓库候选逐字节一致。
- 真实 IPS/持仓未提供；未修改原 55 页生产工作簿，也未生成个人化建议。

## M4 组合风险与集中度评估：2026-09-24

本节记录 M4 非个人化风险域与模拟 Excel 候选。M2 为 `PENDING_HUMAN_REVIEW`，
M3、M4 仍为 `PARTIAL`；本批只使用显式模拟组合，不读取真实账户、IPS 或持仓。

- 新增 `portfolio_risk.py`，建立 `SecurityRiskAttributes`、`RiskFinding` 和
  `PortfolioRiskAssessment`；单股/行业/周期暴露、现金储备、共同因子和流动性
  分别计算，缺失输入失败关闭。
- 实际评估只接受人工确认且已对账的 `ACTUAL` 快照；公开候选只接受
  `SIMULATED` 评估，真实私人数据不得进入公开仓库。
- 新增 `m4_portfolio_risk_workbook.py`、构建脚本、WPS 校验脚本和模拟 fixture，
  并纳入 GitHub Core Research Gate。
- 独立候选 4 页、3 个持仓、3 项风险发现，固定 `action=no_order`；字节数
  10,060，SHA-256
  `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7`。
- WPS 只读收据 `runtime/m4-portfolio-risk-wps-20260924/receipt.json` 为
  `passed`；WPS 云盘同名副本与仓库候选逐字节一致。
- 本批已以 `324694744b51a3f0c3f2316e1ce206ac6cad6cb2` 提交并推送；
  GitHub Core Research Gates run 35913005217 为 `success`。
- 真实组合风险报告、PositionGuidance 和 DividendIncomeProjection 尚未完成；
  本候选不是个人化风险结论。

## M2 AC1-AC12 完整本地回归复核：2026-09-24

- 在 `d6e4179488c11d4833f27fe2f0edde37f4651a46` 重新执行
  `scripts/audit_m2_acceptance.py --run-tests --ci-status success`，并显式核对
  WPS 生产工作簿；最新收据
  `runtime/m2-acceptance-audit-20260923T223550Z/receipt.json`，SHA-256
  `0342ddbedee1ab9906140e6c6be34742434b7e3c687630a311067a6791254ce4`。
- 全量离线回归 2284 passed、6 skipped、0 failed；AC1、AC2、AC3、AC4、AC5、
  AC6、AC7、AC11 为 `DONE`。
- AC8、AC9、AC10、AC12 保持 `PENDING_HUMAN_REVIEW`；整体状态由 `PARTIAL`
  转为 `PENDING_HUMAN_REVIEW`，下一步仍需用户在 WPS 中完成 Checkpoint A。
- GitHub Core Research Gates run 35928696898：`offline-core` 与
  `postgres-integration` 均为 `success`。

## M3 论点连续性历史链只读模型：2026-09-24

本节记录 M3 历史链的公开离线工程。M2、M3、M4 均仍为 `PARTIAL`；
本批只使用显式模拟数据，不读取真实账户、IPS、Entry 或持仓。

- 新增 `m3_history_read_model.py`，建立 `EntryThesisCard`、
  `DecisionJournalLine`、`ConsistencyReviewCard`、`DecisionHistoryChain`
  和 `DecisionHistoryCollection`。
- 公开链只接受 `simulated` 命名空间；Entry、Journal、Consistency 输入均绑定
  不可变 SHA-256，且日志顺序和更正前驱关系会显式校验。
- 新增 `m3_history_workbook.py`，生成 5 页独立候选：
  `00_历史链`、`01_原Entry`、`02_决策日志`、`03_一致性复核`、`04_来源哈希`。
- 新增 `scripts/build_m3_history_candidate.py` 与
  `tests/fixtures/m3_history_demo.json`；示例链路从模拟 Entry 到持有、削弱、
  破坏和减仓复核，固定 `action=no_order`。
- 新增 4 项回归测试并纳入 GitHub Core Research Gate。
- 独立候选字节数 12,121，SHA-256
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`；
  WPS 只读收据为 `passed`，WPS 云盘副本与本仓库候选逐字节一致。
- 本批未修改原 55 页生产工作簿；候选只演示结构，不等于真实历史链或 Checkpoint B
  已由用户签收。

## M4 组合输入合同：2026-09-24

本节记录 M4 的第一批非个人化输入合同。M2、M3 与 M4 均仍为 `PARTIAL`；
本轮没有读取真实账户，不计算仓位、风险或股息预测，也不生成任何订单。

- 新增 `portfolio_contracts.py`，建立 `InvestorPolicyStatement`、
  `PortfolioHolding`、`PortfolioSnapshot` 和 `PortfolioInputBundle`。
- 所有对象固定 `action=no_order`、`sensitivity=PRIVATE_USER_CONFIRMED`；
  缺失输入失败关闭，不补零值或默认 20% 仓位。
- IPS 人工确认门槛、持仓对账门槛和缺失字段均已显式化，见
  [m4-portfolio-input-contracts-20260924.md](m4-portfolio-input-contracts-20260924.md)。
- 新增 7 项回归测试并纳入 GitHub Core Research Gate。
- `PortfolioRiskAssessment` 已在本日后续批次实现；PositionGuidance、
  DividendIncomeProjection、私有持久化、真实账户导入和原 Excel M4 展示尚未完成。
- 本批未修改任何 Excel 字节，原 55 页生产工作簿和 M3 独立候选 Hash 均保持不变。

## M3 决策卡可重复验收审计与 M2 机器门复核：2026-09-24

本节记录当前 HEAD 的机器证据，不把人工验收改写成已完成。M2 与 M3 仍均为
`PARTIAL`，所有动作保持 `action=no_order`。

- 新增 `m3_decision_acceptance_audit.py`、
  `scripts/audit_m3_decision_acceptance.py` 和
  `tests/test_m3_decision_acceptance_audit.py`，并纳入 GitHub Core Research Gate。
- M3 审计器固定冻结输入、M1 预登记、候选工作簿、manifest、WPS 副本与 WPS
  只读收据；重建三张负向卡，验证 deterministic replay、逐卡来源 Hash 绑定和
  原 55 页生产工作簿未改变。
- 机器门 `m3c1-m3c6` 全部 `DONE`；`m3c7` 保持
  `PENDING_HUMAN_REVIEW`，等待用户阅读三张卡并复述理由与反证。
- 收据：`runtime/m3-decision-acceptance-audit-20260923T190024Z/receipt.json`，
  SHA-256 `2bb49e94df6740330d2713dee03eec1c44bb2be753f3afbbd40b1560797c8259`。
- M3 定向回归 29 passed；本次同时以全量离线回归复核 M2：AC1-AC7、AC11 为
  `DONE`，AC8/AC9/AC10/AC12 为 `PENDING_HUMAN_REVIEW`。全量
  2180 passed、6 skipped、18 warnings、0 failed。
- 提交：`41ac62cf77a1e01aaf123c0809ad4baf4bea2a84`；GitHub CI
  `Core Research Gates` 两 job 均为 `success`。
- 未修改原 55 页生产工作簿、未写入 `00_决策复核`、未连接生产 PostgreSQL、
  未触碰服务器 PTA/Web App，也未创建任何 BUY/ADD/仓位或订单。

## M3.2 Decision Card 只读模型与独立 Excel 候选：2026-09-24

本节记录 M3 决策域的第一批可查看离线工程。M2 与 M3 均仍为 `PARTIAL`；本轮未写入
原工作簿 `00_决策复核`，不生成个人化 BUY/ADD、Entry、Journal 或订单。

- 新增 `decision_read_model.py`：把不可变 `InvestmentDecisionReview` 重建成公开
  `DecisionCard`，固定 `requires_human_review=true`、`action=no_order`，并单独表达
  系统负向状态、个人组合缺失、原始 Entry 缺失和人工决策记录缺失。
- 新增 `m3_decision_application.py`：读取冻结 M1
  `runtime/m1-post-review-20260923T114228Z/integrated-runs.json`，对研究门、人工审批、
  估值、模型有效期、价格桥、价格吸引力和当前研究状态逐段做 canonical Hash 绑定，
  再用缺失组合前置和无决策意图构建失败关闭卡片。
- 三张真实卡片均为 `INSUFFICIENT_RESEARCH`，全部为 `no_order`、无决策意图、
  组合输入缺失、原始 Entry 本轮不需要；未产生任何正向复核。
- 新增独立候选
  `A股价值投资_M3决策卡候选_20260924.xlsx`（15,102 bytes，SHA-256
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`），已复制到
  WPS 云盘同名文件。WPS 只读验证通过：4 页、31 个证据链接、无公式错误、打开前后
  Hash 不变；收据 `runtime/m3-decision-card-wps-20260924/receipt.json`。
- 原 55 页生产工作簿未改变，canonical、M2 候选和 WPS 生产原表继续保持 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 测试事实：M3.2 定向 13 passed；Decision/PreDecision 联合 32 passed；
  Core Research Gates 等价离线清单 330 passed；全量离线回归
  2177 passed、6 skipped、18 warnings、0 failed。
- 下一步先由用户在 WPS 云盘查看三张负向决策卡；完成机器验证后，再受保护地把同一
  read model 并入原工作簿 `00_决策复核`，不能直接覆盖原 55 页。

## M3.1 共享决策域契约：2026-09-24

本节记录 M3 解释性决策域的第一批离线工程。M2 仍为 `PARTIAL`，M3 仍为 `PARTIAL`；
本批契约不是 M3 产品验收，也不生成个人化 BUY/ADD、仓位或订单。

- 新增 `src/value_investment_agent/investment_decision.py`，建立
  Evidence Bundle、Minimal Portfolio Preconditions、Decision Review、
  Entry Thesis Snapshot、Decision Journal 与 Consistency Review 的不可变合同。
- 在 research artifact 类型与 codec 中注册六个决策 artifact，支持哈希、版本和仓库
  追加式保存；新增仓库往返测试与 13 项定向回归。
- `evaluate_investment_decision()` 固定 `action=no_order` 与 `requires_human_review=True`；
  缺容量只返回 `WATCH`，正向复核不得绕过价格、置信度、反证和人工确认。
- 实际/模拟 Entry 必须价格，历史重建必须注明；Journal 只追加更正；Consistency 采用
  `BROKEN > NEGATIVE > all-FULFILLED > CONSISTENT` 的保守聚合。
- 测试事实：决策定向 13 passed；联合 codec 17 passed；CI 等价离线清单 317 passed；
  全量离线回归 2164 passed、6 skipped、18 warnings、0 failed。
- 本批未修改任何 Excel 字节，仓库 canonical、M2 候选与 WPS 生产原表继续保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 下一步仍按总Goal继续：Decision/理由卡 read model 与应用编排、版本化历史 replay 输入、
  原 Excel 展示；Checkpoint B 与 M2 的人工验收均不能由代码自行通过。

## M2 AC1-AC12 可重复验收审计器：2026-09-24

本节记录统一审计入口的代码与本地运行事实。M2 仍为 `PARTIAL`，`action=no_order`；
审计器不能替代用户在 WPS 中的实际研究、导航和证据链接复核。

- 新增 `config/m2-acceptance-audit-v1.json`、
  `src/value_investment_agent/m2_acceptance_audit.py`、
  `scripts/audit_m2_acceptance.py` 和
  `tests/test_m2_acceptance_audit.py`，并纳入 GitHub Core Research Gate。
- 审计器重算固定 M2 run、manifest、policy、两个 PIT 快照、AC8 报告、AC9 分层审计、
  工作簿发布收据和 WPS Hash；任何被固定文件的字节变化都会拒绝。
- AC1、AC6 依赖本地全量离线回归；AC8、AC9、AC10、AC12 的机器证据通过后仍为
  `PENDING_HUMAN_REVIEW`，不自动宣布 M2 完成。
- 本地定向回归 33 passed；仓库全量离线回归 2149 passed、6 skipped、18 warnings、
  0 failed。GitHub Actions 对本次新提交的成功结果将在 push 后单独核对。
- 当前 WPS 云盘生产工作簿、仓库 canonical 和 M2 候选工作簿逐字节一致，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 未连接生产 PostgreSQL、未触碰服务器 PTA/Web App、未修改计划任务，也未生成估值、
  BUY、ADD、仓位或订单。
- 详细版本记录见 [CHANGELOG.md](../CHANGELOG.md)；工作簿清单见
  [excel-artifact-version-record-20260924.md](excel-artifact-version-record-20260924.md)。

## M2 AC8 研究报告并入原 Excel 统一入口：2026-09-24

本节记录把 AC8 实质研究/否决报告并入 M2 原表候选、真实 WPS 校验和受保护发布的证据。
M2 仍为 `PARTIAL`，AC8 仍为 `AC8_REVIEW_PENDING`，AC10 为机器检查通过、用户可见审核
待完成；`action=no_order`。

- 代码新增研究页与证据页：`11_研究报告`、`12_研究证据`，并在 `00_M2总览` 加入内部
  导航；候选构造器、发布脚本和 WPS 校验脚本同步补齐，相关文件在本次 Git 版本中公开。
- 发布前原工作簿 SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。
- 新候选及发布后 WPS 原工作簿 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 55 个工作表：13 个 M2、6 个 M1 Application、36 个原工作簿页；42 个原有工作表被
  保留，96 个原始部分未变化。
- 研究报告 22 行、研究证据 245 行、228 个来源链接；AC8 报告 JSON Hash 保持
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- WPS 发布前与发布后只读收据均为 `passed`，实际引擎路径
  `D:\WPS Office\12.1.0.28505\office6`；只验证只读打开/计算、公式错误、工作表顺序和
  链接数量，不冒充人工逐链接或视觉点击验收。
- 受保护发布收据：
  `runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/publication.json`；
  同目录 `before.xlsx` 为回退原件。
- 定向回归 32 passed；最新全量离线回归 2144 passed、6 skipped、18 warnings、0 failed；
  `git diff --check` 通过。
- 未连接生产 PostgreSQL、未触碰服务器 PTA/Web App、未修改计划任务，也未生成估值、
  BUY、ADD、仓位或订单。
- 工作簿版本与 Hash 清单见
  [excel-artifact-version-record-20260924.md](excel-artifact-version-record-20260924.md)。

## M2 AC8 研究报告生成：2026-09-24

本节记录 AC8 的预注册报告工具与真实运行证据。M2 仍为 `PARTIAL`，AC8 单项目前为
`AC8_REVIEW_PENDING`，`action=no_order`。本段是上一阶段报告生成历史；“未生成新 Excel”
只描述当时状态，最新原表集成发布见上一节。

- 新增 `m2_research_report.py`、离线命令、固定输入配置与回归测试；只消费 AC9
  `selected_leads` 已封存样本，不按结果后验选公司。
- 真实报告：`runtime/m2-ac8-research-reports-20260924-v1/report.json`，SHA-256
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 总计 18 份报告，其中 16 份实质报告，覆盖股息、价值、周期三个通道；3 份待深研、
  13 份通道否决、2 份证据不足。证据不足不冒充实质结论。
- 本轮未连接生产 PostgreSQL、未触碰服务器项目或调度、未生成新 Excel，也未覆盖 WPS
  生产工作簿。
- 详细证据见 [m2-ac8-research-reports-20260924.md](m2-ac8-research-reports-20260924.md)。
  AC8 数量门已有机器证据，但仍需与 AC10/W6/W7 一起完成 M2 用户可见验收。

## 用户扩大总Goal至M7：2026-09-23

本节只改变后续执行范围，不改变下方代码审查事实或宣称新增功能。用户最新请求为“把这个目标调整到直接做到m7”。

- 唯一总Goal改为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`；当前聚焦仍是M2/PARTIAL。M1与Post-M1保持DONE，M3-M7未通过产品验收。
- 沿用M1-M6主轴，新增明确定义的M7“个人投资工作台交付与独立使用验收”；M6保留原20连续交易会话/真实事件/恢复等全部实质门，输出运营准入，M7最终用户签收后才标INITIAL_ASSISTED_USE。
- 阶段通过后记录证据、客观审查并在同一Goal继续，不再要求每阶段重建Goal；M4/M5仍仅在依赖成立后有界并行。
- 总范围不授权具体生产迁移、计划任务、通知、私人组合导入或代签G3/IPS/用户验收。这些对应输入和单独授权门保留。
- 本轮仅在上一轮未提交文档修改上增量调整AGENTS、LONG-TERM-GOAL、current-stage-goal、启动Prompt与本状态文件；未启动Goal、未改业务代码/Excel/数据库/服务器/调度，未commit/push。
- 下节“下一Goal只完成M2”的旧范围被本节替代；f4bb55c审查、2118 passed/6 skipped和M2反例仍为上一轮实测，本轮文档调整不冒称重新运行全量测试。

## M2 线索/已核候选边界与未发布原表候选：2026-09-23

本节记录工作树改动与真实候选产物。M2 仍为 `PARTIAL`，没有候选发布为生产工作簿。

- 领域合同：`CandidateReason.candidate_class` 只允许 `LEAD` 或 `VERIFIED_CANDIDATE`；
  当前 Quality/Dividend/Value/Cyclical 筛选输出全部显式标记为 `LEAD`，不能再把便宜筛选结果
  直接表述为已核实候选。`DiscoveryRunReceipt.verified_candidate_pool()` 当前真实运行返回空池。
- 工作簿：新增“研究层级”列和总览计数，明确显示“研究线索/已核候选”；候选签名包含
  `candidate_class`，`action=no_order` 保持不变。
- 原工作簿候选入口：新增 `scripts/build_m2_original_workbook_candidate.py`，要求原工作簿
  预期 SHA-256 与有效 M2 收据，复用受保护 graft，拒绝已有输出或源文件变化，并输出
  `status=candidate_verified_not_published`。脚本不执行 WPS 生产原子替换。
- 真实候选：源原工作簿 SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`；候选
  `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx` SHA-256
  `b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`。
  53 个工作表：前 11 个为 M2，后 42 个原工作簿页保留；`original_parts_unchanged=96`。
- 真实 5,568 家保留输入重放：Quality 0、Dividend 50、Value 50、Cyclical 50；
  `candidate_signature=a4f555b789c3942c690c1e288e5ce3bfa210544cd9ffcc63803d4c1eeb46f4c7`。
- 定向回归 19 passed，`git diff --check` 通过。未连接生产 PostgreSQL、未修改调度、
  未触碰服务器 PTA/Web App，也未替换 WPS 生产原工作簿。

## M2 时点合同与 PARTIAL 证据语义：2026-09-23

本节记录 W1/W2 共同合同加固后的代码、真实冷重放与候选产物。M2 仍为 `PARTIAL`。

- `DiscoveryRunReceipt` 增加向后兼容的 `quote_date`，并拒绝 `quote_date > as_of`、
  `universe.as_of > receipt.as_of` 和 `EvidenceReference.fetched_at > generated_at`。
  Universe 缺少抓取时点直接失败，不再回退到系统今天。
- 财务点只接受带时区且不晚于 `evaluation_at` 的记录；未来或未知时点不会进入
  `FinancialEvidence`。Dividend 证据保存原始输入的实际抓取时间。
- 非 Quality 便宜筛选通道缺少深研证据时全部标 `DATA_PARTIAL`，不再因价格无冲突
  标 `COMPLETE`；当前真实重放中 Dividend 优先级 B，Value/Cyclical 优先级 C。
- `--reuse-inputs` 现在必须读取既有 `receipt.json` 和全部保留输入，并继承原
  `generated_at/quote_date`；新运行 ID 为 `m2-replay-*`，清单记录 `replay_of_run_id`，
  不再把旧快照重标为今天。
- 真实冷重放：从 `runtime/m2-live-20260923-v2b/` 保留输入生成
  `runtime/m2-live-20260923-v3/`。原始时钟仍为 `2026-09-23T15:12:00.735987+00:00`，
  字节收据与原始输入重放均一致。覆盖签名保持
  `4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`；
  候选签名更新为
  `f77fd5f0e139cf0ab283e9aee9fdd2f4f66695071c85816f303c9b31715cbe79`。
- 更新原工作簿候选：SHA-256
  `95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`，
  后 42 个原页和 96 个原始部件不变；同步到 WPS 云盘独立预览，生产原工作簿未替换。
- 定向回归 24 passed；仓库全量离线回归 2131 passed / 6 skipped / 18 warnings / 0 failed；
  `git diff --check` 通过。未连接生产 PostgreSQL、未改调度、
  未触碰服务器 PTA/Web App。

## M2 AC9 分层覆盖审计：2026-09-23

本节记录预注册抽样工具、真实收据审计和抽样阅读结论。M2 仍为 `PARTIAL`；AC9 单项有真实证据，
不等于 M2 或总 Goal 完成。

- 新增 `config/m2-coverage-sampling-v1.json`，固定真实收据 SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`、
  run id、覆盖签名和候选签名，并声明 `action=no_order`。
- 抽样规则在结果观察前登记：`SHA256(seed | stratum_id | channel | symbol)` 稳定排序，
  8 个层每通道各抽 6 条；禁止收益、回测收益和阈值后验键。
- 真实审计输出：`runtime/m2-ac9-coverage-audit-20260923-v2/report.json`，SHA-256
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- 机器勾稽全部通过：每通道 5,568 与官方 Universe 对齐；PASS 与展示候选集合一致；
  150 个展示对象均为 `LEAD`/`DATA_PARTIAL`；已核候选为 0；证据日期与 legacy 记账一致。
- 分层人口：selected 150、REJECTED 7,564、DATA_GAP 6,829、UNSUPPORTED 469、
  BUDGET_EXCLUDED 2,255、NOT_EVALUATED 5,005、显式 excluded/missing 186、legacy 差异 774。
- 抽样阅读结论：Quality 0 的主要成因是财务证据只覆盖 873/5,568，不是全市场无质量公司；
  Value/Cyclical 低 PE 样本仍只作 PARTIAL 研究线索；预算外对象保留分母与原因，但触发指标需
  从原始输入重放才能完整复核；金融画像显式 `UNSUPPORTED`，未进入通用模型。
- 未阻断问题：Value 文案“多指标便宜度”实际输入为 PE、PB 与推导 ROE，下一版规则文本应更精确；
  本版不修改生产签名或历史收据。
- 新增 6 项定向回归并纳入 GitHub Core Gate；未连接生产 PostgreSQL、未改调度、未触碰服务器
  PTA/Web App、未覆盖 WPS 生产工作簿。完整报告见
  [m2-ac9-stratified-coverage-audit-20260923.md](m2-ac9-stratified-coverage-audit-20260923.md)。

## 路线融合复审：2026-09-23，代码基线 f4bb55c

本节是当前状态判断，优先于下方历史记录的“只差三报告”等当时结论。本轮仅审查与文档；未启动Goal、未改业务代码/Excel/数据库/计划任务，未SSH、未commit/push。

- Git：main，HEAD `f4bb55cd686838b874b6a8b0c601492c8bd7aab5`；提交时间21:55:48 +08:00；开始时工作树干净。本轮目标文档修改是未提交工作状态，不算新增已发布功能。
- GitHub本HEAD push run [35870537557](https://github.com/MingMingLiu0112/value-investment/actions/runs/35870537557)：offline-core、postgres-integration均success。CI指定37个离线测试文件及4项一次性PG集成，不是全仓/真实市场/生产可用性证明。
- 本机 `D:/APP/Python313/python.exe -X utf8 -m pytest -q --basetemp runtime/audit-roadmap-20260923-pytest-v2`：**2118 passed / 6 skipped / 18 warnings，290.45s，0 failures**。18条warning来自Backtrader utcnow弃用，不是投资逻辑报警。
- 用 `pytest -q -rs tests/test_postgres_research_artifacts.py tests/test_m1_postgres_cold_replay.py tests/test_moutai_end_to_end_case.py --basetemp runtime/audit-roadmap-20260923-skip-check` 复核：4项无C3_TEST_POSTGRES_DSN、1项无postgresql-binaries、1项已有冻结输出目录，另1 passed。本轮未重跑真实本机PG冷启动，CI一次性PG与历史冷启动收据分开。
- M1与Post-M1稳定化保持DONE；已存在HumanApproval/EventReview/Bridge stress/Interim/PreDecision合同，不重建。三家NOT_ELIGIBLE/STALE或REJECTED结论不提高。
- `runtime/m2-live-20260923/manifest.json` 八项文件Hash均一致，真实收据保留5568匹配、财务覆盖873证券、股息3622、四通道0/50/50/50及113去重候选。Hash一致不证明PIT与研究充分。
- 本轮内存合成反例：未来10月1日宣告仍可进入9月23日Dividend候选；从official删除600004后仍入选，健康仍COMPLETE且含extra blocker；600001入两通道而candidate_pool只保留value；改未来fetched_at/来源Hash后入口仍接受且candidate_signature不变。这些是合成入口缺口，不是实际股票异常。代码定位及修复验收在长期路线第1.4节。
- 源码复核：reuse-inputs重标now/quote_date风险、Dividend/Value/Cyclical以价格无冲突标COMPLETE、FCF/正常化指标仍None、行业存在即SUPPORTED、每通道50截断未保留完整覆盖账。应区分cheap leads与已核候选，不要求全市场DCF。
- 原Excel当前Hash `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，12,210,200 bytes；M2仍在独立工作簿。本轮未做WPS视觉验收，统一原工作台纳入下一Goal受保护发布。
- 本轮调整：LONG-TERM-GOAL更新真实基线/成熟度及M2-M6 DAG；current-stage-goal替换“只差三报告”为W0-W7/AC1-AC12；同步AGENTS、架构、方法/证据政策和启动入口。没有建立第二份Roadmap。
- 当前成熟度：L0 HEALTHY，L1 BASICALLY READY，L2 PARTIAL，L3-L5与INITIAL_ASSISTED_USE均NOT READY。下一唯一Goal完成可信M2，CheckPoint A只帮助研究谁/为什么，不给买卖仓位、不声称每日运营。

## POST-M1 Stabilization + M2 首个真实 run-once：2026-09-23

执行输入是用户复核后的 [m2-current-progress-review-20260923.md](m2-current-progress-review-20260923.md)。
`POST-M1-STABILIZATION` 的 A1-A5 已完成并冻结，当前活动阶段为
`M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`。M1 保持 `DONE`，不重写历史。

- A1：修正茅台旧审计断言，从 P1 v4 契约自带的 hash-bound daily-simulation policy 推导执行政策事实，不删除红测试。
- A2：`build_m1_post_review_receipts.py` 标记为 `ONE_OFF_REVIEW_RECEIPT_GENERATOR`，并增加生产路径防误用测试。
- A3：临时桥接 haircut 增加 `stress_test_only / not_valuation_input / not_price_assessment_input`，域对象可序列化和 round-trip。
- A4：旧十样本估值画像、固定 Universe seed 与 PE/PB screen 明确标记为 legacy；M2 不得复用为候选排序。
- A5：`current-stage-goal.md` 已切换到 M2；本执行手册复制入 `docs/`。
- 稳定化验收：定向回归 14 passed；使用仓库内隔离 basetemp 的全量回归 2112 passed / 6 skipped；`compileall` 与 `git diff --check` 通过；Core 生产路径未新增 `000651 / 600741 / 600887` symbol 特例。

## M2 真实全市场 run-once 结果：2026-09-23

命令 `scripts/run_m2_opportunity_discovery.py` 已完成一次真实运行，
产物目录 `runtime/m2-live-20260923/`。状态为 `PARTIAL`，尚未声明 M2 完成。

- 官方 Universe 5,568 家；腾讯与新浪行情均匹配 5,568 家，缺报/多余/价格冲突均为 0。
- 行业映射 5,568 家；财务证据 873 条；股息证据 3,622 条；金融行业不支持隔离 121 家。
- 四个通道均真实执行：Quality 0、Dividend 50、Value 50、Cyclical 50，合并去重候选 113 家。
- 每份候选保留进入原因、证据日期、`data_status`、`profile_status` 与缺失指标；缺失保留 `None`，不默认为 0。
- Legacy `PE<=25 / PB<=3 / 市值>=50亿` 仅作 shadow：747 家，与新候选重叠 86 家，不参与新候选排序。
- 收据 `action=no_order`；从收据字节和保留原始输入重建的候选签名均一致，`receipt_bytes_match=true`、`raw_inputs_match=true`。
- 独立候选工作簿 `A股价值投资_M2机会发现_20260923.xlsx` 已写入 WPS 云盘“价投跟踪”目录，未覆盖原工作簿；两处 SHA-256 均为 `a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`。
- Quality 为空是证据门禁的失败关闭结果：本轮财务点来自 2026-09-18 前后服务端导出，未达到“验证状态、自动双源交叉核验、完整债务口径、同一报告期年度数据”的门禁，因此未降低阈值强行放行候选。
- 当时曾判断旧验收第1-6、8-10项已有证据、仅差三份报告。**本判断已被顶部f4bb55c复审纠正**：现有收据证明运行/字节重建，不足以证明时点、覆盖、候选质量与统一前台。当前执行范围仅见current-stage-goal，仍禁止symbol专用流水线。
- 本轮 M2 定向回归 6 passed；仓库内隔离 basetemp 全量回归 2118 passed / 6 skipped；未连接生产 PostgreSQL、未改计划任务、未触碰服务器 PTA/Web App 或原 WPS 人工工作簿。

## M1 收口：2026-09-23

- `M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 已达到 `DONE`；AC1-AC10 均由本地产物、隔离 PostgreSQL、WPS 发布收据和定向回归支持，最新审计状态为 `PASSED`、`action=no_order`。收据 `runtime/m1-acceptance-audit-20260923T091447Z/receipt.json`，SHA-256 `f7c71e507585d7660cc9f66320617738525a32abf141f2296ce46ee9ae90d16a`。
- AC4/AC6/AC10 不再被 G3 或事件材料性人工状态阻断。三家公司 G3 研究批准保留到 M3，模型前公告材料性复核保留到 M5，Excel 视觉确认保留到 M6；审计器只登记 `deferred_human_review`，不自动批准。
- 三家正常化股息情景仍 `NOT_READY`、全部估值仍 `conditional_research_only`、价格吸引力仍 `NOT_ASSESSABLE`。M1 完成只表示研究工作台闭环，不表示真实投资或交易准入。
- 未启动 M2，未连接生产 PostgreSQL、未 SSH、未改 PTA 或计划任务。

## M1 后人工复核纠偏与 M3/M5 决策门：2026-09-23

执行输入是用户复核后的 [m1-post-review-decision-gate-20260923.md](m1-post-review-decision-gate-20260923.md)，基线为 `cbec189 Close M1 workbench and defer decision-stage reviews`。M1 仍保持 `DONE`，冻结估值包、历史收据和原 WPS Excel 未修改。

- 新增五个 append-only 领域契约：`human_research_approval.py`、`event_materiality.py`、`valuation_bridge_review.py`、`interim_report_policy.py`、`pre_decision_eligibility.py`；Application、G3、ModelValidity、PriceBridge 和 CurrentStatus 已接入新门禁。
- 三家公司正式人工 G3 回执：`000651=REJECTED_NEEDS_REWORK`、`600741=REJECTED_NEEDS_REWORK + HIGH`、`600887=APPROVED_CONDITIONAL_LOW_CONFIDENCE`。回执绑定估值、ResearchCase、Facts、Assumptions 的 SHA-256，依赖变化会变为 `SUPERSEDED`。
- 24 条公告全部形成 EventMaterialityReview。分类为 2 `MATERIAL_REQUIRES_RECALCULATION`、4 `MATERIAL_RISK_MONITOR`、4 `MATERIAL_ALREADY_INCORPORATED`、5 `DUPLICATE_OR_DERIVED`、7 `NOT_MATERIAL`、1 `MATERIAL_SUPPORTING_EVIDENCE`、1 `REQUIRES_DECOMPOSITION`。格力和华域未解决资金桥接拆分保持 `UNRESOLVED`；伊利成本权益、留存/分红和减值归一化 ROE 仍为 `CONDITIONAL_REVIEW_PENDING`。
- 未经审计半年报默认改为 `CONFIDENCE_MODIFIER`，保留 `previous_classification=HARD_BLOCKER` 和版本链；已核实来源存在冲突、更正、范围不匹配或审计问题时才继续升级 blocker。
- 无有效人工 G3 时 Application 的价格吸引力强制为 `NOT_ASSESSABLE`。PreDecision Eligibility 要求 G0-G3、有效 Approval、当前 Event Review、`VALID`、`READY` 和可评估价格政策同时成立。
- 正式 runtime 收据目录 `runtime/m1-post-review-20260923T114228Z/`，manifest 覆盖 9 个文件 Hash；三家 integrated runs 均为 `action=no_order`，分别保持 `REJECTED/STALE`、`REJECTED/VALID`、`CONDITIONAL_APPROVED/STALE`，均 `NOT_ELIGIBLE`。
- 定向回归 `71 passed`；全量本地回归 `2107 passed, 6 skipped, 1 failed`，唯一失败仍是本文已记录的茅台旧 `daily_simulation_policy_implemented` runtime 指针断言，不在本轮改动路径内。GitHub Core Gate 已加入五个新契约测试文件。
- 未修改 M1 冻结 Hash、生产 PostgreSQL、计划任务、服务器 PTA/Web App 或原 WPS Excel。

## 用户指定的前端调整：2026-09-23 已更新原 Excel

独立于并行 M1 研究任务，本次只调整使用界面，不提升研究或交易准入状态。
原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 已备份并原子更新，新增工作台、研究看板、研究逻辑卡、决策复核、组合与股息、跟踪与数据六页。原30页的worksheet XML逐字节未变，持仓/交易/历史记录保留。

- 本次前台连接3家封存研究样本，含1家条件三情景及2家估值未就绪；不是正式重点关注池，不是今日行情，不是买卖建议。
- 下文 M1 W3 的6份新档案仍在独立候选中，未接入本前台；不能因本次原表发布而宣称M1的研究产品闭环通过。
- 新看板含原生筛选表、冻结导航、内部链接；未来决策、组合和监控区明确“未接入”，未知不填0。
- Excel相关回归：`19 passed`；64个内部链接目标、4个公式缓存和30张原表完整性校验通过；WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 只读打开/计算校验通过。桌面鼠标逐链接点击不在该收据范围内。
- 发布收据：`runtime/workbook-backups/stage-frontend-b65249ffe1874ca1859827665a4a001f/publication.json`；同目录 `before.xlsx` 为回退原件。新文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 保留六页的发布入口修改已在本地测试，未提交/推送；未部署服务器、未改定时任务。现有刷新只保留新页，不自动刷新这些封存快照。
- 构建运行时的退出异常与后续接入约束记录于 [excel-stage-frontend.md](excel-stage-frontend.md)，不把导出文件成功冒充无人值守发布已经可靠。

## M1 当前增量：2026-09-23 格力历史双源收盘价、PIT replay 与新 Application 候选

本节记录当时实际生成的新收据；该时间点的“未完成”只描述当时状态，最终 M1 收口见本文件顶部。

- 格力 `000651` 注入真实历史双源收盘价：腾讯与搜狐均 `38.18`，SZSE 交易日历为 `2026-09-22`；Application 桥接从 `PENDING_EXTERNAL_DATA` 变为 `READY`，当前数据为 `READY`。格力 FY2024 末期与 FY2025 中期派息实施原件也已补齐，见下方“格力股息生命周期”节。
- 三公司最新 Application：`000651 / 600741 / 600887` 全部 `COMPLETED_WITH_BLOCKERS`、`action=no_order`；三家报价桥接均为 `READY`，价格吸引力保持 `NOT_ASSESSABLE`。G3 与事件材料性后来按里程碑边界延后，不作为 M1 阻断。
- 隔离 PostgreSQL 冷启动已用更新后的格力数据包重跑：PostgreSQL 18.6，首轮写入 30 个制品，冷重启后 30/30 验证通过，`semantic_equality=true`。最新收据 `runtime/m1-postgres-cold-replay-20260923T060159Z/receipt.json`，SHA-256 `bd643fc080c82d2c174948067918488ae8c38aee2f6a615d763d7bc9ed9286e8`。
- 新披露 PIT replay：`m1_pit_replay.py` 对格力、华域、伊利三家真实官方 PDF 重放报告期披露可用边界；每家 2 份官方财报、4 个决策边界、3 个未来披露排除点，只按 `published_at` 选择，不用 `retrieved_at` 推断历史可用。收据 `runtime/m1-pit-source-replay-20260923T042556Z/evidence.json`，SHA-256 `f9a19f4da5d06ace7cb5b681e910925f45137f3c17df9e600be0f782ae34bf7f`。
- 原五粮液真实财报更正 replay 继续作为 AC7 的更正反例：`runtime/company-research/000858-revision-replay-20260909T131721971494Z/evidence.json`。
- 新 Application Excel 候选：6 个工作表顺序、WPS 只读打开、公式重算与哈希不变检查通过；候选 SHA-256 `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`。
- 已复制到 WPS 云盘 `M1_三公司研究Application候选_20260923_122010.xlsx`；复制前后哈希一致。原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 未覆盖，AC9 的受保护原表发布仍未完成。

## M1 原 Excel 整合发布：2026-09-23

上一段最后一项已推进为受保护的原表整合发布。这里只是把三公司 Application 六页追加到原 WPS 工作簿，不是 M1 完成，也不是交易建议。

- 修复 `scripts/stage_frontend_package.py` 的关系 ID 冲突：原表与新增 M1 页面都使用过 `stageFrontend1..6`，会导致 WPS 把前六页错误绑定到旧 parts；现在新增页使用独立 `m1Application1..6`，并对每个 `.rels` 做重复 ID、悬空目标和前六页 part 映射 fail-closed 校验。
- 早先 `runtime/m1-integrated-workbook-20260923T043200Z/` 中带重复关系 ID 的候选已判定为结构无效，从未发布；不要把它当作可用 Excel 产物。
- 新候选为 42 个工作表：前 6 个是 M1 Application 页面，原 36 个 worksheet XML 逐字节未变、顺序保留；首屏标题为 `M1 三公司研究 Application 候选`，状态为 `完成，有阻断`，全程 `action=no_order`。
- 集成候选 SHA-256：`36fd26812f84dd0b9931725ebeec93cf5311c17f408974714c434ab5a22970ac`；发布前源文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 发布前 WPS 收据：`runtime/m1-integrated-workbook-20260923T044629Z/wps-integrated-receipt.json`；发布后再次只读打开验证：`runtime/m1-integrated-workbook-20260923T044629Z/wps-published-receipt.json`，42 页、标题/状态、哈希不变检查均通过。
- 发布收据：`runtime/workbook-backups/stage-frontend-3c253a9761bb44489872ce7268e9a933/publication.json`；同目录 `before.xlsx` 为可回退原件。
- 防回归测试：`tests/test_stage_frontend_package.py` `3 passed`，覆盖关系 ID 唯一性、原关系目标保留和重复 ID fail-closed。
- M1 仍未完成：G3 人工估值审批、股息实质评估、更完整的跨模型情景与剩余真实缺口均未结束；发布页明确显示 `完成，有阻断`，没有生成价格吸引力或买入结论。

## M1 事件扫描合同与真实 CNINFO 封存：2026-09-23

上一版把中报原文当作事件扫描证据是不成立的。本轮新增显式 `EventScanResult` 合同，并把三家估值包改绑到真实 CNINFO 公告窗口证据，避免“任意非空引用 = 已完成且无重大事件”。

- 新增 `src/value_investment_agent/event_scan.py`：分别保存扫描窗口、模型有效性窗口、覆盖完整性、公告级规则分类、模型前候选复核状态、阻断和证据引用；扫描窗口必须覆盖报价日，`PENDING_HUMAN_REVIEW` 与不完整覆盖不能生成 `VALID`。
- `scripts/collect_m1_event_scan.py` 从 CNINFO 归档三家 `2026-08-27 ~ 2026-09-22` 共 40 份公告：格力 8、华域 13、伊利 19；每家保留索引 JSON 和全部 PDF，逐份 SHA-256 已校验。收据目录 `runtime/company-research/m1-event-scans/20260923T051018Z/`。
- 三家桥接窗口 `2026-09-22` 均无公告，`ModelValidity` 仍为 `VALID`、`PriceBridge` 仍为 `READY`；但模型构建前分别有 7、4、13 份规则候选标为 `PENDING_HUMAN_REVIEW`，阻断已进入 Application 与 `价格桥` 展示，不冒充全周期事件复核完成。
- 三个估值包的 `model_validity_input.event_scan_ref` 已绑定证据文件 SHA-256，`scan_watermark` 改为 `m1-cninfo-event-scan-v1:<hash16>`；旧 `events=[] + 中报引用` 不再作为新路径的事实来源。
- 新 Application 收据：`runtime/m1-research-application-20260923T051116Z/evidence.json`。新集成候选与原表发布 Hash 均为 `4678b4aa3074f7d4e7c31134a2560326fdcd45f0fb1e367b2bb1c9c971ed0ed7`；原 36 页 XML 逐字节未变。
- 发布前 WPS 收据：`runtime/m1-integrated-event-scan-20260923T051301Z/wps-receipt.json`；发布后再次只读验证：同目录 `wps-published-receipt.json`。发布备份：`runtime/workbook-backups/stage-frontend-1688b2b905714859bc90ca57d9ed7a8c/`。
- M1 仍未完成：事件扫描现在是可审计证据，但模型前披露尚未人工完成材料性复核，G3、股息实质评估和更完整跨模型情景仍未结束。

## M1 AC5 股息生命周期证据与 Excel 发布：2026-09-23

上一版的三家股息包只有不完整除息台账和空收益率快照。本轮为伊利、华域建立真实法定生命周期证据，并把 AC5 的层次直接放进原 Excel 的 `02_股利评估`，而不是只停留在配置 JSON。

- 新增 `scripts/collect_m1_dividend_lifecycle.py`。证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T052056Z/` 共封存 11 份官方 CNINFO PDF：伊利 8 份、华域 3 份；每份保留原 PDF、PDFium 文本提取、来源 URL、发布时间、解析器版本和 SHA-256。清单文件 SHA-256：`974cbf76a327014131e702269aec7279ce9b2398319ee4909f23540c3cdfc89c`。
- 伊利 `600887`：FY2024 末期普通股利 `1.22`，提议 `2025-04-30`、批准 `2025-05-20`、除息/支付 `2025-06-06`；FY2025 中期普通股利 `0.48`，除息/支付 `2025-12-17`；FY2025 末期 `0.90` 仍为 proposal；2025-2027 股东回报计划明确登记为 policy，不是预测；未识别特别股利，未宣称前瞻 payout forecast。
- 华域 `600741`：FY2024 末期普通股利 `0.80`，提议 `2025-04-29`、批准 `2025-06-27`、除息/支付 `2025-07-25`；FY2025 末期 `1.00` 仍为 proposal；长期政策背景为 2009 上市以来每年现金分红，2009-2023 累计 `30.830 billion`；未识别特别股利，未宣称前瞻 payout forecast。
- 两个 package 版本升级为 `20260923.2`：`600887-quality-compounder.json` 有 3 条历史记录、2 个 `READY` 快照和 1 个显式 `NOT_READY` 正常化情景；`600741-mature-manufacturing.json` 有 2 条历史记录、1 个 `READY` 已宣告快照和 2 个 `NOT_READY` 快照。可持续性均为 `LOW`，保留可分配现金、现金流、资本强度和周期敏感等真实阻断。
- `src/value_investment_agent/m1_application_workbook.py` 的股利页扩展为三张连续证据表：可持续性摘要、法定生命周期台账、当前/正常化收益率快照。普通/特别、事实/政策/预测、paid/proposed、current/normalized 均可直接在 Excel 复核；`NOT_READY` 不改成已知。
- 防回归测试 `tests/test_m1_application_workbook.py` 锁定 `02_股利评估` 必须展示生命周期、当前/正常化、特别股利与事实/政策/预测分层。本轮相关聚焦回归：`80 passed, 1 skipped`。
- 新 Application 证据：`runtime/m1-research-application-20260923T053028Z/evidence.json`，SHA-256 `4933cf172f8ba784921ad6146948bd3570a8bf26e56c0cba9026829f92e4b113`。
- 受保护整合发布：42 页，前 6 页为 M1 Application，原 36 页 worksheet XML 逐字节未变；候选及发布 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea`。发布前收据 `runtime/m1-integrated-dividend-20260923T053128Z/wps-integrated-receipt.json`，发布后 WPS 只读收据同目录 `wps-published-receipt.json`，回退原件 `runtime/workbook-backups/stage-frontend-ffa20fa0a1d34a8ab3b41c5cc95759d3/before.xlsx`。
- AC5 已从“PARTIAL 占位”推进为两家有证据的 `LOW` 可持续性结论；但正常化情景仍 `NOT_READY`，格力 `000651` 的 paid 除息/支付台账仍未补全。因此 M1 不因本段完成。

## 当前摘要：M1 W3 已形成 6 份 READABLE 研究档案，估值与产品闭环尚未完成

2026-09-23 已完成 M1 W1 样本与方法预登记、W2 的工程边界，并推进 W3 真实研究档案。当前结果是 `M1 IN_PROGRESS`：已形成 6 份绑定官方原件、反证和下一事件的可阅读研究档案。`READABLE` 仅表示研究已完整呈现且未知项显式可见，不等于估值完成、股息通过、价格合理或可交易。

| 核查项 | 当前事实 |
| --- | --- |
| 新合同 | `research_run_contract.py`、`research_input.py`；版本化 descriptor 为 `m1-fixed-sample-input-v1` |
| PIT 边界 | 分别保存 report/research/valuation/available/computed；拒绝日期掩盖、未来可用时间、未来报告期、来源在可用边界后发布/抓取；三家真实披露边界 replay 已生成 |
| 假设绑定 | 登记 assumption 必须命中实际 `facts.scenario_inputs`；不一致记为 blocker，不生成订单 |
| G3 边界 | `ResearchValuationApproval` 绑定模型、版本、估值日期和结果 SHA-256；旧 `case.valuation_status` 不再自动通过 G3 |
| 依赖失效 | batch 同时比较输入 SHA-256 与 dependency SHA-256；model/parser/scan/profile/requested-model/rule 变化会重跑或隔离失败 |
| 坏输入隔离 | 坏 descriptor、未知 Profile、未来 availability 只进入 `input_failures`，不终止同批其他公司 |
| W1 样本登记 | 20 家分层预登记账在 `config/m1-fixed-sample-preregistration-v1.json`，覆盖原3家、3画像、同画像第二家、不支持、资料不足和风险反例 |
| W1 方法与停止规则 | 来源、字段、深度、预算、20家上限、3次证据尝试后暂停、不伪造 READY、`action=no_order` |
| W3 共享建造器 | `m1_provider_dossier.py` 统一 schema、必需维度、证据 ID 引用、原文件 SHA-256 与 latest pointer 发布 |
| W3 六家证据档案 | 格力 `000651`、五粮液 `000858`、兖矿 `600188`、伊利 `600887`、海尔 `600690`、华域 `600741`；均绑定官方 PDF、来源 URL、发布时间、报告期与 SHA-256 |
| READABLE 语义 | complete 研究章节允许保留显式 `UNKNOWN` 维度；`MISSING/NOT_STARTED/BLOCKED/PARTIAL` 仍阻止可读性；READABLE 不等于估值完成或交易就绪 |
| W3 报告状态 | 20 家：`READABLE=6`、`PARTIAL=0`、`BLOCKED=3`、`NOT_STARTED=11`；全部保持 `action=no_order` |
| 聚焦测试 | 本轮 M1/Research Application/股息/报价相关回归 `80 passed, 1 skipped`；股息页新增 AC5 分层防回归测试 |
| 全量离线套件 | 历史结果为 `2054 passed`、`6 skipped`、`1 failed`；本轮在首个旧失败处停止，失败仍为 `test_moutai_current_valuation_admission.py` 的 `daily_simulation_policy_implemented=false`，与本次 M1 股息文件无依赖 |
| 本地产物 | `runtime/m1-research-dossier-candidate-latest.json`、`m1-research-application-latest.json`、`m1-pit-source-replay-latest.json`、PostgreSQL replay 收据与 Application Excel 候选；原 WPS 工作簿已受保护发布为 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea` |
| 安全边界 | 未连接生产 PostgreSQL/服务器/PTA，未改 WPS 原表，未生成订单或仓位 |

六家 `READABLE` 档案的维度会显式保留 `UNKNOWN`，研究缺口继续显示未审计、ROIC、正常化利润、法人层级现金和模型输入等问题。W3 仍要继续补齐跨模型情景估值、股息可持续性、报价/事件桥接、隔离 PostgreSQL 冷启动 replay 与原 Excel 安全发布；没有这些验收，不能宣称 M1 完成或初步投资就绪。

## M1 格力股息生命周期与 AC 事实矩阵：2026-09-23

本节补齐 AC5 第三家、用更新后输入包重跑 AC8，并把 AC1-AC10 固化为可核对的事实矩阵。所有状态仍是 `action=no_order`。

- 格力 `000651` 新增两份官方派息实施原件：FY2024 末期 CNINFO `1224534765.PDF`、FY2025 中期 CNINFO `1224936369.PDF`。分布包升级为 `package_version=20260923.2`。
- 格力生命周期现在为：FY2024 末期普通股利 `2.00` 已支付，批准日 `2025-06-30`、除息/发放日 `2025-08-29`；FY2025 中期普通股利 `1.00` 已支付，批准日 `2025-11-24`、除息/发放日 `2026-01-23`；FY2025 末期 `2.00` 仍为提议，未批准。无特别股利，无前瞻支付预测。
- 股息快照：trailing paid `3.00 / 38.18 = 0.07857517...` 为 `READY`；声明提议 `2.00 / 38.18 = 0.05238345...` 为 `READY`；正常化情景仍 `NOT_READY`。
- 格力可持续性结论为 `LOW`，不是“可维持”或投资依据；财务公司、受限现金、金融资产与法人层级可分配现金仍未拆通。
- 证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T055500Z/`；清单 SHA-256 `41f2114f7261370984e0219a8ec13aba658ff6f7b32af2b97c2ae7430b97c965`。两份新 PDF SHA-256 分别为 `8d4b488560f9d3ec81c9349757cda9d9bdee4cdbbecb97911761e2f6a93b4b64` 与 `89ab10370d6601c698426eb6a37dba664687ca03ee59a46208e104068d62d3dd`。
- 更新后的三公司 Application 与 42 页集成工作簿再次发布：原 36 页 XML 逐字节保留；发布后 WPS 工作簿 SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。候选、备份与发布前/后 WPS 收据均在 `runtime/m1-integrated-dividend-20260923T055026Z/`。
- AC1-AC10 正式状态与证据见 [m1-acceptance-fact-matrix-20260923.md](m1-acceptance-fact-matrix-20260923.md)。最终：AC1-AC10 `DONE`；G3 研究批准延后到 M3，事件材料性复核延后到 M5，Excel 视觉确认延后到 M6。
- 后续里程碑才需要逐项完成的 G3 估值审批、CNINFO 事件重要性阅读和 Excel 可用性检查见 [m1-human-review-checklist-20260923.md](m1-human-review-checklist-20260923.md)。六份档案的机器可读深度已抽查，人工质量复核可保留，但不阻塞 M1。
- 收束后聚焦回归 `82 passed`；`compileall` 与 `git diff --check` 通过。当前 WPS 工作簿 SHA-256 仍为 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，未再改动。
- 新增可重复执行的本地验收审计器 `scripts/audit_m1_acceptance.py`：只读核对 dossier、输入/估值/股息包、PIT replay、PostgreSQL 冷回放与 WPS 发布收据，并可选重跑 AC1/AC2 回归。审计器 schema v2 区分 M1 机器验收与 M3/M5/M6 后续人工复核；最新运行收据见“机器复算入口”节。
- 新增 `scripts/render_m1_human_review_packet.py`，从冻结 Application/事件扫描包生成 [m1-human-review-packet-20260923.md](m1-human-review-packet-20260923.md)：当前 24 条待人工阅读公告均给出本地原件、CNINFO 原件和 SHA-256 前段，另有三家公司 G3 决策表。生成器只读，`action=no_order`。
- 当前脏工作树按 GitHub offline-core 同款 30 个测试文件重放：`226 passed`。Windows 默认 pytest 临时目录因权限拒绝导致 4 个 setup error；改用项目内临时目录后全部通过，未修改系统目录权限，未把环境错误写成代码失败。

M1 已在上述口径下完成。`VALID` 或 `READY` 仍不能写成价格吸引力或交易准入；条件研究、正常化股息缺口和后续人工复核状态全部保留。

## M1 Application 与三公司候选展示：2026-09-23

本轮没有把 M1 标为完成。当前三家公司均保持 `action=no_order`，输出状态均为 `COMPLETED_WITH_BLOCKERS`。伊利事实层的三条重复门禁已拆开：前瞻 ROE 保持为登记的低置信度假设，ROIC 缺口保留在研究反证/人工批准项，beta 缺失移到 `cost_of_equity` 假设；伊利因此得到 `conditional_research_only` 的 Bear/Base/Bull 与 `READY` 价格桥，但仍没有人工 G3 批准，不能形成价格吸引力或交易结论。华域股利能力说明改为“提议分配，尚未批准/支付”，不再把未经审计的中报语境误写成分母。

- 新增三公司版本化股利包、共享加载器、有界反向估值与批量 Application runner；新候选展示层只读取已有 Application/股利/反向估值结果，不在 Excel 重算。
- 本地产物：`runtime/m1-research-application-latest.json`、`runtime/m1-research-application-workbook-20260923T033001Z/m1-research-application-candidate.xlsx` 及 manifest/WPS 只读收据。
- WPS 云盘只新增独立候选副本 `M1_三公司研究Application候选_20260923_033001.xlsx`，未修改原工作簿。
- WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 以只读方式打开、重算、扫描公式错误后哈希不变：`status=passed`。

## M1 隔离 PostgreSQL 冷启动 Replay：2026-09-23

本地没有启动 Docker Desktop、常驻服务、生产 PostgreSQL、SSH 或 PTA。本轮使用项目内忽略的 `.m1-postgres-venv` 中 `postgresql-binaries==18.6.0`，在 `127.0.0.1` 随机端口创建一次性 PostgreSQL 18.6 集群，从三份真实 M1 valuation/distribution 配置完整执行共享 Application，停库后从同一数据目录冷启动并逐条恢复验证。

- 新增 `src/value_investment_agent/m1_postgres_cold_replay.py` 与 `scripts/run_m1_postgres_cold_replay.py`；只允许 loopback 地址，不接收外部 DSN。
- 首次运行写入 28 个 typed research artifacts、28 个 head、87 条 reference；三家输出均为 `COMPLETED_WITH_BLOCKERS`、`action` 为 `null` 或 `no_order`，无订单或仓位字段。
- 冷启动后 28/28 artifact 通过 SHA-256 与 canonical payload 语义相等校验；首轮和冷启动 artifact fingerprint 均为 `5635429903544517fccb41826a62c1986a3ae855771d49c4cc3c79e248568a8f`。
- 真实验收收据：`runtime/m1-postgres-cold-replay-20260923T040611Z/receipt.json`；收据 SHA-256 `8ec0f2bfbd18e16f8dc7d0ac647c8cbb6df76443945ef59104b2510d0f16f4f8`，状态 `PASSED`。
- 隔离环境定向测试：`2 passed`；普通离线环境无本地二进制时按设计 skip，不把本机真实验收与 CI synthetic fixture 混为一谈。

## M1 启动前审查基线（2026-09-22）

本轮任务是系统审查与长期目标收敛，只修改文档，没有实施 M1、修改业务代码、Excel、数据库、生产任务或服务器。新增 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md) 规划六个大 Milestones；唯一待启动长期目标为 M1-FIXED-SAMPLE-RESEARCH-WORKBENCH。原独立 C4 adapter 建议被吸收为 M1 输入完整性工作包，不再单独作为产品目标。

以下是本轮重新观察的状态；后面 C0-C3 的测试数、Hash、旧缺口和“下一任务”属于各阶段历史，不覆盖本摘要。

| 核查项 | 本轮事实 |
| --- | --- |
| 开始 Git HEAD | `494d0857c7edb4b76b0527d773065013b7abf2d1`，2026-09-22 20:33:40 +08:00，C3.14 close governance and record green CI receipt |
| 本地/远端 | GitHub main 同一 SHA；开始工作树干净；本轮文档为新增未提交工作，未推送 |
| 当前 HEAD CI | [35727941981](https://github.com/MingMingLiu0112/value-investment/actions/runs/35727941981) 两项 offline-core/postgres-integration 均 success；不是只引用前一提交绿色收据 |
| 本机 CI 同款文件清单 | Python 3.13，`pytest -q -p no:cacheprovider`；173 passed、4 skipped，2.48s；4项因未配置 `C3_TEST_POSTGRES_DSN` 跳过，未连接生产 |
| 冻结历史验收 | `test_moutai_valuation_export.py` + `test_three_company_unified_acceptance.py`：9 passed，0.77s |
| 真实 runtime replay | 调用 `run_three_company_replay` + InMemory Repository：all_semantics_matched=true、no_order；未生成新runtime收据/改latest |
| 三公司 | 茅台conditional/低置信度、VALID/READY桥接；美的/神华not_ready；三家production valuation均NOT_AVAILABLE，cash return均PARTIAL |
| 原Excel当前Hash | `4EA4AB6F291E0D3C8838A1729007C8B29D0825CCF7CA6459BBD16257BEC0188E`，12,138,778 bytes，mtime 2026-09-22 17:30:45；不同于历史冻结Hash，不能回退覆盖 |
| 未验证 | 最新生产数据原件、生产DB/服务/计划任务、全量历史测试、WPS界面与公式重算 |

当前 workflow 本机实测是173项，不沿用旧文档176项。CI PostgreSQL的4项使用自包含fixture；本轮真实runtime是在内存repository重放。两者都不证明生产PostgreSQL已迁移或真实市场研究有效。

### 新发现与复现

- `research_application.py:292`：显式spec.as_of可掩盖facts日期不一致。以既有测试fixture令case/spec为2025-12-31、facts为2024-12-31，仍返回outcome，valuation日期为2024-12-31。
- `research_application.py:266`：可将2025年输入的结果available_at设为2024-01-01；完整PIT约束尚未建立。
- `research_batch.py:310`：相同input hash而rule_version从v1变v2，仍得到UNCHANGED。
- 登记AssumptionSet并不自动证明它驱动了facts.scenario_inputs；G3仍读旧case状态。需在M1同一可信输入链修正/证明，而不是继续堆接口。
- Manifest-driven input adapter和Application结果到Excel仍缺；旧PE/PB screen仍可从CLI调用，必须标legacy后迁移，不能声称已经退役。

复现使用既有测试fixture和纯内存对象，无业务文件改动。明确异常原因和证据在LONG-TERM-GOAL第1节；本轮没有为了让状态变好而修代码。

### 成熟度与下一目标

当前是 L0工程基础已具备、L1研究工具早期/PARTIAL，不是L3决策支持或L4组合支持。架构方向总体对齐；主要风险是平台验收领先于真实研究/产品可用性。
M1计划交付20家分层入组、6家深研、真实跨模型/股息/当前桥接、冷启动replay及原Excel共同展示，具体质量与停止条件以current-stage-goal为准。M2全市场、M3决策/Entry/Journal/一致性、M4组合、M5事件、M6生产验收均NOT_STARTED；本轮没有启动它们。

## 历史阶段记录（保留原验收，不作为当前任务队列）

## C0 已冻结

C0-PRICE-BRIDGE-INTEGRITY：`PASSED_FOR_FREEZE`。

- 提交：`df4d343 C0-price-bridge-integrity`。
- 新增 `QuoteSnapshot` 与显式 `bridge_with_quote()`；收紧 ModelValidity、PriceBridgeResult、JSON 恢复和下游聚合。
- `current_research_status_from_payloads()` 不再用估值 symbol 覆盖冲突身份。
- 定向回归 47 项、Core Gate 102 项通过；旧 runtime 合同显式重验，茅台 READY 恢复不静默洗掉冲突。
- 三公司 runtime Hash 与原 Excel Hash 未变。

C0 只修复共享工程合同，不表示研究、估值、股息能力、生产数据或价格判断已经完成。

## C1 验收基线

- C1 开始 HEAD：`df4d343726f0d49fd5570e30b075cc46faf859d0`，工作树干净。
- 未连接服务器、生产数据库或定时任务；未重做原始财报、行情或重大事项审计。
- 目标：固定样本准入协议与公共编排审查。

## C1 验收结果

C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/fixed_sample_admission.py`，显式区分研究样本准入证据与估值推进证据。
- 新增 `FixedSampleAdmissionPolicy`、`FixedSampleCompanyAdmission` 和 `FixedSampleAdmissionReview`。
- 公共入口 `review_fixed_sample()` 对每家公司复用 ResearchGate、ValuationResult、ModelValidity、PriceBridge 和 CurrentResearchStatus 合同；不按 symbol 猜测 profile。
- 三家公司输出：

| 公司 | 编排合同 | 研究样本 | 有界价值 | 生产估值 | 显式决策 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | REUSABLE | ADMITTED_FOR_RESEARCH | CONDITIONAL | NOT_AVAILABLE | CONTINUE_CONDITIONAL_MODEL |
| 000333 美的集团 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | RESOLVE_MODEL_INPUTS |
| 601088 中国神华 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | PAUSE_PRODUCTION_VALUATION |

- 汇总状态：`engineering_orchestration_status=REUSABLE`，`production_valuation_available=false`。
- 所有记录均为 `human_confirmation_required=true`、`action=no_order`；不含仓位、订单、目标权重或实盘指令。
- 新增本地审查命令：`python scripts/review_fixed_sample_admission.py`。命令读取四个冻结指针，验证 Hash 后生成带 script/evidence Hash 的审查产物和 latest 指针。

验证证据：

- 新增防回归：`10 passed`，覆盖显式政策、条件估值不升级、空情景、缺研究证据拒绝、身份冲突、profile/model 类型失配、公共编排、序列化和三公司冻结回归。
- 更新后的 Core Gate：`112 passed`。
- 全量测试：`1901 passed, 1 skipped, 5 failed, 18 warnings`。5 个失败均是旧验收测试硬编码茅台报价日 `2026-09-21`；后台日更在 C1 验证期间将 current 指针推进到 `2026-09-22`。本轮未改历史验收测试或回退 runtime 日更产物。
- `compileall` 通过；`git diff --check` 通过。
- 美的、神华及研究卡 Hash 与冻结记录一致；茅台 current 已被后台日更推进，Hash 为 `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`。原 WPS 工作簿 Hash 仍为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`。
- 未改动估值参数、原 Excel、生产数据库、计划任务或服务器服务。

## 阶段语义

三公司统一工程/Excel MVP、C0 和 C1 均通过冻结。C1 的 `REUSABLE` 表示共享审查入口可用，不表示任何公司生产估值或现金回报结论可用。

| 维度 | 600519 贵州茅台 | 000333 美的集团 | 601088 中国神华 |
| --- | --- | --- | --- |
| Engineering Complete | READY：研究、估值和 C0/C1 共享合同可用 | READY：FCFF 算术与拒绝边界 | READY：周期算术与拒绝边界 |
| Research Complete | PARTIAL：商业/财务材料与论点存在，G3 未通过 | PARTIAL：事实范围 MODEL_NOT_APPLICABLE | PARTIAL：正常化假设和财务门未通过 |
| Valuation Complete | PARTIAL：低置信度 conditional_research_only | NOT_READY：无三情景值 | NOT_READY：无三情景值 |
| Dividend Research Complete | PARTIAL：有历史分红及分配交叉检查 | PARTIAL：有历史派息与部分财务材料 | PARTIAL：有派息与周期候选材料 |
| Production Data Ready | 2026-09-21 快照 READY；未验证 09-22 当前生产 | PENDING_EXTERNAL_DATA，并存模型适用性问题 | PENDING_EXTERNAL_DATA，并存未注册假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE：低置信度及研究门限制 | NOT_ASSESSABLE | NOT_ASSESSABLE |

三家公司完整 DividendSustainability 评估均未完成。

## 当前可追溯产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司研究卡 | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 茅台条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`（后台日更推进） |
| 美的未就绪结果 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 神华未就绪结果 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |
| 固定样本审查 | `runtime/fixed-sample-admission-review-latest.json` | `1dfe78e330ee45242d71a59a6888774408166fc215ca866816e4aefd6e535b4f` |

茅台估值日期为 2026-09-21，报价日已由后台日更推进到 2026-09-22；条件情景 403.44 / 478.43 / 571.25 元每股。此处仅描述研究模型，不是当前合理价或投资建议。美的、神华载荷日期为 2025-12-31，不能称作今日估值。

## 剩余风险与边界

- C1 是工程与准入协议验证，不替代生产行情、公告、重大事项或人工研究复核；当前价格评估仍为 NOT_ASSESSABLE。
- 后台日更会推进 current 指针；硬编码具体报价日的旧测试在日更后可能暂时失败，需在后续任务中把 current 回归改为对冻结快照的显式版本测试。
- 三家公司政策目前由 `scripts/review_fixed_sample_admission.py` 显式登记，属于受控 adapter；新增公司必须新增政策与证据，不能自动推断。
- 研究准入证据目前验证的是结构与 Hash 可追溯性，不是重新证明财务事实或论点内容正确。
- 固定样本协议尚未迁移到 PostgreSQL；runtime JSON 仍为当前可追溯中间产物。
- 通用多模型运行器与持久化注册表仍需在扩样本前补齐；最小现金回报研究合同由 C2 完成。
- 全市场漏斗、Web 前端和券商接入均未实现，不属于 C1 回归范围。

## C2 验收基线

- C2 开始 HEAD：`357e080b69edfe135eaabcd5d31dc7331e05b9d3`，即 C1 提交 `C1-fixed-sample-admission-orchestration`。
- 未连接服务器、生产数据库或定时任务；未改动估值参数、原 Excel、计划任务或服务器 PTA 服务。

## C2 验收结果

C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/distribution.py`：`DividendRecord`、`DividendHistory`、`DistributionCapacity`、`DividendSustainabilityAssessment`、`DividendYieldSnapshot`、`DividendResearchResult` 与两个合法 yield 构建函数。
- `DividendRecord` 强制区分 proposed / approved / paid，并校验公告、批准、除息、支付和 known_at 的时序；`DividendHistory` 只接受 known_at 不晚于 as_of 的事实。
- `DistributionCapacity` 与 `DividendSustainabilityAssessment` 不依赖价格，按 ResearchProfile 识别；READY 能力及已知可持续性均不允许 UNKNOWN 置信度。
- `DividendYieldSnapshot` 只接受同证券 verified close quote，并强制 DPS / price / yield 可复算；当前收益率与周期正常化收益率是不同对象。
- `FixedSampleCompanyAdmission` 和公共入口 `review_fixed_sample()` 接受可选 typed `cash_return_result`，同时保留旧手工 status/explanation 兼容路径。
- `scripts/review_fixed_sample_admission.py` 使用同一合同读取已审查现金分配注册表和冻结研究/估值载荷，为三家公司生成 typed 结果。
- 旧茅台估值与三公司验收测试改为读取冻结的 2026-09-21 快照并校验固定 Hash，不再依赖 rolling current/latest 指针；干净 checkout 中这些冻结 runtime 快照缺失时显式 skip，不误报为当前生产失败。

三公司 typed 现金回报状态：

| 公司 | 历史分红 | 分配能力 | 可持续性 | Yield 快照 | 现金回报研究 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | PARTIAL | PARTIAL | UNKNOWN | 1 | PARTIAL |
| 000333 美的集团 | PARTIAL | UNKNOWN | UNKNOWN | 0 | PARTIAL |
| 601088 中国神华 | PARTIAL | UNKNOWN | UNKNOWN | 2 | PARTIAL |

三家公司均仍是研究状态；有历史派息不等于分红可持续性或现金回报能力完成。公共审查保持 `REUSABLE`、`production_valuation_available=false`、`human_confirmation_required=true`、`action=no_order`。

验证证据：

- Core Gate 同款离线清单：`124 passed`。
- 冻结历史验收：`tests/test_moutai_valuation_export.py` + `tests/test_three_company_unified_acceptance.py`：`9 passed`。
- Distribution + 固定样本 + 价格桥接 + quote 定向回归：`74 passed`。
- 新离线三画像 typed 合同测试覆盖 600519 / 000333 / 601088 的 quality_compounder / mature_manufacturing / cyclical_cash_return，确认三公司复用同一合同且均为 PARTIAL。
- 审查命令成功生成：`runtime/fixed-sample-admission-review-20260922T101442190293Z`，evidence SHA-256 `022cfd2f501a358ff843799ec227a832d5a23a370cbd3238f238f93f2f4ed0d0`。
- `compileall` 与 `git diff --check` 通过。
- 全量历史测试尝试运行至约 83% 后停在旧网络/外部 fixture 路径，未作为 C2 验收依据；C2 只冻结上述离线 Core Gate 和定向回归证据。

## 剩余风险与边界

- 本任务是共享领域合同和 fail-closed 类型验证，不是三家公司的股息可持续性研究、生产数据核验或未来派息承诺。
- 现金分配注册表目前是受控 JSON adapter；茅台 fiscal attribution、提案/批准日期、税费和结算时点仍列为显式 blocker。
- Distribution 对象尚未迁移到 PostgreSQL；runtime JSON 仍是当前可追溯中间产物。
- ShareholderYield、完整 distribution_profile、行业阈值和回购/稀释口径未实现，不属于 C2。

## M1 Gree dividend lifecycle completion: 2026-09-23

See `docs/m1-gree-dividend-lifecycle-20260923.md` for the complete receipt.
The Gree `000651` distribution package now has official CNINFO implementation
evidence for FY2024-final and FY2025-interim dividends, both paid records now
carry verified ex/payment dates, and the workbook includes READY trailing and
declared yield snapshots. The normalized scenario remains NOT_READY.

Published workbook SHA-256:
`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`.

## C3 验收基线

- C3 开始 HEAD：`d658b92 C2-minimal-distribution-research-contract`；工作树开始时的改动仅包含 C3 的 W1 治理校准。
- C2 的唯一建议后续任务“最小 Distribution 合同迁移到 PostgreSQL”已被 C3 吸收，但 C3 范围扩大到通用 Research Artifact 合同、Repository、Runner、Registry、Manifest、Batch、CI 与三公司 E2E。
- 数据库安全边界：`.env` 中的生产 `DATABASE_URL` 在本阶段不得连接；只使用 disposable/local/test PostgreSQL 或 GitHub CI 一次性实例。

## C3 验收结果

C3-RESEARCH-PLATFORM-FOUNDATION：`PASSED_FOR_FREEZE`。

提交序列：

```text
7903933 C3.1 governance and research artifact contract
6eee08e C3.2 repository and typed artifact round-trip
a89e269 C3.3 frozen runtime parity importer
b787b3e C3.4 profile-driven application research runner
365d845 C3.5 explicit valuation model registry contract
2bfe065 C3.6 versioned fixed sample policy manifest
33590bb C3.7 failure-isolated research batch contract
9d9231b C3.8 offline core and disposable postgres CI
13c5b03 C3.10 three-company frozen replay receipt
412564a C3.11 presentation boundary and expansion verdict
957243f C3.12 isolate postgres CI from ignored runtime data
fc49ab7 C3.13 align postgres import assertion with review scope
```

W1-W12 结果：

- W2-W3：新增 `sql/20260922_research_artifacts.sql`、`research_artifacts.py`、`research_artifact_codecs.py` 和 `research_artifact_repository.py`。新表 append-only，与旧混合语义 `valuation_results` 分离；round-trip、版本 head、Hash 与 fail-closed 均有测试。
- W4：`research_runtime_import.py` 把三公司 frozen runtime 核心 artifact 迁入 repository，输出 source path、source/database SHA-256 和 restored semantic status；缺失 `model_validity` 显式记为缺失，不伪造。
- W5：`research_application.py` 使用显式 `ResearchRunSpec`，按 Profile -> Router -> Model -> Validity -> PriceBridge -> Distribution -> CurrentStatus -> Repository 编排，不按 symbol 猜模型。
- W6：`valuation_router.py` 已表达三种 Profile 与三种模型/Facts 合同；未知 profile 为 `UNSUPPORTED`。
- W7：三公司 admission policy 迁入 `config/fixed-sample-manifest.json`，禁止交易键，loader 做 schema 与 profile/model 校验。
- W8：`research_batch.py` 隔离单公司 GAP/FAILED/UNSUPPORTED，支持 run_id、rule_version、时点和幂等输入 fingerprint。
- W9：GitHub Core Gate 保持离线，另增加 disposable PostgreSQL job；本地未使用生产 DSN。
- W10：`research_e2e_replay.py` 完成三公司 Manifest -> ResearchRunSpec -> Application -> Repository -> Batch replay。真实 frozen runtime 结果为 `all_semantics_matched=True`、`action=no_order`。新增命令行 `python scripts/run_three_company_research_replay.py`，输出独立 JSON 审计收据。
- W11：Application/Presentation 边界审查通过并记录技术债，见 [application-presentation-boundary.md](application-presentation-boundary.md)。Domain/Application 不依赖 Excel 或 PostgreSQL schema；旧 Excel publisher 尚未切换到新 Application result。
- W12：Expansion Readiness Verdict 为 `NOT_READY`，原因见 [fixed-sample-expansion-readiness-review.md](fixed-sample-expansion-readiness-review.md)。核心 pipeline 可复用，但缺少 manifest-driven facts/assumptions/quote input adapter，且 replay adapter 仍含茅台 symbol 专用分支。

验证证据：

- Offline Core Gate 全清单：`176 passed`。
- 新增三公司 replay 自包含 fixture：三种 Profile、三种模型、`no_order`、美的/神华 `not_ready`、神华 current/normalized yield 区分和 Hash 篡改 fail-closed。
- PostgreSQL integration 在本机无 disposable DSN，`4 skipped`；GitHub CI 中由一次性 PostgreSQL service 验证 migration、repository round-trip、frozen runtime import 和三公司 replay。最终验收运行 `35727542158` 的离线 Core 与 disposable PostgreSQL job 均为 success。
- 本机真实 frozen runtime 命令验证：`all_semantics_matched=True`、`action=no_order`、收据约 193KB。
- `compileall` 与 `git diff --check` 通过。
- 未连接生产数据库、未修改旧 `valuation_results`、未改动原 Excel、未调整估值参数、未触碰服务器 PTA 项目或计划任务。

## C3冻结时的后续建议（历史，已被M1吸收）

下面保留C3当时的建议，不是当前执行指令。当前唯一待启动目标见本文开头与current-stage-goal.md；adapter只是M1的前置工作包。

```text
NEXT TASK: C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER
```

先移除三公司 replay 中的茅台 symbol 专用分支，建立 versioned per-company input descriptor，再以离线 fixture 和 disposable PostgreSQL replay 验收。验收前不新增第四家真实公司，也不自动扩样本。

## 2026-09-24 M2 Verification v2 / Checkpoint A 重提

M2 Verification v1 已标记 `SEMANTICALLY_SUPERSEDED`。v2 使用独立的四通道
`ChannelVerificationPolicy`，不再允许
`PENDING_DEEP_RESEARCH + evidence_count > 0 -> VERIFIED_FOR_DEEP_RESEARCH`。
对冻结的 18 条 LEAD 重跑后的真实结果如下：

```text
VERIFIED_FOR_DEEP_RESEARCH = 0
REJECTED_AFTER_VERIFICATION = 13
INSUFFICIENT_EVIDENCE = 5
UNSUPPORTED = 0
PIT = PASS
MACHINE_STATUS = MACHINE_CHECKS_PASS
```

分通道结果：

| 通道 | 进入深研 | 否决 | 证据不足 |
| --- | ---: | ---: | ---: |
| Quality | 0 | 0 | 0 |
| Dividend / Cash Return | 0 | 3 | 3 |
| Value | 0 | 5 | 1 |
| Cyclical | 0 | 5 | 1 |

旧 v1 中被写成 VERIFIED 的 `002327 富安娜`、`002867 周大生`、`600011 华能国际`
现在均按 v2 fail-closed 为 `INSUFFICIENT_EVIDENCE`。0 个 VERIFIED 是允许且诚实的
结果，不降低研究标准，也不构成全市场“没有质量公司”的判断。

关键冻结产物：

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| M2 v2 report | `runtime/m2-channel-verification-20260924-v2/report.json` | `310d56e408655c7c46ef510a4ce3aab44d99ab9aeb021c9ddd41f140a2fb1653` |
| M2 v2 manifest | `runtime/m2-channel-verification-20260924-v2/manifest.json` | `520d175d5a7696b970c091c88be9e8b5996a7627a58828594671f524e360aabe` |
| M7 Daily v3 workbook | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx` | `d423ef1ab0114f97e4a20d2f7f770b85e74b3764d6484b63d2fec03c9da82718` |
| M7 Daily v3 manifest | 同名 `.m7-daily-workbench-manifest.json` | `31f918dbf43b0d9b7faaf1f933dace64c1b449d32b675d1058d330e00161e75b` |

M7 Daily v3 的 WPS 只读验证 `passed`：10 个可见页、2 个隐藏页、公式错误扫描和
禁词扫描均通过，打开前后工作簿与 canonical 的 Hash 未变化。同名候选已复制到
WPS 云盘 `价投跟踪`，与仓库文件逐字节一致；没有覆盖 canonical 原表。

本轮新增版本化、只追加、Hash 绑定的
`HumanMilestoneReviewReceipt`。人工结论只记录为：

```text
M2_CHECKPOINT_A = NOT_APPROVED_PENDING_VERIFICATION_V2
M3_NEGATIVE_CARDS = PASS
M3_CHECKPOINT_B = PARTIAL_NOT_APPROVED
M5_1225578520 = NOT_MATERIAL
M7_SEMANTIC_STRUCTURE = PASS
M4_PRIVATE_INPUT = PENDING
M6_AUTHORIZATION = PENDING
M7_FINAL_UX = PENDING
```

Checkpoint A 重提包目录为
`runtime/m2-checkpoint-a-human-resubmission-20260924-v2`。人工收据
`receipt.json` 的 SHA-256 为
`5a29fad3af4b6c3521236aee6d7cd70884287b318b20d3c95535ba974567bd0a`，
Checkpoint A packet 的 SHA-256 为
`c5317f641a8cf56ee2bfddaf7910d0f6b0088c8a331d1c07255094bd416efc13`。
M5 的 `NOT_MATERIAL` 已绑定
`announcement_id=1225578520` 与 PDF SHA-256
`7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`。

以上内容不表示 Checkpoint A、Checkpoint B 或 M7 已签收；`action=no_order`，
没有生产操作、数据库迁移、调度、通知、券商连接或 PTA 项目改动。M2 状态保持
`PENDING_HUMAN_REVIEW`，等待用户重新复核 Checkpoint A。

## 2026-09-24 M2 Checkpoint A 人工签收与 M2 收口

用户完成 Checkpoint A 人工复核并给出正式结论：

```text
M2_CHECKPOINT_A = HUMAN_PASS
```

新的 append-only 人工收据为 sequence=2，不覆盖 sequence=1 的
`NOT_APPROVED_PENDING_VERIFICATION_V2` 历史收据，并绑定其 SHA-256：

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 人工收据 | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/receipt.json` | `9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20` |
| Checkpoint A 验收包 | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/checkpoint-a-packet.json` | `b880b74752362deccd1991d23a43f7347f7e5a8348e0ae6ca0603a5931e8f306` |
| 验收 manifest | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/manifest.json` | `a11552c0dd343564a6024c1feeadcfbca83f97d420aa5519ed4533e09937d501` |

M2 正式状态更新为：

```text
M2 = DONE
M2_CHECKPOINT_A = HUMAN_PASS
OVERALL_PRODUCT = PARTIAL
action = no_order
```

用户同时保留两项非阻断方法债，不影响 M2 收口：

```text
BL-20260924-001: Dividend payout ratio / cash-conversion 语义校正
BL-20260924-002: Value EV/EBIT 或 Profile 等价指标
```

详细条件见
[m2-non-blocking-method-debt-20260924.md](m2-non-blocking-method-debt-20260924.md)。
M3 strict contemporaneous-rule Historical PIT 仍为 `NOT_PROVEN`；Checkpoint B、
M4 私有输入、M6 授权和 M7 用户验收均不因 Checkpoint A 通过而自动签收。下一工作
包回到原总 Goal：继续 M3 Decision Review / Checkpoint B，再按依赖推进
M4/M5、M6、M7。

## 2026-09-24 M3 重建证据连续性工作包

在冻结的 600519 / 2024-06-21 追溯重放基础上，新增一个与真实 Entry、Journal 和
人工决策完全隔离的官方披露连续性候选。它只重建披露数值的算术演变，不签发研究
批准、价格结论、持有决定或执行动作。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 工作簿 | `runtime/m3-reconstructed-continuity-20260924T083028Z/A股价值投资_M3重建证据连续性候选_20260924.xlsx` | `719725a31749558d21070a1211862e2811d7b688082697ad9faad19ace930ccb` |
| Trace | `runtime/m3-reconstructed-continuity-20260924T083028Z/trace.json` | `f49bc61c302e11c70e6ee954768d59389f17b9c2933a9b02364439be74d99cc6` |

边界固定为 `RECONSTRUCTED_EVIDENCE_ONLY`、
`RETROSPECTIVE_RESEARCH_EXTENSION`、`strict_contemporaneous_rule_pit=NOT_PROVEN`、
`actual_entry_present=false`、`human_decision=null`、`action=no_order`。
新增六个展示页：`00_重建边界`、`01_历史基准`、`02_官方披露演变`、
`03_一致性观察`、`04_阻断与结论`、`05_来源哈希`。该候选不是 Checkpoint B；
Checkpoint B 及后续人工/生产验收继续按原边界保持待办。详细来源和边界见
[m3-reconstructed-evidence-continuity-20260924.md](m3-reconstructed-evidence-continuity-20260924.md)。

## 2026-09-24 M5 贵州茅台真实披露队列扩展

在 M3 重建证据连续性候选完成后，继续原总 Goal 中依赖已满足的 M5 离线工作：
使用既有 `scripts/build_m5_disclosure_queue.py` 重建 600519 的真实 CNINFO
公告窗口，不修改既有 3 家公司队列、reconciliation 或 canonical。

- 窗口：`2026-06-01` 至 `2026-09-09`，检索时间
  `2026-09-24T08:47:15Z`。
- 结果：16 条公告，9 条待人工复核，0 条来源缺失，覆盖状态 `COMPLETE`。
- 公开工作簿：
  `A股价值投资_M5真实披露待复核队列_600519_20260924.xlsx`，
  SHA-256
  `02cd3499ed4e805f2d76d0f7f0aba89d02be123b02ae3723b43e80f1509eaa3c`。
- WPS 只读验证 `passed`；WPS 云盘同名副本与仓库文件逐字节一致。
- 标题规则只生成待复核候选；9 条公告仍由用户逐条给出
  `EventMaterialityDecision`，系统不自动判定重大性或产生事件。
- `action=no_order`；不构成 Checkpoint C、生产调度、通知或 M6 运营验收。

九条待复核公告和原件 Hash 见
[m5-600519-disclosure-review-20260924.md](m5-600519-disclosure-review-20260924.md)。

公开工作簿 WPS 云盘全量字节审计已重跑为 `27/27 MATCH`；对应 GitHub Core
Research Gates run `35977515495` 为 `success`。新增文件仍未改变任何公告材料性
结论，所有候选继续等待人工决策。

## 2026-09-24 M7 Daily v4：Checkpoint A 后展示闭环

M2 收口后，继续原总 Goal 中依赖已满足的 M7 展示工程，不覆盖已冻结的 v3 候选或
canonical。新 v4 候选把 M3 重建证据连续性和 600519 真实披露待复核队列接入既有
10+2 页每日工作台，并把 M2 状态在展示层更新为 `DONE / HUMAN_PASS`。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| M7 Daily v4 | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.xlsx` | `569adf26fece3b45666138c050776b40cb077f0e0b9f498a0dd77445a83c2a59` |
| manifest | 同名 `.m7-daily-workbench-manifest.json` | `f8b461a66f7f5a3274fc517e6232f37848f3d9dead4d109fea8fcda05ceae106` |

- 新接入层保持 `RECONSTRUCTED_EVIDENCE_ONLY`、`strict PIT=NOT_PROVEN`、
  9 条待人工复核、`action=no_order`。
- WPS 只读验证 `passed`；WPS 云盘同名候选与仓库文件逐字节一致。
- 定向回归 `14 passed`；canonical SHA-256 保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 隔离 basetemp 全量离线回归：`2403 passed、6 skipped、1 failed`；唯一失败仍是
  仓库既有 `test_moutai_current_valuation_admission.py` 的
  `daily_simulation_policy_implemented` runtime 指针断言，不在本轮 M7 改动路径内。
- 公开工作簿 WPS 云盘全量字节审计更新为 `28/28 MATCH`。
- 详细边界见
  [m7-daily-workbench-v4-post-checkpoint-a-20260924.md](m7-daily-workbench-v4-post-checkpoint-a-20260924.md)。

本候选不构成 Checkpoint B/C/D、真实 IPS/组合、生产授权、M6 运营验收或 M7
最终交付；总 Goal 继续按原依赖推进。

## 2026-09-24 M3 Checkpoint B 版本化人工复核包

M2 Checkpoint A 收口后回到原总 Goal 的 M3 主线，新增只读的 Checkpoint B 人工
复核包生成器，把三份 M3 候选、机器审计、strict PIT 证据和 M2 append-only 收据
合并为同一版本化入口。生成器只汇总证据，不写人工收据，不把 Checkpoint B 标为
通过，不生成 Entry、Journal、个人组合、仓位或订单。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| Checkpoint B packet | `runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-packet.json` | `fab538fb283b55b449d6c52be908216cbe2df06880a2c66848901371a15c7eb4` |
| 人工复核说明 | `runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-review.md` | `b7d0b16cebb6c98537865a878764617a1c102fb3508cd6564022540966a2c712` |
| manifest | `runtime/m3-checkpoint-b-human-review-20260924-v1/manifest.json` | `76082bb8b359964445954293495208cacf385a44374d717629a77ca5f6f23de4` |

- 三张卡保持 `000651 / 600741 / 600887` 均为 `INSUFFICIENT_RESEARCH`、
  `RESEARCH_INCOMPLETE`、`action=no_order`。
- M3 三份审计保持 m3c7 / owc7 / hoc7 `PENDING_HUMAN_REVIEW`。
- strict contemporaneous-rule Historical PIT 保持 `NOT_PROVEN`。
- M2 Checkpoint A 收据保持 sequence=2 与固定 Hash，没有覆盖历史收据。
- 新增定向回归 `2 passed`，并纳入 GitHub Core Research Gate。

用户实际完成三份候选阅读、逐卡复述阻断/反证/重开条件并明确给出
`M3_CHECKPOINT_B=HUMAN_PASS` 后，才会新增下一份 append-only 人工收据；当前包
不构成 Checkpoint B 通过或后续阶段升级。

## 2026-09-24 M5 600519 Hash 对账与空白人工回填表

在 Checkpoint B 等待人工签收期间，继续原总 Goal 中依赖已满足的 M5 离线工作。对
600519 / 2026-06-01 至 2026-09-09 的真实 CNINFO 队列执行既有人工台账 Hash 对账，
并生成九条公告的空白人工材料性回填表。

- 对账结果：当前候选 9、历史结转 0、待人工复核 9、Hash 冲突 0。
- 对账收据：
  `runtime/m5-600519-human-review-reconciliation-20260924-v1/reconciliation.json`
  SHA-256
  `5b9cea760461fb6821777474b05878a7682f08d85cdcbf5a78b917365e4f27ea`。
- 空白回填表：
  `A股价值投资_M5真实披露人工复核回填_600519_20260924.xlsx`
  SHA-256
  `6451f986c81c4db1277f795e6a0666c22810728d621524070935b21edc4e7f0c`。
- WPS 只读验证 `passed`；WPS 云盘同名副本与仓库文件逐字节一致。
- 判定列和复核说明列均从空值开始，`action=no_order`。
- 公开工作簿 WPS 云盘全量字节审计更新为 `29/29 MATCH`，收据
  `runtime/public-workbook-wps-audit-post-m3-m5-20260924/receipt.json`。

本工作包不判定任何公告重大性，不产生 M5 事件、依赖失效、调度、通知或 M6 运营
验收；九条公告仍由用户逐条给出 `EventMaterialityDecision`。

## 2026-09-24 M3 Checkpoint B 人工 partial 收据

用户已完成三张负向决策卡的实际阅读和语义复核。记录结果时严格区分三项通过的
子检查与整体 Checkpoint B，不把子项通过扩大为 `HUMAN_PASS`：

```text
M3_NEGATIVE_CARD_HUMAN_REVIEW = PASS
M3_HUMAN_UNDERSTANDABILITY = PASS
M3_NO_FALSE_BUY_ADD = PASS

M3_CHECKPOINT_B = PARTIAL
M3_BLOCKER = STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN
M4_PERSONALIZED_ACCEPTANCE = PENDING_USER_PRIVATE_INPUT
M6_PRODUCTION_AUTHORIZATION = NOT_YET
action = no_order
```

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| Human receipt sequence 3 | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/receipt.json` | `933f81ace48da1119d6afb26c9fc92ddb0e8de142a83d043df8f43122ea62c98` |
| partial acceptance packet | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/checkpoint-b-partial-packet.json` | `27c489828cf116e5b1d97473f6cc072fb6bace9ad9cfa396665c7039c56fab7a` |
| manifest | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/manifest.json` | `f418f7a36c2635507c3c603a3497e4f46e2822c577ef3380996274791c51255a` |

- 新收据绑定 sequence 2 文件 Hash
  `9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20`，
  不覆盖历史。
- `HumanMilestoneReviewReceipt` 新增可选 `supplemental_decisions`；没有该字段的旧收据
  序列化与 Hash 不变。
- 三张卡保持 `000651 / 600741 / 600887` 的 `INSUFFICIENT_RESEARCH`、
  `RESEARCH_INCOMPLETE`、`action=no_order`。
- strict PIT 的规则版本为 `RETROSPECTIVE_RESEARCH_EXTENSION`，
  `future_rule_version_used=true`；不伪造历史规则登记证据，也不降低标准。
- 新增定向回归 `12 passed`；M3 相关复核回归 `16 passed`。
- 详细边界见
  [m3-checkpoint-b-human-acceptance-20260924.md](m3-checkpoint-b-human-acceptance-20260924.md)。

该 blocker 不阻止 M4/M5 中依赖已满足的离线工程继续。M4 个人化验收仍等待真实
IPS/组合输入；M6 仍只允许 preflight、dry-run、backup/restore、health、
emergency-stop 和 shadow tooling，不授权生产迁移、调度、通知或真实账户导入。

## 2026-09-24 M5 durable run request / receipt 闭环

在 M5 离线链路上补齐「一次请求只提交一次、收据可持久重放」的最小闭环，全部使用
合成数据（symbol `600887`，`SYNTHETIC_OFFLINE_ONLY`），未读取或代签任何真实公告。

```text
M5 Engineering        = DONE_FOR_DURABLE_REQUEST_RECEIPT_LOOP  （新增，仅离线合成数据）
M5 Product Acceptance = PARTIAL                                （不变）
M5 Production         = NOT_AUTHORIZED                         （不变）
M4 Personalized       = PENDING_USER_PRIVATE_INPUT             （不变）
M6 Authorization      = NOT_YET                                （不变）
action                = no_order
```

- 新增自包含 run request（events、observed times、完整 watermark、dependency
  graph、direct kinds、run/batch/stream id），由 `request_id` + SHA-256 固定；
  非 canonical payload 直接拒绝。
- run state 的 batch record 与 run request 共用同一 `batch_request_fingerprint`，
  receipt 发布前校验绑定，防止「请求 A / 提交 B」。
- 新增 write-once receipt store：原子替换 + 文件锁；`audit_fingerprint` 相同才视为
  `ALREADY_PUBLISHED`，不同即冲突，不覆盖既有证据。
- pre-commit 与 post-commit 两个崩溃窗口都有恢复测试：前者只提交一次，后者为
  idempotent replay 并补写一次收据。
- 修复 `FAILED_TERMINAL` 通知失败被当作已结案导致 `HEALTHY` 的 fail-open；
  现在保持 `ATTENTION` 并进入 `review_due`。
- 修复复核对账允许重复 prior `review_id` 覆盖 Hash 的审计漏洞。
- 新增回归 `tests/test_m5_run_request.py`（`12 passed`）与 3 条 fail-closed 回归；
  本地全量离线回归 `2522 passed, 5 skipped, 18 warnings, 0 failed`。

仍未完成，且阻断真实 apply：归档 PDF 字节 Hash 尚未在 intake 重算；工作簿尚未
贯通 `supersedes_event_id` / `event_cluster_id` 列与原件 hyperlink；历史被拒
ingest 需要 M6 运营聚合视图单独呈现。600519 九条真实公告保持
`PENDING_HUMAN_REVIEW`，等待用户逐条材料性判定；本批不产生事件、不发送通知、
不请求生产授权。

## 2026-09-26 Productization / security / real-use closure

本轮没有启动生产、Shadow、调度、通知或真实账户导入。事实状态：

```text
M7_PRODUCT_READ_MODEL = READY
M7_PRODUCT_UX_CANDIDATE = READY / NOT_USER_ACCEPTED
ADV_P1_003 = CLOSED (signed byte-bound receipt + pinned trust root)
ADV_P1_004 = CLOSED (proof re-verified on read/transition/restart + pinned trust root)
ADV2_P0_001 = CLOSED (legacy M5 authorization is read-only replay only)
ADV2_P0_002 = CLOSED (trust roots pinned; empty registry keeps ACTUAL/M6 fail-closed)
ADV2_P0_003 = CLOSED (M6 session/operational/event evidence requires pinned roots)
ADV2_P1_001 = CLOSED (M5 approval expiry window enforced on issuance and replay)
ADV2_P1_007 = CLOSED (test registry cannot be redirected by environment/path)
M4_CONFIRMATION_CONTRACT = READY
M4_SYNTHETIC_ONBOARDING_REHEARSAL = COMPLETED
M4_PERSONALIZED_ACCEPTANCE = WAITING_R2
GENERIC_PRODUCT_CLI = ACTIVE (15 product / 36 engineering / 51 unique; 43 v1 preserved)
M6_START_CRITERIA_MATRIX = COMPLETE
M6_OPERATIONAL = NOT_STARTED
600519_HISTORICAL_VALIDATION = NOT_PIT_SAFE / NOT_ADMITTED / EVIDENCE_STOP
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

- M7 五页产品面为 `今日 / 机会 / 公司 / 我的组合 / 事件`，`系统/审计` 为次级页；
  M2-M6 不再是用户导航。没有真实私人组合时只显示“尚未接入真实组合”，模拟 M4
  数字不会作为个人指标展示。
- 当前候选工作簿为 `runtime/m7-product-ux-candidate-v2-20260926.xlsx`，SHA-256
  `f3d29985f58f8a1e0925781c5161292cf5cf8c4643931cece64ed85fc4f452f3`；manifest
  SHA-256
  `0707513bab1df08bd01dca00f8d200afd105bb8d341e7b78ca18f56e4ab4e6ed`。v1
  候选保留为历史制品但已被 v2 取代。v2 由固定
  M2-M6 packet 生成，来源 packet SHA-256
  `8328bf5dc0427ef7ce66e216ae7f20f32451e95bf70f63ac6bf1be2e9adc7a0d`。
  `final_user_acceptance=NOT_PASSED`、`canonical_pointer_modified=false`，正式 WPS
  工作簿未被替换。五个用户页不再包含 `M2`-`M6` 阶段词；该约束由产品 payload
  门禁和合成回归测试强制。
- M4 合成全链路真实执行了 init、validate、encrypt、verify、双快照 reconciliation、
  confirmation receipt、PortfolioRisk、PositionGuidance、DividendProjection、Product
  Read Model 和 M7 candidate material。最终演练 receipt SHA-256
  `7f6d68b3abcc18c01e95c6798a8647e9ef28afce46b3d4e4a9b88da9e6eae6fe`；分类为
  `SYNTHETIC_REHEARSAL_ONLY`，没有使用或生成真实私人组合证据。
- M5 ACTUAL 能力现在只能由签名、字节绑定、append-only 的人工审批收据签发。默认
  解析、应用和新 CLI 都会拒绝旧式无签名授权；显式 `allow_legacy_read_only` 只允许
  对 durable store 中已存在、request fingerprint 完全一致且已有绑定 receipt 的批次
  做只读读取；底层 runner 不再接受 legacy 标志，空 store 或缺失 receipt 都会以
  `read-only replay only` 失败关闭，不写 state、不发布 receipt。M5 v2 审批载荷新增
  必填 `valid_until`，签发、能力恢复、每次能力验证和 durable application 都按
  `authorized_at <= evaluation_time <= valid_until` 复核；应用 CLI 使用一次系统墙钟
  评估时间，不把调用方提供的 `generated_at` 当成授权时钟。M6 运行控制证明在读取、
  转换、推进和重启时重新验证签名制品、scope、目标模式、部署/配置 Hash、操作者、
  有效期和 trust root。
- 第二轮对抗审查关闭了 trust-root 自签问题：`config/authorization-trust-roots-v1.json`
  目前 pin 列表为空，因此真实 ACTUAL/M6 授权默认 fail-closed；M5 在签发与每次
  `verify()` 时重查 pin，M6 在每次读取、转换与重启时重查 pin，解除 pin 会让既有
  capability 立即失效。负向测试覆盖未 pin 的 M5 收据、全新生成的 M6 keypair、
  授权窗口缺失/倒置/篡改/过期/重放，以及 legacy runner 旁路。真实 operator key 仍应
  放在独立 keystore/OS pin 中，这是首次真实授权前的开放前置条件（ADV2-OPEN-001）。
- 后续证据边界复核关闭了 `ADV2-P0-003`：公开 `verify_shadow_bundle` 必须 pin 完整
  root；operational admission 只 pin 外层 root，内层 candidate root 由外层完整
  fingerprint 绑定并通过内部 byte verifier 使用；event admission 在读证据前执行同一
  pin gate。`ADV2-P1-007` 同时关闭：测试 registry 改为进程内显式 hook，伪造
  `PYTEST_VERSION`/`VIA_AUTHORIZATION_TRUST_REGISTRY` 或传入任意 registry path 均不再
  影响生产 lookup。真实 key、caller-clock 和跨独立 store 的全局 single-use journal
  marker 仍是生产授权前的外部门/后续边界，不在本轮宣称完成。
- 其余同轮修复：M7 组合数值只有在 M4 provenance（reconciled + 确认回执 fingerprint）
  齐备时才显示；候选投影的 `root` 变为必填并逐个校验证据文件 Hash；M6 start matrix
  支持 `SHADOW_START_READY` 但当前仍为 `shadow_start_allowed=false`；event review
  不再默认声称人工 provenance，manifest 明确标注未认证并仍需签名审批收据；
  `build_m5_disclosure_queue.py` 与 `apply_m5_disclosure_review.py` 从产品入口降级
  为工程工具；`virtual_account_store` 强制 simulation-only 标记。
- M4 confirmation receipt 绑定 exact reconciliation bytes、账户范围、快照日期和
  用户确认；公开输出只含 fingerprint。公开 Git 不包含私人 IPS、持仓、现金、密钥
  或明文组合。
- 全量离线回归 `2953 passed, 30 skipped, 18 warnings, 0 failed`（第二轮审查新增
  trust-root pinning、legacy 只读重放、simulation-only、矩阵可启动态等测试）。
  过程中发现并修复多处真实兼容问题：两条历史 M5 ACTUAL 冷重放、一条 M6 旧 scope
  fixture，以及依赖 CLI 自带 trust root 的 M6 集成用例；修复后历史只读路径与新签名
  路径分离，不能用兼容层伪造新授权，测试夹具也改为显式 pin 自己的 trust root。

本工作包仍不产生交易信号、目标仓位、订单、调度、通知、生产数据库写或 M6 运营
验收。下一步只能由真实 R2 私人输入、R3 明确生产授权或 R6 自然时间证据推进对应
门；600519 不重开无边界历史证据收集。

## 2026-09-27 R2 simulated product boundary check

本轮仅完善并验证了模拟产品体验，不读取、复制或发布任何真实个人组合数据。

```text
SIMULATED_PRODUCT_DECISION_REVIEW = READY
M4_SYNTHETIC_ONBOARDING_REHEARSAL = COMPLETED_SYNTHETIC_ONLY
M4_PERSONALIZED_ACCEPTANCE = WAITING_R2
REAL_PRIVATE_INPUT_STATUS = NEEDS_INPUT
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

- 公司页新增可选“决策复核”展示区，用于呈现上游研究的关注重点、买入复核前提、
  加仓纪律和退出/降级条件；该区块不计算估值、仓位或订单，且递归拒绝执行字段。
- 模拟体验脚本位于 `scripts/current/build_simulated_product_user_trial.py`，只能显式确认后
  在 `runtime/` 生成预览，不能替换 `WORKBOOK_PATH` 或写入正式用户入口。
- R2 合成演练收据为
  `runtime/m4-synthetic-onboarding-r2-product-boundary-20260927/receipt.json`，
  SHA-256 `456cb073b2d25004a91fff4842c501c9903aafb7551f8ce7f2b150669975b1c7`；
  分类为 `SYNTHETIC_REHEARSAL_ONLY`，明确不构成真实个人化验收。
- 私有空白模板验证返回 `NEEDS_INPUT`，缺少 IPS 确认、现金、仓位快照与对账；
  不生成任何个人组合数值或仓位建议。
- 本地架构边界测试 `27 passed`，产品与目录纠偏测试 `38 passed`；GitHub Core Research
  Gates 运行 `36270833139` 的 `offline-core` 与 `postgres-integration` 均为成功。
# 2026-09-27：公共研究连续推进阶段启动

`STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-USE-ADVANCEMENT` 取代了将 R2 私人
组合 onboarding 误作全局等待状态的表述。M4 仅在本地保持
`M4_ENGINEERING=COMPLETE_FOR_CURRENT_SCOPE`、`M4_SYNTHETIC_REHEARSAL=COMPLETE`、
`M4_PERSONALIZED=PARKED_WAITING_R2`；未读取、扫描、推断或发布任何私人组合数据。
公共研究、公共事件和 canonical Excel 产品轨道继续独立运行，永久 `action=no_order`。

已新增 `config/prospective-research-observation-plan-v1.json`：它在 2026-09-27
09:30 +08:00 预登记 000333、600887、601088 三个公共观察案例，明确模型画像、公开
来源定位器、待验证假设、基线截止和 PIT 规则，并明确排除 600519（现有 evidence-stop
规则）及任何当前价格、个人组合、订单或结果导向筛选。登记命令
`scripts/current/register_prospective_research.py` 只能将不可覆盖回执写到 `runtime/`，
回执绑定计划 SHA-256 和运行时 Git revision，且明确 `outcomes_observed=false`、
`valuation_executed=false`、`decision_signal_created=false`、`portfolio_data_used=false`。
这建立了前瞻观察边界，不构成估值、投资建议、M3 strict PIT 证明、生产数据验证或 Excel
发布。

当前为周末，尚未形成晚于既有已完成交易会话的官方收盘事实；因此未刷新 Quote、未发布
canonical workbook、未重跑模拟链。下一次仅在新的官方已完成会话或新的有界公共事件到达时，
分别更新相应轨道；M6 保持 `NOT_STARTED`，未做服务器、Shadow、调度、通知或生产操作。

实现提交 `fb8c8da8e9172078bdf7778592f85e9923b7c898` 的本地定向验证为 `37 passed`；
GitHub Core Research Gates run `36280767561` 中 `offline-core` 与
`postgres-integration` 均已 `success`。最终 runtime 登记回执绑定该提交，
`registration_sha256=f42cc5ca2876098fb72f9717fabb2fd4ef3b0f532411123cb663110d37602c96`，
并保留 `action=no_order`。这只证明前瞻登记合同和离线工程边界通过，不能证明任何
公司估值正确、投资逻辑有效、生产数据可用或系统已进入实盘辅助状态。

## 2026-09-28 R1: Midea CapEx 页码纠正与 Yili 复核

对美的 FY2025 年报和 2026H1 半年报开展两位独立只读复核。Root 直接以留存完整 PDF
重新计算 SHA-256，并读取相关物理页文本；两份 PDF 哈希分别为
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6` 和
`576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`，均与研究备忘录
相符。独立 R1 找到两处页码定位错误，金额均可复现且没有发现所核事实数值错误：

- FY2025 在建工程余额汇总（期末余额 3,071,226、减值准备 16,398、账面价值
  3,054,828 千元）在物理页 202；项目变动明细在物理页 203。
- 2026H1 在建工程余额汇总（期末余额 2,976,211、减值准备 16,398、账面价值
  2,959,813 千元）在物理页 157；项目变动明细在物理页 158。

原备忘录由收据以路径和 SHA-256 绑定，因此保持字节不变（当前哈希仍为
`bf732e55b77eea455da71a6c82491a6a9fc324f3d7c27afb556f30a2c2dc5bee`）。页码更正以
`docs/current/track-b-midea-capex-fixed-assets-review-corrigendum-20260928.md` 作为只追加
勘误（SHA-256 `f74da843a08b42e51985c4d127baf85db7c54c658519e6b2df88d1385a4a827e`），
不使旧收据失效。独立复核还确认原备忘录对维护/增长 CapEx、项目回报以及折旧
代理边界的表述审慎；本次不改变 baseline、事实准入、FCFF/估值准备度或股息状态，
不更新 Excel，不推导交易结论，`action=no_order`。

伊利减值与募集资金备忘录由另一 SubAgent 对照七份留存 PDF 作 R1 复核：未发现重大
事实或计算问题，核实了减值口径与商誉测试范围、933,865,021.35 元专户余额计算及
延期信息的未决边界。复核没有把减值机械加回正常化利润，亦未作估值或预测推断；
原件哈希与页码证据记录见 `docs/current/track-b-yili-impairment-and-proceeds-review-20260927.md`。
备忘录未修改。

本轮开始时工作树已有大量未提交改动，当前分支为 `main`。按阶段指令尝试
`git fetch origin`，因 GitHub HTTPS 连接重置失败；不执行 checkout/pull，工作区保持原状。
实时远端 HEAD 与 CI 状态未核验。只对本次两处文档修改运行 whitespace 检查，未跑全量
测试（无代码变更）。
# 2026-09-28 — bounded CNINFO snapshot successor v7

三家公司完成 2026-09-28 的单日 CNINFO 精确发行人查询。美的返回一条已知公告
`1225582141`，伊利与神华均返回零条。index、scan receipt 和 raw response 均由
`config/prospective-public-event-watermarks-v7.json` 按 SHA-256 绑定；新增
`tests/test_prospective_event_watermarks_v7.py` 锁定其单日范围、结果数与 v6 追加关系。
v7 配置 SHA-256：`e4f2c802b1651797e27ff31d3fb83bf08a2ba6e256ba5b9a26cbeaba2309f966`。
这些是检索时点快照，不是全天完整性、多渠道覆盖或严格同期 PIT 证明。正式水位和覆盖状态
未推进，Excel 内容没有变化，未重发工作簿；`action=no_order`。

## 2026-09-28 bounded Track B research supplements

The following source reviews clarify existing registered cases without
rewriting the baseline snapshot, admitting supplemental facts as valuation
inputs, or changing the canonical workbook. Local process-clock time is not
independently attested; these reviews do not establish strict contemporaneous
PIT.

- Midea's baseline card now explicitly distinguishes the registered FCFF
  candidate from its applicability to the current consolidated reporting
  boundary. Direct consolidated FCFF is not applicable until industrial and
  finance-business scope, cash/debt, tax, working capital, invested capital,
  and enterprise-value-to-common-equity are supportably bridged. This does not
  select an alternative model or make the overall valuation ready.
- Yili's 2026H1 liquidity memo is a post-cutoff research supplement, not a
  baseline rewrite. It binds CNINFO interim report `1225511409` to SHA-256
  `423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2` and
  records that short-term borrowings rose CNY 19.0466bn, including CNY
  11.5264bn of additional bill-discount financing (about 60.5% of that
  increase). Cash and deposits also shifted across distinct categories; the
  evidence does not support netting deposits against debt or concluding that
  liquidity risk is resolved. Memo SHA-256:
  `158c5a103085835aa7d0738d9bf7305e49c883f03a2abc07da34f01532de24c9`.
  `MODEL_NOT_READY`, dividend `DATA_INCOMPLETE / UNKNOWN`, and
  `action=no_order` remain unchanged.
- The Shenhua card now states that a 2014-2025 operational-observation package
  already exists, while remaining unapproved as model input. Its twelve-year
  span is not a comparable normalized earnings or owner-cash-flow series;
  remaining work is to classify definition, scope, source timing and bridges,
  not to recollect the same series. Updated memo SHA-256:
  `07b96581ef8ff174b3c114ef1f2a43f19b79da2d3b1dbcac194ca0074ed39d39`.

These supplements do not change baseline snapshot v13, observation ledgers,
event watermarks, valuation or dividend readiness, quote coverage, M6/M7
  gates, or the published Excel. All cases remain research-only and
  `action=no_order`.

## 2026-09-28 product and Track B R1 closeout

The canonical WPS workbook remains at its original WPS cloud path. The final
publication receipt is
`runtime/publication-receipts/canonical-m7-product-publication-20260927T224321Z.json`;
its workbook SHA-256 is
`b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`. The
read-only WPS receipt and readability receipt bind this same hash. All six
product pages, including the secondary audit page, passed the layout audit;
WPS confirmed the evidence column explicitly labels
`最早可用时间（PIT保守口径）`, with announcement date 2026-09-28 and conservative
PIT availability date 2026-09-29. These checks are engineering verification,
not final user acceptance. `action=no_order`.

The first publication attempt after adding the baseline facts was not accepted
because that snapshot was omitted; it was reissued with snapshot v13 and then
verified. Two subsequent layout passes made the audit-page evidence-group rows
and date header explicit-height. The final workbook preserves retained user
managed sheets and is the single canonical workbook.

Track B supplements:

- Midea related-party bridge: five large parent-only subsidiary receivables
  were matched to parent-only statement-note rows; the independent review
  recomputed the CNY 26.969211bn FY2025 and CNY 31.153725bn 2026H1 totals and
  confirmed cited PDF hashes/pages. Individual consolidation eliminations and
  bank-product schedules remain unreconciled. See
  `docs/current/track-b-midea-related-party-bridge-review-20260928.md`.
- Shenhua operating-series classification: 2014-2025 data remain period facts,
  not normalized model inputs. Independent review corrected the acquired
  entity name to Hangjin Energy (杭锦能源) and required explicit comparative
  report citations for later-disclosed self-produced coal sales; the local
  review added those physical page references and hashes. Field-level
  restatement and segment/consolidation bridges remain open. See
  `docs/current/track-b-shenhua-operating-series-classification-20260928.md`.
- Midea model-status wording distinguishes current FCFF candidate applicability,
  industrial carve-out applicability pending scope bridges, and overall
  `MODEL_NOT_READY`; independent review found no substantive contradiction.

`SAFE_R0_REMAINING=0` applies only after the current product repairs, final
WPS/readability checks and pointer/registry rebuild. `SAFE_R1_REMAINING` is
still open for Shenhua restatement/scope bridging. Midea parent-only matching
is complete for retained public evidence; exact internal elimination and
bank-product reconciliation are unavailable external evidence. Strict PIT remains `NOT_PROVEN`, all
three prospective cases remain valuation-not-ready, M6 remains not started,
M7 final user acceptance remains not passed, Initial Assisted Use is not
reached, and `action=no_order`.

## 2026-09-28 continuous public-research run status

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = NO; current cards remain BASELINE_PARTIAL
NEW_EVENTS_PROCESSED = 0
LATEST_VERIFIED_SESSION = 2026-09-24
CANONICAL_UPDATED = false
M4_R2 = PARKED_NONBLOCKING
M6_R3 = PARKED / NOT_STARTED
M7_R5 = NOT_PASSED
TOTAL_GOAL_STATUS = IN_PROGRESS
action = no_order
```

The retained SSE/SZSE calendar evidence records 2026-09-25 as closed; 2026-09-26
and 2026-09-27 were non-trading days. At the 2026-09-28 morning cutoff, that
day's close did not yet exist. No duplicate quote run was performed. The
latest quote evidence therefore remains 2026-09-24, with partial coverage and
`600887` missing from the canonical workbook.

At this earlier v7 checkpoint, the latest retained CNINFO observation was its bounded
2026-09-28 single-day snapshot. It returned the already-known Midea
shareholders' meeting notice and no Yili/Shenhua rows. This does not establish
full-day or multi-channel completeness and did not advance the formal
watermark. No new event was admitted or projected.

An adversarial review found that quote monotonicity previously compared only
the configuration date and could miss a newer successful publication receipt
if that pointer lagged. The publisher now compares the candidate against the
configuration floor and quote dates from successful publication receipts
bound to the current canonical workbook SHA-256; it also validates the
referenced receipt and recognizes hash-bound recovery receipts. No regression
was observed in the current state: the workbook and pointer still match
SHA-256 `b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`.
Focused publisher, preservation and raw quote-binding tests: `23 passed`.
The canonical WPS workbook was not opened for writing or republished.

SAFE_R0_REMAINING=0 for this repaired quote-publication gate. Safe public
research remains available: complete the Shenhua 2023-2025 restatement and
segment/consolidation bridges from retained filings; continue Yili's ordinary
dividend and cash-coverage analysis without treating lifecycle receipts as
proof of sustainability; and process later official disclosures or completed
sessions only when their evidence becomes available. These R1/R6 nodes do not
block one another or the Goal. Strict PIT remains `NOT_PROVEN`; all three
valuation states remain not ready; no baseline was rewritten; M6 is not
started; final M7 acceptance and Initial Assisted Use remain unreached.

## 2026-09-28 prospective-workbench continuation

User-directed focus is now the single canonical Excel, forward research for
000333 / 600887 / 601088, real event observations, financial-quality blockers,
and strict contemporaneous PIT. Do not expand the universe or create parallel
Excel products. Preserve old receipts and historical workbooks unless a
content/hash/reference-aware relocation verifier clears a specific move.

### Public event observation and continuity

One later exact-issuer CNINFO snapshot per registered company was captured for
2026-09-28. Each response was HTTP 200, one page, exact issuer, and terminal
`hasMore=false`; each current raw-page SHA-256 matches its index. Results:

- 000333 at local process time 10:00:41 +08: known notice `1225582141` only;
  index `runtime/prospective-public-event-2026-09-28/gapfill-000333-20260928T020040966184Z/index.json`
  SHA-256 `7fddbe9ea30ddfa2d7113debad410ae8d4f2618fc105d18f011431a29f874890`;
  receipt SHA-256 `6e305597c2604c32a980b72178584ac13b3d3acabd33eccbed68172b71ba484f`.
- 600887 at local process time 10:01:33 +08: zero rows;
  index `runtime/prospective-public-event-2026-09-28/gapfill-600887-20260928T020132411066Z/index.json`
  SHA-256 `39db16b37b92e136b425c7aa49ced860385e19013533fc6fea384ea77dc08e7b`;
  receipt SHA-256 `1964967233fd4f8c3dbf5168902874f0b35539049e9d2caaa1d009548412d0d7`.
- 601088 at local process time 10:02:00 +08: zero rows;
  index `runtime/prospective-public-event-2026-09-28/gapfill-601088-20260928T020200717747Z/index.json`
  SHA-256 `32a4a0f6f6e5da59443ca729f21e6eba5e8fd027fa3729ac7617733dca0225dc`;
  receipt SHA-256 `53de05fdbe327ed9d98334f42817517be3074dc286c70b1a35f54ef3b9f05d53`.

These are later retrieval snapshots, not new company facts. Their timestamps
are local process-clock values with no independent attestation; the snapshots
do not prove full-day completeness, later postings, other channels, or strict
PIT. No event projection, baseline, valuation, decision, or Excel was changed.

At this v7 checkpoint, the retained date-window indexes supported bounded CNINFO coverage through
2026-09-27: 000333 from 2026-03-31 using adjacent 03-31..08-28 and
08-29..09-27 windows, while its initial formal watermark stayed `INCOMPLETE`
because the initial boundary is not tied to a verified query receipt; 600887
from 2026-09-23..09-27; and 601088 from 2026-03-31..09-27 using seven
adjacent/overlapping intervals. For 601088 all seven raw-page hash bindings
and terminal pagination states were rechecked. This corrects the older
gap-fill memo's remaining-date-gaps statement, while the v7 601088 `COMPLETE`
status is limited to its specified CNINFO window chain. All three exclude issuer IR,
exchange-site, correction and later same-day coverage. See
`docs/current/track-c-prospective-watermark-continuity-corrigendum-20260928.md`.

The v2 registration plan declares an observation start of 2026-09-27 08:45
+08, but its registration receipt uses the local process clock. That cannot
anchor strict PIT. `M3=PARTIAL`, `STRICT_PIT=NOT_PROVEN`; no caller-entered
timestamp or later retrieval time upgrades it.

### Shenhua financial-quality bridge

An independent read-only R1 review checked FY2023/FY2024 original and FY2025
comparative report values, their stated page references, volume subtotals and
the FY2024 consolidated profit bridge. FY2023 coal sales volumes reconcile
450.0 Mt original and 454.6 Mt restated, each equal to self-produced plus
purchased coal sales. FY2024 volumes reconcile 459.3 Mt original and 460.2 Mt
restated. FY2024 restated parent profit of CNY 55,805m and NCI profit of
CNY 10,194m sum to restated net profit of CNY 65,999m. No acquired-entity-only
bridge was disclosed.

Corrections are in
`docs/current/track-b-shenhua-operating-series-corrigendum-20260928.md`; the
two source memos and admitted baseline were not rewritten. The FY2025 segment
note is PDF physical p.279 / printed p.278; the FY2024 restated blended coal
price citation is physical p.30 / printed p.29, not p.31. Segment/product
revenue and cost residuals of CNY 8,086m / CNY 4,923m and the 4.5 Mt internal
coal-sales/consumption difference remain unexplained by the retained report.
These facts keep `ACQUISITION_PERIMETER_BRIDGE_INCOMPLETE`,
`SEGMENT_TO_CONSOLIDATED_BRIDGE_INCOMPLETE`, `NORMALIZED_EARNINGS_NOT_ESTABLISHED`,
and `NORMALIZED_FCF_NOT_READY`; 601088 stays `CYCLICAL_MODEL_NOT_READY` and
`VALUATION_NOT_READY`. The legacy FY2025 baseline candidate's 2026-03-30
midnight `available_at` was not changed; the admitted v13 uses conservative
CNINFO next-day availability pending consumer-chain verification.

### Canonical workbook and repository artifacts

Canonical WPS workbook remains SHA-256
`b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`;
there was no publication and no new Excel file. A read-only root-artifact
audit found 29 root-level `.xlsx` files: the repository reference snapshot
plus 28 historical candidates. All have live references; the relocation
auditor has no content-addressed verifier that clears any move. No file was
moved or deleted. The current v2 registry is an untracked working-tree result,
not yet a committed governance baseline; the one untracked M3 addon also has
a manifest reference and is not a safe exception.

M2 remains done / Checkpoint A human pass; M3 partial; M4 non-personalized
engineering done and personalized use parked on R2; all three prospective
valuation states remain not ready; M6 operational work has not started and
production authorization is not granted; M7 final user acceptance has not
passed; Initial Assisted Use remains unreached; `action=no_order`.

### 2026-09-28 watermark successor validation (v8)

`config/prospective-public-event-watermarks-v8.json` is the current successor.
It preserves all four v7 watermark objects unchanged and adds a separate
000333 CNINFO date-chain record. The adjacent complete windows span
2026-03-31..2026-08-28 and 2026-08-29..2026-09-27, with 106 unique
announcement IDs and complete pagination. The query-window evidence is
verified, but formal `coverage_status` remains `INCOMPLETE`: the retrospective
windows do not bind the initial prospective registration boundary to an exact
query receipt. The record's `coverage_through` is the time of the query that
ended on 2026-09-27; its `retrieved_at` is the latest retrieval among the two
referenced indexes and is later than that boundary. Both remain unattested
local process-clock evidence, not trusted PIT anchors.

The manifest separately binds 2026-09-28 10:00:41 / 10:01:33 / 10:02:00 +08
snapshots for 000333 / 600887 / 601088 with counts 1 / 0 / 0. The Midea result
is only the known notice `1225582141`. All three remain
`SINGLE_DAY_SNAPSHOT_ONLY`, with `strict_pit_admissible=false`; no full-day or
multi-channel completeness is claimed. No event projection, valuation,
decision state or canonical workbook changed, and no Excel was published.

The initial v8 focused test found that historical retrieval timestamps had
been timezone-normalized in the successor. The source v7 values are now
preserved, and the test checks manifest-to-index, receipt, and raw-page
identity/query/pagination bindings plus timestamp ordering. The v8 manifest
SHA-256 is `f1d13559580333165c48ecee52db22b96a040cd3af214cce64e3cd19cd1c78d4`.
The focused event scan, manifest, and v5-v8 successor suite passed: `48 passed`.
Canonical workbook preservation, product Excel/read-model, privacy, navigation,
and event-projection gates passed: `66 passed` with two existing openpyxl
named-range deprecation warnings. A full local suite run reached 87% but was
interrupted after sustained high CPU and no test output; no full-suite pass is
claimed. The remote fetch was unavailable, so no CI result is claimed for this
uncommitted worktree. The local `Core Research Gates` offline-core file list
from `.github/workflows/core-research-gates.yml` then passed: `1109 passed,
23 skipped`, with only the same two existing openpyxl named-range warnings.

## 2026-09-28 PIT chronology and artifact-governance correction

An independent adversarial review found a real time-order defect in the
prospective observation path. CNINFO supplies a date-level announcement
marker; the conservative availability rule sets `available_at` to midnight
on the next China-local day. For Midea notice `1225582141`, the retained
record says `observed_at=2026-09-28T01:36:33+08:00` but
`source_available_at=2026-09-29T00:00:00+08:00`. The prior reader checked both
against a later evaluation cutoff but did not require source availability to
precede observation, so the invalid record could have become visible on or
after 2026-09-29.

The writer now refuses a date-only source unless the conservative availability
boundary precedes both the scan response and review time. The reader admits a
record only when `source_available_at <= observed_at`; v2 records must also
have `observed_at <= record_created_at`. This chronology guard is separate
from the existing process-clock trust limitation. The old Midea observation
bytes and hash were preserved, but this record is never selected at a later
cutoff. Regression coverage verifies both the writer rejection and the
verified-ledger exclusion. Focused observation tests: `19 passed`;
observation, Midea event projection, canonical M5 binding and product-candidate
tests: `46 passed`. No ResearchCase, baseline, watermark, valuation or workbook
was changed. `STRICT_PIT=NOT_PROVEN` remains the truthful status.

The v2 registration's `receipt_created_at` is a local process-clock value and
`declared_time_independently_proven=false`. Baseline snapshot v13 was built
after its declared 2026-09-27 08:45 cutoff (local metadata records 17:22 +08);
source availability before a cutoff alone does not prove that the system had
captured and used those inputs contemporaneously. No later TSA result can
retroactively authenticate this registration. A future strict chain needs a
new forward-only anchor binding the exact rules, baseline inputs and code
revision before a subsequent verified source observation and decision review.

A Sectigo RFC 3161 endpoint feasibility probe returned HTTP 200, matched the
requested SHA-256 imprint, verified the CMS signature and built a certificate
chain to the local trust store. Revocation was not checked and the response
was not retained, so this probe is not an admitted time receipt and does not
upgrade the current registration. It only identifies a possible route for a
fresh forward-only anchor.

An independent read-only watermark audit found no date gaps inside the retained
CNINFO windows: 000333 spans 2026-03-31..09-27 but formal status remains
`INCOMPLETE` because its initial boundary lacks an exact bound query receipt;
600887 is `COMPLETE` only for 09-23..09-27; 601088 is complete only within its
specified 03-31..09-27 CNINFO chain. Earlier coverage, issuer IR, exchange
channels, corrections and later 09-28 postings are outside these bounded
claims. No historical windows were rescanned.

The root workbook audit found 29 `.xlsx` files: one repository reference
snapshot and 28 historical candidates. All 29 have path/hash references in
tracked text; 27 candidates are tracked and one M3 add-on is ignored/untracked.
No candidate passed a content-addressed relocation proof, so none was moved
or deleted. The current relocation auditor searches path names rather than
proving all hash/receipt references and labels the repository snapshot as
canonical by filename, although the actual WPS workbook is external under
`WORKBOOK_PATH`. The canonical workbook remains SHA-256
`b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`; no new
Excel was created and no publication occurred.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3
WAITING_FOR_PUBLIC_EVIDENCE = Midea notice outcome; future official events and completed market sessions
NEW_EVENTS_PROCESSED = 0
LATEST_VERIFIED_SESSION = 2026-09-24 / PARTIAL / MISSING_600887
CANONICAL_UPDATED = false
SAFE_PUBLIC_RESEARCH_REMAINING = Yili ordinary/special classification and normalized distributable cash; Shenhua product/segment and acquisition-perimeter bridges; forward-only TSA-chain verifier
M4_R2 = PARKED_NONBLOCKING
M6_R3 = PARKED / NOT_STARTED
M7_R5 = NOT_PASSED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 public-event as-of cutoff correction

An independent read-only review found that the v3 projection displayed Midea
notice `1225582141` as a visible event even though its conservative,
date-only `available_at` is 2026-09-29 and the bounded observation is dated
2026-09-28. The original v3 projection and source evidence were not changed.

The application now filters public-event evidence by an explicit date cutoff,
removes events and audit decisions that depend on future-available evidence,
and rejects missing availability times or dangling evidence references. The
publisher binds the cutoff from the hash-pinned projection report. A v4
successor was generated under `runtime/` with SHA-256
`404cc518c40f6f7f83a866451eca2ab3957f680f3080585da2c61942d520fa5b`:
8 visible event cards, 10 audit-evidence rows and 8 audit decisions. It records
one exclusion (`cninfo-1225582141`, available 2026-09-29) and keeps
`strict_pit_proven=false`, `valuation_or_trade_conclusion_changed=false`, and
`action=no_order`.

The full affected product, publication, protection and event-projection test
selection passed: 115 passed, 2 existing openpyxl named-range deprecation
warnings. The 18-source Yili lifecycle manifest and 18 extracted-text files
were also independently rehashed: 36/36 matched. The current canonical workbook
was not updated. A `--verify-only` attempt exited at the pre-existing WPS open
workbook lock (`CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK`) before
candidate generation or staging; no lock was bypassed, and no backup, staging
workbook, publication receipt, or pointer update was created. The pointer
therefore remains bound to v3 and the saved workbook has not been verified
against this correction in this run.

```text
M5_V3_ASOF_DISPLAY_DEFECT = FOUND / FUTURE_AVAILABLE_NOTICE
M5_ASOF_GUARD = IMPLEMENTED / 115_RELATED_TESTS_PASS
M5_ASOF_SUCCESSOR = runtime/prospective-public-event-20260928/registered-public-event-projection-v4.json / 404cc518c40f6f7f83a866451eca2ab3957f680f3080585da2c61942d520fa5b
M5_ASOF_SUCCESSOR_STATUS = READY_FOR_PRECHECK / NOT_PUBLISHED
CANONICAL_WORKBOOK_POINTER = UNCHANGED / V3
CANONICAL_WPS_PUBLICATION = BLOCKED_BY_OPEN_WORKBOOK / NO_WRITE_ATTEMPTED
CANONICAL_UPDATED = false
NEW_EXCEL_CREATED = false
STRICT_PIT = NOT_PROVEN
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN
M4_PERSONALIZED = PARKED_WAITING_R2_NONBLOCKING
M5 = THREE_PROSPECTIVE_CASES_NOT_VALUATION_READY
M6_OPERATIONAL = NOT_STARTED / PRODUCTION_AUTHORIZATION_NOT_GRANTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 public-research continuation

The read-only research supplements are recorded in
`docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md` and
`docs/current/track-b-shenhua-operating-series-corrigendum-20260928.md`.
Yili's FY2022-2025 dividend-to-profit ratios are partly quantified, as are
FY2023-2025 consolidated CFO coverage ratios. The figures distinguish fiscal-
year distributions from actual calendar-year payments and exclude buybacks.
Ordinary/special classification, FY2021 evidence, FY2022 CFO, and normalized
distributable cash remain open. The FY2025 final-payment lifecycle has since
been verified by the implementation notice described in the 13:30 update
below. Yili's dividend state remains `DATA_INCOMPLETE / UNKNOWN`; no baseline
or ResearchCase state changed.

For Shenhua, the retained FY2025 CNINFO report hash was verified as
`7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2`. The
segment note is physical PDF page 278, not 279. Coal segment external revenue
is CNY 182,874m, inter-segment revenue CNY 38,358m, and total revenue CNY
221,232m. The CNY 8,086m revenue / CNY 4,923m cost residual compares segment
total with the coal-product table. Aggregate segment revenue and cost
reconcile to consolidated totals, but product/segment, internal coal-volume,
and acquisition-perimeter bridges remain incomplete. No normalized earnings,
valuation, or decision status changed.

An adversarial PIT review found a technically possible forward-only path, but
not a way to authenticate the 2026-09-27 registration retrospectively. A
future chain would need ordered RFC 3161 attestations for (T0) exact rules,
baseline/source closure, code and dependency state, (T1) a subsequent official
source observation, and (T2) the later decision-review bundle; token imprint,
nonce, signer chain, policy and revocation evidence must be retained and
verified. No timestamp token was requested or admitted in this continuation.
`STRICT_PIT=NOT_PROVEN` remains unchanged; this is a safe R1 engineering node,
not a product or total-goal completion.

Verification: prospective observation, event-watermark, M5 binding and
baseline projection tests `48 passed`; the exact offline Core Research Gates
selection `1109 passed, 23 skipped` (two existing openpyxl named-range
deprecation warnings). `git diff --check` passed with existing LF/CRLF notices.
`git fetch origin` succeeded and local `main` and `origin/main` both resolve to
`c9449a4fe8881a0cec9ce2f992622b48693c413a`; the pre-existing dirty worktree
was preserved, with no checkout, pull, commit, or push.

The WPS canonical workbook still hashes to
`b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`, matching
the current pointer. No Excel was created or published. As of 2026-09-28
12:46 +08, today's exchange session had not closed; latest verified quotes
remain 2026-09-24, partial, missing 600887. There were no new admitted events.

```text
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3
NEW_EVENTS_PROCESSED = 0
LATEST_VERIFIED_SESSION = 2026-09-24 / PARTIAL / MISSING_600887
CANONICAL_UPDATED = false
SAFE_PUBLIC_RESEARCH_REMAINING = Yili ordinary/special classification and normalized distributable cash; Shenhua product/segment and acquisition bridges; forward-only timestamp-chain engineering
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN
M4_R2 = PARKED_NONBLOCKING
M5 = THREE PROSPECTIVE CASES NOT VALUATION READY
M6_R3 = PARKED / NOT_STARTED
M7_R5 = NOT_PASSED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 13:30 +08 dividend-evidence correction

The retained CNINFO search response identified Yili's FY2025 final-dividend
implementation notice `1225335436`. The original confirms CNY
5,692,824,600.30, or CNY 0.90 per share, paid on 2026-06-05. Its SHA-256 is
`c8cd69e0a195ec9daa702306a2ba1ebf7cb8b53b1f5cae5d872cd590b0ba3c70`; the
retained issuer-specific search response SHA-256 is
`b327f5070b917c6cad0dbc172136e0f7eb31ac58b6b4257d19cb08f2239968ae`, and
the corrected retrieval receipt SHA-256 is
`7d6209f4344d7bb14f1c5686842c8c7fb92b83d2f780891336c9d45a3917d8f8`.
Conservative `available_at` is 2026-05-30 00:00 +08. Retrieval time remains
local-process evidence and is not independently attested.

This closes only the FY2025 final-payment lifecycle. It does not classify the
dividend as ordinary or special, recover missing FY2021 evidence or FY2022
CFO, or establish normalized distributable cash. The 2026H1 CFO / this payment
ratio is 1.715x and is explicitly a calendar-period comparison, not normalized
dividend coverage. No admitted facts, baseline, ResearchCase, valuation,
decision, product projection, or canonical workbook changed. No Excel was
created or published. `STRICT_PIT=NOT_PROVEN`, Yili dividend sustainability
remains `DATA_INCOMPLETE / UNKNOWN`, and `action=no_order`.

```text
YILI_FY2025_FINAL_PAYMENT = VERIFIED / PAID_2026-06-05 / CNINFO_1225335436
YILI_ORDINARY_SPECIAL_CLASSIFICATION = UNKNOWN
YILI_FY2021_EVIDENCE = MISSING_FROM_RETAINED_CHAIN
YILI_FY2022_CFO = MISSING_FROM_RETAINED_CHAIN
YILI_NORMALIZED_DISTRIBUTABLE_CASH = NOT_ESTABLISHED
YILI_DIVIDEND_SUSTAINABILITY = DATA_INCOMPLETE / UNKNOWN
SAFE_PUBLIC_RESEARCH_REMAINING = Yili_ordinary_special_classification_and_missing_year_cash_history; Shenhua_product_segment_and_acquisition_perimeter_bridges; forward_only_TSA_chain_engineering
CANONICAL_UPDATED = false
NEW_EXCEL_CREATED = false
STRICT_PIT = NOT_PROVEN
M3 = PARTIAL
M4_PERSONALIZED = PARKED_WAITING_R2_NONBLOCKING
M5 = THREE_PROSPECTIVE_CASES_NOT_VALUATION_READY
M6_OPERATIONAL = NOT_STARTED / PRODUCTION_AUTHORIZATION_NOT_GRANTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 13:50 +08 Yili lifecycle evidence and CNINFO paging correction

The 13:30 dividend status above is an earlier snapshot and is superseded for
FY2021-FY2023 evidence by this follow-up. A CNINFO query experiment exposed a
real paging defect in `search_announcement_window`: the endpoint returns at
most 30 rows and, with `pageSize=100`, repeated page 1 even when `pageNum`
changed. The collector now requests no more than 30 rows, advances page
numbers explicitly, checks stable totals and rejects duplicate/missing IDs or
count mismatches. The focused disclosure suite passed `21 passed`; direct
CNINFO queries returned 326/326 and 293/293 unique rows for two historical
locator windows, plus 83/83 for the FY2023 source window. Those transient
search indexes were not retained and are only source locators; all financial
claims below bind directly to retained original CNINFO PDFs and their hashes.
No registered event watermark was advanced.

An independent read-only artifact audit confirms 29 root-level `.xlsx` files:
one repository reference snapshot and 28 historical candidates. All 28
candidates still have path/hash/receipt references; 27 are tracked and one is
untracked. The current registry's name-based reference count omits runtime
semantic references, and the relocation module does not prove hash/receipt
consumers survive a move. No candidate has a safe relocation proof, so none
was moved or deleted. The actual WPS canonical workbook remains bound to the
existing pointer and hash; this turn did not publish it.

An independent PIT adversarial review found no currently admitted strict chain:
registration and capture timestamps remain local-process claims, v13 baseline
was created after its declared cutoff, and the Midea 1225582141 observation
whose available_at follows its observed_at is correctly excluded by current
reader checks. The old Sectigo feasibility probe is not a retained receipt and
did not check revocation. The next safe R1 engineering node is an offline
RFC 3161 verifier/conformance contract covering imprint, nonce, signer chain,
TSA EKU, policy, time validity, revocation, complete input closure and strict
T0<T1<T2 ordering. No TSA token was requested or admitted in this turn.

The updated dividend supplement
`docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md` now
verifies FY2021, FY2022 and FY2023 final-payment lifecycles from notices
`1213499389`, `1216991008` and `1220185740`, respectively. Payment dates are
2022-06-01, 2023-06-13 and 2024-06-05. Annual reports `1213169501`,
`1216664083` and `1219916433` provide parent-attributable profit, consolidated
CFO and long-lived-asset purchase cash lines. Payout ratios are 70.58%, 70.21%
and 73.25%; consolidated-CFO coverage is 2.527x, 2.027x and 2.394x. After
subtracting only the reported long-lived-asset cash purchase line, residual
coverage is 1.440x, 1.023x and 1.484x. These are limited cross-period proxies,
not normalized FCF or proof of distributable cash; FY2022's residual coverage
is narrow. The retained lifecycle documents do not explicitly establish an
ordinary/special classification. The 18-original-file manifest is
`runtime/company-research/m1-dividend-lifecycles/20260928T1347Z/manifest.json`,
SHA-256 `d42cba4297ca8c015adc484c75eec5a046e86ffbc62e6e9c6224f0e4d2afc0bb`.

An independent R1 reviewer recalculated 2026H1 consolidated CFO divided by the
FY2025 final parent dividend: 1.7143x, rounded to 1.714x. The earlier 1.715x
figure is corrected. CNY 1.38/share is now described as the FY2025 annual
total (CNY 0.48 interim plus CNY 0.90 final), not as the final proposal. This
ratio remains descriptive and does not establish normalized sustainability.

No baseline, admitted financial-fact set, ResearchCase, observation ledger,
valuation, decision, product projection or canonical workbook changed. New
historical files were collected under `runtime/`; no Excel was created or
published. The complete discovery-index response was not retained, so it is
not treated as PIT or source-completeness evidence. Quote coverage and event
watermarks are unchanged.

```text
YILI_FY2021_FY2023_PAYMENT_LIFECYCLES = VERIFIED / OFFICIAL_IMPLEMENTATION_NOTICES
YILI_FY2021_FY2023_CFO_AND_ASSET_PURCHASES = VERIFIED / ANNUAL_REPORTS
YILI_DIVIDEND_PAYOUT = FY2021_70.58%; FY2022_70.21%; FY2023_73.25%
YILI_CFO_COVERAGE = FY2021_2.527x; FY2022_2.027x; FY2023_2.394x
YILI_POST_ASSET_PURCHASE_COVERAGE = FY2021_1.440x; FY2022_1.023x; FY2023_1.484x
YILI_ORDINARY_SPECIAL_CLASSIFICATION = UNKNOWN
YILI_NORMALIZED_DISTRIBUTABLE_CASH = NOT_ESTABLISHED
YILI_DIVIDEND_SUSTAINABILITY = DATA_INCOMPLETE / UNKNOWN
CNINFO_PAGE_SIZE_BUG = FIXED / 21_DISCLOSURE_TESTS_PASSED
CANONICAL_UPDATED = false
NEW_EXCEL_CREATED = false
STRICT_PIT = NOT_PROVEN
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN
M4_PERSONALIZED = PARKED_WAITING_R2_NONBLOCKING
M5 = THREE_PROSPECTIVE_CASES_NOT_VALUATION_READY
M6_OPERATIONAL = NOT_STARTED / PRODUCTION_AUTHORIZATION_NOT_GRANTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 Canonical As-Of Publication

After the user confirmed the WPS workbook was released, the v4 as-of correction
was published in place. WPS verification then exposed a conflict with the old
verifier: it expected the future-available Midea notice on the workbook audit
page. An independent PIT review correctly identified that even an "audit-only"
copy in the same 2026-09-28 workbook could expose post-cutoff information to a
user. That interim workbook was superseded and backed up; no trade decision was
made from it.

The append-only v5 projection
`runtime/prospective-public-event-20260928/registered-public-event-projection-v5.json`
has SHA-256
`5e543f50690a71254a97ff5c39136cd2bb74d81d1e3c4d3600f023dc948487d6`. It
binds the v4 exclusion to the exact v3 source-evidence predecessor and original
PDF while keeping the item outside active `events`, `audit_evidence` and
`audit_decisions`. The canonical Excel does not display the excluded ID, event
ID, title, path or source hash on any of its six visible product sheets. The
WPS receipt independently verifies the v5 projection hash, source PDF hash,
exclusion availability date, and absence from all six visible sheets.

The existing canonical WPS workbook was updated in place, with its prior bytes
preserved in
`runtime/workbook-backups/canonical-before-m7-product-ux-20260928T074028Z.xlsx`
(backup SHA-256 equals the prior canonical hash
`f4db82e32e5b4786b918f8ce073653e14fe74a1cda400d9ef93a8576192da3e4`). Final
workbook SHA-256 is
`02a5f594c50a402858ddaed5b3520bafd396be1442114add7ae51df011698b47`.
Publication receipt SHA-256 is
`8c6d141fdfb9becfad4ed1dce38f6dae4588320834437c2050ebb53d23ff20f0`.
Read-only WPS verification passed with receipt
`runtime/publication-receipts/wps-m7-product-asof-v5-clean-20260928.json`
(SHA-256 `b666294ba79dcaa412b837cca6e2ad1ea138e16a23b0dae627a3f0287ed0c51a`).
All-page readability passed with receipt
`runtime/publication-receipts/readability-m7-product-asof-v5-clean-20260928.json`
(SHA-256 `4ab4d588fbc22a6d0f31f35863e33c19a177a2e1e2395ebac74170b88f9b807e`).
The current pointer binds these final artifacts. The failed newer quote collection
for 2026-09-28 was not promoted; publication used the raw-validated dual-source
bundle `20260927T165906887834Z`, with all three closes matched at
`2026-09-24`. The current pointer is therefore `COMPLETE` for those three
symbols at that quote date, not a claim of newer prices.

Focused product/as-of regression: `123 passed`, with two existing openpyxl
named-range deprecation warnings. The v5 correction does not prove strict PIT:
the observation clock remains unattested. M3 remains partial, all three
valuations remain not ready, M6 operations remain not started, and M7 final
user acceptance remains not passed. The publication is a product engineering
update only; `action=no_order` and total Goal status remains in progress.

```text
CANONICAL_UPDATED = true / SAME_WPS_PATH / V5_ASOF_VIEW
CANONICAL_WORKBOOK_SHA256 = 02a5f594c50a402858ddaed5b3520bafd396be1442114add7ae51df011698b47
LATEST_VERIFIED_SESSION = 2026-09-24 / COMPLETE / 000333_600887_601088
M5_ASOF_EXCLUSION = FUTURE_NOTICE_OUTSIDE_ACTIVE_PROJECTION_AND_ALL_VISIBLE_EXCEL_PAGES
WPS_READONLY = PASS
PRODUCT_READABILITY = PASS
STRICT_PIT = NOT_PROVEN
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN
M5 = THREE_PROSPECTIVE_CASES_NOT_VALUATION_READY
M6_OPERATIONAL = NOT_STARTED / PRODUCTION_AUTHORIZATION_NOT_GRANTED
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-29 Execution-Correction Review and Historical Handoff (Superseded)

This is a point-in-time handoff from before the shared-model binding and
Shenhua bounded-review closeout recorded near the top of this file. Its open
actions are historical and are not the current task queue.

The execution-correction research package has classified blockers for all
three registered cases. Yili `600887` has zero current A blockers and a
low-confidence `CONDITIONAL_VALUATION_READY` residual-income scenario set;
Midea `000333` and Shenhua `601088` each retain one A blocker. The registered
baseline v13 remains frozen and `BASELINE_COMPLETE=0/3`; this work does not
establish strict PIT, a forecast, fair value, or an investment instruction.

An adversarial review independently recalculated the Yili scenario arithmetic
but found no `ModelValidity` artifact binding the 2026-06-30 valuation basis to
the 2026-09-28 quote after a source-complete event review. The scenario/price
comparison remains arithmetic only. The current Decision Review is therefore
`NOT_ASSESSABLE`; the earlier `WAIT` is withdrawn as a current price decision.
The review JSON and execution-correction memo were corrected accordingly.
The shared-model input/output binding is also still required before product
projection.

The read-only CNINFO event review identified no new Yili event eligible for the
2026-09-29 cutoff. Announcement `1225584526` is date-only and conservatively
available from 2026-09-30; it was not applied early. The query ran after the
review's 13:18 cutoff and was not retained as a receipt, so it does not certify
the exact cutoff or advance a formal watermark. Midea's 2026-09-28 meeting
notice was already in the bounded event projection. The 2026-09-29 session had
not closed at the last review; the latest complete quote remains 2026-09-28.
The retained CNINFO coverage is documented through 2026-09-27 for Yili and
Shenhua; Midea's formal initial watermark remains incomplete. These are
issuer-specific CNINFO states, not complete issuer-IR/exchange-channel proofs.

A read-only integrity check found all 11 source-PDF hashes in the existing
Midea 2014-2024 equity-return candidate series match retained originals. A
simple parent-profit divided by adjacent year-end parent-equity proxy trends
from roughly 25.6%-28.7% in 2015-2019 to about 20.0% in 2024-2025. This is not
issuer-reported weighted ROE, not a forecast, and not an admitted model input;
the Midea A blocker remains. Shenhua's bounded next action is one review of
identified target-level audit/transaction reports, not another broad filing
search.

The physical WPS canonical workbook hash remains
`849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`, matching
the current pointer. It still reflects the prior `VALUATION_NOT_READY` product
view. The approved `@oai/artifact-tool` package is absent from the available
workspace dependencies, so no workbook library substitution, workbook write,
or replacement file was made. Existing WPS/readability receipts only verify
the prior workbook contents.

```text
CURRENT_STAGE = STAGE-CONTINUOUS-PUBLIC-RESEARCH-AND-REAL-INVESTMENT-WORKBENCH
M2 = DONE / CHECKPOINT_A_HUMAN_PASS
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN
M4_PERSONALIZED = PARKED_WAITING_R2_NONBLOCKING
M5_000333 = VALUATION_NOT_READY / A1
M5_600887 = CONDITIONAL_VALUATION_READY / A0 / LOW_CONFIDENCE
M5_600887_PRICE_REVIEW = NOT_ASSESSABLE / MODEL_VALIDITY_NOT_ESTABLISHED
M5_601088 = VALUATION_NOT_READY / A1
M6 = PREFLIGHT_ONLY / OPERATIONAL_NOT_STARTED / REAL_SESSIONS_0
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```
## 2026-09-30 Supported Existing-Read Full Regression and Navigation Reconciliation

- Full workflow-selected offline Core tests after the supported CLI change: 1256 passed, 34 skipped, three existing deprecation warnings in 49.59 seconds. Evidence: `.tmp/existing-command-full-offline-20260930.xml`. This covers the local uncommitted working state, not a new GitHub GREEN or production validation.
- Re-executed the supported `run_company_research.py` existing-manifest mode against the reviewed nine-original manifest without an output path. Returned the actual 600887 conditional scenarios, `EXISTING_RESEARCH_ONLY`, `NOT_READY`, `action=no_order`, with no research rerun or canonical write. Manifest pin remains `032dc2823dcd3e475221e45c8876be1af309b80bcbd8df705b40b33446ebe740`.
- Corrected current CLI navigation: the historical five-page candidate builder is not the current user entry. The sole current workbook remains WORKBOOK_PATH; the seven-page canonical presentation is unchanged. Documented the supported read command and its non-admission/time-observation limits in `scripts/current/README.md`.
- Current model validity, current PriceBridge, strict PIT, personalized portfolio, twenty real sessions, isolated recovery and human acceptance remain unpassed. No investment threshold, evidence-stop scope, server, scheduler or workbook was changed. Continue the single-stock shared research/application path; do not interpret this regression as completed investment research.

## 2026-09-30 Shared Historical Research Gate Connected to Existing-Read Command

- Existing-read Application now verifies the artifact-bound original ResearchCase package and runs shared `evaluate_with_valuation` without inventing an approval. Returns a separately labelled `historical_research_gate`, original research date, package hash and `current_admission=false`. Package hash/issuer/future-date mismatches fail closed before any output is written.
- Real 600887 command output retained at `runtime/real-research-card-flow-20260930/historical-gate-command-result.json`: dated 2026-09-22 case yields G0/G1/G2 true under existing historical contract and G3 false; conclusion valuation not ready. These historical flags are not current financial, business-quality or PIT admission, and old limitations are not reconciled away. Final NOT_READY/no_order, no current quote or portfolio guidance.
- 42 reader/architecture tests passed; `.tmp/historical-gate-reader-20260930.xml`. Four added cases cover historical non-admission and changed package, wrong issuer and future research date. No workbook, thresholds, approval policy, frozen research package or server was changed. Full offline regression from the preceding CLI state is not claimed to cover this subsequent change; updated full CI remains pending.

## 2026-09-30 Historical Gate Assessment Company-Card Projection

- Added a presentation-only projection of the supported Application read's historical gate assessment. Explicit payload hash, symbol, read-only/no_order scope, non-admission and boolean outcomes are required. Displays original date/outcomes/limitations and a current-admission disclaimer; never calls gate evaluation or changes eight current steps, price, valuation, Entry Thesis or action.
- Actual 600887 verification used the existing verified nine-original read model and command output; payload SHA-256 `860ebda0a1a329dacc2b937cf26938fedd9966a3094a15609190001f188a4910`. Three company-card rows projected; original date 2026-09-22, current admission false. No preview/canonical workbook was written. Initial verification incorrectly treated the retained dataclass JSON as the public input payload; corrected the one-off verifier to use the existing read-only typed-model construction, without changing contracts or artifacts.
- Full workflow-selected offline Core run after reader and projector changes: 1265 passed, 34 skipped, three existing deprecation warnings in 56.39s. Evidence `.tmp/historical-gate-product-full-offline-20260930.xml`. Local dirty state only, not remote CI or production admission. Added projector negatives cover changed payload, cross-symbol, current-admission escalation and non-boolean outcomes.
- Canonical presentation remains the previously verified hash `098bcc375eb4d5566054f36396af8d46e6d3b4356b6dd28b371ad345670615e7`. The new historical-assessment rows are not yet published; native readability and protected publication remain necessary. Current model validity, PriceBridge, strict PIT and final assisted-use acceptance remain unpassed.

## 2026-09-30 Canonical Seven-Page Native Review and Opportunity-Surface Gap

- Exported all seven visible canonical product sheets through actual WPS in read-only mode, using each UsedRange and preserving user workbook ownership. Seven PDFs contain ten rendered pages; all have extracted text. Receipt `runtime/canonical-seven-native-20260930/receipt.json` binds per-PDF hashes and unchanged canonical SHA-256 `098bcc375eb4d5566054f36396af8d46e6d3b4356b6dd28b371ad345670615e7`. No save/publication or user acceptance occurred.
- Inspected the ten-page montage and enlarged opportunity page. Navigation/content are nonblank; company spans two pages, audit spans three. Montage inspection is not a cell-by-cell clipping proof and does not pass human comprehension acceptance. Native PDFs/raster previews are verification artifacts only, not competing Excel entrypoints.
- Concrete unmet product requirement: opportunity row currently shows valuation status but omits numerical Bear/Base/Bull, confidence and valuation basis date; it also lacks explicit quote date/price and final suggestion columns. Missing current price must remain unavailable, never populated from an unadmitted quote. Existing scenarios are present in the company card, not sufficient for the goal's one-row comparison requirement.
- Next bounded frontend work: extend the shared OpportunityCard/read-model projection and renderer to expose the already bound scenario values/date/confidence plus explicit unavailable quote and NOT_READY suggestion, validate both surfaces agree, then verify and publish through the retained-sheet-protected canonical path. No financial calculation, new model, changed gate or alternate current workbook is authorized by this UI correction. Historical-gate rows remain unpublished.

## 2026-09-30 Opportunity Comparison Uses the Same Bound Company Assessment

- Opportunity renderer now displays the bound company valuation assessment (including its scenario values, basis date and confidence), complete price assessment with unavailable reason/reopening evidence, and an explicit current decision-status/reason column. It reads existing typed CompanyCard by symbol, performs no financial or decision calculations and creates no duplicate valuation contract. Where no company exists, the row explicitly says research is not ready.
- Company assessment status supersedes potentially stale opportunity-summary valuation/price labels; current eight-step decisions remain unchanged. Actual verified 600887 in-memory rendering shows 8.05/11.02/13.13, 2026-06-30, low confidence, unavailable current price and NOT_READY. No preview/canonical bytes were written; historical gate assessment rows also verified through the same renderer.
- Focused tests 61 passed. Initial new test incorrectly inherited an available synthetic price; corrected its fixture to explicitly model unavailable current PriceBridge, without changing production gates. Complete offline workflow: 1265 passed, 34 skipped, three existing warnings in 53.56s; `.tmp/opportunity-full-offline-20260930.xml`. These are local dirty-state results, not GitHub GREEN.
- Publication remains pending native readability/preservation verification. Canonical hash and unique WORKBOOK_PATH are unchanged. The revised opportunity row includes a longer multi-line comparison cell; full-size native layout must be inspected before protected publication. No current quote, position or new trade recommendation has been invented.

## 2026-09-30 Updated Opportunity and Historical-Gate Native Preview

- Created an explicitly historical, runtime-only integrated preview through the existing protected renderer: `runtime/opportunity-publication-20260930/canonical-integration-historical-preview.xlsx`, SHA-256 `fd91bd44efa092520568e03d5712c572f5d6fec044d582adb6b53939a25c5d77`. Retained-sheet snapshot checks pass for all 55 non-product sheets; canonical source hash remains unchanged. Proof `runtime/opportunity-publication-20260930/canonical-preservation.json`.
- Actual WPS read-only exports cover all seven preview pages with per-PDF hashes, unchanged preview bytes and visible navigation: `runtime/opportunity-publication-20260930/native-review/receipt.json`. Inspected enlarged opportunity page and company pages 2/3. Scenario/date/confidence and NOT_READY blocker are shown; historical date/outcomes/non-admission disclaimer are readable. No current price or research admission was invented.
- Native print review reveals a presentation issue: adding historical assessment pushes the Bear/Base/Bull block alone onto company PDF page 3. Content is present, but print continuity is not accepted. This is a layout issue, not a valuation change; fix bounded pagination/layout and reverify before publication. The preview is not a current pointer and must not be described as a published user workbook.
- Canonical remains `098bcc375eb4d5566054f36396af8d46e6d3b4356b6dd28b371ad345670615e7`; no backup replacement or publication occurred. Final human acceptance, current PriceBridge, strict PIT and the full goal remain unpassed.

## 2026-10-01 Real Retained Valuation / Pending Bridge Verification

- Executed the shared ModelValidity and PriceBridge contracts against the hash-pinned real 600887 retained valuation, without changing business code or canonical Excel. Receipt: `runtime/official-settlement-lead-20261001/shared-pending-bridge-verification.json`.
- The newly reviewed SCP011 advance payment notice is not complete event-scan coverage or evidence of completed settlement. ModelValidity remains UNKNOWN; the missing admitted quote yields PENDING_EXTERNAL_DATA with null price and margins. The full valuation result hash is unchanged. October 1 is the evaluation boundary, not an invented quote date or trading session.
- 71 focused bridge, existing-result reader, bound-valuation and research-card tests passed; `.tmp/real-pending-bridge-20261001.xml`. This validates fail-closed integration, not strategy effectiveness, strict PIT, current research approval or remote CI.
- Complete workflow-selected offline regression: 1276 passed, 34 skipped, three existing openpyxl deprecation warnings in 48.09 seconds; `.tmp/pending-bridge-full-offline-20261001.xml`. Skipped tests are not acceptance evidence, and this local run does not update GitHub CI.
- Registered evidence stop remains closed. Current decision remains NOT_READY/no_order; no orders, publication, scheduler, server or portfolio changes. Continue eligible single-stock work; do not count this verification as a real shadow trading session or stage completion.

## 2026-10-01 Supported Single-Stock Reader Connects Pending PriceBridge

- The existing supported company command now invokes shared ModelValidity/PriceBridge contracts instead of returning a null bridge. It preserves all valuation values and binds the model identity; missing admitted event scan yields UNKNOWN, and missing quote yields PENDING_EXTERNAL_DATA with null quote date, price and margins. The observation date is not presented as a verified quote or event-check date.
- Actual 600887 command completed with the pinned nine-source manifest and reconstructed arithmetic input: `runtime/official-settlement-lead-20261001/supported-research-pending-bridge.json`. All three arithmetic scenarios still match. Historical research gates remain historical; current admission is false, model_validity remains NOT_ESTABLISHED, strict PIT remains NOT_PROVEN and final state is NOT_READY/no_order.
- 71 focused tests passed, including serialized pending bridge, retained source hash, bound scenarios/model identity, absent portfolio and denied current admission: `.tmp/existing-reader-bridge-20261001.xml`. No source evidence, frozen historical engine, canonical Excel, server or scheduler was modified. Full updated offline regression is pending at this entry's creation.
- Updated complete offline regression finished: 1276 passed, 34 skipped, three existing deprecation warnings in 50.76 seconds; `.tmp/reader-pending-bridge-full-offline-20261001.xml`. Actual supported command output SHA-256: `95ad6fea9408a208b2415688e717be9e05520e2d1451a60c59067495c009d7d3`. Remote CI has not verified these uncommitted changes; no graduation claim.

## 2026-10-01 Pending PriceBridge Reaches Formal Excel Read Model

- Added a presentation-only `company_with_pending_price_bridge` adapter in the existing valuation read-model module. It consumes the shared typed bridge, checks bound company/model/scenarios, exposes pending price/margins and leaves valuation scenarios, original entry thesis and final decision gate untouched. It refuses to replace an available price or a passed price/decision gate.
- Actual supported 600887 reader output was hash-checked and rendered through this adapter into all seven sheets in memory. Bear/Base/Bull remained 8.05/11.02/13.13; the opportunity price column now carries model-validity UNKNOWN and no admitted current price; final NOT_READY/no_order remains unchanged. Receipt: `runtime/official-settlement-lead-20261001/pending-bridge-presentation-verification.json`.
- No workbook file was created and canonical Excel was not changed. The older daily publication CLI still requires a verified quote bundle; this work does not relax that policy or claim a supported no-quote publication command exists. Formalizing that bounded research-only publication integration remains unfinished.
- Initial integration-test failures concerned the existing bridge deserializer signature, available-price fixture, required missing-evidence text and an invalid out-of-order scenario mutation. Corrected fixtures without weakening production contracts. Updated full regression is pending at entry creation.
- Updated complete offline regression finished: 1276 passed, 34 skipped and three existing deprecation warnings in 46.94 seconds; `.tmp/pending-bridge-presentation-full-offline-20261001.xml`. This includes the denied available-price overwrite and passed-gate regression checks. Remote CI, current market admission and user acceptance remain unverified.

## 2026-10-01 Reviewed Research Publication Enters Supported Canonical CLI

- The existing canonical publisher now offers explicitly paired reviewed-research folder/proof-hash arguments. This is a separate research-only path, excluding daily quote/observation inputs; normal daily publishing still requires a verified quote bundle. It reuses protected-sheet/OOXML checks, workbook-lock guard, source-hash concurrency guard, durable backup and atomic replacement.
- Reviewed artifacts stay under runtime, proof hashes/scope and matching WPS/readability hashes are required, and the current canonical source is rechecked. Verify-only writes nothing. Publish emits a durable receipt but still reports pending actual post-publication WPS verification, strict PIT NOT_PROVEN, current PriceBridge NOT_ADMITTED and user acceptance NOT_PASSED.
- 63 targeted tests passed, including 18 combinations of publish/verify-only with changed proof, preview, source, WPS/readability result, preserved manual content, simulation scope and sheet count. Publication orchestration tests use a temporary canonical workbook and substituted file transport; existing Windows atomic transport tests are separate. Receipt: `.tmp/reviewed-research-publication-20261001.xml`.
- No actual canonical publication occurred. Existing dated proof folders are not automatically rebound to a changed source. Supported research-only preview generation and a fresh actual publication review remain unfinished; no current market, research or investment acceptance was granted.
- Updated full workflow-selected offline regression: 1294 passed, 34 skipped, 21 openpyxl deprecation-warning instances from the existing named-range fixture in 52.29 seconds; `.tmp/reviewed-research-full-offline-20261001.xml`. No remote CI or committed-state certification is claimed.
- Actual supported verify-only command against `runtime/opportunity-layout-20260930` and proof SHA-256 `c53dd706bff3ae93995ee66c401655b9ee4aa2447f9d2af5d1c4567f76003dcf` correctly refused the stale source binding: that proof predates the latest canonical publication. Canonical file hash before the read-only attempt was `3ee8d4527f4407f61de8982799e1e6189a1b922b33e9204b48de8c6844e55bae`. This expected rejection is not a successful current publication verification; a fresh reviewed preview/proof is still required.
## 2026-10-01 Shared Research Canonical Publication

- Shared existing-research application output `runtime/shared-existing-workbench-20261001/result.json` (SHA-256 `d8f7581b3380741d113e9d964ee74bb606d675b26d769778cc3d6508a39f29dd`) feeds the generic presentation adapter without rerunning or approving research. Original sources are rehashed; current price remains unavailable, model validity unknown and final recommendation NOT_READY/no_order.
- Actual WPS rendering exposed clipping missed by static readability checks. Increased wrapped-row leading in product-managed sheets, regenerated an immutable integrated preview and inspected all eleven rendered pages across seven product sheets. The failed prior preview retains `visual-review.json` with publication denied. Publisher now rejects an explicitly failed or mismatched visual review; 95 targeted tests passed, including visual-failure and visual-hash refusal in publish and verify-only modes. Full updated offline and remote CI are not yet certified.
- Canonical publication completed through the supported reviewed-research publisher, preserving all 55 non-product sheets and protected OOXML state. Receipt: `runtime/publication-receipts/canonical-reviewed-research-20261001T040159Z-c6896445.json`. Before/backup SHA-256: `719fef5f9af7e6746d9690329ed5b5ddb0140203661d28eb34a29ad39d8269a9`; after: `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`. WORKBOOK_PATH unchanged; sole user workbook unchanged in identity; no competing user entry.
- Post-publication WPS read-only open and all seven native exports completed, file hash unchanged: `runtime/shared-canonical-postpublication-20261001/native-receipt.json`. Pre-publication visual/readability/protection evidence: `runtime/shared-canonical-layout-verified-20261001/`. User's earlier workbook-reading, key-custody and WPS-visibility confirmations remain received, not repeated. This publication does not replace final product acceptance.
- Delivery is engineering/research presentation only. STRICT_PIT=NOT_PROVEN, CURRENT_PRICE_BRIDGE=NOT_ADMITTED, INITIAL_ASSISTED_USE=NOT_REACHED, action=no_order. Existing valuation is dated 2026-06-30 and low-confidence, not a current investment conclusion. Personal portfolio remains disconnected. No server/PTA operation occurred.
- Remaining shared-chain engineering gap: whole-workbook integration currently uses a bounded `.tmp` verification runner; seven-page preview and reviewed canonical publishing have supported CLI entrypoints, but the protected whole-workbook preview generation still needs a reproducible supported orchestration path. Next substantive work should close that path and then inspect real-input historical replay applicability, not repeatedly reopen stopped evidence cases.

## 2026-10-01 Supported Integration and Observed Cutoff Replay

- The previous whole-workbook generation gap is closed: existing supported candidate CLI now offers `--integrate-canonical` with pinned base/research inputs and the sole configured original. Actual command produced `runtime/shared-supported-integration-20261001/` with protection PASS and 55 retained sheets, without another canonical write. Full workflow-selected offline regression: 1318 passed / 34 skipped. Commit `7af6e7ba1d355452e0579d24ee5aee0b7636ed79` pushed through configured proxy; GitHub Core Research Gates run `36813967055` completed SUCCESS. This is engineering evidence, not investment approval.
- Inspected historical alternatives: `m3_historical_research_replay.py` separates retrospective/contemporaneous rules but its existing builder is the old 600519 Median-PE experiment; `daily_simulation_policy.py` and current execution contract remain 600519-scoped; `simulation_state.py` contains legacy fixed 30% entry rules. They were not copied into the new shared path, modified or used to approve 600887/000333/601088.
- New application cutoff replay and thin supported engineering CLI bind the verified shared research workbench and original hashes. They replay observed result availability only, preserving unknown current-price/model/portfolio gates; they do not assert reconstructed-public-information PIT, historical fills or strategy effectiveness. Tests cover earlier-cutoff hiding, exact-boundary visibility, unchanged negative decision, source tampering, overwrite refusal, timezone/order requirements and runtime containment; 70 targeted tests passed. Added tests to offline CI selection and registered the CLI in script inventory.
- Actual 600887 replay at Beijing 2026-09-29 15:00, 2026-09-30 15:00 and 2026-10-01 12:00: first two hide the later-produced workbench, last displays existing low-confidence conditional valuation; all remain NOT_READY/no_order, zero orders/fills. Workbench known-at is 2026-10-01 11:27:11.796057 Beijing, not valuation basis 2026-06-30. October 1 is a cutoff timestamp, not a claimed trading session. JSON/report: `runtime/shared-observation-cutoff-report-20261001/`; Chinese interpretation: `runtime/shared-observation-cutoff-replay-20261001/interpretation.md`. No canonical/server/database/scheduler change this replay turn.
- Full historical execution acceptance remains incomplete. Next missing capability is explicitly dated real facts/assumptions plus an applicable model/decision input chain for a historical interval, separate from observed-workbench replay; no performance or buy/sell claim is made from these negative boundary results.
- Updated full offline run had 1323 passed / 34 skipped and one CLI-registry count mismatch; corrected engineering/total counts to 39/58. Targeted registry plus replay rerun: 12 passed. That run is not reported as a fully green updated suite. Receipt `.tmp/cutoff-replay-full-20261001.xml` retains the actual failure; updated remote CI remains to be checked after commit.

## 2026-10-01 Real Financial Input Reconstruction

- Verified remote Core Research Gates for commit `1e17947af6669edf9b955a77aa6c0024f4426f2c`: run `36815019767`, completed SUCCESS. This certifies the previous observed-result replay, not the following uncommitted work.
- Located retained official CNINFO index for 600887 report `1225511409`, matching secCode and PDF URL. Index SHA-256 `1b2674025780741befbddb0fd4fb5e0ae309f6d8efdbb50a033bd2d8d2a6cc98`; announcement date 2026-08-27. Epoch metadata is treated as DATE_ONLY, not precise intraday publication evidence. Conservative reconstructed availability starts 2026-08-28 00:00 China time.
- Added provider-specific infrastructure adapter and separately scoped application reconstruction, exposed through the existing cutoff replay CLI's paired arithmetic/index path+hash options. Existing source/arithmetic checks are rerun; 600887 equity CNY 53,711,364,981.99 and ordinary shares 6,325,360,667 match the retained residual-income calculations. Original review availability and frozen input artifacts are unchanged. Future ROE/retention/capital-cost assumptions remain pinned retrospective scenarios; historical registration is not claimed.
- Actual command produced `runtime/shared-real-input-reconstruction-20261001/result.json` and `report.md`. At 2026-08-27 15:00 both facts are excluded; from 2026-08-28 00:00 they enter the separately labeled reconstruction. Existing observed-workbench output still is not backdated to those times. No current quote, order, fill, personal position guidance, financial-gate approval or strict PIT admission is produced. This is a real-input reconstruction component, not completed historical execution/backtest acceptance.
- 78 targeted tests passed. Full workflow-selected updated offline suite: 1332 passed / 34 skipped / 28 existing named-range deprecation warnings; `.tmp/reconstructed-input-full-20261001.xml`. Tests include issuer/URL/index mismatch, duplicate/missing announcement, invalid timestamp, date-level conservative boundary, preserving later review time and refusing changed index bytes. Application orchestration unit test substitutes already-reviewed arithmetic; actual command separately reruns the real arithmetic/source chain.
- Canonical workbook, server PTA, database and schedules were untouched. Remaining next dependency is historical ModelValidity/current-to-historical quote linkage and decision/execution orchestration using real admitted inputs, not the legacy Median-PE or 30% rule path. Final readiness remains NOT_REACHED/action=no_order.
# 2026-10-01 历史提议与执行逐笔关联（共享工作树）

历史执行回放新增 `decision_outcomes`，用冻结 decision_id 关联账本 fill / rejected_order / deferred_order_id，区分提议日与成交日；报告新增原提议与执行对照。拒绝之后 pending_order_id 被清空不再导致错误归属。未匹配执行明确为 UNRESOLVED，投资理由保持 NOT_RECONSTRUCTED，不生成或批准新买卖逻辑。

真实冻结 600519 upper-30pct 输入产物：`runtime/execution-proposal-link-20261001/report.md` 与 `result.json`；结果 SHA-256 `bd4592e76c6cebb7303c0dcfce32c6be34e348fdb00a579ccdf945ca3edfb9e3`。重建 journal SHA-256 `4b84cd278b32b1a2d7d81f368524535442f2ed4e6b4e75c28775675cd838d4a9`。相关集成测试 34 项通过。代码仍属含其他会话改动的未提交工作树；不代表 GitHub CI 或生产验收通过。

只扩充历史审计可读报告，不改当前公司、组合与信号，不写 canonical、不改服务器或定时任务。CURRENT_RESEARCH_ADMISSION=NOT_READY；strict_pit_admitted=false；historical_execution_validated=false；performance_claim_allowed=false；action=no_order。完整 Goal 尚未完成。

# 2026-10-01 冻结历史决策解释接入共享研究报告

实际依赖：hash-pinned recipe -> 原 execution input / range config / range journal -> 共享账本机械重建 -> 提议执行关联 -> 冻结决策解释 -> ProductWorkbench 次级历史审计 / Markdown。另一独立路径为公开 facts / workbench / arithmetic -> 条件性估值与披露数字 -> 当前公司研究卡；canonical 发布仍要求唯一 WORKBOOK_PATH、来源重验、备份、保留页与原生视觉验收。历史解释不改变当前研究门禁，也不替代发布或严格 PIT。

本轮新增完整的冻结实验解释包：记录提议日收盘、实验价值端点、日志安全边际、原实验分批预算、执行明细和原买入关联；没有数字时保留未记录，不反推、不新增投资规则。只有已执行 entry 可关联后续退出，拒绝 entry 不视为已持仓。企业 Thesis 一致性为 NOT_ASSESSABLE，缺项包括 EntryThesisSnapshot、当时业务判断、反证和 Thesis Breaker 复核。规则实际登记时间 2026-09-25 原样呈现，不能声称在 2015 年已运行或预注册。

真实输入产物 `runtime/frozen-decision-explanation-20261001/report.md`，结果 SHA-256 `380fc807a6625e6e363c1bf4d1f96d3bfd3502579f561353e0cb33d47a20de25`。共享研究报告 `runtime/frozen-logic-shared-product-20261001/company-card.md`；read-model SHA-256 `477f3da15e9f7f99ea750464b2d550ad764aa840438b8e7ccf2f66097a75102c`。共享输出使用原公开 base、现有估值与财务转录输入，并添加新的历史审计；不是原 Excel 已发布的声明。账本 SHA-256 仍为 `4b84cd278b32b1a2d7d81f368524535442f2ed4e6b4e75c28775675cd838d4a9`，数值和执行规则未改变。

新增解释准入防提升、未执行买入关联保护与 read-model snapshot 往返测试。历史解释文件测试 31 项通过。工作树仍包含其他会话未提交变更；远端 CI 不据此宣称通过。没有修改原 Excel、服务器、定时任务或数据库，action=no_order；当前研究准入 NOT_READY，最终运营验收 NOT_REACHED。

# 2026-10-01 三家公司共享证据停止展示闭环

实际缺口是 current-workbench 入口直接索引调度停止结果中不存在的 current_status/valuation/price_bridge，导致 KeyError，且 --report 原先仅支持 existing-result。现在停止结果显式保留 null、NOT_READY、no_order，并在重验 ledger SHA-256 后绑定该公司的问题、期间、已查材料和原始重开条件。通用报告不运行 build_descriptor、不消耗重开请求、不批准估值/仓位、不重搜同一证据。

同一个 `scripts/current/build_current_workbench.py --symbol ... --report ...` 实际跑通 000333 / 600887 / 601088。产物在 `runtime/shared-three-company-readiness-20261001/<symbol>/result.json` 与 `research-readiness.md`，分别呈现 4 / 2 / 1 项真实台账缺口。来源是现有停止台账，不伪装为本轮新财报数字审查；现有封存研究继续保留，不清空旧估值。

相关集成测试 46 项通过，包括三公司停止展示、禁止再次构建研究输入、禁止将停止结果提升为已准入估值和通用 CLI 边界。工作树未提交，不能据此宣称远端 CI 已绿。未修改原 Excel、数据库、服务器或定时任务；当前研究准入和最终运营验收仍未通过。action=no_order。

# 2026-10-01 研究缺项接入同一公司卡

共享缺项入口进一步接入 ProductWorkbench，而非只产生独立报告。Application 在投影前重验结果 Hash、停止台账 Hash 和该公司所有问题的精确匹配；Presentation 只增加 decision_review 与审计引用，拒绝继承已通过的非估值决策门禁，不改变 scenarios、估值、当前价、decision_process、组合或今日提示。

实际伊利产物 `runtime/research-readiness-product-20261001/company-card.md` 与 `read-model.json`，read-model SHA-256 `6c7d6f8b93df6a9c351d254270e8ef22b0faf102e2215c81bbb7f6b7cb20b29d`。输入为原公开卡、现有来源绑定 workbench、条件性估值解释、财务转录和 600887 停止结果；缺项记录引用当前 ledger 的 `14bed2d1609e5479e1f43a90e01bb314d332000fe988b903a3c8adec9f628330`。其中材料编号只是台账记载，不提升为本轮新财报数字或历史可用时间验证。

同一路径在 000333 / 600887 / 601088 测试中验证，且测试台账漂移失败关闭、原估值与决策/组合保持不变。相关测试 46 项通过。`--research-readiness PATH SHA256` 目前仅允许 read-model-only，与 recipe 输入覆盖互斥；不宣称正式 Excel 已发布。当前工作树仍未提交，远端 CI 未验证，完整 Goal 未完成，action=no_order。
# 2026-10-01 一条配方生成完整单票研究解释

在既有冻结 recipe 上新增可选的同公司 `research_readiness` 绑定；加载时重验结果、当前停止台账及公司身份，不允许不同公司缺项或命令行覆盖。旧 recipe 原件不变。新本地输入 `runtime/integrated-company-recipe-20261001/recipe.json`，SHA-256 `34de72cf922c42749e23a375f41b316582dbf877e9105a0c18b6846bb33490ca`。

实际单命令输出 `runtime/integrated-company-review-20261001/company-card.md`，将公司论点、反证、财务转录、经营现金流变动对账、分红生命周期、公告原件问题、估值假设与价值构成、条件性预期及当前研究缺项放在同一公司卡。read-model SHA-256 `de7c7faccdc3ac5819f16fe9858d402dc9c11c48d6000af4ae26fed47feb5994`。只代表已有来源可重现的解释链，不能替代财务质量、股息可持续性、当前价格与研究准入，action=no_order；原 Excel、服务器、数据库与定时任务未改。
# 2026-10-01 利润与现金流方向研究解释

已在共享单票配方中接入同原件年度利润/经营现金流各自的同比变动，区分正基数、零/负基数、相邻年度和事实口径。只生成研究问题，不计算归母利润与经营现金流的同口径现金转换率，不推定利润质量、自由现金、可持续分红或预测。原件、估值、门禁与仓位不改。

实际伊利输出 `runtime/earnings-cash-company-review-20261001/company-card.md`，read-model SHA-256 `1159efdf7c837b284b090bfe370630149f0aa237026a4ed722e8f5f4c01b1f61`。年报同原件比较数显示：2023→2024 归母利润 -18.94%、经营现金流 +18.86%；2024→2025 归母利润 +36.82%、经营现金流 -34.02%。这些是 2025 年报中的描述性比较，不是 2024 年当时可得数据。仍需营运资本、非经常损益、资金归属及现金债务复核，不能据此宣称 FinancialGate 已完成，action=no_order。
# 2026-10-01 历史回放行情逐行原件核验

共享历史执行回放新增未复权日线 open/close 对应检查：文件 Hash、公司身份、日期、原件行号及数值必须一致；已识别原件缺日期、冲突、复权替代或价格漂移时失败关闭。不支持的格式明确 NOT_ASSESSABLE，不能冒充价格已验证。

实际 `runtime/price-source-execution-replay-20261001/report.md` 对应 600519 的 2674 个交易日与 11 个封存行情文件。result SHA-256 为 `d902e14210374d940f9bc9017a8070a2374ebc1a589449a4581afd1e2fffcc99`；journal SHA-256 保持 `4b84cd278b32b1a2d7d81f368524535442f2ed4e6b4e75c28775675cd838d4a9`，不改变投资规则与账本计算。未验证 high/low、当时可得性、停牌涨跌停、流动性或真实成交；严格 PIT 与执行准入仍未通过，action=no_order。相关历史回放测试 32 项通过；远端 CI 待本次提交验证。原 Excel、服务器、数据库和定时任务未修改。

# 2026-10-01 历史原件接入共享产品来源链

回放结果的 source_bindings 现在包含 execution_input.references 中全部原件，使用唯一 execution_original_NNN 角色；既有五个必需角色继续保留。共享产品入口逐项重验，现有正式发布前置核验会沿同一嵌套 source_bindings 重验，因此不再只保护顶层执行输入 JSON。旧冻结回放仍兼容，不改其历史 bytes 或准入状态。

真实 600519 回放形成 33 个来源绑定（五个顶层文件及 28 个执行原件），result SHA-256 `3c5ec119423feb4086de7628352d7e3eb471d47d8770397c821d20affa8a2efc`。共享产品只读集成实际输出 `runtime/source-complete-product-review-20261001/company-card.md` 与 read-model.json，后者 SHA-256 `e0d232f28386926031b4a486d8dbb7ef5c55c846e38f17adcb819a7c2f007b57`。回放只位于次级历史审计区，不提升当前公司研究/决策。相关测试 32 项通过；canonical_written=false，action=no_order，原表及服务器未改。完整目标与最终运营验收仍未完成。

# 2026-10-01 单公司决策复核过程可读闭环

已核验研究停止台账现在进入现有 CompanyCard 的 research_gate 理由、下一动作和证据引用，状态与 assessment_id 保持不变；其他七步、情景估值、组合与今日提示不改。报告展示八步真实门禁、逐步下一动作及原件入口，并明确研究论点不等于 Entry Thesis，不能自动补写历史买入理由或宣称加减仓一致性已通过。

共享冻结单票 recipe 实际生成 `runtime/integrated-decision-guide-20261001/company-card.md`，包含已有论点、反证、财务与现金变动、股息生命周期、条件估值及两项当前研究缺口。read-model SHA-256 `79d5cc30ad278f717e5e52f9fb7d7d0ec88e592f877cbfc72424b7f0e50c015b`。三公司台账投影与 recipe 相关测试 49 项通过，验证所有门禁状态不变；这不是正式研究评估通过。canonical_written=false，action=no_order；原 Excel、服务器、数据库及定时任务未改。

# 2026-10-01 已登记估值敏感性接入单公司闭环

共享 valuation_drivers 现在从算术输入已绑定的 readiness-review-v2 原件读取原登记网格，核对公司、估值日期、模型版本、权益股数、ROE 路径、留存率与终局 ROE，按原资本成本/增长参数组合调用既有 scenario_value，逐格匹配登记精度。缺格、重复格、原件漂移、算术或身份不一致失败关闭；没有该原件则不制造新网格。

伊利实际 18/18 通过，生成 `runtime/sensitivity-company-review-20261001/company-card.md` 与 read-model.json，后者 SHA-256 `22dd62a74ef9866bea5523498497061e6c0dc1c1232d280e1c48a5bf36ce6828`。产品对比确认 scenarios、decision_process、price、margin_of_safety 和 portfolio 均保持不变。相关测试 57 项通过。敏感性只是既有低置信度分析假设的机械重放，不是概率区间、目标价、预测批准或严格 PIT 证据；action=no_order，canonical_written=false，原 Excel 与服务器未改。

# 2026-10-01 完整公司卡准备为来源核验发布输入

当前配方仍只生成只读研究展示；新增可选 `--publication-input` 在同一共享命令中生成 JSON 交接包，不调用 Excel、WPS、服务器或数据库。Application 递归重验本地原件、嵌套绑定及最终读取后 Hash，复制已有 snapshot，不重算或提升门禁。既有公告恢复原件必须重新经过 event_evidence_audit，包内明确记录原路径、期望 Hash 与恢复路径，不能忽略损坏来源。

实际命令输出 `runtime/source-verified-company-handoff-20261001/company-card.md`、read-model.json 与 publication-input.json；后者 SHA-256 `cc4f3d5c208d22657361d4c69894cd25e76d141224ccb4142a99d9721476f21c`。共 61 个来源绑定，一项经过相同 Hash 原件审计的路径恢复。read-model SHA-256 `cfa6424335abb364652c727742a8b43923ad0024a8e9415bd4907bbcc7201f0b`。定向测试 54 项通过；来源漂移、冲突、越界、非只读范围及覆盖旧交接包均拒绝。

此包是研究数据交接，不是发布批准或最终产品验收。publication_approved=false、strict_pit_admitted=false、current_price_admitted=false、canonical_written=false、action=no_order。本轮再次确认获准 @oai/artifact-tool 包不存在；canonical SHA-256 仍 `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`，不绕用其他库写原表。下一依赖仍是获准表格工具及原表保护/视觉发布流程，而不是再次确认用户已阅读。

# 2026-10-02 共享入口消费来源核验交接包

新增 `--base-publication-input`，必须与 pinned base path/hash、historical-preview、read-model-only 配合，禁止混用研究配方或财务/事件/估值覆盖输入。Application 从原研究 envelope 重新构建完整来源链（含原件恢复审计），精确比较交接包；修改 snapshot、省略来源、伪造批准或后续原件漂移均拒绝。不是只信任交接包自述的已通过状态。

实际旧包经共享入口重建为 `runtime/reverified-company-handoff-20261002/company-card.md` 与 read-model.json，后者 SHA-256 `29b66e5963636e675cb0cf4097c4a0d217d2a355d899adae15287417a0a42d59`。此前真实加载失败暴露 PENDING_EXTERNAL_DATA 的安全边际状态不被解析合同接受；现已支持该等待状态并禁止其 available=true。当前完整公司数值、状态码、门禁、来源引用、组合与今日事项往返保持一致；已有 validator 会规范展示标签及 scenario assessment key，不声称原 snapshot bytes 全同。

相关测试 58 项通过。仅只读报告，不调用 Excel，不改变阈值、估值公式、研究批准、PIT、价格或组合准入；canonical_written=false、action=no_order。获准表格工具及保全/视觉发布仍是下一 Excel 依赖，完整目标与最终运营验收未完成。

# 2026-10-02 Canonical research handoff publication

用户已明确允许现有 openpyxl 发布工具。新增共享交接包到受保护原表预览入口；正式发布前再次核验原始研究与传递来源，拒绝遗漏来源或替换交接内容。中文研究缺项解释及哈希过滤仅影响展示，不改变研究或交易门禁。

CANONICAL_WORKBOOK_SOURCE=WORKBOOK_PATH；CURRENT_TRIAL_POINTER=CANONICAL_WORKBOOK；M7_PRODUCT_UX=INTEGRATED；WORKBOOK_PATH_UNCHANGED=true。唯一原表已发布，不是 runtime 预览成为用户入口。

- before_sha256 / backup_sha256: `74439baa82f9ff9f648cb32858af9d3fab03ade06d4f43b1cbdde15fcdef4582`
- after_sha256: `7e2820a66584169adbe05c232ec232920e71d077e0530853d5189470e98ec10f`
- Publication receipt: `runtime/publication-receipts/canonical-reviewed-research-20261001T234433Z-c29f45a8.json`
- Backup: `runtime/workbook-backups/canonical-before-reviewed-research-20261001T234433Z-c29f45a8.xlsx`
- PRESERVED_SHEETS_CONTENT_CHECK=PASS；55 个非产品工作表，包含高级对象/OOXML 保护检查；PRODUCT_SHEETS_PRESENT=true。
- WPS 预览七页原生导出共 20 个 PDF 页面，可读性与原生文本检查通过；全页联系图及关键长文本图像已核看。证明在 `runtime/canonical-handoff-native-clean-20261002/`。
- WPS_CANONICAL_OPEN=PASS；发布后正式原表以只读方式重开，七页导出与错误/内部术语检查通过，哈希未变。证明：`canonical-native-review/receipt.json`。其中 canonical_written=false 表示验证动作没有写文件，不否认上面的发布动作。
- Latest offline Core: 1481 passed, 32 skipped；`.tmp/handoff-provenance-core.xml`。

工程发布已交付，仍保留 strict_pit=NOT_PROVEN、current_price_bridge=NOT_ADMITTED、M7_FINAL_USER_ACCEPTANCE=NOT_PASSED、INITIAL_ASSISTED_USE=NOT_REACHED、action=no_order。缺项不能由 Excel 可打开或工程测试通过替代；完整长期目标未完成。此版敏感性文字仍含文档来源路径，后续渲染的路径过滤修正已加入代码，不影响数值或当前门禁。

## 2026-10-02 Combined research and execution handoff publication

- CANONICAL_WORKBOOK_SOURCE=WORKBOOK_PATH; WORKBOOK_PATH_UNCHANGED=true; M7_PRODUCT_UX=INTEGRATED; CURRENT_TRIAL_POINTER=CANONICAL_WORKBOOK.
- Publication receipt: `runtime/publication-receipts/canonical-reviewed-research-20261002T000341Z-d283a07a.json`; canonical_written=true.
- before_sha256 / backup_sha256: `7e2820a66584169adbe05c232ec232920e71d077e0530853d5189470e98ec10f`.
- after_sha256: `e2df56be2d16e5a5183a22f979b062140b34a40f16c85498a979c6e131bcc147`.
- Backup: `runtime/workbook-backups/canonical-before-reviewed-research-20261002T000341Z-d283a07a.xlsx`.
- PRODUCT_SHEETS_PRESENT=true; PRESERVED_SHEETS_CONTENT_CHECK=PASS; protected sheets=55; verified publication source bindings=123.
- Protected preview: `runtime/combined-handoff-canonical-preview-20261002/`; readability and native visual review PASS; seven sheets exported to 28 PDF pages and contact sheets inspected.
- WPS_CANONICAL_OPEN=PASS; actual canonical readonly reopening, seven-sheet export and unchanged hash verified by `runtime/combined-handoff-canonical-preview-20261002/canonical-native-review/receipt.json`.
- Combined handoff preserves the primary research snapshot exactly, excluding audit evidence and the added historical replay. Historical 600519 execution is secondary audit only, not current-company research, trading admission or a performance claim.
- Parent recovery bindings are freshly reverified; JSON array originals are supported without weakening hash/scope checks. Targeted tests=20 passed; offline Core=1482 passed, 32 skipped, 38 warnings (`.tmp/combined-handoff-core.xml`).
- strict_pit=NOT_PROVEN; current_price_bridge=NOT_ADMITTED; M7_FINAL_USER_ACCEPTANCE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order. Full goal remains incomplete. GitHub CI for this change is pending until independently observed.

## 2026-10-02 Three-company shared research delivery

实际依赖核对：共享研究 runner 的证据停止项仍有效；单公司交接、条件估值、真实冻结输入历史执行回放及受保护发布链已存在。当前可执行缺口是已登记美的与神华披露事实尚未进入同一用户工作台，而不是再次重跑已停止研究。新增共享 retained_research 投影，仅追加缺失公司，不复制单公司流水线、不新增模型、不重开证据停止项。

实际重新读取两公司官方年报/半年报 PDF，沿用原有列、期间、单位与数值校验，核对 12 项披露事实。保留伊利完整公司卡、原机会卡、历史执行回放、组合、事件和阶段准入不变；加入美的/神华原始 URL、模型适用性缺口、反证及明确重开条件。半年报不年化；归母净利润与合并现金流不混算现金转换；经营现金流不当作 FCFF 或可分红现金。没有新估值或买卖信号。

- Code baseline: `82d0289` (Reuse retained company evidence in the shared research workbench).
- GitHub Core Research Gates: PASS, run `36949012200`, https://github.com/MingMingLiu0112/value-investment/actions/runs/36949012200 . Earlier clock-fixture correction `e6d972b` also passed run `36944577289`; production time gates were not changed.
- Offline Core: 1489 passed, 32 skipped, 38 warnings; `.tmp/retained-three-company-core.xml`. Subsequent display-label/new-packet timestamp corrections: 48 targeted tests passed; final code CI passed. These prove engineering contracts, not investment effectiveness.
- Reproducible entry: `build_product_workbench_candidate.py --base-publication-input --retained-baseline <registered snapshot> <sha256> --research-readiness <000333 result> <sha256> --research-readiness <601088 result> <sha256> --historical-preview --read-model-only`; pinned actual inputs and transitive dependencies are preserved in the handoff.
- Handoff: `runtime/three-company-delivery-handoff-20261002/publication-input.json`, SHA-256 `72729880761e05a1340ab0fb72835488e0d875c17a0a1e0b0efbaad366d3f6d9`; read-model SHA-256 `f9303d1f254097b8d418b7ff35387fdb1d8e4ba1357d5660b46d9d8405734376`.
- Integration receipt: `runtime/three-company-delivery-handoff-20261002/integration-receipt.json`; primary research, historical execution, portfolio/events and stage admission unchanged; 12 report facts rechecked; 131 handoff bindings. Publication adds the handoff binding: 132 freshly verified sources.
- CANONICAL_WORKBOOK_SOURCE=WORKBOOK_PATH; CURRENT_TRIAL_POINTER=CANONICAL_WORKBOOK; M7_PRODUCT_UX=INTEGRATED; WORKBOOK_PATH_UNCHANGED=true; PRODUCT_SHEETS_PRESENT=true.
- before_sha256 / backup_sha256: `e2df56be2d16e5a5183a22f979b062140b34a40f16c85498a979c6e131bcc147`.
- after_sha256: `9925ab6a78e8ed10ae3e10d9ea4180d33d9ea9aefb99665b09e88cc38212566a`.
- Publication receipt: `runtime/publication-receipts/canonical-reviewed-research-20261002T011005Z-6c0e94ea.json`; canonical_written=true.
- Backup: `runtime/workbook-backups/canonical-before-reviewed-research-20261002T011005Z-6c0e94ea.xlsx`.
- PRESERVED_SHEETS_CONTENT_CHECK=PASS; 55 protected sheets including advanced OOXML objects. Preview seven-sheet WPS export: 38 PDF pages, readability/visual checks PASS; all contact sheets and the corrected long-text company page inspected.
- WPS_CANONICAL_OPEN=PASS; actual original workbook readonly reopened, seven sheets exported and hash unchanged. Receipt: `runtime/three-company-delivery-canonical-preview-20261002/canonical-native-review/receipt.json`.

CURRENT_RESEARCH=NOT_READY; strict_pit=NOT_PROVEN; current_price_bridge=NOT_ADMITTED; M7_FINAL_USER_ACCEPTANCE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order. 财报事实核对不是完整 FinancialFacts/研究准入。实际处理时间只更新新包元数据，未改变事实可用时间、行情时点或历史冻结日期。原停止台账及生产门禁均未改；服务器、PTA、数据库、定时任务未改，完整长期目标仍在执行。

## 2026-10-02 Retained distribution input correspondence in real execution replay

本轮从真实共享入口、回放、交接和发布代码恢复依赖；上一轮三公司原表交付是实际进展，不重新验收用户阅读。依赖图当前选择：已冻结决策日志 -> 已绑定执行输入 -> 已审阅分红登记表/公告 -> 共享 VirtualAccount -> 回放报告 -> 共享三公司产品交接；独立于当前行情、研究停止项及私人组合。实际缺口是分红原件只验 Hash，执行字段未与已审阅登记表逐项对应。当前价格/完整事实/假设/事件及严格 PIT 仍各自阻塞正式投资结论，不阻塞此输入核验。

新增 Infrastructure 对应核验登记日、除息日、现金到账日、每股毛现金及分母换算、送股比例与上市日，要求原件 path/hash/URL 与执行引用相同；重复、遗漏、日期/金额/送股漂移、原件变化及读取后变化拒绝。范围仅是既有审阅登记表与输入的对应，不是新 PDF 语义复核，不证明历史完整覆盖或当时可得性。Application 在共享执行回放前调用，Presentation 显示范围及逐项公告链接。没有修改冻结输入、模型、规则、成本或账本算法。

真实命令沿用 `runtime/execution-replay-600519-20261001/input.json`，通过 `scripts/current/build_historical_execution_replay.py --input <path> --input-sha256 <actual hash> --output runtime/distribution-verified-execution-replay-20261002/result.json --journal runtime/distribution-verified-execution-replay-20261002/journal.json --report runtime/distribution-verified-execution-replay-20261002/report.md` 生成不可覆盖产物。

- 15 项分红/送股安排对应 MATCH；2,674 个交易日、4 次冻结成交机械对照仍 MATCH。
- Result SHA-256: `5ffc585e8451b1ad1c4c3195a620d93420a789e0c7f3967a795ef38461509c6a`.
- Journal SHA-256: `4b84cd278b32b1a2d7d81f368524535442f2ed4e6b4e75c28775675cd838d4a9`; byte-identical to previous source-complete replay.
- Readable report SHA-256: `56e8177c64a723b5406f04948fa1ff9a40a932173e1070731ab7288603b8cba8`; report distinguishes entitlement arrangements from actual received cash.
- Shared product integration initially exposed exact retained-source ID reuse failure. Projection now reuses only one fully identical EvidenceRecord; path/hash/metadata differences still fail closed, and old replay remains preserved.
- Shared handoff: `runtime/distribution-replay-product-handoff-20261002/publication-input.json`, SHA-256 `61abcadfe560eb418a5f3f40e5fc771b81060ec0ae801a3b7933100540d42548`; read-model SHA-256 `0d84b87c1d1f0a33027e2d29dca3a0b7b7e5f5bcfb23af646ae0e42ba6498b09`.
- Actual comparison: companies/opportunities/portfolio/events/stage_statuses/today unchanged; only secondary replay/audit evidence appended. No canonical publication this turn; sole workbook remains the previously verified `9925ab6a...` version.
- Offline Core before final identical-source reuse correction: 1503 passed, 32 skipped, 38 warnings; `.tmp/distribution-correspondence-core.xml`. Final targeted replay/product tests: 69 passed. Updated code CI must be observed separately.

ENGINEERING_DELIVERY=DELIVERED; CURRENT_RESEARCH_ADMISSION=NOT_READY; FINAL_OPERATIONAL_ACCEPTANCE=NOT_REACHED; strict_pit_admitted=false; historical_execution_validated=false; performance_claim_allowed=false; tax_treatment_verified=false; action=no_order. No server/PTA/database/scheduler changes. Next unresolved real replay dependency remains a separately frozen complete facts/assumptions/rule/event chain and dated execution constraints, not tuning legacy thresholds or relabeling correspondence as investment validation. Complete goal remains active.

## 2026-10-02 Isolated source-bound refusal runner

Continued user task: generate and consume daily artifacts without production start. Existing audit_m6_start_criteria.py now offers --isolated-run with symbol and source-bound event/optional quote inputs. operations/shadow_daily_run.py executes the shared company scheduler, snapshots input bytes, writes exclusive runtime artifacts and a receipt, then mandatorily calls the daily input content audit. The actual stopped outcome is preserved; downstream model/decision/portfolio nodes explicitly report NOT_RUN_UPSTREAM_BLOCKED, not fabricated execution. An admitted research outcome is currently unsupported and rejected. Full admitted-model DAG and formal production consumption remain CODE_GAP; not ENGINEERING_READY=YES.

Actual 600887 original-event run: runtime/shadow-isolated-refusal-20261002/report.md; manifest SHA-256 6a47994a9c7aafc551018b936e323df90f2534f8805bb9fa22b500879166d26f. Research scheduler returned BLOCKED_BY_RESEARCH_SCHEDULER; input audit SHADOW_INPUT_INCOMPLETE (no same-day post-close quote). Snapshot time does not become publication time; bounded retained event input is not a complete prospective event scan. Refused overwrite and hash drift are tested. Targeted tests 33 passed; full offline Core 1517 passed, 32 skipped, 38 warnings (.tmp/shadow-run-core.xml). Previous b061a59 CI run 36963315758 passed; new revision CI must be separately observed.

No production receipt/signature, session-count increment, timer/server/PTA/database/Excel mutation. position_guidance=null; verified_real_session_count=0; dag_execution_complete=false; action=no_order. This delivers an actual refusal path, not the full Shadow start goal or investment readiness.

## 2026-10-02 Shadow daily input content audit

User explicitly redirected continued work to STAGE_5_SHADOW_START_READINESS. Actual inspection found the signed session verifier binds artifact hashes, but daily artifact content consistency is a separate missing path. Added operations/shadow_daily_input.py and integrated it into the existing audit_m6_start_criteria.py command with paired --daily-input/--daily-input-sha256 and immutable runtime --output. Full-role audits revalidate quote originals through the existing quote converter, same-session cutoffs, event-source hashes, coverage, DAG sequence/run/output bindings and no_order outputs. Partial packets identify missing artifacts rather than pretending complete execution. This is not a session producer or proof that a self-authored receipt actually ran the DAG; remaining producer/mandatory-consumer code gaps are explicit.

Actual bounded dry-run used the previously acquired Yili event original package, not synthetic market prices. runtime/shadow-start-readiness-20261002/audit.json reports SHADOW_INPUT_INCOMPLETE, same-day post-close and missing DAG artifacts, with zero countable sessions. No production operation, counter change, key/signature issuance, model promotion or Excel mutation. The initial future generated_at was refused; corrected to an observed current clock without relabeling it post-close.

Targeted matrix/receipt/quote tests: 32 passed. Offline Core: 1516 passed, 32 skipped, 38 warnings (.tmp/shadow-start-core.xml). Synthetic complete-schema tests prove offline consistency only; still shadow_session_valid=false and verified_real_session_count=0. Detailed dependency report: docs/current/shadow-start-readiness-20261002.md. ENGINEERING_READY=NO; existing M3/M4/M5 hard start gates retained. October 8 is official next market opening, not an admitted start date. Existing 20fde39 GitHub CI passed before this new change; new code CI must be separately observed after push. Complete objective is not achieved.

## 2026-10-02 Independent execution cash reconciliation

Previous timeline code `ffac133` passed GitHub Core run `36955462592`. Inspection of the actual shared company runner, historical decision-input join, replay engine and source-bound canonical chain identified an independent runnable replay gap: frozen-journal equivalence did not independently explain cash movements. Added Domain cash/receivable reconciliation, invoked by the existing historical execution service and rendered by the existing report command. No decision-rule recomputation, thresholds, valuations or frozen source bytes changed.

Actual supported replay used `runtime/execution-replay-600519-20261001/input.json` with its freshly checked hash. Final output is `runtime/cash-reconciled-final-20261002/result.json` (SHA-256 `f0c3eb9c015e80f742e71576b21924ca988b2bc6ba32defe21914581d616f3bf`), journal and readable `report.md`. All 2674 daily cash/receivable balances reconcile; initial cash 1000000.00, buy principal 75660.00, sell principal 150876.00, fees 223.37, gross dividends accrued/paid 1912.90, ending cash 1076905.53, ending receivable 0.00. These are the retained experiment's virtual ledger, not personal income or an approved investment performance claim. Journal SHA-256 remains `4b84cd278b32b1a2d7d81f368524535442f2ed4e6b4e75c28775675cd838d4a9`.

Reconciliation rejects balance drift, duplicate cash-event phases, nonfinite/negative amounts and payment against a different dividend's accrual. Record and bonus-credit events have no cash impact. Tests exercise settlement lag and cross-event mismatch. Targeted replay/product tests 48 passed. Core before final per-event entitlement strengthening: 1515 passed, 32 skipped, 38 warnings (`.tmp/cash-core.xml`); final targeted tests and actual full replay passed. Final code CI is separately observed after push.

ENGINEERING_DELIVERY=DELIVERED; CURRENT_RESEARCH_ADMISSION=NOT_READY; historical_execution_validated=false; strict_pit_admitted=false; performance_claim_allowed=false; tax_treatment_verified=false; action=no_order. Canonical Excel, server/PTA, databases and schedulers unchanged. Remaining historical investment dependency is a complete separately frozen dated facts/assumptions/rules/research-event and execution-constraint chain; cash agreement does not supply that admission. Complete Goal remains active.

## 2026-10-02 Historical decision-input evidence timeline

Actual dependency inspection: the shared company runner applies evidence-stop scheduling before research; retained reconstruction and historical bridge are joined by `replay_workbench_cutoffs.py --decision-input-review`; product packets reach the canonical publisher through source-bound preview/native/preservation verification. New official events explain affected findings but do not supply complete historical facts, frozen assumptions/rules, research/event approvals or next-session execution constraints. These missing inputs remain local research dependencies, not global engineering locks.

The historical decision-input join now retains a readable per-fact evidence timeline (value/unit/period, original physical page/hash, conservative publication availability, actual review time and semantic verification). It checks that eligible facts agree with source evidence and cutoff availability; future or altered facts fail closed. Publication availability, retrospective review and strategy admission remain separate. The retained three-cutoff real 600887 input was exercised through the same Application join and renderer, not simulated facts.

Readable result: `runtime/historical-evidence-timeline-20261002/report.md`; JSON SHA-256 `8ae31ecfadcb2b93cf5a9138b854293b51d88684c538f4fdc373f58083b3c5f5`. Frozen parent input SHA-256 `164121333fa1be330979f23b82e52d6940f4bf9c750781b2e5ba0d414e13651e` is recorded in the output. Evidence timeline includes unavailable inputs only as explicitly unavailable audit context, never as decision inputs.

Targeted tests: 6 passed. Offline Core: 1514 passed, 32 skipped, 38 warnings (`.tmp/timeline-core-fixed.xml`). First Core invocation failed setup because project-local TEMP/TMP were omitted; corrected environment, no trust-boundary waiver. GitHub code CI remains separately observable after push. Existing canonical publication and its verified hash unchanged; no Excel/server/PTA/database/scheduler changes. All decision rows remain NOT_READY, orders/fills empty, position_guidance=null, strict PIT and historical execution unvalidated, action=no_order. Complete Goal remains active.

## 2026-10-02 Source-anchored successor explanation published to canonical

Code `69d1331` adds bounded original-page verification in Application and immutable explanatory projection in Presentation. An initial offline architecture failure was corrected by separating these layers, not weakening tests. Final offline Core: 1513 passed, 32 skipped, 38 warnings (`.tmp/event-followup-corrected-core.xml`); targeted architecture/event tests: 38 passed. GitHub Core run `36954311579` completed SUCCESS for exact code HEAD `69d133101a221592fd28c122d11d598fa6dc5f0a`.

The original WORKBOOK_PATH workbook now includes one new Today pending-review item and Yili source-anchored settlement/guarantee explanations. The historical liquidity-gap text is retained and explicitly labeled as pre-disclosure history. Company-reported settlement is disclosed, not independently bank-verified; post-payment cash/debt/refinancing, guarantee materiality and complete event coverage remain unresolved. Investment values, eight decision gates, other company cards, portfolio and retained historical replay are unchanged. No stop-ledger promotion, orders or server/PTA/database/scheduler changes.

- CANONICAL_WORKBOOK_SOURCE=WORKBOOK_PATH; CURRENT_TRIAL_POINTER=CANONICAL_WORKBOOK; M7_PRODUCT_UX=INTEGRATED; WORKBOOK_PATH_UNCHANGED=true.
- Publication input: `runtime/event-followup-final-20261002/publication-input.json`, SHA-256 `cab20925d952e2a12151465ea159f550a9bb480b06d3de827c04657bf3a2dcf2`.
- Publication receipt: `runtime/publication-receipts/canonical-reviewed-research-20261002T021603Z-083f9416.json`; 141 source bindings freshly verified; 55 preserved sheets PASS.
- before_sha256=backup_sha256=`9925ab6a78e8ed10ae3e10d9ea4180d33d9ea9aefb99665b09e88cc38212566a`.
- after_sha256=`5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`.
- PRODUCT_SHEETS_PRESENT=true; PRESERVED_SHEETS_CONTENT_CHECK=PASS; readability and native visual verification PASS. Native PDF contact sheets and the full new explanation page inspected.
- WPS_CANONICAL_OPEN=PASS: actual canonical readonly reopened with matching hash; `runtime/event-followup-final-canonical-preview-20261002/canonical-native-review/receipt.json`. The verifier's canonical_written=false means the readonly check itself did not write, not that publication was absent.

CURRENT_RESEARCH_ADMISSION=NOT_READY; current_price_bridge=NOT_ADMITTED; strict_pit=NOT_PROVEN; M7_FINAL_USER_ACCEPTANCE=NOT_PASSED; INITIAL_ASSISTED_USE=NOT_REACHED; action=no_order. Goal remains active. This is a real evidence explanation/product delivery, not completion of investment or operational admission.

## 2026-10-02 Shared daily DAG successor (isolated, not production)

Normal-path gap found and implemented: generic company entry previously never
attached typed human research approval or event materiality, so its reviewed
pre-decision branch was unreachable through the supported daily runner. Explicit
hash-pinned research-review packets now attach the existing typed contracts and
exact canonical descriptor case/facts/assumptions, before one-shot reopen
consumption. Review hashes change the input fingerprint; the current event scan
hash must match materiality. Existing rejected approvals and recalculation events
remain rejected/recalculation; no real approval was generated or inferred.
Synthetic typed integration tests cover exact payload binding, preserved rejection,
cross-issuer rejection and wrong-scan rejection. Supported command adds only the
paired research-review path/hash flags; existing admission policy is unchanged.
Current issuer admission, strict PIT, complete day execution and production
adoption remain NOT_PROVEN/NOT_READY. Canonical/server/PTA/database/scheduler
unchanged; action=no_order; full objective remains incomplete.

Cross-role lineage increment: daily consumer now checks shared application quote/
raw-event/package bindings, research-to-model projection equality, typed review/
pre-decision identity/date/status, and product-to-decision consistency. It does
not recalculate or change financial policy. The historical hash-only placeholder
test is no longer accepted as a complete day; mismatched model/product projections
are rejected. Real retained-input output:
`runtime/shadow-existing-risk-dag-20261002/lineage-consumer.json`, NOT_ADMITTED,
zero credit. Missing calculation lineage is expected after actual scheduler refusal;
it is not proof of a corrupted original disclosure or a failed valuation formula.
No current quote, research admission, production scheduler adoption or user
portfolio readiness is inferred. Canonical/server/PTA/database unchanged; no_order.

Failed-path product completion: shared descriptor/run-spec rejection now carries
an explicit known input-validation exception, before any one-shot request is
consumed. The isolated daily runner preserves the failed result, diagnostic,
no-order receipt, skipped downstream stages and readable company card. It does
not swallow unexpected programming errors or alter scope/integrity checks.
Synthetic cutoff-rejection evidence:
`.tmp/shadow-rejection-target/test_daily_attempt_seals_known0/runtime/rejected-input/company-card.md`.
Targeted shared scheduler/daily tests: 45 passed, 1 skipped. This is engineering
failure-path coverage only, not a real input failure, positive research admission
or Shadow session. Actual quotes, complete event windows, private portfolio,
authorization and production adoption remain separate. No Excel/server/PTA/
database/scheduler mutation; no_order; full objective not complete.

Daily consumer handoff: the supported audit command now combines daily contents
with the existing operational admission verifier when explicit pinned proof is
supplied. Exact signed manifest hash/run/day/execution-window checks prevent a
valid signature for unrelated artifacts from granting daily credit. The daily
content/hash checks run again after operational verification. No signature fields,
trust infrastructure, authorization rules, persistent counters or scheduler were
changed. Original 20-session/one-event admission scope remains required.
Actual `runtime/shadow-existing-risk-dag-20261002/formal-consumer.json` is
NOT_ADMITTED with zero credit: existing proof absent and day contents incomplete.
Positive proof intersection is synthetic test coverage, not a real authorization
or session. Production scheduler/intake adoption remains unverified. no_order.

Existing risk-engine integration: daily orchestration accepts explicitly hashed
SIMULATED M4 demo inputs and calls the established portfolio risk assessment. The
original demo date/limits are retained, ACTUAL input is rejected, and no personal
capacity or position guidance is inferred. Joined output:
`runtime/shadow-existing-risk-dag-20261002/company-card.md`; manifest SHA-256
`d1b5cbb9038d3201920f3b4c6c1525e017ff04eba42cd51def0bc46992602d07`.
Actual engine result on the retained demo: VIOLATION for 600519/601088 single-name
exposure and reserved cash. Research remains refused. Executed nodes now include
the independent simulated portfolio risk gate; receipt simulation_only=true and
verified real session count remains zero. No new financial rules, actual holdings,
personal position advice, canonical Excel, database, server/PTA or scheduler change.

Raw-event input integration successor: existing M1 scans now project into the
daily event contract with actual acquisition time, unchanged scan bounds/coverage,
original scan/PDF/index hashes, and an explicit coverage-cutoff basis. No provider
watermark is inferred from a date-only scan or rerun time. Shared research still
uses original M1 bytes. Real output `runtime/shadow-projected-events-20261002/company-card.md`,
manifest SHA-256 `b486dfdf0bf0dfc56ac121e405e35bec07f629b7903a916d1e159f743757e2f4`.
Daily audit now consumes the event projection without missing-format errors, but
retains incomplete event coverage, missing quote, pre-close and incomplete DAG.
This is verified input interoperability, not materiality or research admission.
Canonical Excel, server/PTA, database and scheduler remain untouched; count=0;
action=no_order. The total objective remains uncompleted.

Consumer integration correction: missing quote no longer bypasses content checks
for the rest of the day. Present artifacts receive hash/time/run/session/no-order
and DAG-receipt checks; absent event timestamps are explicit contract gaps. Real
600887 output `runtime/shadow-consumer-checked-20261002/company-card.md`, manifest
SHA-256 `e04f9bc3dc6ab1f929136630ee13d2d872a3d04e6511da133fb5c859b36f1773`.
The existing M1 disclosure scan is not a complete daily prospective wrapper; it
lacks that wrapper's time/coverage/source-binding fields. Original PDF verification
and readable claims remain valid for their limited purpose, not current decision
or Shadow admission. DAG remains incomplete, session count zero, no_order. No
canonical workbook, server/PTA, database or scheduler mutation.

Daily product increment: the isolated runner now produces a presentation-only
company review card from the exact research/model/decision outputs. Optional
source-followup input reuses the existing original-page verifier and must bind
the acquired event scan, same issuer and observed cutoff. Real 600887 output:
`runtime/shadow-readable-company-20261002/company-card.md`; daily manifest SHA-256
`9a5e940e3e1fb753b3b2e2d9a39f392619a574dd58ee9d0916a44a14dd0c2fc0`.
The two October 1 disclosure explanations and their unresolved questions appear
alongside actual research refusal, missing quote, missing valuation and null
position guidance. This is new joined user-readable output, not evidence approval
or a real Shadow session. Canonical Excel, server/PTA and production scheduling
remain unchanged. action=no_order; total objective not complete.

Daily-input calculation integration successor: explicit package runs now pass
snapshotted quote/event references to existing shared descriptor parsers. Declared
validity dates, material events, approvals and research cutoff remain unchanged.
All descriptor/run-spec validation precedes one-shot reopen consumption. Corrected
the receipt reader to the actual `input_sha256` contract; no compatibility field
was added. Actual refused run: `runtime/shadow-daily-input-consumption-20261002/report.md`,
manifest SHA-256 `865018c9840cc16ed955b04d348d1b8ddee03b468348bf503535551576ee9718`.
Allowed forwarding and pre-consumption rejection are synthetic engineering tests.
No real current-model admission or daily Shadow credit is claimed.

Broader targeted exploration found four failing legacy valuation-package-builder
expectations (Huayu/Gree scenario and material-event/probe cases expect conditional
valuation but actual returns not_ready). The builder/calculation contracts were
not changed in this package; these failures remain exposed, not weakened to pass.
The current shared-entry/scheduler/research-service targeted selection passed
45 tests with 1 skipped. Offline Core coverage and legacy assertions are separate.

Successor input integration: the daily runner accepts explicitly hashed research
package and optional schedule request, snapshots them, and forwards to the existing
shared research scheduler. It records snapshot-only versus shared-receipt-bound
inputs rather than claiming every acquired file was used. Actual package-bound
attempt: `runtime/shadow-bound-research-20261002/report.md`, manifest SHA-256
`2d879d046a1d1f9f1f1fda1ea26ee1c2e747267b8225a107b279fd35c0135e6c`.
The real 600887 package remains unconsumed after scheduler refusal; no new request
or approval was fabricated. Missing quote/current-input integration and full DAG
remain open; no production/Excel/server changes, no orders, zero real sessions.

The isolated runner now retains shared research model-validity, PriceBridge and
valuation outputs and uses the existing decision evaluator for same-session typed
pre-decision input, with no inferred buy/add intent. Missing pre-decision remains
NOT_READY. Event issuer identity is checked before creating the output directory.
Actual 600887 attempt: `runtime/shadow-isolated-shared-dag-20261002/report.md`,
manifest SHA-256 `d6caf51b364b32ef339c9ad34e0e9f1b6f318f5091f9118bb60ab68d97130cb0`.
Scheduler refusal persists; actual executed nodes are research and refusal product
projection. Same-day post-close quote and complete DAG remain absent. Normal model
branch coverage is synthetic engineering validation only. SHADOW_START_READINESS
remains PARTIAL, ENGINEERING_READY=NO, verified_real_session_count=0, action=no_order.
No canonical workbook, server/PTA, database, production scheduler or admission
policy changes. This record does not supersede the unresolved evidence conditions.

## 2026-10-02 New official settlement and guarantee evidence

Previous turn was substantive progress; distribution replay code `882cd2d` subsequently passed GitHub Core run `36951158275`. This turn inspected shared research scheduling, retained publication input, reconstruction/decision-input review and replay/publisher dependencies. Historical strategy admission still lacks complete dated facts/assumptions/rules/events and execution constraints; did not create retrospective approvals. Current case evidence stops are not reopened by rerunning the same sources.

A bounded NEW October 1-2 official-source query changed the next action: the supported CNINFO index collector returned two new 600887 announcements. Both PDFs were downloaded and byte-hashed, their issuer/date/announcement number and key physical pages text/graphics checked. An SSE URL returned HTML rather than PDF; the challenge response is quarantined as HTML, never admitted as evidence. The successful official originals are `1225591152` (SCP010/011 settlement completed) and `1225591147` (subsidiary guarantee and overdue-guarantee disclosures).

Research update: [600887-liquidity-event-followup-20261002.md](current/600887-liquidity-event-followup-20261002.md). The company-reported payment outcome is now disclosed; post-payment cash/debt, refinancing and guarantee materiality remain unresolved. Do not continue describing the outcome itself as wholly undisclosed, and do not promote it to a completed liquidity bridge or infer a default from subsidiary overdue guarantees. Original ledger remains frozen; no complete stop-consumption or research admission is claimed.

Existing `replay_workbench_cutoffs.py --event-source-pages` produced the real source-review packet; shared `prepare_event_source_review` / `project_company_event_questions` appended the two pending questions to the retained three-company product data. A new source-reverified handoff and readable company cards are in `runtime/public-event-followup-20261002/`. Handoff SHA-256 `2199bfa212d1345424206b2122aec5b7cee9c06e33da726085708ef00ae65627`; fresh verification receipt `integration-receipt.json` confirms investment values/gates, other companies, portfolio/events/stages and historical execution unchanged. Prior numerical receipt remains intact. The original JSON comparison was rechecked on actual `snapshot` fields with required-field assertions, not missing top-level keys.

ENGINEERING_DELIVERY=REAL_SOURCE_PACKET_AND_SHARED_HANDOFF; CURRENT_RESEARCH_ADMISSION=NOT_READY; FINAL_OPERATIONAL_ACCEPTANCE=NOT_REACHED; materiality_approved=false; model_validity_admitted=false; strict_pit_admitted=false; canonical_written=false; action=no_order. Official publication DATE_ONLY is separate from conservative next-day availability and actual October 2 acquisition. Full model-window event coverage, quote, dividend, portfolio and final operational gates remain unchanged. No production code, canonical workbook, server/PTA, database or scheduler change; no unchanged Core/CI rerun. This is a real evidence advance, not a status-only claim or total completion. Next product work is a scoped successor research/decision explanation incorporating these new originals while preserving the unresolved post-payment liquidity and guarantee gates, followed by the protected canonical publishing chain when ready.

