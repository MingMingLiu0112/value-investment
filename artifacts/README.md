# Artifact Layout

This directory is the future home for checked-in product artifacts. The
2026-09-25 cleanup deliberately did not move legacy artifacts whose paths or
bytes are bound by manifests, receipts, tests, documentation, or current
pointers.

```text
artifacts/
  current/   indexes and, later, safely relocatable current artifacts
  archive/   indexes and, later, safely relocatable historical artifacts
```

Until a relocation verifier can preserve old provenance, the authoritative
files may remain at their legacy repository paths or under ignored `runtime/`.
The indexes in this tree describe classification without rewriting history.

Rules for new work:

- Do not add new root-level `.xlsx`, candidate workbooks, manifests, or receipts.
- Check current pointers before creating a new artifact version.
- Treat any path plus SHA-256 binding as immutable.
- Keep `action=no_order`; an artifact is research evidence, not an order.
