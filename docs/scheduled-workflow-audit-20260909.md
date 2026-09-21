# Scheduled workflow live audit

Read-only server inspection: 2026-09-09 around 06:22 Asia/Shanghai.
This supersedes assumptions that enabled timers alone prove the workflow works.

## Confirmed execution

- value-investment-agent-market-screen.timer is enabled, next 16:30 today.
  Its service override executes run_candidate_tracking.sh, not the original
  all-market screening script. Last execution succeeded 2026-09-08 19:39:01
  to 19:40:09; tracking run ac35b4ef-dff9-4211-8d56-2f8fde0b3ded reported
  738 candidates, blocked_count=0, then valuation refresh succeeded for 738.
  This tracking blocked_count does not mean all financial/decision gates pass.
- The scheduled 16:30 execution on September 8 failed the disk reserve check.
  The 17:03 retry exited 137; this exit code alone does not prove kernel OOM.
  Later 19:39 success does not establish that the next scheduled run will pass.
- value-investment-agent-update.timer remains enabled, next 16:10 today.
  Its September 8 execution failed after 10 seconds with Sina TLS unexpected
  EOF while fetching sh600941. The live CLI used the initial UNIVERSE list.
- The old run_update.sh uses set -e and runs init-db, legacy update, quality,
  then backup. Failure in the update skipped the later daily backup stage.
  This does not prove that no other/manual backup exists.
- Filings service was genuinely running (MainPID 370898), not inferred from
  an old lock file. No restart or duplicate worker was launched.
- Monthly snapshot, monthly restore drill, and weekly industry refresh timers
  are enabled. Their existence is not evidence that restore validation passed.

## Gaps changing the next action

1. Separate daily backup execution from success of market-data collection.
   Preserve failure reporting for both; do not hide the legacy update failure.
   Inspect the actual backup implementation and available storage before
   initiating a potentially large backup on this nearly full server.
2. Inspect the industry-refresh service and its timer overrides before adding
   a full-screen schedule. Follow-up below confirmed an existing monthly
   full-universe screen under that service; no duplicate timer is needed.
3. Retire or repurpose the redundant initial-company update only after its
   remaining backup/quality responsibilities have explicit replacements.
4. Check failure and lock-contention reporting: current tracking script exits
   zero when flock cannot acquire the shared lock. A service success can mean
   skipped work; record an explicit skipped status rather than treating it as
   successful fresh collection.

## Resource facts

Root available 1960 MiB, 95% used. Project total approximately 7183 MiB:
evidence 6949, backups 117, exports 56, staging 56. No deletion, volume
expansion, reserve reduction or new PDF download was performed.

Live candidate-collection cap is 512 MiB memory / 768 MiB memory-plus-swap,
with 0.5 CPU; valuation is 256/384 MiB and export 384/512 MiB. These actual
production limits differ from the 384/512 MiB used for our manual parser
operations. No caps were changed in this audit. Legacy update has no explicit
CPU cap in its podman command and still initializes schema on every run.

This turn changed no service, database, trading rule or Excel output. It
established concrete operational defects requiring repair before claiming
unattended end-to-end operation.

## Follow-up correction: monthly screening already exists

At approximately 06:34 on 2026-09-09, systemctl cat revealed that
value-investment-agent-industry-refresh.service executes
run_market_screen.sh weekly. Despite the argument name, the effective timer
override 20-monthly-screen.conf clears the weekly calendar and sets
OnCalendar=Sat *-*-01..07 10:30:00 Asia/Shanghai. This is the first Saturday
of each month, not a weekly industry-only refresh. The script refreshes the
official security list, runs screen-market with industry mapping enabled,
refreshes valuations and exports the result.

The last execution was September 5, 10:30:21 to 10:31:16, exit status 0;
the next timer occurrence is October 3. Available journal history starts
September 6, so September 5 detailed collection evidence was not available
from journalctl. Service success alone cannot establish that collection was
complete or even that the shared lock was acquired, since contention exits 0.

The earlier suggestion of a missing periodic screening timer was premature:
the necessary full-screen schedule already exists under a misleading service
description. No new timer was created and no cadence was changed. Searches
of /etc/cron.d and /var/spool/cron returned no matching project entries; this
is not an exhaustive inventory of external scheduling platforms.
