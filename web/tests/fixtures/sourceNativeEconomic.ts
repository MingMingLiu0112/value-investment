export const economicRef = {
  path: "runtime/TEST_ONLY/candidate.json",
  sha256: "a".repeat(64),
};
export function economicFixture(): any {
  return {
    schema_version: "source-native-economic-review-v1",
    status: "CONDITIONAL_ECONOMIC_RESEARCH",
    scope: "PENDING_NATIVE_CANDIDATE_NOT_PRIMARY_OR_CURRENT_VALUATION",
    symbol: "600519",
    confidence: "LOW",
    action: "no_order",
    g3_status: "NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE",
    current_g3_status: "NOT_QUERIED",
    candidate_binding: { ...economicRef },
    position_guidance: null,
    normalized_parent_profit_cny: null,
    approval_changed: false,
    research_admitted: false,
    price_admitted: false,
    formal_eligibility: false,
    strategy_approved: false,
    canonical_written: false,
    registered_current_case_changed: false,
    share_basis: {
      ordinary_shares: "10000",
      financial_basis: "2026-06-30",
      current_shares: null,
      scope: "BOUND_HISTORICAL_MODEL_DENOMINATOR_NOT_CURRENT_SHARES",
    },
    source_bindings: [{ ...economicRef }],
    five_groups: [
      "EARNINGS",
      "DISTRIBUTION",
      "DURATION",
      "COST_TERMINAL",
      "EVENT_MODEL",
    ].map((id) => ({
      id,
      title: "假设与反证",
      interpretation: "TEST_ONLY 未批准的经济假设",
      approval_status: "PENDING_NOT_APPROVED",
    })),
    scenarios: ["bear", "base", "bull"].map((scenario) => ({
      scenario,
      original: {
        per_historical_share_cny: "100",
        candidate_per_historical_share_cny: "100",
        matches_candidate_at_recorded_precision: true,
        ddm_terminal_fraction: ".7",
        ri_terminal_fraction: ".5",
      },
      first_year_boundary: {
        status: "CASH_ONLY_FIRST_YEAR_IDENTITY",
        cash_only_delay_boundary_fraction: ".2",
        original_cash_above_floor_cny: "100",
        boundary_within_zero_one: true,
      },
      ke_plus_200bp: {
        status: "CONDITIONAL_KERNEL_SENSITIVITY",
        delta_basis_points: 200,
        alternative_candidate_verified: false,
        result: { per_historical_share_cny: "80" },
      },
    })),
  };
}
