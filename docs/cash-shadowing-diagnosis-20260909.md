# Nine cash fields shadowed by newer pending observations

Live read-only database snapshot saved as runtime/cash-acceptance-live-20260909.json.
Affected: 000425, 001233, 001386, 002011, 002043, 002444, 002727, 300815, 301376.

All nine retain verified original-PDF cash facts for 2025-12-31 in CNY, with
cross-source metadata and original hashes. New pending records created around
2026-09-08 22:22-22:28 UTC use CNY 100M and empty metadata. No original facts
were deleted or quarantined in this readback. Decimal arithmetic confirmed
each new value multiplied by 100000000 exactly matches its older verified
original-PDF value (9/9). Thus these gaps are not missing numeric disclosure
or a report-period change.

The latest-point selection ranks period and creation time, so newer pending
observations shadow the older verified facts. Automatic candidate matching
also checks unit equality; unit equivalence alone must not bypass source scope,
latest-source consistency, evidence Hash and audit requirements.

Next: inspect existing reverify_shadowed_facts.py and candidate_review flow,
then implement/reuse narrowly scoped monetary-unit normalization with tests
for genuine revised values and unknown units. Reverify against the original
PDF and latest independent observation, retaining both originals, rather than
changing latest selection to prefer old verified records. No statuses were
changed and no new Excel publication occurred in this diagnosis.

The initial read-only query used a non-existent fetched_at field on data_points
and failed without mutation; it was corrected to the actual created_at column.

## Comparison layer implemented locally

candidate_review.comparable_value_agrees now compares only explicit CNY,
CNY 10K and CNY 100M scales using Decimal and applies existing tolerance in
CNY. Unknown/incompatible units and non-finite values fail closed. Latest
source selection still rejects a changed latest value and disagreements
between sources; it returns the original observation without rewriting IDs,
values or units. Source scope, PDF Hash and period checks remain separate.

Targeted tests: 30 passed. Full suite: 1066 passed, 18 existing Backtrader
warnings. This local comparison change is NOT deployed and does not itself
repair the nine facts: the existing reverification SQL still uses exact-unit
joins and selects consolidated-source evidence. That selection must be
adapted coherently with latest-observation linkage, tested using real rollback,
and deployed against an inspected production baseline. No record is approved
solely because unit conversion produced an equal amount.
