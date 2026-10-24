export type EconomicBinding = { path: string; sha256: string };
type JointCashDiagnostic = {
  status:
    | "UNSUPPORTED"
    | "INHERITED_PAYOUT_INFEASIBLE"
    | "FIVE_YEAR_CONDITIONAL_PLAN_FEASIBLE";
  reason?: string;
  scope?: "MECHANICAL_COUNTEREXAMPLE_NOT_FORECAST_OR_ACCOUNTING_FACT";
  action?: "no_order";
  disclosed_annual_growth?: string;
  first_cash_failure_year?: number | null;
  first_retained_profit_failure_year?: number | null;
  terminal_status?: "UNSUPPORTED_NO_RELEASE_NO_FULL_PAYOUT_TERMINAL";
  rows: {
    year: number;
    P: string;
    M: string;
    U: string;
    C: string;
    B: string;
    D: string;
    cash_floor: string;
    cash_margin: string;
    retained_profit: string;
    status: "UNFUNDED_PLAN" | "CONDITIONAL_PLAN_FEASIBLE";
    D_scope: "PLANNED_NOT_PAID_NO_AUTOMATIC_DIVIDEND_CUT";
    cash_constraint_failed: boolean;
    retained_constraint_failed: boolean;
  }[];
};
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
  joint_adverse_cash?: JointCashDiagnostic;
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

function consistentCashConstraint(r: any): boolean {
  const values = [r.C, r.cash_floor, r.cash_margin, r.retained_profit];
  if (!values.every((v) => number(v) && v.length <= 200)) return false;
  const scale = Math.max(...values.map((v) => (v.split(".")[1] ?? "").length));
  const units = (v: string) => {
    const [whole, fraction = ""] = v.split(".");
    return BigInt(whole + fraction.padEnd(scale, "0"));
  };
  const [cash, floor, margin, retained] = values.map(units);
  return (
    cash - floor === margin &&
    r.cash_constraint_failed === margin < BigInt(0) &&
    r.retained_constraint_failed === retained < BigInt(0)
  );
}

function verifiedJointCash(v: any): boolean {
  if (!object(v) || !Array.isArray(v.rows)) return false;
  if (v.status === "UNSUPPORTED")
    return (
      typeof v.reason === "string" && !!v.reason.trim() && v.rows.length === 0
    );
  const year = (n: any) => Number.isInteger(n) && n >= 1 && n <= 5;
  return (
    [
      "INHERITED_PAYOUT_INFEASIBLE",
      "FIVE_YEAR_CONDITIONAL_PLAN_FEASIBLE",
    ].includes(v.status) &&
    v.scope === "MECHANICAL_COUNTEREXAMPLE_NOT_FORECAST_OR_ACCOUNTING_FACT" &&
    v.action === "no_order" &&
    number(v.disclosed_annual_growth) &&
    v.terminal_status === "UNSUPPORTED_NO_RELEASE_NO_FULL_PAYOUT_TERMINAL" &&
    [v.first_cash_failure_year, v.first_retained_profit_failure_year].every(
      (n) => n === null || year(n),
    ) &&
    v.rows.length > 0 &&
    v.rows.length <= 5 &&
    v.rows.every(
      (r: any, i: number) =>
        object(r) &&
        r.year === i + 1 &&
        [
          "P",
          "M",
          "U",
          "C",
          "B",
          "D",
          "cash_floor",
          "cash_margin",
          "retained_profit",
        ].every((k) => number(r[k])) &&
        r.D_scope === "PLANNED_NOT_PAID_NO_AUTOMATIC_DIVIDEND_CUT" &&
        typeof r.cash_constraint_failed === "boolean" &&
        typeof r.retained_constraint_failed === "boolean" &&
        consistentCashConstraint(r) &&
        r.status ===
          (r.cash_constraint_failed || r.retained_constraint_failed
            ? "UNFUNDED_PLAN"
            : "CONDITIONAL_PLAN_FEASIBLE"),
    ) &&
    v.rows
      .slice(0, -1)
      .every((r: any) => r.status === "CONDITIONAL_PLAN_FEASIBLE") &&
    v.first_cash_failure_year ===
      (v.rows.find((r: any) => r.cash_constraint_failed)?.year ?? null) &&
    v.first_retained_profit_failure_year ===
      (v.rows.find((r: any) => r.retained_constraint_failed)?.year ?? null) &&
    (v.status === "INHERITED_PAYOUT_INFEASIBLE"
      ? v.rows.at(-1).status === "UNFUNDED_PLAN" &&
        [v.first_cash_failure_year, v.first_retained_profit_failure_year].some(
          (n) => n === v.rows.length,
        )
      : v.rows.length === 5 &&
        v.rows.at(-1).status === "CONDITIONAL_PLAN_FEASIBLE" &&
        v.first_cash_failure_year === null &&
        v.first_retained_profit_failure_year === null)
  );
}

export function verifiedEconomicReview(
  v: any,
  symbol: string,
  expected: EconomicBinding,
): v is EconomicReview {
  if (
    v?.joint_adverse_cash !== undefined &&
    !verifiedJointCash(v.joint_adverse_cash)
  )
    return false;
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
