# Project Authority and Execution Boundaries

This repository builds an evidence-driven A-share investment research and monitoring system for long-term capital appreciation AND sustainable shareholder cash income. Human decisions remain separate from research results.

## Authority

The latest explicit user task controls the current action. Within repository documents, use these scoped authorities:

1. `AGENTS.md`: navigation, execution discipline and permanent boundaries.
2. `docs/north-star.md`: product purpose and long-term user outcomes.
3. `docs/architecture.md`: domain responsibilities, identities and dependency contracts.
4. `docs/research-methodology.md`: financial, valuation, capital-allocation and dividend methodology.
5. `docs/current-stage-goal.md`: the ONE currently authorized engineering task and its acceptance.
6. `docs/data-and-evidence-policy.md`: mandatory provenance, point-in-time, operations and publication safeguards.
7. `docs/execution-status.md`: dated observations and evidence, not additional instructions.
8. Historical acceptance, progress and `docs/archive/`: read-only context, never a task queue.

This is a responsibility hierarchy, not permission for a stage goal to weaken architecture, methodology or evidence policy. If documents conflict, apply the scoped authority and expose the conflict; do not choose a larger version number or newest appended paragraph.
`docs/value-investment-goal-prompt.md` is the compatibility launch entry and contains no separate roadmap.
`LONG-TERM-GOAL.md` is the cross-stage roadmap and graduation contract for future Goal Runs. It is subordinate to these permanent architecture/methodology/evidence boundaries; only `docs/current-stage-goal.md` selects the authorized Goal envelope and currently focused milestone. The user has extended the next Goal through M7: proceed within that envelope after evidence-backed stage gates, not outside it. This document revision does not itself launch the Goal or authorize production actions.
Old P0/P0.5, Excel MVP, funnel and v2/v3 goal paths are redirect pages. Their original bytes and hashes are preserved under `docs/archive/goal-consolidation-20260922/`.

## New Code Placement Rules

The package name `value_investment_agent` remains stable while its internal boundaries converge. New code must follow [docs/architecture/repository-architecture.md](docs/architecture/repository-architecture.md):

- `domain/`: durable business and investment contracts, calculations and state transitions. It must not import Excel, database drivers, network clients, operations, scripts or test fixtures.
- `application/`: use-case orchestration and typed results. It may depend on domain and infrastructure interfaces, but not on a concrete Excel renderer.
- `infrastructure/`: database, evidence storage, external data, filings, backup and security adapters.
- `presentation/`: Excel and read-model adapters. It must not recalculate valuation, materiality, portfolio or decision logic.
- `operations/`: M6 shadow, recovery, health and authorization runtime boundaries.
- `scripts/`: thin CLI only: parse args, load config, construct a service, invoke, print/write a result and return an exit code. Do not add new financial, valuation, PIT, portfolio, event or decision logic directly to `scripts/`.

Do not add new modules directly to the root of `src/value_investment_agent/` when a target layer is clear. Temporary compatibility shims are allowed and must be marked `DEPRECATED_COMPATIBILITY_SHIM`; they forward instead of duplicating behavior.

Company-specific research, parsers and one-off experiments belong in a case/tool boundary, not in a symbol branch inside general Domain code. New root-level `.xlsx`, `.manifest.json` and candidate workbooks are not allowed; use `artifacts/current/` for checked-in current artifacts and `artifacts/archive/` for historical artifacts after provenance checks. Existing hash- or receipt-bound paths must remain in place until a verifier proves safe relocation.

Repository navigation is explicit: current supported commands are split by product and engineering layers in `config/current-cli-entrypoints-v2.json`, with every v1 path preserved through `config/current-cli-entrypoints-v1.json` compatibility; full script classification is in `docs/architecture/script-inventory-v1.json`; current documentation starts at `docs/current/README.md`; and retained root artifacts are interpreted through `artifacts/current/artifact-registry-v1.json`. Do not infer a current entrypoint from filename recency or directory position. M7 user-facing Excel is a five-page product surface (`今日 / 机会 / 公司 / 我的组合 / 事件`) plus secondary `系统/审计`; M2-M6 names are not user navigation.

Files registered in an immutable manifest by both path and SHA-256 are provenance-frozen. In particular, `src/value_investment_agent/historical_validation.py` must retain its historical bytes because the current historical-validation receipt binds that exact path and hash. New contracts or behavior require a new versioned admission/receipt chain; they must not be introduced by converting or moving a frozen file into a compatibility shim.

Architecture cleanup is `INCREMENTAL_REFACTOR_ONLY`, behavior-preserving, test-gated and rollbackable. It must never change valuation formulas, investment thresholds, M2-M7 acceptance rules, database schema semantics or `action=no_order` in the same commit.

## Start Each Goal Run

Read this file, `docs/current-stage-goal.md` and `docs/execution-status.md`, then the relevant architecture/methodology/policy sections.
Record HEAD, working-tree changes and affected evidence. Inherit prior work; do not repeat passed Stage A or three-company freeze work.
Implement within the authorized M2-M7 Goal, respect dependencies, verify each stage and record its handoff before continuing. Stop at M7 acceptance, not after every internal workstream. Do not auto-expand beyond M7 or waive human/production authorization gates.
Apply the R0-R6 review and interruption rules in `LONG-TERM-GOAL.md`: machine checks and independent/delegated research reviews continue without routine user interruption; private inputs, production authorization, real-money decisions and final product acceptance retain their respective user gates. A local evidence or natural-time wait never blocks unrelated DAG work. For medium-or-larger packages, consider two or three bounded, independent SubAgents for exploration, adversarial review and tests; Root owns shared files, integration, verification and commit.
Use `docs/project-goal-consolidation-20260922.md` for the audit and complete document governance inventory, not as a second goal.

## Current Boundary

The three-company engineering MVP is frozen. This does not mean research-grade valuation or dividend sustainability is complete.
C0-PRICE-BRIDGE-INTEGRITY, C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION, C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT and C3-RESEARCH-PLATFORM-FOUNDATION are frozen. M1-FIXED-SAMPLE-RESEARCH-WORKBENCH is complete as a machine-verifiable research workbench: AC1-AC10 passed and investment conclusions remain `conditional_research_only`. Post-M1 human approval/event review contracts and stabilization are implemented; existing rejected/stale/not-eligible outcomes must be preserved. The authorized Goal is VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE. M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY is complete and Checkpoint A is `HUMAN_PASS`; the currently focused milestone is now M3-DECISION-REVIEW. M2's two non-blocking method-debt items remain OPEN and are documented in docs/m2-non-blocking-method-debt-20260924.md. Continue the M3-M7 stage gates in the same Goal; do not rebuild passed M2 work or turn Checkpoint A approval into Checkpoint B-D, order, portfolio or production approval.
Keep frozen Moutai values and Midea/Shenhua fail-closed boundaries as regression evidence. New evidence may create separately versioned research, never overwrite historical results to make acceptance pass. M2 permits an official universe, four evidence channels, a replayable candidate pool, shadow comparison with the legacy PE/PB screen, and a presentation-only read model integrated into the existing canonical Excel through protected publication. Preserve manual and frozen sheets; do not silently replace the workbook or create competing current entry points. It forbids all-market DCF, copied symbol-specific pipelines, valuation of financial institutions through general models, BUY/ADD/position outputs, Web, new financial-sector models, portfolio/execution extensions and broker integration. These are M2-specific scope limits, not a permanent ban on later human decision support. After M2 acceptance, continue M3 explanations/Entry continuity, M4 portfolio and M5 monitoring with bounded parallelism, M6 authorized operational validation, and M7 personal workbench delivery. Later reviews remain no_order; broker execution, Web expansion and unregistered financial models remain out of scope. R1 independent research approval may be delegated with evidence and provenance; it never authorizes trade. Private IPS/portfolio data, production migrations/scheduling/notifications, real-money decisions and final user sign-off still require their respective user input or authorization. The M6 minimum of 20 real trading sessions cannot be replaced by replay or repeated runs. Finish only after M7 acceptance; no automatic M8.
Allowed freeze exceptions are scoped bug/regression fixes and security/data-integrity repairs. C3 was completed without a production database migration, scheduler change or deployment. A future production migration remains a separate human-confirmed stage.

## Permanent Research Rules

- Facts, assumptions, materiality, valuation, model validity, market price and execution state stay separate.
- ResearchGate reports research completeness; legal PriceBridge and profile-aware rules govern price assessment. Research attractive never authorizes a trade or position.
- DistributionCapacity and DividendSustainability do not depend on current market price. DividendYieldSnapshot does, with explicit dividend basis, known-at date, quote date and share/currency basis.
- Historical or forecast dividends are not added again to a valuation that already includes their economic cash flows.
- Legacy 20/30/40 percent margin rules remain named historical experiments; never make them default valuation, eligibility or position rules.
- Missing/uncertain data fails closed on affected investment conclusions, not on unrelated engineering. Keep Engineering, Research, Valuation, Dividend Research, Current Data and Price Assessment statuses separate.
- Profile/Router selection follows economic structure. Shared flow does not mean common financial metrics, assumptions or thresholds.
- LLMs assist interpretation; verified Python calculations produce numbers. Preserve counterevidence, available-at timestamps, source hashes and replay boundaries.
- Stop collecting evidence when it cannot change thesis, model applicability, assumption bounds, materiality, confidence, valuation or dividend sustainability. Record a concrete reopen trigger.
- No guarantee of returns, no fabricated readiness, no parameter tuning to create trades.
- Research artifact timestamps and hashes alone do not prove point-in-time safety. Bind the actual facts/assumptions used by the model, enforce input availability, and invalidate incremental reuse on rule/model/parser/profile/event-scan changes.
- Future BUY/ADD/HOLD/REDUCE/EXIT states require reasons and human review, never orders. Entry Thesis, decision evidence, private portfolio constraints and buy/sell consistency must exist before claiming personalized decision support.

## Operations and Workspace

Canonical code: `D:/GPTProject/value-investment`. The WPS canonical workbook remains the existing one configured by WORKBOOK_PATH.
The staged six-tab frontend contract is `docs/excel-stage-frontend.md`. Preserve its source dates, manual-record links and unconnected decision/portfolio/monitoring states until the corresponding backend passes acceptance; new pages alone do not graduate a milestone.
Protect user/manual records. Workbook publication needs candidate preservation, source-hash guarding, atomic publication and appropriate WPS verification.
PostgreSQL is the long-term structured store; runtime JSON is currently an evidence-pinned MVP artifact. Do not place database files in a sync drive.
Protect the server's `web_app_integrated.py` / `web-app-pta` service. Respect memory/concurrency limits and the existing disk reserve; no extra services or duplicate scheduled workers without task scope.
Keep secrets, raw database dumps, personal accounts and unencrypted backups out of Git. Restores use an isolated database; never overwrite production.
On Windows use PowerShell 7 at `C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe`, UTF-8 text and explicit execution paths as needed. Preserve unrelated working-tree changes.
