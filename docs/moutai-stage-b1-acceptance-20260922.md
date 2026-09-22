# Moutai Stage B1 Research Acceptance

> Status as of 2026-09-22: **passed for the bounded Stage-B research deliverable**.
> This is not a formal fair-value approval, simulation acceptance, strategy-performance
> proof, portfolio recommendation, or live-trading admission.

Date: 2026-09-22

## Scope

This acceptance covers the Stage-B requirement for `600519` in
[value-investment-excel-mvp-goal.md](value-investment-excel-mvp-goal.md):

- one frozen applicable primary model;
- dated bear/base/bull scenarios;
- named key assumptions and sensitivities;
- transparent valuation confidence;
- a bounded reverse valuation;
- a separately dated and verified price bridge;
- Excel publication without promotion to a fair value, order, position or trade instruction.

The separate engineering boundary is documented in
[moutai-stage-b1-engineering-acceptance-20260921.md](moutai-stage-b1-engineering-acceptance-20260921.md).

## Authoritative Artifacts

- `scripts/build_moutai_valuation_result.py`
- `scripts/build_moutai_franchise_duration_evidence.py`
- `scripts/build_moutai_distribution_capacity_evidence.py`
- `runtime/valuation-results/600519-current-equity-stage-b/evidence.json`
- `runtime/valuation-results/600519-current-equity-stage-b-latest.json`
- `runtime/company-research/600519-consolidated-parent-equity-residual-income-current-20260921T124252Z/evidence.json`
- `runtime/company-research/600519-current-valuation-admission-20260921T153230Z/evidence.json`
- `runtime/company-research/600519-current-assumption-diagnostic-20260921T124253Z/evidence.json`

Current valuation-result pointer SHA-256:

`5fd86bd643d958a93462905f32eae57fad3e8a7ee6c8986dce7ba2ef73ee9495`

Current published canonical workbook SHA-256:

`030e702789c37d66580f99ca5769b28289cd820457ad77c0c9196e019c499ef5`

## Requirement Audit

| Stage-B requirement | Evidence | Result |
| --- | --- | --- |
| Frozen research primary model | `moutai-current-parent-equity-residual-income-v1`; route is `quality_compounder -> residual_income_or_equity_value` | Pass |
| Bear/base/bull | 403.44 / 478.43 / 571.25 CNY per share, dated 2026-09-21 | Pass |
| Named key assumptions | Dated profit anchor, -5%/0%/+5% growth, 75% payout, five-year forecast, five-year fade, 2% terminal growth and bounded cost of equity | Pass |
| Sensitivity evidence | Five retained cases: payout 0.50/0.85, fade 0/10 and a higher equity-cost stress | Pass |
| Transparent confidence | Shared `valuation_confidence.py` returns `低` with `parameter_sensitivity_high` and `cyclicality_unknown`; no LLM scoring | Pass |
| Reverse valuation | 2026-09-21 quote 1,252.57 solved against the registered -5%/+5% envelope at 0/5/10 fade horizons; no unique implied growth was manufactured | Pass |
| Independent price bridge | Dated matched close at 1,252.57; bridge `READY`; margins to bear/base are -210.5% / -161.8% | Pass |
| No valuation/order promotion | `conditional_research_only`, `formal_fair_value=null`, `valuation_approved=false`, `trade_approved=false`, `live_eligible=false` | Pass |
| Excel publication | Candidate rebuilt, real read-only WPS COM navigation passed, atomic publish with pre-publish backup | Pass |

## Conditional Result

The three values are conditional research scenarios, not a target price or a fair-value
interval. The negative margins are arithmetic comparisons with an observed same-date price.
They are not a sell signal, an overvaluation verdict, or a research-attractiveness upgrade.

## Remaining Production Boundaries

- Full-year 2026 parent remittances and distributable-cash disclosure.
- Empirical evidence for the actual future duration of competitive advantage.
- A company-specific discount basis rather than a bounded research interval.
- A formal valuation-approval gate separate from Stage-B research acceptance.

These boundaries keep the result at low confidence and `conditional_research_only`.

## Verification

Focused B1 valuation, franchise-duration, distribution-capacity, post-close guard,
admission, P1-contract, confidence, price-bridge, current-status and workbook-navigation
regression: `72 passed`.

## Stage Boundary

B1 is complete for the Excel-MVP Stage-B research deliverable. It does not complete all of
Stage B, and it does not approve simulation, portfolio, historical-strategy, or live-trading
use. The next ordered engineering work remains `000333` FCFF production validation, not
re-opening or over-fitting the Moutai model.
