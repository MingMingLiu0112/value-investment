import type {
  CurrentPricePlan,
  HotspotLifecycleReview,
} from "../../src/types/api";

/** TEST_ONLY presentation inputs; not a real entry, position or approval. */
export function lifecycleFixture(): HotspotLifecycleReview {
  const current = {
    path: "runtime/TEST_ONLY/current-case.json",
    sha256: "a".repeat(64),
  };
  const external = [
    "OWNED_ENTRY_THESIS",
    "CORPORATE_ACTION_COMPARABILITY",
    "INDEPENDENT_STRATEGY_ADMISSION",
    "EVENT_RISK",
    "PORTFOLIO_CAPACITY",
    "SELLABLE_QUANTITY_T_PLUS_ONE_AND_EXECUTION",
  ];
  return {
    schema_version: "hotspot-entry-structure-continuity-v2",
    symbol: "600519",
    action: "no_order",
    evaluated_at: "2026-10-23T16:15:00+08:00",
    status: "CURRENT_STRUCTURE_ONLY",
    observed_review: "WATCH",
    current_data_status: "CURRENT",
    source_integrity: "VERIFIED",
    current_pit: false,
    current_case_binding: current,
    entry_case_binding: null,
    entry_at: null,
    holding_ownership: "NOT_VERIFIED_HERE",
    position_guidance: null,
    personal_action: "NO_ACTION",
    formal_eligibility: false,
    trade_eligible: false,
    risk_review_eligible: false,
    strategy_validation: "NOT_PROVEN",
    current_conditions_scope: "RAW_UNADJUSTED_NOT_PERSONAL_ACTION",
    original_entry_comparison: null,
    price_comparability: null,
    unadjusted_structural_observation: null,
    blockers: ["OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW"],
    required_external_reviews: external,
    decision_explanation: {
      schema_version: "hotspot-lifecycle-explanation-v1",
      action: "no_order",
      selected_review: "WATCH",
      basis_code: "ENTRY_STRUCTURE_NOT_QUALIFIED",
      source_scope: "REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS",
      decision_path: [
        {
          check: "CURRENT_DATA",
          outcome: "CURRENT",
          values: { source_integrity: "VERIFIED", current_pit: false },
          evidence_bindings: [current],
        },
        {
          check: "ENTRY_REFERENCE",
          outcome: "NOT_SUPPLIED",
          values: { entry_at: null },
          evidence_bindings: [],
        },
        {
          check: "CURRENT_ADD",
          outcome: "NOT_OBSERVED",
          values: { price: "12.30", observed: false },
          evidence_bindings: [current],
        },
        {
          check: "PRICE_COMPARABILITY",
          outcome: "NOT_EVALUATED",
          values: {},
          evidence_bindings: [],
        },
      ],
      why_not_add: [
        "ENTRY_STRUCTURE_NOT_QUALIFIED",
        "ADD_CONDITION_NOT_OBSERVED",
      ],
      required_external_reviews: external,
      current_price_observation: {
        price: "12.3400",
        as_of: "2026-10-22",
        available_at: "2026-10-22T16:14:00+08:00",
        reference_price_scope: "LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
        current_pit: false,
      },
      recomputed_rule_versions: {
        current: "TEST_ONLY-current-rule-v2",
        entry: null,
      },
    },
  };
}

export function lifecyclePlan(): CurrentPricePlan {
  return {
    action: "no_order",
    signal_state: "WATCH",
    entry_trigger_price: null,
    invalidation_price: null,
    market_trade_date: "2026-10-22",
    case_path: "runtime/TEST_ONLY/current-case.json",
    case_sha256: "a".repeat(64),
  };
}

export function lifecycleHeldFixture(): HotspotLifecycleReview {
  const review = lifecycleFixture();
  review.entry_case_binding = {
    path: "runtime/TEST_ONLY/entry-case.json",
    sha256: "b".repeat(64),
  };
  review.entry_at = "2026-10-19T16:00:00+08:00";
  review.status = "STRUCTURAL_COMPARISON_ONLY";
  review.observed_review = "EXIT_STRUCTURE_REVIEW";
  review.decision_explanation.selected_review = "EXIT_STRUCTURE_REVIEW";
  review.decision_explanation.basis_code = "ORIGINAL_PROTECTION_BREACHED";
  review.decision_explanation.why_not_add = ["ORIGINAL_PROTECTION_BREACHED"];
  review.original_entry_comparison = {
    original_protection_price: "11.00",
    current_rolling_protection_price: "9.00",
    first_breach_at: "2026-10-20T11:30:00+08:00",
    first_breach_close: "10.00",
    breach_count: 1,
    inspected_bar_count: 12,
    missing_completed_bars: [],
    coverage: "COMPLETE",
    comparison_scope:
      "UNADJUSTED_PRICE_STRUCTURE_REQUIRES_CORPORATE_ACTION_REVIEW",
  };
  return review;
}
