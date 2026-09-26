# Script and Tool Navigation

The supported current command-line surface is not inferred from this directory.
It is explicitly registered in:

```text
config/current-cli-entrypoints-v1.json
```

The remaining files are retained tools, not an implicit backlog:

| Location | Meaning |
| --- | --- |
| repository root of `scripts/` | legacy or not-yet-classified tooling; count is frozen by architecture guard |
| `scripts/current/` | reserved for future thin wrappers of registered current CLIs |
| `scripts/historical_validation/` | historical replay, PIT and case evidence producers |
| `scripts/research_cases/` | issuer-specific research and evidence tools |
| `scripts/diagnostics/` | read-only inventory and diagnostic tools |
| `scripts/migrations/` | one-off migration tools after explicit classification |
| `scripts/legacy/` | superseded tools retained only for provenance |

New scripts must be thin CLI wrappers. Business rules belong under
`src/value_investment_agent/`. Permanent boundary: `action=no_order`.
