# Public first-input cold-process delivery

Restores the public registered research for 600519, 600887 and 000568 with
original source bytes, financial sources, configuration and receipts. The
source contents correspond to b640cbea0adeedc40137efb63eee7782089c8127;
historical Windows line endings are preserved for raw implementation hashes.
No receipt is re-signed and no historical result is overwritten.

```powershell
python -B scripts/cases/restore_first_input_delivery.py --archive artifacts/current/first-input-delivery-20261117-cold --sha256 4b95fddb8789946da8d9378087a5886b780e926cd35ff73c09ceef007861f2a4 --destination .tmp/first-input-cold-check
```

The existing archive validates original bytes before extraction. Each company
then runs in an isolated Python process importing the restored source. Receipt
binding, input fingerprint, annual ledgers, valuation and financial-update
observation must exactly match the sealed projection. A mismatch prevents
publication of the restored directory. The direct test uses these real sources,
not simulated financial inputs.

Scope: historical E2 read-model replay only. This does not certify current F2
prices, complete task history, browser acceptance or investment approval.
Permanent action=no_order. The earlier sibling archive is historical evidence
of the failed clean-portability approach, not the accepted current delivery.
