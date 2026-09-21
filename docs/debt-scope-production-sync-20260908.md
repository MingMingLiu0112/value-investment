# Production Debt Scope Sync

2026-09-08, approximately 18:32 CST. Two-file deployment only.

- `quality.py`: `950a7b54e69cc0f1b3466a9095dc94bf49afde477e8175eb07444c2b02bc1015`
- `financial_quality.py`: `f0b732b90942cc2c50096df771e08628532c76f0aaac1dff4065e4cafb20854c`
- Server backup: `/opt/value-investment-agent/deploy-backups/debt-scope-sync-k85hqbgk`
- Command: staged `deploy_debt_scope_sync.py`; baseline hashes, exclusive market
  lock, absence of an active app container, and resulting hashes checked.

The previous filing service run exited 126 at 18:30:15 due to runc cgroup
configuration failure (`unable to freeze`). It had already reported 30 filings
stored and 443 extraction candidates. This was not established to be an OOM.
At deployment there was no active collector; only its ten-minute retry was
pending. The retry was stopped, files backed up/replaced, and the same service
started again. No database, PTA service, resource limits or timers were changed.

The restarted run began 18:32:38, then reported 27 filings stored with one failed
symbol. Its subsequent application container `practical_feynman` was observed
running. A read-only `podman exec` Python smoke test in that actual container
confirmed `accepted_verification` and financial-quality `_accepted` reject an
explicit incomplete-debt point and still accept a verified cash point.

PTA process PID 236577 was present after deployment. Free memory at the earlier
preflight was 1678 MiB available; root disk remained 94% used, 2.3 GiB available.

This verifies deployment and service resumption, not completion of the restarted
collection run or resolution of its failed symbol. No Excel export was published
in this deployment. Research PDF parsers and pdfplumber were not deployed.
