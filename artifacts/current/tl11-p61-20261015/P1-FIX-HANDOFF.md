# P6.1 Independent Review P1 Corrections

Both P1 findings were valid and are fixed. This supplements ROOT-HANDOFF.md;
the earlier report and logs are preserved, not rewritten as successful evidence.

## Historical Replay Versus Current B1

quote_snapshot_from_bundle_file now preserves its historical replay semantics
by default. Existing frozen bundle evidence, descriptor hashes and publication
verification remain reproducible without changing any frozen input bytes.

The converter exposes require_current_b1=False; current quote_bridge admission
explicitly supplies True, requiring both providers to have been acquired on the
quote session after close. Current price-case B1 validation stays strict as well.
The same next-morning archive can therefore reproduce its historical verified
close while being rejected by the current formal admission path. This is not
a waiver of current B1 and does not confer current research/trading eligibility.

## Refresh Recovery

After acquisition, SAFE_REFRESH invokes the actual packet builder again with
--no-publish. Core blocking is recomputed from that invocation's exit code,
parseable output and source_bindings_verified. Latest-session input readiness
is checked separately. Publication is possible only when both checks pass.
The final publishing builder also retains its existing own verification.

Isolated actual PS7 entry tests cover initial core failure followed by successful
revalidation, persistent identity conflict/unavailable chain, newly lost source
integrity, unreadable post-refresh output, partial input and complete success.
They assert two builder invocations when publication is refused and three when
post-refresh verification permits publication.

## Validation

tests-p1-fixes.log: **126 passed in 49.68s**, including all three previous Core
failures (no skips):

- tests/test_workbook_publication.py::test_actual_published_v5_registration_replays_typed_snapshot_and_native_exports
- tests/test_research_review_packet.py::test_retained_real_and_legacy_workbenches_keep_exact_consumption[600741]
- tests/test_research_review_packet.py::test_retained_real_and_legacy_workbenches_keep_exact_consumption[600887]

The same run covers quote conversion/current bridge, B1 price cases, refresh
readiness, actual isolated Windows entry failures/recovery, daily selection,
bounded transport, registry, public packet identity and snapshot publication.
Scoped git diff --check passed.

This correction made no public pointer writes, no main-worktree entry run,
no private/WPS/frontend/app.py/Goal changes, and no commit/push. Only isolated
test projects publish their own temporary pointers. Root still owns the final
public pointer/archive operation and integrated startup/browser acceptance.
