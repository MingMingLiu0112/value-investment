# Moutai Stage B1 Engineering Acceptance

> Status as of 2026-09-21: **passed as a bounded conditional-valuation engineering acceptance**.
> This is not a formal valuation, strategy, simulation, portfolio, or trading-readiness acceptance.

Date: 2026-09-21

## Scope and Evidence

This acceptance covers the B1 engineering boundary for `600519`: a retained
parent-equity residual-income model with dated bear/base/bull arithmetic, a bounded
franchise-fade audit, an independent `ModelValidity` and `PriceBridgeResult`, and the
existing Excel research display.

It does not approve Moutai's fair value, the size of the negative margins, a paper order,
position, live eligibility, or any practical investment conclusion.

Authoritative artifacts:

- `docs/moutai-stage-b1-progress-20260921.md`
- `scripts/build_moutai_valuation_result.py`
- `scripts/build_moutai_franchise_duration_evidence.py`
- `scripts/build_moutai_distribution_capacity_evidence.py`
- `runtime/valuation-results/600519-current-equity-stage-b/evidence.json`
- `tests/test_moutai_valuation_export.py`
- `tests/test_moutai_franchise_duration_evidence.py`
- `tests/test_moutai_distribution_capacity_evidence.py`
- `tests/test_moutai_postclose_guard.py`
- `tests/test_price_bridge.py`

The valuation-result pointer hash is
`47ccfefafbd6e6b36b3ec1df09690340d077b68d19edf52382e9bbb45b0732f0`.

## Requirement Audit

| B1 requirement | Evidence | Result |
| --- | --- | --- |
| One retained model, not an unstable current price multiple | `moutai-current-parent-equity-residual-income-v1` | Pass |
| Valuation arithmetic is separate from market price | `ValuationResult` contains no `current_price` or margin fields | Pass |
| Price comparison has an independent bridge | `PriceBridgeResult` with matched close and `ModelValidity` | Pass |
| Bear/base/bull are dated conditional values | Values are retained in a hash-pinned result and publish gate | Pass |
| Reverse valuation is bounded, not a unique market expectation | All 0/5/10-year horizons are above the registered envelope | Pass |
| Franchise duration is policy, not empirical proof | `bounded_conditional_policy_audited_not_empirical_franchise_duration` | Pass |
| Distribution capacity is historical evidence only | Forward cash capacity remains `not_approved` | Pass |
| Low confidence cannot become research attractiveness | Export and publication gate require low-confidence status and no promotion | Pass |
| No order, position, or trade instruction | All execution flags remain `false` | Pass |

## Conditional Result

The retained dated scenarios are:

- Bear: 403.44 CNY/share
- Base: 478.43 CNY/share
- Bull: 571.25 CNY/share

The 2026-09-21 two-source matched close is 1,252.57 CNY/share. The independent bridge
reports -210.5% to bear and -161.8% to base. Those are arithmetic comparisons between a
conditional research model and an observed price. They are not a sell signal, an
overvaluation ruling, or proof of a research buy point.

## Remaining Production Boundaries

The following are still unresolved and keep B1 from becoming a formal valuation:

- Full-year 2026 parent remittances and distributable-cash disclosure.
- Empirical evidence for the actual future duration of competitive advantage.
- A company-specific discount basis rather than a bounded research interval.
- A formal valuation-approval gate independent from this engineering acceptance.

## Related Paper-Execution Boundary

As of 2026-09-21 the separately dated daily simulation policy
`moutai-daily-simulation-paper-execution-policy-v1` is implemented for paper execution
only. It binds the 2026-09-21 observation and 2026-09-22 validity session to the hash-pinned
execution contract. The current P1 contract and current valuation-admission receipt report
`daily_simulation_policy_implemented=true`, and the actual close-only dry run remained
`watch / no_order` with no fill and no approval state change.

This policy registration belongs to the execution boundary, not to this B1 valuation
acceptance. It does not prove next-session liquidity depth, a real fill, historical
strategy effectiveness, simulation eligibility, or live-trading readiness.

## Stage Boundary

B1 Engineering is accepted as a reproducible, fail-closed conditional boundary. Stage B
as a whole is not complete. Moutai's result must remain
`conditional_research_only`, confidence `低`, `formal_fair_value=null`, and every
valuation, simulation, trade and live flag must remain `false`.

## 2026-09-22 Route-Policy Re-export Note

The same accepted model was re-exported after `valuation_router.py` gained the shared
`quality_compounder -> residual_income_or_equity_value` registration. The export now
validates that route before reading any valuation or quote evidence and records
`valuation_route` in the payload. Bear/base/bull values, confidence, reverse valuation,
price bridge, and all approval flags are unchanged.

On 2026-09-22 a route re-export temporarily dropped the retained same-date bridge because
the producer did not resolve the matching hash-pinned assumption diagnostic by default.
That regression was fixed: the producer now selects the newest diagnostic that reuses the
pinned model and restores the dated `READY` bridge at `1,252.57 CNY` for `2026-09-21`. The
same export now also runs the shared deterministic confidence policy, which returns `低`
on `parameter_sensitivity_high` and `cyclicality_unknown`. The current pointer SHA-256 is
`5fd86bd643d958a93462905f32eae57fad3e8a7ee6c8986dce7ba2ef73ee9495`; the hash above remains
the originally accepted artifact and is superseded only by these provenance, bridge and
confidence-policy recovery changes.
