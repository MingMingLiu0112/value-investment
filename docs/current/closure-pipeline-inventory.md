# Closure Pipeline Inventory (W1, 2026-10-17)

`action=no_order`. Evidence: `artifacts/current/closure-baseline.json`,
`config/decision-writers-registry-v1.json`, and the live audit receipt
`.tmp/decision-writers-audit.json` (10 pipelines, 4 observed Windows tasks,
0 conflicts).

## 1. Authority model

One authoritative writer per decision-state scope. Data collection may happen
in several places; publishing the *current* authoritative state may not.

| Scope | Authoritative writer | Current consumer |
| --- | --- | --- |
| `public_daily_observation` | `daily-public-packet` (`daily-public-packet-engine-v19`) | Web workbench |
| `formal_research_version` | `canonical-reviewed-research` | Web + Excel snapshot |
| `valuation_review` | `signed-research-review` (authenticated reviewer + pinned trust root) | Web (fail-closed while no key is pinned) |
| `current_price_policy` | `daily-public-packet` (dated price-condition observations) | Web |
| `private_ledger` | `private-portfolio-ledger` | Locked by `BLOCKED_PRIVATE_INPUT` |
| `excel_publication` | `canonical-excel-publication` (frozen 2026-10-01 snapshot) | Excel |

## 2. Inventory and disposition

| Pipeline | Entry | Observed state | Writes | Disposition |
| --- | --- | --- | --- | --- |
| Daily public packet | `scripts/current/run_daily_workbench.ps1` | current `pub-cb73f09b88c4150ecf0d`; quote 2026-10-16 | public observation, price policy | **KEEP_READONLY** (authoritative) |
| Canonical reviewed research | `config/current-daily-public-snapshot.json` | research 2026-10-11 | formal research version | **KEEP_READONLY** (authoritative) |
| Signed research review | `application/product/research_reviews.py` | no pinned reviewer key | valuation review | **KEEP_READONLY** (fail-closed until a real reviewer is registered) |
| Private ledger | `application/portfolio/private_portfolio_service.py` | locked, no holdings | private ledger | **KEEP_READONLY** (requires the local owner) |
| Canonical Excel | `config/current-trial-workbook.json` + WPS file | frozen 2026-10-01 | Excel publication | **KEEP_READONLY** (no live writes) |
| `ValueInvestmentAgent-DailyUpdate` | `scripts/run_moutai_b1_after_close.ps1` | Ready, exit 0, last 2026-10-16 17:05 | legacy 600519 B1 archive | **RETIRE_PENDING_APPROVAL** |
| `ValueInvestmentAgent-MoutaiB1ExcelPublish` | `scripts/run_moutai_b1_excel_publish.ps1` | Ready, **exit 1**, last 2026-10-16 17:30 | legacy Excel attempt | **RETIRE_PENDING_APPROVAL** |
| `ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh` | `scripts/run_moutai_preclose_capital_refresh.ps1` | Ready, exit 0, last 2026-10-16 14:45 | legacy capital archive | **RETIRE_PENDING_APPROVAL** |
| `ValueInvestmentAgent-MoutaiPostclosePolicyStage` | `scripts/run_moutai_postclose_p1_refresh.ps1` | Disabled | legacy policy archive | **ARCHIVE** |
| Aliyun DB research pipeline | `refresh-valuations`, `collect-filings`, `enrich-financials` | ~50 runs/48h, last 2026-10-17 17:30 | observation tables (`valuation_results` 888 rows, 0 weight) | **KEEP_READONLY** (observation only) |
| W6 research funnel | `scripts/current/audit_research_funnel.py` | W6 v2 current pointer | research coverage audit only | **KEEP_READONLY** (no eligibility) |
| W7 structure validation | `scripts/current/build_hotspot_structure_validation.py` | W7 v3 current pointer | retained structure evidence | **KEEP_READONLY** (strategy `NOT_PROVEN`) |

All legacy writers declare `effective_authority=false` and
`consumed_by_current_product=false`, so they cannot satisfy a current decision
gate even while the user has not yet authorized disabling the Windows tasks.

## 3. Enforcement

- `src/value_investment_agent/operations/decision_writer_registry.py`
  validates the registry: one effective writer per scope, declared recovery for
  every authority, no observer marked as a current consumer, and every observed
  `ValueInvestmentAgent-*` task declared.
- `scripts/current/audit_decision_writers.py` is a thin read-only CLI. It
  returns exit 1 on any conflict.
- Live run: `status=PASS`, `errors=[]`, 10 pipelines, 4 observed tasks.
- Negative tests: duplicate authority, undeclared task, observer-consumed
  conflict, unknown authority scope (`tests/test_decision_writer_registry.py`).

## 4. What still requires the user

Disabling the three Ready legacy tasks is a production change and remains
`RETIRE_PENDING_APPROVAL`. Until then the fence is read-boundary and registry
based: the current Web/publication path never reads their outputs, and the
verifier fails if they ever re-declare authority.

The server DB pipeline remains observation-only. No schedule, schema or
production write was changed.
