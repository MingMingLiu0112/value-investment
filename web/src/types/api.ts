export type ApiStatus = string;

export type Eligibility = boolean | string | null;
export type PlanCondition =
  | string
  | string[]
  | {
      price?: string | null;
      rule?: string | null;
      status?: string | null;
      [key: string]: unknown;
    };

export interface DecisionItem {
  id: string;
  symbol?: string;
  name?: string;
  strategy?: string;
  status?: string;
  candidate_action?: string;
  action_intent?: string | null;
  formal_eligibility?: Eligibility;
  portfolio_eligibility?: Eligibility;
  reason?: string;
  as_of?: string;
  why_selected?: string;
  channels?: string[];
  blockers?: string[];
  candidate_explanation?: string;
  support?: unknown;
  counter_evidence?: unknown;
  thesis_breakers?: unknown;
  price_context?: unknown;
  next_events?: unknown;
  research?: ResearchDetail | null;
  price_action_plan?: CurrentPricePlan | null;
  [key: string]: unknown;
}

export interface CurrentPricePlan {
  case_path?: string;
  case_sha256?: string;
  candidate_lifecycle?: string;
  publication_blockers?: string[];
  validation?: {
    source_integrity: string;
    applicability: string;
    signal_event_count: number | null;
    mature_five_session_count: number | null;
    right_censored_count: number | null;
    strategy_validation: string;
    strict_pit_admitted: boolean;
    strict_oos_admitted: boolean;
    elapsed_real_shadow_sessions: number;
    execution_metrics: { status: string; trade_count: number | null };
  };
  research_analysis?: ValueResearchAnalysis | null;
  independent_admission?: {
    status: string;
    review_status: string;
    risk_review_eligible: boolean;
    blockers: string[];
    action: "no_order";
  };
  risk_review_eligible?: boolean;
  conditional_action_rules?: Partial<
    Record<
      "OPEN" | "ADD" | "REDUCE" | "EXIT",
      {
        rule: string;
        price: string | null;
        observed: boolean | null;
        requires_existing_holding: boolean;
      }
    >
  >;
  valuation_date?: string | null;
  price_behavior?: {
    rule_version: string;
    daily_trend: string;
    observation_quality: string;
    confirmed_support: { price: string; known_at: string } | null;
    confirmed_resistance: { price: string; known_at: string } | null;
    breakout: {
      observed: boolean;
      confirmed_on_next_completed_bar: boolean;
      confirmation_level?: string | null;
      breakout_at?: string | null;
      confirmed_at?: string | null;
    };
    pullback_recovery: { observed: boolean };
    auxiliary_15m: { observed: boolean };
    volume_ratio: string;
    risk_reward_ratio: string | null;
    risk_reward_scope: string;
  } | null;
  action: "no_order";
  action_intent?: string | null;
  formal_eligibility?: Eligibility;
  portfolio_eligibility?: Eligibility;
  daily_selection?: {
    rank?: number;
    industry?: string;
    trade_date?: string;
    industry_relative_strength_percent?: string;
    persistence?: string;
    fund_flows?: string;
    catalyst?: string;
  } | null;
  selection_rule_version?: string | null;
  market_environment?: {
    trade_date?: string;
    covered_securities?: number;
    equal_weight_change_percent?: string;
    advancing?: number;
    declining?: number;
    regime_admission?: string;
  } | null;
  required_confirmations?: string[];
  entry_condition?: PlanCondition | null;
  invalidation_condition?: PlanCondition | null;
  period_structure?: Partial<Record<"daily" | "60m" | "15m", string>>;
  opportunity_quality?: {
    rule_version: string;
    activity_tier: string;
    structure_tier: string;
    structure_reasons: string[];
    assessed_trade_date: string;
    expires_after_session: string;
    formal_eligibility: false;
    action: "no_order";
  } | null;
  expires_after_session?: string | null;
  next_observation?: unknown;
  supporting_facts?: unknown;
  counter_evidence?: unknown;
  reference_close?: string | null;
  reference_price_scope?: string;
  price_comparison_eligible?: boolean;
  thesis?: string | null;
  conditional_valuation_range?: Partial<
    Record<"bear" | "base" | "bull", string | number | null>
  > | null;
  bear?: string | number | null;
  base?: string | number | null;
  bull?: string | number | null;
  signal_state: string;
  action_eligibility?: boolean;
  entry_trigger_price: string | null;
  invalidation_price: string | null;
  current_reference_price?: string | null;
  market_trade_date?: string | null;
  next_session?: string | null;
  next_session_date?: string | null;
  next_completed_eligible_session?: string | null;
  decision_id?: string | null;
  research_version?: string | null;
  model_or_rule_version?: string | null;
  entry_confirmation_rule?: string | null;
  invalidation_rule?: string | null;
  explanation?: unknown;
  watch_reason?: string | null;
  support?: unknown;
  counter?: unknown;
  blockers?: string[];
  levels?: Partial<
    Record<
      "daily" | "60m" | "15m",
      {
        prior_max_high: string;
        prior_min_low: string;
        volume_ratio: string;
        last_close: string;
      }
    >
  >;
  add_condition?: PlanCondition | null;
  hold_condition?: PlanCondition | null;
  reduce_condition?: PlanCondition | null;
  exit_condition?: PlanCondition | null;
}

export interface PrivateAccountObservations {
  action: "no_order";
  unavailable_count: number;
  accounts: {
    account_label: string;
    snapshot_date: string;
    displayed_clock_time: string;
    active_trading_ledger: false;
    trade_eligible: false;
    snapshot_sha256: string;
    observed_totals: Record<string, string | null>;
    holdings: {
      symbol: string;
      name: string;
      quantity_inferred: string;
      displayed_cost_per_share_cny: string;
      displayed_price_cny: string;
      market_value_cny: string;
      displayed_weight_pct: string;
    }[];
    reconciliation: {
      header_market_value_minus_rows_cny: string;
      total_assets_minus_header_market_value_and_available_funds_cny: string;
    };
  }[];
}

export interface AccountingBridgeReview {
  schema_version: "economic-review-bundle-v1";
  symbol: string;
  action: "no_order";
  status: string;
  input_descriptor_sha256: string;
  bundle_sha256: string;
  primary_valuation_usable: false;
  economic_approval_granted: false;
  source_bindings: { path: string; sha256: string }[];
  unknown_fields: string[];
  bridge_results: {
    kind: "parent_cash" | "equity";
    period: string;
    entity_scope: string;
    unit: "CNY";
    source_binding: { path: string; sha256: string };
    source_url: string;
    physical_pages: number[];
    terms: Record<string, string>;
    reported_adjustment: string | null;
    derived_adjustment_cny: string;
    computed_closing_cny: string;
    reported_closing_cny: string;
    difference_cny: string;
    assurance: string;
  }[];
}

export interface OperatingEarningsReview {
  context_scope?: "INDEPENDENT_RETAINED_FILINGS_V1";
  scope?: string;
  availability_scope?: string;
  read_at?: string;
  report_periods?: string[][];
  execution_bindings?: { path: string; sha256: string }[];
  action_admitted?: false;
  approval_changed?: false;
  primary_valuation_usable?: false;
  source_spec_binding?: { path: string; sha256: string };
  source_bindings?: {
    source_id: string;
    path: string;
    sha256: string;
    source_url: string;
    published_date: string;
    original_acquired_at: string | null;
  }[];
  status: string;
  schema_version?: string;
  symbol: string;
  action: "no_order";
  input_descriptor_sha256?: string;
  candidate_binding?: { path: string; sha256: string };
  g3_changed: false;
  price_admitted: false;
  strategy_admitted: false;
  normalized_parent_profit_cny: null;
  normalized_range?: null;
  normalized_earnings_admitted?: false;
  historical_ttm_cny?: string;
  h1_change?: {
    period: string;
    computed_change_cny: string;
    arithmetic_residual_cny: string;
    rows: {
      field: string;
      current_cny: string;
      comparative_cny: string;
      contribution_cny: string;
      fact_refs: {
        field: string;
        label: string;
        source_id: string;
        path?: string;
        source_url: string;
        sha256: string;
        physical_page: number;
        excerpt: string;
      }[];
    }[];
  };
  annual_change?: { computed_change_cny: string };
  commercial_subtotal?: { change_cny: string };
}

export interface IndustrialEarningsResearch {
  schema_version: "industrial-earnings-research-v1";
  symbol: string;
  status: string;
  action: "no_order";
  confidence: "LOW";
  context_scope: "INDEPENDENT_SOURCE_BOUND_RESEARCH_NOT_CURRENT_VALUATION";
  formal_eligibility: false;
  primary_valuation_usable: false;
  price_admitted: false;
  strategy_admitted: false;
  economic_approval: false;
  normalized_parent_profit_cny: null;
  input_available_at: string;
  evaluated_at: string;
  financial_basis: string;
  rationale: string;
  tax_convention: string;
  counter_evidence: string[];
  thesis_breakers: string[];
  unknowns: string[];
  policy_binding: { path: string; sha256: string };
  source_bindings: { path: string; sha256: string }[];
  official_sources: {
    source_id: string;
    path: string;
    sha256: string;
    source_url: string;
  }[];
  scenarios: Record<
    "bear" | "base" | "bull",
    {
      rationale: string;
      rows: {
        year: number;
        currency: "CNY";
        revenue_cny: string;
        commercial_subtotal_cny: string;
        inventory_impairment_cny: string;
        goodwill_impairment_cny: string;
        other_asset_impairment_cny: string;
        other_pbt_cny: string;
        group_pbt_cny: string;
        income_tax_cny: string;
        signed_nci_cny: string;
        parent_profit_cny: string;
        bridge_residual_cny: string;
        change_from_historical_parent: {
          commercial_subtotal_change_cny: string;
          asset_impairment_change_cny: string;
          other_pbt_change_cny: string;
          income_tax_change_cny: string;
          signed_nci_change_cny: string;
          parent_profit_change_cny: string;
          residual_cny: string;
        };
      }[];
    }
  >;
}

export interface ParentCashResearch {
  schema_version: "parent-cash-research-v1";
  symbol: string;
  status: string;
  action: "no_order";
  formal_eligibility: false;
  economic_approval: false;
  primary_valuation_usable: false;
  price_admitted: false;
  strategy_admitted: false;
  distribution_capacity_status: "UNKNOWN";
  future_distributable_cash_cny: null;
  ordinary_dividends_paid_cny: null;
  upstream_dividends_received_cny: null;
  parent_restricted_cash_cny: null;
  evaluated_at?: string;
  continuity_status?: string;
  historical_cash_reconciliation_status?: string;
  source_bindings: { path: string; sha256: string }[];
  limitations?: string[];
  historical_statements: {
    symbol: string;
    periods: string[];
    statement_scope: "listed_parent_only";
    source_binding: { path: string; sha256: string; source_url: string };
    balances: {
      period: string;
      opening_cash_and_equivalents_cny: string;
      closing_cash_and_equivalents_cny: string;
      cfo_cny: string;
      cfi_cny: string;
      cff_cny: string;
      fx_cny: string;
      reported_net_change_cny: string;
      mixed_distribution_interest_paid_cny: string;
      cash_residual_cny: string;
      movement_residual_cny: string;
    }[];
  }[];
}

export interface FiscalEarningsResearch {
  schema_version: "fiscal-earnings-research-v1";
  symbol: string;
  currency: "CNY";
  scope: "consolidated";
  status: string;
  action: "no_order";
  confidence: "LOW";
  formal_eligibility: false;
  economic_approval: false;
  price_admitted: false;
  strategy_admitted: false;
  primary_valuation_usable: false;
  dividend_capacity_cny: null;
  normalized_parent_profit_cny: null;
  input_available_at: string;
  evaluated_at: string;
  rationale: string;
  stub_rationale: string;
  accounting_comparability: { perimeter: string; limitations: string };
  historical_h2_2025: { classification: string; lines: Record<string, string> };
  source_bindings: { path: string; sha256: string }[];
  official_sources: { path: string; sha256: string; source_url: string }[];
  scenarios: Record<
    "bear" | "base" | "bull",
    {
      stub: {
        period_start: string;
        period_end: string;
        classification: string;
        lines: Record<string, string>;
      };
      fy2026: {
        period_start: string;
        period_end: string;
        classification: string;
        lines: Record<string, string>;
      };
      rows: {
        year: number;
        currency: "CNY";
        period_start: string;
        period_end: string;
        classification: string;
        revenue_cny: string;
        group_pbt_cny: string;
        income_tax_cny: string;
        signed_nci_cny: string;
        parent_profit_cny: string;
        bridge_residual_cny: string;
      }[];
    }
  >;
}

export interface ValueResearchAnalysis {
  finite_advantage_research?: FiniteAdvantageResearch;
  fiscal_earnings_research?: FiscalEarningsResearch;
  parent_cash_research?: ParentCashResearch;
  industrial_earnings_research?: IndustrialEarningsResearch;
  historical_operating_review?: OperatingEarningsReview;
  blockers?: string[];
  source_native_cash_review?:
    import("../services/valuePolicy").SourceNativeCashReview | null;
  approval_changed?: boolean;
  available_at?: string | null;
  valuation?: {
    symbol?: string;
    confidence?: string;
    status?: string;
    model_type: string;
    model_version: string;
    valuation_date: string;
    bear_value: string;
    base_value: string;
    bull_value: string;
    assumptions: {
      valuation_timing?: { basis_at: string; valuation_at: string } | null;
    };
  };
  joint_capital_review?:
    import("../services/valuePolicy").JointCapitalReview | null;
  review_binding?: {
    candidate_binding: { path: string; sha256: string };
    model_context: Record<string, unknown>;
    package_binding?: { path: string; sha256: string };
    workbench_binding?: { path: string; sha256: string };
    review_packet_binding?: { path: string; sha256: string };
  };
  economic_assessment?: {
    schema_version: "value-economic-assessment-v1";
    action: "no_order";
    symbol: string;
    primary_valuation_usable: false;
    economic_assumptions_reviewed: false;
    input_descriptor_sha256?: string;
    review_binding?: ValueResearchAnalysis["review_binding"];
    source_bindings?: { path: string; sha256: string }[];
    accounting_bridge_review?: AccountingBridgeReview;
    model_applicability?: { assessment: string; reasons?: string[] };
    earnings?: {
      historical_ex_nonrecurring_ttm_cny: string | null;
      normalization_status: string;
      operating_quality_bridge?: OperatingEarningsReview;
    };
    sustainable_distribution_status?: string;
    cash_conversion_diagnostic?: {
      status: string;
      scope: string;
      symbol: string;
      action: "no_order";
      input_descriptor_sha256?: string;
      candidate_binding?: { path: string; sha256: string };
      source_bindings?: { path: string; sha256: string }[];
      execution_bindings?: { path: string; sha256: string }[];
      primary_valuation_usable: false;
      g3_changed: false;
      approval_changed: false;
      price_admitted: false;
      strategy_admitted: false;
      historical_pit_admitted?: false;
      normalized_parent_profit_cny: null;
      rows: {
        physical_page: number;
        source_binding: { path: string; sha256: string };
      }[];
      calculation?: {
        reported_cfo_change_cny: string;
        identified_outflow_direction_contribution_cny: string;
        contribution_fraction_of_reported_change: string | null;
      };
      counter_evidence?: string;
    };
    historical_cash_observations?: {
      id: string;
      recomputed_value: string;
      scope: string;
      evidence?: {
        label?: string;
        period: string;
        value: string;
        source_url?: string;
        physical_page: number;
        sha256: string;
      }[];
    }[];
    blockers: string[];
  } | null;
  schema_version: "value-research-analysis-v1";
  symbol: string;
  action: "no_order";
  status: "CONDITIONAL_ANALYSIS_VERIFIED" | "SOURCE_OR_REPLAY_UNAVAILABLE";
  arithmetic_complete: boolean;
  economic_assumptions_reviewed: false;
  action_admitted: false;
  strategy_admitted: false;
  price_comparison_eligible: false;
  input_descriptor_sha256?: string;
  valuation_date?: string | null;
  research_as_of?: string | null;
  computed_at?: string | null;
  scenarios: {
    scenario: "bear" | "base" | "bull";
    per_share_value: string | number | null;
    inputs: Record<string, unknown>;
  }[];
  sensitivity?: {
    status?: string;
    rows: {
      assumption_name: string;
      field_path: string;
      basis?: string | null;
      rationale?: string | null;
      evidence_refs?: { id?: string }[];
      points: {
        bound: string;
        input_value: string | number | null;
        status: string;
        per_share_value: string | number | null;
        delta_from_base?: string | number | null;
        reason?: string;
      }[];
    }[];
  } | null;
  counter_evidence?: unknown;
  model_applicability?: {
    blockers?: string[];
    scope?: string | null;
    route?: { profile_id: string; selected_model: string; model_type: string };
  };
  source_bindings: { path: string; sha256: string }[];
}

export interface FiniteAdvantageResearch {
  schema_version: string;
  symbol: string;
  status: string;
  action: string;
  scope: string;
  currency: string;
  confidence: string;
  formal_eligibility: boolean;
  economic_approval: boolean;
  price_admission: boolean;
  input_available_at?: string;
  research_as_of?: string;
  basis_date?: string;
  primary_valuation_changed?: boolean;
  price_condition_cny?: string | null;
  rationale?: string;
  counter_evidence?: string[];
  source_bindings?: { path: string; sha256: string }[];
  branches: {
    scenario: string;
    branch: string;
    fade_years: number;
    net_maintenance_gap_cny: string;
    result: {
      status: string;
      action: string;
      formal_eligibility: boolean;
      economic_approval: boolean;
      price_admission: boolean;
      blockers: string[];
      valuation: {
        usable: boolean;
        per_share_cny: string | null;
        ri_ddm_residual_cny: string | null;
      };
      rows: {
        year: number;
        profit_cny: string;
        distribution_cny: string;
        closing_cash_cny: string;
        closing_book_cny: string;
      }[];
    };
  }[];
}

export interface CurrentPriceCase {
  action: "no_order";
  symbol: string;
  status?: string;
  market_trade_date: string;
  current_reference_price: string | null;
  bars: Partial<Record<"daily" | "60m" | "15m", HistoricalBar[]>>;
  levels: Partial<Record<"daily" | "60m" | "15m", HistoricalLevels>>;
  price_action_plan: CurrentPricePlan;
  source_bindings?: HistoricalPriceCase["source_bindings"];
  blockers?: string[];
}

export interface HistoricalBar {
  time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  amount: string;
}

export interface HistoricalLevels {
  period: string;
  rule_version: string;
  window: number;
  last_bar: string;
  reference_close: string;
  entry_trigger_price: string;
  entry_confirmation_rule: string;
  invalidation_price: string;
  invalidation_rule: string;
  volume_ratio: string;
  breakout_observed: boolean;
  risk_reward_ratio: string | null;
  target_price: string | null;
  action: "no_order";
}

export interface HistoricalPriceCase {
  action: "no_order";
  status?: string;
  symbol: string;
  market_trade_date: string;
  current_reference_price: string;
  levels: Record<"daily" | "60m" | "15m", HistoricalLevels>;
  bars: Record<"daily" | "60m" | "15m", HistoricalBar[]>;
  source_bindings: Record<
    string,
    {
      path: string;
      sha256: string;
      source_url: string;
      fetched_at: string;
      adjustment: string;
      scope: string;
    }
  >;
  signal_state: "HISTORICAL_OBSERVATION_NOT_ADMITTED";
  blockers: string[];
  price_action_plan: {
    entry_trigger_price: string;
    entry_confirmation_rule: string;
    invalidation_price: string;
    risk_reward_ratio: null;
    action_eligibility: false;
    signal_state: "HISTORICAL_OBSERVATION_NOT_ADMITTED";
    model_or_rule_version: string;
    action: "no_order";
  };
  close_crosscheck?: {
    status: "VERIFIED_HISTORICAL_CLOSE";
    price: string;
    manifest_path: string;
    manifest_sha256: string;
  };
}

export interface HistoricalCaseListing {
  action: "no_order";
  status: "HISTORICAL_NOT_CURRENT" | "UNAVAILABLE";
  items: Array<
    Pick<
      HistoricalPriceCase,
      "symbol" | "market_trade_date" | "levels" | "signal_state" | "blockers"
    > & {
      reference_price: string;
    }
  >;
}

export interface ResearchEvidenceRef {
  id: string;
  path: string;
  sha256: string | null;
}

export interface ResearchGateRow {
  key: string;
  status: string | null;
  reason: string | null;
  next_action: string | null;
  evidence_refs: string[];
}

export interface ResearchBinding {
  status: string;
  path: string | null;
  sha256: string | null;
}

export interface ResearchStatusSummary {
  code: string | null;
  label: string | null;
  case_status: string | null;
  financial_period: string | null;
  evidence_scope: string | null;
}

export interface ResearchValuation {
  model_type: string | null;
  model_version: string | null;
  valuation_date: string | null;
  status: string | null;
  confidence: string | null;
  bear: string | number | null;
  base: string | number | null;
  bull: string | number | null;
  currency: string | null;
  basis: string | null;
  disclaimer: string | null;
  scope: string | null;
}

export interface ResearchModelValidity {
  status: string | null;
  model_id: string | null;
  model_as_of: string | null;
  valid_from: string | null;
  last_material_event_check: string | null;
  blockers: string[];
}

export interface ResearchPrice {
  current_price: string | number | null;
  price_as_of: string | null;
  quote_admission_status: string | null;
  bridge_status: string | null;
  model_validity_status: string | null;
  margin_to_base: string | number | null;
  margin_to_bear: string | number | null;
  attractiveness_status: string | null;
  attractiveness_label: string | null;
  unavailable_reason: string | null;
  needed_evidence: string | null;
  blockers: string[];
}

export interface ResearchSuggestedState {
  value: string | null;
  human_review_required: boolean | null;
  boundary: string | null;
}

export interface PriceBridgeSource {
  provider: string | null;
  source_url: string | null;
  fetched_at: string | null;
  sha256: string | null;
}

/** Read-only scope metadata; never confers strategy or execution authority. */
export interface CurrentSnapshotScope {
  scope?: string | null;
  knowledge_as_of?: string | null;
  observed_at?: string | null;
  full_calendar_window_elapsed?: boolean | null;
  strict_contemporaneous_pit?: boolean | null;
  research_comparison_only?: boolean | null;
  formal_eligibility?: boolean | null;
  strategy_approval_granted?: boolean | null;
  action?: string | null;
  source_assurance?: string | null;
}

export interface CurrentSnapshotValidity extends CurrentSnapshotScope {
  schema_version: string | null;
  status: string | null;
  symbol: string | null;
  evaluated_at?: string | null;
  availability_basis?: string | null;
  research_cutoff_changed?: boolean | null;
  usable_for_research_comparison: boolean | null;
  g3_approval_granted?: boolean | null;
  blockers: string[];
  bindings?: Record<string, unknown>;
}

export interface CurrentEventCoverage extends CurrentSnapshotScope {
  required_through: string | null;
  query_through: string | null;
  covered_through: string | null;
  observed_at: string | null;
  full_calendar_window_elapsed: boolean | null;
  status:
    | "PARTIAL_CURRENT_SNAPSHOT"
    | "CLOSED_WINDOW_NOT_CURRENT"
    | "SNAPSHOT_NOT_CURRENT"
    | "FULL_WINDOW"
    | "CURRENT_AS_OF_SNAPSHOT";
}

/** One executed admission of the registered close against the registered research cutoff. */
export interface PriceBridgeExecution extends CurrentSnapshotScope {
  current_snapshot_validity?: CurrentSnapshotValidity | null;
  current_event_coverage?: CurrentEventCoverage | null;
  historical_model_validity?: { status?: string | null } | null;
  incremental_validity?: {
    status: string | null;
    review_cutoff: string | null;
    announcement_count: number | null;
    blockers: string[];
    observed_at?: string | null;
    full_calendar_window_elapsed?: boolean | null;
  } | null;
  schema_version: string | null;
  status: string | null;
  reason: string | null;
  next_step: string | null;
  price_admitted: boolean | null;
  comparison_eligible: boolean;
  compatibility?: PriceBridgeCompatibility | null;
  quote_date: string | null;
  display_price: string | null;
  collected_at: string | null;
  display_scope: string | null;
  is_historical_close: boolean | null;
  latest_completed_session: string | null;
  bundle_path: string | null;
  bundle_sha256: string | null;
  research_day: string | null;
  research_version: string | null;
  pointer_path: string | null;
  pointer_sha256: string | null;
  sources: PriceBridgeSource[];
}

export interface PriceBridgeCompatibilityStep {
  eligible: boolean | null;
  reason: string | null;
}

export interface PriceBridgeCompatibility {
  verified_quote?: PriceBridgeCompatibilityStep | null;
  research_compatible?: PriceBridgeCompatibilityStep | null;
  historical_reconstruction_eligible?: PriceBridgeCompatibilityStep | null;
  comparison_eligible?: PriceBridgeCompatibilityStep | null;
  formal_decision_eligible?: PriceBridgeCompatibilityStep | null;
}

export interface ResearchReadingRow {
  label: string;
  value: string;
}

export interface ResearchValuationProvenance {
  bound_decision: string | null;
  bound_research_version: string | null;
  registered_research_note: string | null;
}

export interface ResearchDetail {
  symbol?: string;
  company_name?: string | null;
  action?: string | null;
  research_binding: ResearchBinding;
  research_status: ResearchStatusSummary;
  decision_cutoff: string | null;
  research_version: string | null;
  source_version: string | null;
  financial_facts_status: ResearchGateRow | null;
  business_quality_status: ResearchGateRow | null;
  valuation_model: string | null;
  valuation: ResearchValuation;
  valuation_confidence: string | null;
  model_validity: ResearchModelValidity;
  price: ResearchPrice;
  price_bridge_execution?: PriceBridgeExecution | null;
  price_as_of: string | null;
  quote_admission_status: string | null;
  margin_to_base: string | number | null;
  margin_to_bear: string | number | null;
  gates: Array<ResearchGateRow | null>;
  research_gate: ResearchGateRow | null;
  decision_gate: ResearchGateRow | null;
  portfolio_gate: ResearchGateRow | null;
  suggested_state: ResearchSuggestedState;
  candidate_explanation: string | null;
  position_guidance: unknown;
  portfolio_input_status: string | null;
  thesis: string | null;
  return_driver: string | null;
  mispricing_hypothesis: string | null;
  blockers: string[];
  next_events: unknown[];
  reopen_triggers: string[];
  exit_conditions: string[];
  evidence_refs: ResearchEvidenceRef[];
  reading_order: ResearchReadingRow[];
  valuation_provenance: ResearchValuationProvenance;
}

export interface DailyResearchRow {
  symbol: string;
  name: string;
  research_day: string | null;
  quote_date: string | null;
  bridge_status: string | null;
  price_admitted: boolean;
  needs_re_research: boolean;
  research_covers_close: boolean;
  reason: string | null;
  next_step: string | null;
}

export interface DailyResearchStatus {
  schema_version: string;
  action: "no_order";
  status?: string;
  registry_status?: string;
  reason?: string;
  registered_count: number;
  verified_close_count?: number;
  needs_re_research_count?: number;
  admitted_count?: number;
  rows: DailyResearchRow[];
  blockers?: string[];
}

export interface DailyDualSleeveSurface {
  schema_version: string;
  action: "no_order";
  status: string;
  namespace: string | null;
  portfolio_connected: boolean;
  position_guidance: unknown | null;
  position_guidance_available: boolean;
  trade_eligible: boolean;
  acceptance_authority: string | null;
  review_generated_at: string | null;
  blockers: string[];
  next_user_input: string | null;
  source: string | null;
}

export type ReadinessStatus = "READY" | "PARTIAL" | "PENDING" | "NOT_EVALUATED";

export interface StrategyReadiness {
  schema_version: "strategy-readiness-v1";
  strategy: string;
  action: "no_order";
  authorization_granted: false;
  steps: {
    key: string;
    label: string;
    status: ReadinessStatus;
    reason: string;
  }[];
  primary_gap: {
    code: string;
    category: string;
    summary: string;
    next_action: string;
    url: string;
  } | null;
  conditional_valuation: {
    bear: string | number | null;
    base: string | number | null;
    bull: string | number | null;
    currency: string | null;
    as_of: string | null;
    scope: "UNAPPROVED_RESEARCH_ONLY";
  } | null;
  price_snapshot: {
    value: string | number | null;
    date: string | null;
    usage: "DISPLAY_ONLY";
  } | null;
  independent_of_value_valuation: boolean;
}

export interface DailyEvaluationItem {
  symbol: string;
  company_name?: string;
  strategy: string;
  decision_action: "NO_TRADE" | "UNASSESSABLE" | "CONDITIONAL_MANUAL_REVIEW";
  public_action_intent?: "OPEN" | "ADD" | "HOLD" | "REDUCE" | "EXIT";
  decision_reason: string;
  evaluation_status: string;
  eligibility: false;
  readiness?: StrategyReadiness | null;
}

export interface DailyResponse {
  actionable_evaluation?: {
    action: "no_order";
    scope: "PUBLISHED_COMPANIES_ONLY";
    evaluated_count: number;
    unassessable_count: number;
    operation_eligible_count: number;
    conditional_review_count?: number;
    conclusion:
      | "INCOMPLETE_EVALUATION"
      | "NO_QUALIFIED_NEW_TRADE"
      | "PUBLIC_CONDITIONAL_REVIEWS_AVAILABLE";
    items: DailyEvaluationItem[];
  };
  action: "no_order";
  status: ApiStatus;
  as_of?: string;
  market: { status: string; reason?: string };
  summary: {
    universe_count: number | null;
    formal_count: number;
    watch_count: number | null;
  };
  sections: {
    holdings: DecisionItem[];
    value: DecisionItem[];
    hotspot: DecisionItem[];
  };
  research?: DailyResearchStatus;
  dual_sleeve?: DailyDualSleeveSurface;
  publication?: PublicPacketBlock;
  blockers: string[];
  gate_code?: string;
  reason?: string;
  publication_source?: string;
}

export interface ResearchDraftScenario {
  scenario: "bear" | "base" | "bull";
  per_share_value: string;
  terminal_residual_contribution_ratio?: string | null;
  basis_to_valuation_factor?: string | null;
  dividend_crosscheck_difference?: string | null;
}

export interface ResearchDraftAssumption {
  name: string;
  unit?: string | null;
  bear?: string | number | null;
  base?: string | number | null;
  bull?: string | number | null;
  basis?: string | null;
  rationale?: string | null;
  confidence?: string | null;
}

export interface ResearchDraftEvidence {
  id: string;
  title?: string | null;
  url?: string | null;
  published_at?: string | null;
  available_at?: string | null;
  sha256: string;
}

export interface ResearchDraftEvent {
  announcement_id?: string | null;
  title?: string | null;
  published_at?: string | null;
  review_status?: string | null;
  source_url?: string | null;
}

export interface ResearchDraftVersionComparison {
  from: {
    status: string;
    research_version: string;
    valuation?: unknown;
  };
  to: {
    status: string;
    research_version: string;
    research_as_of?: string | null;
    valuation?: unknown;
    model_validity?: string | null;
    price_bridge?: string | null;
  };
  changed: string[];
  unchanged: string[];
  next_gate?: string | null;
}

export type ResearchDraft = ValuationResearchDraft | ResearchOnlyDraft;

export type ResearchOnlyStatement =
  | string
  | {
      kind?: string;
      text: string;
      evidence_refs?: string[];
    };

export interface ResearchOnlyDraft {
  schema_version: "public-research-only-draft-v1";
  research_mode: "research_only_v1";
  action: "no_order";
  symbol: string;
  company_name: string;
  run_id: string;
  research_version: string;
  status: "RESEARCH_DRAFT_NOT_APPROVED";
  research_as_of: string;
  available_at: string;
  financial_period: string;
  assessment_status: "UNASSESSABLE";
  native_status: "UNSUPPORTED";
  issuer_identity_status: string;
  confidence: "LOW";
  observations_verified: false;
  summary: string;
  thesis: string;
  return_driver: string;
  mispricing_hypothesis: string;
  valuation: null;
  quote_fact: null;
  price_bridge: null;
  model_validity: null;
  gates: null;
  observations: {
    field_name: string;
    value: string | null;
    prior_value?: string | null;
    period_label?: string;
    prior_period_label?: string;
    unit?: string;
    statement_scope?: string;
    evidence_refs: string[];
  }[];
  research_topics: {
    id: string;
    status: string;
    explanation: string;
    evidence_refs: string[];
    missing: string[];
  }[];
  evidence: (ResearchDraftEvidence & {
    page?: number;
    physical_page?: number;
    excerpt?: string;
    published_date?: string | null;
    retrieved_at: string;
  })[];
  counter_evidence: ResearchOnlyStatement[];
  thesis_breakers: ResearchOnlyStatement[];
  next_events: ResearchOnlyStatement[];
  blockers: string[];
  boundary: string;
  research_input_binding: {
    package: { path: string; sha256: string };
    input_sha256: string;
  };
  input_verification: {
    status: "SOURCE_INPUTS_MATCH_NO_VALUATION";
    source_contract_status: "SOURCE_CUTOFF_VALIDATED_NO_SCENARIOS_OR_FACT_ADMISSION";
    input_sha256: string;
    computed_at: string;
    cutoff_at: string;
    economic_approval: false;
  };
}

export interface ValuationResearchDraft {
  schema_version: "public-research-draft-v1" | "public-research-draft-v2";
  action: "no_order";
  symbol: string;
  company_name: string;
  run_id: string;
  research_version: string;
  status: "RESEARCH_DRAFT_NOT_APPROVED";
  research_as_of: string;
  available_at: string;
  financial_period: string;
  summary: string;
  thesis?: string | null;
  return_driver?: string | null;
  mispricing_hypothesis?: string | null;
  financial_facts?: Record<string, string | null>;
  input_verification?: {
    status: "SOURCE_AND_MODEL_INPUTS_MATCH";
    input_sha256: string;
    computed_at: string;
    cutoff_at: string;
    basis_date: string;
    share_basis:
      "issued_ordinary_shares" | "ordinary_shares_excluding_treasury";
    capital_inputs: {
      field: string;
      value: string;
      unit: string;
      scope: string;
      period_end: string;
      source_id: string;
      physical_page: number;
      normalization_rule: string;
      component_values: string[];
    }[];
    economic_approval: false;
  };
  valuation: {
    model_type: string;
    model_version: string;
    valuation_date: string;
    status: "conditional_research_only";
    confidence?: string | null;
    currency: string;
    scope?: string | null;
    disclaimer?: string | null;
    scenarios: ResearchDraftScenario[];
    assumptions: ResearchDraftAssumption[];
  };
  model_validity: {
    model_id?: string | null;
    model_as_of?: string | null;
    last_material_event_check?: string | null;
    status: string;
    blockers: string[];
  };
  quote_fact: {
    quote_date: string;
    current_price: string | number;
    currency: string;
    status: "VERIFIED_CLOSE_NOT_ADMITTED";
    providers?: unknown[];
  };
  price_bridge: {
    status: string;
    price_admitted: false;
    margin_to_bear: null;
    margin_to_base: null;
    blockers: string[];
    reason?: string | null;
    needed_evidence?: string | null;
  };
  gates?: {
    results?: Record<string, boolean>;
    blockers?: string[];
    conclusion?: string | null;
  } | null;
  events?: {
    status?: string | null;
    coverage_status?: string | null;
    pending_count?: number;
    items?: ResearchDraftEvent[];
  } | null;
  counter_evidence: string[];
  thesis_breakers: string[];
  next_events: string[];
  reopen_triggers: string[];
  limitations: string[];
  boundary: string;
  evidence: ResearchDraftEvidence[];
  version_comparison: ResearchDraftVersionComparison;
}

export interface HotspotLifecycleReview {
  schema_version: "hotspot-entry-structure-continuity-v2";
  symbol: string;
  action: "no_order";
  evaluated_at: string;
  status: string;
  observed_review: string;
  current_data_status: string;
  source_integrity: string;
  current_pit: boolean;
  current_case_binding: { path: string; sha256: string };
  entry_case_binding: { path: string; sha256: string } | null;
  entry_at: string | null;
  holding_ownership: "NOT_VERIFIED_HERE";
  position_guidance: null;
  personal_action: "NO_ACTION";
  formal_eligibility: false;
  trade_eligible: false;
  risk_review_eligible: false;
  strategy_validation: string;
  current_conditions_scope: "RAW_UNADJUSTED_NOT_PERSONAL_ACTION";
  original_entry_comparison: Record<string, unknown> | null;
  price_comparability: Record<string, unknown> | null;
  unadjusted_structural_observation: Record<string, unknown> | null;
  blockers: string[];
  required_external_reviews: string[];
  decision_explanation: {
    schema_version: "hotspot-lifecycle-explanation-v1";
    action: "no_order";
    selected_review: string;
    basis_code: string;
    decision_path: {
      check: string;
      outcome: string;
      values: Record<string, unknown>;
      evidence_bindings: { path: string; sha256: string }[];
    }[];
    why_not_add: string[];
    required_external_reviews: string[];
    current_price_observation: Record<string, unknown> | null;
    recomputed_rule_versions: {
      current: string | null;
      entry: string | null;
    } | null;
    source_scope: "REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS";
  };
}

export interface DetailResponse {
  hotspot_lifecycle_review?: HotspotLifecycleReview | null;
  strategy_evaluation?: DailyEvaluationItem & {
    action: "no_order";
    review_quantity: null;
    position_range: null;
    available_cash_impact: null;
  };
  action: "no_order";
  status: ApiStatus;
  decision: DecisionItem | null;
  research_draft?: ResearchDraft | null;
  review_replay?: {
    status:
      | "VERIFIED_EXACT_INPUT_REPLAY"
      | "VERIFIED_NEW_INPUT_CANDIDATE"
      | "SOURCE_UNAVAILABLE";
    symbol: string;
    action: "no_order";
    formal_eligibility: false;
    approval_changed?: false;
    research_admitted?: false;
    price_admitted?: false;
    scope?: "UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY";
    research_as_of?: string;
    replayed_at?: string;
    prepared_at?: string;
    valuation_basis_date?: string;
    valuation_basis_scope?: "EX_POST_PRIOR_COMPLETED_SESSION";
    next_url?: string;
  };
  financial_progress?: {
    status: "VERIFIED_FACT_ADOPTION" | "UNVERIFIED";
    action: "no_order";
    symbol: string;
    adopted_fact_count: number;
    research_inputs_updated: boolean;
    quality_coverage_before: string;
    quality_coverage_after: string;
    source_financial_funding_scope?: {
      status: string;
      symbol: string;
      period_label: string;
      action: "no_order";
      financial_fact_admitted: false;
      required_fields: string[];
      unresolved_fields: string[];
      source_binding: {
        path: string;
        sha256: string;
        source_url: string;
        available_at: string;
      };
      observations: {
        field_name: string;
        value: string | null;
        period_label: string;
        unit: string;
        currency: string;
        statement_scope: string;
        page: number;
        excerpt: string;
      }[];
      industrial_financing_composition?: {
        version: "OFFICIAL_FINANCING_COMPOSITION_OBSERVATION_V1";
        status: "SOURCE_BOUND_PARTIAL_COMPOSITION_NOT_COMPLETE_DEBT";
        action: "no_order";
        complete_debt_verified: false;
        interest_bearing_debt: null;
        economic_approval: false;
        source_binding: {
          symbol: string;
          period: string;
          path: string;
          sha256: string;
          source_url: string;
        };
        six_balance_buckets_cny: string | null;
        six_buckets_plus_other_noncurrent_cny: string | null;
        reported_interest_contracts_total_cny: string | null;
        balance_subset_minus_reported_interest_contracts_cny: string | null;
      };
      research_context?: {
        schema_version: "funding-cash-research-observations-v1";
        symbol: string;
        period_label: string;
        status: string;
        action: "no_order";
        financial_fact_admitted: false;
        formal_eligibility: false;
        source_binding: { path: string; sha256: string };
        observations: {
          observation_id: string;
          field_name: string;
          value: string;
          symbol: string;
          period_label: string;
          statement_scope: string;
          unit: string;
          currency: string;
          page: number;
          excerpt: string;
          source_binding: { path: string; sha256: string };
        }[];
        derivations: {
          field_name: string;
          value: string;
          unit: string;
          symbol: string;
          period_label: string;
          input_observation_ids: string[];
          source_binding: { path: string; sha256: string };
        }[];
      };
    } | null;
    adopted_metrics?: {
      field_name:
        "debt_ratio" | "revenue_yoy" | "net_income_yoy" | "net_income";
      value: string;
      unit: string;
      period_label: string;
    }[];
    source_original?: {
      symbol: string;
      period: string;
      path: string;
      sha256: string;
      source_url: string;
      available_at: string;
    };
    verification_methods?: string[];
    formal_eligibility: false;
  } | null;
  publication?: PublicPacketBlock;
  reason?: string;
}

export interface HistoryResponse {
  action: "no_order";
  status: ApiStatus;
  as_of?: string | null;
  counts?: { symbols: number; versions: number };
  items: ResearchHistoryItem[];
  note?: string;
  published_decision_history?: {
    status: "HISTORY_AVAILABLE" | "CURRENT_ONLY" | "NOT_AVAILABLE";
    history: Array<{
      publication_id: string;
      research_version?: string | null;
      decision_cutoff?: string | null;
      generated_at?: string | null;
      published_at?: string | null;
      packet_path?: string | null;
      packet_sha256?: string | null;
      content_sha256?: string | null;
      receipt_path?: string | null;
      action: "no_order";
    }>;
    note?: string;
    skipped_publications?: Array<{ artifact: string; reason: string }>;
  };
  observation_changes?: {
    status: "SOURCE_REVALIDATED" | "UNAVAILABLE";
    scope: "OBSERVATION_ONLY";
    completed_session?: string;
    evaluated_at?: string;
    formal_eligibility: false;
    action: "no_order";
    items: Array<{
      symbol: string;
      transition:
        | "new"
        | "continue"
        | "approach"
        | "triggered"
        | "invalid"
        | "expired"
        | "left";
      reason: string;
      trend_strengthened: boolean;
      selected_today: boolean;
      fresh_evidence: boolean;
      market_trade_date: string;
    }>;
  };
}

export interface ResearchVersionRow {
  version_label: string;
  research_date: string;
  artifact: string;
  sha256: string;
  bound_to_current_publication: boolean;
}

export interface ResearchAttention {
  choice_id: string | null;
  scope: string | null;
  confidence: string | null;
  reason: string | null;
  countercase: string | null;
  reopen_triggers: string[];
}

export interface ResearchReviewItem {
  id: string | null;
  question: string | null;
  support: string | null;
  countercase: string | null;
  impact: string | null;
  field_paths: string[] | null;
}

export interface ResearchEvidenceRow {
  path: string;
  sha256: string | null;
}

export interface ResearchFieldChange {
  before?: unknown;
  after?: unknown;
}

export interface ResearchReviewGroupChanges {
  added: string[];
  removed: string[];
  changed: string[];
}

export interface ResearchComparison {
  status: string;
  observation?: string;
  changed_fields?: string[];
  field_changes?: Record<string, ResearchFieldChange>;
  review_group_changes?: ResearchReviewGroupChanges;
  admission_effect?: string;
  reason?: string;
  from_version?: string;
  to_version?: string;
}

export interface ResearchHistoryItem {
  id: string;
  symbol: string;
  strategy: string;
  status: string;
  action: string;
  candidate_action: string;
  published_research_version: string | null;
  latest_version_label: string;
  attention: ResearchAttention;
  assumptions: Record<string, string> | null;
  assurance_limits: string[];
  review_items: ResearchReviewItem[];
  evidence: ResearchEvidenceRow[];
  versions: ResearchVersionRow[];
  comparison: ResearchComparison;
}

export interface PortfolioSleeve {
  sleeve: string;
  quantity: string;
  cost_cny: string;
  average_cost_cny: string;
  sellable_quantity: string;
  next_sell_session: string | null;
}

export interface PortfolioPosition {
  symbol: string;
  exchange: string;
  quantity: string;
  cost_cny: string;
  average_cost_cny: string;
  sleeves: PortfolioSleeve[];
  market_value_cny: string | null;
  floating_pnl_cny: string | null;
  weight_pct: string | null;
}

export interface RecordingTimeRiskCapture {
  status: string;
  scope?: string;
  reason?: string;
  risk_status?: string | null;
  review_quantity?: number | string | null;
  blockers?: string[];
}

export interface RecordingTimeRiskEvidence {
  recording_time_personal_risk?: RecordingTimeRiskCapture | null;
  recording_time_risk_status?: string;
}

export interface PortfolioTrade {
  judgment_snapshot?: {
    publication_id: string;
    recorded_at: string;
    trade_time_availability_proven: boolean;
    snapshot_sha256: string;
    plan: CurrentPricePlan;
    personal_risk_capture?: RecordingTimeRiskCapture;
  } | null;
  transaction_id: string;
  side: string;
  sleeve: string;
  symbol: string;
  exchange: string;
  quantity: string;
  price_cny: string;
  fees_cny: string;
  trade_date: string;
  next_sell_session: string | null;
  confirmed_at: string;
  record_sha256?: string;
  decision_id?: string | null;
  research_version?: string | null;
  publication_id?: string | null;
}

export interface PortfolioDraft {
  status: string;
  prepared_record_sha256: string;
  fill: Record<string, unknown>;
  cash_cny: string;
  realized_pnl_cny: string;
  positions: PortfolioPosition[];
}

export interface PortfolioReconciliation {
  status: string;
  superseded: boolean;
  reason: string | null;
  state_version: number | null;
  snapshot_version: number | null;
  scope: string | null;
  reconciled_at: string | null;
}

export interface PortfolioResponse {
  total_position_weight_pct?: string | null;
  confirmed_cash_reserve_cny?: string | null;
  cost_basis_total_cny?: string | null;
  sleeve_summaries?: {
    sleeve: string;
    cost_basis_cny: string;
    market_value_cny: string | null;
    weight_pct: string | null;
  }[];
  action: "no_order";
  status: ApiStatus;
  revision: number;
  as_of: string | null;
  cash_cny: string | null;
  realized_pnl_cny: string | null;
  total_equity_cny?: string | null;
  market_value_total_cny?: string | null;
  unrealized_pnl_total_cny?: string | null;
  positions: PortfolioPosition[];
  trades: PortfolioTrade[];
  policy: Record<string, unknown> | null;
  pending_policy?: PolicyDraft | null;
  pending_draft: PortfolioDraft | null;
  latest_snapshot: Record<string, unknown> | null;
  reconciliation: PortfolioReconciliation | null;
  valuation: { status: string; reason: string };
  blockers: string[];
}

export interface PolicyDraft {
  prepared_record_sha256: string;
  state_version: number;
  policy: Record<string, unknown>;
  missing_fields?: string[];
}

export interface PolicyResponse {
  action: "no_order";
  status: string;
  revision: number;
  policy: Record<string, unknown> | null;
  pending_policy: PolicyDraft | null;
  missing_fields: string[];
}

export interface WriteResponse {
  action: "no_order";
  status: ApiStatus;
  revision?: number;
  record_sha256?: string;
  detail?: unknown;
  personal_risk_capture?: RecordingTimeRiskCapture;
  [key: string]: unknown;
}

export interface RiskFactsSleeveRow {
  sleeve: string;
  quantity: string;
}

export interface HeldContinuityResponse {
  action: "no_order";
  status: string;
  revision?: number;
  items: {
    symbol: string;
    quantity: string;
    sellable_quantity: string | null;
    selected_today: boolean;
    review_priority: number;
    review_reasons: string[];
    data_gaps: string[];
    strategy_plan: CurrentPricePlan | null;
    actionable_decisions?: import("../components/ActionableDecisionResult").ConditionalAccountDecision[];
  }[];
}

export interface RiskFactsPosition {
  symbol: string;
  exchange: string;
  quantity: string;
  cost_basis_cny: string;
  market_value_cny: string | null;
  unrealized_pnl_cny: string | null;
  sleeves: RiskFactsSleeveRow[];
}

export interface RiskFacts {
  revision: number;
  account_scope: string;
  as_of: string;
  cash_cny: string;
  realized_pnl_cny: string;
  cost_basis_total_cny: string;
  positions: RiskFactsPosition[];
  confirmed_fill_count: number;
  reconciliation_status: string;
  reconciliation?: PortfolioReconciliation | null;
  price_status: string;
  price_reason?: string | null;
}

export interface RiskEngineSleeveReview {
  contract_sleeve: string;
  budget_cny: string;
  equity_cny: string;
  used_funds_cny: string;
  cash_cny: string;
  available_funds_cny: string;
  risk_budget_cny: string;
  committed_risk_cny: string | null;
  available_risk_cny: string | null;
  unrealized_pnl_cny: string;
  realized_pnl_cny: string | null;
  full_capital_at_risk_cny: string;
  limits: Record<string, string>;
  exit_basis: string;
  [key: string]: unknown;
}

export interface RiskEngineReport {
  schema_version: string;
  action: "no_order";
  status: string;
  namespace?: string;
  generated_at?: string;
  blockers: string[];
  sleeves: Record<string, RiskEngineSleeveReview> | null;
  aggregate?: {
    total_assets_cny?: string;
    cash_cny?: string;
    reserve_cny?: string;
    [key: string]: unknown;
  } | null;
  position_guidance?: unknown;
  expected_return?: unknown;
  trade_eligible: boolean;
  acceptance_authority: string;
  [key: string]: unknown;
}

export interface RiskResponse {
  security_attributes?: Record<string, unknown> | null;
  action: "no_order";
  status: ApiStatus;
  blockers: string[];
  engine: RiskEngineReport | null;
  facts: RiskFacts | null;
}

/** TL9 MVP-1: the compact identity block every public endpoint carries. */
export interface PublicPacketBlock {
  schema_version: string;
  action: "no_order";
  packet_status: string;
  publication_id: string | null;
  research_version: string | null;
  research_as_of: string | null;
  decision_published_on: string | null;
  excel_published_as_of: string | null;
  quote_bridge: {
    registered_at: string | null;
    sha256: string | null;
    quotes_registered: number;
  } | null;
  source_binding_count: number;
  generated_at: string;
}

export interface PacketFreshness {
  status: string;
  reason?: string | null;
  note?: string | null;
  quote_date?: string | null;
  latest_completed_trade_session?: string | null;
  research_as_of?: string | null;
  as_of?: string | null;
}

/** Optional last_run.research_review; machine replay is not research approval. */
export interface DailyMachineResearchReview {
  status:
    "SOURCE_REPLAYED" | "UNVERIFIED" | "RECEIPT_UNAVAILABLE" | "NOT_RECORDED";
  checked_at: string | null;
  review_cutoff: string | null;
  scope?: "MACHINE_REVIEW_NOT_RESEARCH_APPROVAL";
  action: "no_order";
  formal_eligibility: false;
  rows: {
    symbol: string;
    status: string;
    research_as_of: string | null;
    scan_through: string | null;
    observed_at?: string | null;
    full_calendar_window_elapsed?: boolean | null;
    event_coverage_through: string | null;
    event_coverage_status: "COMPLETE" | "UNCONFIRMED";
    announcement_count: number | null;
    facts_change_status: string | null;
    model_validity_status: string | null;
    model_recalculation_required: boolean | null;
    materiality_review_required: boolean | null;
    formal_eligibility: false;
  }[];
}

export interface PacketPendingAction {
  code: string;
  actor: string;
  label: string;
}

export interface PacketCompanyStatus {
  decision_chain?: {
    action: "no_order";
    formal_eligibility: boolean;
    research_conclusion?: {
      status: string | null;
      summary: string | null;
      evidence_verified: boolean;
      scope: string;
    };
    gaps: {
      code: string;
      classification:
        "ENGINEERING" | "DATA" | "EVIDENCE" | "HUMAN" | "STRATEGY" | "PRIVATE";
      reason: string;
      next_url: string;
    }[];
  };
  symbol: string;
  name: string;
  coverage: string;
  research_status: { code?: string; user_label?: string } | null;
  valuation_status: { code?: string; user_label?: string } | null;
  research_version: string | null;
  decision_as_of: string | null;
  price_bridge: Record<string, unknown> | null;
  next_trigger: string | null;
  pending_actions: PacketPendingAction[];
  blockers: string[];
  valuation_review?: {
    model_validity?: { status?: string } | null;
    price_attractiveness_status?: string | null;
    conditional_range_present?: boolean;
    blockers?: string[];
  } | null;
  registered_research?: {
    status?: string | null;
    valuation_route?: string | null;
    summary?: string | null;
    missing_inputs?: string[];
    evidence?: {
      path: string;
      sha256: string | null;
      sha256_verified: boolean;
      present: boolean;
    }[];
  } | null;
}

/** The shared date block carried by the packet and the snapshot metadata. */
export interface PacketDates {
  current_natural_date: string | null;
  latest_completed_trade_session: string | null;
  quote_trade_date: string | null;
  quote_observed_at: string | null;
  research_as_of: string | null;
  model_validity: { status: string; valid_through: string | null };
  decision_published_on: string | null;
  excel_published_as_of: string | null;
  excel_quote_observation_as_of: string | null;
}

/** TL10-RC: the workbook comparison recorded inside the published packet. */
export interface ExcelSyncRecord {
  path: string | null;
  status: string;
  expected_sha256: string | null;
  observed_sha256: string | null;
  matches: boolean | null;
  checked_at: string | null;
  note: string | null;
}

/** TL10-RC: read-time, read-only comparison against the formal workbook. */
export interface ExcelLiveCheck {
  status: string;
  path: string | null;
  expected_sha256: string | null;
  observed_sha256: string | null;
  pointer_published_as_of: string | null;
  checked_at: string | null;
  note: string | null;
}

/** TL10-RC: version metadata for the one frozen daily public snapshot. */
export interface DailyPublicSnapshot {
  schema_version: string;
  action: "no_order";
  status: string;
  reason: string | null;
  publication_id: string | null;
  packet_path: string | null;
  packet_sha256: string | null;
  content_sha256: string | null;
  engine_version: string | null;
  research_version: string | null;
  generated_at: string | null;
  published_at: string | null;
  receipt_path: string | null;
  dates: PacketDates | null;
  excel_sync: ExcelSyncRecord | null;
  excel_live: ExcelLiveCheck | null;
}

export interface RuntimeIdentity {
  schema_version: "runtime-identity-v1" | "runtime-identity-v2";
  action: "no_order";
  checked_at: string;
  status: "MATCHED" | "MISMATCH";
  reasons: string[];
  current_source_head: string | null;
  source_worktree_dirty: boolean | null;
  backend_loaded_head: string | null;
  backend_module_sha256_loaded: string | null;
  backend_module_sha256_on_disk: string | null;
  web_build: {
    commit: string;
    built_at: string;
    source_dirty: boolean;
  } | null;
  web_index_sha256: string | null;
  publication_registry?: {
    status: "MATCHED" | "MISMATCH" | "UNAVAILABLE";
    checked_count: number;
    mismatched_roles: string[];
  };
  publication: {
    status: string;
    publication_id: string | null;
    packet_sha256: string | null;
    published_at: string | null;
    dates: PacketDates | null;
  };
}

export interface ResearchFunnelStatus {
  schema_version: "public-research-funnel-status-v1";
  action: "no_order";
  status: "VERIFIED" | "UNAVAILABLE" | "INVALID";
  reason: string | null;
  task_id: string | null;
  as_of: string | null;
  audit_sha256: string | null;
  review: {
    status: string | null;
    approved: boolean;
  } | null;
  universe: {
    securities: number;
    industries_mapped: number;
    market_snapshots: number;
    leads: number;
  } | null;
  evidence: {
    financial_symbols: number;
    financial_points: number;
    dividend_evidence_count: number;
    same_period_complete_symbols: number;
    quality_pass: number;
    quality_data_gap: number;
    quality_insufficient_evidence: number;
    capital_return_status: string | null;
    capital_return_reason: string | null;
  } | null;
  quote: {
    date: string | null;
    trade_date_verified: boolean;
    verified_count: number;
    unverified_count: number;
  } | null;
  queue: {
    entry_count: number;
    selected_count: number;
    deferred_count: number;
    selected_symbols: string[];
  } | null;
  channels: Array<{
    key: string;
    pass_count: number;
    data_gap_count: number;
    insufficient_evidence_count: number;
    rejected_count: number;
    not_evaluated_count: number;
    budget_excluded_count: number;
    unsupported_count: number;
    top_reason: string | null;
  }>;
  sample: Array<{
    symbol: string;
    name: string;
    industry: string;
    channels: string[];
    research_state: string;
    gaps: string[];
  }>;
  blockers: string[];
  source_files: Record<string, { path: string; sha256: string }>;
  artifacts: {
    manifest: { path: string; sha256: string };
    result_sha256: string;
    report_sha256: string;
    review_packet_sha256: string;
  } | null;
}

/** The one public daily decision packet (TL9 MVP-1). */
export interface DailyPublicPacket {
  schema_version: string;
  engine_version?: string | null;
  action: "no_order";
  packet_status: string;
  publication_id: string | null;
  research_version: string | null;
  generated_at: string;
  chain_error?: string | null;
  snapshot_status?: string | null;
  snapshot_reason?: string | null;
  content_sha256?: string | null;
  identity_inputs?: Record<string, unknown> | null;
  dates: PacketDates;
  formal_admission_count: number;
  pending_review_count: number;
  research_counts: {
    universe_count: number | null;
    lead_count: number | null;
    queue_count: number | null;
    needs_re_research_count: number;
    incomplete_research_count: number;
    awaiting_verified_close_count: number;
  };
  blockers: string[];
  data_freshness: {
    quote: PacketFreshness;
    research: PacketFreshness;
    excel: PacketFreshness;
  };
  quote_bridge?: {
    path: string;
    sha256: string | null;
    registered_at: string | null;
    quotes_registered: number;
  } | null;
  source_bindings?: Array<{
    role: string;
    path: string;
    sha256: string | null;
    present?: boolean;
    sha256_verified?: boolean;
  }> | null;
  source_bindings_verified: boolean;
  company_statuses: Record<string, PacketCompanyStatus>;
  excel_sync?: ExcelSyncRecord | null;
}
