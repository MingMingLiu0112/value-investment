# D5 satellite interface freeze

Date: 2026-10-07. This is an interface and synthetic-contract checkpoint, not
a tactical strategy, recommendation, or production admission.

## Ownership and budget

`PortfolioSleeve` separates `CORE_VALUE`, `TACTICAL_HOTSPOT`, and
`CASH_RESERVE`. `SharedSleeveBudget` requires explicitly sourced core and
tactical reservations plus a cash floor. Their sum may not exceed one
portfolio. Cross-sleeve single-stock and sector caps are shared constraints,
not independent allowances. No real percentages have been selected; the
current tests use `SYNTHETIC_POLICY_ONLY`.

Core research, intrinsic Bear/Base/Bull, business quality, dividend
sustainability and the core thesis remain owned by the value engine. Tactical
features may eventually affect timing and review priority only. A tactical
signal never mutates a valuation or a core research artifact. Entry thesis,
exit rules, state and performance will be tracked separately by sleeve.

## Contracts now present

- `SentimentFeatureSnapshot` requires a dated, timezone-aware, evidence-linked
  multi-feature snapshot. It does not score or produce a signal.
- `SentimentSignal` defines review states and refuses synthetic
  `ENTRY_REVIEW` unless identity, basic financial sanity, value/risk floor,
  liquidity and event-risk gates are all marked passed. It is not an order.
- `SwingTradePlan` and `TacticalRiskPolicy` are synthetic-only; a plan must
  identify an entry trigger, stop, profit review, time exit, slippage model and
  failure conditions. It remains in `TACTICAL_HOTSPOT` with `action=no_order`.

No production feature collector, theme detector, market scanner, score,
backtest, shadow worker, current Excel page or real hotspot recommendation
exists. These contracts cannot be used to label a company as a current
tactical opportunity.

## Preregistered admission before any real D5 review state

1. Retain timestamped raw feature sources and enforce strict point-in-time
   availability, issuer identity and source hashes. Control survivorship and
   index/constituent changes.
2. Register features, thresholds, regimes and failure cases before evaluating
   returns. Use walk-forward and untouched out-of-sample periods; do not tune
   rules to the highest historical yield.
3. Simulate commission, stamp duty, slippage, turnover, liquidity, limit-up
   and limit-down, suspension and rejected fills. Disclose sensitivity to all
   cost assumptions.
4. Report drawdown, hit rate, payoff ratio, recovery time, exposure, turnover
   and failure regimes, not just cumulative return. Compare with a suitable
   benchmark and report uncertainty.
5. Complete independent replay and shadow observation before any real
   `ENTRY_REVIEW`; human decision and explicit production authorization remain
   separate. No signal ever becomes a broker order automatically.

D2 value-decision and canonical Excel work retain priority. Private IPS and
portfolio inputs remain `BLOCKED_PRIVATE_INPUT`, nonblocking for D2 research.
