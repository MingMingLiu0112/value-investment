# WEB-FIRST-FULL-PRODUCT-CLOSURE-V1 execution ledger

## 2026-10-18 S4 browser bookkeeping loop and S6 bounded Mock workflows

### Successor: workflow-specific Web research and private retrospective

The existing Agent read route now selects event/financial/legacy workflows from
an explicit version-2 server registry while retaining version-1 compatibility.
Daily packets must reproduce their exact workflow/provider-input fingerprint;
a generic three-role packet cannot be relabelled as a daily event or financial
draft. Financial transcription/metric-workbench bytes are rechecked. Missing
financial work returns WORKFLOW_NOT_REGISTERED with no substitute findings.
The actual retained 600519 event draft is registered separately from the older
generic Mock packet; both remain historical cutoff 2026-10-08, not current
financial conclusions. The stock detail selects these three material types.

Private retrospective reads use only the existing journal validator/replay and
saved recording-time judgment. The authenticated route never writes a journal
or public packet; the portfolio shows a dated Mock draft after confirmed trades.
It reports reference differences and missing trade-time/risk/reason/subsequent
evidence, not inferred approval, plan compliance or strategy performance.
TEST_ONLY namespace variants remain labelled synthetic; user-confirmed ledgers
remain explicitly unverified by a broker. No model provider is called.

Verification before independent review: 373 backend/API/architecture tests,
238 Web tests, typecheck and format passed. Browser interaction for these new
controls remains NOT_VERIFIED because the normal tab's URL policy still blocks
observation. Actual loopback API and committed runtime evidence must be recorded
separately after build/restart. S6 remains IN_PROGRESS: hotspot research, complete
daily orchestration, actual provider and full product acceptance are not done.

Independent review found a P2 missing-journal display ambiguity: the reader
correctly refused unavailable private input, but the panel could label an empty
result as no fills. The panel now renders a distinct unavailable-input state.
Its regression passes, along with the strengthened real-fingerprint relabelling
counterexample: 73 backend focused tests and 6 Web focused tests passed. The
review found no concrete P0/P1; that does not replace pending browser acceptance.

Exact d4d356ae Core CI found a repository-boundary regression: the new local
runtime event packet had been force-added to Git. Web and PostgreSQL passed;
Core correctly rejected tracked runtime data. Removed that file from the Git
index only, preserving its local bytes and registered SHA-256. No runtime-data
allowlist or architecture test was weakened. Current public research inputs
remain external/local assets, as in the existing legacy registration. Successor
Core/runtime verification must bind to the corrective commit separately.

Successor inspection on baseline 7a1e09ae traced the actual 000333 null expiry to
`infrastructure/hotspot/current_price_case.py::_display_close`: its explicit
LAST_COMPLETED_CLOSE_DISPLAY_ONLY contract returns next_session=null. The
projector preserves this lack of future validity. No calendar date, B1 admission
or formal investment permission was invented to unblock sizing.

A separate TEST_ONLY integration regression now connects the real scenario risk
engine to a 100-share-unit manual buy, same-day T+1 rejection, next-day sale,
explicit fees, idempotent confirmations and journal restart. Preparation leaves
cash/holdings unchanged; rejected selling leaves journal bytes unchanged; replay
recovers cash, positions, trades and realized PnL. Synthetic price 10 / stop 9.9
belongs only to that fixture, never actual 300364 research. The complete risk
preview module passes 62 tests. This is automated integration evidence, not a
positive browser or signed-research acceptance, and not investment performance.
The normal user browser tab still reports connection failure to browser tools;
its URL policy rejects observation. No alternate browser/workaround was used.

The existing `scripts/current/run_agent_research_pilot.py` now exposes
`--workflow event|financial --mode mock` with pinned source-request JSON;
financial inputs optionally bind their transcription and metric workbench.
Legacy execution/output remains supported. These branches reject live/offline
modes and paid-provider settings, never register or publish a packet, and return
exit 2 for a blocked missing-input outcome. Root exercised the CLI against the
retained real 600519 originals (historical research cutoff 2026-10-08): three
event questions, byte-identical repeat, and a financial missing-period-contract
refusal without creating an output packet. Evidence:
`artifacts/current/web-first-acceptance/s6/daily-cli-validation.json`.
Combined S4/S6/IPS/ledger/account-continuity regression: 137 passed. The CLI is
not yet the complete four-workflow daily launcher, and no live model was called.

Actual TEST_ONLY browser operations initialized virtual cash and IPS, confirmed
two buys in separate sleeves, rejected same-day selling, confirmed next-day
hotspot selling, reconciled internal records and displayed all three fills in
history. Restart preserved revision 10, cash 9097, CORE_VALUE 100 shares/cost
1001 and synthetic realized PnL 98. Journal SHA-256 stayed unchanged. These are
synthetic accounting outcomes, never strategy performance or real signatures.
Receipt: `artifacts/current/web-first-acceptance/s4/private-browser-loop.json`.

The exercise exposed a cross-strategy exit alert after the hotspot sleeve was
fully sold. Fixed alerts to require actual positive holdings in the matching
strategy; verified in the rebuilt browser. Fill requests now retain immutable
retry bodies and synchronous locks, with an accessible confirmation-note field.
Web full regression before the alert change: 234 passed; subsequent alert/Daily
targeted regression: 16 passed. Typecheck and build passed.

S6 adds bounded offline event and annual cash-row research questions using the
existing snapshot, source verifier, disclosed-metric verifier and Mock pilot.
Cross-workflow/changed-transcription reuse refuses immutable old packets. Selected
financial rows are not full financial analysis or approved economic comparability.
Root integration tests: 134 passed. No daily launcher or new current Web packet
is wired by this slice; S6 remains IN_PROGRESS, including live-provider and other
research workflows. S4 risk scenario and full approved-research positive E2E also
remain incomplete. Total Goal ACTIVE; Excel FROZEN; action=no_order.

Port 8001 HTTP responds 200, but the user-restored normal browser tab still fails
the browser URL policy gate. No alternate browser or policy workaround used.
This affects normal-browser acceptance only, not isolated engineering checks.

Follow-up adversarial review found two P2 edges: definitive 4xx fill rejection
must clear the retry body (network/5xx ambiguity still preserves it), and the
backend held-continuity resolver must also match real positive sleeve holdings.
Both are repaired with counterexample regressions. Actual browser scenario
submission after a clearly TEST_ONLY synthetic statement reference exposed an
HTTP 500: the current 000333 plan has null expires_after_session. Missing expiry
now returns explicit PLAN_EXPIRY_MISSING_OR_INVALID instead of guessing an expiry.
The actual retained plan plus isolated journal replay returns BLOCKED, null
quantity and unchanged ledger. This is a repaired error path, not positive
quantity acceptance; rebuilt browser verification and complete scenario success
remain on the continuation list. No synthetic reference entered a real account.

Continuation: verify repaired scenario in the rebuilt TEST_ONLY browser, inspect
why the current plan has no admissible expiry without inventing one, then complete
positive isolated risk/plan/research binding, S5 remaining completed-bar/event
orchestration, S6 launcher/workflows and S7 acceptance. Do not repeat the passed
three-fill bookkeeping exercise or claim full S4/S6/Goal completion.

Rebuilt TEST_ONLY browser subsequently verified the expiry repair: explicit
missing-expiry message, preserved cash/cost/PnL and no quantity, replacing HTTP
500. Screenshot `s4/test-only-scenario-expiry-repaired.png` is that repaired
negative path (not a positive sizing pass). Remote 2f516aee Web/Postgres passed;
Core was 3519 passed / 1 failed / 87 skipped because the old signed-workflow
fixture supplied a schema-less synthetic hotspot plan. The fixture now explicitly
uses the supported independent hotspot plan contract and strategy; production
scope checks remain intact. The complete signed-workflow file passes 16 tests.

## 2026-10-18 interruption audit and S0 start

Previous goal turn: PROGRESS (independent source/runtime audit, counterexamples,
five audit/plan artifacts). That turn did not implement this new product Goal.
Actual starting HEAD d56ae6517b8121ed5677fa566263faf8db295f67 on
codex/web-d1-investment-workbench. Existing untracked full-audit-20261017 evidence
and five audit documents are retained. No source changes existed at this start.
Goal objective read from the user's 064c26dd attachment; no production permission
or real investment approval inferred. action=no_order.

| Stage | State | Evidence / next action |
| --- | --- | --- |
| S0 baseline and requirements | ENGINEERING_PASS | 0e794af Core/Web CI success, runtime MATCHED; browser generic acceptance still NOT_VERIFIED |
| S1 independent strategy/shared risk | PARTIAL | Independent contract/API and bounded daily browser checks; full shared-risk/private acceptance remains |
| S2 value research | PARTIAL | Verified consumed inputs and exact-version external review handoff; economic/materiality/G3 and full browser flow remain |
| S3 hotspot | PARTIAL | Display-only 10-industry/10-case API parity, bounded daily/detail browser checks; zero qualified structures and incomplete full-stage validation |
| S4 private workflow | IN_PROGRESS | Composed TEST_ONLY cross-sleeve BUY/partial-SELL/T+1/restart loop and bounded public/locked desktop/mobile checks pass; real/private browser acceptance remains |
| S5 intraday alerts | IN_PROGRESS | Retained QUOTE/completed-bar bridges; atomic TEST_ONLY history/read/cancel/expiry Web loop, exact 44a7e8cd Core/Postgres/Web CI pass; actual manual monitor/source orchestration and other reminder rules remain |
| S6 Agent/research operations | IN_PROGRESS | Authenticated retained Mock/replay packets connected to stock details with exact source replay; new research workflows and daily orchestration remain; paid live trial separately gated |
| S7 integration/recovery/acceptance | NOT_STARTED | Four viewports, five E2E chains, isolated recovery, latest CI |

Artifacts namespace: artifacts/current/web-first-acceptance/.
Single requirements: product-requirements-web-first-v1.md.
Single final acceptance: web-first-full-product-acceptance.md (not yet passed).

External gates remain: real private inputs/reconciliation, legitimate research
review and event materiality, paid services, production scheduler/deployment/task
changes, natural-time strategy evidence, off-machine/production restore and final
user acceptance. They do not block unrelated implementation.

## S0 verification in progress

Local Web format, typecheck, 210 tests (37 files), and production build all
returned exit 0. Machine receipt: artifacts/current/web-first-acceptance/s0/web-checks.json.
Core workflow-selected regression completed: 2936 passed, 35 skipped, exit 0.
This scope excludes the separate inline M4 rehearsal and PostgreSQL job; skipped
cases are not passed evidence. Public local API /api/v1/daily-public-packet returned HTTP 200 on port
8001. Browser observation was rejected by the browser URL security policy when
acquiring the existing tab; no alternate browser or indirect workaround was
attempted. Actual browser acceptance remains NOT_VERIFIED, distinct from API
health. Commit 0e794af5da982febd688b0bfc78a9d720ece639f was pushed.
Exact-SHA Core run 39111512322 (offline-core and PostgreSQL) and Web runs
39111512457 / 39111508407 all concluded success. Runtime was rebuilt/restarted
and reports source/backend/Web MATCHED with clean source, unchanged publication.
S0_BASELINE_AND_REQUIREMENTS=PASS is scoped to its baseline/requirements exit;
it does not certify generic browser acceptance or S1-S7 product readiness.

## S1 implementation and outstanding acceptance

Versioned independent hotspot gate evaluation and signed release loading now
exist without value valuation/G3 inputs. Authorization uses a distinct purpose,
explicit scope, pinned trust root, current server-owned release, exact evidence
hashes, rule/case binding and availability/expiry. TEST_ONLY cannot be loaded by
the actual API. A bounded independent review found a source-namespace gap;
explicit source namespace/availability and recursive structured-source rejection
were added and re-reviewed with no remaining concrete P1 in that review scope.
Signed claims are not proof of economics or strategy profitability.

The successor projection preserves legacy cases, blockers and snapshots, adds
an independent risk-review status and never grants formal/trade eligibility.
Existing shared risk engine is reused unchanged. Unified public read-model
adapters are connected through /api/v1/strategy-decisions; independent hotspot
conditions use /api/v1/independent-hotspot-conditions. Today-page cards consume
the successor only for the matching publication. No private approval is exposed.

Local API observed six CORE_VALUE objects and five HOTSPOT_SATELLITE objects.
All five real hotspots remain OBSERVATION_ONLY / MISSING authorization, with
formal and trade eligibility false. No real reviewer enrollment or signature
was created. No strategy validation advantage is claimed.

S1 remains PARTIAL pending actual browser acceptance. Source 87339513 now has
Core run 39112633707 and Web runs 39112633714 / 39112629808 SUCCESS, including
PostgreSQL integration; rebuilt/restarted runtime is MATCHED. Receipts bind that
commit and unchanged publication, not the upcoming evidence-only revision.
The final local suite passed 120 Python/API and 212 Web cases; a separate
35-case regression covers additional signature-purpose/scope/retirement negatives.
Browser safety rejection is not bypassed. S2-S7 have
not been declared started or passed. Frozen Excel and production remain untouched.

Final test/evidence revision 334cc10b709eb936f155e8489d3ff3494dbba38e is
pushed. Exact-SHA Core 39112896776 (both jobs) and Web 39112896790 SUCCESS.
Rebuilt/restarted local runtime is MATCHED at this SHA; API still yields five
observation-only hotspots and eleven unified objects. Post-commit observations
are saved locally in the same S1 namespace. The only outstanding S1 stage
acceptance is actual authorized browser interaction; do not infer a waiver or
TOTAL_GOAL completion. Goal remains active and incomplete.

## S1 closure fixes after 334cc10b

The detail endpoint now uses the same versioned independent projection as the
today-page successor, after current-case verification. Invalid/stale evidence
retains nulled prices and cannot gain risk-review eligibility. Historical
packets and original blockers remain unchanged.

A real isolated TEST_ONLY signed pipeline now constructs completed raw bars,
runs the existing collector, case/registry validators and independent signed
release loader. Qualified structure can reach risk review without value/G3;
the actual API never enables TEST_ONLY, and formal/trade eligibility stays false.

Independent shared-risk review found a prospective cyclical IPS-cap omission.
The sizing engine now subtracts aggregate existing cyclical exposure, counting
each symbol once across sleeves. Fee-inclusive proposed capital is constrained
by the remaining cap. The 15/25/40 percent isolated cases yield 0/100/200 shares;
noncyclical behavior is unchanged. Independent rereview found no defect in this
bounded fix. Focused risk regression: 39 passed.

Combined Python/API regression initially passed 154 cases. Commit 501c5972
passed Core 39113592936 but Web 39113593056/39113590291 exposed three legacy
daily/detail contract regressions. The successor is now explicit opt-in via
independent_hotspot=true; the Web client selects it for hotspot detail only.
Default API behavior and frozen packets retain the legacy contract. Expanded
regression includes the entire Web API suite (327 passed). Web checks and
exact corrected-commit CI are being refreshed. Actual browser acceptance remains NOT_VERIFIED: the
selected tab is still a data-URL connection-error page. User recovery was
requested once; no alternative browser/surface bypass is attempted. S1 remains
PARTIAL, S2-S7 are not accepted, and no total-goal completion is claimed.

Corrected source 28a4e9448153074fc0a628518ed1a2de1654c427 is pushed.
Local checks: 327 Python/API, 213 Web, format/typecheck/build all pass.
Rebuilt/restarted runtime is MATCHED with clean source. Actual read APIs verify
five homepage/successor-detail pairs have matching schema, blockers and risk
eligibility; all remain observation-only without real strategy release authority.
Independent bounded static review found no concrete P1 in the opt-in API/Web
boundary: no TEST_ONLY, private-store or formal-eligibility bypass. Fresh CI is
recorded in the existing github-current receipt when concluded. Browser recovery
remains the exact outstanding S1 interaction boundary; no S2 graduation occurs.

Exact 28a4e944 Core 39114093485 (both jobs) and Web 39114089866 SUCCESS.
Duplicate Web 39114093513 remains in progress at last observation. Latest
post-commit runtime/API/CI observations are local receipts in the same S1
namespace; no evidence-only source rebuild loop is introduced.

## Independent S2 input-integrity work while S1 UI remains unverified

Objective section 16 permits independent work during a human/environment wait.
This security/integrity repair does not depend on browser interaction. S1 is
not waived or passed, and S2 stage acceptance is not claimed.

Reproduced the actual Midea package flaw: changing only consumed book equity
or ordinary shares was accepted by v2, despite unchanged summary/source anchors.
Added opt-in source-bound-research-inputs-v3. It inherits v2 provenance/cutoff
and assumption checks, requires complete unique operating-input mappings,
canonical units/scope/basis date, positive values and integral shares, and binds
actual inputs to source anchors. Explicit share basis separates issued shares
from shares excluding treasury. Supported source normalizations are narrowly
deterministic: same-page share-component sum and thousand-CNY to CNY. Unknown,
duplicate, self-referential, nested, mismatched and unconsumed derivations fail.
Official exchange filings are admitted as anchors only under the v3 contract;
v1/v2 behavior and immutable artifacts are unchanged.

Offline actual candidate: s2/midea-consumed-v3 in the existing acceptance namespace.
All ten retained source hashes verify. H1 p7 equity 212861055 thousand CNY
normalizes to 212861055000 CNY; HKEX p2 A shares excluding treasury 6813498835
plus H shares 650848500 equals 7464347335. Derived totals are explicitly marked,
not claimed to be literally printed on the page. Independent local-source
review rebuilt the same descriptor and found no concrete P1 in the bounded
implementation/candidate review. Bear/Base/Bull are unchanged at approximately
36.01/45.74/58.17. Both consumed-input tamper cases are now rejected by v3.

Targeted regression: 213 passed, including source contracts, derived components
and the unchanged residual-income model. Broader Core regression is running.
No current pointer, real approval, price admission, personal position or Excel
was changed. Binding consistency is not financial/economic approval. Remaining
S2 work includes economic research, lawful review handoff and Web acceptance.

S2 source 44996c8e7e30c73889aa626f20a87851d055d8b5 is pushed. Core
39114974369 (offline/PostgreSQL) and Web 39114974270 SUCCESS. Local workflow
standalone-line regression: 3109 passed, 35 skipped; this is not the entire
Python collection or the inline M4/private rehearsal. Local rebuilt runtime is
MATCHED; five independent hotspot details still match current observations.

Timestamp correction: the first offline v3 candidate copied the predecessor's
output timestamps and must not be admitted. It is preserved for audit. The
current offline candidate is s2/midea-consumed-v3-dated/package.json, with a
supersession receipt: actual computed_at/available_at are 2026-10-18T09:24:36.822583Z,
while historical cutoff remains 2026-10-17T10:58:56.051146Z. Source catalog,
model timing and values remain unchanged. Independent replay verifies all ten
local hashes and descriptor 574a7a1b...657cb5c6. Corrected candidate and latest
post-commit receipts are local work pending the next scoped commit; code through
44996c8e is remote. No current-publication or formal-qualification change.

Continuation: do not re-run passed integrity work without a new defect. S1
browser recovery is still pending (one existing user request; do not duplicate
it or bypass the refused data-URL page). S2 economic research/review handoff
and eventual current API/Web integration remain incomplete. All Goal stages
retain their evidence requirements; overall Goal remains IN_PROGRESS.

### S2 source-bound Web draft integration (local, in progress)

The opt-in public-research-draft-v2 loader now verifies the package hash and
complete v3 consumed-input contract, replays the shared residual-income model,
and compares displayed financial facts, assumptions, scenario values, quote and
model validity with those bound inputs. Verification badges are server-derived;
authored badges are removed, including from legacy v1 drafts. Independent
review found a model-validity display-spoof gap; the loader now recomputes the
existing validity evaluator and rejects mismatched status/dates/blockers.

The local read-only draft pointer selects the separately versioned
s2/midea-consumed-v3-dated/public-draft-v4.json. Its predecessors remain intact.
The source bundle retains local official originals; a checkout without these
originals must fail closed rather than display an unverified v2 draft. New
synthetic integration tests use the real descriptor, quote verifier, valuation
and validity evaluator, with no fake research approval. Frontend changes show
capital inputs, share basis, source page, normalization and replay/cutoff time.
Narrative corrections separate H1/FY ROE, FX classification, consolidated cash
flow and model-step years from issuer-distributable cash or economic approval.

Local Web format/typecheck/build and 219 tests passed. Focused Python regression
passed 257 tests including final validity-negative cases; broader regression and
exact commit/runtime/API checks remain pending. No actual browser acceptance, G3,
event approval, formal price admission, private position, Excel or production
schedule has changed. S1 and S2 remain PARTIAL, and the full Goal is IN_PROGRESS.

S2 integration source f7b64043 is pushed: exact-SHA Core 39116150362 (offline
and Postgres) and Web 39116150356/39116147145 SUCCESS. Its rebuilt local runtime
was MATCHED; actual detail API returned the bound v3 draft with source/model
input verification and G3 false, and five hotspot homepage/detail projections
matched. The broad local intermediate regression passed 3134 / skipped 35;
the final focused suite with all validity and assumption drift cases passed 257.
The later v4 narrative-only correction removes a contradictory inherited H1/FY
ROE comparison in counterevidence as well as the already corrected summary;
all model inputs and numeric results remain unchanged. Latest successor
runtime/API/CI must be rechecked after its commit, not inferred from f7b64043.

S3 independent preparation: the existing candidate selector discarded industry
and activity rank, corrupting industry coverage statistics and tie ordering.
The narrow repair preserves verified metadata, rejects explicitly invalid
values and supports legacy missing metadata. Related regression: 93 passed.
It neither collects extra quotes nor completes the nine unassessed structures.
No S3 acceptance, strategy advantage, browser PASS or formal eligibility follows.

Latest code checkpoint: c461e8a9e755afc1daea39635cf431368f27de7e is pushed.
The local rebuilt service reports code/config MATCHED and serves the v4 bound
draft. Five independent hotspot detail projections still match. Latest exact-SHA
Core 39116419282 (offline/Postgres) and Web 39116419314 SUCCESS, independently
queried for c461e8a9 rather than inherited from f7b64043. Post-commit
API/CI observations are retained locally for the next evidence commit.

Exact S2 next engineering gap (read-only independent audit): the public bound
draft is not a registered pending-review candidate. G3 selection in
research_review_wizard.py/user_research_workflow.py only permits candidates
bound to the publication; its registry has 600519/600887, not 000333.
research_materiality_reviews.py also finds neither an incremental scan binding
nor a registered research package for this Midea version. Do not reuse prior
signatures, run a proposal builder that changes inputs, fabricate a review
candidate, or relax complete acquired-scan requirements to make a button work.
Next: adapt the exact v3 package hash/descriptor into the existing consumed
review packet and pending-review contracts, with positive/negative integration
tests before adding any Web signing handoff. The existing packet builder already
checks the consumed workbench/package/descriptor. The actual research scheduler
and full acquired-scan gates must still be honored. This handoff is NOT_DONE;
the visible source-bound draft is not approval-workflow closure.

Continuation commands (PS7, repo root): .tmp/web-first-draft-check.ps1;
.tmp/web-first-hotspot-check.ps1; .tmp/web-first-ci-wait.ps1. Reuse the official
launcher; .tmp/web-first-start.ps1 only wraps it and retains authorization output
privately. Never publish .tmp/web-first-runtime/launch-private.log. S1 browser
recovery remains pending the one existing request; no alternate-browser bypass.

### S2 exact-version review handoff adapter (local implementation)

The next gap above is now implemented for local verification, not yet stage
acceptance. A symbol-neutral adapter retains the verified package bytes and
descriptor, runs the existing workbench through the ordinary scoped scheduler,
and constructs the existing pending-research-candidate-v1/intake contracts.
The explicit engineering replay question is consumed_input_review_handoff;
no new official evidence, economic parameter, prior stop resolution or approval
is invented. Actual Midea replay retains all three active FCFF Evidence Stops.
Its consumed valuation is unchanged and G1/G3/PriceBridge remain restricted.

The existing authenticated handoff route has an explicit bound_draft selector;
legacy publication-based selection is unchanged. Current draft, package,
descriptor, actual workbench and consumed packet must all match. A changed
draft or missing source/candidate returns NOT_READY with no signing commands.
The ordinary CLI now supports --prepare-bound-draft and preserves --preview.
No GET creates candidates or writes review responses. The local registration
uses a separate field in the existing workflow config, not a new approval registry.
No actual reviewer key or real signature was created.

Independent review found and fixed a rehashed-packet deception: packet contents
are now recomputed by a pure projection from verified consumed inputs and
compared in full. Historical packet output shape is preserved. Current v4
interpretation notes are explicitly separate from retained consumed research,
including the H1/FY ROE correction. Positive TEST_ONLY signature consumption
passes without whole-model approval and cannot grant research/price/event
permission. Focused Python: 184 passed; Web: 224 passed plus format/typecheck/build.
Independent bounded review found no remaining concrete P0/P1 in this repair.

Actual local candidate: runtime/bound-draft-reviews/midea-consumed-v3-dated-20261018.
Existing CLI --preview successfully reads three concrete review groups. Direct
wizard returns EXTERNAL_SIGNATURE_REQUIRED, whereas materiality remains
MATERIALITY_HANDOFF_BLOCKED because complete acquired scan coverage is missing.
Committed-runtime API passed on f602e7d52d91ecf86102345a87207f42db720288:
anonymous access returns 401, authenticated handoff returns 200/no-store with
exact consumed materials, no signed reviewer/whole-model approval, and blocked
materiality. Detail retains G3 false and price_admitted false. Exact-SHA Core
and Web CI passed; local broad Core regression: 3172 passed, 35 skipped.
Evidence: artifacts/current/web-first-acceptance/s2/bound-review-api.json,
github-current.json and core-check.json. Browser interaction remains
NOT_VERIFIED; S1/S2 and total product completion are not passed.

### S3 completed-close coverage integration (2026-10-18)

The ordinary refresh CLI now explicitly accepts LAST_COMPLETED_CLOSE_DISPLAY_ONLY;
default SAME_SESSION_B1 is unchanged. It reuses the existing verified collector,
calendar, dual-source quote and completed-bar engines. No backdated acquisition,
PIT, strategy release, price admission or personal permission is invented.

Actual fresh public collection exposed and repaired two additional integration
gaps: the collector omitted the nondefault candidate_pool_limit needed for exact
ranking replay, and the registry reader only recognized the activity top list,
not verified cross-industry pool members. Historical reports remain unchanged.
The independent successor view also removes inherited value-gate wording from
its OPEN explanation without changing legacy case bytes or price calculations.

Fresh dated selection: 10 candidates across 10 industries, all 10 structures
assessed, zero collection failures. Four ACTIVE_ONLY (600150, 600667, 002008,
600019); six CONFLICT_OR_REJECTED; zero STRUCTURE_QUALIFIED_OBSERVATION.
Registry loading verifies all ten active cases and retains four older cases
only as retired observations. Source acquisition is 2026-10-18; market date is
2026-10-16. This is completed-close display coverage, not contemporaneous PIT.
Evidence: artifacts/current/web-first-acceptance/s3/completed-close-coverage.json.
Committed runtime/API/CI verification follows integration. Browser remains
NOT_VERIFIED; S3 is PARTIAL and the complete S0-S7 Goal remains IN_PROGRESS.

Integrated hotspot/current-price/selection/strategy regression: 301 passed,
1 skipped. Independent review found no concrete P0/P1 in this bounded change.
Historical structure tests now bind config/archive/price-conditions-20261017-e65444f2.json,
an exact-byte copy of the retained previous pointer (SHA-256 e65444f2b42130161d02fb5397c15f09061cc0250f77888966f0b48026eb8a8d),
instead of treating the mutable current registry as frozen history. Historical
manifests and their original outputs are unchanged; no retrospective acceptance
or replacement of source evidence is claimed.

3b518b0a3572c3fc829cc2938b5c9cda3e156c0f passes exact-SHA Core/Web CI.
Actual API revealed two further consumer gaps after the collection succeeded:
Web frozen-selection revalidation also needed full candidate-pool membership,
and retired STALE observations poisoned the whole independent opportunity list.
Both are repaired with five API regressions; active STALE/BLOCKED and forged
metadata still fail closed. Retired rows remain in historical/detail views.
The existing daily packet builder published local Web snapshot
pub-8b9016624014e824aa3b; no Excel, server deployment or scheduling was changed.
Final successor runtime/API/CI checks remain pending until that code is committed.

3994e748dc653a11896b37061438a70e053097f5 rebuilt and restarted successfully.
Actual local runtime MATCHED; independent list has 10 current hotspots and
unified list has 16 strategy objects. All ten detail projections match the
list and all formal/trade eligibility flags remain false. API receipts are in
s3/api-smoke.json, detail-api-parity.json and runtime-identity.json. Their stage
label was corrected from inherited S1 helper metadata to S3; measured results
are unchanged. Actual browser remains NOT_VERIFIED, not an API substitute.

### S4 retained announcement coverage and isolated private loop

The held-plan provider now replays exact registered incremental observations,
including retained official response bytes, issuer identity, pagination, full
elapsed window and original document hashes. Authored COMPLETE labels cannot
substitute for that replay. Coverage is limited to the research cutoff through
the plan's verified completed session; earlier reviews remain applicable.

Actual 2026-10-18 acquisition for 2026-10-11 through 2026-10-16 passed for
600519 (zero announcements) and 600887 (two retained original PDFs). Existing
incremental registration was used only after independent raw replay succeeded.
Neither registration grants materiality approval, model revalidation or G3.
Public-only provider probe now reports COMPLETE for those two symbols; 000333
has no exact registered original package and 000651/600741/601088 have no
verified completed-session date in the selected plan. Those remain UNKNOWN.
Evidence: s4/public-coverage-probe.json. No private journal was opened by it.

The TEST_ONLY single-account API loop covers confirmed IPS, both sleeves,
conditional risk preview, manual fill, fees, T+1, history and restart; preview
does not mutate the journal and actual fills invalidate prior reconciliation.
Combined coverage/event/held/private regressions: 140 passed (14.06 seconds).
Synthetic public inputs in the isolated loop do not grant real eligibility.
Actual browser inventory still reports a connection-refused page after the
user's opened-page reply; browser interaction remains NOT_VERIFIED. S4 remains
IN_PROGRESS and the full product Goal remains IN_PROGRESS. No Excel changes,
production scheduling, real signatures or orders were performed.

b501ef5d exact-SHA Core/Postgres passed; Web CI exposed three historical API
assertions requiring an unaugmented plan. The new UNKNOWN coverage and explicit
missing-session reason are now asserted alongside exact preservation of all
original strategy fields. This is a response-contract test update, not a
relaxation of eligibility. Local rebuilt runtime MATCHED; all ten hotspot
detail/list projections and sixteen unified objects remain available without
formal eligibility. Full cross-sleeve BUY/partial-SELL composition is still an
S4 acceptance gap and is being added using the existing isolated HTTP helpers.

After the explicit response-contract update, the complete Web API suite passes:
196 passed in 49.37 seconds. Exact-SHA successor CI remains to be checked.

1851b3b2 passes exact-SHA Core/Postgres/Web CI. Browser connection recovered
by opening a fresh tab in the SAME selected in-app browser after restart; no
security interstitial or different browser was used. Actual daily page loads
the dated value/hotspot rows; Chinese Shipbuilding detail shows 36.450 entry
observation / 34.410 invalidation with unmet admission restrictions. Actual
portfolio page preserves LOCKED/unknown facts on desktop and a 390x844 viewport
(DOM innerWidth 390, document scrollWidth/clientWidth 375; no horizontal spill).
These bounded observations do not pass all stages or real private acceptance.
Screenshots: s4/hotspot-detail-desktop.jpg, portfolio-locked-desktop.jpg,
portfolio-locked-mobile.jpg.

Actual daily UI exposed per-company private-policy requests while locked,
rendering fifteen misleading read-failure tasks. The daily page now passes its
verified private-read state to the existing confirmations component; locked
sessions show one connection path without loading private per-company tasks.
Unlocked-but-uninitialized accounts remain distinct from locked sessions.
Targeted regression passes; full Web suite 225 passed and typecheck passed.
Rebuild and actual browser recheck of this UI fix follow its commit.

The composed TEST_ONLY account loop now covers both sleeves holding one symbol,
same-day rejected SELL, next-session partial SELL, shared cash, sleeve-specific
cost and sellable shares, fees/realized P&L, loss of Top5 membership and restart.
Root focused integration: 16 passed in 2.53 seconds. No account result or risk
engine output was mocked; public market inputs remain labelled synthetic.

3a2ebd34 browser recheck confirms zero repeated confirmation-failure alerts and
one connection path while locked. Receipt: s4/browser-check.json; screenshot:
s4/locked-confirmations-fixed-desktop.jpg. Runtime correctly reports dirty
source during concurrent uncommitted S5 adapter work; exact runtime MATCHED is
not claimed for that moment. Full S4 browser/private acceptance remains open.

### S5 first bounded integration

New pure intraday_conditions adapter consumes an explicit versioned condition
and caller-verified observation; it does not calculate a new strategy, admit a
B1 close, authorize ACTUAL M5 ingestion or grant investment eligibility.
Exchange-calendar/session, lunch, future/stale clocks, completed-bar grid,
observation regression and rewritten-bar checks fail closed. Stable condition/
strategy/rule/cycle event identity suppresses repeated polling and permits
explicit rearming after recovery or a new session. Caller-owned prior state
must be exact and atomically persisted with events; no untrusted HTTP state
input is exposed.

Independent bounded review found no concrete P0/P1 within that trust contract.
Adapter tests: 42 passed. Root adapter + existing M5 persistence/state-boundary
regressions: 77 passed in 2.47 seconds, including SIMULATED disk restart/dedupe
and rejection of ACTUAL execution without the existing authorization.
No source monitor, live data collection, scheduler, alert Web API or user
acknowledgment lifecycle is claimed. Those remain S5 engineering work, not
external blockers. S4 and S5 remain IN_PROGRESS; total Goal remains IN_PROGRESS.

6afa0c22f456681c655cd0925ca8e5cd494c54a7 passes exact-SHA Core/Postgres/Web
CI. Rebuilt/restarted local runtime MATCHED and all ten hotspot detail/list
projections pass again (sixteen unified objects, no formal eligibility).
Post-commit receipts are under s5; the inherited browser-failure metadata was
corrected to reflect recovered S4 public/locked-page checks and the still absent
S5 alert UI. Next concrete work: reuse retained dual-provider quote parsing for
a strict intraday observation bridge, then persist the condition cursor and
events together, expose authenticated alert history/acknowledgment, and test the
manual local monitor. No production activation is authorized or claimed.

### S5 retained source bridge, atomic replay and Web history

Retained dual-source quotes now reuse resolve_session_reference/parse_quote
with strict identity, raw hashes, exact cross-source price agreement, clock,
session/lunch and freshness checks. Actual bounded collection for 600150 stored
three documents with zero request failures; the real Sunday observation is
OUTSIDE_EXCHANGE_SESSION and yields no usable intraday quote or trigger.
Receipt: s5/real-source-negative.json. Provider clocks were not backdated.

The TEST_ONLY monitor commits adapter cursor and existing M5 aggregate in one
fsynced atomic snapshot under the existing interprocess lock. No independent
risk/event engine was rebuilt. Initial untriggered, transition, failure,
recovery, restart, deduplication and failed-write behavior are covered.
Independent review found a P2 recombination gap; latest M5 status/cycle/identity
and session are now cross-checked against the cursor. Fourteen focused monitor/
API regressions pass after that repair. Earlier combined API/source/adapter/
monitor regression: 297 passed. Source bridge and original parsers: 129 passed.

Authenticated read-only /api/v1/condition-alerts and /alerts are connected.
Normal mode truthfully returns NOT_STARTED and never reads TEST_ONLY data.
Explicit isolated mode reads only runtime/intraday-monitor/test-only.json.
The finite scripts/current/replay_intraday_test_only.py replay generated four
labelled isolated events/alerts, no eligibility, no network or monitor process.
Web hides responses from a previous mode while changing mode, preventing a
TEST_ONLY response from briefly appearing as a normal reminder. Web suite:
228 passed; format and typecheck passed. Commit-specific build/runtime/browser
and CI verification follow integration.

S5 remains IN_PROGRESS: actual local monitoring, legitimate ACTUAL persistence,
completed-bar acquisition, alert acknowledgment/cancellation/expiry and full
interactive acceptance are not implemented by this read-only history step.
S6/S7 remain open; the total Goal is not complete.

### S5 local-page reading acknowledgment

Actual ced4e602 browser checks verify desktop/mobile history, unchanged count
after refresh, and strict mode separation: four isolated records become zero
in normal mode. Mobile 390x844 has equal document scroll/client width 375.
See s5/browser-check.json and screenshots. Normal monitoring remains NOT_STARTED.
Exact-SHA Web/Postgres CI passed; offline-core failed and is being repaired.

The successor reuses M5 SENT/DELIVERED/ACKNOWLEDGED transitions to record a
user's explicit local-page reading confirmation, never external notification
delivery or investment approval. Scoped alert identifiers, snapshot comparison,
atomic persistence and idempotent receipts protect concurrent/stale actions.
Authenticated Web POST cannot select a path, namespace or clock; the UI requires
confirmation and refreshes persisted results. Initial API integration: five pass.
Actual successor browser verification and CI follow the scoped commit.
Existing M5 has no CANCEL/EXPIRE/RESET transition; those are explicit engineering
gaps, not disguised FAILED_TERMINAL states or external authorization blockers.
S5 remains IN_PROGRESS, including actual monitoring/completed-bar acquisition.

Offline-core failure reproduced as the omitted replay command's architecture
inventory/CLI registration, not a strategy or source-validation failure.
Both registries are now updated; architecture regression: 30 passed. Root's
combined S5 and complete Web API regression: 300 passed; isolated acknowledgment
regression: 16 passed; Web: 228 passed, typecheck/build passed. Exact successor
CI and actual acknowledgment browser checks remain pending at this writing.

b061bfd2f1dceead534f115081d37588cc1fbbcd subsequently passed exact-SHA
Core/offline, Postgres and Web CI. Actual browser confirms explicit reading,
one persisted ACKNOWLEDGED alert across page reload, four unchanged records,
normal-mode isolation and no mobile horizontal overflow. The bounded evidence
does not establish real monitoring or research/investment approval.

### S5 notification lifecycle and completed-bar source bridge

The existing M5 outbox now has a nested v2 for CANCELLED/EXPIRED with immutable
reason, deadline and evidence identity; old v1 payload/IDs remain unchanged.
Termination does not increment delivery attempts, reopen an alert, remove a
human-review requirement or turn degraded source coverage into healthy status.
Monitor actions remain TEST_ONLY, authenticated, snapshot-checked and atomic.
Cancellation stops the notification only. Explicit expiry uses server-owned
intraday-alert-session-expiry-v1: price-observation notification deadline is
15:00 Shanghai on its detected exchange session. Source-health notifications
cannot use this expiry policy. Historical notifications were not previously
declared to have this deadline; an explicit successor action binds the policy.
New condition cycles can create a new alert without reopening the old one.

The retained Sina 15m/60m bridge reuses parse_klines with an explicit optional
completed-through cutoff; historical default parsing retains full-close
requirements. Raw hash, URL/security/period, receipt clock, exchange calendar,
completed grid and freshness reject invalid or unfinished bars. Single-provider
limitations and no B1/formal eligibility remain explicit. No live collection
or ACTUAL monitor is implied. Web displays original condition price/direction,
Beijing times and source links separately from investment permission.

Root integration: 405 passed; existing M5 regression: 280 passed / 23 skipped.
New lifecycle tests are included in Core CI. Actual successor browser actions,
commit CI and runtime checks follow integration. S5 remains IN_PROGRESS;
manual actual monitoring/source orchestration and other S5 rules are still
engineering work. S6/S7 remain open; total Goal IN_PROGRESS, Excel FROZEN.

44a7e8cd exact-SHA Core 39124449266 (offline/Postgres) and Web
39124449183/39124446256 succeed. Rebuilt/restarted code/config runtime MATCHED;
ten hotspot detail/list projections and sixteen unified objects remain available
without eligibility. Actual browser performs CANCEL and EXPIRE, reloads all four
records with ACKNOWLEDGED/CANCELLED/PENDING/EXPIRED, then returns to normal mode
with zero simulated records. Source-expanded mobile viewport remains 375/375
scroll/client width. Independent bounded review finds no concrete P0/P1/P2.
Evidence: s5/lifecycle-validation.json, browser-check.json and screenshots.

Precise continuation: retain this branch and existing launcher at port 8001;
do not repeat source/model redesign or frozen Excel work. Next S5 task is
manual real-source monitor orchestration and its Web running/stopped lifecycle.
Reuse retained quote/bar bridges and M5 infrastructure, but do not bypass the
existing signed ACTUAL ingestion boundary or relabel SIMULATED records as real.
Exercise positive behavior with isolated clocks/data and real negative behavior
with actual source clocks; no waiting for a future session to continue coding.
Then connect remaining reminder inputs and continue S6/S7. Missing real user
inputs/signatures and production permissions stay separate from engineering.

### S5 bounded local real-source observation session

The normal authenticated reminder page now offers manual START/STOP for one
currently verified public candidate. This is a source-observation session, NOT
an ACTUAL M5 ingestion run or a formal condition alert. It reuses the retained
dual-provider collector and quote verifier, records immutable raw bundles and
hash-bound replayable reports, and never changes publication/private ledgers.
The process-local worker is cross-process locked, limited to ten samples with
60-second intervals, and never restarts automatically. STOP binds the displayed
session identity; an old page cannot stop its successor. In-flight requests may
finish archiving after STOP; the UI reports STOPPING until they finish. Service
shutdown admits no further requests. GET never starts collection or creates files.

Actual Sunday browser collection for 600150 retained Tencent/Sina sources and
correctly returned OUTSIDE_EXCHANGE_SESSION, then stopped. No backdated quote,
formal alert, M5 authorization or investment admission was manufactured. The
existing TEST_ONLY M5 lifecycle remains isolated and unchanged. This is a bounded
S5 source/lifecycle increment; actual price-condition orchestration, remaining
reminder types, S6 and S7 are still open. S5 remains IN_PROGRESS, total Goal active.
Final tests/browser/restart/CI evidence accompanies the scoped commit.

### S5 plan-reference binding and S6 retained research read model

Existing current plans now bind server-side to bounded public quote observations.
The binding preserves original rule, evidence hashes, expiry and blockers. Each
sample replays its condition state against retained raw sources; repeated states
do not create duplicate transitions. Reference crossings remain unadmitted
observations, never completed-bar confirmations or formal investment permission.
Candidate-list errors preserve the live session identity and STOP operation.

The authenticated stock detail can read exact registered retained AI packets,
including three roles, original citations, counterevidence and follow-up. The
initial actual binding is historical 600519 MOCK research with cutoff 2026-10-08;
it is neither fresh analysis nor claim-semantic approval. No provider is called.
Missing, replaced or corrupt materials never upgrade research or eligibility.

Integration: 328 backend tests passed; 232 Web tests passed; typecheck/build
passed. The candidate-error STOP regression plus authenticated route tests pass
(10 tests). One initial targeted run omitted the required TEMP/TMP setup and
failed fixture isolation; the corrected environment passed without changing gates.
Committed-build browser/restart and exact-SHA CI must be recorded separately.
S5 and S6 remain IN_PROGRESS; full Goal is active and Excel remains FROZEN.

### S6 explicit daily Mock batch integration (2026-10-18)

The existing research CLI now accepts a SHA-256-pinned bounded batch plan
(`daily-agent-mock-batch-v1`, MOCK/no_order only). It calls existing event and
financial use cases independently, prevalidates distinct runtime-only outputs,
and distinguishes missing inputs from failed jobs. Existing immutable pilot
reuse/source verification is preserved. No automatic registration or approval.
The existing daily PowerShell entry accepts `-ResearchMockPlan` and
`-ResearchMockPlanSha256`; research failures add notes without stopping public
data updates. No second launcher, scheduler, provider or Excel operation.

Local real retained-original run: 600519 event DRAFT_READY, financial
BLOCKED_INPUT (missing comparable-period transcription), overall PARTIAL.
Research cutoff remains 2026-10-08; this is historical MOCK, not new current
investment research. Actual READ_ONLY/NoServer daily entry completed PARTIAL,
published verified display snapshot pub-9b49ff2e54323150a06d, and kept formal
admissions at zero. Local plans and receipts are untracked:
`.tmp/s6-research-batch.json`, `.tmp/daily-workbench-research-latest.json`,
`.tmp/daily-workbench-latest-run.json`. Generated runtime files stay untracked.

Verification: 98 relevant Python/Windows entry/architecture tests passed; after
the final batch-pin and child-failure tests, five targeted tests passed.
The real CLI returned exit 3 as designed for PARTIAL; its containing shell
reported exit 1 for the nonzero child code, not a pytest failure.

Browser remains NOT_ACCEPTED: current IAB tab inventory still reports an
ERR_CONNECTION_REFUSED data error page despite user reopening. Direct local
HTTP /daily was 200, and runtime identity matched 6b47fe9b before this patch;
neither proves current UI interaction acceptance. No browser-policy workaround.

Remaining: daily draft registration/display handoff, hotspot research workflow,
complete daily/after-close orchestration, full positive browser closure and S7
restore/responsive acceptance. Independent static review also identified an
existing single-instance/receipt concurrency gap in the daily launcher. It is
now repaired with an exclusive file handle before receipt writes and release
before the long-lived Web service. A concurrent real pwsh process returns BUSY
without changing the active receipt. Unexpected Web startup failure preserves
the completed update receipt. Final entry/CLI regression: 37 passed (one
previously passed slower offline-failure test deselected); final lock/research
failure/core-unavailable checks: three passed. Independent implementation review
found no confirmed new P0/P1. New patch is not yet committed or
covered by exact-commit remote CI. S6 remains IN_PROGRESS; total Goal incomplete.

### S6 verified draft-to-Web handoff

The same research CLI now supports explicit `--register-drafts` with a pinned
batch plan. The existing daily entry forwards `-RegisterResearchDrafts`; it is
not enabled by default. The application registrar reuses the exact Web verifier
against a temporary candidate registry, preserves failed jobs' previous entries,
retains the previous registry by content hash, serializes cooperating writers,
and atomically changes only the display pointer. All registered packets remain
MOCK drafts with zero approvals and no formal eligibility change. Public GET
still reads only the fixed server registry; no arbitrary-path API was added.

Example against the retained local plan (historical sources, no live model):
`pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode READ_ONLY -NoServer -ResearchMockPlan .tmp/s6-research-batch.json -ResearchMockPlanSha256 7b7d13f719a644d20d86c7b5d85bf3dde7a25e70c788937728e8242ea47ad466 -RegisterResearchDrafts`.
Use the actual plan hash if its bytes differ. This command is display-only and
does not approve G3, event materiality, facts, risk capacity or orders.

Independent subagent added 19 source-contract registration tests, all passed;
related full Web API/research/architecture regression: 356 passed. Existing
reader/CLI tests: 72 passed. Real retained600519 batch with explicit registration
returns PARTIAL: event UNCHANGED, financial SKIPPED, zero new registrations and
zero approvals. Failed/tampered candidate tests preserve the previous good Web
view, including when the attacker recomputes a packet hash. Final entry regression,
exact-commit CI and rebuilt runtime evidence are recorded after integration.
This closes the optional event/financial display handoff, not all S6 workflows.

### S6 retained official financial inputs now connected

Successor investigation closed the actual financial-draft input gap for the
retained 600519 snapshot. Official 2025 annual report cninfo:1225114741, SHA-256
474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288, physical pages
64-65 were text-extracted and visually checked. The 2025/2024 consolidated CNY
operating cash-flow and cash-capex rows pass the existing transcription verifier
(four numeric row observations). A separate source-record view provides only the
already verified original catalog, explicitly not a financial research result.

CLI batch plan `runtime/agent-research-s6-financial-20261018/batch-plan.json`,
SHA-256 e21b71d1e3aa09363988eabbf6f93d61c5b98c5ebb7a07a6c06032310a329884,
returns SUCCESS with explicit display registration UPDATED. Authenticated real
loopback API now verifies financial/event/legacy separately, three questions each.
The financial packet binds transcription, source view, exact excerpts and the
unchanged 2026-10-08 research fingerprint. These are historical MOCK research
questions, not current financial admission, normalized parent earnings, approved
accounting comparability, G3 or new valuation. No original or runtime file is
tracked in Git. Evidence: s6/retained-financial-validation.json and local
s6/workflow-api-validation.json. The old missing-input plan remains a valid
negative example; its missing transcription is not silently filled.

Engineering commit faf0486e passed exact-HEAD Core/offline, PostgreSQL and Web CI.
Its local rebuilt backend/Web identity MATCHED; real authenticated API passed.
First verification immediately after restart hit a local harness log-read race;
the live launcher was confirmed, fresh bootstrap readiness checked, then the same
API check passed. The local helper now waits for fresh bootstrap output. This is
not a browser acceptance claim. S6 remains IN_PROGRESS (hotspot Agent and complete
daily operational integration pending); S7 and the full Goal remain incomplete.

### S7 scoped actual isolated public-chain restore

Existing `run_closure_restore_drill.py` ran against current local publication
pub-9b49ff2e54323150a06d into `.tmp/web-first-s7-public-20261018`, with fresh
local AES-GCM drill key separate from the package directory. Receipt:
`artifacts/current/web-first-acceptance/s7/public-chain-restore.json`.
24 source files copied, 28 restored files verified, no missing/mismatched files,
publication identity matched, the historical workbook copy matched its existing
pointer, and a corrupted encrypted copy was rejected. Original Excel was only
read; no server, production database, scheduling or offsite transfer was used.

This is ONLY the existing public-chain restore scope. Its legacy
OFF_MACHINE_BACKUP_READY field is packaging readiness, not independent-machine
retrieval; REAL_OFF_MACHINE_COPY_CONFIRMED remains NOT_CONFIRMED. The existing
selector does not yet close the complete Web-first recovery inventory: new
Agent registry/inputs, alert history, private ledger/strategy records and database
recovery need separately bound coverage and acceptance. Do not mark S7 or full
product recovery PASS from this receipt. Latest engineering/config commit is
b98f49e3; rebuilt local code/config/Web identity MATCHED and authenticated
financial/event/legacy reads VERIFIED. Exact latest-SHA CI is checked separately.

Final latest-SHA verification: b98f49e3 Core/offline, PostgreSQL and Web CI PASS;
rebuilt local identity MATCHED; authenticated three-workflow API PASS. The final
actual Windows offline-failure regression passed (1 test); retained financial
replay returns SUCCESS without changing packet bytes or modification time.
Current scoped receipt: s6/current-batch-handoff-closure.json. These latest local
receipts and the scoped restore addendum are preserved in the worktree for the
next substantive integration, without creating an evidence-only commit loop.

Scoped service/API final tests: 45 passed; source plus complete Web API regression:
371 passed; Web full regression: 229 passed, final targeted test: 4 passed,
typecheck/build pass. Browser confirms explicit real collection for 600150 and
000333, automatic non-session stop, 600150 history after restart, source expansion,
and 390x844 viewport without horizontal overflow (375/375). Real browser manual
STOP was not exercised because collection finished first; in-flight STOP and stale
session rejection are covered by injected service/API regressions. Independent
review's stale STOP finding is fixed and rechecked. Initial remote Core failed
because one folded YAML command line was over-indented; 34588e40 fixes that
workflow invocation, without changing any test or investment threshold. Successor
exact-SHA CI evidence is recorded separately; no previous CI pass is substituted.

## 2026-10-19 Four business loops successor

Latest explicit user scope: VALUE-INVESTMENT-FOUR-BUSINESS-LOOPS-V1. This
existing ledger remains the single execution authority; there is no competing
four-loop task ledger. Web-first, Excel FROZEN and permanent action=no_order.

G0 baseline: b98f49e3f84bac8a0e044adfff89c3341e2422d7 on
codex/web-d1-investment-workbench. Exact baseline CI: Core 39136610119 and Web
39136610159 both SUCCESS. Existing dirty s4/s5 acceptance receipts, public
snapshot pointer, acceptance/ledger text and untracked prior audits were
recorded and preserved. Public snapshot is pub-9b49ff2e54323150a06d, quote
session 2026-10-16, research cutoff 2026-10-11; those dates are not advanced by
starting development on 2026-10-19. Source/config/runtime versions remain
separate. No real private account has been entered by the agent.

| Loop | Actual baseline | Current concrete work | Gate |
| --- | --- | --- | --- |
| G1 hotspot | Ten cross-industry completed-close observations; bounded live quote worker and plan-reference transitions exist, ordinary alert API always empty | Extend same replay-verified observation store with inbox, reading lifecycle, deduplication and cross-session history; connect completed bars | IN_PROGRESS |
| G2 portfolio | Append-only ledger, dual sleeves, fills/T+1/restart exist; previous browser case does not prove registered-plan sizing | Reject expired sizing plans and cross-sleeve thesis capture; complete real-contract TEST_ONLY sizing/fill rehearsal | IN_PROGRESS |
| G3 value | 000333 original-bound draft, shared residual-income arithmetic, unresolved economic/materiality/G3 gates | Render available financial facts and verify model diagnostics; preserve true blocked admission and signed isolated positives | IN_PROGRESS |
| G4 Agent | Financial/event Mock batch and verified draft registration exist; hotspot/retrospective disconnected | Reuse provider/batch/registrar for four work types and source-driven context export | IN_PROGRESS |
| G5 integration | Scoped older HTTP/browser/recovery receipts exist, not complete four-loop acceptance | API, actual browser, restart/replay, shared regression and exact-commit CI | NOT_STARTED |

Machine receipts for this successor live only under
artifacts/current/four-business-loops/. Engineering, source quality, human
approval, actual personal input, live model authorization and prospective
strategy validation are reported independently. No loop is marked PASS from
interface existence or a test count alone.

### Four-loop delivery checkpoint, 2026-10-19

The implementation slice for G1-G4 is present in the working tree and passes the
local regression gates, but no complete investment loop is being represented as
production accepted. The five required machine receipts now exist and all carry
`status=PARTIAL`: `hotspot-loop`, `portfolio-loop`, `value-loop`, `agent-loop`
and `web-integration`.

Actual state:

- G1 has completed-bar observation, deduplicated reminder inbox, lifecycle and
  restart recovery. The current public packet remains observation-only with no
  formally admitted hotspot or positive real-session chain.
- G2 has deterministic dual-sleeve sizing, fees, fills, T+1 and restart replay.
  The accepted browser case is TEST_ONLY. Real IPS/portfolio/cash, broker
  reconciliation and price admission remain unavailable.
- G3 has source-bound financial facts, valuation diagnostics and five-action
  contracts. The current 000333 research still has model validity UNKNOWN,
  PriceBridge INVALID and no formal economic or G3 approval; action remains
  `no_order`.
- G4 reuses the existing provider/registration path for event, financial,
  hotspot and retrospective workflows. Only Mock drafts and TEST_ONLY
  retrospective inputs have been executed; no paid live model call or formal
  fact approval is claimed.
- G5 is integrated in the authenticated Web shell with static browser evidence,
  but complete same-commit five-workflow interaction and off-machine recovery
  remain unproven.

Local verification for this checkpoint: targeted four-loop regression `75
passed`; full Python regression `6662 passed, 44 skipped`; Web `251 passed`;
Prettier check, TypeScript check and production build `PASS`. Exact-SHA remote
Core/Postgres/Web CI is deliberately recorded only after the delivery commit.

Current P0 list is empty. Known P1 issues remain: the manual-fill path can record
a broker-confirmed cross-sleeve fill before the downstream projection reports
`SLEEVE_CASH_OVERDRAWN`; portfolio and held-continuity reads are slow; Agent PIT
is date-level rather than exact timestamp-level; live sessions, private inputs,
human research approvals and final browser acceptance are still missing. These
limits are why every loop receipt is PARTIAL and why the overall Goal is not
complete. Excel remains frozen and `action=no_order` remains permanent.

## 2026-10-20 Dual-strategy actionable decision V2

User successor: DUAL-STRATEGY-ACTIONABLE-DECISION-V2. Actual HEAD at entry is
e435d1fcb7f9636c6c540f7c61e3372c6cbf1c00, not the older b98 baseline. Exact
baseline Core run 39212011280 and Web run 39212011327 both SUCCESS. Existing
s4/s5 receipts, snapshot pointer and untracked audits were already dirty and
are preserved; they are not new delivery evidence.

Read-only actual application audit: the current publication reports universe
5573, research leads 114 and formal admissions 0. Its 29 displayed companies
cannot currently establish complete actionable eligibility. This is incomplete
evaluation, NOT evidence that the whole market has no opportunities. The live
public route was exercised with a temporary in-process operator session; no
account, approval, original workbook or production service was changed.

Concrete successor work: latest-report financial field consistency and missing
versus rejected channel semantics; structure-evidence-first observation ranking;
pretrade sleeve capacity and post-fill overspend disclosure; shared plan-derived
public evaluation and actual-account conditional decision output. Display
projections cannot approve research or mint personal capacity. Private action
assembly is separate from public read-only NO_TRADE explanations. TEST_ONLY
positive contracts do not establish real company investment readiness.

Verification is ongoing. Do not inherit the baseline CI pass as validation of
this working tree, and do not mark the V2 Goal complete from these changes.

V2 audit corrections to the previous checkpoint's "P0 empty": actual execution
still had three code gaps, not just external gates: legacy hotspot plans could
not reach the independent risk contract; CORE had scenario-only sizing; held
continuity unconditionally requested thesis/announcement review instead of
consuming the full authorized continuity chain. The first two are being wired
to existing verifiers/engines. The held-decision gap must not be described as
only missing personal input or waived by displaying NO_TRADE.

Retained-source re-evaluation (NOT a current market publication): annual rows
adopted 16480, of which 6206 already verified statutory facts; general-enterprise
annual-period coverage 43 -> 659. Actual nonquote financial coverage is 728,
not the earlier 873 which included quote-only records. Quality outcomes remain
0 PASS, 5452 DATA_GAP and 121 UNSUPPORTED; 775 earlier rejections were actually
missing evidence. Lead count remains 114. Full financing debt and verified
ROIC have not been manufactured. One official 600741 annual PDF was fetched
again and matched its retained SHA; this verifies those original cash/ROE rows,
not all financial quality or investment eligibility. Bounded evidence is under
runtime/screening-A-20261020-v1/, with source and implementation hashes.

### Actual close update, 2026-10-20

The unique SAFE_REFRESH entry completed SUCCESS twice, with the second run
reusing the admitted-date quote observations and completed structure cases.
Both runs resolve the SAME publication pub-9b63d8aae9b265fdcf6a (SHA-256
69e1e9adbc287c9f507bcc30ec4dcd58451c4b6b1cf5524e2e10149097f10cd3).
Six existing value securities now have verified 2026-10-20 dual-source closes;
this does not repair their economic/model/event admissions. Five current
hotspot observations are 300821, 300308, 002242, 300012 and 688825, all WATCH,
formal eligibility false. No broker action, private ledger write or Excel
publication occurred.

The real M2 input run covers 5575 securities, with 111 deduplicated research
leads: quality 0, value/dividend/cyclical 50 each before deduplication. Its
provider trade-date qualification remains unverified, so it is research-only,
not a current formal investment universe. The previous published research
list still contains 114 historical leads. The Web update receipt separately
hash-binds the latest scan manifest instead of silently replacing that
published research authority or counting new leads as completed research.

The previous full regression reached 6751 PASS / 44 SKIP with one CLI-size
architecture failure. Financial-export/timestamp replay helpers were moved
from the root CLI into the existing screening infrastructure; the threshold
was not raised, and 58 related tests pass. The legacy READ_ONLY test now runs
in an isolated project and proves the actual pointer/latest receipt unchanged
(4 tests PASS). Agent replay fixtures pin retained metadata, while expiry
negatives still use a later clock; a market update must not invalidate an
offline fixture or make historical tests appear current.

Personal decision boundary: BUY requires the actual registered plan and risk
contract; simulated accounts remain vetoed. ADD additionally needs a dedicated
observed add condition and the user's original thesis ownership. That durable
confirmation adapter does not yet exist, so current ADD is NO_TRADE with an
explicit CODE_GAP, not a fabricated positive. Held HOLD/REDUCE/EXIT similarly
remain unaccepted; the new strict entry/consistency validator alone is not a
completed personal decision workflow. Final V2 acceptance remains NOT_PASSED.

Browser continuation verification: rebuilt the current working-tree Web bundle,
restarted only the repository-owned loopback 8001 process through its existing
launcher, and verified the actual API-backed daily -> 000333 detail -> portfolio
-> history -> daily route. The current daily shows 2026-10-20 quote dates,
5575 scanned / 111 research leads, and separately 5 evaluated NO_TRADE / 15
NOT_ASSESSABLE in the published-company scope. The demo account remains revision
7 and is visibly TEST_ONLY; no form or journal confirmation was submitted.
At viewport width 390 the document width is 375, without horizontal overflow.
Screenshots: artifacts/current/dual-strategy-v2/daily-current-20261020.png and
daily-current-mobile-20261020.png. These are working-tree product checks, not
economic approval or final user acceptance. Private reads and evidence-backed
pages can remain in loading state for a noticeable interval; latency remains
an observed usability risk, not a passed performance acceptance.

The existing Core Research Gates workflow now includes the new versioned
screening, CLI integration, retained hotspot selection, personal entry contract,
held code-gap, decision read-model and refresh-readiness tests. This is CI
configuration only; the baseline green run is not evidence of new-source CI.

Continuation verification result: full Python release regression returned
6801 passed / 44 skipped / 10 failed in 1363.70 seconds. All ten failures were
isolated Windows CLI fixtures whose mock M2 child omitted the newly mandatory
manifest, correctly causing BLOCKED/PARTIAL instead of their expected states.
The fixtures now materialize their isolated manifest and assert its recorded
hash; an explicit missing-manifest negative was added. The entire affected
file then passed 18 tests in 62.33 seconds. No production logic was loosened.
The full suite was NOT rerun after this test-only repair; do not call this a
single all-green full run. Web repeat: 42 files / 261 passed; build PASS.
Changes remain uncommitted, and latest-source GitHub CI remains NOT_RUN.

## V3 continuation, 2026-10-21

Inherited baseline remains e435d1fc plus the V2 dirty tree, not a clean submitted
release. Public outcome assembly now lives under application/decision with a
documented presentation compatibility shim. UNASSESSABLE is distinct from a
calculated NO_TRADE in public and private outcomes; no unowned holding becomes
HOLD or ADD. Targeted public/API/architecture tests: 94 PASS; risk and integrated
action contracts: 127 PASS; combined resumed target set: 283 PASS. Current Web:
262 PASS, typecheck/build PASS. A new full regression is running, not yet passed.

Three real retained 2025 annual sources were extracted and re-evaluated with
original hashes/periods retained: 600519 (17 candidates, 14 retained matches),
600887 (16/13), 600741 (15/5). Complete debt scope remains DATA_GAP in all three;
no missing bucket is zero-filled and candidate matches are not new E3 facts.
Independent source backing bytes, PIT and classification are required before
adopting scope into an already verified aggregate. Frozen quality/scoring and
historical engines have not changed. Evidence summary is in the V3 artifacts.

The v2 research scheduler reuses the validated v1 discovery inputs, separates
complete-quality research from evidence work, and labels unknown valuation,
dividend durability, business quality and events rather than scoring them.
The existing daily entry has an explicit -BuildValueResearchPriority switch,
valid only with SAFE_REFRESH. READ_ONLY cannot start this work. Actual controlled
execution on 2026-10-21 returned SUCCESS: universe 5576, deduplicated leads 111,
quality 0, selected enrichment 10, complete-quality deep research 0. This selects
work; it does NOT claim all ten companies have been enriched. Market-wide date
qualification remains UNVERIFIED_PROVIDER_TRADE_DATE. Verified value/hotspot
closes remain 2026-10-20, not today's intraday prices. Publication:
pub-21cd20169c8e3ae9c899. No Excel/private journal/server/scheduler change.

Hotspot observation continuity verifies retained registry/case/watch originals,
distinguishes activity-only exclusion from expiry/invalidity, and never grants
price admission. Existing refresh now archives a snapshot and attempts this
comparison; missing historical evidence reports UNASSESSABLE without suppressing
independently valid prices. Replay and integration remain distinct from a
completed current cross-day production/browser acceptance. Existing candidate
and held-monitoring gates remain unchanged.

Remaining real engineering is not hidden as an authorization gap: automatic
execution of the entire enrichment queue, admitted source revisions/re-ranking,
personal entry ownership and held advisory handoff, and complete cross-day Web
history are NOT finished. G3/strategy release/private IPS and external account
reconciliation are separate human/data dependencies. V3 final acceptance is
NOT_PASSED; current work must not be described as a closed real trading product.

### V3 bounded enrichment execution

An explicit -ExecuteValueEnrichment option now requires SAFE_REFRESH plus
-BuildValueResearchPriority. It invokes the existing queue CLI with an execution
budget of two (service maximum three). The application replays the queue from
its bound original inputs, downloads only a registered official annual URL with
an expected hash through the existing bounded PDF adapter, caches immutable
originals, extracts candidates and runs the unchanged quality scorer. Each issuer
gets an immutable result and failure/reopen reason; no fact or approval is minted.
READ_ONLY cannot reach this network path. Queue execution is not automatic full
coverage, admitted fact persistence or completion of deep research.

Actual execution initially exposed a parser error: two genuine annual reports
put their labelled stock code on page six, not within the first three pages.
The adapter now verifies explicit labelled code within the first twelve pages,
retaining the report-year/Hash checks and rejecting a different labelled issuer.
With no network permission on the rerun, both cached originals were reused:
000589 extracted 16 / matched 15; 000612 extracted 17 / matched 16. Both remain
DATA_UNAVAILABLE for complete financial quality due to debt-scope gaps, not
because extraction failed. The initial failure and repair receipts both remain
under runtime/value-evidence-enrichment/runs/. No original was deleted or redated.

The full regression snapshot completed 6863 passed / 44 skipped in 1112.14s.
The bounded executor and final parser/summary changes were made after collection
and are covered separately by 80 passing targeted tests; do not pretend that the
earlier full run covered every subsequent change. Latest-source CI and committed
browser acceptance still need verification before any release claim.
