# Archived Artifacts

This directory is an index for historical artifacts that have a clear
successor or belong to a frozen stage.

The first bounded payload archive is in legacy-root-20260925/. It contains
six superseded root workbooks whose bytes, original paths, and SHA-256 values
are recorded in elocation-record.json. No receipt-bound or current-pointer
artifact was moved.

The following classes are logically archived even while their bytes remain at
legacy root or `runtime/` paths:

- superseded candidate workbooks and their manifests;
- stage-specific WPS verification receipts;
- one-off migration and research probes with no current entry point;
- historical acceptance files that still prove a past decision.

They were not moved because current manifests, receipts, tests, documentation,
or absolute paths can bind them. Git-tracked files have Git history, but ignored
`runtime/` evidence does not; both must be copied into the encrypted local
evidence archive before any future physical cleanup.
