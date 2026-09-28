# Track C public event check, 2026-09-27

Read-only CNINFO source audit at 2026-09-27 00:39:25 UTC (08:39:25 China time), on Git HEAD `c9449a4fe8881a0cec9ce2f992622b48693c413a`. This precedes the v2 observation start of 08:45 China time and is not a prospective checkpoint. Source index: `https://www.cninfo.com.cn/new/hisAnnouncement/query`. The existing `search_announcement_window` client used exact symbol filters, page size 100, and checked returned IDs. Hashes below are SHA-256 of its canonicalized JSON index objects (sorted keys, compact separators, UTF-8), not hashes of raw HTTP response bytes. This audit does not advance registered watermarks.

| Symbol | Registered CNINFO watermark | Queried date window (China time) | Index SHA-256 | Result |
| --- | --- | --- | --- | --- |
| 000333 | 2026-09-27 00:24:16 UTC, INCOMPLETE | 2026-09-27 | `e0196223e9b450baecd2ea106bf4e2c616e45a24e779ed017514b5aef881474d` | 0 records |
| 600887 | 2026-09-22 16:00:00 UTC, COMPLETE | 2026-09-23 to 2026-09-27 | `b08fd509408a155997e695c6b78e40faeadcc75c1a7172c480e77bcea38d4154` | 1 record |
| 601088 | 2026-09-27 00:24:16 UTC, INCOMPLETE | 2026-09-27 | `9e68af481a72e0a69c90963e9aeafc444e428f122e2e79f10386ee222fd2e7e7` | 0 records |

The 600887 record is CNINFO announcement ID `1225578520`, PDF `https://static.cninfo.com.cn/finalpage/2026-09-24/1225578520.PDF`. CNINFO's `announcementTime` is `1790179200000`, equivalent to 2026-09-24 00:00:00 +08:00; treat this as a date-level disclosure marker, not a verified publication second. The two-page PDF identifies 600887 and announcement number `临2026-069`, titled `关于2023年持股计划（第三期）完成股票购买的公告`. The PDF returned HTTP 200, `application/pdf`, 100986 bytes, `%PDF-` signature at 2026-09-27 00:39:38 UTC. Its byte SHA-256 is `7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`. Its first page states purchase completion on 2026-09-22; this is an effective/event date, distinct from disclosure date. No materiality conclusion is made from the title or this check.

Gaps: 000333 and 601088 remain INCOMPLETE in the registered ledger; today's empty windows do not establish complete coverage of any earlier period. The 600887 query covers calendar dates after its prior watermark, but no new watermark was recorded, and the CNINFO index hash is a derived serialization rather than a raw-response archive. The query does not verify issuer IR or exchange sources, subsequent corrections, or whether the disclosure changes any model input. A fresh post-start observation would need its own system timestamp and evidence. Reopen the affected research only after document-level review and dependency assessment. `action=no_order`; no ACTUAL application, production notification, or workbook action.

## Post-start bounded observation

One read-only CNINFO scan was sent at 2026-09-27 00:48:35 UTC, after the 08:45 China observation start. The append-only run directory is `runtime/prospective-public-event-20260927/20260927T004835372Z/`. `receipt.json` (SHA-256 `730ea9ced3609192b659539f32757cc5dd0b3eb72e71b985cbdfab593fbfd3cf`) records per-request system send/receive times and response hashes. Its parsed `total` and `announcements` summary fields are null/empty because that parser invocation failed; the raw responses were preserved. `interpretation.json` (SHA-256 `4bcade44b280400396644ba7e698133ac479013d05d257b470affc50f406b18e`) is the subsequent, append-only parse of those same raw bytes. It reports `hasMore=false` and exact issuer codes for the returned item. Neither receipt advances a registered watermark.

| Symbol | Window, China calendar dates | Raw response path within run directory | Raw byte SHA-256 | Official result |
| --- | --- | --- | --- | --- |
| 000333 | 2026-09-27 | `000333-page1.raw.json` | `c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114` | HTTP 200; total 0; prior coverage INCOMPLETE |
| 600887 | 2026-09-23 to 2026-09-27 | `600887-page1.raw.json` | `deb64898cd1e39774942c22fd858aa8aabbca8f51a133a183d5b6837b9f6acee` | HTTP 200; total 1; `cninfo:1225578520` |
| 601088 | 2026-09-27 | `601088-page1.raw.json` | `c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114` | HTTP 200; total 0; prior coverage INCOMPLETE |

The fresh official PDF response, `600887-1225578520.pdf`, was received at 2026-09-27 00:48:36.4933271 UTC: HTTP 200, 100986 bytes, `%PDF-` signature, SHA-256 `7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`. Its official document ID is `cninfo:1225578520`, URL `https://static.cninfo.com.cn/finalpage/2026-09-24/1225578520.PDF`; the bytes match the earlier archived copy. CNINFO's midnight `announcementTime` is treated as date-level metadata, not a verified publication second.

Document-level assessment: announcement `临2026-069` says the 2023 employee holding plan's third tranche bought 8,476,357 existing shares through exchange trading on September 22 for CNY 224,997,098.71 excluding fees, average CNY 26.5441 per share, about 0.13% of total shares; the purchase is complete and the disclosed lockup is 12 months. This is a capital-allocation and ownership/float monitoring lead, but the document does not establish a new issuance, a changed ordinary-share denominator, a dividend, or a measured change to operating cash flow, earnings, ROIC, or sustainable distributable cash. Funding and accounting treatment cannot be resolved from this two-page notice alone. Accordingly, materiality to the prospective valuation remains **UNDETERMINED**, with no model-input change or research-status promotion. Revisit the `capital_allocation`, `ordinary-share denominator`, and potentially `financial_quality` dependencies only after tracing the plan's funding and accounting through governing disclosures/financial statements; `business_quality` and `dividend_sustainability` have no demonstrated direct change here. The 000333/601088 empty daily windows leave their earlier INCOMPLETE coverage unresolved. `action=no_order`; no ACTUAL apply or production/WPS/private-data action.

## Validated contiguous successor scan

The earlier post-start re-fetch is retained as historical evidence but is not
used to advance the watermark because its receipt summary parse failed and it
did not preserve the full query contract. A new exact-issuer CNINFO scan was
performed at `2026-09-27T10:00:05.035069Z` for the contiguous interval
`2026-09-23..2026-09-27`, immediately after the prior 2026-09-22 boundary.
The new index is
`runtime/prospective-public-event-20260927/gapfill-600887-20260927T100004825304Z/index.json`
(SHA-256 `7231cfb60764ee91a3446a77a63569f31ece34d2b4264af47e398e781ac482cd`)
and contains the complete original query contract, one returned item, and
`hasMore=false`. Its archived raw page SHA-256 is
`deb64898cd1e39774942c22fd858aa8aabbca8f51a133a183d5b6837b9f6acee` and
matches the prior raw response. The source builder revalidated exact issuer,
window, pagination, index-to-raw equality, announcement ID `1225578520`, and
the official PDF bytes; scan evidence SHA-256 is
`a4e6857a2b3ec3b60cd7b98fca0ab9839c29040cee5ec55562f1068bbbcdd360` and PDF
SHA-256 remains `7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`.

Append-only watermark successor
`config/prospective-public-event-watermarks-v3.json` advances only 600887
through this bounded CNINFO interval. The 000333 and 601088 formal watermarks
remain `INCOMPLETE`. This confirms no additional CNINFO announcement in the
interval; it does not cover issuer-IR, exchange-site notices, later corrections,
or prove that the employee-plan disclosure changes valuation. Its document was
already public before registration, so no post-registration event or new PIT
observation is claimed. Broad materiality remains
`UNDETERMINED / INSUFFICIENT_EVIDENCE`; no model input, valuation, or workbook
state changes. `action=no_order`.

## Append-only observation correction

The initial observation record `prospective-2c9c950216328f270a1614e9f357fce5`
used the ambiguous classification
`PREEXISTING_SOURCE_DISCOVERED_AFTER_START`. Track C's contemporaneous
pre-start scan already listed `cninfo:1225578520` at 08:39:25 China time,
before the registered 08:45 start. The post-start run was therefore a re-fetch,
not first discovery. Its append-only successor is
`runtime/prospective-observations/600887/prospective-cd9d6cc7382f67d1565132787949682b.json`,
SHA-256
`76e7e48699dd184950f1a5e13517546d24b4ed56ef2476bf920ddc602f3f65f6`; it is
classified `PREEXISTING_PUBLIC_DOCUMENT_REOBSERVED_AFTER_START` and binds the
superseded record SHA-256
`dc675d603f56c8303239f719448af06f95fa1dbe3987872d80898df1abc4515f`. The
pre-start scan's underlying HTTP response bytes were not retained, so that
first-sighting claim remains documented but is not independently reproducible
from raw bytes. PIT evaluation must use the successor and must not count this as
a newly disclosed post-registration event.

## Funding and accounting follow-up (bounded)

Three official filings now narrow, but do not close, the funding question:

- The 2023 plan (`cninfo:1217393829`, published 2023-07-27; archived at
  `runtime/prospective-event-support/600887/1217393829-2023-plan.pdf`, SHA-256
  `b80c62cc47ae92c049ed628627cf7e24805b75c9dda0d4b5ce638c44bc427e43`)
  defines an award formula of 30% of the year-over-year increase in audited
  adjusted net profit and allows company award funding from after-tax profit,
  employee salary contributions, and employee financing/self-raised funds.
  These are permitted sources; they do not alone prove this tranche's actual
  funding mix.
- The 2026-04-30 board resolution (`cninfo:1225259570`, for the 2026-04-28
  meeting; archived at
  `runtime/prospective-event-support/600887/1225259570-2026-board-resolution.pdf`,
  SHA-256 `7369a05f737a7c786b226237a5149d59b0a243619bc005a5a94e660bae94f697`)
  reports CNY 225,018,899.80 of the third-phase after-tax award transferred
  into the plan account and 396 participants. This quantifies the disclosed
  transfer, but does not identify its accounting recognition period or gross
  pre-tax expense.
- The completion notice `cninfo:1225578520` reports CNY 224,997,098.71 of
  exchange purchases excluding fees. The difference from the transferred
  amount is CNY 21,801.09; retained evidence does not explain its disposition.
  The purchase was of existing shares through exchange trading, not a new
  issuance.

For scale only, CNY 225,018,899.80 is approximately 2.03% of Yili's audited
2025 adjusted attributable net profit (CNY 11,068,321,695.12) and 1.57% of
2025 operating cash flow (CNY 14,343,920,490.32). These are not materiality
thresholds: an after-tax plan-account transfer is not necessarily the same
measure or period as annual recognized expense or operating cash flow. The
comparison does not establish EPS, ROIC, distributable-cash, or dividend
sustainability effects. Denominators are from the archived audited 2025 annual
report `runtime/company-research/m1-valuation-filings-20260923/600887/2025-12-31-annual-ef988688acf64ebeafd5ad3da4721c9f3390ae9c204038cd4e1e3ae3b5ec8451.pdf`.

The audited 2025 annual report (physical PDF page 239) and unaudited 2026H1
report (physical PDF page 199) both mark the Note XV share-based-payment
disclosure items, including current-period share-based-payment expense, as
not applicable. Both reports also mark the optional disclosure of profit
excluding share-based-payment impact as not applicable. This narrows the
specific disclosed share-based-payment accounting path; it does not establish
that the plan award had zero cost or zero effect in other employee-benefit,
bonus, payable, or tax accounts. The 2026H1 reporting period also ends before
the September purchase completion. No retained disclosure currently ties the
third-phase transfer to a gross award cost, recognition schedule, cash-flow
classification, or any additional issuer guarantee/financing. The annual
report PDF is bound by SHA-256
`d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac` and the
2026H1 PDF by SHA-256
`423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`.

Disposition: preserve the historical receipt-bound `NOT_MATERIAL` only within
its scoped no-immediate-recalculation judgment. Current M5 queue disposition
stays `PENDING_HUMAN_REVIEW`; broader funding/accounting/dependency materiality
stays `UNDETERMINED / INSUFFICIENT_EVIDENCE`. No model input or valuation is
changed. Reopen on the next official financial report covering a period after
the 2026-09-22 purchase completion, or an official plan-account settlement
disclosure, and inspect the share-based-payment and employee-benefit notes.
Until then, do not assert broader `NOT_MATERIAL`, and do
not recalculate valuation solely from the purchase amount. `action=no_order`.

## Independent CNINFO watermark continuity audit — 2026-09-27

An independent read-only audit validated stored query indexes and raw-page
bindings without repeating covered scans. The formal watermarks for 000333 and
601088 remain `INCOMPLETE`: their original evidence points to the prospective
registration receipt rather than a CNINFO query receipt, so it cannot establish
the original query start, exact window or pagination. Later bounded scans are
not retroactively connected to that unsupported boundary.

For 000333, two adjacent complete exact-issuer windows are independently
verified and may be described as bounded coverage from 2026-03-31 through
2026-09-27:

| Window | Index | Index SHA-256 | Coverage |
| --- | --- | --- | --- |
| 2026-03-31..2026-08-28 | `runtime/prospective-public-event-20260927/gapfill-000333-20260927T135108559217Z/index.json` | `31d99109b568f0753d194165c86c98a2b157e7715e2fb5b505f976c502e51652` | 98 records, 4 complete pages |
| 2026-08-29..2026-09-27 | `runtime/prospective-public-event-20260927/gapfill-000333-20260927T114140840633Z/index.json` | `6c04cd73eeb3e3d79e9589b80398b96eafa34d36f7f49d317300a630e5ea1dab` | 8 records, complete pagination |

This does not establish coverage before 2026-03-31 or repair the formal
watermark's unsupported earlier boundary.

For 601088, retained complete queries support only separate windows:

| Window | Index | Index SHA-256 | Coverage |
| --- | --- | --- | --- |
| 2026-03-31 | `runtime/prospective-public-event-20260927/gapfill-601088-20260927T051418865783Z/index.json` | `99cb7f5143c4b37b44c7c954ea37701d8ea325b73d753ea65d7f44c9455d92e8` | one date, 2 complete pages |
| 2026-06-26..2026-08-27 | `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/index.json` | `fd953fc2c1a34df4249ea373efb1a2287a103833caccb6c38f89e118afbea44c` | complete interval |
| 2026-08-25..2026-08-31 | `runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/index.json` | `726a5b26757a6726cc699615738b39463a21af7b08d7728d11e677cb1e00e517` | overlaps prior interval |
| 2026-09-23..2026-09-26 | `runtime/prospective-public-event-20260927/gapfill-601088-20260927T045325203193Z/index.json` | `0717da2e13c2c17f95015a3c28795cd447cd0a3bf920cb917ca9b1f950175e2a` | 5 records, complete pagination |
| 2026-09-27 | `runtime/prospective-public-event-20260927/gapfill-601088-20260927T112235104724Z/index.json` | `e2c3b27cc18386024e27e349790df0478852271cca720647308a43dd22ceb9cc` | zero records, complete one-page query |

The uncovered intervals 2026-04-01..2026-06-25 and 2026-09-01..2026-09-22
prevent a continuous range claim. These are CNINFO exact-issuer results only;
they do not establish issuer-IR, exchange-site, correction or other-channel
coverage. Advance neither formal watermark until its coverage start is
explicitly versioned and every intervening gap has a query index with raw
response hashes, exact issuer/date parameters and complete pagination. No
duplicate query is warranted solely to move a watermark.
