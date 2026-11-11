# D2 Price Review Method Registration

Status: method review only. This is not a claim of investment effectiveness or
production admission. All outputs remain `action=no_order` and require human review.

## Boundary

`ValuationResult` contains intrinsic-value scenarios and uncertainty; it does
not ingest the market quote. `PriceBridge` binds a dated, verified quote to a
still-valid model. `PriceAttractivenessAssessment` describes a research price
zone, never an order or a portfolio weight. A missing quote, stale model,
incomplete research gate, or missing human G3 price authorization fails closed.

This separation follows the [CFA Institute's equity valuation framework](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/equity-valuation-concepts-basic-tools),
which distinguishes fundamental value estimation from comparison with the
market price. Its [applications and processes reading](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/equity-valuation-applications-and-processes)
also treats valuation as an estimate, not a deterministic trade instruction.

## Registered Profile Semantics

| Profile | Current price method | Positive research zone | Low confidence | Unresolved method risk |
| --- | --- | --- | --- | --- |
| `quality_compounder` | Compare verified price with the approved Bear/Base/Bull range. | Only price at or below Bear, with medium/high valuation confidence and all upstream gates. This is a conservative research condition, not `MANUAL_BUY_REVIEW`. | `WAIT_FOR_BETTER_PRICE`; do not elevate to a positive research zone. | Bear is scenario-dependent; the condition has not been proven optimal or sufficient for a purchase. |
| `mature_manufacturing` | Show bound price and scenario margins if available. | Not registered; `KEY_OBSERVATION` only. | No positive elevation. | FCFF inputs, capital intensity, and model applicability need company-specific validation. |
| `cyclical_cash_return` | Show bound price and scenario margins if available. | Not registered; `KEY_OBSERVATION` only. | No positive elevation. | Peak earnings and current dividends cannot stand in for normalized earnings or sustainable distributions. |

For `quality_compounder`, the implemented condition is **price <= Bear**. The
former text saying "between Bear and Base or lower" was inconsistent with the
code; it has been corrected without relaxing the threshold. If Bear <= Base,
the earlier Base check after price <= Bear was unreachable and has been removed.
No historical-return search was used to choose or revise this rule.

## Decision Boundary

`RESEARCH_ATTRACTIVE` means a price condition for further review, not BUY.
Positive review additionally requires the research thesis, counter-evidence,
model validity, current quote, material-event coverage, predecision eligibility,
and the applicable portfolio preconditions. Without real private portfolio
input, personal position guidance remains `BLOCKED_PRIVATE_INPUT` and null.
Price falls cannot automatically trigger ADD; price rises cannot automatically
trigger REDUCE or EXIT. Both require a comparison with the original thesis and
current evidence.
