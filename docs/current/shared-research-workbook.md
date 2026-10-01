# Shared Research Workbook Flow

This is a research-presentation flow, not investment admission. Every command retains `action=no_order`. Unknown model validity, pending prices and unapproved research remain blocked.

## Reproducible Integrated Preview

Use `scripts/current/build_product_workbench_candidate.py` with all of:

```text
--historical-preview
--integrate-canonical
--base-payload <repository-contained public payload>
--base-payload-sha256 <pinned SHA-256>
--existing-workbench <verified shared research output>
--existing-workbench-sha256 <pinned SHA-256>
--output runtime/<new-review-folder>/canonical-integration-historical-preview.xlsx
```

For an explicitly public serialized read-model snapshot, add `--base-read-model-snapshot`. Private portfolio snapshots are refused by that adapter. The original workbook is resolved through the existing WORKBOOK_PATH configuration, never a new user path. Generation retains non-product sheets and protected OOXML state, rechecks the original hash and creates an exclusive `canonical-preservation.json` only after those checks pass. Existing output/proof paths are refused. Failed previews may remain for diagnosis but do not receive a PASS proof.

Generation does not publish. The source-binding receipt pins research, base input and preservation proof. Actual WPS/readability review must precede the existing `publish_product_workbench_to_canonical.py --reviewed-research-folder ... --reviewed-research-proof-sha256 ... --publish` command. An explicitly failed or mismatched `visual-review.json` prevents publication. If the original workbook changes, regenerate against its new hash; never edit an old proof to fit.

## Current Dependency Map

| Requirement | Actual implementation | Missing dependency / next action | Acceptance evidence |
| --- | --- | --- | --- |
| Source-bound single-stock presentation | Existing research loader, workbench application, typed valuation and pending PriceBridge projection | Shared integration now has supported CLI; native review remains per generated artifact | Source hashes, human-readable report, preview proof and publication receipt |
| Current investment conclusion | Separate ModelValidity and PriceBridge contracts | Official event outcome, approved research and compatible verified quote for the affected case | Actual admission, not a preview or passing test |
| Historical decision replay | `m3_historical_research_replay.py` explicitly separates retrospective and contemporaneous rules | Inspect real input interval and availability bindings before choosing an authorized case | Version-frozen inputs/rules and reproducible dated decisions, no claim of historical preregistration |
| Three-company contract replay | `research_e2e_replay.py` and frozen manifest runner | Useful regression, not a substitute for real valuation/execution replay | Cross-company semantic equality only |
| Daily production packet | `daily_product_packet.py` rehashes contained quote bundle before frozen packet builder | Current dual-source quote and applicable research needed for current advice | Actual quote binding and applicable decision gates |
| Final operational acceptance | Existing M6/restore/user gates | Twenty real sessions, full restore and final acceptance remain outstanding | Actual operational evidence; no replay substitution |

Do not repeatedly reopen stopped research inputs or let them block independent historical/integration work. The canonical publication on 2026-10-01 demonstrates protected research presentation, not completion of current market or investment gates.

## Observed Result Cutoff Replay

`scripts/current/replay_workbench_cutoffs.py` accepts a pinned `--workbench`, `--workbench-sha256`, increasing timezone-aware repeated `--cutoff` values, a new runtime `--output` and optional new runtime `--report`.

It rehashes original evidence and uses the latest of workbench generation and source-observation timestamps. Before that boundary no valuation is shown. After it the existing blocked research is visible without orders, fills, current price or portfolio guidance. Cutoff timestamps are not asserted to be trading sessions.

This contract deliberately does **not** reconstruct earlier public-information availability, run valuation-based decisions, validate execution mechanics, prove strict PIT or measure returns. The old Median-PE replay is a retained retrospective experiment; the old daily simulator still includes legacy 30% margin rules and must not become the default shared path. Full historical execution acceptance remains outstanding.

## Separate Financial Input Reconstruction

The same replay CLI optionally accepts paired `--arithmetic-input` / `--arithmetic-input-sha256` and `--disclosure-index` / `--disclosure-index-sha256`. All four are required together. This adds a separately scoped `reconstructed_financial_inputs` section; it never changes the observed-result timeline or strict PIT verifier.

The application reuses the existing residual-income arithmetic replay, requiring original source hashes and the two reviewed basis inputs. The infrastructure adapter matches announcement ID, security code and official file URL against a pinned CNINFO index. Since the retained announcement timestamp does not establish precise intraday publication, availability is conservatively the following midnight in China time. Later source-review dates are preserved, not rewritten.

Forecast assumptions are explicitly retrospective pinned scenarios, not contemporaneous forecasts or registered historical rules. Source excerpt semantics, complete FinancialFacts admission, current ModelValidity, price and portfolio gates remain unapproved. Model arithmetic agreement plus date-level disclosure reconstruction alone does not validate a trading strategy.

## Historical Quote and Event Integration

The replay CLI accepts paired `--event-scan` / `--event-scan-sha256` for original-reference integrity auditing. Adding paired `--quote-bundle` / `--quote-bundle-sha256` also invokes the existing quote-session validator, ModelValidity and PriceBridge contracts. All quote/event arguments are required together for bridge integration. This is a retained-observation replay, not reconstructed historical decision or execution acceptance.

The application verifies both the event-scan envelope and every original reference. Missing or changed originals produce NOT_READY and prevent ModelValidity/PriceBridge evaluation. A top-level hash alone is insufficient. Earlier cutoffs cannot see a later-captured quote or later-produced valuation; rows retain separate quote and valuation observation states. The original valuation is never overwritten by price or failed event coverage. Even an arithmetic bridge cannot approve research, portfolio guidance or orders.

Real-input evidence: `runtime/historical-bridge-time-verified-20261001/result.json` and `report.md`. The 600887 September 22 quote passes its existing dual-provider close check, but was captured September 23. The retained valuation was produced October 1. The event index original has a hash mismatch against its sealed scan reference, so no bridge is admitted. This is an identified integrity gap, not completed historical strategy validation. Do not alter the sealed reference to match the changed file.

Next substantive dependency: obtain or independently reconstruct a separately versioned, source-complete historical event package and an explicitly retrospective valuation/rule basis before historical decision/execution integration. An independent reconstruction must preserve the failed old package and cannot claim original historical capture, preregistration or strict PIT approval.

### Exact Original Recovery

An explicit repeated `--recovered-event-original ID=PATH` can locate a misplaced original without rewriting the sealed scan. The recovered file must match the scan's original SHA-256 exactly; an unknown ID, duplicate binding, out-of-root path or different content fails closed. The receipt records the failed original-path status alongside the recovered path and verified hash. This is content-addressed recovery, not a new source or research approval.

The actual sealed index bytes were found at `runtime/company-research/m1-event-scans/20260923T050735Z/600887/cninfo-index.json`, hash `f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93c9f383349388bbc2d815ceea`. No original file was moved or overwritten. `runtime/historical-bridge-recovered-original-20261001/` demonstrates quote validation plus existing model/bridge arithmetic after result observation. Earlier cutoffs still cannot see the later valuation. Pre-model disclosure review remains outstanding, all decisions remain NOT_READY and this does not establish current advice, contemporaneous rules, historical execution or strict PIT.

### Source-Readable Event Packet

Add `--event-source-pages` with the pinned event arguments to extract physical-page PDF text through the existing PDFium adapter. The application requires all original evidence to pass integrity, checks each announcement binding against the audited scan and rehashes each PDF before and after extraction. A failed scan produces NOT_READY without extracting misleading text. Full pages are retained in JSON; the readable report shows bounded excerpts and pending impact questions.

This packet never signs `EventMaterialityDecision`, marks model inputs incorporated, changes valuation assumptions or emits trades. Empty text requires visual review. Actual 19-announcement output and the bounded initial original-source reading are in `runtime/historical-event-source-review-20261001/`. Buyback approval is not execution/cancellation, and guarantee exposure is not automatically a realized loss; both require explicit economic review before model changes.

## Shared Execution Mechanism Integration

The existing virtual-account engine is reused through paired `--execution-scenario` / `--execution-scenario-sha256`. Only `shared-execution-engineering-input-v1` with explicit `SYNTHETIC_ENGINEERING_FIXTURE` scope is admitted here. Capital, prices, proposals and cash events are fixtures, not real company research or personal accounts. Every proposal needs bounded next-session terms; no live approval is accepted. Every journal row, virtual fill and account snapshot carries the simulation-only marker. No new trading thresholds are introduced.

The existing dated statutory fee calculator is used only inside its frozen 2015-2025 span. The current legacy next-session execution contract is 600519-specific and its separate fee review covers only one 2026 session: neither is silently generalized to 600887 or September 2026. Broker-invoice commission and dividend tax remain unvalidated. Real 2026 execution needs separately dated fee, suspension, price-limit and liquidity evidence, plus admitted retrospective research/decision inputs.

Actual fixture replay: `runtime/shared-execution-scenario-20261001/input.json`, `result.json`, `report.md`. It runs entry/add/hold/reduce/exit proposals, next-session fills, fees/slippage, dividend entitlement/payment and a blocked suspension-session exit. This proves shared execution plumbing, not actual historical decisions or strategy returns; `historical_execution_validated=false`, `strict_pit_admitted=false`, `action=no_order` remain mandatory.

## Conditional Price-Implied Terminal ROE

`--reverse-equity-expectations` uses paired arithmetic and verified quote inputs in the same replay CLI. It replays the pinned existing arithmetic first, then inverts only terminal ROE using the existing residual-income formula and reconciles the result through the original forward model. No Bear/Base/Bull, forecast ROE, retention, growth or cost assumptions are modified. The inverse cannot approve a model or decision; results are a separately scoped retrospective comparison, not backdated observations or contemporaneous expectations.

Actual 600887 inputs in `runtime/shared-reverse-equity-expectations-20261001/` imply terminal ROE about 23.7%-28.9% for the September 22 price of CNY26.77, conditional on each pinned scenario's other assumptions. This is not evidence of overvaluation: different discount rates, reinvestment, growth, capital allocation or an inadequate model could explain the difference. Event review, forecast justification and model admission remain outstanding. Full precision is retained for arithmetic reconciliation; the readable report rounds display values.

### Company-Card Projection

The historical preview CLI supports pinned `--expectations-replay` / `--expectations-replay-sha256`. Its loader rehashes the parent replay, follows explicit original workbench/arithmetic/quote bindings and recomputes the inverse before comparing every semantic output. Only the actual artifact creation timestamp is excluded from recomputation equality. Old expectations without those source bindings are not promoted automatically.

The read model appends historical quote date, conditional implied terminal ROE and interpretation limits to existing company review rows and an audit reference. It does not replace current price, valuation scenarios, model/decision gates or portfolio. An explicit `--presentation-as-of` sets the observation date of this newly prepared historical presentation; original fact and quote dates remain unchanged. It cannot backdate the base presentation or exceed generation date.

`--read-model-only` with a new runtime JSON output prepares the exact projection without exporting or publishing Excel. Actual source-bound inverse and company-card data are in `runtime/shared-reverse-equity-source-bound-20261001/` and `runtime/shared-company-expectations-card-20261001/`. Workbook authoring dependency `@oai/artifact-tool` is currently absent from the configured workspace bundle; no alternative user workbook or unverified canonical publication was made. Source-bound read-model engineering continues independently of that export dependency.
