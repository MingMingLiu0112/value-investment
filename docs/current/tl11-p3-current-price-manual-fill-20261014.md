# TL11-P3 actual daily observations and manual fills

Permanent `action=no_order`. Engineering delivery, research admission and final
user operational acceptance are independent. No actual user trade or portfolio
write was performed. The canonical Excel was not edited.

## Current bounded observation

Completed session: **2026-10-14**, Asia/Shanghai. Next session observation:
2026-10-15, resolved from the bound official calendar. These are closing
observations, not retrospectively executable intraday entries.

| Symbol | Company | Close | Breakout reference | Invalidation reference | State |
|---|---|---:|---:|---:|---|
| 300308 | 中际旭创 | 692.90 | 746.00 | 697.20 | TRIGGER_REJECTED |
| 300750 | 宁德时代 | 280.12 | 294.98 | 280.23 | TRIGGER_REJECTED |
| 300502 | 新易盛 | 330.80 | 359.00 | 332.73 | TRIGGER_REJECTED |
| 688825 | 长鑫科技 | 46.00 | 48.55 | 46.33 | TRIGGER_REJECTED |
| 002384 | 东山精密 | 131.41 | 142.30 | 132.80 | TRIGGER_REJECTED |

The existing industry watch queue remains UNKNOWN because its session date is
unverified. This bounded sample comes from the published, dated securities
observations instead; it does not claim industry or catalyst admission.
Watch source: `runtime/daily-trade-assistant/fm3-v3-publish-20261012-v2/hotspot-observation/report.json`,
SHA-256 `66f3f90d71ae341d9f00c492effed308a3e14293548dc53fccc9d596c43f7c4a`.

The unchanged primary 60m rule is `hotspot-prior-five-completed-bars-v1`:
close strictly above the previous five completed highs AND volume at least
1.2 times their mean. The previous five lows determine structural invalidation.
All five latest closes are below that invalidation reference. No thresholds were
tuned, no BUY was generated, and formal admission count is zero. Complete
15m/60m session grids and derived daily OHLCV are retained; Tencent/Sina closes
are checked through B1. Intraday bars remain a single-provider observation.

## Value research and private facts

600887 retains its 2026-10-11 conditional research scenarios: Bear 9.79764,
Base 10.07514, Bull 10.30069 CNY/share. These are model scenarios, not admitted
buy prices. Current quotes do not approve model/event validity or G3. Formal
entry/add/reduce/exit thresholds remain null when absent from the bound rules.
The detail retains financial facts, assumptions, support and counterevidence.

The existing FillPanel carries only symbol, strategy, decision_id and research
version. Actual price, shares, date and fees require user entry and confirmation.
No second ledger exists. Isolated synthetic transactions against the real
600887 judgment proved cash 5000 -> 2995 -> 4490, final quantity 200, remaining
cost 3005 and realized PnL 495. Drafts do not change facts, replay retains the
original version, repeat confirmation is idempotent, shared cash cannot be spent
twice, and T+1/sleeve checks apply. Missing real IPS keeps position guidance null.

Final real-judgment isolated receipt:
`.tmp/tl11-p3-ledger/acceptance-20261014T090936Z-8188fcd8/public-safe-acceptance-receipt.json`,
SHA-256 `a743263e97bd3b3c7b2746761d114e460d7d11685123ef5081289a0e34a37328`.

## Reproduce and verify

Run in PowerShell 7 after market close:

```powershell
pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode SAFE_REFRESH -Open
```

Collection, structure calculation, research freshness, trigger state, formal
eligibility and Web availability are reported independently. Failed sources
retain raw evidence and do not overwrite the previous verified registry.
One pinned snapshot per request prevents mixed versions. Raw tampering and stale
closes block current details/charts; malformed registry data returns BLOCKED.

Final packet: `pub-3f3b6d7dcc99a2716c10`.
Path: `runtime/daily-public-packet/daily-public-packet-pub-3f3b6d7dcc99a2716c10.json`.
SHA-256 `3e56b8b8bdbd7b2a632d3254b7fe6b755922221c2edfc84d39374e7a5a5c5a71`.
Raw current cases and B1 bundles remain project-local under `runtime/` and are
hash-bound by `config/current-price-conditions.json`, not synthetic fixtures.

Windows desktop Web: `http://127.0.0.1:8012/daily` during acceptance, with real
candidate detail `http://127.0.0.1:8012/decisions/hotspot-300308`.
Screenshots: `.tmp/tl11-p3-daily-v5.png`, `.tmp/tl11-p3-hotspot-300308-v5.png`.
The actual chart displays OHLCV, the 746/697.2/692.9 references and the five
input bars, with the next-session boundary and the manual-fill link.

Core local regression: 2369 passed, 33 skipped; Web: 83 passed, typecheck,
format and build passed. Final API/security changes receive targeted regression
and remote Core/Web CI before engineering closure. PR stays Draft; no merge.

Remaining admission limitations: industry date/catalyst qualification,
single-source intraday data, independent value/event/risk checks, PIT/OOS/cost/
Shadow validation and real private IPS. Final operational acceptance is
NOT_PASSED; it requires the user's actual use and sign-off.
