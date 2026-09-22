# Shenhua Stage B3 Engineering Acceptance

> Status as of 2026-09-21: **passed as a fail-closed cyclical-model engineering acceptance**.
> This is not a valuation, strategy, simulation, portfolio, or trading-readiness acceptance.

Date: 2026-09-21

## Scope and Evidence

This acceptance covers the B3 engineering boundary for `601088`:
`CyclicalFacts -> CyclicalNormalizedValuationModel -> ValuationResult`, plus the current
Excel research display. It does not approve normalized earnings, bear/base/bull values,
a current price, reverse valuation, position, order, or trading readiness.

Authoritative artifacts:

- `src/value_investment_agent/valuation_models/cyclical.py`
- `scripts/build_shenhua_cyclical_scope.py`
- `scripts/build_shenhua_cyclical_time_series.py`
- `scripts/build_shenhua_cyclical_valuation_result.py`
- `scripts/build_shenhua_bridge_independent_review.py`
- `scripts/build_shenhua_route_delivered_cost_audit.py`
- `tests/test_cyclical_normalized_valuation.py`
- `tests/test_shenhua_cyclical_scope.py`
- `tests/test_shenhua_cyclical_time_series.py`
- `tests/test_shenhua_cyclical_valuation_result.py`
- `tests/test_shenhua_bridge_independent_review.py`
- `tests/test_shenhua_route_delivered_cost_audit.py`
- `docs/shenhua-stage-b3-progress-20260921.md`

The retained official filing is `runtime/shenhua-2025-official.pdf` with SHA-256
`460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`.

## Requirement Audit

| B3 requirement | Evidence | Result |
| --- | --- | --- |
| Shared cyclical model; no Shenhua-specific valuation framework | Shared `CyclicalNormalizedValuationModel` contract | Pass |
| No generic PE as the primary model | Finite resource-life normalized distributable-cash arithmetic | Pass |
| Current-year profit is not permanentized | Required mid-cycle, trough, resource-life and cost inputs | Pass |
| Official 2025 facts are source-pinned | Pages 20, 30, 31, 32, 47, 148, 458, 460 in evidence JSON | Pass |
| Missing inputs block all scenario values | Model returns `not_ready` with null bear/base/bull | Pass |
| Normalized arithmetic is isolated and tested | Unit tests with synthetic complete inputs | Pass |
| No order, position, or trade instruction | `VALUATION_NOT_READY` and model contract | Pass |

## Runtime Verification

- B3 focused tests: `7 passed`.
- Combined P0, Midea B2 and Shenhua B3 regression set: `30 passed`.
- Cyclical scope payload SHA-256:
  `4C69CF09F81AE8C0CF7FD5537276A3147D1C25ADF3EEE80B92C455EE2A3134C0`.
- Reviewed 2014--2025 raw annual time-series payload SHA-256:
  `49CEF89EA5309AD556B09132924845F02DE79204C75D0CE3467FB3A9BB23F04E`.
- Valuation result payload SHA-256:
  `D9122554F812BB88EFCD3482A12C1D1722CA27778C9144E89A5D6C95C9EB8D8D`.
- Bridge independent-review payload SHA-256:
  `6F4238A5C520CA956E3D72D3EF366CE80E647FC4684A8FDAB897D3BA80A09E44`.
- Bridge independent-review focused tests: `5 passed`.

## Objective Assessment

The engineering path is complete and correctly fail-closed. The annual report provides
strong current-cycle segment, reserve and balance-sheet facts, but does not by itself
prove a full mid-cycle profit, cash, capex, cost and price series. It also does not
state mine service life in years, split maintenance from growth capital, allocate
consolidated cash and debt to the parent common-equity claim, or establish a verified
trough-solvency test.

No high-point profit, low PE, generic multiple or estimated net cash was used to create
the appearance of a valuation. The correct state is a traceable `VALUATION_NOT_READY`.

## Stage Boundary

Production validation requires a separately reviewed multi-year cycle package, then
approved normalized scenarios, reverse valuation and a hash-guarded Excel publication.
Until those inputs are verified, B3 remains `not_ready` and must not be promoted to
simulation, portfolio or trading readiness.

## Candidate-Input Compilation Note

A later `shenhua-cyclical-candidate-inputs-20260921` package records selected
official-disclosure derivations as `unreviewed` candidates. It confirms that the parent
pre-tax operating-profit bridge, post-balance ordinary-share denominator and attributable
net-cash allocation are still missing, so it does not change this acceptance or permit the
shared model to run.

## Bridge Independent Review Note

On 2026-09-21 the three bridge packages were independently reviewed against the full
HKEX and company Chinese 2026 interim reports. The ordinary-share denominator
`21,689,434,304` was approved as a point-in-time input for a valuation date at or after
2026-06-30, but was not registered alone. The parent pre-tax operating-profit pro forma
and attributable net-cash interval were rejected as verified model inputs because the
disclosures still lack subsidiary-level pre-tax, tax, minority, cash and debt allocation.

The review package is
`runtime/company-research/shenhua-2026-bridge-independent-review-20260921/evidence.json`.
No `CyclicalFacts.operating_inputs` value was registered, so this fail-closed acceptance
and the production `VALUATION_NOT_READY` state remain unchanged.

## Subsidiary Allocation Boundary Note

On 2026-09-21 a later `shenhua-2025-subsidiary-allocation-evidence-20260921` package pinned
the parent legal-entity income statement and seven material non-wholly-owned subsidiaries.
It confirms that named minority profit of RMB8,832 million does not reconcile consolidated
minority profit of RMB9,934 million, and named minority equity of RMB45,723 million does not
reconcile consolidated minority equity of RMB72,344 million. The filing still gives no
subsidiary-by-subsidiary pre-tax profit or tax allocation, so every model input remains null.
This addition strengthens the evidence trail without changing the fail-closed acceptance.

## IFRS 12 Cross-Report Review Note

On 2026-09-22 the HKEX English/IFRS 2025 annual report was independently reviewed for the
specific missing subsidiary-level pre-tax and tax allocation. IFRS Note 44 gives summarized
revenue, expenses and profit and total comprehensive income before intragroup eliminations,
but still gives no subsidiary-level profit-before-income-tax or income-tax-expense line.
The consolidated tax reconciliation also discloses a RMB(4,228) million different-tax-rate
effect across branches and subsidiaries, so proportional ownership allocation remains
unsupported. The review package is
`runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922/evidence.json`.
No model input was registered; `VALUATION_NOT_READY` remains unchanged. The review was also
added to the Shenhua research card and atomically republished to the canonical Excel workbook,
without changing the fail-closed display state.

## Route-Specific Delivered-Cost Audit Note

On 2026-09-22 the 2014--2025 Chinese annual reports and the 2025 English/IFRS report were
searched for route-specific railway tonne-kilometres, port tonnage, shipping nautical-mile
equivalents, route-specific cost and an explicit route-allocation matrix. No retained filing
contains those disclosures. The production-scope 171.6 CNY/t unit cost and aggregate 0.082
CNY/t-km, 11.5 CNY/t and 0.030 CNY/t-nautical-mile mode averages therefore cannot be combined
into an audited mine-to-customer delivered cost. The evidence package is
`runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-20260922/evidence.json`;
`registered_cyclical_facts_operating_inputs=[]`, and `VALUATION_NOT_READY` remains unchanged.
