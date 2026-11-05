# Web-first full product requirements v1

Effective: 2026-10-18. Goal: WEB-FIRST-FULL-PRODUCT-CLOSURE-V1.
Authority: latest user objective in attachment 064c26dd-a712-499f-9db8-7a12da99e3eb/goal-objective.md.
This selects future development scope; immutable historical research, approvals,
evidence, accounting and source-availability constraints retain their meaning.

## Product contract

- Web is the primary daily product. Preserve existing routes and deep links.
- Excel is FROZEN: no new features, synchronization, style work or production
  publication development. Preserve the historical workbook, manual records,
  hashes, receipts and recovery dependencies. Task retirement requires separate
  production authorization; freezing development does not disable real tasks.
- CORE_VALUE independently consumes financial and business research, appropriate
  valuation, economic validity, legitimate review, events and price policy.
- HOTSPOT_SATELLITE is an independent price-action strategy. Its new versioned
  path must not require CORE_VALUE Bear/Base/Bull or value G3. It still requires
  identity, security/event risk, available-at evidence, completed bars, structure,
  strategy validation, execution constraints and personal risk. Legacy D5
  results remain evaluated under their original policies.
- Both strategies share actual cash, total symbol/industry exposure, cash floor,
  account-wide risk, settlement, fees and confirmed manual fills. Separate sleeve
  accounting must never duplicate available cash.
- After-close research and intraday observations are distinct. Intraday prices
  never become B1 completed-close evidence. Unfinished bars cannot satisfy
  completed-bar rules. Alerts are observations/review requests, never orders.
- Alerts persist identity, strategy, rule version, observation/source times,
  condition, deduplication key and lifecycle (read/cancel/expire/retrigger).
  Monitoring exists only while its actual process and data source are healthy.
- Reuse the existing Agent/provider/research services for financial, event,
  hotspot and review workflows. Deterministic code owns financial calculations.
  Live paid calls require explicit cost authorization. Mock is not live proof.
- User-entered cash, positions, IPS, reconciliation and manual fills remain
  private. Public research, personal policy, risk preview and formal eligibility
  have separate states. No simulated reviewer or private fact upgrades production.
- Permanent action=no_order. No automatic brokerage or trading.

## Stages and ownership

S0 baseline/CI/requirements -> S1 versioned independent strategy and shared risk.
After S1, S2 value research, S3 hotspot and S4 private workflow may proceed with
disjoint write scopes. S5 intraday alerts depends on S3/S4 interfaces. S6 Agent
research may run alongside independent S5 work. S7 integrates Web, recovery,
operations instructions and five end-to-end routes.

Root owns shared contracts, admission, private risk, current pointers, Git and
integration. At most three independent writing workflows, no shared-file races.
Each stage needs code, connected API/Web behavior, positive/negative tests,
persistence/replay, regression and a machine-readable receipt before PASS.

## Reuse and gap inventory at starting HEAD

| Capability | Existing implementation | Next implementation boundary |
| --- | --- | --- |
| Completed close and public publication | Existing B1 chain, public snapshot loader, hash-bound current pointers | Reuse; keep intraday separate |
| Hotspot structure | current_price_case, price_action_case, current_registry | Legacy v1 is explicitly observation-only; add versioned independent admission, do not remove its exact blocker validation |
| Shared risk | dual_sleeve_risk and private_risk_preview | Reuse cash/exposure engine; strategy approval is a separate responsibility |
| Value model and evidence | residual income model and source_bound_inputs | Repair binding of model-consumed facts; preserve economic formulas |
| Private account | PrivateJournal and private_portfolio_service | Verify connected Web setup, reconciliation, fills, persistence and replay |
| Agent | Existing provider and research workflows | Reuse adapter; mock results do not prove live model operation |
| Web | Existing frontend/API and startup command | Local build passes; actual browser workflow acceptance remains outstanding |
| Recovery | Existing isolated component recovery | Verify integrated product artifacts and restart; production/off-machine acceptance separate |

The 2026-10-17 audit contains reproducible counterexamples, not product PASS.
Inventory entries establish reuse responsibilities, not acceptance of missing
business integration. Detailed next-stage locators remain in the execution
ledger and stage evidence rather than competing requirement documents.

## Superseded future-scope requirements

| Existing requirement | Future scope | Preserved history |
| --- | --- | --- |
| AGENTS/current-stage old D5 value-before-hotspot | S1 introduces a new independent hotspot policy, not deletion of legacy gates | Original D5 packets/rules/refusals stay immutable |
| Excel-first and ongoing protected publication | Web-first, Excel-frozen | Existing workbook/manual data/hashes/recovery stay protected |
| Old prohibition of later Web expansion | Existing Web evolves into seven business entries | Old stage-specific restrictions remain historical |
| Prior audit-only and next-goal plan | Actual S0-S7 implementation is now authorized | 2026-10-17 audit remains evidence, not completion |
| Prior next-executable plan WP09 Excel synchronization | No new Excel work in this Goal | Read-only integrity checks remain permitted |

These changes do not waive data provenance, economic review, strategy evidence,
private input, production authorization or actual user acceptance.

## Independent exits

Engineering completion requires all autonomous S0-S7 work, five E2E chains,
desktop 1440x900/1280x900 and mobile 390x844/430x844 actual interaction, persistence,
isolated recovery and no repairable P0/P1 gaps. Final source CI must be verified.
Real personal use requires actual user cash/holdings/IPS/reconciliation and signoff.
Value eligibility is per-security; hotspot validity is per-rule/security with
PIT/OOS/cost/Shadow evidence. Continuous production operations require actual
runtime and authorization. None of these exits substitutes for another.

External waits block only dependent nodes. A bounded evidence-insufficient value
case may close research engineering honestly without granting investment approval.
Never tune assumptions or rules simply to produce a BUY or a profitable backtest.
