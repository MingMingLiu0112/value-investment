export type State = {
  cash_cny: string;
  confirmed_fees_cny: string;
};

export type SimulatedPosition = {
  symbol: string;
  quantity: string;
  cost_cny: string;
  sleeves: {
    sleeve: "CORE_VALUE";
    sellable_quantity: string;
    next_sell_session?: string | null;
  }[];
};

export type Journey = {
  schema_version: "simulated-trade-journey-v1";
  status: "SIMULATED_JOURNEY_COMPLETE";
  approval_changed: false;
  namespace: "SIMULATED";
  action: "no_order";
  actual_account_used: false;
  strategy_validated: false;
  broker_execution_permission: false;
  steps: {
    label: string;
    sleeve?: string;
    rationale?: string;
    reason?: string;
    quantity?: string;
    price_cny?: string;
    before: State;
    after: State;
  }[];
  checks: Record<string, boolean>;
  assumptions: {
    entry_thesis: string;
    initial_cash_cny: string;
  };
};

export type Binding = {
  path: string;
  sha256: string;
};

export type SourceCase = {
  symbol: string;
  company_name: string;
  action: "no_order";
  research: {
    candidate_binding: Binding;
    research_version: string;
    model_context: Record<string, unknown>;
    generated_at: string;
    replayed_at?: string | null;
    research_as_of: string;
    valuation_date: string;
    available_at: string;
    computed_at: string;
    thesis: unknown;
    confidence?: string;
    counter_evidence?: unknown;
    thesis_breakers: unknown;
    scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL";
  };
  plan: {
    research_version: string;
    signal_state: string;
    candidate_action: string;
    verification_scope: string;
  };
  evaluation: {
    symbol: string;
    action: "no_order";
    strategy: "CORE_VALUE";
    decision_action: string;
    eligibility: false;
    review_quantity: null;
    position_range: null;
  };
  action_slots: {
    intent: string;
    outcome: string;
    strategy_verdict: string;
    reasons: string[];
    formal_eligibility: false;
    review_quantity: null;
    action: "no_order";
  }[];
};

export type ManualRow = {
  symbol: string;
  side: "BUY" | "SELL";
  scope: string;
  fill: {
    symbol: string;
    side: string;
    quantity: string;
    price_cny: string;
    fees_cny: string;
    trade_date: string;
    next_sell_session?: string;
  };
  source_candidate_binding: Binding;
  fill_record_sha256: string;
  recorded_at: string;
  original_entry_advisory_eligible: false;
  execution_price_scope: string;
  snapshot_status: string;
  historical_reference_status: string;
  historical_reference_scope: string | null;
  t1_negative_status?: string;
  confirmation_idempotent: true;
  prepared_cash_unchanged: true;
};

export type SourceBoundJourney = {
  schema_version: "source-bound-simulated-trade-journey-v1";
  namespace: "SIMULATED";
  research_namespace: "PUBLIC_SOURCE_BOUND";
  action: "no_order";
  scope: "PUBLIC_RESEARCH_WITH_OPTIONAL_ISOLATED_MANUAL_ACCOUNTING";
  research_evaluated_at: string;
  strategy_validated: false;
  approval_changed: false;
  broker_execution_permission: false;
  personal_risk_evaluated: false;
  position_guidance: null;
  source_files_verified: number;
  cases: SourceCase[];
  manual_rehearsal: {
    status: "NOT_REQUESTED" | "EXPLICIT_SIMULATED_RECORDS_ONLY";
    fills: ManualRow[];
    account_state:
      | (State & {
          positions?: SimulatedPosition[];
        })
      | null;
    journal_receipt: {
      sha256: string;
      retained: false;
    } | null;
    actual_account_used: false;
    temporary_journal_removed: true;
    restart_equal?: true;
    same_session_sell_rejected?: boolean | null;
    t1_negative_checks?: number;
  };
};

export type ExpectedCandidate = {
  symbol: string;
  candidate_binding: Binding;
  research_version: string;
};
