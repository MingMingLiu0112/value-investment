# TL11-P6 first usable workbench

## User entry

```powershell
& 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File 'D:\GPTProject\value-investment\scripts\current\run_daily_workbench.ps1' -Mode SAFE_REFRESH -Open
```

The verified local backend serves the built Web at http://127.0.0.1:8001/daily.
An occupied port is retained; the launcher verifies its own process identity or
selects another loopback port. It opens the browser only after readiness. Public
research works without private authorization. The per-start unlock link is local
and must not be shared. For an expired private session, the same entry supports
`-Reauthorize -Open`; only a verified launcher-owned process may be restarted.

Page refresh rereads published data. SAFE_REFRESH checks the latest completed
exchange session, reuses complete verified observations on repeated same-day
runs, and otherwise attempts collection. A failed update retains the old
publication with an explicit failure status. No arbitrary command HTTP endpoint
was added. The run observed at 22:56:55 Beijing time on 2026-10-14 completed using
already verified same-day inputs; it is not evidence of a new network acquisition.

## Actual product path

Windows browser acceptance exercised daily decisions, actual stock details,
daily/60m charts, private setup, IPS draft and explicit confirmation, manually
entered fills, recalculated ledger facts, and history. Desktop 1280x900 and
1440x900 and mobile 390x844 and 430x844 were checked. Screenshots and actual
public API results are in `artifacts/current/tl11-p6-20261014/`.

The homepage prioritizes dates, formal count, pending conditions, holdings and
tasks. Unvalued companies are folded. Failed public reads stop current candidate
display; failed or unverified strategy reads cannot imply no exit matters.
Frozen quote freshness is labeled as publication-time verification. Detail pages
lead with six operating questions and fold research, provenance and replay.

On the verified 2026-10-14 publication, formal eligibility remains zero. 中文在线
300364 has reference 26.58, 60m entry observation 27.88 and invalidation 24.70.
Its daily trend is descending. Entry needs a completed close above the prior
five-bar high with volume at least 1.2 times their mean. A single-cycle trigger
does not establish multi-cycle or formal admission. 伊利股份 600887 shows reference
28.13 and research scenarios 9.80/10.08/10.30, with unapproved price comparison
and no selected action-price policy. Scenarios are not operational buy prices.

## Isolated account proof

All account writes were to TEST_ONLY journals under `.tmp/`, never the real
private store. An empty account dated 2026-10-12 was initialized with cash 10000,
then a synthetic IPS was drafted and confirmed via the Web. The browser recorded
BUY 100 at 20 with fee 5 on 10/13 and SELL 100 at 22 with fee 5 on 10/14. Final
cash is 10190, realized PnL 190, holdings zero, and two retained confirmed trades.
Both survive an isolated service restart and new authorization. History expands
the original recording-time plan: 27.88/24.70, publication identity and false
formal eligibility. It explicitly does not prove pre-trade contemporaneous
knowledge. Synthetic PnL is not user performance or strategy validation.

Another synthetic account demonstrated retained costs and verified marked value,
plus a five-yuan hotspot-pool overdraft warning. Backdated trades before account
state and future-trade confirmations were rejected. Unknown legacy risk appetite
now returns a missing-input result, not HTTP 500 or an invented default.

The authenticated, non-writing sizing preview binds the server's current plan
and reuses the existing loss-based engine. User assumptions are explicit, with
no default quantity. The actual current 300364 preview returns null because
liquidity, price-limit execution state and reconciliation are unverified. Reads
and sizing do not mutate the journal. Missing models do not imply sell.

## Completion boundary

This release concerns engineering first use, not the total long-term Goal or
investment authorization. Final user acceptance is not signed. G3/model approval,
material event review, explicit price policy, real IPS/holdings, verified economic
attributes and sufficient prospective strategy evidence remain independent.
No WPS workbook, production database, scheduler, broker order or Draft PR merge
is included. Permanent `action=no_order` remains enforced.

Local validation and final-head CI are recorded with the release evidence.
No remaining engineering P0/P1 may be hidden behind these external gates.

## Validation

Local Core regression: 2567 passed, 33 skipped. Web: 141 tests across 27
files passed; TypeScript checks and production build passed. Additional Windows
startup, failure-retention and retained-publication checks: 14 passed, 2 skipped.
Final-head Core, PostgreSQL and Web CI must pass before engineering release is
reported ready. The existing PR remains Draft and final user acceptance remains
pending. No unresolved P0/P1 was identified in the exercised product path.
