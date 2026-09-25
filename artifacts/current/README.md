# Current Artifacts

This directory is an index, not a second source of truth. A file is current
only when a pointer or authoritative document names it.

## User-Facing Workbook

The formal Excel workbook remains at the user's configured `WORKBOOK_PATH`.
Repository code must not replace or silently overwrite that file.

## M7 Read-Only Trial

The single current trial pointer is:

```text
config/current-trial-workbook.json
```

It resolves to the reviewed M7 candidate and binds its SHA-256. The candidate
currently lives under ignored `runtime/`; it must be included in local evidence
archives even though it is not a Git-tracked payload.

## Logical Artifact Registry

`artifacts/current/artifact-registry-v1.json` lists every retained root
artifact, its hash, current/historical interpretation, successor pointer and
the provenance reason it remains in place. It is a navigation registry, not a
license to move or delete path-bound evidence.

## Current Human Evidence

Current append-only human evidence is under `docs/receipts/`. Existing receipt
bytes must not be rewritten to make a directory layout look cleaner.

## Relocation Rule

No legacy path-bound workbook, manifest, or receipt is moved into this folder
without a verifier proving that the old provenance check still succeeds.
