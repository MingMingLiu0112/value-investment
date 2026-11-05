# Human Review and G3 Boundary (W4)

`action=no_order`. Human review engineering exists; no human or machine is
allowed to impersonate approval.

## What is enforced

- Review consumption uses the existing signed-response and pinned-trust-root
  contract. Local login does not grant research-approval authority.
- Legacy records generated without reviewer identity are not importable.
- The known script-frozen 2026-09-23 approval cluster is demoted to
  `SUPERSEDED`; its historical bytes remain available as audit evidence.
- A decision with a new explicit reviewer identity still resolves through the
  legitimate path.
- Missing, expired, wrong-version and wrong-hash approvals fail closed and
  cannot produce a price or order.

## Midea review packet pending

The current 000333 draft has four retained announcements awaiting human
materiality review:

| Announcement | Date | Required review |
| --- | --- | --- |
| 1225608903 - buyback progress | 2026-10-17 | Determine whether the disclosed repurchase changes shares, cash or the valuation thesis |
| 1225603532 - extraordinary shareholder meeting resolution | 2026-10-14 | Confirm approved resolutions and any capital-impacting authority |
| 1225603533 - legal opinion | 2026-10-14 | Cross-check the meeting resolution and capital actions |
| 1225603534 - cancellation of restricted shares and creditor notice | 2026-10-14 | Determine share-count, capital and claim-period effects |

Until a real authorized reviewer completes those judgments and a valid G3
record is imported:

```text
HUMAN_REVIEW_ENGINEERING=PASS
REAL_G3_APPROVAL=BLOCKED_HUMAN
FORMAL_INVESTMENT_ELIGIBILITY=NOT_REACHED
```

