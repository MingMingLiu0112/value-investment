# Adversarial Findings - 2026-09-25

Read-only adversarial review baseline: 2135be59. The architecture-only
cleanup commit c87bc1c did not change valuation formulas, investment gates,
database schema semantics, or action=no_order; these findings remain open
unless a later verification receipt says otherwise.

## P0 Findings

### ADV-P0-001 - M3 replay accepts future evidence

m3_historical_research_replay.py validates the future_facts_used boolean,
but does not compare each fact, filing, quote, or evidence reference
availability time with the replay date. A replay can therefore display a
later filing or quote as if it were known on the replay date.

Minimum fix: add an independent replay-time verifier that checks exact
available_at <= replay_date, validates quote dates and evidence hashes, and
rejects future disclosures, quotes, and price files with negative tests.

Status: OPEN_NOT_FIXED.

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

Status: OPEN_NOT_FIXED; current first-case conclusion remains
NOT_PIT_SAFE / NOT_ADMITTED.

## P1 Findings

### ADV-P1-003 - M5 ACTUAL authorization can be constructed locally

M5ActualOfflineAuthorization accepts caller-provided hex strings and the
guard checks only dependency-graph equality. It does not verify an external
human approval or reread the reviewed bytes.

Minimum fix: make ACTUAL capability issuance depend on a separately verified,
byte-bound approval receipt and add forged-hash negative tests.

Status: OPEN_NOT_FIXED.

### ADV-P1-004 - M6 proof can be forged inside the Python process

OperationalAuthorizationProof._issue is callable by ordinary code and
persisted control state is not revalidated against the signed authorization
bundle on every read or transition. The normal CLI path fails closed, but the
domain API is not an unforgeable capability boundary.

Minimum fix: use a signed token or non-exportable capability, bind persisted
state to the original authorization bytes and trust root, and reverify on
read and transition.

Status: OPEN_NOT_FIXED; no Shadow or production action has been started.

## P2 Findings

- Legacy simulation state still exposes review intents that are not orders,
  but the virtual account path consumes state rather than a universal
  action=no_order invariant. Add an explicit simulation-only order contract.
- M4 private-intake RECONCILED currently accepts a CLI-supplied confirmation
  id and timestamp without an independent external receipt. Keep private data
  out of Git and require a byte-bound confirmation before calling it actual.
- CI runs a selected core test list, not the full suite and not every negative
  authorization/PIT counterexample. Add the smallest deterministic negative
  tests to CI and report real-data-only checks as not run.

## Permanent Semantics

action = no_order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Backtest != M6 Shadow

## Next Task

NEXT TASK: PIT_CONFORMANCE_VERIFIER_V2

Goal: independently verify point-in-time availability, quote dates, evidence
coverage, benchmark version, universe, and survivorship before any historical
replay or admission result can be consumed. It must reuse existing engines,
leave the frozen historical-validation bytes untouched, and remain read-only
with respect to production and private data.
