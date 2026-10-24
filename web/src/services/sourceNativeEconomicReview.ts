export type EconomicBinding = { path: string; sha256: string };
export type EconomicReview = {
  schema_version: "source-native-economic-review-v1";
  status: "CONDITIONAL_ECONOMIC_RESEARCH";
  symbol: string;
  candidate_binding: EconomicBinding;
  confidence: "LOW";
  g3_status: "NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE";
  current_g3_status: "NOT_QUERIED";
  action: "no_order";
  share_basis: { ordinary_shares: string; financial_basis: string };
  scenarios: {
    scenario: "bear" | "base" | "bull";
    original: {
      per_historical_share_cny: string;
      candidate_per_historical_share_cny: string;
      matches_candidate_at_recorded_precision: true;
      ddm_terminal_fraction: string;
      ri_terminal_fraction: string;
    };
    first_year_boundary: {
      cash_only_delay_boundary_fraction: string;
      original_cash_above_floor_cny: string;
      boundary_within_zero_one: boolean;
      status: "CASH_ONLY_FIRST_YEAR_IDENTITY";
    };
    ke_plus_200bp: {
      status: "CONDITIONAL_KERNEL_SENSITIVITY" | "UNSUPPORTED";
      alternative_candidate_verified: false;
      delta_basis_points: 200;
      result?: { per_historical_share_cny: string };
    };
  }[];
  five_groups: {
    id: string;
    title: string;
    interpretation: string;
    approval_status: "PENDING_NOT_APPROVED";
  }[];
  source_bindings: EconomicBinding[];
};

const object = (v: any) => !!v && typeof v === "object" && !Array.isArray(v);
const number = (v: any) =>
  typeof v === "string" &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(v) &&
  Number.isFinite(Number(v));
const binding = (v: any) =>
  object(v) &&
  typeof v.path === "string" &&
  !!v.path &&
  !/^(?:[\\/]|[a-z]+:)/i.test(v.path) &&
  !v.path.split(/[\\/]/).includes("..") &&
  /^[a-f0-9]{64}$/.test(v.sha256);

export function verifiedEconomicReview(
  v: any,
  symbol: string,
  expected: EconomicBinding,
): v is EconomicReview {
  if (
    !object(v) ||
    v.schema_version !== "source-native-economic-review-v1" ||
    v.status !== "CONDITIONAL_ECONOMIC_RESEARCH" ||
    v.symbol !== symbol ||
    v.scope !== "PENDING_NATIVE_CANDIDATE_NOT_PRIMARY_OR_CURRENT_VALUATION" ||
    v.action !== "no_order" ||
    v.confidence !== "LOW" ||
    v.position_guidance !== null ||
    v.normalized_parent_profit_cny !== null ||
    v.current_g3_status !== "NOT_QUERIED" ||
    v.g3_status !== "NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE" ||
    !binding(v.candidate_binding) ||
    v.candidate_binding.path !== expected.path ||
    v.candidate_binding.sha256 !== expected.sha256 ||
    [
      "approval_changed",
      "research_admitted",
      "price_admitted",
      "formal_eligibility",
      "strategy_approved",
      "canonical_written",
      "registered_current_case_changed",
    ].some((k) => v[k] !== false)
  )
    return false;
  if (
    !object(v.share_basis) ||
    !number(v.share_basis.ordinary_shares) ||
    v.share_basis.current_shares !== null ||
    !/^\d{4}-\d{2}-\d{2}$/.test(v.share_basis.financial_basis) ||
    v.share_basis.scope !==
      "BOUND_HISTORICAL_MODEL_DENOMINATOR_NOT_CURRENT_SHARES" ||
    !Array.isArray(v.source_bindings) ||
    !v.source_bindings.length ||
    !v.source_bindings.every(binding)
  )
    return false;
  if (
    !Array.isArray(v.scenarios) ||
    v.scenarios.length !== 3 ||
    new Set(v.scenarios.map((s: any) => s?.scenario)).size !== 3 ||
    !v.scenarios.every(
      (s: any) =>
        object(s) &&
        ["bear", "base", "bull"].includes(s.scenario) &&
        object(s.original) &&
        s.original.matches_candidate_at_recorded_precision === true &&
        [
          "per_historical_share_cny",
          "candidate_per_historical_share_cny",
          "ddm_terminal_fraction",
          "ri_terminal_fraction",
        ].every((k) => number(s.original[k])) &&
        object(s.first_year_boundary) &&
        s.first_year_boundary.status === "CASH_ONLY_FIRST_YEAR_IDENTITY" &&
        typeof s.first_year_boundary.boundary_within_zero_one === "boolean" &&
        number(s.first_year_boundary.cash_only_delay_boundary_fraction) &&
        number(s.first_year_boundary.original_cash_above_floor_cny) &&
        object(s.ke_plus_200bp) &&
        s.ke_plus_200bp.alternative_candidate_verified === false &&
        s.ke_plus_200bp.delta_basis_points === 200 &&
        (s.ke_plus_200bp.status === "UNSUPPORTED" ||
          (s.ke_plus_200bp.status === "CONDITIONAL_KERNEL_SENSITIVITY" &&
            object(s.ke_plus_200bp.result) &&
            number(s.ke_plus_200bp.result.per_historical_share_cny))),
    )
  )
    return false;
  return (
    Array.isArray(v.five_groups) &&
    v.five_groups.length === 5 &&
    new Set(v.five_groups.map((g: any) => g?.id)).size === 5 &&
    v.five_groups.every(
      (g: any) =>
        object(g) &&
        [
          "EARNINGS",
          "DISTRIBUTION",
          "DURATION",
          "COST_TERMINAL",
          "EVENT_MODEL",
        ].includes(g.id) &&
        typeof g.title === "string" &&
        !!g.title.trim() &&
        typeof g.interpretation === "string" &&
        !!g.interpretation.trim() &&
        g.approval_status === "PENDING_NOT_APPROVED",
    )
  );
}
