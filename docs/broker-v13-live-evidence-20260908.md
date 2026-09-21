# Great Wall Securities interim metrics: production persistence

On September 8, 2026, production collection inspected one issuer (002939),
stored four pending points, and reported no failures using
`institution-table-v13-broker-continuation`.

Source: https://static.cninfo.com.cn/finalpage/2026-08-27/1225509373.PDF

SHA-256: `08dab93cd70dbea1a8ab2ec9bf4cfd9124d9572965007f3d0ee60ee32d5dd64b`.

| Field | Percent at 2026-06-30 |
| --- | --- |
| risk_coverage | 343.21 |
| capital_leverage | 25.21 |
| liquidity_coverage | 304.74 |
| net_stable_funding | 184.10 |

The explicit parent-company heading and period header are on PDF page 8;
the continuation values are on page 9. Do not represent these as consolidated
group ratios. A fresh read-only database connection verified exactly four rows,
matching period, values, pending status, original document hash and
`automatic_cross_source_verification=false`. Same-document extraction is not
independent cross-source verification and does not approve trading signals.

## Disk recovery before collection

The server initially had 2026 MiB free. Inspection found 484 pip HTTP download
cache files older than 30 days under `/home/admin/.cache/pip/http-v2`, totaling
634549065 bytes. Only those aged cache files were removed after path checks.
No installed packages, Playwright browsers, PTA/Hermes files, database data,
original evidence or backups were deleted. Independent post-cleanup checks
showed 2632 MiB free and the cache directory at 4 MiB.

Collection used the existing PDF via a read-only evidence mount, a 512 MiB
container limit and the market-screen lock. This headroom is temporary and
does not establish sufficient capacity for unlimited all-market collection.

The subsequent export completed successfully with SHA-256
`4c55cbce870099676fbff7fbe068b996a3c23cf10fd47f7fa8f410884a83b60e`.
Workbook publication is verified separately by the synchronization status and
preservation validator, not inferred from successful export.
