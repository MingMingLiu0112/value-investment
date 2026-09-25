# M5 actual event replay handoff (2026-09-25)

This branch adds an offline, fail-closed replay for the 600519 actual event receipts. It verifies five half-year financial facts against archived PDF bytes and announcement metadata, builds a versioned fact artifact, derives a bounded recalculation plan, and projects the result into an M7 workbook candidate. No order, production database, scheduler, notification, or account action is performed.

The two actual receipts remain `STILL_NOT_READY`: `valuation_inputs` is missing, `model_executed=false`, and `new_valuation_result=null`. The workbook is a candidate, not the published WPS original or a trading recommendation. The current v5 candidate SHA-256 is `ff4a1412b41b313e347b9177207caab8a498a2bf04dd31742cfb1b2858fc460a`.

Verification in this isolated checkout: 22 targeted tests passed and 6 evidence-dependent tests skipped. Eight pre-existing outbox fixture failures were traced to Windows CRLF conversion; the fixture now retains LF bytes and those eight tests pass. The full repository suite is not green here (`2244 passed, 44 skipped, 208 failed, 87 errors`), principally because the isolated checkout lacks ignored `runtime` research evidence used by unrelated tests. Do not treat that run as production acceptance.

Follow-up binding audit: the result validator now checks exact active-event coverage and the status/blockers/task set implied by the frozen plan, even when a forged result is rehashed. Both the evaluator and M7 reader bind the facts artifact to the graph node's file-byte SHA and PDF evidence. An isolated replay regenerated two `STILL_NOT_READY` outcomes and a nine-review M7 read model; the replay files remain ignored under `runtime/`.

With `M5_ACTUAL_EVIDENCE_ROOT` pointing at the existing local evidence archive, the scoped M5/M7 regression is `34 passed` with no skips. This does not supersede the separate full-repository result above.

The M7 event sheet now exposes affected dependencies, explicit recalculation blockers, Event ID, human Decision Review requirement and the absence of a new valuation. A v5 candidate was rebuilt and read directly through openpyxl; WPS/Excel COM read-only acceptance passed. The canonical WPS workbook remained byte-identical at SHA-256 `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`. The exact `core-research-gates.yml` offline test command passed locally: `678 passed, 18 skipped` (with the existing local actual-evidence root available).

Next engineering gate: create a source-bound, versioned `valuation_inputs` artifact, rerun the model through the unified valuation interface, and verify that the new result is tied to the actual event and facts before changing any decision presentation. Keep the formal workbook unchanged until that gate is met.
