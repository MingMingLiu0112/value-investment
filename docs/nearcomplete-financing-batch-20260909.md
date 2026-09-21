# Six near-complete company financing tables

Selection: six candidates whose annual quality required-field set lacks only
interest_bearing_debt, selected from the latest exported quality queue before
this audit. Other decision gates remain unpassed. Not a strategy selection.

Existing audit_candidate_financing.py fetched six CNINFO originals to D: and
verified each against the archived export SHA-256. No server storage increase,
database promotion or Excel write. Manifest and raw PDFs:
runtime/nearcomplete-financing-20260909/manifest.json.

| Symbol | Physical page | Parser outcome | Remaining issue |
| --- | ---: | --- | --- |
| 001233 | 216 | Four components, closing 384102952.80 CNY | Notes/classification; blank movement cells remain unknown |
| 001386 | 203 | Four components, closing 814858072.56 CNY | Balances and movements reconcile, but full financing scope unverified |
| 002011 | 191 | Five rows, closing total 736363131.54 CNY | Contains dividends 3182036.73; borrowing/lease rows include current maturities; blank ending rent row |
| 002043 | 166 | Three rows, closing total 43862633.62 CNY | Dividends included in table; ending dividend cell blank, not observed zero |
| 002444 | 156 | Title found, no component parse | Inspect layout before parser extension |
| 301376 | 202 | Heading-only/cross-page evidence captured | Needs bounded continuation parsing and scope review |

For 001233 the automated extraction independently reproduces the previously
read same-document components. This is parser validation, not an independent
financial source. For 001386 rollforward arithmetic passes; arithmetic does
not prove the table covers every financing obligation.

Next actions are now concrete: inspect 002444 layout and 301376 continuation;
compare 001386 components with current-maturity/lease/payable notes; preserve
dividend exclusions and unknown blank balances for 002011/002043. Do not
promote table totals to complete debt merely to clear the quality gate.
