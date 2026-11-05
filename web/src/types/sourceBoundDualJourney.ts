import type { Binding, SourceCase } from "./simulatedJourney";

export type DualIdentity = {
  core: {
    symbol: string;
    candidate_binding: Binding;
    research_version: string;
  }[];
  hotspot: {
    symbol: string;
    receipt_binding: Binding;
    entry_freeze_sha256: string;
  };
};
export type DualActionSlot = Omit<
  SourceCase["action_slots"][number],
  "strategy_verdict"
>;
export type DualAccountState = {
  cash_cny: string;
  confirmed_fees_cny: string;
  hypothetical_equity_cny: string | null;
  positions: unknown[];
  aggregate_holdings: {
    symbol: string;
    quantity: string;
    market_value_cny: string | null;
  }[];
  mark_scope: string;
  risk_scope: string;
  sleeve_cash_review: {
    action: "no_order";
    trade_eligible: false;
    status: string;
    blockers: string[];
    sleeves: Record<string, { cash_cny: string; shortfall_cny: string }> | null;
  };
  risk_review: Record<string, unknown> & { status: string; blockers: string[] };
};
export type DualManualRow = {
  intent: "BUY" | "ADD" | "REDUCE" | "EXIT";
  fill: {
    transaction_id: string;
    side: "BUY" | "SELL";
    sleeve: "CORE_VALUE" | "HOTSPOT_SATELLITE";
    symbol: string;
    quantity: string;
    price_cny: string;
    fees_cny: string;
    trade_date: string;
  };
  rationale: string;
  source_version: string;
  fill_record_sha256: string;
  source_reference: unknown;
  original_entry_transaction_id: string | null;
  original_entry_reference: {
    narrative: {
      thesis: string;
      hold_logic: string;
      invalidation_conditions: string[];
    };
    fill_record_sha256: string;
    key: string[];
  } | null;
  consumed_original_entries?: {
    transaction_id: string;
    quantity: string;
    original_entry_reference: NonNullable<
      DualManualRow["original_entry_reference"]
    >;
    manual_rationale: string;
    consistency_scope: "MANUAL_REASON_COMPARED_WITH_RECONSTRUCTED_THESIS_NOT_APPROVAL";
  }[];
  original_pit_proven: false;
  original_entry_advisory_eligible: false;
  confirmation_idempotent: true;
  prepared_cash_unchanged: true;
  entry_blockers: string[];
  scope: string;
  execution_price_scope: string;
  fee_scope: string;
  requested_quantity: string;
  unfilled_quantity: string;
  unfilled_scope: string;
  before: DualAccountState;
  after: DualAccountState;
};
export type SourceBoundDualPacket = {
  schema_version: "source-bound-dual-sleeve-journey-v1";
  namespace: "SIMULATED";
  action: "no_order";
  scope: "DISPOSABLE_SOURCE_BOUND_REHEARSAL_NOT_PERSISTENT_PORTFOLIO";
  research_evaluated_at: string;
  source_identity: DualIdentity;
  core_cases: SourceCase[];
  hotspot_case: {
    symbol: string;
    sleeve: "HOTSPOT_SATELLITE";
    action: "no_order";
    receipt_binding: Binding;
    entry_freeze_sha256: string;
    source_scope: unknown;
    historical_only: true;
    current_signal: false;
    current_pit: false;
    strategy_validated: false;
    formal_eligibility: false;
    review_quantity: null;
    entry_reference: Record<string, unknown> & {
      namespace: "SIMULATED";
      symbol: string;
      assumed_entry_at: string;
      generated_at: string;
      entry_case_binding: Binding;
      entry_origin: string;
      fill_scope: string;
    };
    lifecycle_reviews: (Record<string, unknown> & {
      evaluated_at: string;
      action: "no_order";
    })[];
    action_slots: DualActionSlot[];
  };
  manual_rehearsal: {
    status: "NOT_REQUESTED" | "EXPLICIT_SIMULATED_RECORDS_ONLY";
    fills: DualManualRow[];
    account_state: DualAccountState | null;
    journal_receipt: {
      sha256: string;
      retained: false;
      record_count: number;
    } | null;
    temporary_journal_removed: true;
    actual_account_used: false;
    persistent_simulated_portfolio: false;
    restart_equal?: true;
    assumptions?: Record<string, unknown>;
  };
  actual_account_used: false;
  formal_eligibility: false;
  strategy_validated: false;
  approval_changed: false;
  broker_execution_permission: false;
  position_guidance: null;
};

export type DualFormRow = {
  price: string;
  fees: string;
  quantity: string;
  rationale: string;
  thesis: string;
  hold: string;
  breakers: string;
};
