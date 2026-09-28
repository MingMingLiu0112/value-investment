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

`artifacts/current/artifact-registry-v2.json` is the current navigation registry.
It resolves the canonical workbook from local `WORKBOOK_PATH`, verifies its
SHA-256 against `config/current-trial-workbook.json`, and omits the personal
absolute path. The tracked root workbook is classified as a repository
reference snapshot, not the user-facing canonical workbook. The v1 registry is
preserved as a historical snapshot. Neither registry licenses moving or
deleting path-bound evidence.

## Current Human Evidence

Current append-only human evidence is under `docs/receipts/`. Existing receipt
bytes must not be rewritten to make a directory layout look cleaner.

## Relocation Rule

No legacy path-bound workbook, manifest, or receipt is moved into this folder
without a verifier proving that the old provenance check still succeeds.
