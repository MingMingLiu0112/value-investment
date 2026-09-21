# CEB Bank specialized metric gap evidence

The latest exported 328 required institution values comprise 181 unverified
visible values, 145 absent values with matching-period disclosure metadata,
and two absent values without matching disclosure metadata. A production
limit-5 institution collection returned inspected=0, stored=0, failures=[]:
repeating the same parser does not address these gaps.

Read-only inspection of 601818's archived 2026 interim report verified SHA-256
db2628aeec795f5cd79f7c4d860b34a61ec847bc4f99dc49e69debd59d0ee7be.
Source: https://static.cninfo.com.cn/finalpage/2026-08-29/1225528526.PDF
Archive: /app/evidence/601818/2026-06-30-interim.pdf.
Only the first 25 PDF pages were searched with pypdf in a capped container.

## Observed cells and extraction obstacles

- PDF p10: provision coverage current 150.02%, prior year-end 174.14%.
  The label is followed by a standalone footnote 6 before the value. That
  footnote must not become the current-period value.
- PDF p11: CET1 ratio current consolidated 9.67%, non-consolidated 9.30%.
  Each date has two entity columns. A single-date/one-value parser is insufficient.
- PDF p18: explicit group asset-quality paragraph reports NPL 1.44% and
  provision coverage 150.02%; group capital paragraph reports CET1 9.67%.
  The current prose recognizer assumes restrictive sentence boundaries and
  direct adjacency of group name and metric, which these paragraphs do not use.
- PDF p10 begins with net interest yield 1.42, 1.40, +0.02 percentage points,
  1.54. The period header is on the previous page and has NOT been examined
  in this check; do not approve its period based only on this row.

Next parser work must preserve footnote handling, multilevel entity headers,
explicit period mapping and conflicting-scope rejection. Repeated table/prose
within one report corroborates decoding, not independent-source verification.
No new data point was approved or written to Excel by this investigation.

## Local v11 and production read-only comparison

Local institution-table-v11-group-balances-footnotes now handles bounded
explicit group balance paragraphs, same-page defined standalone footnotes,
and an adjacent-page profitability-table continuation with explicit matching
YTD headers. PDF p9 confirms the p10 net interest yield of 1.42% refers to
2026 Jan-Jun. The output retains period_header_page=9 and value page=10;
entity scope for this ratio still requires corroboration.

Full regression: 784 passed, 18 existing Backtrader warnings. A staged copy
of the new module was loaded outside the production package in a read-only
0.5 CPU / 512 MiB container. Database transactions were read-only; all three
original file hashes were checked. Full reports were parsed using both PDFium
and pypdf. Results archived in runtime/bank-parser-comparison-20260908.jsonl
(PowerShell Tee-Object encoding). No parser was deployed or facts inserted.

| Company | Pages | Previous candidates | New candidates | Observation |
| --- | ---: | ---: | ---: | --- |
| 600036 | 246 | 3 | 3 | Values unchanged; NPL/provision gain explicit group prose |
| 601166 | 272 | 1 | 1 | CET1 9.43 unchanged; remaining gaps persist |
| 601818 | 248 | 1 | 4 | NIM 1.42, NPL 1.44, provision 150.02, CET1 9.67 |

This is a three-report regression comparison, not financial approval or
proof of full-bank coverage. New CEB values agree across both decoders,
which are not independent financial sources. Production still uses v10.

## Subsequent v11 deployment

Hash-pinned deployment completed with backup
`/opt/value-investment-agent/deploy-backups/institution-v11-j86rhyuz`.
Old module SHA: 368084a4d29bd37a04b24a8e2d7c354141c117f3c26bd68c71767c16077d948a.
New module SHA: b6410ad3aa11ffebeb719f1ae3eb4a1bb8afc388abc04218b9cea7b7a7edfaa1.
Only the reviewed institution parser diff was deployed.

Single-issuer live run (limit 1, symbols=['601818']) inspected 1, stored 4,
failures []. Fresh read-only DB verification found exactly four v11 rows,
all period 2026-06-30, unit percent, validation_status pending, automatic
cross-source verification false: CET1 9.67 (p18), NIM 1.42 (p10/header p9),
NPL 1.44 (p18), provision coverage 150.02 (p18). Candidate generation may
complete with one decoder when all required fields are found; independent
source verification remains separate. Prior two-decoder research is retained.
No Excel publication was performed in this deployment turn.

## Additional bounded batches and rejection filter

The next 10-issuer v11 batch processed 10 reports and stored 37 pending
values, no failures. A fresh read-only audit confirmed 41 v11 values across
11 issuers including CEB; all 11 linked document file hashes matched.
This includes replacement candidates, not 37 newly filled spreadsheet gaps.

The institution report selector was then aligned with the general extraction
queue to exclude review_status='rejected'. Read-only impact audit found zero
existing institution points linked to rejected disclosures. Full suite 785
passed. Production diff was only this WHERE filter. Deployment backup:
`/opt/value-investment-agent/deploy-backups/institution-rejection-tsavslzl`.
Current module SHA:
80f581517c92c439160fa1b8e6d4035e51bed188a69348ed381d3b4774984ae2.

Post-deployment live batch: inspected 5, stored 9, failures []. Per-issuer
candidate counts: 002807=1, 002839=0, 002926=4, 002936=4, 002939=0.
Zero extraction count is an unresolved parser/evidence gap, not proof the
issuer omitted the metrics. No independent verification or Excel publication
was performed by these batches. Memory remained 512 MiB with sequential work.
