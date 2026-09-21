# Tracking service audit, 2026-09-08

## Authoritative observations

The systemd unit `value-investment-agent-market-screen.service` retains its
initial-screen description, but the active drop-in
`/etc/systemd/system/value-investment-agent-market-screen.service.d/20-daily-tracking.conf`
clears ExecStart and invokes `run_candidate_tracking.sh`.

The September 8 19:39 run reported tracking run
`ac35b4ef-dff9-4211-8d56-2f8fde0b3ded`, candidate_count 738,
blocked_count 0, status succeeded. Valuations and export followed successfully.
This is daily tracking, not evidence of a new all-market screen. The latest
membership date in market_screen_results remains September 7 (738 rows).
Tracking quote gates do not approve financial evidence or strategy performance.

Earlier runs failed: 16:30 reported `Low disk: preserve database reserve`;
17:04 exited 137. Exit 137 alone does not establish an OOM diagnosis.

## Capacity and pending work

At approximately 22:47 CST the root filesystem had 2026 MiB available, below
the 2048 MiB reserve. Available RAM was 1759 MiB. Read-only disk inventory:
evidence 6377 MiB, exports 55 MiB, project backups 117 MiB, container storage
2135 MiB, system journals 168 MiB. No evidence, backup or other application
was removed, and no service was restarted during this audit.

Institution parser v13 is deployed with SHA-256
`1575b15a51fe45dfd90cca029e72a970325c78efd47e34575722e8667cddd2b6`.
A fresh database query found no 002939 data points with this parser version.
Deployment is not proof of successful extraction or independent verification.

The full-screen timer was separately inspected: the industry-refresh timer's
`20-monthly-screen.conf` clears its weekly calendar and sets
`Sat *-*-01..07 10:30:00 Asia/Shanghai` (first Saturday each month).
Its service runs `run_market_screen.sh weekly`, which includes industry mapping.
The next observed trigger was October 3, 2026, 10:30 CST. Daily tracking is
scheduled at 16:30 CST. Unit descriptions remain stale; effective drop-ins,
not names or descriptions, establish the actual schedule.

Before further bulk collection, resolve disk headroom without deleting unique
evidence. Do not infer strategy readiness from successful task status.
