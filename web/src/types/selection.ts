export interface SelectionCondition {
  field: string;
  unit: string;
  period: string;
  status: string;
  value?: number | string | null;
  operator?: string;
  threshold?: number | string;
  favorable?: boolean | null;
  stale?: boolean;
  evidence?: {
    source_url?: string;
    raw_file_hash?: string;
    available_at?: string;
  }[];
}
export interface SelectionRow {
  research_summary?: {
    status: string;
    valuation?: {
      bear_value?: string | number;
      base_value?: string | number;
      bull_value?: string | number;
      confidence?: string;
    } | null;
    valuation_date?: string;
    research_as_of?: string;
    blockers?: string[];
  };
  valid_from_session?: string;
  expires_after_session?: string;
  source_available_at?: string;
  evidence_refs?: string[];
  channel_evaluations?: { channel: string; status: string; reason: string }[];
  blockers?: string[];
  symbol: string;
  company_name?: string;
  name?: string;
  industry?: string;
  profile_status?: string;
  cycle_status?: string;
  selection_status?: string;
  structure_status?: string;
  data_status?: string;
  reasons?: string[];
  decision_explanation?: {
    state: "WAIT";
    action: "no_order";
    formal_eligibility: false;
    holding_action_eligibility: false;
    owned_entry_supplied: false;
    wait_reasons: string[];
    rule_inputs?: {
      daily_trend: string;
      primary_structure: string;
      structural_distance_ratio: string | number | null;
      next_bar_confirmed: boolean;
      pullback_recovery_observed: boolean;
    };
  };
  conditions?: SelectionCondition[];
  missing_periods?: string[];
  entry_condition?: unknown;
  invalidation_condition?: unknown;
  observation_summary?: {
    favorable: number;
    unfavorable: number;
    missing: number;
    conflicting: number;
  };
}
export interface SelectionLane {
  pagination?: { offset: number; limit: number; total: number | null };
  items: SelectionRow[];
  shortlist: SelectionRow[];
  coverage?: Record<string, number>;
  quote_date?: string;
  trade_date?: string;
  data_status?: string;
  status?: string;
  blockers?: string[];
  rule_version?: string;
  snapshot_status?:
    "CURRENT_ATTEMPT_SOURCE_REVALIDATED" | "RETAINED_DATED_RESEARCH";
  refresh_status?:
    "SOURCE_REVALIDATED" | "NOT_ATTEMPTED" | "INCOMPLETE" | "COLLECTION_FAILED";
  available_at?: string;
  latest_attempt?: {
    mode: string;
    status: string;
    run_status?: string;
    started_at?: string;
    finished_at?: string;
  };
}
export interface DualStrategySelection {
  value: SelectionLane;
  hotspot: SelectionLane;
  action: "no_order";
  evaluated_at: string;
  content_sha256: string;
}
