# Closure Baseline (W0, 2026-10-17)

`action=no_order`. This is the frozen starting point for
`VALUE-INVESTMENT-REAL-DECISION-CLOSURE`. Machine-readable twin:
`artifacts/current/closure-baseline.json`.

## 1. What code is running

- Repository: `D:\GPTProject\value-investment`
- Branch: `codex/web-d1-investment-workbench`
- HEAD: `4a56ab357322122079400a0fed33fd023fceeff3`
- Origin branch: same commit, ahead 0 / behind 0.
- Worktree: 7 modified + 43 untracked files, all predating this Goal Run.
  They are preserved untouched; no reset, checkout or bulk staging was done.
- Live API: `uvicorn value_investment_agent.presentation.web_api.app:app`
  on `127.0.0.1:8001`, PID 21624, started 2026-10-16 19:32:49 +08:00.
- `/api/v1/runtime-identity`: `MATCHED`; backend module SHA-256 equals the
  on-disk module (`375bb220...`); Web build is commit `4a56ab3`, clean,
  index SHA-256 `9fef6d5f...`.

## 2. What data is published

- Publication: `pub-5f803ec65b6e52fd7de4`, status `VERIFIED`.
- Packet: `runtime/daily-public-packet/daily-public-packet-pub-5f803ec65b6e52fd7de4.json`
  SHA-256 `1ed978a5b2fe8baf9f7db801b46c97ca97fa3b03575ac4115c3eef57aa8a93b4`.
- Engine: `daily-public-packet-engine-v18`.
- Research version: `canonical-reviewed-research-20261012T113935Z-362d7928`
  (research as of 2026-10-11; decision published 2026-10-12).
- Quotes: 2026-10-16 close from two sources, both raw payload hashes verified
  by the independent audit (`08a8cb10...` bundle).
- Formal admissions: **0**. `action=no_order`.

## 3. Read-only boundary check (W0.2)

`scripts/current/audit_p9_readonly.ps1` reads the published pointer, packet,
receipt and snapshot and writes only one receipt under `.tmp/`. It does not
capture quotes, touch the private journal, publish Excel, approve research or
create orders. `scripts/current/accept_p10_assisted_use.ps1` writes only its
receipt under `.tmp/` and does not mutate `runtime/` or `config/`.

Actual run: 38 checks, `PASS_ENGINEERING_PRECHECK`, receipt
`.tmp/p9-readonly-preflight.json`.

## 4. What else is writing today

| Writer | State | Entry | Writes decision-shaped state? |
| --- | --- | --- | --- |
| `ValueInvestmentAgent-DailyUpdate` | Ready, last exit 0 | `scripts/run_moutai_b1_after_close.ps1` | Yes, legacy 600519 B1 artifacts |
| `ValueInvestmentAgent-MoutaiB1ExcelPublish` | Ready, **last exit 1** | `scripts/run_moutai_b1_excel_publish.ps1` | Yes, legacy Excel publication attempt |
| `ValueInvestmentAgent-MoutaiPostclosePolicyStage` | Disabled | `scripts/run_moutai_postclose_p1_refresh.ps1` | No (disabled) |
| `ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh` | Ready, last exit 0 | `scripts/run_moutai_preclose_capital_refresh.ps1` | Legacy capital refresh |
| Aliyun DB pipeline | Running (50 runs/48h) | `refresh-valuations` etc. | Yes, `valuation_results` (888 rows, 0 with weight) |
| Daily public packet | Manual / SAFE_REFRESH | `scripts/current/run_daily_workbench.ps1` | **Yes, current authoritative product chain** |
| Private ledger | Locked | `private_portfolio_service.py` | Only after local unlock; currently empty |
| Signed research review | Not used yet (no pinned reviewer key) | `research_reviews.py` | Only after authenticated signature |

W1 converts this table into an enforceable registry.

## 5. Data assets and recovery exposure

- `runtime/`: 128,326 files, 21.7 GB, **0 files tracked by Git**. It includes
  source originals, publication packets, receipts, research cases, approvals
  and 10+ legacy pytest basetemp directories.
- Canonical Excel:
  `C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx`
  SHA-256 `aeaa3c7fec2b46d34c0651b0384dec49fb3ca16747dc41fcf675bbd022be82f1`.
- PostgreSQL: 14 tables; `valuation_results` 888 rows, 0 with target weight.

W2 defines the backup scope, recovery order and restore drill; the 21.7 GB
runtime must not be copied blindly because most of it is disposable test output.

## 6. Baseline answer

On this computer today, the running code is `4a56ab3`, the published data is
`pub-5f803ec65b6e52fd7de4`, the research version is
`canonical-reviewed-research-20261012T113935Z-362d7928`, quotes are the
2026-10-16 close, formal admissions are 0, and the only authoritative current
product chain is the daily public packet plus the read-only Web workbench.
Legacy Moutai tasks and the server DB pipeline still write archival or
observation state and must be fenced in W1.