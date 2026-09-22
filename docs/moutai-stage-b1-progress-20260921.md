# Moutai Stage B1 Progress

Date: 2026-09-21

## Current Result

The retained model is `归母权益剩余收益 / 分配能力`
(`moutai-current-parent-equity-residual-income-v1`). Its dated conditional values are:

- Bear: 403.44 CNY/share
- Base: 478.43 CNY/share
- Bull: 571.25 CNY/share

The 2026-09-21 two-source quote was verified as a matched close at 1,252.57 CNY/share.
The independent price bridge is `READY`:

- Margin to bear: -210.5%
- Margin to base: -161.8%

This result was written to the canonical WPS workbook with a backup, SHA-256 check and
actual WPS read-only navigation verification. The published workbook SHA-256 is
`76b3d55e0009a88a1366b281acaca9b3238ab8e3c53e2bb340440ca28cdca946`.

After the later Shenhua candidate-card publication on the same date, the canonical
workbook SHA-256 is
`a1d755f7705135d3ada9c84a8021cb57b0c3b4459b08dc802f133aade4ddf26f`.

On 2026-09-22 the dated same-date price bridge was restored after a route re-export had
inadvertently left it pending. The export now also evaluates confidence with the shared
deterministic policy rather than a hard-coded label. The canonical workbook was rebuilt,
WPS-verified read-only, and atomically published again. Current canonical workbook SHA-256 is
`030e702789c37d66580f99ca5769b28289cd820457ad77c0c9196e019c499ef5`.

The result remains `conditional_research_only` with `confidence=低`,
`formal_fair_value=null`, `valuation_approved=false`, `trade_approved=false` and
`live_eligible=false`.

## What The Negative Margins Mean

The quote is far above both registered conditional scenarios. Under the frozen -5%/0%/+5%
profit-growth and franchise-fade assumptions, the reverse valuation cannot solve for a
growth rate inside the registered envelope at any 0, 5 or 10 year fade horizon.

This is not proof that Moutai is overvalued and is not a sell instruction. The scenarios
are explicitly conditional research arithmetic. The franchise-duration policy is now
audited as bounded, but its future real-world duration and terminal profit remain
unverified; forward full-year 2026 cash capacity is not disclosed, so confidence is low.
The result cannot be promoted to research attractiveness, a fair value, an order, a paper
fill or live readiness.

## Distribution-Capacity Evidence Added

A separate hash-bound primary-report package now verifies:

- FY2025 total disclosed cash dividend plus repurchase is about 86.43% of consolidated profit.
- The latest three-year disclosed cash dividend is about 75.35% of average profit.
- FY2025 proposed annual plus implemented interim cash is about 79.00% of FY2025 consolidated profit.
- FY2025 parent CFO plus subsidiary investment income, after parent capex, covered paid
  distributions and interest by about `1.224x`.
- H1 2026 parent CFO after capex covered distributions by only about `0.411x`; the small
  subsidiary investment-income receipt shows why half-year coverage is not a full-year
  conclusion.
- Finance-company deposits and the disclosed restricted-cash subset remain excluded from
  parent distributable cash.

The package status is
`distribution_history_verified_but_forward_cash_capacity_not_approved`. It improves the
evidence boundary around historical payout and FY2025 cash coverage, but it does not by
itself increase valuation confidence or approve a forward payout policy.

## Franchise-Duration Evidence Added

A separate hash-bound audit now verifies the bounded geometry behind the five-year fade:

- Five forecast years and five fade years are explicit, internally consistent model policy.
- Immediate fade and ten-year fade are explicit stress bounds: the zero-year case removes
  the assumed excess-return window, while the ten-year case tests a materially longer
  duration.
- The terminal ROE equals the scenario cost of equity, so no permanent excess franchise
  return is capitalized.
- The audit re-extracts the FY2025 volume/price, capacity and aged-product pages, plus the
  H1 2026 dynamic-price language, and retains Wuliangye H1 2026 revenue, operating-cash-flow
  and selling-expense observations as counterevidence.
- The archived quote lies above every registered 0/5/10-year fade and -5%/0%/+5% growth
  combination, so the five-year policy was not selected to manufacture a positive margin.

The status is
`bounded_conditional_policy_audited_not_empirical_franchise_duration`. This closes the
question of whether the policy geometry is defensible, but it does not measure how long
Moutai's competitive advantage will actually persist and does not raise valuation
confidence.

## What Is Verified Versus Assumed

Verified and hash-bound:

- The issuer capital-event bridge and current share denominator.
- Parent equity, parent profit and issued-share scope.
- The dated cost-of-equity selection policy.
- The 2026-09-21 two-source matched close and exchange-calendar session.
- Reproduction of the residual-income and dividend arithmetic.
- 2015-2025 disclosed cash distributions and the FY2025 parent cash-coverage chain.
- The bounded five-year franchise-fade policy, its 0/10 stress bounds and its
  no-permanent-excess-return terminal regime.

Explicit assumptions, not independently verified forecasts:

- Five-year profit growth of -5%, 0% and +5%.
- 75% payout and 25% retention as a forward policy; 75% is bounded by the disclosed
  historical record, but future commitment and settlement timing remain assumptions.
- The actual future length of Moutai's competitive advantage; five years remains a
  conditional policy, not an empirical measurement.
- 2% terminal growth and the selected discount-rate range.

## B1 Engineering Acceptance

See [moutai-stage-b1-engineering-acceptance-20260921.md](moutai-stage-b1-engineering-acceptance-20260921.md).

## P1 Boundary

The current P1 model audit is admitted for bounded current paper research. However, the
separate dated daily paper-execution policy is now implemented as
`moutai-daily-simulation-paper-execution-policy-v1`. The retained
2026-09-21 -> 2026-09-22 policy is hash-bound to the current execution contract and is
reported by the current P1 contract and admission receipt as implemented. A real
close-only dry run with that policy produced `watch / no_order` at 1,252.57 CNY/share:
no proposal, no fill and no account delta beyond the session record. This is execution
policy registration only; it proves neither next-session liquidity depth nor a real fill,
and `specified_simulation_eligible` remains `false`.

Authoritative policy artifacts:

- `runtime/strategy-validation/moutai-current-execution-contract-20260921T153023Z/evidence.json`
- `runtime/strategy-validation/moutai-daily-simulation-policy-20260921T153024Z/evidence.json`
- Policy evidence SHA-256: `3ce32b9bb29a4f6fd104d8a9fe93d3e65b88c95d4e2ae11c109fef8b84352fe3`

## Required Next Evidence

The bounded franchise-duration policy and the dated cost-of-equity selection policy have
now been independently audited. The remaining real dependencies are full-year 2026 parent
remittances and cash-flow disclosure, future empirical evidence on competitive-advantage
duration, and the separate formal valuation approval gate. The research card should be
republished to the WPS workbook with the new evidence references; the valuation result,
bridge, confidence and no-trade flags remain unchanged.

## Runtime Controls

`ValueInvestmentAgent-DailyUpdate` runs
`scripts/run_moutai_b1_after_close.ps1` after the close. It accepts a same-date matched
close, rebuilds the P1 evidence chain, creates a bounded reverse-valuation diagnostic and
exports a separate `ValuationResult` plus `PriceBridgeResult`.

`ValueInvestmentAgent-MoutaiB1ExcelPublish` runs afterward. It publishes only when the
model is valid, the bridge is `READY`, the quote date equals the expected date and no trade
or live flag is present. The candidate-first publication route preserves non-derived
sheets, verifies WPS navigation read-only and atomically replaces the canonical workbook.
