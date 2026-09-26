# Current Readiness Matrix

> Snapshot: 2026-09-26. This is a factual readiness view, not a new roadmap.
> Every status remains decision support only: `action = no_order`.

## Current Daily Data Fact

The latest completed official SSE/SZSE session is `2026-09-24`; both exchanges
were closed from 2026-09-25 through 2026-09-27. The bounded quote collection
`runtime/quote-sessions/20260926T081028140946Z/` retained dual-source,
matched-close observations for `600519`, `000333`, and `601088` and the
corresponding official calendar evidence. Its bundle SHA-256 is
`d161c6ed8acf2034544aa63fb101922d0ec22f537cdf2c69268243aaecb82974`.

This is `DATA_PARTIAL`, not `FRESH`: the current canonical Excel publisher is
still bound to a frozen research packet and has not consumed that quote bundle.
Therefore `CANONICAL_DAILY_RUN = NOT_VERIFIED`; no Excel publication was made
in this readiness phase.

## Milestone Matrix

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
| Initial assisted use | — | No fresh daily packet has been safely bound to the canonical workbook; no user final acceptance | R0/R5 | NOT_REACHED | Bind a current daily packet to the canonical publisher, then complete user acceptance |

## Safe Work Boundary

`m6c2` and `m6c3` were re-verified by
`runtime/m6-operational-preflight-20260926T081452Z/receipt.json` at commit
`0ce39a7ddc900ce6830d94304b094b430b268112`. The M4 receipt
`runtime/m4-synthetic-onboarding-real-use-readiness-pre-gate-20260926/receipt.json`
is explicitly `COMPLETED_SYNTHETIC_ONLY` and keeps
`M4_PERSONALIZED_ACCEPTANCE = WAITING_R2`.

No R3 production activity, real account import, scheduler, notice, Shadow run,
or trading action occurred. The remaining safe engineering issue is narrow:
the daily packet-to-canonical-publication binding must be made evidence-bound
before a canonical workbook can describe current data. It must not be bypassed
by publishing the frozen packet.
