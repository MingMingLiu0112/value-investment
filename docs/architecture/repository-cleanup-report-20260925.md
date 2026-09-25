# Repository Cleanup Report - 2026-09-25

This report covers the first bounded pass of
`ARCHITECTURE-CONSOLIDATION-AND-REPOSITORY-CLEANUP`. It is not a new
milestone and does not change business behavior.

## Baseline

Start baseline: `5eacfb9`.

Observed inventory at the start of review:

```text
src/value_investment_agent Python modules: about 210
tracked scripts: 600
test Python files: 456
tracked docs: 217
root *.xlsx: 35
root manifests/receipts: 22
```

The repository had no missing static imports. Three independent read-only
audits covered architecture, redundancy, and regression risk. No payload was
deleted, moved, renamed, or re-signed.

## Changes Applied

### Application Boundary

The historical-validation receipt audit logic moved to:

```text
src/value_investment_agent/application/historical_validation/receipt_audit.py
```

`scripts/audit_historical_validation_receipt.py` is now a thin CLI. The result
schema, errors, hashes, and `action=no_order` behavior are unchanged.

### First Safe Domain Boundary

The pure blocker-classification rules moved to:

```text
src/value_investment_agent/domain/research/gap_classification.py
```

The old `src/value_investment_agent/gap_classification.py` path is a
`DEPRECATED_COMPATIBILITY_SHIM`. Existing imports and behavior remain stable;
the new domain module has no I/O or presentation dependency.

The pure `ResearchCase` contract then moved to:

```text
src/value_investment_agent/domain/research/research_case.py
```

The old path is a forwarding shim. No source-path or SHA consumer was found;
the contract itself and all existing imports remain unchanged.

The cohesive research-contract group then moved together:

```text
src/value_investment_agent/domain/research/research_run_contract.py
src/value_investment_agent/domain/research/human_research_approval.py
src/value_investment_agent/domain/research/research_gate.py
```

These modules remain pure domain code. Their same-directory relative imports
preserve the original dependency graph, and all legacy root paths forward
without duplicating behavior.

### Provenance Rollback

The first attempted domain migration moved
`src/value_investment_agent/historical_validation.py` behind a compatibility
shim. The frozen historical-validation input manifest binds that exact path and
SHA-256, so the old receipt failed verification.

The migration was rolled back. The frozen module was restored byte-for-byte and
now has an architecture regression test. Its current hash is:

```text
806d890817611000a588c9ee76ee00cc18a2529d5e1ee9769c092cc00452c5ba
```

Any new historical-validation behavior must create a new versioned
admission/receipt chain instead of editing or moving this file.

### Navigation And Guardrails

The repository now has:

```text
artifacts/current/README.md
artifacts/archive/README.md
docs/current/README.md
docs/archive/README.md
```

Architecture tests prevent new root workbook growth, verify the frozen
historical-validation bytes, verify shim identity, and check dependency
direction for new domain and application modules.

## Deliberate Non-Actions

No root workbook or manifest was moved. The redundancy audit found that current
pointers, tests, documentation, or immutable receipts reference the existing
paths. Moving them would trade cognitive clutter for broken provenance.

No script was deleted solely because it lacked a direct text reference. Several
scripts are reached through `runpy`, delayed imports, tests, or historical
receipt replay chains.

No production database, server, scheduler, Excel workbook, or runtime receipt
was changed.

## Known Risks To Carry Forward

```text
M6 CI evidence is bound to repository identity, workflow text, step names and
  an expiring GitHub artifact.
M5 historical manifests contain absolute Windows paths bound by later hashes.
M7 current evidence lives under ignored runtime/ and needs the local encrypted
  evidence archive.
core.autocrlf=true can change bytes outside explicitly frozen paths.
setup_private_portfolio.py still assumes an editable installation or suitable
  PYTHONPATH when run directly.
```

These are engineering risks, not reasons to stop the current M6/M7 or
historical-validation workstreams.

## First Physical Archive Batch

Six superseded root workbooks with documentation-only references were moved
byte-for-byte to rtifacts/archive/legacy-root-20260925/. Their original
paths and SHA-256 values are recorded in elocation-record.json. No current
pointer, code consumer, test consumer, or sibling manifest binding was found
by the relocation audit before the move.

Root workbook count changed from 35 to 29. The canonical workbook, current
M7 pointer target, and all receipt-bound artifacts remain in place.

## Verification

```text
historical validation receipt audit: AUDIT_OK
classification: NOT_PIT_SAFE
admission_status: NOT_ADMITTED
walk_forward_status: NOT_RUN
action: no_order
targeted tests: 18 passed
full offline suite: 2796 passed, 30 skipped, 18 warnings
clean-checkout targeted CI subset: 24 passed, 1 skipped
GitHub Core Research Gates: success
```

## Next Safe Batch

The next useful cleanup is a machine-readable hash-consumer and relocation
inventory. It should answer which consumer reads each path/hash and which files
can never move. Only after that verifier exists should any physical artifact
move begin.

## Second Pass: Relocation Inventory

The read-only relocation inventory is now implemented in
src/value_investment_agent/application/architecture/artifact_relocation.py
and exposed by the thin CLI scripts/audit_artifact_relocation.py. It records
each root workbook SHA-256, tracked status, and every code, configuration,
pointer, documentation, or JSON consumer found in the bounded reference scope.

The inventory is intentionally conservative: JSON consumers are marked as
possible hash/receipt bindings and cannot be moved until a relocation verifier
proves the old path and digest still resolve. Canonical workbooks and current
pointers are always KEEP. A documentation-only reference can become an
archive candidate, but only after those references are updated and the
targeted regression suite passes.

This pass does not alter any workbook, manifest, receipt, runtime pointer,
database, or scheduled task.
