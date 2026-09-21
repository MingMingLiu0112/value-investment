# Explicit tracking lock contention

2026-09-09: local run_candidate_tracking.sh and run_market_screen.sh now
emit SKIPPED_LOCK_BUSY to stderr and exit 75 if the shared lock is occupied,
instead of exiting zero without collecting data. No force unlock or parallel
worker was introduced. Existing schedules remain unchanged.

Five local script-contract tests passed. The staged scripts were also tested
on server Bash with real flock and isolated temporary lock files via
scripts/test_tracking_lock_runtime.py: both returned 75 while locked and zero
after release. Only the pre-collection prefix ran; no real project lock,
container, database, or network collection was used in this fixture.

Files are staged in deploy-staging/backup-space-20260909, not installed in
deploy/server. Production still has the old zero-exit behavior. Before rollout,
review bounded retry/reporting so contention becomes actionable without
starting overlapping jobs or treating a skipped run as fresh market evidence.

## Bounded waiting installed

Follow-up on 2026-09-09 replaced the immediate attempt with flock -w 30 9.
This waits up to 30 seconds for short contention; prolonged contention emits
the skipped marker and exits 75. It is not an automatic rescheduled retry.
The real temporary-lock fixture exercised the full 30-second timeout for
each script and then successful acquisition after release; no collection ran.
Full local suite: 1054 passed, 18 existing Backtrader warnings.

scripts/install_tracking_lock_release.py confirmed that the ONLY difference
from live scripts was replacement of the old zero-exit lock block. It backed
up both originals, checked Bash syntax, installed under the shared lock and
verified exact content. Production installation succeeded without restarting
services or changing timers. Original files and receipt are in
deploy-staging/backup-space-20260909/lock-originals and lock-receipt.json.

Installed hashes:
- run_candidate_tracking.sh: c8edb6bc57cd6a04dc309a6f8ca12f1dd2d3ceddd70946dab03e946edf8c0330.
- run_market_screen.sh: a0af0b31cf3783b6d5447705e1c5a38812803e23a09957ec8f644be9c8a837c7.

The earlier staging-only description is historical. Remaining limitation:
after the bounded wait expires, systemd reports failure but no new dedicated
retry timer or Excel skip-status publication was added. Do not claim that
this change alone guarantees eventual execution or fresh workbook data.
