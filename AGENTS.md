# Value Investment Methodology Context

Read `docs/value-investment-goal-prompt.md` first. Its Excel MVP scope controls
near-term work; `docs/value-investment-goal-framework-v2.md` controls financial
definitions, evidence requirements and admission boundaries.

## Execution Rule Distinction

- The old `safety_margin >= 30%` rule is a named legacy / long-hold candidate
  experiment only. It is not a universal value-investing rule, default model
  parameter, generic Paper Eligibility condition, position-sizing trigger or
  real-trading instruction.
- Files, receipts and backtests that retain 20% / 30% / 40% thresholds are
  historical or explicitly versioned experiments. Preserve their identity and
  results, but never import their threshold into a new company or a generic
  execution path without a separately registered and validated strategy
  version.
- `ResearchCase -> ResearchGate -> 估值具备研究吸引力` is a research path.
  `估值具备研究吸引力` is not a paper order, a position, or a signal by itself.
  Low valuation confidence cannot reach that research status.
- Paper Eligibility is a separate AND gate. It requires the applicable,
  versioned strategy's evidence and price rule, same-date facts/model/quote,
  thesis and risk status, account capacity, and next-session execution checks.
  A paper order may exist only after every applicable gate passes. Paper
  eligibility never authorizes a real order.
- Price attractiveness is path-specific. The relevant rule for an asset
  discount, compounder, growth, cash-return or cyclical case must state its
  own value basis, uncertainty treatment, time/value-realisation mechanism,
  downside/failure case and exit/re-entry policy before simulation.
- Keep evidence, valuation, strategy, account and execution state separate.
  Unknowns, conflicts, low confidence or data freshness failures fail closed:
  research observation / no new risk, never an inferred order.

## Current MVP Boundary

- Stage B1 Moutai remains low-confidence conditional research until the dated
  evidence chain and its independent acceptance checks pass. It is not a
  research-attractive, simulation-eligible or trading state.
- The current user-authorized 000333 scope is limited to the shared
  `FinancialFacts -> ValuationModel -> ValuationResult` engineering path and
  Excel display. Do not create a Midea-specific valuation framework, produce
  scenario values without verified facts, or change execution code. Shenhua
  B3 remains deferred until its stated evidence prerequisites are met.
- Never replace the WPS canonical workbook without candidate preservation,
  source-hash guarding and WPS read-only verification. Preserve all manual
  records and never write broker orders.

## External Data Waiting

Read `docs/external-data-blocking-policy.md` for the complete policy. Do not
mark project development `BLOCKED` merely because a market session, quote,
filing or provider response has not yet formed. Record independent
`Engineering Status` and `Current Data Status`; use
`PENDING_EXTERNAL_DATA` for the latter, replay the latest verified Snapshot,
and finish non-dependent code, tests and Excel/JSON integration.

Keep `FinancialFacts -> ValuationModel -> ValuationResult` separate from
`ModelValidity + QuoteSnapshot -> PriceBridge`. A valid research model can be
bridged to a later quote only through an explicit material-event validity
check. This does not weaken the stricter versioned Paper Eligibility gate.
