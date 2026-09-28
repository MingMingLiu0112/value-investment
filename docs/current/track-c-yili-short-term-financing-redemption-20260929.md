# Yili Short-Term Financing Redemption Observation — 2026-09-29

## Status

This is a verified public-source observation and a `MATERIAL_RISK_MONITOR`
candidate. It is not a formal M5 `EventMaterialityDecision` or applied
`ChangeEvent`. The registered 2026-09-27 baseline remains frozen; the scan
does not prove strict contemporaneous PIT.

## Verified facts

CNINFO notice `1225584526`, dated 2026-09-29, reports that Yili completed
redemption on 2026-09-24 of its 2026 twelfth, thirteenth and fourteenth
super-short-term financing notes. Their principals were CNY 7.5bn, CNY 10bn
and CNY 7.5bn, respectively, for CNY 25bn total. Each carried a 1.29% rate
and an 83-day term. The reported settlement totals were CNY
7,522,000,684.93, CNY 10,029,334,246.58 and CNY 7,522,000,684.93. They sum to
CNY 25,073,335,616.44, including CNY 73,335,616.44 interest.

The notice confirms payment of these specific notes. It does not identify the
cash source, refinancing activity, post-redemption cash balance, or remaining
short-term debt. The event therefore neither proves a liquidity improvement
nor proves a liquidity deterioration.

### Earlier issuance and maturity schedule

The issuer's 2026 tenth-to-fourteenth super-short-term financing note
issuance-results notice, CNINFO `1225412264` ([official PDF](https://static.cninfo.com.cn/finalpage/2026-07-07/1225412264.PDF)),
dated 2026-07-07, reports five issues totaling CNY 45bn. Issues 12-14 totaled
CNY 25bn principal, began accruing on 2026-07-03, and matured on 2026-09-24;
issues 10-11 totaled CNY 20bn principal, began accruing on 2026-07-02, and
were scheduled to mature on 2026-09-29. The July notice reports issue terms,
not the actual use of proceeds, and does not connect the July proceeds to the
September 24 repayment. The September 24 redemption notice verifies payment of
issues 12-14 only.

The July source was available before the registered 2026-09-27 research cutoff,
but this is a late source review and does not establish that the registered
baseline used it. It narrows the known maturity schedule; the source and
post-redemption cash/debt bridges remain unknown. As of this bounded review,
the September 29 maturity date for issues 10-11 has arrived, but no payment
completion is inferred from the schedule or the limited CNINFO snapshot.

## Correction: issuer attribution and scale comparison

An earlier version of this note incorrectly used Midea Group's 2026H1
consolidated figures as Yili figures. The CNY 74.614244bn cash-equivalent
balance and CNY 47.305038bn short-term borrowings belong to Midea Group, not
Yili; those figures and the resulting 33.51% and 52.85% comparisons are
withdrawn from the Yili analysis. They are verified in Midea's 2026H1 report,
CNINFO document `1225531404`, SHA-256
`576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`.

Yili's own 2026H1 report, CNINFO document `1225511409`, reports consolidated
short-term borrowings of CNY 64,677,193,034.15 on printed page 46 (PDF page
49), and ending cash and cash equivalents of CNY 13,914,277,571.64 on printed
pages 170-171 (PDF pages 173-174). The retained report SHA-256 is
`423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`.

For scale only, the CNY 25bn note principal is approximately 179.67% of
Yili's June 30 cash and cash equivalents and 38.65% of its June 30 short-term
borrowings. These compare a September 24 redemption with June 30 balances;
they are not a post-redemption cash/debt bridge, netting calculation, or
standalone measure of liquidity pressure. The redemption notice does not
disclose the funding source or balances after redemption, so no direction of
liquidity change can be inferred.

## Materiality and dependency disposition

Classify as `MATERIAL_RISK_MONITOR_CANDIDATE` because the confirmed CNY 25bn
principal is large relative to the latest retained cash and short-term debt
facts. Reopen only the affected forward-looking dependencies:

- Post-H1 short-term debt and maturity schedule.
- Post-redemption cash and liquidity bridge.
- Any net-debt bridge that uses post-June 30 balances.
- Dividend-capacity context that depends on current cash or refinancing.
- Whether the two CNY 10bn issues scheduled for 2026-09-29 were repaid or
  refinanced, once an eligible official disclosure becomes available.

Do not rewrite 2026H1 financial statements, infer a current debt balance, or
change ordinary/special dividend classification, normalized distributable
cash, valuation, thesis, or decision status from this notice alone. Further
research should use a later issuer filing that reports cash and debt balances
or separately verified issuance/redemption disclosures. No order or trade
signal is produced (`action=no_order`).

## Availability and provenance

The official notice is [CNINFO PDF](https://static.cninfo.com.cn/finalpage/2026-09-29/1225584526.PDF),
SHA-256 `4ef69c200e7b3d0cde3e1b667bcbb4304d15dd6aa406585ca796aa2c3ab4a270`.
The retained local copy is
`runtime/company-research/m1-yili-event-followup-20260929/1225584526.pdf`.
It identifies security `600887`, issuer organization `gssh0600887`, and
announcement `临 2026-070`.

Because the publication timestamp is date-only, use conservative
`available_at=2026-09-30T00:00:00+08:00`. The exact-issuer CNINFO query
covered the requested date window 2026-09-28..2026-09-29 and returned this
notice once, with pagination complete for that retrieval. The retrieval time
was 2026-09-29 00:31:18 +08 according to the local process clock; that clock
is not independently attested. Retained scan receipt:
`runtime/prospective-public-event-2026-09-29/gapfill-600887-20260928T163118110265Z/scan-receipt.json`,
SHA-256 `afa5db545de95f43415e5aa2eebfc281a002ae8fc4661d9f4916b00455976c1c`.

This is a bounded CNINFO retrieval snapshot, not full-day or multi-channel
coverage. Formal watermark coverage remains at the v8 registered boundary;
the successor v9 records this snapshot without advancing that watermark.
The canonical workbook is unchanged because its current cutoff is 2026-09-28
and this notice's conservative availability begins on 2026-09-30.

The earlier issuance-results PDF is retained at
`runtime/company-research/yili-financing-results-20260707/1225412264.pdf`,
SHA-256 `f8c529139b7f49d73f355ecd41c8dea44e68ff35765379538dd090ccba5f6a2d`.
