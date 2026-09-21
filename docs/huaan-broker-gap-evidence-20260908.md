# Huaan Securities: three explicit interim ratios recovered

Issuer: 600909, report period 2026-06-30.

Official PDF: https://static.cninfo.com.cn/finalpage/2026-08-25/1225499631.PDF

SHA-256: `620f00d9258f69bb6c21a46fdd0ec098a5462f5c1f7f1a64a716f218c6ba01fd`.
Local research file: `runtime/600909-2026-interim-research.pdf` (212 pages).

The explicit parent-company risk-control table begins on PDF page 11. Its
current-period-first header applies to the continuation on page 12. Percent
units appear in row labels, not on individual values. The previous parser did
not recognize this layout; this was not evidence that the report lacked values.

| Field | Current percent | Prior percent | PDF page |
| --- | --- | --- | --- |
| capital_leverage | 21.18 | 19.62 | 12 |
| liquidity_coverage | 300.67 | 628.70 | 12 |
| net_stable_funding | 177.09 | 165.87 | 12 |

The page 11 net-capital/risk-reserve-sum ratio (235.76%) is deliberately not
renamed risk_coverage without a separate regulatory-definition review.

## Implementation and verification

Version `institution-table-v14-broker-label-units` adds a bounded adjacent-page
parser. It requires the explicit parent heading, current-first period header,
recognized previous-page rows and expected first continuation row; new section
headings terminate the table. It does not carry context across blank pages.

Seven new tests cover positive extraction and wrong scope, reversed columns,
new tables, invalid continuation and page gaps. Focused suite: 24 passed.
Full suite: 841 passed, 18 pre-existing Backtrader datetime warnings.
Both PDFium and pypdf reproduce the three values. Dual decoding is not an
independent financial source and does not justify verification promotion.

Production SHA-256:
`a5b0fd95f2391e5d1c43ae4171a0f5900fa4c00238117a936c42783eef5e7aa5`.
Backup: `/opt/value-investment-agent/deploy-backups/institution-v14-vxloddt9`.
Deployment required idle filing service, application-container absence, an
exclusive market-screen lock and matching baseline/staged hashes.

Single-issuer live run: inspected 1, stored 3, failures 0. A fresh read-only
database connection confirmed all three values, pending status, original PDF
hash and automatic_cross_source_verification=false. Both decoding engines are
recorded in production supporting_text_engines. No trading signal approved.

Post-run export SHA-256:
`e21b633e58d2e8a630ce14bdaa8f7d3eb7fe2adf31cec78eab076b667688a35f`.
Workbook publication must be confirmed independently from this export.
