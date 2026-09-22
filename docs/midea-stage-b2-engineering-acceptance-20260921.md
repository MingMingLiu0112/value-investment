# Midea Stage B2 Engineering Acceptance

> Status as of 2026-09-21: **passed as a fail-closed engineering acceptance**.
> This is not a valuation, strategy, simulation, portfolio, or trading-readiness acceptance.

Date: 2026-09-21

## Scope and Evidence

This acceptance covers only the B2 engineering boundary for `000333`:
`FinancialFacts -> FCFFValuationModel -> ValuationResult` plus the existing
Excel research display. It does not approve a formal valuation, price bridge,
margin of safety, position, order, or trading readiness.

Authoritative artifacts:

- `docs/midea-stage-b2-progress-20260921.md`
- `runtime/company-research/midea-ebit-scope-20260921/evidence.json`
- `scripts/build_midea_ebit_scope.py`
- `tests/test_midea_ebit_scope.py`

The retained official filing is `runtime/midea-2025-official.pdf` with SHA-256
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`.

## Requirement Audit

| B2 requirement | Evidence | Result |
| --- | --- | --- |
| Shared FCFF contract only; no Midea-specific valuation framework | `FCFFValuationModel` and shared `ValuationResult` tests | Pass |
| Explicit model selection; no implicit FCFF default for all companies | `scripts/build_company_valuation_result.py` requires `--model fcff` | Pass |
| Midea financial facts are dated, source-pinned and fail-closed | `build_midea_fcff_facts.py` plus regression test | Pass |
| EBIT scope is audited from the official filing | Page 135, 225, 227, 229, 234, 249, 250 references in evidence JSON | Pass |
| Financial-business carve-out is not fabricated | `industrial_fcff_carve_out: MODEL_NOT_APPLICABLE` | Pass |
| Enterprise-value bridge is not fabricated | `consolidated_enterprise_value_bridge: VALUATION_NOT_READY` | Pass |
| No bear/base/bull scenario values are emitted | Regression test asserts those keys are absent | Pass |
| No order, position, or trade instruction is emitted | `VALUATION_NOT_READY` and `not_ready` FCFF output | Pass |

## Runtime Verification

- Focused B2 tests: `5 passed` covering EBIT scope, financial facts, business
  evidence and the unified FCFF contract.
- Full P0 plus B2 regression set: `25 passed`.
- EBIT evidence payload SHA-256:
  `E9527B6C824BE83366EAEF9F7FFB95288C3BEFBFC1AC1F8811C56441C5248566`.
- Source PDF hash is checked in every evidence reference.

## Objective Assessment

The engineering path is complete and correctly fail-closed. The annual report
does not disclose a standalone financial-business profit and balance-sheet
scope, and the `other` segment mixes financial services with robotics, energy,
medical and other businesses. Therefore industrial EBIT and invested capital
cannot be observed from this filing, and a consolidated enterprise-value
bridge lacks the required financial-business and non-operating-asset evidence.

No approximated net debt, tax, WACC, or scenario arithmetic was used to produce
the appearance of a valuation. The correct next state is a blocked, fully
traceable `VALUATION_NOT_READY`, not a weak per-share estimate.

## 2026-09-22 Arithmetic Addendum

The shared model now has a tested scenario-arithmetic path in addition to the
accepted fail-closed boundary. `FCFFScenarioInputs` carries explicit
bear/base/bull forecast, terminal, bridge, exposure, share and evidence inputs;
`FCFFValuationModel` delegates to the existing shared calculator and returns
`conditional_research_only` only for complete, verified facts.

This addendum does not reopen or weaken the production boundary. The retained
2025 Midea filing still has no approved industrial EBIT, financial-business
carve-out, cash-tax/WACC/net-debt scope or weighted ordinary-share denominator,
so the production payload remains `not_ready` with null scenario values.
The arithmetic path is reusable engineering, not a Midea valuation.

## Stage Boundary

B2 Engineering is accepted at this boundary. Production validation would require
a separately disclosed financial-business scope or an audited enterprise-value
bridge, plus date-matched, point-in-time price evidence. Neither is available
from the retained filing, so the next work moves to 601088's cycle and
normalized-earnings input contract rather than manufacturing Midea FCFF inputs.
