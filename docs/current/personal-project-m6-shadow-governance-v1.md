# PERSONAL_PROJECT_M6_SHADOW_GOVERNANCE_V1

Status: USER_APPROVED_FOR_OFFLINE_IMPLEMENTATION on 2026-10-03.
Proposal date: 2026-10-02. The user explicitly confirmed this integrated proposal.
Scope: governance redesign for a single-user observational no_order system.
This approval grants no deployment, scheduler, signing, database, restore,
paid-resource or workbook publication authorization. Existing contracts stay active.

## Current Reality and Dependencies

Inspected sources: config/m6-start-criteria-matrix-v1.json,
config/m6-production-authorization-vfinal.json, docs/m6-shadow-receipt-contract.md,
docs/current/shadow-start-readiness-20261002.md, and the user goal supplement.
The matrix explicitly describes itself as STATIC_BASELINE_NOT_CURRENT_READINESS:
its historical booleans are not fresh operational evidence.

Source HEAD: 9ad637b0ecb1f04070495f2c3c401ebd4e96af46.
Actual isolated imports established missing cryptography/PyYAML; shared Shadow
producer import fails. Source upload/hash checks passed. The first dependency
image build exited nonzero during download; no completed test image was found.
Root cause beyond the observed interrupted download/build is NOT_ESTABLISHED.
Current engineering authorization permits bounded isolated repair/retry, not
production deployment. Existing six-node synthetic assembly is verified, not
real-company admission or a real observed session.

Dependency order proposed:

1. Compatible isolated runtime and resource measurements.
2. User-approved successor governance contract and corresponding implementation.
3. Exact deployment/scheduler authorization and verified resource/backup baseline.
4. Nonpersonalized observational sessions with honest missing-data/refusal states.
5. Prospective PIT, full source coverage, real events and review accumulation.
6. Separate research/decision, personal portfolio, recovery and user acceptance.
7. Initial assisted use only after all applicable final requirements are verified.

No observation may be relabeled as admitted investment advice. An event snapshot
without coverage/watermark evidence cannot become a complete daily event scan.

## Integrated Governance Review

| Current Requirement | Original Reason | Current Risk | Personal-Project Necessity | Treatment | Proposed Replacement | Risk After Change |
| --- | --- | --- | --- | --- | --- | --- |
| Five distinct signer roles | Separate authorization/runtime/witness/intake/admission | Same owner can manufacture five keys without five independent controls | Role independence useful; key count alone misleading | SIMPLIFY | One explicit user authorization bound to artifacts; separate runtime integrity identity; externally retained checkpoints; truthful single-operator assurance label | Compromised owner may fabricate evidence; no institutional independence claim |
| Five externally pinned trust roots | Prevent bundle-controlled identity substitution | Operational burden; no real independent custodians established | External pinning remains necessary, five roles not inherently necessary | SIMPLIFY | Approved identity and exact artifact digests retained outside candidate/runtime; documented custody and revocation | User custody loss remains a stop condition |
| Enterprise witness/intake/admission | Reject backfills, replay and rollback | Independent service not established; circular infrastructure prerequisite | Anti-replay and provenance essential | SIMPLIFY | Append-only run sequence, predecessor hash, unique day/run ledger, earliest acquisition records and independent retained checkpoints | Local clocks/signatures alone do not prove contemporaneity; missing anchor means unproven credit |
| Mandatory OSS Object Lock | Offsite preservation and independently controlled arrival timestamps | Paid cloud dependency conflated with backup requirement | Independent encrypted recovery copy essential; provider not essential | SIMPLIFY | Provider-neutral encrypted offsite backup plus tested retrieval/integrity; separately assess immutable checkpoint/time assurance | WPS sync is not WORM and remote visibility is not retrieval/hash proof |
| Real production-server restore before first observation | Demonstrate recoverability of operating state | Resource pressure on PTA; broader than disposable observational job | Recovery proof necessary, exact host placement not always necessary | DEFER | Before observation: verified isolated recovery of complete job inputs/config/output and independent backup; before assisted use: target-compatible full recovery and measured RTO/RPO | Existing selected local restore does not yet prove complete coverage or PostgreSQL same-major restore |
| Strict contemporaneous PIT fully passed before Shadow | Prevent unsupported investment conclusions | Need real observation to build contemporaneous evidence; pre-start dependency may be circular | Mandatory before positive decision admission, not all observation | SIMPLIFY | Observation gathers prospectively frozen facts/assumptions/rules with actual acquisition cutoffs; strict PIT remains separate admission gate | Observation does not automatically pass PIT; backfills never receive contemporaneous credit |
| Real portfolio/IPS before Shadow | Validate personalized product | Stops public nonpersonalized workflow unnecessarily | Necessary for personalized sizing, not public observation | DEFER | Separate personalized gate; missing input yields BLOCKED_PRIVATE_INPUT, null guidance, false personal capacity | No personal buy/add/reduce quantities or capacity claims |
| M5 product acceptance before Shadow | Ensure real monitoring works | Observing event-loop defects itself needs runtime evidence | Input checks essential; complete product graduation can follow observation | SIMPLIFY | Start with validated capture/refusal mechanics; incomplete coverage blocks affected decisions and session-completeness claims | No promotion of partial scans or automatic materiality approval |
| Exact production scope authorization | Prevent unapproved live changes | Test permission mistaken for production permission | Essential | KEEP | One consolidated reviewed scope binds code/image/config/dates/exchanges/limits/rollback; no implied DB/restore/broker authority | Drift invalidates authorization |
| Resource caps, disk reserve, PTA protection | Avoid OOM and production regression | Recent available RAM below old 1228 MiB threshold | Essential; threshold changes require measurements and approval | KEEP | Serial bounded jobs, exact estimated write reserve, fresh baseline and PTA stop policy | No threshold reduction merely to pass preflight |
| Backup/key separation and emergency stop | Preserve assets, stop bad jobs | Existing selected backup is incomplete for full recovery | Essential | KEEP | Verified complete manifests, separate key custody, offsite retrieval checks, job-only stop/rollback | Never stop PTA or restore over production |
| Twenty real sessions and real event | Validate observed daily operation | Replay/synthetic dates can inflate apparent completion | Essential final acceptance | KEEP | Twenty consecutive official completed sessions plus one source-bound real event under approved successor contract | Missing/failed sessions recorded; no retrospective credit |
| External notifications, advanced rotation/TSA/PKI | Delivery and sophisticated timestamp assurance | Additional services/cost before basic product validation | Not mandatory for first local-outbox observation | DEFER | Local outbox, human review, explicit limited time-assurance claim; stronger assurance before claims requiring it | No assertion of trusted timestamps without actual proof |

No REMOVE recommendation is made. Simplification is not proof of equivalent
institutional security. The proposed personal assurance level must be explicit.

## Proposed Admission Separation

- ENGINEERING_RUN: isolated synthetic/real refusal checks; zero real session credit.
- OBSERVATIONAL_SESSION: authorized actual-day public-input acquisition and
  computation attempt, operational checks and sealed artifacts. NOT_READY is legal.
- COMPLETE_OBSERVATION: full required DAG/input coverage and resource/integrity
  checks pass; missing quote/event coverage remains an incomplete attempt, not credit.
- INVESTMENT_RESEARCH_ADMISSION: official facts, issuer identity, applicable model,
  assumptions, available_at/PIT, human review and no unresolved thesis breaker.
- PRICE_DECISION_ADMISSION: valid ModelValidity/PriceBridge and decision conditions.
- PERSONALIZED_ADMISSION: real reconciled portfolio/IPS/capacity required separately.
- INITIAL_ASSISTED_USE: original final product, historical validation, strict PIT,
  actual-session/event, complete recovery and user-comprehension acceptance.

All stages use action=no_order. No observation authorizes a trade. Missing private
inputs cannot be filled by synthetic accounts. Positive research/decision output
must never arise merely because an operational session was counted.

## Versioned Implementation and Approval Boundary

Following approval, create a separately versioned personal observational contract and
verifier. Preserve five-party legacy verification and existing frozen receipts;
never reinterpret old candidate signatures as successor operational admission.
Old and new counts/assurance labels must be distinguishable. Historical fixtures,
offline tests and prior unsupported sessions receive no migrated real-session credit.
Explicitly update authority documents and configuration only after approval,
including cross-references that currently require private portfolio/PIT/OSS at start.
No generic skip_gate flags or relaxed source/temporal comparisons.

Required tests before any production request: authorization/hash drift, duplicate
day/run, rollback, late/backfilled input, private-data absence, model stale, quote
invalid, incomplete events, resource refusal, synthetic credit refusal, legacy
contract regression and restart/window rules. Real independent checkpoint/recovery
evidence cannot be replaced by generated local test signatures.

## Consolidated User Decision

Approval received for successor offline contract implementation, NOT production
keys, deployment or Shadow start. No further governance approval request is needed
for implementing this approved scope.
Later one production request must list requested actions, prohibited actions,
exact artifacts, measured resource limits, reversibility and expected receipts.
Paid resources, private portfolio use and real restore retain explicit scopes.

## Implementation Evidence / 2026-10-03

The existing read-only CLI now accepts --governance-profile personal-observation-v1.
It reports a versioned dependency assessment separately from the unchanged legacy
matrix. Private portfolio and strict PIT move to their appropriate later admission
boundaries in the plan; backup/identity replacements remain NOT_VERIFIED pending
actual successor verification. Static all-pass flags never grant production start
or investment admission. Unknown hard gates, duplicate/missing baseline criteria
and non-no_order payloads fail closed. Default legacy behavior remains unchanged.

This is the dependency-assessment integration, not the completed successor session
verifier: exact authorization/evidence ingestion, anti-replay checkpoint validation,
session persistence and final admission integration remain implementation work.
Do not claim this plan alone starts Shadow or counts an observed session.

The offline observation ledger (`operations/personal_shadow_observation.py`) now
captures source-bound daily input audit attempts in exclusive-create records with
monotonic day/run uniqueness, sequence numbers and predecessor hashes. Reading
verifies the chain; each append requires the previously retained head hash so
tail deletion is rejected when that hash is held outside the ledger. All ledger
outputs are `LOCAL_OFFLINE_ONLY`, `NOT_ADMITTED`,
`verified_real_session_count=0`, `action=no_order`. A local hash chain alone cannot
prove contemporaneous intake, authorized production execution, independent custody
or genuine market data. This ledger does not replace the legacy five-party verifier
or count toward the 20 real sessions. Exact authorized scope, external checkpoint
custody, restart/window behavior and actual-session admission remain pending.
The current audit CLI exposes this only through explicit personal-governance,
daily-input path/hash, ledger path and externally retained prior head hash. The
first bounded run and its refusal reasons are in
`runtime/personal-observation-offline-20261003/report.md`.

## Independent Work Available Now

The new goal supplement authorizes isolated dependency/network diagnosis and
bounded build retries. These do not depend on approval of this proposal. Do not
repeat Core/CI without a relevant change, reopen evidence-stopped cases without
new material evidence, or create another workbook. Stop only the failed node
after a bounded budget and record root cause/reopen condition.
