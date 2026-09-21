# 600519 Historical Backtest Admission Reassessment

Date: 2026-09-18

The repeatable admission audit produced
`runtime/strategy-validation/moutai-historical-admission-20260918T113035Z/evidence.json`.
It covers 2,674 SSE sessions from 2015-01-05 through 2025-12-31 and confirms
that no session currently has a point-in-time available, approved historical
value model. A return series must therefore not be described as a real strategy
backtest.

The remaining blockers are substantive rather than a test failure:

- Historical valuation approval is absent for all 2,674 sessions.
- The dated account, fill, corporate-action and benchmark acceptance contract
  is incomplete for all 2,674 sessions.
- A dividend/equity-recognition bridge is absent after 1,995 sessions.
- The issued/treasury-share denominator is incomplete for 243 sessions after
  the 2025 repurchase-program start.

The practical sequence remains: finish the current bounded paper-account input
producer; build a narrow, point-in-time valuation contract for one pre-registered
historical window; then validate its dated corporate-action, fee, execution and
benchmark inputs before expanding coverage. Do not fill missing sessions with
today's model assumptions, later disclosures or proxy performance figures.
