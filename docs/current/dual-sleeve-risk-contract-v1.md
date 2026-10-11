# P3-C dual sleeve risk contract

This module reviews private/synthetic risk arithmetic, not investment entry eligibility. It preserves `action=no_order`, `trade_eligible=false`, `acceptance_authority=NONE`, `position_guidance=null` and `expected_return=null`. Existing G3, event, value/price, Shadow and human gates are not modified.

Root Application integration imports `review_dual_sleeve_risk(payload, generated_at=aware_datetime, allow_synthetic=False)` from `domain.portfolio.dual_sleeve_risk`. File IO is `application.product.dual_sleeve_risk.run_dual_sleeve_review`. Output schema is `dual-sleeve-risk-review-v1`. Do not publish private values into a public runtime receipt or synthetic demonstration.

## Input JSON

The empty template is `config/private-template/dual-sleeve-risk-input-v1.json`. All monetary amounts and fractions are decimal strings; no investment threshold is supplied by the template. `namespace` is `ACTUAL` or explicitly isolated `SIMULATED`. The top-level fields are exact:

- `schema_version`: `dual-sleeve-risk-input-v1`.
- `action`: `no_order`.
- `portfolio`: the existing `m4-portfolio-contracts-v1` bundle with one IPS and one aggregate PortfolioSnapshot, unchanged. Policy/snapshot account scopes must match; confirmation, reconciliation, availability and quantity evidence are required.
- `shared_budget`: existing SharedSleeveBudget fields `core_value_budget`, `tactical_hotspot_budget`, `cash_floor`, `cross_sleeve_single_stock_cap`, `cross_sleeve_sector_cap` (fractions), `policy_scope` (`USER_CONFIRMED` for actual, `SYNTHETIC_POLICY_ONLY` for simulated), `action=no_order`.
- `sleeves`: exactly `CORE_VALUE` and `HOTSPOT_SATELLITE`. Hotspot maps to the existing `PortfolioSleeve.TACTICAL_HOTSPOT`; no existing contract is renamed.
- `cash_reserve_cny`: cash not assigned to either sleeve. Sleeve cash plus reserve must equal aggregate cash exactly. Budget fractions plus cash floor cannot exceed one portfolio.
- `allocations`: exact fields `sleeve`, `symbol`, `quantity`, `sellable_quantity`, `committed_risk_cny`, `evidence_ref`. Each aggregate share belongs to exactly one sleeve; the same symbol may be split. `committed_risk_cny=null` means unknown, not zero. Quantities sum exactly to the reconciled holding. Sellable quantity is explicit human input, never inferred from a plan.
- `security_attributes`: existing SecurityRiskAttributes payloads, including source evidence, industry, liquidity profile and common factors. Missing attributes fail closed. High volatility can be recorded as an evidenced common factor; no volatility threshold is invented.
- `hotspot_request`: null or the exact request below.

Each sleeve policy has `cash_cny`, `risk_budget_cny`, `max_single_security_fraction`, `max_industry_fraction`, `max_factor_fraction`, `single_trade_risk_fraction`, `single_security_risk_cny`, `realized_pnl_cny`, `financing_allowed`, `risk_tools_allowed`, `confirmed_at`, `evidence_ref`. The two risk limits are required for hotspot and may be null for core. Realized P&L is a user-provided reconciled amount or null; it is never calculated from plans. Financing/risk-tool permission must be explicit; if enabled, the unsupported instruments block sizing rather than borrowing cash.

Hotspot request fields: `sleeve=HOTSPOT_SATELLITE`, `symbol`, `entry_price_cny`, `stop_price_cny`, `gap_stress_cny`, `entry_slippage_cny`, `exit_slippage_cny`, `buy_fee_fraction`, `sell_fee_fraction`, `minimum_buy_fee_cny`, `minimum_sell_fee_cny`, `lot_size` (explicit integer), `max_trade_notional_cny` (user liquidity/cash bound), `quote_as_of`, `available_at`, `valid_until`, `liquidity_verified`, `limit_up`, `limit_down`, `research_version_sha256`, `evidence_ref`. Input dates must match the private snapshot; stale or future market inputs block sizing. Missing permission/evidence is not approval. Core cannot use this stop-based request.

## Output JSON

`status=NOT_CONNECTED` means no private portfolio is connected. Partial inputs produce `BLOCKED_PRIVATE_INPUT`. Both have `sleeves`, `aggregate`, `hotspot_quantity_review` all null, with no personal quantities, P&L or return expectations. For complete inputs:

- `sleeves[CORE_VALUE|HOTSPOT_SATELLITE]`: budget/equity/used/cash/available funds, risk budget/committed/available risk, realized and unrealized P&L, allocated holdings with sellable quantities, concentration limits, industry/factor exposure, full capital at risk. Core exit basis is fundamental thesis and liquidity review, `mechanical_stop_required=false`.
- `aggregate`: exact total assets/cash/reserve, cross-sleeve duplicate symbols with each sleeve quantity and value, and the unchanged existing PortfolioRiskAssessment (security/industry/cyclical/factor/liquidity exposures and findings). Assets are not counted twice.
- `blockers`: sleeve/aggregate budget, concentration, liquidity and missing-risk findings. Core and hotspot risk budgets are independent; no transfer is performed.
- `hotspot_quantity_review`: null, a blocked result with `review_quantity=null`, or `QUANTITY_REVIEW_ONLY` with integer `review_quantity`, cash required, stressed loss, risk limit, full capital at risk, formula and limitations. This number is a risk-bound review ceiling, never an entry signal or order.

Planned single-trade risk is hotspot equity times the user's risk fraction, capped by remaining hotspot and single-security risk budgets. Quantity is rounded down to the supplied lot unit and bounded by cash, fees, liquidity notional, sleeve and aggregate security/industry limits and common-factor limits. Buy and sell fees include explicit per-side minima. Gap and slippage stress lower the planned exit. T+1 prevents guaranteed same-day sale; stop prices cannot guarantee execution, and actual loss may exceed the stress estimate. Full capital loss remains visible separately.

## Local usage and manual records

`python scripts/current/review_dual_sleeve_risk.py` reports NOT_CONNECTED without writing anything. Root's default `run_dual_sleeve_review(root=ROOT, output_path=fresh_runtime_path)` produces a fresh no-amount report for envelope role `dual_sleeve_report`. CLI `--output runtime/fresh.json` does the same with no portfolio. Actual input/output requires an existing private root outside all Git and sync roots: `--private-root PATH --portfolio PATH --portfolio-sha256 SHA --output PATH`. `--portfolio` aliases `--input` and names the complete dual-sleeve input JSON, including the unchanged existing portfolio bundle inside `portfolio`. Actual private numeric details are not printed to stdout. Synthetic input requires `--synthetic`, `namespace=SIMULATED`, and input/output under repository `.tmp/`.

Every file-bound review includes `semantic_content`, produced by the Application helper of the same name. It retains the economic/risk inputs, evidence hashes, policy/model versions, market as-of/availability/expiry, outcomes and blockers; it excludes generated_at, per-run input binding, paths and non-economic run/snapshot/policy IDs. Root should compare this field for update idempotence. Raw file pins remain in the outer report for audit. `risk_input_semantics` is PRIVATE when inputs are actual; do not copy it into public diagnostics.

## Sagan private-input area handoff

No renderer or existing Excel page is changed here. The separate blank CSV template is `config/private-template/dual-sleeve-private-input-v1.csv`; use columns `section,field,value,source_ref` for a preserved manual input area on managed `04我的组合`, without changing the 55 protected old worksheets. Each editable value starts blank, never zero; only user input makes it nonempty. Preserve raw text and source references during import/republication. The table is not an economic calculation sheet and must not compute holdings from plans.

Renderer/Excel adapters can pass a list of these four-field row objects to `application.product.dual_sleeve_input_sheet.parse_dual_sleeve_input_rows(rows, namespace='ACTUAL', generated_at=aware_datetime)`. CSV files use `parse_dual_sleeve_input_csv`; neither function writes files or changes a workbook. Empty/partial input returns `dual-sleeve-private-input-validation-v1`, `status=INPUT_INCOMPLETE`, exact `missing_inputs`, and `payload=risk_report=null`; completed input is validated through the existing IPS/Portfolio and dual-sleeve review contracts. Blank is distinct from an explicitly entered numeric 0 or false. Financial cells cannot be formulas; populated values require source_ref.

CLI `--input-sheet PRIVATE_CSV --input-sheet-sha256 SHA --private-root PATH --output PRIVATE_JSON` validates/imports instead of `--portfolio`. All actual paths use the existing outside-Git/outside-sync privacy boundary. Simple policy/cash cells are text values; holdings/allocations/security attributes preserve their existing structured JSON arrays in separate rows (`[]` means explicitly confirmed empty). Root can later render these arrays as distinct private tables, then compose the same contracts. Optional hotspot request is null or its existing typed JSON object. This is an import interface, not a claim that manual Excel preservation/publication has already been integrated or tested.

Manual declarations use `--manual-record PATH --manual-record-sha256 SHA --record-directory PATH`; existing history additionally requires `--expected-head-sha256 SHA`. `append_dual_sleeve_manual_record` appends an immutable hash-linked `dual-sleeve-manual-record-v1`, with one explicit namespace and strategy. No edit/replacement, estimated fills or automatic portfolio changes occur. An existing claim from an interrupted append is retained and rejects another append; preserve it for audit rather than silently reusing the slot.

Body fields are `record_id`, `kind` (PLAN/FILL/REVIEW), `namespace`, `sleeve`, `symbol`, `recorded_at`, `trade_date`, `research_version_sha256`, `candidate_action`, `observed_price_cny`, `reason`, `risk_budget_cny`, `invalidation_condition`, `user_confirmation` (PENDING/USER_CONFIRMED), `plan_record_sha256`, `fill`, `retrospective`, `evidence_ref`. PLAN leaves the last three null. FILL/REVIEW binds an exact existing plan of the same symbol/strategy/research version. FILL requires USER_CONFIRMED and explicit `transaction_id`, `side`, `quantity`, `price_cny`, `fees_cny`, `next_sell_session`, `source_ref`; BUY next actual sell session must be later than trade date (T+1), SELL leaves it null. REVIEW has no fill and requires retrospective text. Same transaction cannot be counted twice. Records are user assertions, not signature approvals, and do not alter the snapshot; holdings change only through the existing reconciliation workflow.

Root owns renderer/read-model, registry and CI integration. Dedicated tests: `tests/test_dual_sleeve_risk.py`, `tests/test_dual_sleeve_records.py`, `tests/test_dual_sleeve_input_sheet.py`; all amounts and thresholds in tests are explicitly synthetic.

## Local verification, 2026-10-12

Focused dual-sleeve, private-input sheet, manual record, existing IPS/Portfolio, aggregate risk and reconciliation regression: **68 passed**. An additional architecture run earlier reported 92 passed and three integration failures: four new CLIs not yet in Root-owned registry/inventory, and the separate `infrastructure/evidence/product_update_publication.py` importing scripts. This package does not edit those shared files. Final clean/core verification remains Root integration work.

Actual local isolated evidence:

- `.tmp/p3c-dual-sleeve-evidence/synthetic-report.json`, SHA256 `acebf6a194c53a98dde88791d99f601cf951038a15ec190665ce47067672aaf4`: SIMULATED only, aggregate equity 10000, duplicated symbol split 60/40 shares, hotspot review ceiling 200 shares, cash required 2004.002, gap/fee/slippage stressed loss 227.78000, no trade eligibility or personal return estimate.
- `runtime/p3c-dual-sleeve-20261012/not-connected.json`, SHA256 `c13759e0af6cfd36438ded6c18369bedfa548ceef945cb708d0f089089ef52d7`: ACTUAL NOT_CONNECTED, no private holdings/amounts/quantity/return result; suitable for Root's default `dual_sleeve_report` role.
- `.tmp/p3c-dual-sleeve-evidence/validation-receipt.json`: binds the two reports and the separate manually declared synthetic PLAN/FILL journal; confirms no fills applied to snapshot and no real approval generated.

Engineering contracts are ready for Root integration; no real portfolio policy/holding was supplied, no real investment strategy thresholds were invented, no renderer was edited, no workbook was published, and no Git commit was made.
