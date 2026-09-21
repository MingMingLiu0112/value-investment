# Brokerage cash scope investigation

Original PDFs downloaded locally and matched the retained SHA-256 values.
Artifacts: `runtime/broker-cash-conflicts-20260909/`.
No production facts changed; these are original-document scope findings.

## 601555 Soochow Securities

CNINFO: https://static.cninfo.com.cn/finalpage/2026-04-29/1225227241.PDF

SHA256: `1acbe54e5c65fee0dfe5f8c7e5befb78dcca87eca714f2a7b91769f1e915eb1b`

- PDF page 103 consolidated balance sheet: monetary funds 50,712,968,311.82
  CNY, including customer deposits 46,899,008,797.56 CNY.
- Page 195 also reports 50,712,968,311.82.
- Page 203 explicitly reports maximum credit risk exposure: monetary-funds
  exposure 50,712,957,311.82, not the identical balance-sheet measure.
- Difference 11,000 CNY is not evidence of an issuer revision. Its precise
  component explanation has not yet been checked; do not invent one.

## 601688 Huatai Securities

CNINFO: https://static.cninfo.com.cn/finalpage/2026-03-31/1225050753.PDF

SHA256: `21cc964443b83a0ceff0333600e53abe8d948e987ec2604de992443258cd3d34`

- PDF page 203 financial statement monetary funds: 223,337,707,129.80 CNY,
  including customer deposits 175,644,151,904.04 CNY (first current group column).
- Page 347 financial-instrument measurement classification confirms carrying
  amount 223,337,707,129.80 CNY.
- Page 313 maximum credit-risk-exposure table: 223,337,448,815.74 CNY.
  PDF text places some subsection prose after the table; do not infer scope
  solely from the first heading on the page.
- Difference 258,314.06 CNY is a scope discrepancy pending component
  reconciliation, not permission to substitute exposure for monetary funds.

## Implications

Exclude risk-exposure observations from the canonical balance-sheet cash field.
Retain them as separately scoped evidence if useful. Even canonical brokerage
monetary funds are not shareholder-available cash: customer money, settlement
balances, restrictions and prudential requirements need separate modelling.
Subtracting customer deposits alone does not prove free cash. Keep financial
institution valuation gates in place; these findings do not authorize trades.
