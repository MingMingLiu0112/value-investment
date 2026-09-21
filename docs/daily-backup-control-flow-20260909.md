# Daily backup dependency repair

2026-09-09: local run_update.sh now separates data-stage and backup exit status.
Each data command explicitly returns on failure; backup is attempted afterward
even if initialization, quote collection, or quality checking fails. Backup
failure takes exit-code priority, while the journal summary retains both codes.
The repair does not claim a completed backup or restore exercise.

Verification:
- Existing script contract tests: 2 passed locally.
- scripts/test_daily_update_control_flow.py executed on server Bash with an
  in-shell podman stub. Six scenarios passed: success, initialization failure,
  quote failure, quality failure, backup failure, and both quote/backup failure.
- The test executes the real script control flow but never starts a container,
  accesses credentials, creates a database dump, or writes a database.
- Staged files are under deploy-staging/parser-release-v33-20260909; the live
  deploy/server/run_update.sh has NOT been replaced.

Production rollout remains pending: inspect backup disk-size needs and add a
reserve-preserving preflight before enabling new automatic backup attempts on
the nearly full root volume. The current backup implementation inventories
PDFs under target_dir/evidence; this must be reconciled with the actual evidence
mount and complete non-PDF/raw/configuration scope before claiming complete
asset backup. Offsite encryption and verified restore remain separate work.

No timer, service, resource cap, original evidence, or canonical Excel changed.

## Space admission implemented locally

backup.py now queries pg_database_size(current_database()) in its read-only
snapshot transaction and requires free space of at least 2 GiB plus twice the
physical database size plus 64 MiB for metadata. Unknown or invalid sizes fail
closed. The check runs before table hashing and again immediately before dump
execution. Successful manifests record the last preflight measurements.

This is a conservative estimate, not a hard filesystem reservation: database
growth, dump expansion beyond the estimate, and concurrent unrelated writers
can still consume space. It does not claim complete protection against disk
exhaustion or certify offsite backup. No reserve setting was lowered.

Tests cover threshold equality, insufficient space, invalid sizes and disk
space dropping during table hashing; both low-space paths start no dump and
create no manifest. Targeted tests: 15 passed. Full suite: 1052 passed with 18
existing Backtrader deprecation warnings. This addition and the control-flow
repair remain local/staged, not installed in production; deployment must use
a checked production baseline to avoid shipping unrelated local backup edits.

## Production installation completed

2026-09-09 follow-up: downloaded live backup.py and run_update.sh and reviewed
the diff. Only the space admission and data/backup control-flow edits differed.
Installed using scripts/install_backup_space_release.py under the shared lock.
Old files are retained at
/opt/value-investment-agent/deploy-staging/backup-space-20260909/originals.
Server receipt is in the same staging directory as receipt.json.

Installed hashes:
- backup.py: f63960f6fa4dd8810fd168be0301a9a2100b25485a66fe90f5b15ed144016af1.
- run_update.sh: abc6278a3075e4f009da2c57d326749939a9ebb6fb52096b80c98c2b5322be9c.

The installed shell script passed all six stubbed real-Bash scenarios. The
installer validated old/new hashes and syntax and contains rollback handling.
This is not evidence of a real backup or restore: no real dump or service
restart was initiated. Low free space still needs remediation, not a lower
reserve. The historical paragraphs above describe pre-installation status.
