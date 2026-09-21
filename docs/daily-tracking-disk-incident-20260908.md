# Daily tracking disk incident

Observed 2026-09-08, approximately 16:57 Asia/Shanghai.

The authoritative systemd state for `value-investment-agent-market-screen.service`
was failed, exit status 1, since 16:31:06 CST. Its daily-tracking drop-in invokes
`/opt/value-investment-agent/deploy/server/run_candidate_tracking.sh`.
The traceback at 16:30:50 identifies `tracking_collection.archive_snapshot`:
`OSError: Low disk: preserve database reserve`.

Read-only `df -h` showed the root filesystem at 96%, 1.9G available of 40G.
Project-only `du` showed 6.2G total: evidence 6.0G, exports 53M, backups 117M,
runtime 4.8M. Evidence is not disposable cache.

The downloaded export generated at 2026-09-08T08:31:02.514865+00:00 contains an
empty `candidate_tracking` list. The workbook correctly blocks stale/missing
tracking rather than treating screening prices as daily observations. Workbook
publication succeeded at 16:55:57 CST; publication is not collection success.

Recovery requirements:

- Preserve disk reserve and the PTA project; do not weaken the collection guard.
- Inspect current unused project image/cache references before any removal.
  Historical image IDs in cleanup scripts are not sufficient proof of current safety.
- Do not delete evidence, database files, or backups to make the task pass.
  Any evidence relocation needs hashes, verified copies, and working lookup paths.
- After reclaiming adequate headroom, verify no tracking job is active before
  starting one bounded retry. Verify its committed observations and evidence chain,
  then republish the original workbook.

No server files, service configurations, thresholds or processes were changed in
this diagnostic pass. Recovery and a successful fresh daily run remain outstanding.
