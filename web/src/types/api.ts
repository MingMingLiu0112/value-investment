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
  reduce_condition?: PlanCondition | null;
  exit_condition?: PlanCondition | null;
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

/** One executed admission of the registered close against the registered research cutoff. */
export interface PriceBridgeExecution {
  incremental_validity?: {
    status: string | null;
    review_cutoff: string | null;
    announcement_count: number | null;
    blockers: string[];
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

export interface DailyResponse {
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

export interface DetailResponse {
  action: "no_order";
  status: ApiStatus;
  decision: DecisionItem | null;
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

export interface PortfolioTrade {
  judgment_snapshot?: {
    publication_id: string;
    recorded_at: string;
    trade_time_availability_proven: boolean;
    snapshot_sha256: string;
    plan: CurrentPricePlan;
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
