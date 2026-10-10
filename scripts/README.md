# Script and Tool Navigation

The supported current command-line surface is not inferred from this directory.
It is explicitly registered in:

```text
config/current-cli-entrypoints-v2.json
```

`config/current-cli-entrypoints-v1.json` remains the 43-path compatibility
baseline. The v2 registry preserves every v1 path, separates 20 product and 42
engineering CLIs, and declares 12 internal product helpers. Only the two
supported layers are user-facing commands.

The remaining files are retained tools, not an implicit backlog:

| Location | Meaning |
| --- | --- |
| repository root of `scripts/` | legacy or not-yet-classified tooling; count is frozen by architecture guard |
| `scripts/current/` | reserved for future thin wrappers of registered current CLIs |
| `scripts/cases/` | issuer/case-specific research adapters |
| `scripts/historical_validation/` | historical replay, PIT and case evidence producers |
| `scripts/research_cases/` | issuer-specific research and evidence tools |
| `scripts/diagnostics/` | read-only inventory and diagnostic tools |
| `scripts/migrations/` | one-off migration tools after explicit classification |
| `scripts/operations/` | bounded server/runtime operations tools |
| `scripts/legacy/` | superseded tools retained only for provenance |

New scripts must be thin CLI wrappers. Business rules belong under
`src/value_investment_agent/`. Permanent boundary: `action=no_order`.

The 2026-10-10 relocation/delete proof is
`docs/architecture/script-relocations-20261010.json`; it records old/new paths
and SHA-256 values for every moved file and the consumer proof for the one
deleted duplicate. The architecture guard checks that old paths stay absent and
that moved files remain byte-identical.
