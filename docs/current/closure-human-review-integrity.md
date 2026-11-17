# Closure Human Review Integrity (W1, 2026-10-17)

`action=no_order`. Problem: `scripts/build_m1_post_review_receipts.py` emitted
three records named `*-g3-human-approval-20260923.1` in
`runtime/m1-post-review-20260923T114228Z/human-research-approvals.json`:

| Symbol | Decision | Price eligible | Reviewer id | Reviewed at |
| --- | --- | --- | --- | --- |
| 000651 | REJECTED_NEEDS_REWORK | false | (absent) | 2026-09-23T13:30:00+08:00 |
| 600741 | REJECTED_NEEDS_REWORK | false | (absent) | 2026-09-23T13:30:00+08:00 |
| 600887 | **APPROVED_CONDITIONAL_LOW_CONFIDENCE** | false | (absent) | 2026-09-23T13:30:00+08:00 |

All three share one script-frozen timestamp and have no reviewer identity. The
600887 record would previously resolve as `approved=True` (research-only) if
its bound payloads matched. That is exactly the failure mode this work closes.

The historical files are not deleted or rewritten: their bytes remain audit
evidence. What changes is consumption.

## Mechanism

`src/value_investment_agent/domain/research/human_review_integrity.py` screens
approval payloads before they can become a decision:

- `reviewer_identity_missing`: a `human_research_lead` receipt with no
  `reviewer_id` can never be approved.
- `machine_generated_legacy_approval`: the known one-off generator signature
  (`-g3-human-approval-20260923.` plus the frozen
  `2026-09-23T05:30:00+00:00` instant) is rejected even if someone later adds
  an identity field.
- `fixed_script_review_timestamp`: exposes the frozen timestamp as a reason.
- `identical_script_timestamp_cluster`: a bundle where several identity-less
  approvals share one exact instant is flagged as non-independent review.
- `require_importable_approval()` raises `ApprovalImportRejected` for import
  surfaces; `resolve_human_research_approval()` demotes any approved decision
  carrying these reasons to `SUPERSEDED` with the reasons preserved as blockers.

## Result

- Legacy 600887 record: `status=SUPERSEDED`, `approved=false`,
  `price_assessment_eligible=false`, blockers include
  `reviewer_identity_missing` and `machine_generated_legacy_approval`.
- A new decision with an explicit reviewer id and a non-legacy id/timestamp
  still resolves normally; the change is about identity and provenance, not
  about weakening research approval.
- Rejected legacy records remain rejected and now carry the same audit reasons.

## Tests

`tests/test_human_review_integrity.py` (6 tests): legacy payload not
importable; legacy approval never resolves as approved G3; known generator
signature stays rejected even with an added identity; new decision with an
explicit reviewer stays importable; identical-timestamp bundle flagged;
`require_importable_approval` raises with source context.

Existing approval/eligibility/recommendation fixtures now carry
`reviewer_id=TEST_ONLY-HUMAN-RESEARCH-LEAD`, making the synthetic nature
explicit. Four focused suites: 48 passed.

## Boundary

This is not a real G3 approval and does not create one. A real approval still
requires the authenticated signed-response workflow with a pinned trust root.
`REAL_G3_APPROVAL` remains `BLOCKED_HUMAN` until an authorized reviewer signs.