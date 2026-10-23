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
  items: SelectionRow[];
  shortlist: SelectionRow[];
  coverage?: Record<string, number>;
  quote_date?: string;
  trade_date?: string;
  data_status?: string;
  status?: string;
  blockers?: string[];
  rule_version?: string;
}
export interface DualStrategySelection {
  value: SelectionLane;
  hotspot: SelectionLane;
  action: "no_order";
  evaluated_at: string;
  content_sha256: string;
}
