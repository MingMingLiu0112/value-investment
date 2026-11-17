# Public first-input delivery

Historical in-process validation only. A clean-checkout check subsequently
failed because Git-normalized source bytes differed from the historical
implementation hashes. Use `../first-input-delivery-20261117-cold` for the
corrected cold-process delivery. This archive remains unchanged as evidence;
its original validation is not a clean-checkout acceptance.

This content-addressed archive restores the exact public inputs currently read
for 600519, 600887 and 000568. It contains no portfolio or approval record.
The source snapshot is commit `b640cbea0adeedc40137efb63eee7782089c8127`.

Restore and recalculate into a new isolated directory:

```powershell
python -B scripts/cases/restore_first_input_delivery.py --archive artifacts/current/first-input-delivery-20261117 --sha256 e79dbe10d20d22ce432b491fc9d6ef1efbf5d0f4853d48a3792c74917399d66d --destination .tmp/first-input-delivery-check
```

The existing archive adapter validates every object hash and publishes the
isolated directory only after the registered receipt, input fingerprint,
annual ledgers, valuation and financial-update observation match the sealed
expected result. Historical files retain their original runtime paths.

This proves the E2 read-model closure only. It does not prove complete D2 task
history, current F2 price alignment, current quote registration, formal
approval, personal account readiness, or browser acceptance. `action=no_order`.
`validation.json` records the original local archive path; its manifest bytes
are identical to this portable archive.
