export type SimulatedSleeve = "CORE_VALUE" | "HOTSPOT_SATELLITE";
export type SimulatedOperation =
  | "initialize"
  | "prepare-fill"
  | "confirm-fill"
  | "cancel-fill"
  | "confirm-entry"
  | "correct-fill";
export type SimulatedBinding = { path: string; sha256: string };
export type SimulatedFill = {
  transaction_id: string;
  side: "BUY" | "SELL";
  sleeve: SimulatedSleeve;
  symbol: string;
  exchange: "SSE" | "SZSE";
  quantity: string;
  price_cny: string;
  fees_cny: string;
  trade_date: string;
};
export type SimulatedEntry = {
  transaction_id: string;
  symbol: string;
  sleeve: SimulatedSleeve;
  remaining_quantity: string;
  fill_record_sha256: string;
  hypothesis: {
    thesis: string;
    hold_logic: string;
    invalidation_conditions: string[];
    research_version: string;
    strategy_version: string;
  } | null;
  entry_confirmation_sha256: string | null;
  original_pit_proven: false;
  advisory_eligible: false;
  fill_correction?: SimulatedFillCorrection | null;
  hypothesis_review_status?:
    "UNCHANGED" | "ACCOUNT_HISTORY_CORRECTED_REVIEW_REQUIRED";
};
export type SimulatedFillCorrection = {
  original_fill: SimulatedFill & Record<string, unknown>;
  effective_fill: SimulatedFill & Record<string, unknown>;
  effective_version_sha256: string;
  correction_record_sha256s: string[];
};
export type PersistentSimulatedWorkbench = {
  schema_version: "persistent-simulated-workbench-v1";
  action: "no_order";
  namespace: "SIMULATED";
  formal_eligibility: false;
  actual_account_used: false;
  position_guidance: null;
  server_now: string;
  account: {
    schema_version: "persistent-simulated-portfolio-v1";
    account_context: {
      namespace: "SIMULATED";
      account_id: string;
      version: "persistent-simulated-portfolio-v1";
    };
    account_id: string;
    namespace: "SIMULATED";
    action: "no_order";
    status: "NOT_INITIALIZED" | "CONNECTED";
    revision: number;
    formal_eligibility: false;
    actual_account_used: false;
    ownership_verified: false;
    position_guidance: null;
    confirmed_fill_correction: "UNSUPPORTED" | "PRICE_QUANTITY_FEES_ONLY_V1";
    fill_corrections?: Record<string, SimulatedFillCorrection>;
    correction_reconciliation_status?:
      | "INVALIDATED_RECONCILIATION_REQUIRED"
      | "RECONCILED_AFTER_CORRECTION"
      | "NOT_APPLICABLE";
    source_scope: "HASH_BOUND_REFERENCE_NOT_STRATEGY_OR_MARKET_PRICE_ADMISSION";
    entries: SimulatedEntry[];
    portfolio: {
      action: "no_order";
      revision: number;
      as_of: string;
      cash_cny: string;
      realized_pnl_cny: string;
      positions: {
        symbol: string;
        exchange: string;
        quantity: string;
        cost_cny: string;
        sleeves: {
          sleeve: SimulatedSleeve;
          quantity: string;
          cost_cny: string;
          sellable_quantity: string;
          next_sell_session: string | null;
        }[];
      }[];
      trades: (SimulatedFill & {
        record_sha256: string;
        confirmed_at: string;
        fill_correction?: SimulatedFillCorrection;
      })[];
      pending_draft: {
        status: "DRAFT_UNRECONFIRMED";
        prepared_record_sha256: string;
        fill: SimulatedFill;
        cash_cny: string;
        realized_pnl_cny: string;
      } | null;
    } | null;
  };
  sources: {
    status: "AVAILABLE" | "UNAVAILABLE";
    items: {
      id: "core:600519" | "swing:300750";
      symbol: string;
      sleeve: SimulatedSleeve;
      candidate_binding: SimulatedBinding;
      scope: "REFERENCE_ONLY_NOT_APPROVAL";
    }[];
  };
  mutation?: {
    operation: SimulatedOperation;
    record_sha256: string;
    result?: unknown;
  };
};
export type SimulatedWrite = {
  confirmed_hypothetical: true;
  idempotency_key: string;
  expected_revision: number;
} & Record<string, unknown>;
