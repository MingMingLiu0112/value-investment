# M5 actual event replay handoff (2026-09-25)

This branch adds an offline, fail-closed replay for the 600519 actual event receipts. It verifies five half-year financial facts against archived PDF bytes and announcement metadata, builds a versioned fact artifact, derives a bounded recalculation plan, and projects the result into an M7 workbook candidate. No order, production database, scheduler, notification, or account action is performed.

The two actual receipts remain `STILL_NOT_READY`: `valuation_inputs` is missing, `model_executed=false`, and `new_valuation_result=null`. The workbook is a candidate, not the published WPS original or a trading recommendation. The candidate SHA-256 is `0278e9528580e18122d8f72ff80202699d9a73bc13313ad43d1e0cff57fa316e`.

Verification in this isolated checkout: 22 targeted tests passed and 6 evidence-dependent tests skipped. Eight pre-existing outbox fixture failures were traced to Windows CRLF conversion; the fixture now retains LF bytes and those eight tests pass. The full repository suite is not green here (`2244 passed, 44 skipped, 208 failed, 87 errors`), principally because the isolated checkout lacks ignored `runtime` research evidence used by unrelated tests. Do not treat that run as production acceptance.

Follow-up binding audit: the result validator now checks exact active-event coverage and the status/blockers/task set implied by the frozen plan, even when a forged result is rehashed. Both the evaluator and M7 reader bind the facts artifact to the graph node's file-byte SHA and PDF evidence. An isolated replay regenerated two `STILL_NOT_READY` outcomes and a nine-review M7 read model; the replay files remain ignored under `runtime/`.

With `M5_ACTUAL_EVIDENCE_ROOT` pointing at the existing local evidence archive, the scoped M5/M7 regression is `34 passed` with no skips. This does not supersede the separate full-repository result above.

Next engineering gate: create a source-bound, versioned `valuation_inputs` artifact, rerun the model through the unified valuation interface, and verify that the new result is tied to the actual event and facts before changing any decision presentation. Keep the formal workbook unchanged until that gate is met.
