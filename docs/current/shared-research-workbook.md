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
