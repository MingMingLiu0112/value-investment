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
`LONG-TERM-GOAL.md` is the cross-stage roadmap and graduation contract for future Goal Runs. It is subordinate to these permanent architecture/methodology/evidence boundaries; only `docs/current-stage-goal.md` selects an executable milestone. Do not run the entire roadmap automatically.
Old P0/P0.5, Excel MVP, funnel and v2/v3 goal paths are redirect pages. Their original bytes and hashes are preserved under `docs/archive/goal-consolidation-20260922/`.

## Start Each Goal Run

Read this file, `docs/current-stage-goal.md` and `docs/execution-status.md`, then the relevant architecture/methodology/policy sections.
Record HEAD, working-tree changes and affected evidence. Inherit prior work; do not repeat passed Stage A or three-company freeze work.
Implement only the active task, verify its acceptance, update execution status and stop at the stated boundary. Do not auto-expand to the roadmap.
Use `docs/project-goal-consolidation-20260922.md` for the audit and complete document governance inventory, not as a second goal.

## Current Boundary

The three-company engineering MVP is frozen. This does not mean research-grade valuation or dividend sustainability is complete.
C0-PRICE-BRIDGE-INTEGRITY, C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION, C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT and C3-RESEARCH-PLATFORM-FOUNDATION are frozen. The sole next long goal is M1-FIXED-SAMPLE-RESEARCH-WORKBENCH, defined in `docs/current-stage-goal.md`; this roadmap-authoring turn does not start implementation. On user launch, complete its shared input integrity gate before expanding the preregistered sample to 20 companies, with at least six real deep-research dossiers. The former standalone C4 adapter proposal is absorbed into M1, not a competing goal or a sufficient completion condition.
Keep frozen Moutai values and Midea/Shenhua fail-closed boundaries as regression evidence. New evidence may create separately versioned research, never overwrite historical results to make acceptance pass. M1 permits shared research/distribution work and a guarded Application-to-original-Excel publisher, but no copied company pipelines, full-market engine, Web, new financial-sector model, complete ShareholderYield engine, portfolio/execution extension or broker integration. Complete M1, review and stop; M2-M6 require separate user launch.
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
