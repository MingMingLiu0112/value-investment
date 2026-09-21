# Midea Historical Suspension Evidence

Reviewed: 2026-09-09 Asia/Shanghai. Research evidence, not strategy approval.

## Original Disclosure

- Issuer: Midea Group, 000333; announcement 2018-092.
- CNINFO URL: https://static.cninfo.com.cn/finalpage/2018-10-29/1205546211.PDF
- Archive: `runtime/historical-filing-index/20260908T160809868309Z/pdfs/000333-1205546211.pdf`.
- SHA-256: `1598465ac494fb404a5148abf6a791ebb08a5e6b6134d3818d2569d791c03242`.
- Page 1 explicitly states suspension from the opening of 2018-09-10 and resumption from the opening of 2018-10-29.
- Page 2 dates the board announcement 2018-10-29.
- PDFium and pypdf both expose the same dates and issuer text. These are two decoders of one source, not independent sources.

## Reconciliation

The archived peer-date audit at `runtime/historical-prices/20260908T061418761988Z/peer-date-audit.json` contains 29 peer trading dates from 2018-09-10 through 2018-10-26 with no Midea bars. All fall inside the disclosed suspension interval [2018-09-10, 2018-10-29).

This original disclosure explains that gap as a suspension. It does not establish a complete exchange calendar: the peer-date union cannot detect dates missing from all three series. Other Midea gaps (2015, 2016 and 2019) still require original disclosures.

## Backtest Treatment

- Reject executions during the suspension interval. Never fill missing bars with executable carried-forward prices.
- A resumption date does not guarantee an order can fill; price limits and actual liquidity remain separate checks.
- This is retrospective evidence of execution availability. Do not feed the October announcement's merger details into a September strategy decision or assume the resumption date was known in September.
- No intraday publication timestamp is established. A date-only signal input must follow the conservative availability policy separately from the execution calendar.
- This note has not changed the engine input ledger, production database, or canonical Excel. Integration requires a provenance-linked suspension ledger plus the remaining calendar checks.

## Remaining Work

Resolve the other sample-company gaps using original disclosures; assemble a dated execution ledger; reconcile its calendar with the historical bars; then run the frozen strategy against compatible point-in-time financial and valuation inputs. No performance result is established by this evidence.
