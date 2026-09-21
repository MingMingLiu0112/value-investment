# Validation checkpoint: 2026-09-09

## Direct observations

- Read-only SSH inspection succeeded using the project key. The initial sandboxed attempt could not read the key; retry with approved access succeeded. No SSH configuration was changed.
- Root filesystem: 39,942 MiB total, 36,049 MiB used, 2,047 MiB available, 95% usage.
- Available memory: 1,754 MiB; swap used: 418 MiB. This snapshot does not establish an OOM event.
- Filing service: inactive, ExecMainStatus=0. This does not prove all individual downloads succeeded.
- PostgreSQL container: up 37 hours. No services were restarted or stopped.
- Production financial_quality.py SHA-256: 6b01ea1b85a61ef1b9259e51f5a56bd4d19731c0b4b968caf645b6f6ebe3c02c.
- Numeric-validation changes remain local; no deployment performed in this checkpoint.

## Re-run verification

Command: `runtime/venv/Scripts/python.exe -m pytest tests/test_financial_quality.py tests/test_research_broker.py tests/test_research_commission.py -q -p no:cacheprovider`

Result: 35 passed in 0.31 seconds. These checks cover software behavior, not independent source verification, historical valuation completeness, profitability or portfolio suitability.

## Execution priorities

1. Keep the 2 GiB PDF download reserve. Current available space is below that threshold; retries alone cannot fix capacity. Do not delete evidence or other projects, or provision paid storage without authorization.
2. Continue historical research locally. Reconstruct valuation from inputs available at each historical decision date before reporting strategy performance. Do not reuse current fair values or the current candidate universe as historical inputs.
3. Treat the three-company experiment in strategy-validation-protocol.md as a case study, not proof of whole-market selection effectiveness.
4. Keep evidence verification and strategy validation visibly separate. No performance result or strategy approval was produced in this checkpoint; the canonical workbook was not changed.

The overall investment-assistant objective remains incomplete.
