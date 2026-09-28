# Track B Shenhua 2026H1 source admission, 2026-09-27

Scope: public baseline facts for registered case `prospective-601088-20260927-v2` only. This is item-level source admission, not a valuation or investment recommendation. `action=no_order`.

## Source binding

CNINFO lists announcement `1225531759`, titled `中国神华2026年半年度报告`, for issuer `601088`, with date-level announcement marker `2026-08-29`. The bounded issuer scan was retrieved at `2026-09-27T07:06:20.930086Z`; the index, scan evidence, and PDF are bound in `config/prospective-baseline-verification-v8.json`. The original is [CNINFO PDF](https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF), archived at `runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf`, SHA-256 `ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4`.

Because CNINFO provides a date-level marker rather than an independently verified release time, the facts use the conservative next-day availability `2026-08-30T00:00:00+08:00`.

## Admitted values

Physical/printed page 6, section “主要会计数据”, reports the unit as CNY million. The page's ordered columns identify 2026H1 first, followed by 2025H1 comparison columns. The comparison values below are the report's restated 2025H1 figures; the report also separately shows the pre-restatement figures.

| Fact | 2026H1 | 2025H1 restated | Dependency |
|---|---:|---:|---|
| Revenue | CNY 189,338m | CNY 175,423m | financial quality |
| Parent-attributable net profit | CNY 28,715m | CNY 27,583m | financial quality |
| Net cash from operating activities | CNY 54,664m | CNY 51,545m | financial quality |

The three current-period facts are admitted; the restated comparison values are source context only and are not separate admitted facts in this snapshot. They must not be mixed with the report's pre-restatement comparator.

## Column binding

The admission check uses pypdfium2 character boxes from the original PDF. It requires distinct ordered bounding boxes for the `2026年上半年` and `2025年上半年` headings, then checks that each fact row's first numeric cell falls under the 2026H1 group while the next two cells fall under the 2025H1 group. It also requires the value row to be vertically below the headers. If character coordinates are missing, ambiguous, shifted, or inconsistent with the displayed period order, the fact is rejected. A negative test shifts the revenue current value into the comparison column and confirms fail-closed behavior.

## Assurance and limits

The report states that its interim financial statements are unaudited. The attached accountant's review report provides limited assurance under the review standard and explicitly says no audit was performed and no audit opinion is expressed. The workbook therefore labels this boundary rather than calling the figures audited.

These headline facts do not establish normalized coal-cycle earnings, unit-cost bridge, maintenance versus growth capex, ordinary-dividend sustainability, or valuation. Shenhua remains `VALUATION_NOT_READY`; the three-company snapshot remains `strict_pit_admissible=false` because registration time has no independent TSA/signature attestation. This admission does not advance the formal public-event watermark, which remains `INCOMPLETE`.

The successor snapshot is `runtime/prospective-baseline-20260927/snapshot-v12-h1-column-bound.json` (SHA-256 `7de4c67f00f1096795b684d7cb1510f0c80418ae92f2ea677c1589e4d8dd988f`). Facts input SHA-256: `94e481589554613d4eafd22ef5606aeb59296545af8b7f4d39f399467e7b5f24`. Publication and WPS read-only verification are recorded in `docs/execution-status.md`. Final user acceptance remains `NOT_PASSED`; `action=no_order`.
