# Midea CapEx Memo Receipt-Binding Audit — 2026-09-29

## Verified byte identities

The current CapEx/fixed-assets research memo is
`docs/current/track-b-midea-capex-fixed-assets-review-20260928.md`, SHA-256
`b2d14f93f46806948d42c07dcf6f74b70380371d036242f373fbdb7023849e51`. The
same hash was computed from the `HEAD` Git blob. The memo's referenced machine
receipt, `runtime/company-research/midea-capex-fixed-assets-review-20260928/receipt.json`,
records `report_sha256=bf732e55b77eea455da71a6c82491a6a9fc324f3d7c27afb556f30a2c2dc5bee`.
The existing page-corrigendum also identifies `bf732e...` as the memo hash.
These are different byte sequences; the current memo is not byte-bound by that
receipt. The current repository history contains no earlier committed copy of
the memo, and the current runtime directory contains the receipt but no saved
copy of the memo bytes matching `bf732e...`.

This is not a line-ending-only difference: the current memo is LF text without
a byte-order mark. The FY2025 and 2026H1 source PDF hashes were independently
recomputed and match the hashes cited by the receipt and memo:

| Source | SHA-256 |
|---|---|
| FY2025 report, CNINFO `1225065145` | `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6` |
| 2026H1 report, CNINFO `1225531404` | `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8` |

The receipt's extracted numeric payload remains inspectable against those
source hashes. However, it must be described as bound to the earlier memo
bytes identified by `bf732e...`, not as a receipt for the current narrative
file. No evidence here implies the reported facts are false; it narrows what
the receipt proves about the current document.

## Disposition

Keep the current memo, receipt, and earlier page-corrigendum immutable. Before
the current memo is used as an authoritative byte-bound artifact, issue a
versioned successor receipt that binds its exact SHA-256 and independently
rechecks the material figures against the retained reports. Until then, treat
the source PDFs and their hashes as the primary evidence, and the current memo
as a source-cited research note whose complete byte identity is documented
here. This does not change `MODEL_NOT_READY`, `VALUATION_NOT_READY`, the frozen
prospective baseline, or `action=no_order`; no workbook update follows.
