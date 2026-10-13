export type ApiStatus = string;

export interface DecisionItem {
  id: string;
  symbol?: string;
  name?: string;
  strategy?: string;
  status?: string;
  candidate_action?: string;
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
  [key: string]: unknown;
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
  blockers: string[];
  gate_code?: string;
  reason?: string;
  publication_source?: string;
}

export interface DetailResponse {
  action: "no_order";
  status: ApiStatus;
  decision: DecisionItem | null;
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
}

export interface PortfolioDraft {
  status: string;
  prepared_record_sha256: string;
  fill: Record<string, unknown>;
  cash_cny: string;
  realized_pnl_cny: string;
  positions: PortfolioPosition[];
}

export interface PortfolioResponse {
  action: "no_order";
  status: ApiStatus;
  revision: number;
  as_of: string | null;
  cash_cny: string | null;
  realized_pnl_cny: string | null;
  positions: PortfolioPosition[];
  trades: PortfolioTrade[];
  policy: Record<string, unknown> | null;
  pending_draft: PortfolioDraft | null;
  latest_snapshot: Record<string, unknown> | null;
  valuation: { status: string; reason: string };
  blockers: string[];
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
  action: "no_order";
  status: ApiStatus;
  blockers: string[];
  engine: RiskEngineReport | null;
  facts: RiskFacts | null;
}
