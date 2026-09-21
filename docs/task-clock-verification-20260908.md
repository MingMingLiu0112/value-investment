# Task clock verification

Observed production task start/end timestamps were equal because PostgreSQL
now() returns transaction time. Local begin_run/end_run now use
clock_timestamp(). Failure recording first rolls back and checks whether the
original row survived; reconstructed starts are explicitly marked in details,
while ON CONFLICT preserves committed started_at. Reconstructed starts must
not be used to infer runtime or RTO. Historical records are not rewritten.

Full local regression before integration: 818 passed, 18 existing warnings.
scripts/test_task_clock_postgres.py loads the exact three functions from the
staged local db.py via AST and executes them against a PostgreSQL TEMP table
named task_runs. The table is committed before test transactions, allowing
rollback behavior without touching the public business table.

Server test under 0.5 CPU / 256 MiB passed all three cases:
normal elapsed 0.054519 seconds after pg_sleep(0.05); rolled-back start tagged
start_time_reconstructed=true; committed start preserved and tag false.
The process exited successfully; connection closure removed the temporary
table. Production code has not been replaced by this test.

## Deployment

First attempt correctly refused while the filings service was processing.
After systemd reported Result=success, ActiveState=inactive, SubState=dead,
hash-pinned deployment succeeded. Backup:
`/opt/value-investment-agent/deploy-backups/task-clock-_3gfcv_8`.
Current db.py SHA:
14183f93cff8849fc4337cfc3acb03047d4f5b4d87c20d5a72fd17d55b8b1f97.
No historical timestamps were rewritten and no other service was stopped.

The deployment helper now checks whole filing-service state as well as
containers; six targeted tests passed. This detects observed between-container
gaps, but state checks alone are not an atomic lifecycle interlock against a
new service start. Full mutual exclusion requires the service to share the
deployment lock for its entire lifecycle. That additional change is not made
by this deployment.
