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

For scale only, CNY 25bn equals 33.51% of the 2026H1 consolidated cash and
cash-equivalent balance of CNY 74.614244bn, and 52.85% of 2026H1 short-term
borrowings of CNY 47.305038bn. These are cross-date size comparisons, not a
netting calculation: the three notes were issued after the June 30 balance
sheet date and redeemed on September 24.

## Materiality and dependency disposition

Classify as `MATERIAL_RISK_MONITOR_CANDIDATE` because the confirmed CNY 25bn
principal is large relative to the latest retained cash and short-term debt
facts. Reopen only the affected forward-looking dependencies:

- Post-H1 short-term debt and maturity schedule.
- Post-redemption cash and liquidity bridge.
- Any net-debt bridge that uses post-June 30 balances.
- Dividend-capacity context that depends on current cash or refinancing.

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
