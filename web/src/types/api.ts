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
    universe_count: number;
    formal_count: number;
    watch_count: number;
  };
  sections: {
    holdings: DecisionItem[];
    value: DecisionItem[];
    hotspot: DecisionItem[];
  };
  blockers: string[];
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
  items: DecisionItem[];
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
