export type EconomicBinding = { path: string; sha256: string };
export type ProductOperatingResearch = {
  schema_version: "product-operating-research-v1";
  status: "CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED";
  symbol: "600519";
  policy_binding: EconomicBinding;
  input_available_at: string;
  evaluated_at: string;
  annual_drivers: Record<
    "bear" | "base" | "bull",
    {
      moutai_volume_growth: string;
      moutai_realization_growth: string;
      series_volume_growth: string;
      series_realization_growth: string;
      other_revenue_growth: string;
      cost_ratio: string;
    }[]
  >;
  product_source: {
    period: "H12026";
    source_url: string;
    physical_page: 8;
    product_revenue_cny: { moutai: string; series: string; other: string };
    source_binding: EconomicBinding;
  };
  scenarios: {
    scenario: "bear" | "base" | "bull";
    per_historical_share_cny: string;
    ke_plus_200bp_per_historical_share_cny: string;
    operating_rows: {
      year: number;
      revenue: string;
      legacy_ex_parent: string;
    }[];
    annual_cash_rows: {
      year: number;
      profit: string;
      cash_close: string;
      dividend_paid: string;
      book_close: string;
    }[];
    cash_replay_scope: "ALL_TRANSITIONS_VERIFIED_BY_EXISTING_NATIVE_KERNEL";
  }[];
};
export type ReplacementBearComparison = {
  schema_version: "source-native-replacement-bear-comparison-v1";
  status: "VERIFIED_BOUND_RESEARCH_COMPARISON";
  baseline_candidate_binding: EconomicBinding;
  replacement_candidate_binding: EconomicBinding;
  evidence_binding: EconomicBinding;
  observed_at: string;
  replacement_generated_at: string;
  input_available_at: string;
  original_bear: { per_historical_share_cny: string };
  replacement_bear: { per_historical_share_cny: string };
  difference_per_historical_share_cny: string;
  operating_rows: { year: number; revenue: string; legacy_ex_parent: string }[];
  annual_cash_rows: {
    year: number;
    profit: string;
    cash_close: string;
    book_close: string;
    dividend_paid: string;
  }[];
  derived_historical_ratios: {
    mixed_realization_factor: string;
    h1_cost_ratio: string;
  };
  negative_conditions: string[];
  source_bindings: EconomicBinding[];
};
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
  replacement_bear?: ReplacementBearComparison;
  product_operating_research?: unknown;
  unsupported_challenges?: {
    id: string;
    status: "UNSUPPORTED";
    reason: string;
  }[];
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

export function verifiedProductOperatingResearch(
  v: any,
  parent: any,
): v is ProductOperatingResearch {
  const names = ["bear", "base", "bull"];
  const drivers = [
    "moutai_volume_growth",
    "moutai_realization_growth",
    "series_volume_growth",
    "series_realization_growth",
    "other_revenue_growth",
    "cost_ratio",
  ];
  return (
    object(parent) &&
    parent.symbol === "600519" &&
    Array.isArray(parent.source_bindings) &&
    object(v) &&
    v.schema_version === "product-operating-research-v1" &&
    v.status === "CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED" &&
    v.symbol === "600519" &&
    v.action === "no_order" &&
    v.confidence === "LOW" &&
    v.assumption_scope === "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST" &&
    v.formal_eligibility === false &&
    v.research_admitted === false &&
    v.price_admitted === false &&
    v.normalized_parent_profit_cny === null &&
    binding(v.policy_binding) &&
    instant(v.input_available_at) !== undefined &&
    instant(v.evaluated_at) !== undefined &&
    instant(v.input_available_at)! <= instant(v.evaluated_at)! &&
    instant(v.evaluated_at)! <= BigInt(Date.now()) * BigInt(1000) &&
    Array.isArray(v.source_bindings) &&
    v.source_bindings.every(binding) &&
    v.source_bindings.every((ref: any) =>
      parent.source_bindings.some(
        (r: any) => r.path === ref.path && r.sha256 === ref.sha256,
      ),
    ) &&
    [v.policy_binding, v.product_source?.source_binding].every(
      (ref) =>
        binding(ref) &&
        v.source_bindings.some(
          (r: any) => r.path === ref.path && r.sha256 === ref.sha256,
        ),
    ) &&
    object(v.product_source) &&
    v.product_source.period === "H12026" &&
    v.product_source.physical_page === 8 &&
    v.product_source.source_url ===
      "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF" &&
    ["moutai", "series", "other"].every((key) =>
      number(v.product_source.product_revenue_cny?.[key]),
    ) &&
    object(v.annual_drivers) &&
    names.every(
      (name) =>
        Array.isArray(v.annual_drivers[name]) &&
        v.annual_drivers[name].length === 5 &&
        v.annual_drivers[name].every(
          (r: any) => object(r) && drivers.every((key) => number(r[key])),
        ),
    ) &&
    Array.isArray(v.scenarios) &&
    v.scenarios.length === 3 &&
    names.every(
      (name) =>
        v.scenarios.filter((r: any) => r?.scenario === name).length === 1,
    ) &&
    v.scenarios.every(
      (r: any) =>
        object(r) &&
        [
          r.per_historical_share_cny,
          r.ke_plus_200bp_per_historical_share_cny,
        ].every(number) &&
        r.cash_replay_scope ===
          "ALL_TRANSITIONS_VERIFIED_BY_EXISTING_NATIVE_KERNEL" &&
        Array.isArray(r.operating_rows) &&
        r.operating_rows.length === 5 &&
        r.operating_rows.every(
          (row: any, i: number) =>
            object(row) &&
            row.year === i + 1 &&
            [row.revenue, row.legacy_ex_parent].every(number),
        ) &&
        Array.isArray(r.annual_cash_rows) &&
        r.annual_cash_rows.length === 5 &&
        r.annual_cash_rows.every(
          (row: any, i: number) =>
            object(row) &&
            row.year === i + 1 &&
            [
              row.profit,
              row.cash_close,
              row.dividend_paid,
              row.book_close,
            ].every(number),
        ),
    )
  );
}

const calendarDay = (value: any): boolean => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  return (
    year >= 1 &&
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
};

// Calendar-valid ISO instants, retaining the producer's microsecond precision.
function instant(value: any): bigint | undefined {
  if (typeof value !== "string") return undefined;
  const m =
    /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(
      value,
    );
  if (!m || !calendarDay(m[1])) return undefined;
  const [hour, minute, second] = m.slice(2, 5).map(Number);
  if (hour > 23 || minute > 59 || second > 59) return undefined;
  const [year, month, day] = m[1].split("-").map(Number);
  const d = new Date(0);
  d.setUTCFullYear(year, month - 1, day);
  d.setUTCHours(hour, minute, second, 0);
  let offset = 0;
  if (m[6] !== "Z") {
    const hours = Number(m[6].slice(1, 3)),
      minutes = Number(m[6].slice(4, 6));
    if (hours > 23 || minutes > 59) return undefined;
    offset = (hours * 60 + minutes) * (m[6][0] === "+" ? 1 : -1);
  }
  return (
    BigInt(d.getTime()) * BigInt(1000) +
    BigInt((m[5] ?? "").padEnd(6, "0")) -
    BigInt(offset) * BigInt(60000000)
  );
}

function consistentObservation(v: any, parent: any): boolean {
  const observed = instant(v.observed_at),
    generated = instant(v.replacement_generated_at),
    available = instant(v.input_available_at),
    evaluated = instant(parent.evaluated_at);
  return (
    observed !== undefined &&
    generated !== undefined &&
    available !== undefined &&
    evaluated !== undefined &&
    observed === generated &&
    observed === available &&
    observed <= evaluated &&
    evaluated <= BigInt(Date.now()) * BigInt(1000) &&
    calendarDay(parent.point_in_time?.report_period) &&
    parent.share_basis?.financial_basis === parent.point_in_time.report_period
  );
}

export function verifiedReplacementBear(
  v: any,
  parent: any,
): v is ReplacementBearComparison {
  const same = (a: any, b: any) =>
    binding(a) && binding(b) && a.path === b.path && a.sha256 === b.sha256;
  const refs = (list: any) =>
    Array.isArray(list) &&
    list.length > 0 &&
    list.every(binding) &&
    new Set(list.map((r: any) => r.path)).size === list.length;
  if (
    !object(v) ||
    !object(parent) ||
    !Array.isArray(parent.scenarios) ||
    v.schema_version !== "source-native-replacement-bear-comparison-v1" ||
    v.status !== "VERIFIED_BOUND_RESEARCH_COMPARISON" ||
    v.symbol !== parent.symbol ||
    v.confidence !== "LOW" ||
    v.action !== "no_order" ||
    v.scope !==
      "CONDITIONAL_OPERATING_EROSION_NOT_FULL_DOWNSIDE_OR_ENTRY_PRICE" ||
    v.base_bull_exactly_preserved !== true ||
    v.normalized_parent_profit_cny !== null ||
    [
      "research_admitted",
      "price_admitted",
      "formal_eligibility",
      "strategy_approved",
    ].some((k) => v[k] !== false) ||
    !same(v.baseline_candidate_binding, parent.candidate_binding) ||
    !binding(v.replacement_candidate_binding) ||
    same(v.replacement_candidate_binding, parent.candidate_binding) ||
    v.replacement_candidate_binding.path === parent.candidate_binding.path ||
    !binding(v.evidence_binding) ||
    !refs(v.source_bindings) ||
    !refs(parent.source_bindings) ||
    ![v.replacement_candidate_binding, v.evidence_binding].every((r) =>
      v.source_bindings.some((s: any) => same(r, s)),
    ) ||
    !v.source_bindings.every((r: any) =>
      parent.source_bindings.some((s: any) => same(r, s)),
    ) ||
    typeof v.observed_at !== "string" ||
    !/(?:Z|[+-]\d{2}:\d{2})$/.test(v.observed_at) ||
    !Number.isFinite(Date.parse(v.observed_at)) ||
    !consistentObservation(v, parent) ||
    !Array.isArray(v.negative_conditions) ||
    !v.negative_conditions.length ||
    !v.negative_conditions.every(
      (s: any) => typeof s === "string" && !!s.trim(),
    ) ||
    !object(v.original_bear) ||
    !object(v.replacement_bear) ||
    ![
      v.original_bear.per_historical_share_cny,
      v.replacement_bear.per_historical_share_cny,
      v.difference_per_historical_share_cny,
    ].every(number) ||
    v.original_bear.per_historical_share_cny !==
      parent.scenarios?.find((s: any) => s.scenario === "bear")?.original
        ?.per_historical_share_cny ||
    !object(v.derived_historical_ratios) ||
    ![
      v.derived_historical_ratios.mixed_realization_factor,
      v.derived_historical_ratios.h1_cost_ratio,
    ].every(number) ||
    Number(v.derived_historical_ratios.mixed_realization_factor) <= 0 ||
    Number(v.derived_historical_ratios.mixed_realization_factor) >= 1 ||
    Number(v.derived_historical_ratios.h1_cost_ratio) < 0 ||
    Number(v.derived_historical_ratios.h1_cost_ratio) > 1
  )
    return false;
  const amounts = [
    v.original_bear.per_historical_share_cny,
    v.replacement_bear.per_historical_share_cny,
    v.difference_per_historical_share_cny,
  ];
  if (amounts.some((s) => s.length > 200)) return false;
  const scale = Math.max(...amounts.map((s) => (s.split(".")[1] ?? "").length));
  const units = (s: string) => {
    const [whole, fraction = ""] = s.split(".");
    return BigInt(whole + fraction.padEnd(scale, "0"));
  };
  if (units(amounts[1]) - units(amounts[0]) !== units(amounts[2])) return false;
  return (
    [v.operating_rows, v.annual_cash_rows].every(
      (rows) =>
        Array.isArray(rows) &&
        rows.length === 5 &&
        rows.every((r: any, i: number) => object(r) && r.year === i + 1),
    ) &&
    v.operating_rows.every((r: any) =>
      [r.revenue, r.legacy_ex_parent].every(number),
    ) &&
    v.annual_cash_rows.every((r: any) =>
      [r.profit, r.cash_close, r.book_close, r.dividend_paid].every(number),
    )
  );
}

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
    v?.unsupported_challenges !== undefined &&
    (!Array.isArray(v.unsupported_challenges) ||
      new Set(v.unsupported_challenges.map((row: any) => row?.id)).size !==
        v.unsupported_challenges.length ||
      !v.unsupported_challenges.every(
        (row: any) =>
          object(row) &&
          [
            "PERSISTENT_UPSTREAM_RESTRICTION",
            "TERMINAL_APPROPRIATION_CONTINUES",
            "DELAY_BOUNDARY_FULL_PATH",
          ].includes(row.id) &&
          row.status === "UNSUPPORTED" &&
          typeof row.reason === "string" &&
          !!row.reason.trim(),
      ))
  )
    return false;
  if (
    v?.point_in_time !== undefined &&
    (!object(v.point_in_time) ||
      !calendarDay(v.point_in_time.report_period) ||
      !calendarDay(v.share_basis?.financial_basis) ||
      v.share_basis.financial_basis !== v.point_in_time.report_period)
  )
    return false;
  if (
    v?.replacement_bear !== undefined &&
    !verifiedReplacementBear(v.replacement_bear, v)
  )
    return false;
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
