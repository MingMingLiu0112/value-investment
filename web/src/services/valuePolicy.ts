import type { ValueResearchAnalysis } from "../types/api";

type EvidenceBinding = { path: string; sha256: string };

export type JointCapitalReview = {
  schema_version:
    | "joint-capital-review-v1"
    | "joint-capital-cash-review-v2"
    | "joint-capital-cash-review-v3";
  input_mode?: string;
  symbol: string;
  action: "no_order";
  status: "CONDITIONAL_PATH_NOT_APPROVED";
  scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS";
  candidate_binding: EvidenceBinding;
  proposal_binding: EvidenceBinding;
  policy_binding: EvidenceBinding;
  input_descriptor_sha256: string;
  selected_choice: string;
  date_scope: "DATED_CONDITIONAL_MODEL" | "UNDATED_CONDITIONAL_MODEL";
  basis_at: string | null;
  valuation_at: string | null;
  scenarios: {
    scenario: "bear" | "base" | "bull";
    drivers: Record<string, unknown> & {
      years: { year: number; revenue_growth: string; cost_ratio: string }[];
    };
    ledger: Record<string, unknown> & {
      rows: (Record<string, unknown> & { year: number })[];
      forecast_roe: string[];
      cash_funding_status?: "PASS" | "FAIL";
      scope: string;
      limitations: string[];
    };
    valuation_per_share: string;
    terminal_economics?: {
      mechanism: "recursive_capital_use_and_owner_distribution";
      terminal_contract_version: "terminal-economic-contract-v1";
      explicit_distribution_pv_cny: string;
      terminal_value_at_year_10_cny: string;
      terminal_distribution_value_cny: string;
      terminal_convergence_residual_cny: string;
      terminal_years_evaluated: number;
      ri_ddm_difference_cny: string;
      limitations: string[];
    };
  }[];
};

export type EconomicReviewMaterial = {
  schema_version: "value-economic-review-materials-v1";
  symbol: string;
  action: "no_order";
  status: "PENDING_ECONOMIC_JUDGMENT" | "STRESS_ONLY_NOT_PRIMARY";
  candidate_binding: EvidenceBinding;
  model_context: Record<string, unknown>;
  input_descriptor_sha256: string;
  valuation_artifact_sha256: string;
  assessment_sha256: string;
  materials_sha256: string;
  primary_valuation_usable: false;
  approval_changed: false;
  groups: {
    id: string;
    title: string;
    field_paths: string[];
    verified_observations: string[];
    conditional_assumptions: string[];
    counter_evidence: string[];
    judgment_questions: string[];
    evidence_refs: EvidenceBinding[];
  }[];
  economic_assessment: NonNullable<
    ValueResearchAnalysis["economic_assessment"]
  > & {
    assessment_sha256: string;
    approval_changed: false;
    strategy_admitted: false;
    action_admitted: false;
    review_binding: {
      candidate_binding: EvidenceBinding;
      model_context: Record<string, unknown>;
      package_binding?: EvidenceBinding;
      workbench_binding?: EvidenceBinding;
      review_packet_binding?: EvidenceBinding;
    };
  };
  source_bindings: EvidenceBinding[];
  joint_capital_review?: JointCapitalReview;
};

export const nativeCashFields = [
  "opening_book",
  "profit",
  "roe",
  "book_close",
  "actual_retention",
  "legacy_profit_before_new_cash_cost",
  "permanent_after_tax_cash_expense",
  "assumed_parent_standalone_profit",
  "parent_net_funds",
  "incremental_parent_cash_income",
  "opening_parent_cash",
  "opening_delayed_asset",
  "newly_withheld",
  "released",
  "delayed_close",
  "cash_capacity",
  "cash_close",
  "cash_bridge_residual",
  "project_cash",
  "fund_capital_call",
  "fund_asset_at_cost",
  "dividend_planned",
  "dividend_paid",
  "retained_profit_capacity",
  "parent_retained_profit_close",
  "parent_equity_close",
  "statutory_appropriation",
] as const;

export type SourceNativeCashReview = {
  schema_version: "source-native-economic-review-materials-v1";
  symbol: string;
  scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_G3";
  action: "no_order";
  cash_branch: "TIMING_DELAY";
  authenticated_consumption_supported: false;
  confidence: "低" | "LOW";
  research_admitted: false;
  primary_registered: false;
  approval_changed: false;
  strict_contemporaneous_pit: "NOT_PROVEN";
  point_in_time: {
    valuation_date: string;
    report_period: string;
    research_as_of: string;
    available_at: string;
    computed_at: string;
  };
  valuation_timing_status: "EXPLICIT_MODEL_TIMING";
  valuation_timing: {
    basis_at: string;
    valuation_at: string;
    evidence_refs: (EvidenceBinding & { id: string })[];
  };
  historical_cash_bridge: { scope: string; unit: "CNY"; unknowns: string[] };
  joint_assumptions: Record<string, unknown> & {
    action: "no_order";
    horizon: 5;
    explicit_retention: string;
    incremental_parent_cash_yield: string;
    ke: string;
    TIMING_DELAY: {
      meaning: string;
      release: string;
      withheld_fraction: string;
      withheld_years: number[];
    };
  };
  scenarios: Record<
    "bear" | "base" | "bull",
    {
      cash_ledger: (Record<(typeof nativeCashFields)[number], string> & {
        year: number;
      })[];
      inputs: Record<string, unknown>;
      per_share_value: string;
    }
  >;
  candidate_binding: EvidenceBinding;
  model_context: Record<string, unknown>;
  source_bindings: EvidenceBinding[];
};

export type PolicyRule = {
  action: "entry" | "add" | "reduce" | "exit";
  scenario: "bear" | "base" | "bull";
  value_fraction: string;
  comparison: "LTE" | "GTE";
  rationale: string;
};

export type MaterialityReviewHandoff = {
  status: string;
  approval_granted: false;
  reason?: string;
  scan_window?: { scan_from: string; scan_to: string };
  announcements?: unknown[];
  unsigned_response?: unknown;
  recompute_status?: string;
  recompute_reason?: string;
  commands?: {
    prepare_handoff?: string;
    consume_signed_response?: string;
    recompute?: string;
  };
  publication_required?: boolean;
};

export type PolicyHandoffNotReady = {
  action: "no_order";
  status: "NOT_READY";
  symbol: string;
  blockers: string[];
  bindings?: {
    draft: { path: string; sha256: string };
    package: { path: string; sha256: string };
    input_sha256: string;
  };
  verification: { approval_changed: false; research_admitted: false };
  materiality_handoff?: MaterialityReviewHandoff;
  supplemental_materiality_handoff?: MaterialityReviewHandoff;
};

export type PolicyHandoff =
  | PolicyHandoffNotReady
  | {
      action: "no_order";
      status: "EXTERNAL_SIGNATURE_REQUIRED";
      symbol: string;
      candidate_binding: unknown;
      model_context: unknown;
      valuation_artifact_sha256: string;
      review_questions: unknown;
      unsigned_response: unknown;
      authorization: { pinned_root_count: number; status: string };
      steps: { id: string; action: string }[];
      verification: { approval_changed: false; research_admitted: false };
      commands: { draft_preview: string; consume_signed_response: string };
      materiality_handoff?: MaterialityReviewHandoff;
      supplemental_materiality_handoff?: MaterialityReviewHandoff;
      economic_review_materials?: EconomicReviewMaterial;
    };

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const digest = (value: unknown): value is string =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
function binding(value: unknown): value is EvidenceBinding {
  return (
    record(value) &&
    typeof value.path === "string" &&
    value.path.length > 0 &&
    !/^(?:[\\/]|[a-z]+:)/i.test(value.path) &&
    !value.path.split(/[\\/]/).includes("..") &&
    digest(value.sha256)
  );
}
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (record(value))
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, ordered(value[key])]),
    );
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  )
    return value;
  throw new Error("Non-JSON review context");
}
const same = (left: unknown, right: unknown) =>
  JSON.stringify(ordered(left)) === JSON.stringify(ordered(right));

const finiteDecimal = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) &&
  Number.isFinite(Number(value));

export const jointRowFields = [
  "revenue",
  "cost",
  "legacy_pre_tax_profit",
  "legacy_parent_profit",
  "new_operating_profit",
  "new_liquidity_profit",
  "profit",
  "opening_book",
  "roe",
  "retained",
  "dividend",
  "closing_book",
  "net_operating_addition",
  "net_liquidity_addition",
  "maintenance_capex_assumption",
  "cash_open",
  "cash_close",
] as const;
export const jointTerminalFields = [
  "retention",
  "terminal_roe",
  "terminal_growth",
  "terminal_profit",
  "terminal_book",
  "terminal_retention",
  "terminal_net_operating_investment",
  "terminal_new_liquidity_investment",
  "terminal_dividend",
] as const;
const driverFields = [
  "retention",
  "operating_allocation",
  "new_operating_return",
  "new_liquidity_return",
  "parent_cash_conversion",
  "terminal_growth",
  "terminal_profit_scale",
];

export const JOINT_CASH_SCHEMA = "joint-capital-cash-path-proposal-v2";
export const JOINT_CASH_V3_SCHEMA = "joint-capital-cash-path-proposal-v3";
export function isJointCashReview(value: unknown): boolean {
  return (
    record(value) &&
    (["joint-capital-cash-review-v2", "joint-capital-cash-review-v3"].includes(
      String(value.schema_version),
    ) ||
      [JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA].includes(
        String(value.input_mode),
      ))
  );
}

export const jointCashPolicyFields = [
  "target_payout_ratio",
  "accessible_profit_ratio",
  "reserve_ratio",
  "net_maintenance_cash_cny",
  "operating_wc_cash_cny",
  "commitment_cash_cny",
] as const;
export const jointCashRowFields = [
  "profit",
  "opening_book",
  "opening_cash",
  "opening_unremitted",
  "opening_distribution_capacity",
  "opening_operating_capital",
  "opening_liquidity_capital",
  "forecast_roe",
  "target_distribution",
  "accessible_profit",
  "newly_unremitted",
  "net_maintenance_cash_cny",
  "operating_wc_cash_cny",
  "commitment_cash_cny",
  "mandatory_cash",
  "cash_distribution_limit",
  "capacity_distribution_limit",
  "reserve_transfer",
  "distribution",
  "retained",
  "retention",
  "discretionary_operating_addition",
  "closing_productive_operating_capital",
  "closing_operating_capital",
  "closing_liquidity_capital",
  "closing_cash",
  "closing_book",
  "closing_unremitted",
  "closing_distribution_capacity",
  "funding_shortfall",
  "clean_surplus_residual",
  "capital_identity_residual",
] as const;
export const jointCashOperatingFields = [
  "revenue",
  "cost",
  "pre_tax_profit",
  "tax",
  "legacy_parent_profit",
  "new_operating_profit",
  "new_liquidity_profit",
  "historical_da_anchor",
  "other_pre_tax_balance",
] as const;
export const jointCashTerminalFields = [
  "terminal_roe",
  "terminal_retention",
  "terminal_growth",
  "terminal_profit",
  "terminal_distribution",
  "terminal_book",
] as const;

const cashRatio = (value: unknown) =>
  finiteDecimal(value) && Number(value) >= 0 && Number(value) <= 1;
const exactFields = (
  value: Record<string, unknown>,
  fields: readonly string[],
) =>
  Object.keys(value).length === fields.length &&
  fields.every((key) => key in value);
function cashPolicy(value: unknown): value is Record<string, string> {
  return (
    record(value) &&
    jointCashPolicyFields.every((key) => finiteDecimal(value[key])) &&
    ["target_payout_ratio", "accessible_profit_ratio", "reserve_ratio"].every(
      (key) => cashRatio(value[key]),
    ) &&
    Number(value.net_maintenance_cash_cny) >= 0 &&
    Number(value.commitment_cash_cny) >= 0
  );
}
function cashRow(
  value: unknown,
  year: number,
): value is Record<string, unknown> {
  if (
    !record(value) ||
    value.year !== year ||
    !jointCashRowFields.every((key) => finiteDecimal(value[key])) ||
    !cashPolicy(value.cash_policy) ||
    !exactFields(value.cash_policy, jointCashPolicyFields) ||
    !cashRatio(value.retention) ||
    Number(value.profit) <= 0 ||
    Number(value.opening_book) <= 0 ||
    Number(value.funding_shortfall) < 0 ||
    value.funding_status !==
      (Number(value.funding_shortfall) > 0 ? "SHORTFALL" : "FUNDED")
  )
    return false;
  return [
    "net_maintenance_cash_cny",
    "operating_wc_cash_cny",
    "commitment_cash_cny",
  ].every(
    (key) =>
      decimalIdentity(value[key]) ===
      decimalIdentity((value.cash_policy as Record<string, string>)[key]),
  );
}

const v3TerminalPolicyFields = [
  ...jointCashPolicyFields,
  "profit_scale",
  "rationale",
  "terminal_mechanism",
  "terminal_start_year",
  "first_distribution_timing",
  "legacy_profit_dynamics",
  "commitment_occurrences",
  "restricted_cash_release_cny",
  "restricted_cash_release_year",
  "convergence_tolerance_cny",
  "max_tail_years",
] as const;
const v3TerminalContractFields = [
  "opening_book",
  "opening_cash",
  "opening_unremitted",
  "opening_distribution_capacity",
  "opening_operating_capital",
  "opening_productive_capital",
  "opening_cash_reference",
  "cash_floor",
  "legacy_profit",
  "operating_allocation",
  "productive_marginal_return",
  "liquidity_return",
  "policy",
  "commitment_occurrences",
  "restricted_cash_release_cny",
  "restricted_cash_release_year",
  "convergence_tolerance_cny",
  "max_tail_years",
  "rationale",
] as const;
const v3TerminalEconomicsFields = [
  "mechanism",
  "terminal_contract_version",
  "explicit_distribution_pv_cny",
  "terminal_value_at_year_10_cny",
  "terminal_distribution_value_cny",
  "terminal_convergence_residual_cny",
  "terminal_years_evaluated",
  "ri_ddm_difference_cny",
  "limitations",
] as const;

function v3TerminalPolicy(value: unknown): boolean {
  return (
    record(value) &&
    exactFields(value, v3TerminalPolicyFields) &&
    cashPolicy(value) &&
    finiteDecimal(value.profit_scale) &&
    Number(value.profit_scale) > 0 &&
    value.terminal_mechanism ===
      "recursive_capital_use_and_owner_distribution_v1" &&
    Number.isInteger(value.terminal_start_year) &&
    Number(value.terminal_start_year) === 11 &&
    value.first_distribution_timing === "end_of_terminal_year_1" &&
    value.legacy_profit_dynamics === "constant_after_profit_scale_transition" &&
    (value.commitment_occurrences === null ||
      (Number.isInteger(value.commitment_occurrences) &&
        Number(value.commitment_occurrences) >= 0)) &&
    finiteDecimal(value.restricted_cash_release_cny) &&
    Number(value.restricted_cash_release_cny) >= 0 &&
    (value.restricted_cash_release_year === null ||
      (Number.isInteger(value.restricted_cash_release_year) &&
        Number(value.restricted_cash_release_year) >= 1)) &&
    finiteDecimal(value.convergence_tolerance_cny) &&
    Number(value.convergence_tolerance_cny) > 0 &&
    Number.isInteger(value.max_tail_years) &&
    Number(value.max_tail_years) >= 1 &&
    typeof value.rationale === "string" &&
    !!value.rationale.trim()
  );
}

function v3TerminalContract(value: unknown): boolean {
  if (!record(value) || !exactFields(value, v3TerminalContractFields))
    return false;
  const decimalFields = v3TerminalContractFields.filter(
    (key) =>
      ![
        "policy",
        "commitment_occurrences",
        "restricted_cash_release_year",
        "max_tail_years",
        "rationale",
      ].includes(key),
  );
  return (
    decimalFields.every((key) => finiteDecimal(value[key])) &&
    Array.isArray(value.policy) &&
    value.policy.length === jointCashPolicyFields.length &&
    new Set(value.policy.map((row) => (Array.isArray(row) ? row[0] : null)))
      .size === jointCashPolicyFields.length &&
    value.policy.every(
      (row) =>
        Array.isArray(row) &&
        row.length === 2 &&
        jointCashPolicyFields.includes(row[0] as never) &&
        finiteDecimal(row[1]),
    ) &&
    (value.commitment_occurrences === null ||
      (Number.isInteger(value.commitment_occurrences) &&
        Number(value.commitment_occurrences) >= 0)) &&
    (value.restricted_cash_release_year === null ||
      (Number.isInteger(value.restricted_cash_release_year) &&
        Number(value.restricted_cash_release_year) >= 1)) &&
    Number.isInteger(value.max_tail_years) &&
    Number(value.max_tail_years) >= 1 &&
    typeof value.rationale === "string" &&
    !!value.rationale.trim()
  );
}

function v3TerminalEconomics(value: unknown): boolean {
  return (
    record(value) &&
    exactFields(value, v3TerminalEconomicsFields) &&
    value.mechanism === "recursive_capital_use_and_owner_distribution" &&
    value.terminal_contract_version === "terminal-economic-contract-v1" &&
    [
      "explicit_distribution_pv_cny",
      "terminal_value_at_year_10_cny",
      "terminal_distribution_value_cny",
      "terminal_convergence_residual_cny",
      "ri_ddm_difference_cny",
    ].every((key) => finiteDecimal(value[key])) &&
    Number(value.terminal_value_at_year_10_cny) > 0 &&
    Number(value.terminal_distribution_value_cny) > 0 &&
    Number(value.terminal_convergence_residual_cny) >= 0 &&
    Number.isInteger(value.terminal_years_evaluated) &&
    Number(value.terminal_years_evaluated) >= 1 &&
    strings(value.limitations) &&
    value.limitations.length > 0 &&
    value.limitations.every((text) => !!text.trim())
  );
}
/** Validate the v2 cash contract independently of the legacy five-year fields. */
function jointCashScenariosMatch(review: Record<string, unknown>): boolean {
  const v3BySchema = review.schema_version === "joint-capital-cash-review-v3";
  const v3ByInput = review.input_mode === JOINT_CASH_V3_SCHEMA;
  const v3 = v3BySchema || v3ByInput;
  if (
    (v3 && v3BySchema !== v3ByInput) ||
    (!v3 &&
      !["joint-capital-review-v1", "joint-capital-cash-review-v2"].includes(
        String(review.schema_version),
      )) ||
    (!v3 &&
      review.input_mode !== undefined &&
      review.input_mode !== JOINT_CASH_SCHEMA) ||
    (!v3 &&
      review.schema_version === "joint-capital-review-v1" &&
      review.input_mode !== JOINT_CASH_SCHEMA)
  )
    return false;
  if (
    v3 &&
    (review.explicit_years !== 10 ||
      review.distribution_scope !==
        "ANNUAL_CASH_AND_CAPACITY_CONSTRAINED_NOT_APPROVED" ||
      review.terminal_scope !==
        "RECURSIVE_CAPITAL_USE_AND_OWNER_DISTRIBUTION_NOT_GROWTH_PERPETUITY")
  )
    return false;
  if (
    ("explicit_years" in review && review.explicit_years !== 10) ||
    ("distribution_scope" in review &&
      review.distribution_scope !==
        "ANNUAL_CASH_AND_CAPACITY_CONSTRAINED_NOT_APPROVED") ||
    ("terminal_scope" in review &&
      review.terminal_scope !==
        (v3
          ? "RECURSIVE_CAPITAL_USE_AND_OWNER_DISTRIBUTION_NOT_GROWTH_PERPETUITY"
          : "EXPLICIT_CONTINUING_CASH_NEEDS_NOT_DEFAULT_FULL_PAYOUT"))
  )
    return false;
  for (const key of [
    "approval_changed",
    "research_admitted",
    "primary_registered",
    "strategy_admitted",
    "action_admitted",
  ])
    if (key in review && review[key] !== false) return false;
  if (review.date_scope === "DATED_CONDITIONAL_MODEL") {
    const basis = instant(review.basis_at),
      at = instant(review.valuation_at);
    if (basis === null || at === null || basis > at) return false;
    const first = new Date(review.basis_at as string);
    first.setUTCFullYear(first.getUTCFullYear() + 1);
    if (at >= BigInt(first.getTime()) * BigInt(1000000)) return false;
  }
  return (review.scenarios as unknown[]).every((item, index) => {
    if (
      !record(item) ||
      item.scenario !== ["bear", "base", "bull"][index] ||
      !finiteDecimal(item.valuation_per_share) ||
      Number(item.valuation_per_share) <= 0 ||
      !record(item.drivers) ||
      !exactFields(item.drivers, [
        "years",
        "operating_allocation",
        "new_operating_return",
        "new_liquidity_return",
      ]) ||
      ![
        "operating_allocation",
        "new_operating_return",
        "new_liquidity_return",
      ].every((key) =>
        cashRatio((item.drivers as Record<string, unknown>)[key]),
      ) ||
      !Array.isArray(item.drivers.years) ||
      item.drivers.years.length !== 10 ||
      !item.drivers.years.every(
        (row, i) =>
          record(row) &&
          exactFields(row, [
            "year",
            "revenue_growth",
            "cost_ratio",
            ...jointCashPolicyFields,
          ]) &&
          row.year === i + 1 &&
          finiteDecimal(row.revenue_growth) &&
          Number(row.revenue_growth) > -1 &&
          cashRatio(row.cost_ratio) &&
          cashPolicy(row),
      )
    )
      return false;
    const ledger = item.ledger;
    const terminalPolicy = record(ledger) ? ledger.terminal_policy : undefined;
    if (
      !record(ledger) ||
      ledger.version !==
        (v3 ? "joint-capital-cash-path-v3" : "joint-capital-cash-path-v2") ||
      ledger.action !== "no_order" ||
      ledger.status !== "CONDITIONAL_RESEARCH_NOT_APPROVED" ||
      ledger.scope !== "ordinary_owner_equivalent_cash_mapping" ||
      ledger.currency !== "CNY" ||
      !strings(ledger.limitations) ||
      !ledger.limitations.length ||
      ledger.limitations.some((text) => !text.trim()) ||
      !jointCashTerminalFields.every((key) => finiteDecimal(ledger[key])) ||
      !cashRatio(ledger.terminal_retention) ||
      !Array.isArray(ledger.rows) ||
      ledger.rows.length !== 10 ||
      !Array.isArray(ledger.forecast_roe) ||
      ledger.forecast_roe.length !== 10 ||
      !ledger.forecast_roe.every(finiteDecimal) ||
      !Array.isArray(ledger.forecast_retentions) ||
      ledger.forecast_retentions.length !== 10 ||
      !ledger.forecast_retentions.every(cashRatio) ||
      !cashRow(ledger.terminal, 11) ||
      !record(terminalPolicy) ||
      !(v3 ? v3TerminalPolicy(terminalPolicy) : cashPolicy(terminalPolicy)) ||
      !(v3
        ? true
        : exactFields(terminalPolicy, [
            ...jointCashPolicyFields,
            "profit_scale",
            "rationale",
          ])) ||
      !finiteDecimal(terminalPolicy.profit_scale) ||
      Number(terminalPolicy.profit_scale) <= 0 ||
      typeof terminalPolicy.rationale !== "string" ||
      !terminalPolicy.rationale.trim()
    )
      return false;
    if (
      v3 &&
      (ledger.terminal_growth_status !==
        "NON_AUTHORITATIVE_ACCOUNTING_DIAGNOSTIC" ||
        !v3TerminalContract(ledger.terminal_economic_contract) ||
        !v3TerminalEconomics(item.terminal_economics) ||
        !record(item.actual_calculation_inputs) ||
        item.actual_calculation_inputs.terminal_contract_version !==
          "terminal-economic-contract-v1" ||
        item.actual_calculation_inputs.terminal_mechanism !==
          "recursive_capital_use_and_owner_distribution")
    )
      return false;
    if (!v3 && item.terminal_economics !== undefined) return false;
    const roes = ledger.forecast_roe,
      retentions = ledger.forecast_retentions,
      years = item.drivers.years;
    if (
      !ledger.rows.every(
        (row, i) =>
          cashRow(row, i + 1) &&
          jointCashOperatingFields.every((key) => finiteDecimal(row[key])) &&
          record(row.expenses) &&
          exactFields(row.expenses, [
            "surcharges",
            "selling",
            "admin",
            "research",
          ]) &&
          Object.values(row.expenses).every(finiteDecimal) &&
          decimalIdentity(row.forecast_roe) === decimalIdentity(roes[i]) &&
          decimalIdentity(row.retention) === decimalIdentity(retentions[i]) &&
          jointCashPolicyFields.every(
            (key) =>
              decimalIdentity(
                (row.cash_policy as Record<string, unknown>)[key],
              ) === decimalIdentity(years[i][key]),
          ),
      )
    )
      return false;
    const terminal = ledger.terminal;
    return (
      jointCashPolicyFields.every(
        (key) =>
          decimalIdentity(
            (terminal.cash_policy as Record<string, unknown>)[key],
          ) ===
          decimalIdentity(
            (ledger.terminal_policy as Record<string, unknown>)[key],
          ),
      ) &&
      [
        ["terminal_roe", "forecast_roe"],
        ["terminal_retention", "retention"],
        ["terminal_profit", "profit"],
        ["terminal_distribution", "distribution"],
        ["terminal_book", "opening_book"],
      ].every(
        ([a, b]) => decimalIdentity(ledger[a]) === decimalIdentity(terminal[b]),
      ) &&
      ledger.funding_status ===
        ([...ledger.rows, terminal].some(
          (row) =>
            (row as Record<string, unknown>).funding_status === "SHORTFALL",
        )
          ? "SHORTFALL"
          : "FUNDED")
    );
  });
}

/** Source-only presentation validation; never an approval or file-hash verifier. */
function jointCapitalSourceMatches(
  value: unknown,
  symbol: string,
  candidateBinding: unknown,
  descriptor: unknown,
  sources: EvidenceBinding[],
): value is JointCapitalReview {
  try {
    if (!record(value)) return false;
    const review = value;
    if (
      !review ||
      ![
        "joint-capital-review-v1",
        "joint-capital-cash-review-v2",
        "joint-capital-cash-review-v3",
      ].includes(String(review.schema_version)) ||
      review.symbol !== symbol ||
      review.action !== "no_order" ||
      review.status !== "CONDITIONAL_PATH_NOT_APPROVED" ||
      review.scope !== "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS" ||
      !binding(review.candidate_binding) ||
      !same(review.candidate_binding, candidateBinding) ||
      !binding(review.proposal_binding) ||
      !binding(review.policy_binding) ||
      ![review.proposal_binding, review.policy_binding].every((ref) =>
        sources.some((source) => same(source, ref)),
      ) ||
      !digest(review.input_descriptor_sha256) ||
      review.input_descriptor_sha256 !== descriptor ||
      typeof review.selected_choice !== "string" ||
      !review.selected_choice.trim() ||
      !(review.date_scope === "UNDATED_CONDITIONAL_MODEL"
        ? review.basis_at === null && review.valuation_at === null
        : review.date_scope === "DATED_CONDITIONAL_MODEL" &&
          [review.basis_at, review.valuation_at].every(
            (value) =>
              typeof value === "string" &&
              /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
              Number.isFinite(Date.parse(value)),
          )) ||
      !Array.isArray(review.scenarios) ||
      review.scenarios.length !== 3
    )
      return false;
    if (isJointCashReview(review)) {
      const closure = new Map<string, string>();
      for (const ref of sources) {
        if (
          !binding(ref) ||
          (closure.has(ref.path) && closure.get(ref.path) !== ref.sha256)
        )
          return false;
        closure.set(ref.path, ref.sha256);
      }
      return jointCashScenariosMatch(review);
    }
    return review.scenarios.every((item, index) => {
      if (
        !record(item) ||
        item.scenario !== ["bear", "base", "bull"][index] ||
        !finiteDecimal(item.valuation_per_share) ||
        !record(item.drivers) ||
        Object.keys(item.drivers).some(
          (key) => key !== "years" && !driverFields.includes(key),
        ) ||
        !driverFields.every((key) =>
          finiteDecimal((item.drivers as Record<string, unknown>)[key]),
        ) ||
        !Array.isArray(item.drivers.years) ||
        item.drivers.years.length !== 5 ||
        !item.drivers.years.every(
          (row, i) =>
            record(row) &&
            row.year === i + 1 &&
            finiteDecimal(row.revenue_growth) &&
            finiteDecimal(row.cost_ratio),
        )
      )
        return false;
      const ledger = item.ledger;
      return (
        record(ledger) &&
        ledger.scope === review.scope &&
        typeof ledger.cash_funding_status === "string" &&
        ["PASS", "FAIL"].includes(ledger.cash_funding_status) &&
        strings(ledger.limitations) &&
        jointTerminalFields.every((key) => finiteDecimal(ledger[key])) &&
        Array.isArray(ledger.forecast_roe) &&
        ledger.forecast_roe.length === 5 &&
        ledger.forecast_roe.every(finiteDecimal) &&
        Array.isArray(ledger.rows) &&
        ledger.rows.length === 5 &&
        ledger.rows.every(
          (row, i) =>
            record(row) &&
            row.year === i + 1 &&
            jointRowFields.every((key) => finiteDecimal(row[key])) &&
            typeof row.cash_funding_status === "string" &&
            ["PASS", "FAIL"].includes(row.cash_funding_status),
        )
      );
    });
  } catch {
    return false;
  }
}

/** Retains the full signing-context check before sharing source-only validation. */
export function jointCapitalReviewMatches(
  handoff: PolicyHandoff,
  symbol: string,
): boolean {
  try {
    if (
      !economicMaterialsMatch(handoff, symbol) ||
      handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED"
    )
      return false;
    const material = handoff.economic_review_materials!;
    return jointCapitalSourceMatches(
      material.joint_capital_review,
      symbol,
      handoff.candidate_binding,
      material.input_descriptor_sha256,
      material.source_bindings,
    );
  } catch {
    return false;
  }
}

/** Canonical decimal identity without rounding either side to a JS number. */
function decimalIdentity(value: unknown): string | null {
  if (!finiteDecimal(value)) return null;
  const [mantissa, power = "0"] = value.toLowerCase().split("e");
  const [whole, fraction = ""] = mantissa.replace(/^[+-]/, "").split(".");
  const digits = (whole + fraction).replace(/^0+/, "");
  if (!digits) return "0";
  const coefficient = digits.replace(/0+$/, "");
  const exponent =
    BigInt(power) -
    BigInt(fraction.length) +
    BigInt(digits.length - coefficient.length);
  return `${mantissa.startsWith("-") ? "-" : ""}${coefficient}e${exponent}`;
}

function calendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/** Preserve fractional seconds when comparing actual model instants. */
function instant(value: unknown): bigint | null {
  if (typeof value !== "string") return null;
  const parts =
    /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(
      value,
    );
  if (
    !parts ||
    !calendarDate(parts[1]) ||
    Number(parts[2]) > 23 ||
    Number(parts[3]) > 59 ||
    Number(parts[4]) > 59
  )
    return null;
  const offset = parts[6];
  if (
    offset !== "Z" &&
    (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4)) > 59)
  )
    return null;
  const milliseconds = Date.parse(
    `${parts[1]}T${parts[2]}:${parts[3]}:${parts[4]}${offset}`,
  );
  if (!Number.isFinite(milliseconds)) return null;
  return (
    BigInt(milliseconds) * BigInt(1000000) +
    BigInt((parts[5] ?? "").padEnd(9, "0"))
  );
}

const financialDayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function financialDay(value: string): string {
  const parts = Object.fromEntries(
    financialDayFormatter
      .formatToParts(new Date(value))
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function publicModelMatches(analysis: ValueResearchAnalysis): boolean {
  const context = analysis.review_binding?.model_context;
  const valuation = analysis.valuation;
  const route = analysis.model_applicability?.route;
  const joint = analysis.joint_capital_review;
  if (
    !record(context) ||
    !record(valuation) ||
    !record(route) ||
    !joint ||
    !["model_id", "model_version", "profile_id"].every(
      (key) =>
        typeof context[key] === "string" && !!(context[key] as string).trim(),
    ) ||
    !["research_case_sha256", "facts_sha256", "assumptions_sha256"].every(
      (key) => digest(context[key]),
    ) ||
    !calendarDate(context.research_as_of) ||
    context.research_as_of !== analysis.research_as_of ||
    context.model_id !== valuation.model_type ||
    context.model_version !== valuation.model_version ||
    context.model_id !== route.selected_model ||
    context.model_id !== route.model_type ||
    context.profile_id !== route.profile_id ||
    !record(valuation.assumptions)
  )
    return false;
  const timing = valuation.assumptions.valuation_timing;
  if (joint.date_scope === "UNDATED_CONDITIONAL_MODEL") {
    if (
      timing != null ||
      joint.basis_at !== null ||
      joint.valuation_at !== null
    )
      return false;
  } else {
    if (!record(timing)) return false;
    const basis = instant(joint.basis_at),
      at = instant(joint.valuation_at);
    if (
      basis === null ||
      at === null ||
      basis > at ||
      basis !== instant(timing.basis_at) ||
      at !== instant(timing.valuation_at) ||
      !calendarDate(analysis.valuation_date) ||
      analysis.valuation_date !== valuation.valuation_date ||
      typeof timing.valuation_at !== "string" ||
      financialDay(timing.valuation_at) !== analysis.valuation_date
    )
      return false;
  }
  if (!Array.isArray(analysis.scenarios)) return false;
  return joint.scenarios.every((row) => {
    const matches = analysis.scenarios.filter(
      (item) => item?.scenario === row.scenario,
    );
    const expected =
      matches.length === 1 ? decimalIdentity(matches[0].per_share_value) : null;
    return (
      expected !== null &&
      expected === decimalIdentity(row.valuation_per_share) &&
      expected ===
        decimalIdentity(
          valuation[
            `${row.scenario}_value` as
              "bear_value" | "base_value" | "bull_value"
          ],
        )
    );
  });
}

/** Public research identity checks; no fabricated signing handoff is involved. */
export function publicJointCapitalReviewMatches(
  analysis: ValueResearchAnalysis,
  symbol: string,
): boolean {
  try {
    const reviewBinding = analysis.review_binding;
    if (
      analysis.schema_version !== "value-research-analysis-v1" ||
      analysis.symbol !== symbol ||
      analysis.action !== "no_order" ||
      analysis.status !== "CONDITIONAL_ANALYSIS_VERIFIED" ||
      analysis.arithmetic_complete !== true ||
      analysis.economic_assumptions_reviewed !== false ||
      analysis.action_admitted !== false ||
      analysis.strategy_admitted !== false ||
      analysis.price_comparison_eligible !== false ||
      !digest(analysis.input_descriptor_sha256) ||
      !record(reviewBinding) ||
      !binding(reviewBinding.candidate_binding) ||
      !record(reviewBinding.model_context) ||
      reviewBinding.model_context.input_descriptor_sha256 !==
        analysis.input_descriptor_sha256 ||
      !Array.isArray(analysis.source_bindings) ||
      !analysis.source_bindings.every(binding) ||
      !analysis.source_bindings.some((source) =>
        same(source, reviewBinding.candidate_binding),
      )
    )
      return false;
    // Reject contradictory public assessment identities if one is supplied.
    const assessment = analysis.economic_assessment;
    if (
      assessment &&
      (assessment.symbol !== symbol ||
        assessment.action !== "no_order" ||
        assessment.input_descriptor_sha256 !==
          analysis.input_descriptor_sha256 ||
        assessment.primary_valuation_usable !== false ||
        assessment.economic_assumptions_reviewed !== false ||
        (assessment.review_binding &&
          (!same(
            assessment.review_binding.candidate_binding,
            reviewBinding.candidate_binding,
          ) ||
            !same(
              assessment.review_binding.model_context,
              reviewBinding.model_context,
            ))))
    )
      return false;
    ordered(reviewBinding.model_context);
    return (
      jointCapitalSourceMatches(
        analysis.joint_capital_review,
        symbol,
        reviewBinding.candidate_binding,
        analysis.input_descriptor_sha256,
        analysis.source_bindings,
      ) && publicModelMatches(analysis)
    );
  } catch {
    return false;
  }
}

/** Exact native appendix identity only; never recalculates cash or approves research. */
export function sourceNativeCashReviewMatches(
  analysis: ValueResearchAnalysis,
  symbol: string,
): boolean {
  try {
    const native = analysis.source_native_cash_review;
    const valuation = analysis.valuation;
    const review = analysis.review_binding;
    if (
      !native ||
      !valuation ||
      !review ||
      analysis.symbol !== symbol ||
      analysis.schema_version !== "value-research-analysis-v1" ||
      analysis.action !== "no_order" ||
      analysis.status !== "CONDITIONAL_ANALYSIS_VERIFIED" ||
      analysis.arithmetic_complete !== true ||
      analysis.economic_assumptions_reviewed !== false ||
      analysis.action_admitted !== false ||
      analysis.strategy_admitted !== false ||
      analysis.price_comparison_eligible !== false ||
      analysis.approval_changed !== false ||
      native.schema_version !== "source-native-economic-review-materials-v1" ||
      native.symbol !== symbol ||
      native.scope !== "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_G3" ||
      native.action !== "no_order" ||
      native.cash_branch !== "TIMING_DELAY" ||
      native.authenticated_consumption_supported !== false ||
      !["LOW", "低"].includes(native.confidence) ||
      !["LOW", "低"].includes(valuation.confidence ?? "") ||
      valuation.symbol !== symbol ||
      valuation.status !== "conditional_research_only" ||
      native.research_admitted !== false ||
      native.primary_registered !== false ||
      native.approval_changed !== false ||
      native.strict_contemporaneous_pit !== "NOT_PROVEN" ||
      !binding(native.candidate_binding) ||
      !same(native.candidate_binding, review.candidate_binding) ||
      !record(native.model_context) ||
      !same(native.model_context, review.model_context) ||
      !["model_id", "model_version", "profile_id"].every(
        (key) =>
          typeof native.model_context[key] === "string" &&
          !!(native.model_context[key] as string).trim(),
      ) ||
      !digest(analysis.input_descriptor_sha256) ||
      native.model_context.input_descriptor_sha256 !==
        analysis.input_descriptor_sha256 ||
      !["research_case_sha256", "facts_sha256", "assumptions_sha256"].every(
        (key) => digest(native.model_context[key]),
      ) ||
      native.model_context.model_id !== valuation.model_type ||
      native.model_context.model_version !== valuation.model_version ||
      native.model_context.profile_id !==
        analysis.model_applicability?.route?.profile_id ||
      native.model_context.model_id !==
        analysis.model_applicability?.route?.selected_model ||
      native.model_context.model_id !==
        analysis.model_applicability?.route?.model_type ||
      !calendarDate(native.model_context.research_as_of) ||
      native.model_context.research_as_of !== analysis.research_as_of ||
      !Array.isArray(analysis.source_bindings) ||
      !analysis.source_bindings.every(binding) ||
      !Array.isArray(native.source_bindings) ||
      !native.source_bindings.length ||
      !native.source_bindings.every(binding)
    )
      return false;
    const closure = new Map<string, string>();
    for (const ref of analysis.source_bindings) {
      if (closure.has(ref.path) && closure.get(ref.path) !== ref.sha256)
        return false;
      closure.set(ref.path, ref.sha256);
    }
    const bound = (ref: unknown) =>
      binding(ref) && closure.get(ref.path) === ref.sha256;
    if (
      !bound(native.candidate_binding) ||
      !native.source_bindings.every(bound)
    )
      return false;
    const pit = native.point_in_time,
      timing = native.valuation_timing;
    const available = instant(pit?.available_at),
      computed = instant(pit?.computed_at);
    const basis = instant(timing?.basis_at),
      at = instant(timing?.valuation_at);
    const consumedTiming = valuation.assumptions?.valuation_timing;
    if (
      !pit ||
      !timing ||
      native.valuation_timing_status !== "EXPLICIT_MODEL_TIMING" ||
      !calendarDate(pit.report_period) ||
      !calendarDate(pit.research_as_of) ||
      !calendarDate(pit.valuation_date) ||
      pit.valuation_date !== analysis.valuation_date ||
      pit.valuation_date !== valuation.valuation_date ||
      pit.research_as_of !== analysis.research_as_of ||
      available === null ||
      computed === null ||
      available > computed ||
      available !== instant(analysis.available_at) ||
      computed !== instant(analysis.computed_at) ||
      basis === null ||
      at === null ||
      basis > at ||
      !consumedTiming ||
      basis !== instant(consumedTiming.basis_at) ||
      at !== instant(consumedTiming.valuation_at) ||
      financialDay(timing.valuation_at) !== pit.valuation_date ||
      !Array.isArray(timing.evidence_refs) ||
      !timing.evidence_refs.length ||
      !timing.evidence_refs.every(
        (ref) => bound(ref) && typeof ref.id === "string" && !!ref.id.trim(),
      )
    )
      return false;
    const plan = native.joint_assumptions;
    if (
      !plan ||
      plan.action !== "no_order" ||
      plan.horizon !== 5 ||
      ![
        plan.explicit_retention,
        plan.incremental_parent_cash_yield,
        plan.ke,
        plan.TIMING_DELAY?.withheld_fraction,
      ].every(finiteDecimal) ||
      !same(plan.TIMING_DELAY?.withheld_years, [1]) ||
      plan.TIMING_DELAY?.release !==
        "all opening incremental delayed asset in year 2; no fresh withholding after year 1" ||
      native.historical_cash_bridge?.unit !== "CNY" ||
      !strings(native.historical_cash_bridge.unknowns) ||
      !record(native.scenarios) ||
      Object.keys(native.scenarios).sort().join(",") !== "base,bear,bull" ||
      !Array.isArray(analysis.scenarios) ||
      analysis.scenarios.length !== 3
    )
      return false;
    return (["bear", "base", "bull"] as const).every((name) => {
      const scenario = native.scenarios[name];
      const matches = analysis.scenarios.filter((row) => row.scenario === name);
      const expected = decimalIdentity(valuation[`${name}_value`]);
      return (
        expected !== null &&
        matches.length === 1 &&
        record(scenario) &&
        expected === decimalIdentity(scenario.per_share_value) &&
        expected === decimalIdentity(matches[0].per_share_value) &&
        record(scenario.inputs) &&
        same(scenario.inputs, matches[0].inputs) &&
        decimalIdentity(scenario.inputs.cost_of_equity) ===
          decimalIdentity(plan.ke) &&
        decimalIdentity(scenario.inputs.retention) ===
          decimalIdentity(plan.explicit_retention) &&
        [
          "cost_of_equity",
          "retention",
          "terminal_growth",
          "terminal_roe",
        ].every((key) => finiteDecimal(scenario.inputs[key])) &&
        Array.isArray(scenario.inputs.forecast_roes) &&
        scenario.inputs.forecast_roes.length === 5 &&
        scenario.inputs.forecast_roes.every(finiteDecimal) &&
        Array.isArray(scenario.cash_ledger) &&
        scenario.cash_ledger.length === 5 &&
        scenario.cash_ledger.every(
          (row, index) =>
            record(row) &&
            row.year === index + 1 &&
            nativeCashFields.every((field) => finiteDecimal(row[field])) &&
            decimalIdentity(row.roe) ===
              decimalIdentity(
                (scenario.inputs.forecast_roes as string[])[index],
              ),
        )
      );
    });
  } catch {
    return false;
  }
}

/** Presentation identity check only; source/hash verification stays server-owned. */
export function economicMaterialsMatch(
  handoff: PolicyHandoff,
  symbol: string,
): boolean {
  try {
    if (
      handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED" ||
      handoff.symbol !== symbol ||
      handoff.action !== "no_order" ||
      handoff.verification.approval_changed !== false ||
      handoff.verification.research_admitted !== false
    )
      return false;
    const material = handoff.economic_review_materials;
    if (
      !material ||
      material.schema_version !== "value-economic-review-materials-v1" ||
      material.symbol !== symbol ||
      material.action !== "no_order" ||
      !["PENDING_ECONOMIC_JUDGMENT", "STRESS_ONLY_NOT_PRIMARY"].includes(
        material.status,
      ) ||
      material.primary_valuation_usable !== false ||
      material.approval_changed !== false ||
      !binding(material.candidate_binding) ||
      !binding(handoff.candidate_binding) ||
      !same(material.candidate_binding, handoff.candidate_binding) ||
      !record(material.model_context) ||
      !record(handoff.model_context) ||
      !same(material.model_context, handoff.model_context) ||
      !digest(material.input_descriptor_sha256) ||
      material.input_descriptor_sha256 !==
        handoff.model_context.input_descriptor_sha256 ||
      !digest(material.valuation_artifact_sha256) ||
      material.valuation_artifact_sha256 !==
        handoff.valuation_artifact_sha256 ||
      !digest(material.assessment_sha256) ||
      !digest(material.materials_sha256) ||
      !Array.isArray(material.source_bindings) ||
      !material.source_bindings.length ||
      !material.source_bindings.every(binding)
    )
      return false;
    const assessment = material.economic_assessment;
    if (
      !assessment ||
      assessment.schema_version !== "value-economic-assessment-v1" ||
      assessment.symbol !== symbol ||
      assessment.action !== "no_order" ||
      assessment.primary_valuation_usable !== false ||
      assessment.economic_assumptions_reviewed !== false ||
      assessment.approval_changed !== false ||
      assessment.strategy_admitted !== false ||
      assessment.action_admitted !== false ||
      assessment.assessment_sha256 !== material.assessment_sha256 ||
      assessment.input_descriptor_sha256 !== material.input_descriptor_sha256 ||
      !record(assessment.review_binding) ||
      !same(
        assessment.review_binding.candidate_binding,
        handoff.candidate_binding,
      ) ||
      !same(assessment.review_binding.model_context, handoff.model_context) ||
      !strings(assessment.blockers) ||
      (assessment.model_applicability?.assessment === "STRESS_ONLY") !==
        (material.status === "STRESS_ONLY_NOT_PRIMARY")
    )
      return false;
    const bridge = assessment.accounting_bridge_review;
    if (
      bridge &&
      (bridge.schema_version !== "economic-review-bundle-v1" ||
        bridge.symbol !== symbol ||
        bridge.action !== "no_order" ||
        bridge.primary_valuation_usable !== false ||
        bridge.economic_approval_granted !== false ||
        bridge.input_descriptor_sha256 !== material.input_descriptor_sha256 ||
        !digest(bridge.bundle_sha256) ||
        !strings(bridge.unknown_fields) ||
        !Array.isArray(bridge.source_bindings) ||
        !bridge.source_bindings.every(binding) ||
        !Array.isArray(bridge.bridge_results) ||
        !bridge.bridge_results.every(
          (row) =>
            record(row) &&
            binding(row.source_binding) &&
            record(row.terms) &&
            Object.values(row.terms).every(
              (value) => typeof value === "string",
            ) &&
            typeof row.source_url === "string" &&
            Array.isArray(row.physical_pages) &&
            row.physical_pages.every(
              (page) => Number.isInteger(page) && page > 0,
            ),
        ))
    )
      return false;
    const questions = handoff.review_questions;
    if (
      !Array.isArray(material.groups) ||
      !Array.isArray(questions) ||
      material.groups.length !== questions.length ||
      new Set(material.groups.map((group) => group.id)).size !==
        material.groups.length
    )
      return false;
    return material.groups.every((group, index) => {
      const question = questions[index];
      return (
        record(group) &&
        typeof group.id === "string" &&
        !!group.id &&
        typeof group.title === "string" &&
        !!group.title &&
        record(question) &&
        group.id === question.id &&
        strings(group.field_paths) &&
        same(group.field_paths, question.field_paths) &&
        strings(group.verified_observations) &&
        strings(group.conditional_assumptions) &&
        strings(group.counter_evidence) &&
        strings(group.judgment_questions) &&
        Array.isArray(group.evidence_refs) &&
        group.evidence_refs.every(
          (ref) =>
            binding(ref) &&
            material.source_bindings.some((source) => same(source, ref)),
        )
      );
    });
  } catch {
    return false;
  }
}

export type PolicySelection = {
  effective_from: string;
  effective_through: string;
  rationale: string;
  dividend_coverage_risk: string;
  rules: PolicyRule[];
};

export type PolicyPreview = {
  action: "no_order";
  status: string;
  scope: "ISOLATED_TEST" | "LOCAL_USER_POLICY";
  preview_id: string;
  expires_at: string;
  preparation: {
    status: string;
    blockers: string[];
    existing_research_blockers: string[];
    draft_prices: Record<string, string | null>;
  };
};

export type PolicyRegistration = {
  action: "no_order";
  status: "REGISTERED";
  scope: string;
  preview_id: string;
  conditional_plan: Record<string, unknown>;
  registered_policy: {
    draft: PolicySelection;
    draft_prices: Record<string, string | null>;
    price_scope: "PRIVATE_POLICY_ARITHMETIC_NOT_ADMITTED";
  };
  formal_eligibility: false;
  portfolio_eligibility: null;
  research_approval_changed: false;
  production_published: false;
};

export type PolicyStatus =
  | PolicyRegistration
  | {
      action: "no_order";
      status: "NOT_REGISTERED" | "REVIEW_REQUIRED";
      scope: string;
      detail?: string;
      conditional_plan: null;
    };

export type ValuePolicyTransport = {
  handoff?(symbol: string, boundDraft?: boolean): Promise<PolicyHandoff>;
  status(symbol: string): Promise<PolicyStatus>;
  preview(symbol: string, selection: PolicySelection): Promise<PolicyPreview>;
  confirm(
    symbol: string,
    body: { preview_id: string; acknowledged: true; note: string },
  ): Promise<PolicyRegistration>;
};

/** Root supplies headers from the existing authenticated session. */
export function createValuePolicyTransport(
  authenticatedHeaders: () => Promise<Record<string, string>>,
): ValuePolicyTransport {
  async function post<T>(symbol: string, operation: string, body: unknown) {
    const response = await fetch(
      `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/${operation}`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          ...(await authenticatedHeaders()),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      },
    );
    const result = await response.json();
    if (!response.ok || result.action !== "no_order")
      throw new Error(result.detail ?? "政策操作未完成，请重新授权或重试");
    return result as T;
  }
  return {
    handoff: async (symbol, boundDraft = false) => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/handoff${boundDraft ? "?bound_draft=true" : ""}`,
        {
          credentials: "same-origin",
          headers: await authenticatedHeaders(),
          cache: "no-store",
        },
      );
      const result = await response.json();
      if (!response.ok || result.action !== "no_order")
        throw new Error(result.detail ?? "审核交接读取失败");
      return result as PolicyHandoff;
    },
    status: async (symbol) => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/status`,
        {
          credentials: "same-origin",
          headers: await authenticatedHeaders(),
          cache: "no-store",
        },
      );
      const result = await response.json();
      if (!response.ok || result.action !== "no_order")
        throw new Error(result.detail ?? "私人政策读取失败，请重新授权或重试");
      return result as PolicyStatus;
    },
    preview: (symbol, selection) =>
      post<PolicyPreview>(symbol, "preview", selection),
    confirm: (symbol, body) =>
      post<PolicyRegistration>(symbol, "confirm", body),
  };
}

export function fractionFromPercent(percent: string): string {
  if (!/^(?:0|[1-9]\d{0,3})(?:\.\d{1,6})?$/.test(percent))
    throw new Error("比例须为大于零的百分数，最多六位小数");
  const [whole, decimal = ""] = percent.split(".");
  const digits = whole.padStart(3, "0");
  const fraction = `${digits.slice(0, -2)}.${digits.slice(-2)}${decimal}`;
  if (!/[1-9]/.test(fraction)) throw new Error("比例必须大于零");
  return fraction;
}
