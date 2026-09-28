# Prospective CNINFO Watermark Continuity Corrigendum - 2026-09-28

This note reconciles the earlier bounded-gap-fill memo with the retained
query indexes and the later 2026-09-28 snapshots. It does not backdate a
registration time, attest the local process clock, or claim coverage outside
the stated CNINFO exact-issuer scope. `action=no_order`.

## Current observation

The scanner was run once for each registered issuer for the forward date
window 2026-09-28, after the prior 2026-09-28 morning snapshots. All three
responses were HTTP 200, had one complete page with terminal `hasMore=false`,
and their page hashes match the retained index. The retrieval timestamps below
come from the local process clock and are **not independently timestamp
attested**.

| Symbol | Local `retrieved_at` | Results | Index SHA-256 | Scan receipt SHA-256 | Finding |
|---|---|---:|---|---|---|
| 000333 | 2026-09-28 10:00:41 +08:00 | 1 | `7fddbe9ea30ddfa2d7113debad410ae8d4f2618fc105d18f011431a29f874890` | `6e305597c2604c32a980b72178584ac13b3d3acabd33eccbed68172b71ba484f` | Existing notice `1225582141`; no new document |
| 600887 | 2026-09-28 10:01:33 +08:00 | 0 | `39db16b37b92e136b425c7aa49ced860385e19013533fc6fea384ea77dc08e7b` | `1964967233fd4f8c3dbf5168902874f0b35539049e9d2caaa1d009548412d0d7` | No result in this bounded query |
| 601088 | 2026-09-28 10:02:00 +08:00 | 0 | `32a4a0f6f6e5da59443ca729f21e6eba5e8fd027fa3729ac7617733dca0225dc` | `53de05fdbe327ed9d98334f42817517be3074dc286c70b1a35f54ef3b9f05d53` | No result in this bounded query |

Raw page hashes are respectively `ad8cb13b94623e0cffa83621c91d1c98a4af7723335f0699ac64aa8c0ab068eb`, `c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114`, and `c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114`. The exact retained paths are listed in `docs/execution-status.md` under the 2026-09-28 continuation entry.

The Midea notice was already reviewed in
`track-c-midea-egm-notice-20260928.md`. This later retrieval does not create a
new event, new company fact, or changed ResearchCase. The Yili and Shenhua
zero-result responses are snapshots, not proof that no later announcement was
published that day.

## Coverage by issuer

The coverage ranges below describe complete retained date-filtered query
windows only. They are distinct from exact intraday observation times and from
the registered prospective cutoff. The v2 plan declares an observation start
of 2026-09-27 08:45 +08:00, but its registration receipt is process-clock-only;
that declaration is not an independently proven time anchor.

| Symbol | Verified `coverage_from` -> `coverage_through` | Source / health | Missing interval and limits |
|---|---|---|---|
| 000333 | 2026-03-31 -> 2026-09-27, with adjacent complete windows 03-31..08-28 and 08-29..09-27; 09-28 snapshot through local 10:00:41 | CNINFO exact issuer `9900005965`; all indexed raw-page hashes match; complete pagination | No date gap inside the bounded 03-31..09-27 queries. Earlier than 03-31 is not evidenced. After the 09-28 snapshot is unobserved; issuer IR, exchange-site channels, corrections, and independently attested retrieval time are outside coverage. v8 verifies the bounded date windows, but the formal registration watermark remains `INCOMPLETE` because its initial boundary is not tied to an exact query receipt. Neither entry proves strict PIT. |
| 600887 | 2026-09-23 -> 2026-09-27; 09-28 snapshot through local 10:01:33 | CNINFO exact issuer `gssh0600887`; 09-23..27 index has one page and complete pagination; current zero-result query uses a hash-bound identity index | No date gap in the stated bounded interval, which includes 09-27. After the 09-28 snapshot is unobserved; earlier than 09-23 and other channels/corrections are not evidenced. v8 preserves `COMPLETE` only for its 09-23..27 CNINFO window, not the open 09-28 day or strict PIT. |
| 601088 | 2026-03-31 -> 2026-09-27 via seven adjacent/overlapping complete query windows; 09-28 snapshot through local 10:02:00 | CNINFO exact issuer `9900003701`; all indexed raw-page hashes match; complete pagination | No date gap inside the bounded 03-31..09-27 chain. Earlier than 03-31 is not evidenced. After the 09-28 snapshot is unobserved; issuer IR, exchange-site channels, corrections, and independently attested retrieval time are outside coverage. v8 preserves `COMPLETE` only for this CNINFO date-window chain. |

For 601088, the retained chain includes 2026-03-31, 04-01..06-25,
06-26..08-27, 08-25..08-31 (overlap), 09-01..09-22, 09-23..09-26, and
09-27. The relevant index hashes are `99cb7f5143c4b37b44c7c954ea37701d8ea325b73d753ea65d7f44c9455d92e8`,
`bee306d21c9426bd670695a93e827dc0a9c412829fefd45ce28bd061e545f8f4`,
`fd953fc2c1a34df4249ea373efb1a2287a103833caccb6c38f89e118afbea44c`,
`726a5b26757a6726cc699615738b39463a21af7b08d7728d11e677cb1e00e517`,
`ef375fec015315f79f863d21dec8dbd683fe0d2bee6455f14aac61cb394c120b`,
`0717da2e13c2c17f95015a3c28795cd447cd0a3bf920cb917ca9b1f950175e2a`, and
`e2c3b27cc18386024e27e349790df0478852271cca720647308a43dd22ceb9cc`.
Every referenced page hash was rechecked against its retained raw response;
each interval ended with `hasMore=false`. This corrects the older gap-fill
memo's statement that 601088 still had date gaps, but does not extend its
channel scope or prove a trusted observation clock.

## V8 successor

`config/prospective-public-event-watermarks-v8.json` preserves the four v7
watermark objects unchanged and appends a separate 000333 CNINFO date-chain
entry for 2026-03-31 through 2026-09-27. Its two adjacent complete windows
contain 106 unique announcement IDs and retain their index/page hashes. The
query-window chain is verified, but the successor's formal `coverage_status`
remains `INCOMPLETE`: retrospective date windows do not bind the prospective
registration boundary to an exact query receipt.

The v8 manifest also records the three 2026-09-28 snapshots above as separate
`current_bounded_observations`, with result counts 1/0/0. They do not extend
the date-chain endpoint or prove full-day/multi-channel completeness. Their
retrieval times are `PROCESS_CLOCK_ONLY_UNATTESTED`, and each has
`strict_pit_admissible=false`.

## Disposition

- Keep the predecessor records and formal registration states unchanged. The
  v8 000333 record retains verified date-window evidence but remains formally
  `INCOMPLETE`; the 09-28 queries remain `SINGLE_DAY_SNAPSHOT_ONLY` and do not
  extend the date chain or prove full-day completeness.
- Retain `STRICT_PIT=NOT_PROVEN`. The registration receipt and retrieval
  timestamps use the local process clock without independent attestation.
- No new public filing, financial fact, material event, price close, valuation,
  or decision state was found. Do not rebuild the event projection and do not
  republish the canonical workbook for these unchanged results.
- Reopen on a source-attested registration/observation time, a new official
  filing, or the next completed exchange session. Continue exact-issuer scans
  only forward from the last confirmed source boundary; do not repeat a query
  solely to make a watermark look newer.
