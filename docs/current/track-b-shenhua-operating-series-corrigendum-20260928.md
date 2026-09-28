# Shenhua Operating-Series Corrigendum - 2026-09-28

This addendum corrects page references and records a bounded restatement and
segment bridge from retained annual-report originals. The source memos remain
unchanged. It does not admit these operating facts as normalized earnings,
change a baseline, or create a valuation input. `action=no_order`.

## Source and page corrections

The reviewed FY2025 HKEX report copy is
`runtime/shenhua-2025-official.pdf`, SHA-256
`460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`. The
separate CNINFO copy is
`runtime/prospective-baseline-20260927/shenhua-index-20260927T044701251789Z/shenhua-2025-annual.pdf`,
SHA-256 `7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2`.
They are two copies of the same annual report, not independent evidence.

- The 2025 segment note is PDF physical page 279, printed page 278. The prior
  baseline memo's printed-page citation is correct; any unqualified "physical
  page 278" citation should be corrected to "PDF physical page 279 (printed
  page 278)."
- The 2024 group blended coal price restated to CNY 563/t is on PDF physical
  page 30, printed page 29. PDF physical page 31 / printed page 30 is the
  customer-type table, not that blended-price row. The earlier classification
  memo's page reference is therefore corrected here without rewriting it.
- For the FY2025 coal product tables, use printed pages 28-32 (PDF physical
  pages 29-33), rather than citing only printed pages 30-32.
- The earlier source review records HKEX publication at 2026-03-30 22:47 HKT.
  The legacy `config/prospective-baseline-input-v1.json` value
  `available_at=2026-03-30T00:00:00+08:00` predates that publication and must
  not be treated as valid. The admitted v13 baseline uses the more conservative
  CNINFO next-day date boundary; do not change a frozen input until its active
  consumer and receipt chain are independently confirmed.

## Restated observations

Original and comparative values remain separate versions. Arithmetic below
was checked against the retained FY2023, FY2024 and FY2025 report copies; the
restated group values do not identify Hangjin Energy's standalone contribution.

| Measure | Original disclosure | FY2025 comparative | Check / implication |
|---|---:|---:|---|
| FY2023 group coal sales | 450.0 Mt | 454.6 Mt | +4.6 Mt |
| FY2023 self-produced coal sales | 325.4 Mt | 339.0 Mt | +13.6 Mt |
| FY2023 purchased coal sales | 124.6 Mt | 115.6 Mt | -9.0 Mt; each version sums to group sales |
| FY2023 electricity sold | 199.75 TWh | 205.17 TWh | +5.42 TWh |
| FY2024 group coal sales | 459.3 Mt | 460.2 Mt | +0.9 Mt |
| FY2024 self-produced / purchased coal sales | 327.0 / 132.3 Mt | 337.6 / 122.6 Mt | Each version sums to group sales |
| FY2024 group coal selling price | CNY 564/t | CNY 563/t | -CNY 1/t |
| FY2024 self-produced coal price / unit cost | CNY 527 / 179.0 per tonne | CNY 521 / 180.2 per tonne | Price -6; unit cost +1.2 |
| FY2024 electricity sold / average tariff | 210.28 TWh / CNY 403 per MWh | 215.41 TWh / CNY 402 per MWh | Scope remains group-reported; +5.13 TWh / -CNY 1 |

The FY2024 consolidated restatement (CNY million) is:

| Measure | Original FY2024 | Restated FY2024 | Change |
|---|---:|---:|---:|
| Operating profit | 88,362 | 87,082 | -1,280 |
| Profit before tax | 85,793 | 82,928 | -2,865 |
| Income tax expense | 16,928 | 16,929 | +1 |
| Profit attributable to parent | 58,671 | 55,805 | -2,866 |
| Profit attributable to non-controlling interests | 10,194 | 10,194 | 0 |

Both versions arithmetically reconcile: `85,793 - 16,928 = 68,865 = 58,671 +
10,194`; `82,928 - 16,929 = 65,999 = 55,805 + 10,194`. The original FY2024
statements are PDF physical pages 142-143. The FY2025 comparative statements
are PDF physical pages 337-338 (printed statement pages 9-10). Arithmetic
closure does not explain the acquisition-perimeter adjustments.

## Segment and operating bridge limits

The FY2025 segment note is on PDF physical page 278 / printed page 278 (CNINFO
copy SHA-256 `7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2`).
The earlier sentence locating it on physical page 279 was incorrect; physical
page 279 is the geographic-information note.

The segment table distinguishes coal external revenue (CNY 182,874 million),
coal inter-segment revenue (CNY 38,358 million), and coal-segment total revenue
(CNY 221,232 million). A prior sentence incorrectly described CNY 8,086 million
as the difference between coal-product revenue and coal external revenue. The
correct comparison is coal-segment **total** revenue less the coal-product
table: `221,232 - 213,146 = 8,086`. Likewise, coal-segment total cost less the
coal-product table cost is `154,631 - 149,708 = 4,923`. The product values are
in the report's coal-product table (PDF physical page 29 and page 32); the
segment values are on physical page 278. The report does not provide a
line-by-line bridge for either residual.

The aggregate FY2025 revenue and cost bridges do reconcile. External revenue
for all segments sums to CNY 294,916 million. Total segment revenue of
CNY 371,606 million less CNY 76,690 million segment eliminations also equals
CNY 294,916 million. Segment costs of CNY 267,425 million less CNY 75,960
million cost eliminations equal consolidated cost of CNY 191,465 million.
This closes the aggregate revenue/cost arithmetic, not the coal product-to-
segment residual or the bridge from segment profit to consolidated earnings.

The FY2025 report states Hangjin Energy was acquired at 100% under common
control on 2025-02-11 for CNY 853 million. It discloses Hangjin revenue/net
profit of CNY 361 million/CNY 1 million from the start of 2025 to acquisition,
FY2024 revenue/net loss of CNY 4,760 million/CNY 2,866 million, and a FY2023
net loss of CNY 1,938 million primarily attributable to Hangjin. The reviewed
material does not disclose Hangjin standalone FY2023 revenue. The difference
between Hangjin FY2024 disclosed revenue (CNY 4,760 million) and the group's
FY2024 revenue restatement (CNY 1,413 million) is CNY 3,347 million, but the
report gives no line-by-line standalone-to-consolidated reconciliation; any
elimination explanation remains an inference.

The report also shows 73.2 Mt of coal sales to the power segment versus 77.7 Mt
of power-segment consumption of coal sold within the Group, a 4.5 Mt difference
against 97.7 Mt total power coal consumption. It does not quantify a delivery,
inventory, timing, or measurement bridge. Do not force the product, segment,
and consumption scopes to balance.

## ResearchCase and gate effect

These are verified period facts, not a normalized cycle series. The restated
comparatives confirm that acquisition perimeter affects reported operating
series and FY2024 attributable profit; they do not isolate acquired economics.
For the existing 601088 ResearchCase, retain these concrete blockers:

- `ACQUISITION_PERIMETER_BRIDGE_INCOMPLETE` for operating and consolidated
  restatements, including the CNY 3,347 million FY2024 revenue difference and
  missing FY2023 acquired-entity revenue;
- `COAL_PRODUCT_TO_SEGMENT_BRIDGE_INCOMPLETE` for the CNY 8,086 million
  revenue and CNY 4,923 million cost residuals;
- `INTERNAL_COAL_VOLUME_BRIDGE_INCOMPLETE` for the 4.5 Mt sales/consumption
  difference. Aggregate FY2025 segment revenue and cost arithmetic reconciles;
  do not retain the broader label as if those aggregate totals were missing;
- `NORMALIZED_EARNINGS_NOT_ESTABLISHED` and `NORMALIZED_FCF_NOT_READY`;
- maintenance/growth CapEx split, sustainable ordinary-dividend capacity, and
  acquired-entity contribution remain unknown.

Accordingly `CYCLICAL_MODEL_NOT_READY`, `VALUATION_NOT_READY`, and the current
non-personalized decision remains `WAIT / NOT_ASSESSABLE`; no fair value,
price-attractiveness, or trading conclusion is derived. The facts narrow the
ResearchCase blockers but do not upgrade readiness.
