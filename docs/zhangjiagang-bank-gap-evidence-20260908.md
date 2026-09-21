# Zhangjiagang bank zero-extraction investigation

Issuer 002839, report period 2026-06-30.
Source: https://static.cninfo.com.cn/finalpage/2026-08-28/1225521596.PDF
SHA-256: f2ccde460ef1c60c8462dbf1b9e1b26e85827edf34eb75c7ff1665502e6aa571.
Local research copy: runtime/002839-2026-interim-research.pdf.
Server and copied PDF hashes checked; first 35 pages searched with pypdf.

The v11 collector returned zero candidates, but the original contains metrics.
PDF p8 has regulatory headings split over lines, a regulatory-threshold column,
and current/prior-year-end/earlier-year-end date columns. CET1 ratio is 10.63%,
not the adjacent 7.5% threshold. PDF p9 continues without repeating dates:
NPL 0.94% (threshold 5), provision coverage 325.07% (threshold 150).
NIM 1.35% appears in the same period-end-headed table. Its cumulative or
annualized duration must be separately corroborated; do not assume it from
the period-end column alone. PDF p12 repeats the three risk/capital figures
in issuer narrative but does not supply independent-source verification.

PDF p9 then starts a NEW capital table with explicit consolidated and
non-consolidated columns for each date. PDF p10 continues that table:
current CET1 ratios 10.63% consolidated, 10.60% non-consolidated.
Do not carry the earlier regulatory table header through this new header.

## Capital arithmetic cross-check

All numerator/denominator amounts below are CNY ten-thousand on PDF p9.

- Consolidated CET1 net capital 1,812,767.51 / risk-weighted assets
  17,050,315.87 * 100 = 10.63187054%, consistent with displayed 10.63%.
- Non-consolidated 1,789,401.09 / 16,875,328.41 * 100 = 10.60365195%,
  consistent with displayed 10.60%.

These are reviewed-body observations and arithmetic, not independently verified
financial facts. Next parser work needs explicit threshold-column handling and
adjacent-page capital entity headers; it must not confuse the two table
continuations or assign annual/YTD semantics to a stock-date header. No new
financial points or Excel cells were written in this investigation.

## Full-report margin search

Subsequently searched all 158 PDF pages using pypdf for net-interest-margin
mentions and annualized-return wording. Net interest margin was found only
in the p9 table and its definition: net interest income / average
interest-earning assets * 100. The searched text did not establish an explicit
Jan-Jun or annualization basis. Absence in extracted text is not proof of
absence in the rendered PDF. Do not label 1.35% as verified YTD, annualized,
or TTM from this check. Its period-end-headed comparative table alone is
insufficient for a flow-ratio basis. Continue the three stock-date risk and
capital metrics separately rather than blocking all evidence on this ratio.

## v12 implementation and live validation

Added explicit three-date regulatory table parsing with separate threshold
column and restricted adjacent-page continuation. New table headers terminate
the inherited context. Net interest margin is excluded from this rule.
Actual full PDF parsed with PDFium/pypdf yielded matching CET1 10.63, NPL 0.94,
provision coverage 325.07; full suite 787 passed (18 existing warnings).

Hash-pinned deployment backup:
`/opt/value-investment-agent/deploy-backups/institution-v12-b64lrsd6`.
Current institution_metrics.py SHA:
fc6613cae13c6f1949d367d99829e42b968a28d2d725f6de251a4a4ff761f61d.
Live issuer-limited run inspected 1, stored 3, failures []. Fresh read-only
connection confirmed all three values are pending for 2026-06-30, and threshold
metadata is separate (CET1 >=7.5, NPL <=5, provision >=150). CET1 value/header
page 8; NPL/provision value page 9, header page 8. No margin row generated.
This is candidate persistence, not financial validation. No Excel sync yet.
