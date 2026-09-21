# Candidate filing refresh verification

Production read-only coverage found 738 candidates, 735 with archived 2025
annual reports, 733 with 2026 interim reports, and no candidate Q3 archives.
These are document counts, not verified financial completeness.

The production service runs collect-filings (default initial universe), then
enrich-financials with limit 40. The queue previously never reclaimed archived
issuers. The tested local correction makes archived current candidates eligible
after one day and orders claims oldest-first, retaining SKIP LOCKED and limits.
One day is an eligibility delay, not a guaranteed daily refresh SLA for 738
issuers; actual throughput and source failures still determine completion.

Full unit suite: 772 passed, 18 Backtrader deprecation warnings.
`scripts/test_refresh_queue_postgres.py` executed the exact local function
against server PostgreSQL TEMP tables in a 256 MiB container. Verified:
old current candidate claimed first with limit 1; pending candidate next;
recent archived and no-longer-current archived candidates not claimed;
fresh processing claims not duplicated; attempts incremented only for claims.
Connection closure removed the temporary tables. No business rows were changed.

Production diff against staged local db.py contains only this queue change.
Local SHA-256: 0548178e2f6f7655628bdb8cdca5b5177a81bbce3468f125df7cf71ef48249e3.
Not yet deployed. Staged research copy: /tmp/value-investment-refresh-db.py.

Resource check: available memory 1727 MiB, disk free 2348232 KiB (94% used).
The shell checks the 2 GiB reserve at batch start; local disclosures._download
also checks before every 1 MiB write and removes partial files on failure.
Confirm production hash before relying on that protection for resumed batches.
No memory limits, other services, Excel signals, or production queue state were
changed by these checks. Next: hash-pinned deployment and bounded live collection.

## Deployment and live follow-up

Subsequently deployed successfully after confirming production db.py baseline
`baf7cf6659e2b34b8192446bb43ae779debd6c96da772f9610c45c5bd1a0b9bd`
and disclosures.py hash
`d28f4291751f9122a2d550a34ee1aa6a7c30e3f6a74c3e74a36f29ce3f97f145`.
The latter includes the per-chunk disk reserve guard.
Backup: `/opt/value-investment-agent/deploy-backups/filing-refresh-queue-2_79_b5f`.
Deployment retained the expected local db.py hash above.

A locked, 0.5 CPU / 512 MiB enrich-financials run with limit 1 completed one
issuer, zero failures. A fresh read-only connection identified 600015 as the
latest completed queue item at 2026-09-08 13:07:39.957124 UTC, attempts 3.
All four archived report files recomputed to their stored hashes. The newly
present 2025-09-30 Q3 report is still pending extraction:
https://static.cninfo.com.cn/finalpage/2025-10-24/1224728982.PDF
SHA-256: dc709803bddf7dd642cba94380dbff150fa48fda9b6a76bdf5dd65fd1063f9e2.
2025 annual, 2026 Q1 and 2026 interim archives also passed file-hash checks.
This proves one live collection, not completion of the remaining candidate pool.
No Excel publication or financial fact promotion was performed in this run.

## Extraction follow-up

A subsequent production batch processed 40 reports at 0.5 CPU / 512 MiB.
Fresh database connection confirmed committed task details: requested 40,
candidate counter 392, failed 0; 13:09:37 to 13:10:56 UTC. This counter is not
a count of newly inserted unique verified facts (inserts can ignore conflicts).
600015 Q3 remains pending with zero stored candidates: newer candidate-pool
reports precede it. Do not describe this batch as having parsed that Q3 report.

Code inspection found whole-batch rollback risk if a later report fails.
Local cli.py now commits each successful report and each failure status
separately. A regression test with success/failure/success confirms earlier
evidence survives. Targeted test passed; this transaction fix is not deployed
and still requires full regression and production baseline review.

## Transaction fix deployment

Full regression subsequently passed: 773 tests, 18 existing Backtrader
deprecation warnings. Production diff was exactly two commit calls and one
comment. Hash-pinned deployment succeeded with backup
`/opt/value-investment-agent/deploy-backups/extraction-transactions-q53mgf7a`.
cli.py moved from
`80febb2e8c89e4be9cc0c2a76313ce47c338d01ffd15f39871c7ddaaa4ebb25a` to
`a59782f4374717742cd7d8ace2f8a9ab9fac457deef413a5a230f1791c721f0c`.
A subsequent locked one-report production smoke run completed successfully:
requested 1, candidate counter 15, failed 0. This confirms the successful
path runs; injected failure isolation is covered by the local regression,
not a deliberately broken production report. No financial approval or Excel
publication occurred, and resource limits and other services were unchanged.
