# Daily tracking service verification: 2026-09-08

This is an operational verification, not investment-strategy approval.

## Authoritative service run

- Started the existing `value-investment-agent-market-screen.service` through systemd.
- The installed drop-in routes it to `run_candidate_tracking.sh`, not the old daily full-screen script.
- Start: 19:39:01 CST. End: 19:40:09 CST. `Result=success`, `ExecMainStatus=0`.
- Existing limits unchanged: 0.5 CPU; collection 512 MiB, valuation 256 MiB, export 384 MiB. Stages execute serially.
- The earlier failed systemd run was not treated as evidence of a currently running job or a successful repair. This new run verifies the actual timer's service entry point after the prior memory fix.

## Export and canonical workbook

- Export timestamp: `2026-09-08T11:40:06.644042+00:00`.
- Payload SHA-256: `ba5119a741f938c96890723f4c08f1ad4816498361a666af0d95341df7d46ce7`.
- 738 candidates, 738 daily tracking rows, all quote status `matched`, zero quote-tracking blocked rows. This does not mean financial, valuation or strategy gates passed.
- Workbook generator reports 2858 verified points, 3981 annual numeric cells, 181/328 specialized financial values across 62 companies. Filled cells are not proof of all required evidence being approved.
- Initial screening official reconciliation remains dated 2026-09-07: 5558 matched securities, no missing codes or board conflicts. No claim of a fresh September 8 all-market screen.
- `run_server_excel_sync.ps1` completed canonical publication at 19:42:40 CST with checksum verification, dated original backup, preservation validation, lock/change guard and atomic replacement.
- Main data tabs contain 738 companies; company research retains 744 rows including preserved research records.
- Reopened the canonical workbook after publication. `12_提醒`: 741 rows, 14 columns. `21_决策验证`: 741 rows, 25 columns, including strategy status and backtest run ID.
- Manual holdings, trades, review records and historical audit/monthly rows passed preservation checks.

## Resource checks and outstanding risk

After completion: 1840 MiB available memory, 2.3 GiB free disk, root filesystem 94% used. PostgreSQL container remains running. PTA PID 236577 and Hermes PID 1220 were present. No other application was restarted or stopped, no memory limit was raised, and no evidence was deleted.

The 2 GiB disk reserve remains enforced. Capacity must be addressed before substantial additional archival work; this successful small run does not resolve disk risk. Financial completeness, historical point-in-time inputs, validated trading rules and full portfolio guidance remain incomplete.
