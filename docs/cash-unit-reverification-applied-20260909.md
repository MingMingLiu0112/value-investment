# Nine cash observations reverified

2026-09-09. Used an isolated staged candidate_review module; production package
files were not replaced. Reverification script keeps the consolidated-scope
secondary observation and requires a scaled trigger to share its source_id,
field cash and annual period. The trigger must equal the CNY amount exactly;
ambiguous latest timestamps are rejected. Latest-source disagreement still
blocks promotion, and each original PDF hash and parser candidate are checked.

Initial dry run also found one operating-cash-flow row; it was NOT committed.
Added --cash-only and reran: nine cash rows, zero skipped, applied=false,
rollback_verified=true. Rollback readback compared original fact rows and
confirmed the rehearsal task row absent. Subsequent --apply --cash-only run
committed nine rows. Independent database readback confirmed all nine latest
cash facts verified in CNY with original trigger amount/unit and previous IDs.

Run ID: 8df6c159-4558-4ea1-90b0-184ed2cdad7c.
Symbols: 000425, 001233, 001386, 002011, 002043, 002444, 002727, 300815, 301376.

Existing records were retained. No new original downloads, service restarts,
trade-rule changes or Excel publication occurred. Shared-lock execution was
limited to 0.5 CPU, 384 MiB memory and 512 MiB memory-plus-swap.

Remaining: downstream refresh and canonical workbook sync; production recurring
collection/reverification integration so equivalent pending observations do not
repeatedly shadow verified facts. The staged comparator alone is not a complete
production fix. This data repair does not approve full debt scope, valuation or
historical strategy performance.
