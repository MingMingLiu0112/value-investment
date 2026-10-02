# Shadow Start Readiness / 2026-10-02

Scope: STAGE_5_SHADOW_START_READINESS within VALUE-INVESTMENT-TRADING-ASSISTANT-V1. This report does not grant R3, change M6 start gates, or count a session. action=no_order.

## Actual dependency map

| DAG_NODE | CURRENT_IMPLEMENTATION | CURRENT_REAL_INPUT | MISSING_DEPENDENCY | GAP_TYPE | IS_EXECUTABLE_NOW | ACCEPTANCE_EVIDENCE |
| --- | --- | --- | --- | --- | --- | --- |
| Shared research | application/product/company_research.py | Retained source-bound cases and stop ledger | Reopen evidence for admitted conclusions; blocked outcomes remain legal | DATA_GAP | Yes, no promotion | Existing scheduler/gate regression tests |
| Historical decision replay | application/historical_validation/decision_input_review.py | Source-bound retrospective equity facts | Complete dated assumptions/rules/gates | DATA_GAP | Temporal review only | Retained three-cutoff report |
| Historical execution replay | application/historical_validation/historical_execution_replay.py | Frozen historical OHLC/dividends | No historical input can replace today's observation | DATA_GAP | Mechanical replay only; no expansion | cash-reconciled-final-20261002 |
| Daily quote | quote_session_collection.py, quote_session_conversion.py, scripts/current/daily_quote_binding.py | Retained bundles, not October 2 matched closes | Same-day post-close dual-source matched closes for authorized symbols | NATURAL_TIME_WAIT | No full trading session today | B1 raw revalidation tests |
| Daily events | M5 observation/review and m6_event_observation | October 1 Yili originals, bounded October 2 acquisition | Full prospective daily coverage, original/index hashes and scan cutoff | DATA_GAP | Evidence capture yes; no complete current scan claimed | Existing source-review packet |
| ModelValidity / PriceBridge | Shared research service and typed contracts | Conditional valuation / no admitted current bridge | Event impact and valid same-session quote | DATA_GAP | Fail-closed output yes | Existing model/bridge tests |
| Decision / portfolio | Shared decision and portfolio gates | Public research; no confirmed real private portfolio | Personalized inputs; nonpersonalized refusal remains possible | DATA_GAP | Yes for refusal, not sizing | Decision/portfolio tests |
| Daily product | scripts/current/daily_product_packet.py | Frozen M7 packet plus quote overlay | A run-bound full daily DAG packet, not just frozen packet + quote | CODE_GAP | Isolated integration yes | New daily audit refuses missing nodes |
| Session artifact verification | m6_shadow_receipts.py plus new operations/shadow_daily_input.py | Old receipts bind artifact hash, not complete daily contents | Mandatory generation/consumption wiring for full run artifact | CODE_GAP | Independent content audit now executable; end-to-end producer still pending | Existing CLI --daily-input, tests, retained incomplete packet |
| M6 preflight | operations/start_criteria.py, m6_operational_readiness.py | Static matrix is not fresh production readiness | M3/M4/M5 acceptance and current measured operational receipts | DATA_GAP | Offline audit yes; real start no | Matrix unchanged; latest scoped audit |
| Scheduler / operation | Existing deployment timers, operational control and admission | No newly established R3 authorization for this task | Approved scope and fresh operational bindings | AUTHORIZATION_GAP | Configuration review only, no launch | No scheduler/production mutation |
| Excel | Source-bound publisher and canonical read model | Latest verified original workbook | Nothing for this backend audit; no new workbook needed | DATA_GAP | Existing publishing chain available independently | Existing 55-sheet preservation/WPS receipt |

The new audit closes content-consistency checks, not the remaining full daily producer/consumer integration. CODE_GAP is not zero. Do not claim ENGINEERING_READY=YES.

## What a NOT_READY day means

The signed session verifier counts successful authenticated resource-safe completed sessions and does not inspect a suggested investment state. Thus NOT_READY is not intrinsically a failed run. However the existing start matrix explicitly retains M3 strict contemporaneous PIT, M4 real confirmed portfolio and M5 product acceptance as HARD_START_GATE. Daily input consistency cannot waive those gates or produce signed admission.

CAN_A_NOT_READY_DAY_COUNT_AS_VALID_SHADOW = NO under current unmet formal start/admission conditions. After the unchanged formal start conditions and authenticated observation chain pass, NOT_READY alone need not invalidate a technically successful session. This is not a change to the old contract. Nonpersonalized isolated DAG execution can proceed without private inputs; formal M6 production start still follows its existing matrix.

## Delivered and reproducible

Successor engineering delivery: the existing audit command now accepts
`--isolated-run runtime/<new-directory> --symbol 600887 --event-input <path> --event-input-sha256 <hash>`
and optional paired quote path/hash. It invokes the shared research scheduler,
snapshots original input bytes, persists research/model/decision/portfolio/product
refusal artifacts, a run receipt and manifest, then mandatorily consumes that
manifest through the daily input audit before returning. Existing output
directories are refused. Actual evidence is in
`runtime/shadow-isolated-refusal-20261002/report.md`; manifest SHA-256
`6a47994a9c7aafc551018b936e323df90f2534f8805bb9fa22b500879166d26f`.
Only research scheduling executed; downstream nodes are NOT_RUN_UPSTREAM_BLOCKED.
The successor runner also preserves normal shared research model/bridge outputs
without recalculating them, and calls the existing decision evaluator only for
same-symbol, same-session typed pre-decision input. Missing or dated inputs remain
NOT_READY; it never invents a buy/add intent. This does not close the full
current-input DAG producer gap or formal production integration.
Snapshot acquisition time is explicitly not original source publication time.
The retained event package remains incomplete, not a full prospective scan.

Existing command extended, no alternate daily state counter:

```powershell
py -3 scripts/current/audit_m6_start_criteria.py --daily-input runtime/shadow-start-readiness-20261002/input.json --daily-input-sha256 2ccda3af3d13079784086e9c45330c77cdc5a43a8d3a2397897c073aaa332732 --output runtime/shadow-start-readiness-20261002/recheck.json
```

Output must be new; immutable previous outputs are not overwritten. The retained real original-event binding produces SHADOW_INPUT_INCOMPLETE with missing DAG artifacts, not a fictional full run. The initial manually entered future generation time was rejected before any result was saved; corrected to the observed current clock, with post-close incompleteness retained. This dry-run manifest is not a Shadow session. Synthetic complete-contract tests exercise byte/time/run binding only and grant zero real sessions.

SHADOW_SESSION_VALIDITY and INVESTMENT_DECISION_VALIDITY remain separate; offline consistency always has shadow_session_valid=false and verified_real_session_count=0. Signing, independent intake, admission, event credit and 20-session counting are unchanged. No TSA/PKI/backup/broker/model expansion, no server/PTA mutation, no Excel publication.

## Required final status

### Calculation-to-product lineage is now checked

Daily audit also checks that the shared application receipt consumed the exact
quote and raw event-scan hashes (not merely their projected wrapper), with a
valuation-package binding. Model validity, PriceBridge and valuation projections
must match the actual research result. Existing typed decision/pre-decision
parsers validate review identity, date, status and blockers; the product state
must match that decision. These are provenance checks, not new valuation or
portfolio rules. Missing/refused computation remains incomplete; NOT_READY is
never itself substituted for evidence of a computed review.

Actual re-consumption: `runtime/shadow-existing-risk-dag-20261002/lineage-consumer.json`.
The stopped research has no admitted quote/event calculation or model/decision
lineage. It remains NOT_ADMITTED, count zero. Earlier hash-only synthetic placeholder
fixtures now correctly fail full consistency rather than PASS. Tests also reject
a substituted valuation and a product BUY state inconsistent with the decision.
Operational proof matching remains a separate unchanged gate; no production
adoption, real model calculation or investment-effectiveness claim is added.

### Known research-input rejection is now an auditable daily outcome

Shared descriptor/run-spec ValueError and missing-file rejection before one-shot
reopen consumption use an explicit ResearchInputValidationError (still ValueError
compatible). The isolated runner seals this known rejection as
REJECTED_BY_INPUT_VALIDATION with failed application receipt, untouched reopen
consumption, NOT_READY decision, skipped downstream computations and readable
company-card output. It does not turn a failed calculation into a completed model.
Unknown RuntimeError and input-integrity/scope errors outside this narrow boundary
still propagate; no fabricated receipt is written for an unexpected program bug.

Synthetic integration output:
`.tmp/shadow-rejection-target/test_daily_attempt_seals_known0/runtime/rejected-input/company-card.md`.
The fixture exercises quote-after-research-cutoff rejection and confirms no-order,
zero daily credit and retained refusal explanation. It is explicitly not a real
company valuation, a real source failure observation or production evidence.
Actual issuer evidence stops and all positive admission gates remain unchanged.

### Read-only daily consumer uses existing operational admission

The supported daily-input command now calls `consume_shadow_daily_input`, not
just the offline consistency audit. Without existing operational proof it returns
NOT_ADMITTED and zero credit. Optional hash-pinned `--operational-inputs` describes
exact bundle/trust_root/schedule bindings; existing M6 signature, pinned trust,
authorization and independent witness validation is called unchanged with the
original 20-session/one-event admission scope. Daily content is rechecked after
that validation. The signed session must bind this exact manifest SHA-256, run ID,
session day and generation time inside its signed execution window. Counts are
the intersection with already verified operational sessions, never a new ledger.
No signing, new trust setup, scheduler, admission envelope or production action
was added. Existing historical verifier callers remain unchanged; production
scheduler/intake adoption of this consumer is NOT_VERIFIED and still requires
the original authorization and readiness gates.

Real existing package consumption result:
`runtime/shadow-existing-risk-dag-20261002/formal-consumer.json`.
NOT_ADMITTED: existing operational admission absent, quote/event/DAG incomplete.
It does not seek authorization or reinterpret the synthetic risk sample as a day.
Reproduce with `--daily-input` pointing to the existing input.json, SHA-256
`d1b5cbb9038d3201920f3b4c6c1525e017ff04eba42cd51def0bc46992602d07`,
and a fresh runtime `--output`. Operational proof matching is covered with mocked
signature-verifier test fixtures only; no real positive admission is claimed.

### Existing portfolio risk engine connected (explicit rehearsal only)

Optional `--simulated-portfolio` and paired SHA-256 connect the already existing
M4 risk engine to the daily orchestration, independent of a stopped company case.
Only the established `m4-portfolio-risk-demo-v1` SIMULATED contract is accepted;
ACTUAL namespaces are rejected, not copied into repository artifacts. The demo
snapshot retains its original date, policy and limits; there are no new position
rules or inferred human confirmations. Its exact input snapshot/hash is retained
under runtime after validation. Results appear in portfolio.json and the company
card; personal capacity remains false and position guidance remains null.

Actual joined run: `runtime/shadow-existing-risk-dag-20261002/company-card.md`;
manifest SHA-256 `d1b5cbb9038d3201920f3b4c6c1525e017ff04eba42cd51def0bc46992602d07`.
Existing September 22 demo produced VIOLATION: 600519/601088 single-security caps
and emergency/liquidity cash reserve. These are simulated account findings, not
current user exposures or company sell recommendations. Executed nodes: research,
portfolio_gate (simulated), product. Receipt simulation_only=true; no real session
credit. Missing model/decision/current quote/event coverage remain visible.

Reproduce the existing command with a fresh runtime destination and add
`--simulated-portfolio tests/fixtures/m4_portfolio_risk_demo.json` and the actual
file SHA-256. This is a technical demonstration path, not an alternate formal M6
start contract, production portfolio intake or permission to bypass private input.

### Raw scan to daily event contract integration

The isolated producer now uses `project_daily_event_input` for M1 scans. Research
still reads the unchanged original M1 bytes; daily audit reads `daily-event.json`
with a hash-bound raw scan, original evidence and index bindings. Acquisition
time is the scan's actual retrieved_at, not a fresh rerun clock or publication
time. Declared scan bounds and coverage remain unchanged. COMPLETE day coverage
also requires an explicit timezone-aware post-close `covered_through` watermark
no later than acquisition; date-only acquisition does not supply this watermark.
This is input projection, not independent proof of provider completeness,
materiality approval, research admission or operational authorization.

Actual output: `runtime/shadow-projected-events-20261002/company-card.md`; manifest
SHA-256 `b486dfdf0bf0dfc56ac121e405e35bec07f629b7903a916d1e159f743757e2f4`.
Raw scan and both original PDFs plus index are checked by the existing loader and
hash binding. Actual audit no longer reports missing wrapper timestamps/sources;
it retains EVENT_COVERAGE_INCOMPLETE, missing quote, pre-close and incomplete DAG.
Current research is still refused; zero real sessions; no_order. This closes the
raw-scan adapter gap, not the full operational start-readiness gap.

### Mandatory consumer now audits incomplete runs, not just their hashes

Removed the missing-role early return. Every present daily artifact is now loaded,
byte/time checked and tested for run/session identity and the no-order boundary,
even if quote or another role is absent. Available quotes still use the existing
verified converter. Missing event time fields become explicit contract blockers,
not a KeyError or an assumed completed scan. Receipt/DAG checks and the final
byte recheck always apply to present files. A malformed/order-bearing partial
artifact is rejected rather than hidden behind a missing quote.

Real successor: `runtime/shadow-consumer-checked-20261002/company-card.md`; manifest
SHA-256 `e04f9bc3dc6ab1f929136630ee13d2d872a3d04e6511da133fb5c859b36f1773`.
The retained official M1 event scan is valid as disclosure acquisition context,
but does not provide the daily prospective wrapper fields (`observed_at`,
`scan_as_of`, `coverage_complete`, `source_bindings`). The audit now exposes these
specific missing contract fields and incomplete execution, in addition to quote
and cutoff gaps. This does not mean the original PDFs are missing or unverified.
The original-page followup verifier remains separate and its explanations remain
visible. No full-run PASS, investment admission or real session credit is claimed.

### Readable company output integrated into the daily attempt

`--event-followup` with `--event-followup-sha256` connects the existing source-page
verification use case to the daily product artifact and new presentation-only
`company-card.md`. It rechecks originals, page anchors, cutoff, issuer and exact
acquired event-scan hash before creating output. The explanation packet is copied
unchanged into runtime. Claims remain SOURCE_ANCHORED_EXPLANATION_ONLY; unresolved
questions, research refusal, missing estimate and no portfolio guidance remain
visible. No materiality, valuation or order rule is introduced by the renderer.

Actual 600887 report: `runtime/shadow-readable-company-20261002/company-card.md`.
Daily manifest SHA-256 `9a5e940e3e1fb753b3b2e2d9a39f392619a574dd58ee9d0916a44a14dd0c2fc0`.
This joins original disclosure explanations to the same daily research/decision
refusal, instead of making the user interpret a machine receipt alone. Both
official facts and unresolved liquidity/guarantee/dividend questions are retained.
No positive investment admission, portfolio result or real session credit follows.

Reproduce the preceding command with a fresh runtime destination, adding
`--event-followup runtime/public-event-followup-20261002/followup.json` and its
SHA-256 `0f775175dee1a8e12161b877c09ee8e50bcc90b10e00ff2cef186d9936e9420d`.
The canonical workbook and production publisher are unchanged.

### Explicit shared research inputs

The isolated entry now accepts paired `--research-package` / SHA-256 and paired
`--schedule-request` / SHA-256. A request requires an explicit package. Inputs are
copied into the immutable runtime attempt and passed to the existing shared
research entry, whose official-source, Evidence Stop and once-only consumption
checks are unchanged. The original package is not rewritten. Research bindings
live inside the hashed research artifact, not as invented daily DAG roles.
Each binding distinguishes shared-receipt binding from a snapshot never consumed.

Actual output: `runtime/shadow-bound-research-20261002/report.md`, manifest
SHA-256 `2d879d046a1d1f9f1f1fda1ea26ee1c2e747267b8225a107b279fd35c0135e6c`.
The existing real 600887 package was snapshotted, not consumed, because the shared
scheduler refused. No reopen request was manufactured. Request forwarding is
covered by synthetic integration tests only, not production evidence acceptance.

Reproduction (PowerShell 7, repository root; choose a fresh runtime output):

```powershell
$package = 'config/m1-valuation-packages-v1/600887-quality-compounder.json'
$hash = (Get-FileHash $package -Algorithm SHA256).Hash.ToLowerInvariant()
py -3 scripts/current/audit_m6_start_criteria.py --isolated-run runtime/shadow-bound-research-recheck --symbol 600887 --event-input runtime/public-event-followup-20261002/event-scan.json --event-input-sha256 4318426b8ea4e54d2f40ec03b01c31f20f3c9a83560b7bea028641a0af8a3cbc --research-package $package --research-package-sha256 $hash
```

Successor integration: with an explicit package, the isolated runner forwards
the snapshotted quote and event into shared descriptor construction. Existing
verified quote/event adapters now consume those references instead of the package's
old quote/scan references, after the scheduler permits research. The declared
model validity window and material events remain unchanged; no approval is inferred.
Descriptor and run-spec validation precede one-shot reopen consumption. A later
quote still cannot follow the research cutoff; no research date is rewritten.
Application input hashes use the established `input_sha256` receipt key.

Actual successor report: `runtime/shadow-daily-input-consumption-20261002/report.md`,
manifest SHA-256 `865018c9840cc16ed955b04d348d1b8ddee03b468348bf503535551576ee9718`.
The real scheduler still refuses; quote is absent and the package remains
snapshot-only. Allowed-path forwarding/order validation is synthetic, not real
investment acceptance. Remaining gap: a genuinely permitted, dated package plus
verified quote and complete event window, and full downstream daily consumer
integration. Normal output preservation alone is not current-input recalculation.
The mandatory daily audit and unchanged M6 admission remain separate gates.

Successor isolated attempt: `runtime/shadow-isolated-shared-dag-20261002/report.md`;
manifest SHA-256 `d6caf51b364b32ef339c9ad34e0e9f1b6f318f5091f9118bb60ab68d97130cb0`.
The real 600887 scheduler still refused research. Executed nodes are research and
refusal product projection only; no full model/decision/portfolio execution is
claimed. Input audit remains incomplete (no quote, no same-day post-close input).
Event issuer mismatch or missing identity now fails before output creation.
Normal-result branch validation uses isolated synthetic tests, not real admitted
company evidence. Real session credit remains zero.

- SHADOW_START_READINESS: PARTIAL.
- ENGINEERING_READY: NO.
- CODE_GAPS: full current daily Research/Model/Decision DAG producer and mandatory artifact-consumer integration; the audit does not prove actual execution from a self-authored receipt.
- DATA_GAPS: matched same-day authorized-symbol quotes, complete prospective event input, existing formal product/operational start prerequisites.
- AUTHORIZATION_GAPS: explicit R3/scoped production Shadow authorization and bound operational proof; historical authorization cannot be assumed applicable.
- NATURAL_TIME_GAPS: next actual trading session; 20 distinct authorized real sessions remain future acceptance, not an engineering startup lock.
- 600887_CURRENT_STATE: settlement outcome=VERIFIED_BY_OFFICIAL_DISCLOSURE; post-maturity cash/debt bridge=NOT_ESTABLISHED; ModelValidity=NOT_ESTABLISHED; Current PriceBridge=NOT_ADMITTED. This is issuer disclosure, not independent bank confirmation.
- 000333_CURRENT_STATE: INSUFFICIENT_PUBLIC_EVIDENCE / EVIDENCE_STOP.
- 601088_CURRENT_STATE: INSUFFICIENT_PUBLIC_EVIDENCE / EVIDENCE_STOP.
- EARLIEST_SHADOW_START_DATE: NOT_COMMITTED. October 8 is the next scheduled market opening, not proven readiness or authorization.
- CANONICAL_EXCEL: same WORKBOOK_PATH, no new user workbook.
- ACTION: no_order. Total objective is not complete; continue the independently executable producer/consumer integration rather than expanding research or declaring all engineering done.

Official opening schedule: [SSE](https://www.sse.com.cn/disclosure/announcement/general/c/c_20260915_10832273.shtml), [SZSE](https://investor.szse.cn/disclosure/notice/general/t20260917_622911.html). Both specify October 1-7 closure and October 8 reopening; calendar web verification is not itself a production-bound calendar receipt.
