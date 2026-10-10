# Repository Cleanup Report - 2026-10-10

Baseline: `2fb5a73a83e75f9c33ac714dd42f2700c3534a08`

Scope: repository structure consolidation, safe deletion, relocation and reference repair

Action: `no_order`

## Outcome

This batch performed real repository cleanup rather than only adding another
architecture plan. It removed one proven redundant tracked script, relocated 18
one-off tools into explicit ownership directories, registered 12 previously
unregistered current product helpers, rebuilt the script inventory, and added
architecture guards for relocations, secrets and oversized runtime payloads.

No investment rule, valuation formula, research gate, data-admission rule,
portfolio-position rule, canonical workbook or production service was changed.

```text
INCREMENTAL_REFACTOR_ONLY = true
BEHAVIOR_PRESERVING = true
FROZEN_PATHS_UNCHANGED = true
CORE_BEHAVIOR_CHANGED = false
CANONICAL_WORKBOOK_CHANGED = false
action = no_order
```

## Before / After Metrics

`HEAD` is the pre-cleanup commit. `WORKTREE` includes the staged and unstaged
cleanup batch but excludes pre-existing D2 working documents.

| Metric | HEAD | Current worktree | Change |
| --- | ---: | ---: | ---: |
| Git-tracked files | 1986 | 1985 | -1 |
| Files tracked under `scripts/` | 654 | 653 | -1 |
| Files at `scripts/` root | 582 | 563 | -19 |
| Python modules at package root | 199 | 199 | 0 |
| Files tracked under `docs/` | 272 | 272 | 0 |
| Files tracked under `tests/` | 573 | 573 | 0 |
| Local root `.xlsx` / manifest files | 0 / 0 | 0 / 0 | 0 |

The root script reduction consists of 18 byte-identical moves and one verified
deletion. The package root did not grow.

## Actual File Operations

### Deleted

`scripts/deploy_institution_v9.py`

Evidence:

- superseded by `deploy_institution_v10.py`;
- not present in the active CLI v1 or v2 registries;
- no current import, subprocess, CI, receipt or documentation consumer;
- SHA-256 `dcbda23f2d82728c062de0055a0f6ae6e780fece0bd095419ba97c1f612c2754`;
- Git history still contains the old bytes.

### Relocated

Migration and installer tools:

```text
scripts/install_backup_space_release.py       -> scripts/migrations/
scripts/install_debt_scope_gate.py            -> scripts/migrations/
scripts/install_parser_release.py             -> scripts/migrations/
scripts/install_quote_session_release.py      -> scripts/migrations/
scripts/install_single_cash_adapter.py        -> scripts/migrations/
scripts/install_tracking_lock_release.py      -> scripts/migrations/
scripts/install_tracking_schema.py            -> scripts/migrations/
scripts/migrate_maturity_sources.py           -> scripts/migrations/
scripts/migrate_provider_scope.py             -> scripts/migrations/
scripts/migrate_reviewed_candidates.py        -> scripts/migrations/
scripts/migrate_roe_scope.py                  -> scripts/migrations/
scripts/migrate_tied_inputs.py                -> scripts/migrations/
scripts/migrate_workspace.ps1                 -> scripts/migrations/
scripts/deploy_institution_v10.py             -> scripts/migrations/
scripts/tied_input_resolution.py              -> scripts/migrations/
```

Operations and diagnostics:

```text
scripts/server_reclaim_build_cache.py -> scripts/operations/
scripts/report_recommendations.py     -> scripts/diagnostics/
scripts/sync_workbook_low_memory.py   -> scripts/legacy/
```

The machine-readable old path, new path and SHA-256 proof is stored in
`docs/architecture/script-relocations-20261010.json`. The architecture test
checks every moved target for byte identity and every old path for absence.

### Duplicate and Compatibility Handling

- `deploy_institution_v9.py` was removed as a superseded duplicate.
- No second implementation was added for any moved tool.
- Eleven pre-existing compatibility shims were registered in addition to the
  seven already known; the registry now contains 18 forward-only shims.
- No compatibility shim was removed because its old import path may still be
  consumed by external or historical tooling.

### Preserved Without Relocation

- all nine paths and SHA-256 values in
  `config/architecture-frozen-paths-v1.json`;
- the canonical WPS workbook resolved through `WORKBOOK_PATH`;
- receipt-, manifest- and runtime-pointer-bound artifacts;
- historical research, PIT, replay, human-review and evidence files;
- private portfolio inputs, backups and production database assets.

The frozen-path verifier completed with 9/9 exact hash matches. The canonical
workbook hash remained
`5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`.

## Local Generated-Data Cleanup

The following ignored/reproducible local data was removed:

- `.tmp/oss`;
- 59 `.pytest_cache` / `.pytest-*` directories;
- 38 `__pycache__` directories under source and tests.

The `.tmp` root, backups, restore evidence, `.m1-postgres-venv`, `runtime/`,
`scratch/` and other unresolved local assets were deliberately retained. No
batch `git clean` command was used.

## Actual Directory Shape

The repository now has these active classified script areas:

```text
scripts/
  current/                 current thin CLI wrappers
  cases/                   issuer/case adapters
  research_cases/          issuer research and evidence tools
  historical_validation/   PIT, replay and historical evidence tools
  diagnostics/             read-only audits and diagnostics
  migrations/              bounded one-off migrations/installers
  operations/              server/runtime operations
  legacy/                  superseded tools retained for provenance
```

`config/current-cli-entrypoints-v2.json` is the authoritative current CLI
registry. It contains 20 product CLIs, 42 engineering CLIs and 12 internal
product helpers; all 43 v1 paths remain compatible.

## Regression Evidence

```text
focused cleanup suite: 60 passed
CLI registry + architecture guard: 37 passed
targeted workbook/architecture regression: 109 passed
offline CI regression: 1614 passed, 32 skipped
synthetic M4 rehearsal: 3 passed, 2 skipped
clean-checkout offline regression: 1597 passed, 49 skipped
clean-checkout synthetic M4 rehearsal: 3 passed, 2 skipped
frozen paths: 9/9 exact SHA-256 matches
canonical workbook: hash unchanged
```

The CI workflow now explicitly runs `tests/test_daily_trade_assistant.py`.
Architecture checks also reject new tracked secrets, forbidden runtime paths
and tracked files larger than 32 MiB.

## GitHub Delivery

Status is recorded after the commit and push:

```text
HEAD_BEFORE_BATCH = 2fb5a73a83e75f9c33ac714dd42f2700c3534a08
IMPLEMENTATION_COMMIT_1 = 245163d
IMPLEMENTATION_COMMIT_2 = 878ff3e
LOCAL_REMOTE_SYNC = pending
CI_RUN = pending
```

## Open Debt

- Files at `scripts/` root still contain legacy research orchestration; they
  remain classified and frozen against growth rather than mass-moved.
- Root historical artifacts must not be physically moved until a
  content-addressed relocation verifier preserves old path/hash receipts.
- `.tmp`, `scratch/`, `.m1-postgres-venv` and local backup evidence remain
  unresolved for deletion and were retained.
- `docs/` root remains large; only proven historical documents should be
  archived in later batches.
- No production scheduler, migration, notification or private portfolio data
  was touched.

## Permanent Boundaries

```text
action = no_order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Margin of Safety != Position Size
Current Price != Intrinsic Value
Historical Return != Future Return
Backtest != Shadow
Good Backtest != Buy Signal
```
