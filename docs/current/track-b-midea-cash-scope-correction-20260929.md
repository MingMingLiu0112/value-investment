# Midea Cash-Scope Correction — 2026-09-29

## Status

This is an additive, source-verified research supplement. It does not modify
the frozen prospective baseline v13 (`ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`),
produce a net-debt estimate, or make Midea valuation-ready. The old v2 evidence
bytes remain preserved; the current facts pointer now resolves to a versioned
v3 package.

## FY2025 field correction

The FY2025 package had placed CNY 85,247,150,000 of balance-sheet **monetary
funds** into the field named `cash_and_cash_equivalents_cny`. The audited annual
report distinguishes these items: consolidated monetary funds were CNY
85,247,150 thousand on physical PDF page 132, while year-end cash and cash
equivalents were CNY 68,508,670 thousand on physical PDF pages 234-235.

The successor package records them separately:

| Field | FY2025 value | Source scope |
| --- | ---: | --- |
| `monetary_funds_cny` | 85,247,150,000 | Consolidated balance sheet, CNY |
| `cash_and_cash_equivalents_cny` | 68,508,670,000 | Cash-flow statement and note, CNY |

The source is Midea's [FY2025 annual report](https://static.cninfo.com.cn/finalpage/2026-04-30/1225259562.PDF),
SHA-256 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`.
The current evidence package is
`runtime/company-research/midea-fcff-facts-20260929/evidence.json`, SHA-256
`d0453422d13fe2c30e3f623de2ad07357b9e6f287fb12ed900937d577d67bc40`;
`runtime/company-research/midea-fcff-facts-latest.json` points to that package.

## FY2026H1 liquidity facts

The retained 2026H1 report provides a more recent consolidated snapshot.
Amounts below are CNY billions; source statement amounts are in CNY thousands.

| Item | 2026-06-30 | Physical PDF page(s) |
| --- | ---: | --- |
| Monetary funds | 90.642783 | 96, 146 |
| Cash and cash equivalents | 74.614244 | 99, 177 |
| Restricted monetary funds | 15.925778 | 164 |
| Accrued interest within monetary funds | 0.102761 | 146 |
| Short-term borrowings | 47.305038 | 97 |
| Current portion of non-current liabilities | 5.063161 | 97 |
| Long-term borrowings | 15.417300 | 97 |
| Bonds payable | 6.665757 | 97 |
| Lease liabilities | 1.919149 | 97 |

The arithmetic `90.642783 - 15.925778 - 0.102761 = 74.614244` reconciles the
reported monetary-funds amount to cash and cash equivalents after the cited
restricted funds and accrued interest. It does not establish industrial
segment ownership, unrestricted upstreamability, or cash available to
shareholders. Financial subsidiaries and intercompany balances remain in the
consolidated scope; do not calculate industrial net debt by subtracting these
cash totals from consolidated borrowings.

The source is Midea's [2026 interim report](https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF),
SHA-256 `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`.
The retained local original is
`runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf`.
Using the report date with the conservative next-day convention gives
`available_at=2026-08-30T00:00:00+08:00`. These are late-researched public
facts that were available before the registered cutoff; adding them here
does not rewrite the baseline or establish a contemporaneous decision chain.

## Research effect

The new package and source reconciliation close a cash-field labeling error
and sharpen the consolidated liquidity picture. They do not resolve Midea's
industrial/financial-business scope, maintenance versus growth CapEx, the
valuation share denominator, or cost of capital. Keep `financial_scope_approved=false`,
`net_debt=null`, `MODEL_NOT_READY`, `VALUATION_NOT_READY`, and `action=no_order`.
