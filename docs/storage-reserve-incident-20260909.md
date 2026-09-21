# Storage Reserve Incident

Observed 2026-09-09 00:36-00:38 Asia/Shanghai via SSH and read-only database query.

Root filesystem: 39,942 MiB total, 36,049 MiB used, approximately 2,048 MiB available (95% used). Available RAM 1,682 MiB. No evidence here establishes an OOM.

The 00:20:41 filing service archived 40 index records; its archive stage completed 30 of 40 and failed 10. Querying `financial_enrichment_queue` confirmed these ten symbols have retry status and error `Low disk during PDF download; preserve database reserve`:

`000708`, `600720`, `600717`, `002061`, `002128`, `000617`, `601298`, `000589`, `601901`, `000783`.

The 2 GiB chunk-level download guard remains enabled. No retained evidence was deleted and the threshold was not lowered. Failed PDF downloads are not completed evidence. Later stages processed already archived material, and the service ended with exit status 0 at 00:38:40; that process status does not erase the ten archive failures. A new export was produced at 00:38:40.

## Recovery Boundary

Storage choice requested from the user: new data disk (recommended for evidence and backups), system disk expansion, or object-storage evaluation. No paid change authorized or executed. Do not remove other projects, PostgreSQL data, retained reports, or backups to create apparent progress.

After storage is provisioned, confirm actual free bytes exceed the reserve with room for the bounded batch, then revalidate these queue entries and use existing retry behavior. Do not reset all candidate statuses or rerun the entire universe simply to address this incident. Repeated failures can still arise from network or disclosure changes; verify their actual reason at retry time.

Current guard protects PDF writes, not every database/log/export write on the shared filesystem. It is not a substitute for capacity remediation. Local D-drive research remains available without consuming server PDF storage. PTA, Hermes and PostgreSQL were not restarted or reconfigured in this check.
