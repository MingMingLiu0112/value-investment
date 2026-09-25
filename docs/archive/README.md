# Documentation Archive

This directory contains immutable historical context and compatibility
snapshots. Archived material is not an active task queue.

The existing goal-consolidation manifest is:

```text
docs/archive/goal-consolidation-20260922/manifest.json
```

The first archive pass for reference-free historical research material is:

```text
docs/archive/legacy-research-20260925/relocation-record.json
```

Many earlier stage, progress, candidate, parser, and research documents remain
at their original `docs/` paths because they are referenced by current
documents, tests, manifests, or receipts. They are logically archived but were
not physically moved in the 2026-09-25 cleanup.

Before moving any historical document, verify:

1. no active document links to the old path;
2. no test or CLI uses the path;
3. no manifest or receipt binds the path or bytes;
4. the content remains recoverable from Git or the encrypted evidence archive.
