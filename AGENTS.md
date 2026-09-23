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

## Start Each Goal Run

Read this file, `docs/current-stage-goal.md` and `docs/execution-status.md`, then the relevant architecture/methodology/policy sections.
Record HEAD, working-tree changes and affected evidence. Inherit prior work; do not repeat passed Stage A or three-company freeze work.
Implement within the authorized M2-M7 Goal, respect dependencies, verify each stage and record its handoff before continuing. Stop at M7 acceptance, not after every internal workstream. Do not auto-expand beyond M7 or waive human/production authorization gates.
Use `docs/project-goal-consolidation-20260922.md` for the audit and complete document governance inventory, not as a second goal.

## Current Boundary

The three-company engineering MVP is frozen. This does not mean research-grade valuation or dividend sustainability is complete.
C0-PRICE-BRIDGE-INTEGRITY, C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION, C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT and C3-RESEARCH-PLATFORM-FOUNDATION are frozen. M1-FIXED-SAMPLE-RESEARCH-WORKBENCH is complete as a machine-verifiable research workbench: AC1-AC10 passed and investment conclusions remain `conditional_research_only`. Post-M1 human approval/event review contracts and stabilization are implemented; existing rejected/stale/not-eligible outcomes must be preserved. The authorized next Goal is VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE; the currently focused milestone remains M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY. At audited HEAD f4bb55c, a real 2026-09-23 all-market run and separate workbook exist, but M2 remains PARTIAL: temporal validation, official-universe enforcement, per-security coverage, multi-channel reason merging, candidate-quality semantics, newly discovered research, PIT validation and unified Excel acceptance still require work. It is NOT merely three missing reports. Complete M2 using current-stage-goal W0-W7 and AC1-AC12, then follow its M3-M7 stage gates in the same Goal; revalidate completed stabilization rather than rebuilding it.
Keep frozen Moutai values and Midea/Shenhua fail-closed boundaries as regression evidence. New evidence may create separately versioned research, never overwrite historical results to make acceptance pass. M2 permits an official universe, four evidence channels, a replayable candidate pool, shadow comparison with the legacy PE/PB screen, and a presentation-only read model integrated into the existing canonical Excel through protected publication. Preserve manual and frozen sheets; do not silently replace the workbook or create competing current entry points. It forbids all-market DCF, copied symbol-specific pipelines, valuation of financial institutions through general models, BUY/ADD/position outputs, Web, new financial-sector models, portfolio/execution extensions and broker integration. These are M2-specific scope limits, not a permanent ban on later human decision support. After M2 acceptance, continue M3 explanations/Entry continuity, M4 portfolio and M5 monitoring with bounded parallelism, M6 authorized operational validation, and M7 personal workbench delivery. Later reviews remain no_order; broker execution, Web expansion and unregistered financial models remain out of scope. Human approval, private IPS/portfolio data, production migrations/scheduling/notifications and user sign-off still require their explicit inputs or separate authorization. The M6 minimum of 20 real trading sessions cannot be replaced by replay or repeated runs. Finish only after M7 acceptance; no automatic M8.
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
