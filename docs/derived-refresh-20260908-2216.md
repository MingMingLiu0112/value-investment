# Derived financial refresh

Latest exported snapshot at 2026-09-08T14:08:06.944979Z yielded 49 research
recalculation candidates after explicit latest-period/created-time selection.
This was an input-availability probe, not a claim of 49 newly filled cells.

Production refresh-financial-quality completed for 738 issuers with existing
logic and retained verified inputs, under 0.5 CPU / 256 MiB, no downloads.
A fresh read-only connection confirmed 38 derived rows created in the run's
database timestamp window:

| Metric | 2025-12-31 | 2026-06-30 |
| --- | ---: | ---: |
| Borrowings/bonds subtotal | 2 | 2 |
| Debt ratio | 28 | 0 |
| Net margin | 2 | 0 |
| Operating cash flow / net income | 3 | 1 |

Annual values cannot fill latest-half-year gaps. Borrowings/bonds subtotal is
not complete interest-bearing debt. This refresh does not validate a trading
strategy or complete industry valuation models. No Excel publication this run.

The task's started_at and finished_at both read 2026-09-08 14:16:15.321271 UTC,
consistent with PostgreSQL transaction-time defaults; these timestamps are not
evidence of zero elapsed runtime. Do not derive runtime/RTO from that equality.
The latest snapshot's 4380 cross-source flags were all real booleans; the local
strict-boolean defense remains undeployed and its full suite passed 814 tests.
