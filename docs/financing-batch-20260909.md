# Financing Evidence Expansion

Reviewed 2026-09-09. Local research, not production debt approval.

## Selection and Archive

Latest export SHA-256: `f6415efc06459fc25bf7b5b1e42d46ca706c35ce6fe3c54c2da25308bd41d97e`.
Selection was recomputed against this export, rather than continuing stale offsets from the previous export. Five new issuers: 000719, 001872, 002078, 002170, 600008.

Archive and exact URLs/hashes: `runtime/candidate-financing-batch-20260909-01/manifest.json`. All five downloads match the exported PDF hashes. This proves archive identity, not financial completeness or independent corroboration.

## Findings

| Issuer | Physical page | Finding |
| --- | --- | --- |
| 000719 | 152 | Financing-liability table marked not applicable; not evidence of zero debt |
| 001872 | 268 | Heading found; existing component parser did not parse; needs layout review |
| 002078 | 167 | Wrapped numeric cells; table includes equity and restricted cash as well as debt |
| 002170 | 218 | Financing-liability table marked not applicable; not evidence of zero debt |
| 600008 | 225 | Explicit CNY ten-thousand unit; current maturities included in several rows |

### 002078 Scope Counterexample

Original: https://static.cninfo.com.cn/finalpage/2026-04-11/1225093922.PDF
SHA-256: `8ad0fa1bf25e1aa5a9d8470b759769ef7fa766366c53499c8b9d2a2dd88dd3e2`.

Page 167 states unit yuan. The table includes short borrowings, long borrowings, long-term payables and lease liabilities, but ALSO other monetary funds (net guarantee changes), share capital and capital reserve. It also includes dividend and financing-fee cash flows. Its closing total 25,792,977,205.48 is therefore not an interest-bearing debt total. Numeric fragments wrap within cells; do not join whitespace across the entire table. Long-term payable financing classification and current maturities require note reconciliation.

### 600008 Unit and Maturity Boundary

Original: https://static.cninfo.com.cn/finalpage/2026-04-11/1225095393.PDF
SHA-256: `1540fcaf4ae3cb08a63b9f2d2245956361b6ce20b4c2e5c891f040d23e9697a4`.

Page 225 changes from a yuan cash-flow table to a **ten-thousand yuan** financing table. Closing rows as printed: short borrowings 230,234.77; long borrowings 3,571,469.31; long-term payables 107,990.78; special payables 10,447.60; bonds 1,000,000.00; short-term financing notes 251,512.33; leases 19,516.04; total 5,191,170.83.

The footnote explicitly says long borrowings, long-term payables, leases and bonds are BEFORE reclassification of amounts due within one year. Adding the current portion again would double count. Special payables are not automatically interest-bearing; the preceding cash-flow table's perpetual-bond repayment is a flow, not an ending balance. Full debt scope remains unresolved.

## Next Action

Use cell-bound extraction for the 002078 wrapped table and inspect 600008 long-term/special-payable notes. Retain separate financing components and explicit unit/scope metadata; no full debt value, quality score or buy signal was promoted by this batch. No server or Excel change.
