# 600887 Retained H1 Financial Quality Review

## Scope

Current numeric review of the retained 2026 H1 report, not a new filing,
current financial admission, investment recommendation or strict PIT replay.
`action=no_order`; `suggested_state=NOT_READY`.

Source: [CNINFO H1 report](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF),
SHA-256 `423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`.
Page numbers below are physical PDF pages. Monetary amounts are consolidated
CNY, except that profit is explicitly parent-attributable.

## Verified Numbers

| Item | 2026 H1 / June 30 | Comparison | Page |
| --- | ---: | ---: | --- |
| Revenue | 64,330,936,547.38 | 2025 H1: 61,776,746,682.68 | 52 |
| Parent-attributable profit | 5,758,628,097.79 | 2025 H1: 7,200,477,611.91 | 53 |
| Operating cash flow | 9,759,147,483.18 | 2025 H1: 2,964,215,363.27 | 55 |
| Asset impairment loss | -2,455,875,173.02 | 2025 H1: -337,447,486.85 | 52 |
| Short-term borrowing | 64,677,193,034.15 | 2025 year-end: 45,630,626,027.83 | 49 |
| Contract liabilities | 4,948,856,599.18 | 2025 year-end: 10,564,239,506.92 | 49 |
| Gross purchases of long-lived assets | 1,304,262,044.68 | 2025 H1: 1,452,716,041.52 | 56 |

The existing shared fact verifier accepted all six registered facts. Each
matched the frozen v13 snapshot. Six comparative-value substitutions were
rejected: the preceding-period column cannot silently become the current fact.
This verifies item-level numerical placement, not complete financial quality.

## Cash Reconciliation

Physical page 56, checked with Decimal arithmetic:

```text
Operating cash flow                 9,759,147,483.18
Investing cash flow               -13,195,068,088.81
Financing cash flow                  -241,598,720.31
FX effect                             -85,791,022.96
Net cash/equivalent movement        -3,763,310,348.90

Opening cash/equivalents            17,677,587,920.54
Closing cash/equivalents            13,914,277,571.64
```

Both sums reconcile exactly. Revenue grew 4.13% and parent profit fell 20.02%
year-on-year. Operating cash flow grew 229.23%, while short-term borrowing rose
41.74% and contract liabilities fell 53.15% against year-end. These are different
comparison periods, explicitly kept separate.

## Research Implications And Limits

- Improved operating cash flow is a positive observation, but it coexists
  with declining earnings, material impairment, negative total cash movement
  and increased short-term borrowing. It is not sufficient evidence of durable
  earnings quality or dividend sustainability.
- CFO less gross capital purchases is CNY 8,454,885,438.50. It is only a
  descriptive consolidated cash proxy, not FCFF, FCFE or parent ordinary-share
  distributable cash. Maintenance/growth investment, financing, restrictions
  and parent/subsidiary cash access are not resolved by this subtraction.
- The CNY 6,287,065,552.99 cash-flow line combines dividends, profit
  distributions and interest. Do not use it as ordinary-share dividend cash or
  claim a dividend coverage ratio from it.
- June cash, borrowing and share balances do not prove September SCP010/011
  settlement or post-maturity liquidity. This review does not reopen the
  registered evidence stop, infer payment/default, or establish ModelValidity.
- The report is unaudited interim evidence. Publication-date metadata and
  current extraction do not independently prove historical capture/PIT.

## Reproduction And State

Numeric receipt: `runtime/financial-quality-review-20261001/review.json`,
SHA-256 `22613674337cee28d96bb5de9822958ab0ad1715c2495879fe894e42bffb740c`.
It contains fourteen source rows, excerpts, comparative periods, frozen
snapshot/config bindings, calculations and actual current observation time.
The bounded review script is retained under `.tmp/review-yili-financial-quality.py`;
the receipt is immutable, so reruns require a new output rather than overwrite.

No model, threshold, frozen snapshot, official source or canonical workbook
changed. No current research/financial gate was approved. Strict PIT remains
NOT_PROVEN; ModelValidity NOT_ESTABLISHED; current decision NOT_READY.

The concrete reopen condition remains new eligible official settlement and
post-maturity cash/debt evidence, followed by current research, quote and
portfolio admission. Engineering and honest historical/research display can
continue without treating this external requirement as satisfied.
