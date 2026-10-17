# TL11-P10 real assisted-use acceptance, 2026-10-16

## Verdict

`action=no_order`. This is an incremental engineering delivery, **not** initial
formal investment eligibility or user sign-off. Published public packet remains
`pub-6167d094c68f6d8105c1`, with research cutoff 2026-10-11 and market
observation dated 2026-10-15. Neither the 2026-10-16 daytime development work
nor a browser refresh creates a new completed-market-session observation.

## Delivered and checked

- B1 acquisition timing now has one shared verdict for collection diagnostics
  and strict typed quote conversion. It records the final source availability
  time and rejects mixed dates, next-day collection and pre-close acquisition.
  `run_daily_workbench.ps1 -Mode SAFE_REFRESH` still owns the user path. No
  scheduler was created; no old source dates or frozen bundle bytes were altered.
- Hotspot activity ranking and price-structure quality are separate. Existing
  threshold values remain unchanged. Historical v1 ranking replay remains
  compatible; new plans carry a v1 quality tier. Web consumption cannot promote
  a backend `ACTIVE_ONLY` result to a qualified structure. Real 601318, 300059
  and 600030 are retained negative observations, not buys.
- TEST_ONLY private continuity now covers account isolation, confirmed cash and
  IPS, T+1, partial sale, restart, a holding outside Top5, and one security
  across two sleeves. These tests do not inspect or populate the actual account.
- P8 read-only original/replay check reverified 600887's 64 financial rows,
  31 calculations and two later announcements, plus six direct 600519 rows.
  This validates sources and arithmetic, **not** the economic assumptions.
- P10 acceptance CLI is default read-only, restricts its receipt to `.tmp/p10`,
  and reports source/market/research/human/private statuses separately.

## Current research and observation

- **600887 Yili:** Business franchise and historic earnings are observable, but
  the TTM nonrecurring-adjusted profit is not normalized profit. The 9.80 /
  10.08 / 10.30 values are old conditional residual-income calculations,
  dominated by an unapproved rapid full-capital ROE decline. Cash perimeter,
  2026 year-end short-term financing repayment, sustainable distribution,
  incremental ROIC, advantage duration and issuer-specific equity cost remain
  decisive gaps. Conclusion: `CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED`;
  no authorized entry/add/reduce/exit price.
- **600519 Moutai:** Historic operating profitability is evidenced, but group
  cash flow includes finance-company effects. Normalized earnings, cash
  distributability, advantage duration and capital cost are not approved.
  Conditional scenarios are not formal fair value or buy prices.
- **601318 China Ping An:** A local 60-minute trigger was observed at 51.600,
  with structural invalidation reference 50.850, on the retained 2026-10-15
  observation. Daily downtrend conflicts with entry; no formal buy.
- **300059 East Money:** Retained observation 18.320 is below 18.480 entry
  watch level; 17.680 is an invalidation reference. Upper-space/structure
  evidence is insufficient; no formal buy. These are historical observation
  levels, not current executable quotes.
- **Actual holdings:** `NOT_CONNECTED`/locked from independent browser check;
  it is unknown, not a zero position. No current personal concentration,
  capacity, realized trades or sellable shares can be asserted.

## Evidence and limits

P9 source/publication preflight: 38 checks passed. Focused quote tests: 30
passed. P8 original check: `VERIFIED_EXISTING_ORIGINALS_AND_ARITHMETIC_NOT_APPROVED`.
Signed-review/policy tests: 69 passed. P10 acceptance `-RunTests` passed 234
focused tests and a Web build; the full Web suite passed 198 tests. The first
full local Core run had 5677 pass, 44 skip and one date-sensitive TEST_ONLY
HTTP fixture failure. That test now freezes its clock. The complete local
rerun passed 5678 tests with 44 skipped. Exact-commit GitHub Web Workbench and
Core Research Gates (including disposable PostgreSQL) passed for
`d68fb3d497d7e1b53f0455a1547b25e79b30e588`. The P10 receipt at
`.tmp/p10/acceptance.json` reports `ENGINEERING_PASS` for tests and
`BLOCKED_EXTERNAL` overall, with no failures and `action=no_order`.
Chrome checked seven routes at four viewports (1280x900,
1440x900, 390x844, 430x844), the public packet API, and a daily-to-600887
click: 30 checks, no HTTP failure or document overflow. Private routes were
locked, so browser evidence does not prove real-account usability. Local
browser receipt: `.tmp/p10/browser-check.json` (ignored runtime evidence).

The 2026-10-15 value quotes were fetched 2026-10-16 at about 02:32 China
time. They are source-bound display closes, **not** B1 same-session post-close
acquisitions. No natural-time B1 success, authorized G3/materiality signature,
real IPS/account reconciliation, strategy edge, actual trade or final user
acceptance is claimed. Historical replay is not an OOS/shadow profitability
result.

## User actions when ready

1. After a real trading-day close, run the existing SAFE_REFRESH entry and
   check `/system` for the actual quote date, two source acquisition times and
   B1 status. Do not backdate a next-morning download.
2. In the local `/portfolio` flow, enter and personally confirm real cash,
   holdings, cost basis and IPS. Do not send account secrets into public Git.
3. An authorized reviewer must separately sign the exact event-materiality
   and G3 research versions. Only then can price policy and personal risk be
   reconsidered. Every actual fill remains a manual user action.
