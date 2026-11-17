# Current public first-input replay delivery

Source commit: 0e993ab4 (full commit recorded in the hash-bound bundle).
This corrects Windows source-name parsing on POSIX without changing original
PDFs, OCR outputs, historical financial receipts or their hashes.
Raw source line endings are retained for historical implementation bindings.

```powershell
python -B scripts/cases/restore_first_input_delivery.py --archive artifacts/current/first-input-delivery-20261117-portable --sha256 d78f8b5be8f76f197146e08ecb1c3c71770c99a2d63105e2e20811ba87247001 --destination .tmp/portable-check
```

Each company runs in an isolated process from restored source. Receipt bindings,
annual ledgers, valuations, input fingerprints and new-financial observations
must match. Previous sibling archives remain historical evidence of attempts;
only this archive is targeted by the current real-source test.

Scope remains E2 read-model replay, not complete F2 or investment approval.
action=no_order.
