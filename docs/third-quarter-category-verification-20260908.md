# Third-quarter collection verification, 2026-09-08

## Defect and bounded deployment

CNINFO third-quarter reports require `category_sjdbg_szsh`. The previous
mapping used the first-quarter category `category_yjdbg_szsh`, omitting Q3
reports. Category-specific regression fixtures now prevent the former mock
from returning every report type for every category. The full suite recorded
761 passing tests; this is software verification, not strategy validation.

Only the category correction was deployed. Backup directory:
`/opt/value-investment-agent/deploy-backups/third-quarter-category-2w0f1ecd`.
Deployed disclosures.py SHA-256:
`d28f4291751f9122a2d550a34ee1aa6a7c30e3f6a74c3e74a36f29ce3f97f145`.

## Independent persistence check

After the single-symbol collector returned four stored filings, a fresh
container opened a new database connection with `SET TRANSACTION READ ONLY`.
The evidence mount was read-only. Limits: 0.5 CPU, 256 MiB memory, 384 MiB
memory-plus-swap. The check exited successfully and the container was removed.

- Symbol: 600519
- Report period: 2025-09-30
- Report kind: third_quarter
- Original URL: https://static.cninfo.com.cn/finalpage/2025-10-30/1224764517.PDF
- SHA-256: `622935d03b23310dcde1ba3c3d398b130c3fbf73b753fb79fab934999524307a`
- Archived file exists: true
- Recomputed file hash equals database hash: true
- Extraction status: pending

This verifies one archived report, not completeness across the company pool,
financial extraction accuracy, or historical strategy performance. No Excel
publication or financial approval was performed by this verification. Other
application services were not restarted.

## Research consequence

Historical Q3 indexes must use the corrected category and bounded date ranges.
TTM construction still requires compatible current cumulative, prior annual,
and prior comparative cumulative figures, their original disclosure dates,
and a consistent share basis. Annual EPS is not a substitute for daily TTM.
Keep decision-validation status incomplete until real point-in-time financials
and executable trading assumptions support a reproducible backtest.
