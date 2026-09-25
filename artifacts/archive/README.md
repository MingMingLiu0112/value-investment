# Archived Artifacts

This directory is an index for historical artifacts that have a clear
successor or belong to a frozen stage. It is intentionally empty of payload
during the first cleanup pass.

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
