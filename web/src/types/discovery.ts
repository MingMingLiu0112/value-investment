export interface ScanLead {
  symbol: string;
  company_name: string;
  channels: string[];
  screening_reasons: string[];
  next_required_evidence: string;
  evidence_ids: string[];
  financial_observations?: {
    field_name: string;
    value: string;
    unit: string;
    period_label: string;
    available_at: string;
    source_name: string;
    source_url: string;
    raw_file_hash: string;
    validation_status: string;
  }[];
}

export interface CurrentScreening {
  status: string;
  scope: string;
  as_of?: string;
  universe_count?: number;
  lead_count?: number;
  channel_counts?: Record<string, number>;
  quote_date_verification?: string;
  screening_scope?: {
    all_a_complete: false;
    covered_venues: string[];
    failed_venues: string[];
    observed_universe_count: number;
    quote_coverage: Record<string, { excluded_row_count: number }>;
  };
  details?: {
    status: string;
    leads: ScanLead[];
    financial?: {
      status: string;
      period?: string;
      provider_rows?: number;
      observation_count?: number;
      adopted_observation_count?: number;
      missing_fields?: number;
    };
  };
}
