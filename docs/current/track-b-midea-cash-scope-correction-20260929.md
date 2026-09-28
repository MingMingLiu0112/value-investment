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

The source is Midea's [FY2025 annual report](https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF),
SHA-256 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`.
The current evidence package is
`runtime/company-research/midea-fcff-facts-20260929/evidence.json`, SHA-256
`d0453422d13fe2c30e3f623de2ad07357b9e6f287fb12ed900937d577d67bc40`;
`runtime/company-research/midea-fcff-facts-latest.json` points to that package.

### Source locator correction

An earlier version of this note linked CNINFO document `1225259562` dated
2026-04-30 while citing the Midea annual-report hash above. That URL returns
different bytes (SHA-256
`d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac`) and is
not the cited Midea report. The corrected Midea CNINFO URL above returned
HTTP 200 and 5,942,399 bytes with the cited hash; the retained local source
`runtime/midea-2025-official.pdf` has the same hash. This corrects the source
locator only; the reported amounts, their page references, and frozen
baseline v13 are unchanged.

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

## FY2026H1 segment and financial-business scope

The same report's consolidated income statement (physical p. 98) and segment
note (physical pp. 186-188) reconcile total external segment revenue to
consolidated **total operating revenue**. Amounts are CNY thousand:

| Revenue line | 2026H1 | 2025H1 |
| --- | ---: | ---: |
| Operating revenue (`营业收入`) | 260,042,490 | 251,123,714 |
| Interest revenue | 1,009,683 | 1,207,524 |
| Commission and fee revenue | 206 | 256 |
| Total operating revenue (`营业总收入`) | 261,052,379 | 252,331,494 |
| Segment-note external revenue total | 261,052,379 | 252,331,494 |

The segment-note totals therefore do not conflict with the smaller `营业收入`
line; the difference is the separately presented interest and commission
revenue. Intersegment revenue of CNY 19,563,948 thousand in 2026H1 (CNY
21,102,913 thousand in 2025H1) is eliminated by the matching amounts in the
segment table. Do not add intersegment revenue to consolidated external
revenue.

The four reported segments are smart home, building technologies, industrial
technology, and other segments. The report says the other-segment activities
include financial services alongside automation, energy-storage, logistics,
medical-device and other businesses. The segment table combines `other
segments and unallocated amounts`; it does not show a standalone finance
segment. Its 2026H1 column reports assets of CNY 421,870,161 thousand and
liabilities of CNY 399,730,346 thousand, before large consolidation
eliminations. The report also allocates indirect expenses among segments in
proportion to revenue. These disclosures cannot establish finance-only
earnings, cash, debt, working capital or capital needs.

Reported total segment profit was CNY 24,601,987 thousand in 2026H1 versus
CNY 31,310,842 thousand in 2025H1. The segment note's separate `other
gains/losses` row was CNY 7,242,569 thousand versus CNY 32,447 thousand; adding
each amount to the segment-profit total ties to reported profit before tax of
CNY 31,844,556 thousand and CNY 31,343,289 thousand, respectively. The cited
table does not decompose that other-gains/losses row by business. Neither the
segment-profit total nor a revenue-based allocation is a finance-only EBIT,
normalized FCFF or forecast input.

Disposition: the source cross-check resolves the revenue presentation and
confirms financial services are grouped with other businesses, while the
profit/cash/debt carve-out remains unavailable. The separate related-party
balance reconciliation is documented in
[`track-b-midea-related-party-bridge-review-20260928.md`](track-b-midea-related-party-bridge-review-20260928.md).
This late-researched pre-start supplement is not strict-PIT evidence and does
not amend baseline v13.

## Research effect

The new package and source reconciliations close a cash-field labeling error,
clarify consolidated revenue presentation, and sharpen the consolidated
liquidity picture. They do not resolve Midea's industrial/financial-business
scope, maintenance versus growth CapEx, the valuation share denominator, or
cost of capital. Keep `financial_scope_approved=false`, `net_debt=null`,
`MODEL_NOT_READY`, `VALUATION_NOT_READY`, and `action=no_order`.
