# Financing-to-balance evidence bridge

Date: 2026-09-09. Local research and gate correction; no server deployment,
database promotion or canonical Excel update.

## Actual audit

New command:

```powershell
runtime/venv/Scripts/python.exe scripts/audit_financing_balance_bridge.py runtime/server-export-payload.json runtime/nearcomplete-financing-20260909/manifest.json runtime/nearcomplete-financing-20260909/continuation-sign-replay.json --output runtime/nearcomplete-financing-20260909/balance-bridge.json
```

The output already exists; exclusive creation prevents accidental overwrite.
The audit rehashes each local original, retains input hashes, report URLs,
physical table pages, raw rows, database point IDs and secondary evidence.
It does not silently choose between distinct candidate facts or equate
current-inclusive rows with noncurrent balance-sheet fields.

Snapshot generated at 2026-09-08T23:15:40.333435+00:00; not a live database query.

| Symbol | Financing rows | Exact matches to verified same-report facts |
| --- | ---: | ---: |
| 001233 | 4 | 4 |
| 001386 | 4 | 4 |
| 002011 | 5 | 1 |
| 002043 | 3 | 1 |
| 002444 | 2 | 1 |
| 301376 | 3 | 0 |

Total: 11 of 21 rows. The other ten need note classification, not guessed zeros
or relaxed numeric tolerance. All outputs retain `complete_debt_verified=false`.
Even a lease row matching a noncurrent balance numerically is not proof that the
financing-table row excludes current maturities; note evidence remains necessary.

## 001386 original-note review

Source: https://static.cninfo.com.cn/finalpage/2026-04-29/1225226366.PDF

SHA-256: e3a51ce63efb2cff575d6cec6cbc33b12ca3c7ed6afc1f75be4ce8c25cad1bf2.

Read physical PDF pages 186, 188, 189, 191, 192 and 203 using pypdf layout.
Do not confuse printed page numbers with physical PDF pages.

- Page 186 short borrowings: CNY 344,918,343.77.
- Page 191 current long borrowings 293,633,910.04 plus current leases
  15,480,543.10 equals current noncurrent liabilities 309,114,453.14.
- Page 191 noncurrent long borrowings: 127,318,994.79.
- Page 192 noncurrent leases: 33,506,280.86.
- These four presentation lines sum to 814,858,072.56, exactly matching
  the financing rollforward on page 203. Underlying balance-sheet facts
  have independent structured corroboration retained in the snapshot.
- Pages 191-192 bond and long-term-payable templates are blank. They are
  not explicit zero declarations and were not filled with zero.
- Page 188 other payables 852,462,474.28 include expenses/accruals
  468,788,691.79, deposits 301,927,957.47, equipment/construction
  80,705,864.27, related-party amounts explicitly 0.00, and collection/payment
  agency amounts 1,039,960.75. Labels alone do not prove financing terms.
- Page 186 restricted cash is 822,618,728.53, including bill/guarantee margins,
  term deposits and subscribed structured deposits. Gross cash must not be
  presented as fully freely available without an availability policy.

Remaining scope: payable bills and financing/recourse terms, complete treatment
of empty liability presentations, and cash availability. The matched subtotal
is not a complete interest-bearing-debt certification.

## Missing-scope gate correction

`financial_quality._accepted` previously rejected explicit false scope but
accepted an absent scope marker on otherwise verified interest-bearing debt.
It now requires `complete_debt_verified is True`. Automatic cross-source
verification and quarantine checks remain required; the known four-line proxy
remains rejected even with a true scope flag. This marker is a necessary gate,
not a new mechanism for approving debt or replacing retained evidence.

Positive synthetic fixtures now explicitly identify approved debt scope.
Negative tests verify that omission blocks a buy research reminder even when
cached financial quality says verified, and hides an Excel total score while
retaining other annual/interim evidence. No real facts were assigned new flags.
Snapshot check: 902 debt export rows (not distinct companies), zero accepted
after the strict scope gate. Production gate deployment remains outstanding.

## Verification and next work

Full suite: 1104 passed, 18 existing Backtrader datetime deprecation warnings.
Actual six-report audit was rerun read-only after the final code changes:
11 matches, 21 rows. Tests also cover mismatched report hashes, changed original
bytes, nonindependent source IDs, stale/rejected facts, duplicate candidates,
unit normalization and unknown blanks.

Next: scope-aware current-maturity note extraction and financing-bill evidence,
then a controlled production release of the explicit-scope gate. Historical
performance backtests and approved portfolio guidance remain incomplete.

Follow-up: the narrow production gate release subsequently completed; see
`debt-scope-gate-installed-20260909.md` for installed hashes and actual probe
results. This does not deploy the local research bridge or approve its subtotals.
