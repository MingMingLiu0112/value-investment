# Financing evidence batch 03

Date: 2026-09-09. Local original-report research, not production debt approval.

Source manifest: `runtime/candidate-financing-batch-20260909-03/manifest.json`.
Payload SHA-256: e7f836eb7aa6a2eb2f53d68ed25f1519ccf080c4dd989c0d5dd8e08f8bd45660.

Recomputed selection against the current export and five prior batch manifests (30 previously selected symbols). The next five unselected entries were offsets 7..11. All five downloaded original PDFs matched the exported SHA-256; no server storage was used and no evidence was promoted.

| Symbol | Physical page | Observation | Remaining work |
| --- | --- | --- | --- |
| 600018 | 241 | Financing table declared applicable, no component parse | Inspect layout and unit; do not infer absence of debt |
| 600060 | 186 | Five components, opening/closing sums reconcile | Employee-plan payable 206,428,136.43 CNY is included; enterprise borrowing 17,442,609.25 CNY requires contractual scope review |
| 600258 | 183 | Financing table declared applicable, no component parse | Inspect layout and continuation before extracting |
| 600267 | 229 | Three components, opening/closing sums reconcile | Short borrowing 1,979,788,723.38; long borrowing including current maturities 895,843,752.78; leases including current maturities 64,233,460.64 CNY. Check completeness against balance sheet and notes; do not add current maturities twice |
| 600284 | 189 | Five rows extracted; closing sum not established | Bond and current-bond closing cells are blank, retained as null, not zero. Review original notes and continuation |

None of the parsed tables established complete movement reconciliation. That flag alone does not establish an issuer accounting error: missing cells, table scope and parsing must be checked first. Same-file hash matching proves archive consistency, not independent financial verification or debt-scope completeness.

Next bounded step: inspect 600267 debt notes against the three captured components, and 600060 employee-plan contractual terms. Current Excel signals and scores remain unchanged.
