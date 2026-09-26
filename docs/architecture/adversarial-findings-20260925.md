# Adversarial Findings - 2026-09-25

Read-only adversarial review baseline: 2135be59. The architecture-only
cleanup commit c87bc1c did not change valuation formulas, investment gates,
database schema semantics, or action=no_order. The later verifier v2 below is
an independent gate; findings stay open until every relevant consumer invokes
it and the old paths fail closed.

## P0 Findings

### ADV-P0-001 - M3 replay accepts future evidence

m3_historical_research_replay.py validates the future_facts_used boolean,
but does not compare each fact, filing, quote, or evidence reference
availability time with the replay date. A replay can therefore display a
later filing or quote as if it were known on the replay date.

Minimum fix: add an independent replay-time verifier that checks exact
available_at <= replay_date, validates quote dates and evidence hashes, and
rejects future disclosures, quotes, and price files with negative tests.

Status: MITIGATED_FOR_REPOSITORY_STRICT_CONSUMERS. The verifier independently
rechecks facts, filings, quote dates, evidence availability, file existence,
hashes, coverage, and rule registration. `m3_strict_pit_evidence.audit` now
requires a fresh in-process v2 PASS before returning
`EVIDENCE_VALID_FOR_CONTEMPORANEOUS_BINDING`, the thin CLI distinguishes
PASS/FAIL/NOT_PROVEN, and M7 labels the raw replay as
`REPORTED_NOT_V2_VERIFIED` rather than claiming verified PIT.

### ADV-P0-002 - Historical admission PIT is caller-declared

The frozen historical-validation contract accepts PitAssessment status
strings and arbitrary evidence ids. It does not independently prove that
every evidence item was available before the decision, that the benchmark
version is point-in-time, or that universe and survivorship controls are
real. The receipt audit verifies bytes and hashes, not those claims.

Minimum fix: build a separate versioned verifier in
application/historical_validation; do not edit or move the frozen
historical_validation.py file. The verifier must recompute temporal and
coverage predicates and must fail closed when the evidence cannot prove them.

Status: MITIGATED_FOR_REPOSITORY_STRICT_CONSUMERS. The verifier checks
benchmark identity/version/as_of, universe snapshot and survivorship controls,
evidence-dimension bijection, execution semantics, and one approved
model-session proof per claimed session. The receipt auditor requires a fresh
v2 PASS for strict admission claims and binds the enforcement to the exact
admission bytes. The frozen 600519 builder remains byte-identical and still
cannot produce a strict result; future strict writers must use a versioned
successor with the same gate. The frozen domain contract remains unchanged.
Current first-case conclusion remains NOT_PIT_SAFE / NOT_ADMITTED.

## P1 Findings

### ADV-P1-003 - M5 ACTUAL authorization can be constructed locally

M5ActualOfflineAuthorization accepts caller-provided hex strings and the
guard checks only dependency-graph equality. It does not verify an external
human approval or reread the reviewed bytes.

Minimum fix: make ACTUAL capability issuance depend on a separately verified,
byte-bound approval receipt and add forged-hash negative tests.

Status: CLOSED_BY_SIGNED_APPROVAL_RECEIPT. Capability issuance now requires a
separately verified, byte-bound, append-only human approval receipt and the
reviewed event bytes, identity, graph and receipt chain are rechecked. Focused
forged-hash/replay/identity negative tests pass. Trust-root provenance is now
additionally pinned by the committed `authorization-trust-roots-v1.json`
registry, so a self-minted keypair can no longer issue a capability; see
ADV2-P0-002 and ADV2-OPEN-001 for the remaining keystore prerequisite.

### ADV-P1-004 - M6 proof can be forged inside the Python process

OperationalAuthorizationProof._issue is callable by ordinary code and
persisted control state is not revalidated against the signed authorization
bundle on every read or transition. The normal CLI path fails closed, but the
domain API is not an unforgeable capability boundary.

Minimum fix: use a signed token or non-exportable capability, bind persisted
state to the original authorization bytes and trust root, and reverify on
read and transition.

Status: CLOSED_BY_SIGNED_AUTHORIZATION_REVERIFICATION. The callable `_issue`
path is removed; issuance and persisted-state reads/transitions verify the
signed authorization artifact, scope, target mode, deployment/config hashes,
operator, validity window and trust root. Legacy authorized v1 state fails
closed. Trust-root provenance is pinned by the same committed registry, and an
unpinned root invalidates previously issued proofs on read, transition and
restart; see ADV2-P0-002. No Shadow or production action has been started.

## P2 Findings

- Legacy simulation state now carries an explicit simulation-only contract:
  `SIMULATION_ONLY`, `trade_approved=false`, `live_eligible=false` and
  `action=no_order`; tampered or unmarked snapshots fail closed. The frozen
  legacy virtual-account module remains byte-identical, so the enforcement is
  in the verifier/consumer boundary rather than by rewriting frozen bytes.
- M4 private intake has a byte-bound confirmation receipt that binds the exact
  reconciliation-report bytes, account scope, snapshot date and explicit user
  confirmation. This is an integrity contract, not production authorization or
  a signature. Private receipt storage and key separation remain mandatory.
- CI now includes the smallest deterministic Product UX, CLI v2, M4
  confirmation, M5 approval/run-request, M6 authorization/start-matrix and
  existing PIT negative tests. It still runs a selected core list rather than
  the full repository suite; production/private-data/natural-time checks remain
  not run and must not be inferred from CI success.

## Second Adversarial Review - 2026-09-26

Read-only review of the productization round (baseline `5d8ba6d` plus the
working tree). Every finding is recorded with the action actually taken;
nothing here claims production readiness.

### ADV2-P0-001 - Legacy M5 authorization could create a new ACTUAL run

`apply_run_request(..., allow_legacy_read_only=True)` accepted an unsigned v1
authorization against an empty store and published a fresh ACTUAL receipt for
`600887-synthetic-run-20260924`. The unsigned payload, not a signature, was the
only input needed.

Status: CLOSED. Legacy read-only replay now requires the pinned request to
already exist in the durable state store with an identical request
fingerprint. An empty store raises `read-only replay only`, and neither the
state store nor the receipt store is written. The archived 600519 cold-replay
test now seeds the archived state, asserts an idempotent replay, and keeps a
separate test proving a fresh run is refused.

### ADV2-P0-002 - M5/M6 trust-root provenance was caller-controlled

Verification used the caller-supplied public key and trust root, so a freshly
generated keypair could self-authorize an M5 ACTUAL capability or advance M6 to
`STAGING` with `authorization_id="synthetic-only"`.

Status: CLOSED_BY_PINNED_TRUST_REGISTRY.
`operations/authorization/trust_root_registry.py` now accepts a trust root only
when its canonical fingerprint appears in
`config/authorization-trust-roots-v1.json`. That committed registry is empty, so
production ACTUAL and M6 authorization stay fail-closed until a real operator
key is registered by a reviewed change. M5 re-checks the pin at capability
issuance and on every `verify()`; M6 re-checks it on every proof read,
transition and restart, so unpinning a root invalidates previously issued
proofs. Negative tests cover an unpinned M5 receipt, a fresh M6 keypair, and a
proof re-read after unpinning.

### ADV2-P1-001 - M5 approvals had no expiry window

Receipt payloads carry `authorized_at` but no `valid_until`, and a synthetic
receipt still verified with a use time in 2099.

Status: OPEN - replay hardening, non-blocking for this round. No v2 approval
receipt exists outside synthetic fixtures and the pinned registry is empty, so
no production approval can be issued or replayed today. A bounded
`valid_until` window is required before the first real trust root is pinned.

### ADV2-P1-002 - M4 RECONCILED was an unsigned self-assertion

The confirmation receipt binds exact reconciliation bytes, scope, snapshot date
and confirmation string, but carries no signature or signer identity, and the
CLI supplied the confirmation id and timestamp.

Status: CLOSED_BY_EXPLICIT_NON_AUTHORITATIVE_CONTRACT. The receipt contract now
states that it is an unsigned human assertion whose acceptance authority is
`NONE`, and its public fingerprint carries `authentication_basis =
UNSIGNED_HUMAN_ASSERTION` and `acceptance_authority = NONE`.
`M4_PERSONALIZED_ACCEPTANCE` remains a human milestone at `WAITING_R2` with no
code path from this receipt to acceptance.

### ADV2-P1-003 - Event review minted ACTUAL provenance from a default string

`review_provenance` defaulted to `USER_CONFIRMED_DELEGATED_REVIEW` and was only
compared as a string, so running the CLI silently produced ACTUAL bridge
batches.

Status: CLOSED_BY_EXPLICIT_CLAIM_AND_UNAUTHENTICATED_MANIFEST. The default is
removed; callers and the CLI must state the claim explicitly, and the manifest
records `provenance_authenticated=false` plus
`requires_signed_approval_receipt_for_actual=true`. The authenticated boundary
remains the signed, pinned M5 approval receipt at the run gate.

### ADV2-P1-004 - M7 could present self-asserted portfolio values as real

The read model trusted an upstream `real_data_available` boolean, so a payload
with invented totals rendered as a real portfolio.

Status: CLOSED_BY_PROVENANCE_GATE. Portfolio totals and positions render only
when `portfolio_provenance.reconciled is true` and a non-empty confirmation
receipt fingerprint are present; otherwise the page reports
`PENDING_USER_PRIVATE_INPUT` with empty figures. The gate checks provenance
presence and reconciliation state, not the receipt cryptographically - that
remains an upstream responsibility.

### ADV2-P1-005 - Candidate projection trusted legacy status when root was omitted

`project_product_workbench_candidate` treated `root` as optional, so a direct
caller could inject M3/M6 stage statuses without evidence files being checked.

Status: CLOSED. `root` is now a required, runtime-validated keyword argument and
evidence files are always hash-checked against it. The production CLI already
passed `root`, so its behaviour is unchanged.

### ADV2-P1-006 - The M6 matrix could not represent an allowed start

All hard gates satisfied plus `shadow_start_allowed=true` still forced
`BLOCKED_PENDING_HARD_START_GATES`, and the M3 criterion was classified
`NATURAL_TIME_REQUIRED` while being a pre-start hard gate.

Status: CLOSED. The matrix now supports `SHADOW_START_READY` and rejects a
startable matrix that reports the blocked decision (and the reverse). The M3
criterion is classified `RESEARCH_EVIDENCE_REQUIRED` while staying a
`HARD_START_GATE`; its elapsed-time dependency stays in the reopen condition,
and `NATURAL_TIME_GATE` is reserved for post-start observation windows. The
committed matrix still reports `shadow_start_allowed=false`.

### ADV2-P2-001 - Run-specific disclosure tools were listed as product CLI

Status: CLOSED. `build_m5_disclosure_queue.py` and
`apply_m5_disclosure_review.py` are engineering tools; the product surface is
now 15 generic entrypoints with the run-specific ones excluded by test.

### ADV2-P2-002 - Simulation-only marker had no production consumer

Status: CLOSED. `virtual_account_store` writes the canonical simulation marker
and fails closed on load when `simulation_only`, `trade_approved=false` or
`live_eligible=false` is missing or contradicted. The frozen
`virtual_account.py` bytes are unchanged.

### ADV2-OPEN-001 - Trust roots remain repository-local

The pinned registry closes self-minted keys, but it is a reviewed file in the
same repository. A real operator key should live in an OS or hardware keystore,
and registering the first fingerprint must be a signed, reviewable change. This
is a documented prerequisite for the first real production authorization, not a
claim made by this round.

## Permanent Semantics

action = no_order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Backtest != M6 Shadow

## Next Task

## Next Task

NEXT TASK: ADD_BOUNDED_VALIDITY_WINDOW_TO_ACTUAL_AUTHORIZATIONS

Goal: give the M5 v2 approval receipt and the M6 operational authorization
proof a required, bounded `valid_until` that is re-checked on issuance, replay,
transition, restart and read, with a negative test proving an approval cannot be
consumed after expiry. This is the last self-owned gap from the 2026-09-26
adversarial review and must land before the first real trust-root fingerprint
is pinned.

Files likely affected:
`src/value_investment_agent/operations/authorization/m5_actual_approval_receipt.py`,
`src/value_investment_agent/m6_operational_control.py`,
`src/value_investment_agent/m6_shadow_receipts.py`, the M5/M6 thin CLIs, the
synthetic authorization fixtures and their focused tests.

Forbidden changes: editing `virtual_account.py`, `historical_validation.py` or
`scripts/build_moutai_historical_validation_admission.py`; pinning a real trust
root; requesting production authorization; starting Shadow, a scheduler,
notifications, migrations or a real-account import; weakening any existing
fail-closed check; treating an expiry window as production readiness.

Acceptance criteria: a receipt or proof used after `valid_until` fails closed
with a clear error on every path; receipts with an invalid or inverted window
are refused; existing pinned-registry, legacy read-only and simulation-only
tests still pass; full offline regression and Core Research Gates pass;
`action=no_order`, `M6_OPERATIONAL=NOT_STARTED` and
`INITIAL_ASSISTED_USE=NOT_REACHED` remain unchanged.
