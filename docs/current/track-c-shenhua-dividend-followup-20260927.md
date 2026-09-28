# Track C Shenhua 2025FY A-share dividend follow-up, 2026-09-27

Scope: resolve the bounded evidence gap for the 2025FY A-share distribution
from the 2025 annual report proposal through shareholder approval and the
issuer's implementation notice. This is public-document research only;
`action=no_order`.

## Bounded query and retained bytes

CNINFO exact-issuer query: `601088`, `2026-06-26..2026-08-27`, retrieved
`2026-09-27T08:03:49.358525Z`. The complete one-page response contains 23
records, all for `601088`, with unique announcement IDs and Shanghai-local
announcement dates inside the requested closed interval. This establishes
only this CNINFO issuer/date window; it is not continuous issuer coverage and
does not advance the formal event watermark.

- Parsed index: `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/index.json`, SHA-256 `fd953fc2c1a34df4249ea373efb1a2287a103833caccb6c38f89e118afbea44c`.
- Raw HTTP response: `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/601088-page-1.raw.json`, SHA-256 `113d955b03d6de946805d13a122b46bbd75be2429cb5d6646a4e634bbc64c80f`.
- Two-document download receipt: `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/document-download-receipt.json`, SHA-256 `53ebd41d0c54598eb48c667e8fb6a484840da67a2aace6b62f2848b7b4c78921`.

Both downloads returned HTTP 200 and `application/pdf`. Retrieval timestamps
are process-clock-only and are not independently attested.

## Source findings

1. Shareholder-resolution announcement `cninfo:1225393356`, dated by CNINFO
   `2026-06-27`, [official PDF](https://static.cninfo.com.cn/finalpage/2026-06-27/1225393356.PDF),
   is retained at
   `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/1225393356.pdf`.
   SHA-256: `d1a074bcfc80f14445f901162a850953b2c1e8c366f2adaa8842654cde47c560`.
   Physical page 3 records that agenda item 3, the 2025FY profit-distribution
   proposal, passed; the A-share vote is 99.993551% in favor. This proves the
   resolution notice reports approval, not later account-level receipt.
2. Implementation announcement `cninfo:1225410284`, dated by CNINFO
   `2026-07-06`, [official PDF](https://static.cninfo.com.cn/finalpage/2026-07-06/1225410284.PDF),
   is retained at
   `runtime/prospective-public-event-20260927/gapfill-601088-20260927T080349157627Z/1225410284.pdf`.
   SHA-256: `af14443530d39cd7ad4a46a0acbf51fa5550b1a9e884cb97544b24419d118507`.
   Physical page 1 states A-share cash dividend CNY 1.03 per share gross,
   using total share capital of 21,689,434,304 shares, with total gross
   distribution CNY 22,340,117,333.12. The A-share record date is 2026-07-10;
   ex-dividend and stated payment dates are 2026-07-13. It says distribution
   is made through China Securities Depository and Clearing Shanghai Branch,
   except issuer self-distribution recipients.

The project evidence builder independently bound each document to the exact
issuer query, archived raw response page, announcement ID, official URL and
PDF bytes:

- Resolution scan evidence `scan-evidence-1225393356-v3.json`, SHA-256 `3e955e48b5343b729f12ead3ccd624912c33675e3fd3fad04124bd6f272b79d2`.
- Implementation scan evidence `scan-evidence-1225410284-v3.json`, SHA-256 `72cbbf8a090ca274a5aa037c95dbc1eb425858cd90278f31671f27de432c88b4`.

The v3 builder call separately supplied the expected query window
`2026-06-26..2026-08-27`; it rejects an index that changes both its declared
window and query parameters away from that expected scope. It also requires
the scanner's full unfiltered exact-issuer query contract, rather than trusting
the index's `COMPLETE` label or accepting a narrowed category/search filter.
These caller inputs and local receipts are not signature/TSA attestations.
The expected dates and CNINFO organization ID are not independently signed
registration inputs; the chain proves local query-contract consistency and
source-byte binding, not cryptographic proof of the request parameters received
by CNINFO.

The two notices are distinct issuer filings but share CNINFO as their source
channel; they are not represented as independent-provider corroboration.

## Disposition and limits

The narrow open gap is closed: the 2025FY A-share proposal is reported as
approved, and its implementation notice specifies amount, record date,
ex-date and stated payment date. Relative to the earlier annual-report
proposal, this is `MATERIAL_SUPPORTING_EVIDENCE` for historical capital
allocation and ordinary-dividend tracking.

This does not establish that a specific account received funds, the net amount
after shareholder-specific tax, future dividend sustainability, cash coverage,
normalized-cycle distribution capacity or valuation impact. H-share payment
arrangements are outside this A-share follow-up. The query examined 23 rows,
but this memo does not claim document-level review of every other row.

Both source dates precede the registered observation start
`2026-09-27T08:45:00+08:00`; their conservative next-day availability dates
are 2026-06-28 and 2026-07-07. Retrieval/review after observation start is a
re-observation of pre-existing public material, not a new post-registration
disclosure and not strict contemporaneous PIT evidence. No observation-ledger
entry was created by this memo.

No formal watermark is advanced: `601088` remains `INCOMPLETE` because
continuous prior coverage is not established. No baseline fact, dividend
sustainability assessment, valuation, quote, canonical workbook or production
state changed. `action=no_order`.
