# External Gate Handoff

Current handoff date: 2026-09-26. This document records remaining external
gates; it is not an authorization request. Every path remains `action=no_order`.

## Current System State

- M2: DONE, with Checkpoint A `HUMAN_PASS`.
- M3: waiting for real contemporaneous evidence; historical replay is not strict PIT proof.
- M4: ready for deliberately supplied private R2 input; no private input is present.
- M5: event-to-product projection engineering passes supported states; a real current operational observation waits for R3 and R6.
- M6: operationally not started; `shadow_start_allowed=false`.
- M7: stable canonical user trial is ready; final acceptance is not yet due or passed.

## R2 - Private Portfolio Input

The user would provide the scoped IPS, portfolio snapshot, cash/liquidity
constraints, concentration limits and dividend objective through the existing
private package path. It stays outside Git, public runtime, CI artifacts and
the canonical workbook. The system would encrypt, reconcile and wait for human
confirmation; it still creates no order or delegated investment decision.

## R3 - Production / Infrastructure Decisions

Each item requires a separately scoped future decision and validation:

| Area | Decision needed | Validation after a decision |
| --- | --- | --- |
| Server resources | Release capacity, resize host, isolate host, or reduce workload | PTA baseline plus memory headroom |
| Disk capacity | Make enough bounded write space available | Reserve plus measured peak-write check |
| Host/runtime | Confirm deployment host and runtime boundary | Host identity and rollback verification |
| Backup and OSS | Approve storage/cost and private bucket scope | Encrypted offsite package and retention check |
| Real isolated restore | Permit an isolated source/restore drill | Bound RPO/RTO and restored-content receipt |
| Production identities/trust roots | Establish controlled external pins and operators | Five-role, epoch and pin verification |
| Scheduler/local outbox | Approve limited no-order schedule and delivery boundary | Locking, receipt and silence behavior |
| SSE/SZSE Shadow start | Approve only after all technical preconditions | Scoped no-order Shadow admission |

## R5 - Final Product Acceptance

Not yet due. Final M7 acceptance waits for M6 operational evidence; it cannot
be substituted by the current canonical workbook opening or engineering tests.

## R6 - Natural Time

- M3 needs contemporaneous rule-and-input evidence before a future decision cutoff.
- Authorized Shadow needs 20 consecutive real completed exchange sessions.
- Authorized Shadow also needs at least one real financial or capital-allocation event.

## R4 - Investment Decisions

Investment decisions are not delegated. Research, prices, valuations, event
alerts and portfolio guidance remain material for human review only; no system
state authorizes a broker order.
