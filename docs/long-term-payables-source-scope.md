# Long-Term Payables Source Scope

Read-only comparison on 2026-09-08, period 2025-12-31.

## 000683

- Official consolidated balance sheet, PDF page 91: CNY 856,562,918.59.
- Sina detailed statement item: CNY 856,562,918.59.
- Official URL: https://static.cninfo.com.cn/finalpage/2026-04-21/1225131777.PDF
- Verified archive SHA-256: `42c2341862a91730353744194cef8eba83ec199a4ce50eec1a4c9b6356880edd`.

## 000338

- Official consolidated balance sheet, PDF page 80: CNY 11,548,169,161.00.
- Sina detailed statement item: CNY 11,525,169,161.00.
- Difference: CNY 23,000,000.00.
- Official URL: https://static.cninfo.com.cn/finalpage/2026-03-27/1225037559.PDF
- Verified archive SHA-256: `3541dbf8f49275eb161afaab322dd8ef4919faa56e297690a22c0197639de1ba`.

The raw label alone does not establish equal scope. The official note observed
in the earlier scope audit separately reports the same CNY 11,525,169,161.00
component. Inspect special payables and the complete note reconciliation before
mapping the structured component to the consolidated balance-sheet total.
Do not relax numeric tolerance to absorb the difference. A smaller omitted
component could fall within tolerance, so scope must be resolved before using
this mapping for automatic promotion across the pool.

No new facts were stored by this probe. The new mapping is not deployed.

## Confirmed Reconciliation

PDF page 151 explicitly shows CNY 11,525,169,161.00 long-term payables plus
CNY 23,000,000.00 special payables equals the CNY 11,548,169,161.00 total.
The special-payable note describes provincial finance loan-interest subsidies.
The other component itself includes government project funding, guaranteed
residual values, and sale-and-leaseback financial liabilities. It is not a pure
financing-debt balance either.

The structured adapter now retains `long_term_payables_excluding_special` and
`special_payables_noncurrent` separately. Direct automatic promotion of the
official total is disabled until an evidence-backed same-scope sum is available.
Absent special payables must remain unknown, not implicit zero.
