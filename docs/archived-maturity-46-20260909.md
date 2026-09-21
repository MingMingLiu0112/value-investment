# Archived current maturity batch

Date: 2026-09-09. Local research only; no server change, database promotion,
canonical Excel rewrite or strategy approval.

## Completed replay

`scripts/audit_archived_current_maturities.py` sequentially processed 46 unique
companies from the six `candidate-financing-batch-*` manifests and the six-company
`nearcomplete-financing-20260909` manifest. It rehashed original files and reran
both financing-table and current-maturity-note extraction. No new download.
Duplicates with different report records are rejected; limit is 50 companies.

Output: `runtime/archived-current-maturity-46-20260909.json`.
Actual elapsed: 82.56 seconds, completed successfully.

- 25 companies had one parsed current-maturity note.
- 23 note totals exactly matched accepted same-period, same-original database
  balances with retained secondary-source IDs and evidence.
- 002440 and 002452 had notes but no corresponding same-period balance fact in
  the snapshot. This is a missing-evidence result, not a numeric conflict.
- 21 companies had no uniquely parsed note under the supported formats. This
  does not mean their reports omit the disclosure or their debt is zero.
- No per-company execution exception was reported. All 46 retain
  `complete_debt_verified=false`.

## New borrowing bridge

`audit_current_maturity_notes.reconcile` now distinguishes current long-term
borrowings from current leases. It subtracts only the matching explicit component
from an exact current-inclusive row label. A current-maturity aggregate must
first reconcile and match an accepted database fact; missing components are not
defaulted to zero. Existing lease output keys remain unchanged.

| Company | Current long borrowing CNY | Noncurrent long borrowing CNY | Financing inclusive borrowing CNY |
| --- | ---: | ---: | ---: |
| 002091 Jiangsu Guotai | 52,929,144.55 | 268,390,114.73 | 321,319,259.28 |
| 002011 Dunan Environment | 6,886,329.16 | 484,500,000.00 | 491,386,329.16 |

Both equations match exactly, with noncurrent inputs traced to verified database
facts. The Dunan aggregate current maturity also includes current leases, so
subtracting its entire CNY 14,185,700.88 would be wrong.

Five inclusive lease bridges also matched: 002091, 002011, 002043, 002444,
301376. The first company is Jiangsu Guotai, not Zhongtai Chemical; an interim
chat name mistake was corrected after checking the candidate payload. Stored
audit identifiers and amounts were always 002091.

## Tests and next evidence work

21 focused tests passed; full suite 1128 passed, 18 existing Backtrader datetime
deprecation warnings. Tests cover bounded selection, ambiguous versions,
unverified archives, borrowing/lease component separation, missing components,
and blocked aggregate evidence. Actual stored results were read back for counts
and the two borrowing equations.

The underlying exported snapshot remains the September 9 morning snapshot;
this was not a live provider or database refresh. Parsing and same-document
reconciliation do not independently verify component classification or prove
complete financing scope. No debt fact or buy/sell instruction was approved.

Next: classify unsupported note formats among the 21 companies, obtain missing
balance facts for 002440/002452 through official statements and corroboration,
and inspect financing bills and other-payable terms. Bank-borrowing inclusive
rows require separate short/noncurrent/current reconciliation; they were not
mapped to the long-borrowing-only formula.

Later diagnosis correction: 002440/002452 current note totals are blank in the
originals, not known numeric facts missing only from the database. See
`maturity-geometry-v3-20260909.md`; do not retry collection on the assumption
that a disclosed current amount was lost, and do not synthesize zero.
