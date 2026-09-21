# Broker regulatory research and workbook references

Official sources were opened in the browser on September 8, 2026:

- CSRC management rules, amended by order 166:
  https://www.csrc.gov.cn/csrc/c106256/c1653957/content.shtml
- CSRC announcement 2024 No. 13:
  https://www.csrc.gov.cn/csrc/c101954/c7507765/content.shtml

Original HTML and the calculation-standard PDF were archived with timestamps,
final URLs and SHA-256 in
`runtime/trading-rule-evidence/20260908T152309866547Z/manifest.json`.
The PDF SHA-256 is
`6259b9d61918aaa5491a514cd161a9e3ccf5d7f78cb320eac3b94f3f19f8b530`.

## Findings

The 2024 calculation standard takes effect January 1, 2025 and repeals the
2020 calculation standard. Relevant PDF pages: 1 (effective date), 20
(threshold table), 21 (formulas), 22 (consolidated-supervision exceptions).
Management-rule articles 17, 21 and 22 state formulas, warning thresholds and
the usual parent-company reporting basis, respectively.

| Metric | General minimum % | General warning line % |
| --- | --- | --- |
| Risk coverage | 100 | 120 |
| Capital leverage | 8 | 9.6 |
| Liquidity coverage | 100 | 120 |
| Net stable funding | 100 | 120 |

Risk coverage uses net capital divided by total risk capital requirements.
Capital leverage uses core net capital divided by on/off-balance-sheet assets;
the 2024 attachment explicitly excludes the deduction for guarantee/other
contingent-liability risk adjustments from that numerator. Ordinary balance
sheet leverage is not a substitute. Issuer-specific and consolidated regulatory
requirements may differ; general numerical comparison is not a compliance
determination or an investment-quality score.

Huaan's abbreviated net-capital/risk-reserve wording remains unmapped: the
official rule alone does not establish that the issuer's differently named
denominator has exactly the required scope. Its missing risk_coverage field
was not fabricated or promoted by this change.

## Workbook change

The financial-specialized sheet preserves its first twelve columns and appends
general minimum, warning line and a numerical-comparison column. Comments link
to the official notice and PDF hash and state the limitations. References are
bounded to report dates from 2025-01-01 through the research review date
2026-09-08; older/future periods and non-broker fields are not assigned these
rules. Missing/nonfinite/negative/bool values do not produce comparisons.
Values exactly at the warning line are conservatively described as within the
warning interval. No data verification status or trading gate is promoted.

Tests: 30 focused passed; 860 full-suite passed with 18 existing Backtrader
datetime deprecation warnings. Integration coverage verifies that a pending
ratio above the warning line remains pending and strategy validation remains
incomplete. This change runs in the local Excel renderer; it is not a server
valuation model deployment or historical strategy backtest.
