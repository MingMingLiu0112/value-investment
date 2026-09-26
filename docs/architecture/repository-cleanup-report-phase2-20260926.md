# Repository Cleanup Report - Phase 2

Date: 2026-09-26  
Baseline: `aed0e963c6e0a9a3bf83a2939fa30840514f51e9`  
Scope: `ARCHITECTURE-CONSOLIDATION-AND-REPOSITORY-CLEANUP / PHASE-2`  
Action: `no_order`

## Outcome

Phase 2 completed the safe structure-reduction batches. It did not perform a
mass move, did not change valuation, decision, portfolio or materiality logic,
and did not move any provenance-bound root artifact.

```text
TARGET_ARCHITECTURE_DEFINED = true
NEW_CODE_PLACEMENT_RULES = ACTIVE
ROOT_ARTIFACT_CLUTTER = LOGICALLY_REDUCED
ROOT_ARTIFACT_PHYSICAL_BATCH_2 = NO_SAFE_MOVE
DOCS_CURRENT_ENTRY = FUNCTIONAL
DOCS_CURRENT_VS_ARCHIVE = OPERATIONALLY_CLEAR
SCRIPT_INVENTORY = COMPLETE
CURRENT_SUPPORTED_CLIS = 43
SCRIPT_BUSINESS_LOGIC = PARTIALLY_REDUCED
PRESENTATION_DIRECTORY = ACTIVE
OPERATIONS_DIRECTORY = ACTIVE
INFRASTRUCTURE_DIRECTORY = ACTIVE
COMPANY_SPECIFIC_TOOLING = CLASSIFIED
COMPATIBILITY_SHIMS = REGISTERED
NEW_CODE_ROOT_GROWTH = BLOCKED
CORE_BEHAVIOR_CHANGED = false
action = no_order
```

## Before / After Metrics

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| Root Python scripts under `scripts/` | 548 | 528 | -20 |
| Total classified script/tool files | 602 | 604 | +2 reusable diagnostic CLIs |
| Root documents under `docs/` | 187 | 175 | -12 archived |
| Root `src/value_investment_agent/*.py` modules | 199 | 199 | no growth; 7 implementations moved behind shims |
| Tracked root `.xlsx` artifacts | 28 | 28 | 0 physical moves; 58 artifacts logically registered |
| Local root `.xlsx` artifacts | 29 | 29 | unchanged; no provenance-safe move |
| Registered compatibility shims | 0 | 7 | forward-only old paths |

Docs root count excludes the populated `docs/current/`, `docs/architecture/`,
`docs/archive/` and `docs/receipts/` trees.

## Script Classification

`docs/architecture/script-inventory-v1.json` classifies every `.py`, `.ps1`,
`.mjs` and `.sql` tool file under `scripts/`:

| Category | Count |
| --- | ---: |
| `CURRENT_OPERATIONAL_CLI` | 12 |
| `CURRENT_PRODUCT_CLI` | 7 |
| `CURRENT_RESEARCH_CLI` | 174 |
| `HISTORICAL_VALIDATION_TOOL` | 57 |
| `COMPANY_RESEARCH_CASE_TOOL` | 211 |
| `MIGRATION_TOOL` | 13 |
| `DIAGNOSTIC_TOOL` | 130 |
| `SUPERSEDED` | 0 |
| `DELETE_CANDIDATE` | 0 |
| **Total** | **604** |

The supported entrypoint allowlist is
`config/current-cli-entrypoints-v1.json` with 43 entries. The frozen admission
script remains at its original path with SHA-256
`6f8a55ea6fbcd4f1db37e614b9cfc7e05a5084d927bee1810b63e39afb022e60`.

Twenty no-consumer scripts were physically moved into `scripts/diagnostics/`,
`scripts/historical_validation/` and `scripts/research_cases/`. Two reusable
diagnostic CLIs were added for complete script inventory and logical artifact
registration.

## Layer Boundaries

The first physical batches are active:

```text
presentation/
  excel/workbook_compat.py
  excel/workbook_frontdoor.py
  read_models/research_read_model.py

operations/
  authorization/m6_authorization_artifacts.py

infrastructure/
  filings/pdf_text.py
  evidence/evidence_tiering.py
  backup/backup_snapshot.py
```

Current layer module counts are:

```text
domain          = 10
application     = 10
infrastructure  = 7
presentation    = 6
operations      = 3
```

Every moved implementation has an explicit forwarding shim listed in
`docs/architecture/compatibility-shims-v1.json`. Shim files contain no copied
business logic. Frozen `historical_validation.py` was not moved or modified.

## Artifacts and Docs

The second physical root-artifact batch is deliberately empty. The relocation
audit found all 58 root artifacts bound by at least one of canonical status,
current pointer, manifest, receipt, static consumer, or untracked runtime
evidence. `artifacts/current/artifact-registry-v1.json` therefore provides a
logical registry with path, SHA-256, status, successor, reason kept and
relocation blocker.

Twelve legacy financing/debt notes moved to
`docs/archive/legacy-financing-debt-20260926/` with a relocation record and
byte-for-byte SHA-256 checks. `docs/current/README.md` now points directly to
the current goal, execution status, M4 input, M6 authorization, M7 trial,
historical-validation status and architecture status.

No tracked file was deleted. Local cleanup removed 311 reproducible pytest
temporary directories (about 186 MiB); no `runtime/`, backup, receipt or user
artifact was removed.

## Verification

```text
targeted layer tests: 63 passed
targeted workbook/backup tests: 53 passed, 1 skipped
targeted read-model/architecture tests: 54 passed
architecture-boundary regression: 26 passed
full offline suite: 2865 passed, 30 skipped, 18 warnings
local Core Research Gate test list: 979 passed, 22 skipped
CORE_BEHAVIOR_CHANGED = false
action = no_order
```

Remote Core Research Gates for pushed commit `908444b`: **success**.
Run: `https://github.com/MingMingLiu0112/value-investment/actions/runs/36203428899`.

## Open Debt

- Root artifact physical relocation needs an approved content-addressed
  relocation verifier that preserves old path/hash receipts.
- Seven compatibility shims remain and are intentionally temporary.
- 528 Python scripts still remain at the `scripts/` root; classification is
  complete, but large current research scripts still contain orchestration that
  should move into application services incrementally.
- `ADV-P1-003` and `ADV-P1-004` remain open. No Shadow or production action has
  been started.
- The 175 flat documents left under `docs/` require further selective archiving;
  they were not mass-moved because the governance report and links still bind
  them.

## Permanent Semantics

```text
action = no_order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Good Backtest != Buy Signal
Backtest != M6 Shadow
```
