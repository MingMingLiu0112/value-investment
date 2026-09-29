# China Shenhua 2026H1 acquisition, segment and capex supplement

Date: 2026-09-29
Case: `prospective-601088-20260927-v2`
Disposition: supplemental public research only; not an item-level baseline admission, normalized-cycle input, valuation, or investment recommendation. `action=no_order`.

## Source and availability

The source is China Shenhua's 2026 interim report, CNINFO announcement
`1225531759` ([official PDF](https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF)). The retained original is
`runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf`, SHA-256
`ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`.
This matches the hash in the existing H1 source admission. CNINFO's date marker
is 2026-08-29; the admitted conservative availability is 2026-08-30T00:00:00+08:00.
This is a late review of a pre-existing report, not proof of contemporaneous
capture or strict PIT. Physical report pages are cited below.

## Separate retained restructuring report review

A second official filing was reviewed as a bounded follow-up to the acquisition-perimeter question. It is a different document from the 2026 interim report above: CNINFO announcement `1224979750`, retained at
`runtime/company-research/shenhua-acquisition-2026-02/1224979750.pdf`.
The file is 20,495,810 bytes and its directly measured SHA-256 is
`533bc24a80aeb1fbf2357218c5c19825cb0ab23176eb7d25d8ecd2d1f1256703`.
No separate manifest was retained in that directory; the PDF is under ignored
`runtime/` and is not included in a public GitHub clone. The hash therefore
binds this local retained file for this review, not an independently signed or
publicly reproducible source package. Do not substitute it for the H1 report's
`1225531759` / `ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`.

The PDF contains 2,886 physical pages and has no PDF page labels. The physical
page numbers below differ by one from the printed page numbers:

| PDF physical page | Printed page | Bounded observation |
|---:|---|---|
| 20 | `1-1-19` | Target companies' aggregate 2024 adjusted net profit attributable to parent was CNY 9.428bn; excluding long-lived-asset impairment, CNY 10.570bn. |
| 555 | `1-1-554` | Pro forma adjusted net profit attributable to parent increased from CNY 58.962bn to CNY 66.851bn for 2024 (CNY 7.889bn transaction increment); for 2025 January-July, from CNY 29.255bn to CNY 32.637bn (CNY 3.382bn increment). |
| 1281-1322 | `1-1-1280` onward | Target-company financial statements. |
| 1323-1328 | `1-1-1322` onward | Pro forma consolidated financial statements. |

This bounded review establishes recent target-level and pro forma contribution,
not current-perimeter mid-cycle earnings. It contains one full year plus seven
months for the pro forma comparison; do not annualize the seven-month result,
splice target-company aggregate profit directly into Shenhua attributable
profit, or treat the report's valuation forecasts as a cross-cycle operating
series. It does not change frozen baseline v13, prove strict PIT, or close the
valuation A blocker.

## Facts

### Acquisition perimeter and funding disclosures

The report says the equity interests in 12 target companies were registered
under Shenhua by 2026-03-17; 11 became subsidiaries, while the 49% interest in
Jinshen Energy became an associate (pp. 56-57). It records control of the
acquired subsidiaries from 2026-04-01 in the combination note (pp. 177-178).

Page 56 reports contractual transaction terms of CNY 40,080m in share
consideration (1,363,248,446 A shares at CNY 29.40) and CNY 85,791m cash. It
also separately describes CNY 7,728m cash consideration for the 100% equity
interest in Inner Mongol JianTou acquired from Xibu Energy. Page 65 says a
separate placement raised CNY 20,000m gross and CNY 19,967.49m net; by June 30,
the net proceeds had been fully used for cash consideration, intermediary
fees, and related taxes. This is only a partial funding disclosure, not a
complete reconciliation of acquisition cash payments and funding sources.

The common-control accounting table on page 178 lists 11 acquired companies
and CNY 90,942m cash plus CNY 1,322m share face value, for CNY 92,264m reported
combination cost. This accounting table has a different perimeter and share
measurement from the contractual terms on page 56; the figures are not
interchangeable and are not forced into a single bridge here.

Page 16 reports consolidated net cash used in investing activities of
CNY 36,007m in 2026H1, versus restated CNY 31,432m in 2025H1. This is a total
cash-flow measure, not the acquisition payment amount; it does not resolve the
cash-consideration reconciliation.

Page 91 separately reports consolidated cash paid to acquire fixed assets,
intangible assets and other long-lived assets of CNY 29,579m in 2026H1,
versus restated CNY 32,163m in 2025H1. These are cash payments, distinct from
the page 210 segment-capex measure. Cash payments fell about 8.0% while
reported segment capex rose about 5.5%; the respective differences are
CNY 6,289m and CNY 10,087m. The report does not reconcile these differences
here, and they must not be assigned to maintenance or growth spending without
asset-level evidence.

Page 93's **company-only** cash-flow statement separately reports CNY 90,942m
cash paid to acquire subsidiaries in 2026H1. This matches the CNY 90,942m cash
component in the page 178 common-control combination table for 11 controlled
subsidiaries. This is a useful perimeter cross-check, not a consolidated
cash-flow bridge or proof of the funding source. The page 56 contractual
cash terms, including the separately described CNY 7,728m Inner Mongol
JianTou payment, exceed this amount by CNY 2,577m; the residual is not
attributed to a target or consideration component without target-level
source support.

### Segment results and reported capex

The segment table on page 210 labels 2025H1 as restated. Amounts below are
CNY million; the page omits a separate unit legend, and segment revenue totals
reconcile to the CNY 189,338m consolidated revenue on page 16.

| Segment | Segment profit 2026H1 | Segment profit 2025H1 restated | Segment capex 2026H1 | Segment capex 2025H1 restated |
|---|---:|---:|---:|---:|
| Coal | 26,998 | 26,663 | 6,271 | 6,118 |
| Power | 5,804 | 6,012 | 11,654 | 11,071 |
| Railway | 7,662 | 7,037 | 1,286 | 1,136 |
| Port | 1,561 | 1,351 | 1,002 | 287 |
| Shipping | 427 | 282 | 1 | 1,001 |
| Coal chemicals | 2,132 | (338) | 2,901 | 2,459 |
| Unallocated | 1,235 | 2,703 | 175 | 4 |
| Eliminations | (325) | (539) | — | — |
| Total | 45,494 | 43,171 | 23,290 | 22,076 |

Segment profit is not parent-attributable net income or owner cash flow.
Reported segment capex is spending/costs on segment assets expected to be used
for more than one year; it is not a cash-payment schedule and the report does
not split maintenance from growth capex.

Page 23 separately reports exploration expenditure of CNY 50m versus CNY 540m
in 2025H1, mainly for Xinjie mine exploration, and mine development/extraction
related capital expenditure of CNY 3,210m versus CNY 1,490m, mainly mine
construction and land-use-right acquisition. These categories are not added to
the segment-capex table and are not treated as cash paid without a
reconciliation.

## Assumptions and unknowns

No new model assumption is admitted. In particular, this supplement does not
assume segment profit is distributable cash, segment capex is cash paid, or
any capex is maintenance or growth spend.

Still unknown are acquisition-adjusted steady-state segment earnings over a
comparable full period; target attribution of the CNY 2,577m contractual/cash
residual; maintenance versus growth capex by asset and the timing/scope bridge
between cash paid and segment capex; project returns; and the acquired assets'
contribution across a full comparable period. The retained restructuring report
has now received the bounded review above, but it does not supply a full
comparable post-acquisition cycle or a defensible mid-cycle earnings range.
Stop reviewing this same report; reopen only if new official evidence changes
the current-perimeter cycle bounds or resolves one of the stated blockers.

## Research effect

The two separately hash-described reports add bounded acquisition-perimeter
observations: the H1 report provides 2026H1 segment/capex facts, and the
retained restructuring report provides recent target and pro forma results.
The latter's local file hash has no retained manifest and is not present in the
public repository. Neither report establishes normalized cyclical earnings,
owner cash flow, or sustainable ordinary dividend capacity. Keep
`CYCLICAL_MODEL_NOT_READY`, `VALUATION_NOT_READY`, and dividend sustainability
`NOT_READY`. Do not update frozen baseline v13, valuation, canonical workbook,
or decision status from this evidence alone. It does not advance the formal
event watermark or prove strict PIT. `action=no_order`.
