# Closure Runtime and Recovery (W2, 2026-10-17)

`action=no_order`. This file is the current operating note. The
machine-readable source is
`artifacts/current/closure-restore-drill-latest.json`.

## Current public publication

- Publication: `pub-cb73f09b88c4150ecf0d`.
- Packet:
  `runtime/daily-public-packet/daily-public-packet-pub-cb73f09b88c4150ecf0d.json`,
  SHA-256 `f0efba54ff69ccc774eba6a9ce4ec43deea2b541488af934cce11606c31b6dff`.
- Content SHA-256 `b122238fec7e2703342ce83244fd9feab82074a2ac33df917e51175416321d1a`.
- Engine `daily-public-packet-engine-v19`.
- Research version `canonical-reviewed-research-20261012T113935Z-362d7928`.
- Research cutoff 2026-10-11; verified quote session 2026-10-16.
- Formal admissions: 0.

The earlier `pub-5f803e...` and `pub-6167d0...` records are historical
provenance, not current pointers. Pointer changes are data updates; they are
reported separately from source-code identity by `/api/v1/runtime-identity`.

## Current research pointers

| Artifact | Pointer | Current evidence |
| --- | --- | --- |
| Research funnel | `config/current-research-funnel-audit.json` | W6 v2 manifest `18aa508a...183e` |
| Hotspot structure validation | `config/current-hotspot-structure-validation.json` | W7 v3 manifest `3b8e10f8...873b` |
| Company research draft | `config/current-research-drafts.json` | 000333 public draft `6ddde5fd...a907` |

These pointers are included in the encrypted recovery package together with
their manifests, reports, validation output and research draft.

## Restore drill

Command:

```powershell
python scripts/current/run_closure_restore_drill.py --receipt artifacts/current/closure-restore-drill-latest.json
```

Latest isolated drill:

- Drill root `.tmp/closure-restore-drill/20261017T135312Z`.
- 24 source files copied; no missing source; 11 research files.
- 28 restored files verified with zero mismatches.
- Publication id and packet hash match the current pointer.
- Canonical workbook is present and matches its pointer.
- A deliberately corrupted encrypted copy is rejected.
- Package SHA-256
  `f5551f5d385430f602a2de97383a56c77d19c3a4a3cec6dcff54165448dd8f7d`.
- Package manifest SHA-256
  `368b980f88ceb8be0d2f3f49d1bfd610cfcee87b3b3c8aa906c4adda3e9ffbb1`.

```text
RESTORE_DRILL_PASS=PASS
OFF_MACHINE_BACKUP_READY=PASS
REAL_OFF_MACHINE_COPY_CONFIRMED=NOT_CONFIRMED
```

The test key remains only under the ignored drill directory and is never
committed beside a portable package. The latest drill is a local isolated
rehearsal; it does not claim that an off-machine copy was actually made.

## Data assets and boundaries

| Asset | Git tracked | Recovery treatment |
| --- | --- | --- |
| Public packet, receipt and bound source files | no | Included in encrypted drill package |
| Current W6/W7/draft pointers and outputs | yes where under `artifacts/current`; source runtime files remain local | Pointer and hash-bound output included in drill |
| Current config pointers | yes | Included and hash-checked |
| Canonical Excel | no | Included as a release file; never rewritten by the drill |
| Private portfolio journal | no | Excluded; requires separate encrypted user-controlled backup |
| Keys and `.env` | no | Excluded from package |
| PostgreSQL | no | Server backup remains a separate production operation |

The remaining recovery boundary is real off-machine placement and the
server-side PostgreSQL backup/restore rehearsal. Neither is replaced by this
local encrypted drill.

