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

## Verification

```text
historical validation receipt audit: AUDIT_OK
classification: NOT_PIT_SAFE
admission_status: NOT_ADMITTED
walk_forward_status: NOT_RUN
action: no_order
targeted tests: 18 passed
full offline suite: 2796 passed, 30 skipped, 18 warnings
```

The final architecture batch must also pass the repository-wide offline test
suite and GitHub Core Research Gates before this report is accepted.

## Next Safe Batch

The next useful cleanup is a machine-readable hash-consumer and relocation
inventory. It should answer which consumer reads each path/hash and which files
can never move. Only after that verifier exists should any physical artifact
move begin.
