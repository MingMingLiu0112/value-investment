import type { TrackingPoolView } from "../components/ValueTrackingResearchPool";
import type { ScreenPage } from "../components/SseMainScreeningPanel";
import type { CompanyProfile } from "../components/CompanyProfilePanel";
import type {
  PrivateAccountObservations,
  DailyResponse,
  DailyPublicPacket,
  DailyPublicSnapshot,
  RuntimeIdentity,
  ResearchFunnelStatus,
  DetailResponse,
  HistoryResponse,
  HistoricalCaseListing,
  HistoricalPriceCase,
  CurrentPriceCase,
  CurrentPricePlan,
  PortfolioResponse,
  PolicyResponse,
  RiskResponse,
  HeldContinuityResponse,
  WriteResponse,
} from "../types/api";
import type { CurrentScreening } from "../types/discovery";
import type { DualStrategySelection } from "../types/selection";

export interface PublicEvidenceStatus {
  schema_version: "public-evidence-status-v1";
  action: "no_order";
  status: "VERIFIED" | "PARTIAL" | "MISSING" | "CONFLICT";
  scope: "REQUESTED_REPORTS_ONLY";
  generated_at: string | null;
  reason: string | null;
  items: {
    symbol: string;
    issuer_name: string;
    period: string;
    status: string;
    source_url: string | null;
    sha256: string | null;
    published_date: string | null;
    fetched_at: string | null;
    reused: boolean;
    reason: string | null;
    fact_status: string;
    adopted_fact_count: number;
    fact_issues?: string[];
    adopted_fields?: string[];
  }[];
  exchanges: Record<
    "SSE" | "SZSE" | "BSE",
    { requested: number; verified: number }
  >;
  formal_eligibility: false;
  strict_historical_pit: false;
}

export interface HeldSellReviewRequest {
  schema_version: "private-held-sell-review-request-v1";
  action: "no_order";
  expected_revision: number;
  account_scope: string;
  symbol: string;
  exchange: string;
  sleeve: string;
  requested_action: "REDUCE" | "EXIT";
  requested_quantity: number;
  entry_thesis_record_sha256: string;
  read_and_confirmed: true;
}
import type {
  HotspotSizingRequest,
  HotspotSizingResponse,
} from "../components/HotspotSizingPanel";
import type { PrivateRiskContext } from "../components/PrivateRiskContext";
import type { EntryThesisView } from "./entryThesis";
import type { CommittedRiskView } from "./committedRisk";
import type {
  PolicyPreview,
  PolicyRegistration,
  PolicySelection,
  PolicyStatus,
  PolicyHandoff,
} from "./valuePolicy";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, detail: unknown) {
    super(detail ? String(detail) : `${code} (HTTP ${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function read(response: Response): Promise<Record<string, unknown>> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (
    !body ||
    typeof body !== "object" ||
    (body as Record<string, unknown>).action !== "no_order"
  ) {
    throw new Error("服务响应不符合只读决策契约");
  }
  const record = body as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      String(record.status ?? "HTTP_ERROR"),
      record.detail ?? record.reason ?? null,
    );
  }
  return record;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    signal,
    credentials: "same-origin",
  });
  return (await read(response)) as T;
}

const SESSION_HEADER = "X-Local-Session";
const TOKEN_STORAGE_KEY = "vi-local-session";
const UNLOCK_PATH = "/api/v1/private/session/unlock";
let sessionToken: string | null = null;
let handshake: Promise<string> | null = null;

type WorkbenchWindow = {
  location?: { hash?: string; pathname?: string; search?: string };
  history?: {
    replaceState(data: unknown, unused: string, url?: string): void;
  };
  sessionStorage?: Storage;
};

function workbenchWindow(): WorkbenchWindow | null {
  return typeof window === "undefined" ? null : (window as WorkbenchWindow);
}

function fragmentSecret(): string | null {
  const hash = workbenchWindow()?.location?.hash ?? "";
  const match = /[#&]unlock=([A-Za-z0-9_-]{16,})/.exec(hash);
  return match ? match[1] : null;
}

function stripUnlockFragment(): void {
  const holder = workbenchWindow();
  if (!holder?.location || !holder.history || fragmentSecret() === null) return;
  holder.history.replaceState(
    null,
    "",
    holder.location.pathname + (holder.location.search ?? ""),
  );
}

function readStoredToken(): string | null {
  try {
    return (
      workbenchWindow()?.sessionStorage?.getItem(TOKEN_STORAGE_KEY) ?? null
    );
  } catch {
    return null;
  }
}

function storeToken(token: string): void {
  try {
    workbenchWindow()?.sessionStorage?.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Storage can be unavailable; the in-memory token still covers this tab.
  }
}

function forgetSession(): void {
  sessionToken = null;
  handshake = null;
  try {
    workbenchWindow()?.sessionStorage?.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage failures; nothing else is persisted.
  }
}

function forgetRefusedSession(token: string): void {
  // A late 401 must not discard a newer authorization or its shared handshake.
  if (!handshake && (sessionToken ?? readStoredToken()) === token)
    forgetSession();
}

/**
 * Whether this tab already holds an unlock session. The private-state mapping
 * uses it to tell a session that expired (service restarted) apart from a
 * page that was never unlocked; the current read itself changes nothing here.
 */
export function hadSessionToken(): boolean {
  return sessionToken !== null || readStoredToken() !== null;
}

// The workbench starts locked. The launcher mints a per-run secret and opens
// the page with `#unlock=<secret>`; the fragment never reaches the server, and
// this exchange is the only way to obtain a session token.
async function unlockSession(): Promise<string> {
  const secret = fragmentSecret();
  if (!secret) {
    throw new ApiError(
      401,
      "LOCAL_SESSION_LOCKED",
      "工作台已锁定：请通过本机启动脚本（start_web_workbench.ps1）重新打开一次性解锁链接",
    );
  }
  const response = await fetch(UNLOCK_PATH, {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ bootstrap_token: secret }),
  });
  let body: Record<string, unknown> | null = null;
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = null;
  }
  const token = body && typeof body.token === "string" ? body.token : "";
  if (!response.ok || token.length === 0) {
    throw new ApiError(
      response.status,
      String(body?.status ?? "LOCAL_SESSION_LOCKED"),
      body?.detail ?? null,
    );
  }
  storeToken(token);
  stripUnlockFragment();
  return token;
}

async function operatorToken(): Promise<string> {
  if (handshake) return handshake;
  // A freshly supplied launch link takes priority over a stale stored session.
  if (!fragmentSecret()) {
    if (sessionToken) return sessionToken;
    const stored = readStoredToken();
    if (stored) {
      sessionToken = stored;
      return stored;
    }
  }
  if (!handshake) {
    handshake = unlockSession()
      .then((token) => {
        sessionToken = token;
        return token;
      })
      .finally(() => {
        handshake = null;
      });
  }
  return handshake;
}

//
// Consume a launcher-provided one-time fragment as soon as the app loads.
// Client-side navigation otherwise drops it before the first explicit
// research-task read. No data or model task is requested by this exchange.
if (fragmentSecret()) {
  void operatorToken().catch(() => undefined);
}
async function post<T>(
  path: string,
  body: Record<string, unknown>,
): Promise<T> {
  let usedToken = "";
  const send = async (): Promise<Response> => {
    usedToken = await operatorToken();
    return fetch(`/api/v1/${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        [SESSION_HEADER]: usedToken,
      },
      body: JSON.stringify(body),
    });
  };
  let response = await send();
  if (response.status === 401) {
    // The session token expired or the service restarted; a rejected request
    // never touched the ledger, so one re-handshake and one retry is safe.
    forgetRefusedSession(usedToken);
    response = await send();
  }
  return (await read(response)) as T;
}

async function getPrivate<T>(path: string, signal?: AbortSignal): Promise<T> {
  let usedToken = "";
  const send = async (): Promise<Response> => {
    usedToken = await operatorToken();
    return fetch("/api/v1/" + path, {
      signal,
      credentials: "same-origin",
      headers: { [SESSION_HEADER]: usedToken },
    });
  };
  let response = await send();
  if (response.status === 401) {
    // Same re-handshake pattern as POST: the refused read never reached the
    // ledger, so one fresh token and one retry is safe.
    forgetRefusedSession(usedToken);
    response = await send();
  }
  return (await read(response)) as T;
}

export type QuotePlanObservation = {
  binding_sha256: string;
  states: {
    kind: string;
    status?: string;
    reason?: string;
    next_step?: string;
    blockers?: string[];
    condition: { threshold: string; operator: "GT" | "LT" };
    state: { status: string; reason: string; checked_at: string };
  }[];
  transitions: QuotePlanTransition[];
};

export type FirstResearchScenarioKey = "bear" | "base" | "bull";

export type FirstResearchAnnualRow = {
  year: number | string;
  profit?: string | number;
  distribution?: string | number;
  retained?: string | number;
  [key: string]: unknown;
};

export type FirstResearchAnnualLedger = {
  rows10?: FirstResearchAnnualRow[];
  rows?: FirstResearchAnnualRow[];
  funding_status?: string;
  [key: string]: unknown;
};

export type FirstResearchInputResponse = {
  schema_version?: string;
  symbol: string;
  status: "NOT_STARTED" | "SOURCE_BOUND_FIRST_INPUT_COMPILED" | "UNASSESSABLE";
  scope: "CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE";
  action: "no_order";
  successor_update?: {
    status:
      "NOT_STARTED" | "SOURCE_BOUND_CONDITIONAL_SUCCESSOR" | "UNASSESSABLE";
    reason?: string;
    symbol: string;
    action: "no_order";
    formal_eligibility: false;
    main_range_adopted: false;
    price_admitted: false;
    changed_input_fields?: string[];
    change_rationale?: string;
    countercase?: string;
    research_as_of?: string;
    financial_basis?: string;
    predecessor_input_fingerprint?: string;
    successor_input_fingerprint?: string;
    predecessor_valuation?: FirstResearchInputResponse["valuation"];
    successor_valuation?: FirstResearchInputResponse["valuation"];
    valuation_changed?: boolean;
  };
  formal_eligibility: false;
  main_range_adopted: false;
  main_valuation_range: null;
  current_price: null;
  quote_observation?: {
    status: string;
    quote_date: string | null;
    display_price: string | number | null;
    bundle_sha256: string | null;
    price_admitted: boolean;
    comparison_eligible: boolean;
  };
  condition_price: null;
  personal_quantity: null;
  company_name?: string;
  financial_basis?: string;
  research_as_of?: string;
  available_at?: string;
  reason?: string | null;
  investment_conclusion?: string;
  research_case?: {
    symbol?: string;
    name?: string;
    thesis: string;
    return_driver?: string;
    counter_evidence: unknown[];
    thesis_breakers: unknown[];
    next_events: unknown[];
  };
  valuation?: {
    bear_value: string | number;
    base_value: string | number;
    bull_value: string | number;
    confidence: string;
    valuation_date: string;
  } | null;
  annual_ledgers?: Record<FirstResearchScenarioKey, FirstResearchAnnualLedger>;
  source_bindings?: { path: string; sha256: string }[];
  input_fingerprint?: string;
  sources?: {
    id?: string;
    title?: string;
    source_url?: string;
    official_url?: string;
    officialURL?: string;
    location?: string;
    url?: string;
    sha256?: string;
  }[];
  native_fact_count?: number;
  operating_assumptions?: unknown;
  blockers?: string[];
};

export type OperatingAssumptionScenario = {
  drivers: unknown;
  operating_capital_path?: unknown;
  terminal_policy: unknown;
  cost_of_equity: string | number;
  classification: string;
  evidence_ref: { path: string; sha256: string; field_path?: string[] };
};

export type OperatingAssumptionDraftResponse = {
  schema_version?: string;
  symbol: string;
  status: "SOURCE_BOUND_D2_DRAFT" | "MISSING_SOURCE" | "UNASSESSABLE";
  company_name?: string;
  as_of?: string;
  available_at?: string;
  branches: {
    branch_id: string;
    title: string;
    economic_rationale: string;
    proposal_rationale: string;
    counter_evidence: string[];
    scenarios: Record<"bear" | "base" | "bull", OperatingAssumptionScenario>;
    classification?: string;
    confidence?: string;
  }[];
  historical_observations: unknown[];
  unknowns: unknown[];
  invalidation_conditions: string[];
  limitations?: string[];
  source_bindings: { path: string; sha256: string }[];
  input_fingerprint?: string;
  missing_sources?: { path: string; sha256?: string | null }[];
  blockers?: string[];
  parameter_basis?: unknown;
  historical_statement_replay?: unknown;
  fact_anchors?: unknown[];
  normalization_open_items?: unknown;
  economic_review_items?: unknown;
  assurance_limits?: unknown;
  action: "no_order";
  formal_eligibility: false;
  valuation_computed: false;
  assumptions_approved?: false;
  research_admitted?: false;
  approval_changed?: false;
  e2_new_company_compilation?: false;
};

export type ResearchTaskCreateRequest = {
  symbol: string;
  workflow: "legacy";
  request_key: string;
};

export type ResearchTaskResponse = {
  task_id: string;
  status:
    | "QUEUED"
    | "RUNNING"
    | "WAITING_EVIDENCE"
    | "SUCCEEDED"
    | "FAILED"
    | "CANCELLED";
  workflow: string;
  symbol: string;
  execution_mode: "SAVED_RESPONSE" | "MOCK";
  snapshot_status: string;
  checkpoint_verified: boolean;
  finding_count?: number;
  error_code: string | null;
  attempts: number;
  provider_requests: number;
  usage: { prompt_tokens: number; completion_tokens: number };
  usage_basis: string;
  new_llm_calls: 0;
  record_binding: { path: string; sha256: string };
  action: "no_order";
  formal_eligibility: false;
};

export type ResearchTaskHistoryResponse = {
  action: "no_order";
  symbol: string;
  items: ResearchTaskResponse[];
  scope: "BOUNDED_TASK_HISTORY";
};

export type AgentResearchResponse = {
  workflow?: string;
  available_workflows?: string[];
  status: string;
  reason: string;
  mode: "MOCK" | "OFFLINE_REPLAY" | "LIVE" | null;
  research_as_of?: string;
  generated_at?: string;
  model_id?: string;
  findings: {
    finding_id: string;
    role: string;
    claim: string;
    evidence_refs: string[];
    counter_evidence_refs: string[];
    proposed_follow_up: string;
  }[];
  sources: {
    evidence_id: string;
    title: string;
    sha256: string;
    available_at: string;
    source_url?: string;
  }[];
  decision_changed: false;
  approval_count: 0;
  formal_fact_count: 0;
};

export type AgentResearchReviewQueueItem = {
  symbol: string;
  name: string | null;
  workflow: string;
  status: "PENDING_HUMAN_REVIEW";
  verification_status: "VERIFIED";
  research_as_of: string | null;
  available_at: string | null;
  source_available_at: string | null;
  source_scope: {
    scope: string;
    data_scope: string | null;
    mode: "MOCK" | "OFFLINE_REPLAY" | "LIVE";
    classification:
      | "TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE"
      | "RESEARCH_DRAFT_NOT_FORMAL_EVIDENCE";
    test_only: boolean;
    formal_evidence: false;
    excerpt_origin: "DERIVED_FROM_VERIFIED_PLAN" | null;
  };
  packet_binding: { path: string; sha256: string };
  registration_binding: { path: string; sha256: string };
  review_reason: string;
  review_reason_text: string;
  next_action: string;
  next_action_text: string;
  pending_findings_count: number;
  action: "no_order";
  approval_unchanged: true;
  formal_eligibility_unchanged: true;
  decision_changed: false;
};

export type AgentResearchStatusResponse = {
  action: "no_order";
  status: string;
  items: {
    symbol: string;
    workflow: string;
    status: string;
    mode: AgentResearchResponse["mode"];
    research_cutoff: string | null;
    packet_sha256: string | null;
    generated_at: string | null;
    findings_count: number;
    pending_human_review: number;
  }[];
  failures: {
    symbol: string | null;
    workflow: string | null;
    status: string;
    reason: string;
  }[];
  review_queue: AgentResearchReviewQueueItem[];
  review_queue_count: number;
  approval_unchanged: true;
  formal_eligibility_unchanged: true;
  decision_changed: false;
};

export type PrivateRetrospective = {
  status: string;
  mode: "MOCK";
  ledger_source: string;
  review_date: string;
  unprocessed_trade_count?: number;
  items: {
    manual_fill: {
      transaction_id: string;
      symbol: string;
      side: string;
      price_cny: string;
      quantity: string;
    };
    differences: {
      field: string;
      saved_reference_cny: string;
      fill_minus_reference_cny: string;
    }[];
    evidence_gaps: string[];
  }[];
};

export type QuotePlanTransition = {
  transition_id: string;
  kind: string;
  status: string;
  checked_at: string;
  price: string | null;
  threshold: string;
  reason: string;
  next_step?: string;
  blockers?: string[];
};

export type PublicObservationResponse = {
  sealed_condition_path?: {
    status: string;
    reason?: string | null;
    scope: string;
    action: "no_order";
    eligibility: false;
    formal_eligibility: false;
    strict_pit_admitted: false;
    strict_oos_admitted: false;
    actual_shadow_sessions: 0;
    real_trade: false;
    hypothetical_fills: null;
    profit: null;
    personal_sell_permission: false;
    original_binding_sha256: string | null;
    bound_at: string | null;
    original_condition?: {
      entry_trigger_price: string;
      invalidation_price: string;
      mean_volume: string;
    } | null;
    first_valid_trigger?: { time: string; close: string } | null;
    invalidation_at?: string | null;
    ambiguous_at?: string | null;
    trade_date?: string;
    trace?: {
      time: string;
      close: string;
      volume: string;
      minimum_volume: string;
      reason: string;
    }[];
  };
  choices_status?: "UNAVAILABLE";
  choices_detail?: string;
  status: string;
  monitor_running: boolean;
  symbol?: string;
  session_id?: string;
  detail?: string;
  choices?: { symbol: string; company_name: string }[];
  plan_binding?: { symbol: string; binding_sha256: string };
  condition_observation?: QuotePlanObservation | null;
  condition_transitions?: QuotePlanTransition[];
  completed_plan_observation?: {
    status: string;
    checked_at: string;
    periods: Record<
      string,
      { status: string; reason: string; document_sha256?: string | null }
    >;
  } | null;
  samples: {
    sample_id: string;
    symbol: string;
    checked_at: string;
    status: string;
    reason: string;
    source_refs: { source_url: string; sha256: string }[];
    observation?: { price?: string } | null;
    bar_collection_status?: "CAPTURED" | "UNAVAILABLE";
  }[];
  eligibility: false;
  m5_admitted: false;
};

export type ConditionAlertsResponse = {
  action: "no_order";
  status: string;
  test_only: boolean;
  monitor_running: boolean;
  detail?: string;
  public_observation?: PublicObservationResponse;
  snapshot_sha256?: string;
  condition?: {
    symbol: string;
    strategy: string;
    operator: "GT" | "LT";
    threshold: string;
    input_kind: "QUOTE" | "COMPLETED_BAR";
    period: string;
  } | null;
  alerts: {
    alert_id: string;
    event_id: string | null;
    status: string;
    available_operations: string[];
    expiry_at?: string | null;
  }[];
  history: {
    event_id: string;
    symbol: string;
    event_type: string;
    detected_at: string;
    reason: string;
    source_event_id: string;
    effective_at?: string | null;
    evidence_refs?: { source_url?: string; sha256?: string }[];
    price?: string | null;
    threshold?: string;
    plan_sha256?: string;
    completed_bar?: boolean;
    input_kind?: "QUOTE" | "COMPLETED_BAR";
    period?: string;
    bar_end?: string | null;
    completed_periods?: Record<
      string,
      {
        status: string;
        reason: string;
        bar_end: string | null;
        completed: boolean;
        price?: string | null;
      }
    > | null;
  }[];
};

export type OperatingResearchModelStatus = {
  status:
    "READY" | "MODEL_AUTHORIZATION_REQUIRED" | "MODEL_CREDENTIAL_REQUIRED";
  model_id: string | null;
  currency?: "CNY";
  max_run_cost?: string | number | null;
  daily_cost_limit?: string | number | null;
};
export type OperatingResearchCompleteness = {
  structured_driver_range_count?: number;
  derived_scenario_metric_count?: number;
  numeric_basis?: "GROWTH_AND_PROFIT_ARE_CODE_DERIVED_NOT_MODEL_ENTERED";
  scenario_count: number;
  numeric_assumption_count: number;
  unknown_assumption_count: number;
  status: "REVIEW_REQUIRED" | "INSUFFICIENT_FOR_NUMERIC_SCENARIOS";
  economic_validation: "NOT_APPROVED";
};
export type OperatingResearchIndependentReview = {
  status: "REVIEW_REQUIRED_NOT_APPROVAL";
  findings: {
    priority: string;
    role: "FUNDAMENTAL" | "COUNTER_EVIDENCE" | "EVENT";
    claim_index: number;
    reason: string;
  }[];
};
export type OperatingDriverNumber = string | number | null;
export type OperatingDriverScenario = "bear" | "base" | "bull";
export type OperatingDriverRange = {
  lower: OperatingDriverNumber;
  upper: OperatingDriverNumber;
};
export type OperatingDriverAssumption = OperatingDriverRange & {
  rationale: string;
  evidence_ids: string[];
};
export type OperatingDriverKey =
  | "volume_change"
  | "realization_mix_change"
  | "unit_cost_change"
  | "fixed_cogs_share"
  | "opex_change"
  | "surcharge_ratio"
  | "other_pretax_cny";
export type OperatingDriverBaseline = {
  period_basis: string;
  scope: string;
  currency: string;
  fields: Record<
    | "revenue"
    | "cost"
    | "surcharges"
    | "selling"
    | "admin"
    | "research"
    | "pre_tax_profit",
    { value: OperatingDriverNumber; evidence_id: string }
  >;
  opex_cny: OperatingDriverNumber;
  other_pretax_cny: OperatingDriverNumber;
  pretax_margin: OperatingDriverNumber;
  surcharge_ratio: OperatingDriverNumber;
  evidence_ids: string[];
};
export type OperatingDriverExtremum = {
  revenue_cny: OperatingDriverNumber;
  cogs_cny: OperatingDriverNumber;
  opex_cny: OperatingDriverNumber;
  surcharges_cny: OperatingDriverNumber;
  other_pretax_cny: OperatingDriverNumber;
  pretax_profit_cny: OperatingDriverNumber;
  drivers: Record<string, OperatingDriverNumber>;
};
export type OperatingDriverBridge = {
  version: string;
  basis: {
    baselines: Record<string, OperatingDriverBaseline>;
    comparisons: {
      field: string;
      current_period: string;
      prior_period: string;
      period_basis: string;
      current_value: OperatingDriverNumber;
      prior_value: OperatingDriverNumber;
      change_ratio: OperatingDriverNumber;
      status: string;
      evidence_ids: string[];
    }[];
    gaps: unknown;
  };
  inputs: Record<
    OperatingDriverScenario,
    {
      baseline_period: string;
      period_start: string;
      period_end: string;
      drivers: Record<OperatingDriverKey, OperatingDriverAssumption>;
      capital_assumptions: unknown;
    }
  >;
  paths: Record<
    OperatingDriverScenario,
    {
      growth_range: OperatingDriverRange;
      margin_range: OperatingDriverRange;
      baseline: unknown;
      comparison_basis: unknown;
      extrema: Record<
        "growth_lower" | "growth_upper" | "margin_lower" | "margin_upper",
        OperatingDriverExtremum
      >;
      limitations: string[];
      period_start: string;
      period_end: string;
      scope: string;
      period_basis: string;
    }
  >;
  thresholds: {
    scenario: OperatingDriverScenario;
    metric: string;
    direction: string;
    threshold: OperatingDriverNumber;
    period_start: string;
    period_end: string;
    baseline_period: string;
    period_basis: string;
    scope: string;
    comparison_basis: unknown;
    meaning: string;
  }[];
};
export type CapitalObservationSource = {
  path: string;
  sha256: string;
  source_url: string;
  available_at: string;
  report_period: string;
  kind: string;
};
export type NativeCapitalObservation = {
  status: string;
  symbol: string;
  report_period: string;
  issuer_name?: string;
  report_kind?: string;
  kind?: string;
  observation_date?: string;
  record_date?: string;
  ex_date?: string;
  agency_payment_date?: string;
  distribution_base_shares?: string;
  excluded_repurchase_shares?: string;
  dividend_per_10_shares_cny?: string;
  payment_scope?: string;
  share_effective_date?: string;
  share_observation_state?: string;
  share_table_qualification?: string;
  historical_cancelled_shares?: string;
  historical_cancellation_date?: string;
  equity_distribution_implementation?: Record<string, unknown>;
  financial_update?: {
    status: string;
    period_start?: string;
    period_end?: string;
    period_basis?: string;
    fields?: Partial<
      Record<
        "revenue_cny" | "parent_profit_cny",
        {
          value: string;
          unit: string;
          scope: string;
          physical_page: number;
          excerpt: string;
        }
      >
    >;
  };
  ordinary_shares?: string;
  shares_before?: string;
  cancelled_shares?: string;
  cancellation_date?: string;
  cancellation_state?: string;
  interim_proposal_state?: string;
  report_approved_date?: string;
  published_date?: string;
  payment_completion_state?: string;
  declared_ordinary_dividend_cny?: string;
  dividend_fiscal_year?: string;
  dividend_observation_basis?: string;
  dividend_policy?: {
    status: string;
    policies: {
      fiscal_year: number;
      minimum_payout_ratio: string;
      minimum_distribution_cny: string;
      currency: string;
      scope: string;
      physical_page?: number;
      excerpt?: string;
    }[];
    limitations?: string[];
  };
  evidence_refs?: { field: string; physical_page: number; excerpt: string }[];
  unknowns?: string[];
};
export type CurrentCapitalObservation = {
  schema_version?: string;
  status: "NOT_STARTED" | "VERIFIED" | "PARTIAL" | "UNASSESSABLE";
  symbol?: string;
  action: "no_order";
  formal_eligibility: false;
  current_capital_continuity?: "NOT_PROVEN";
  h1_share_observation?: {
    status: "NOT_REGISTERED" | "VERIFIED" | "UNASSESSABLE";
    report_period_end: string | null;
    ordinary_shares: number | null;
    shares_before?: number;
    cancelled_shares?: number;
    current_continuity: "UNPROVEN";
    formal_eligibility: false;
    action: "no_order";
    source?: { original_sha256: string; source_url: string };
    error_code?: string;
  };
  q3_h1_capital_bridge?: {
    status: "MONETARY_CAPITAL_VERIFIED_SHARES_UNKNOWN" | "UNASSESSABLE";
    symbol?: string;
    q3_monetary_capital_cny?: string;
    q3_comparison_capital_cny?: string;
    q3_ordinary_shares: "UNKNOWN";
    h1_ordinary_shares: number | "UNKNOWN";
    current_continuity: "UNPROVEN";
    q3_source?: { original_sha256: string; source_url: string };
    error_code?: string;
    action: "no_order";
    formal_eligibility: false;
  };
  quarter_financial_observation?: {
    status: "VERIFIED_OBSERVATION_ONLY" | "UNASSESSABLE";
    supported_scope?: string;
    reason?: string;
    action: "no_order";
    formal_eligibility: false;
    valuation_admitted: false;
    current_comparison_changed?: false;
    ytd_9m_observation?: {
      symbol: string;
      report_period: string;
      period_basis: string;
      currency: string;
      facts: { revenue_ytd_cny: string; attributable_profit_ytd_cny: string };
      source_sha256: string;
      formal_eligibility: false;
      valuation_admitted: false;
      action: "no_order";
    } | null;
  };
  source_bound_observations?: {
    source_index: number;
    status: string;
    source_id?: string;
    source: CapitalObservationSource;
    observation: NativeCapitalObservation;
  }[];
  source_results?: {
    source_index: number;
    status: string;
    error_code?: string;
    source?: Partial<CapitalObservationSource>;
  }[];
  current_financial_coverage?: {
    status: string;
    report_periods: string[];
    latest_report_period: string | null;
    complete_current_coverage?: false;
  };
  error_code?: string;
  reason?: string;
};
export type FiscalDistributionScenario = {
  status?: "CONDITIONAL_FISCAL_POLICY_DIAGNOSTIC";
  fiscal_year: number;
  reported_h1_parent_profit_cny: string;
  assumed_h2_parent_profit_cny: string;
  conditional_fy_parent_profit_cny: string;
  ratio_target_cny: string;
  disclosed_floor_cny: string;
  policy_target_cny: string;
  target_above_current_year_positive_earnings_cny: string;
  dominant_constraint: "ABSOLUTE_FLOOR" | "PAYOUT_RATIO";
  funding_status: "NOT_ASSESSED";
  payment_status: "NOT_ASSESSED";
  policy_compliance: "NOT_ASSESSED";
  limitations?: string[];
};
export type FiscalQ3Comparison = {
  status: "ACTUAL_UPDATE_COMPARED_WITH_FROZEN_CONDITIONAL_PATH";
  fiscal_year: number;
  reported_ytd_parent_profit_cny: string;
  unchanged_conditional_fy_parent_profit_cny: string;
  implied_q4_parent_profit_cny: string;
  implied_q4_start: string;
  implied_q4_end: string;
  implication:
    | "IMPLIED_Q4_LOSS_REQUIRES_EXPLICIT_REVIEW"
    | "IMPLIED_Q4_PROFIT_REQUIRES_EXPLICIT_REVIEW";
  source_anchor: {
    value: string;
    unit: string;
    scope: string;
    physical_page: number;
    excerpt: string;
  };
  model_revalidated: false;
  action: "no_order";
  formal_eligibility: false;
  condition_price: null;
};
export type FiscalDistributionReview = {
  schema_version?: string;
  symbol?: string;
  status: "SOURCE_BOUND_FISCAL_POLICY_REVIEW" | "UNASSESSABLE" | "NOT_STARTED";
  action: "no_order";
  formal_eligibility: false;
  main_range_adopted?: false;
  condition_price?: null;
  personal_quantity?: null;
  scenarios?: Partial<
    Record<OperatingDriverScenario, FiscalDistributionScenario>
  >;
  source_binding?: CapitalObservationSource[];
  financial_basis?: string;
  review_fingerprint?: string;
  fiscal_payment_alignment?: "NOT_ASSESSED";
  financial_update_review?: {
    status:
      "NEWER_REPORT_REQUIRES_MODEL_REVALIDATION" | "REGISTERED_COVERAGE_ONLY";
    model_financial_basis: string;
    latest_registered_report_period: string | null;
    comparisons?: Partial<Record<OperatingDriverScenario, FiscalQ3Comparison>>;
    comparison_source?: CapitalObservationSource;
    comparison_status?: string;
    current_model_validity: "NOT_GRANTED";
  };
  current_observations?: CurrentCapitalObservation;
  limitations?: string[];
  reason?: string;
  error_code?: string;
};
export type ParentFundingSource = {
  sha256: string;
  path?: string;
  url?: string;
  source_url?: string;
  available_at?: string;
  [key: string]: unknown;
};
export type ParentFundingFact = {
  field: string;
  value: string;
  unit: string;
  scope: string;
  period_end: string;
  source_id: string;
  physical_page: number;
  [key: string]: unknown;
};
export type ParentFundingPage = {
  source: ParentFundingSource;
  physical_page: number;
  amount: string;
  excerpt: string;
};
export type ParentFundingReview = {
  cash_input_comparison?: {
    status:
      | "AMOUNT_EQUAL_NOT_MAPPING_VERIFIED"
      | "AMOUNT_DIFFERENT"
      | "NOT_ASSESSABLE";
    source_mapping_verified: false;
    scope: "AMOUNT_COMPARISON_NOT_SOURCE_MAPPING_OR_LEGAL_CAPACITY";
    source_static_remainder_cny?: string;
    model_opening_cash_cny?: string;
    model_financial_basis?: string;
    model_scope?: string | null;
    explanation?: string;
    reason?: string;
    action?: "no_order";
    current_capacity_proven?: false;
  };
  status: "HISTORICAL_PARENT_REVIEW" | "NOT_STARTED" | "UNASSESSABLE";
  symbol?: string;
  action: "no_order";
  formal_eligibility: false;
  current_capacity_proven?: false;
  reason?: string;
  error_code?: string;
  review?: {
    period: string;
    action: "no_order";
    native_sha256: string;
    result: {
      static_after_declared_dividend: string;
      status: string;
      conditional_distribution_ceiling: string | null;
      conditional_shortfall: string | null;
      current_capacity_proven: false;
      approved: false;
      action: "no_order";
    };
    evidence: ParentFundingFact[];
    sources: Record<string, ParentFundingSource>;
    debt_review: {
      parent_current_noncurrent_liabilities: string;
      other_payables_ex_dividend: string;
      other_payables_cash_timing: string;
      principal_interest_split: unknown | null;
      parent_page?: number;
      warning?: string;
      [key: string]: unknown;
    };
    debt_evidence?: ParentFundingPage[];
    historical_capex?: ParentFundingPage;
    retained_profit_evidence?: ParentFundingPage;
    future_necessary_investment?: string;
    legal_adjustments?: string;
    unknowns?: string[];
    historical_cash_uses?: {
      scope: string;
      period: string;
      unit: string;
      treatment: string;
      cash_statement_reconciliation?: string;
    };
    post_h1_bridge?: {
      status: "IMPLEMENTATION_ARRANGEMENT";
      fiscal_attribution: string;
      scheduled_date: string;
      additional_cash_deduction: string;
      current_parent_cash: null;
      amount_evidence?: ParentFundingPage;
      timing_evidence?: ParentFundingPage;
      receipt_sha256?: string;
      reason?: string;
      action?: "no_order";
    };
  } | null;
};
export type MainValuationRevalidationRecord = Record<string, unknown>;
export type LiveOperatingResearchTask = {
  controller_finalization?: { status: string; pending_bindings: unknown[] };
  live_controller?: {
    schema_version: string;
    started_at: string;
    deadline_at: string;
    timeout_seconds: number;
    result: string;
    finished_at?: string;
  };

  main_valuation_revalidation?: MainValuationRevalidationRecord;
  parent_funding_review?: ParentFundingReview;
  current_capital_observation?: CurrentCapitalObservation;
  fiscal_distribution_review?: FiscalDistributionReview;
  operating_driver_bridge?: OperatingDriverBridge;
  cash_consumption?: Record<string, unknown>;
  parent_cash_followup?: Record<string, unknown>;
  research_completeness?: OperatingResearchCompleteness;
  independent_review?: OperatingResearchIndependentReview;
  independent_review_status?: "REVIEW_BINDING_INVALID";
  task_id: string;
  symbol: string;
  status: string;
  scope:
    | "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED"
    | "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH";
  model_id: string;
  new_llm_calls: number;
  usage: Record<string, unknown>;
  currency: "CNY";
  reserved_cost: string | number;
  settled_cost: string | number;
  error_code?: string | null;
  research_draft?: {
    FUNDAMENTAL?: unknown;
    COUNTER_EVIDENCE?: unknown;
    EVENT?: unknown;
  } | null;
  source_binding: unknown;
  context_fingerprint: string;
  research_as_of: string | null;
  main_range_adopted: false;
  approval_changed: false;
  formal_fact_count: 0;
  condition_price: null;
  personal_quantity: null;
};
export type LiveOperatingResearchRole = {
  model_id: string;
  generated_at: string;
  source_bindings: unknown[];
  draft: Record<string, unknown>;
};
export type PublicOperatingResearchSuccess = Pick<
  LiveOperatingResearchTask,
  | "main_valuation_revalidation"
  | "parent_funding_review"
  | "current_capital_observation"
  | "fiscal_distribution_review"
  | "operating_driver_bridge"
  | "cash_consumption"
  | "parent_cash_followup"
  | "independent_review_status"
  | "independent_review"
  | "research_completeness"
  | "task_id"
  | "symbol"
  | "scope"
  | "model_id"
  | "new_llm_calls"
  | "source_binding"
  | "context_fingerprint"
  | "research_as_of"
  | "main_range_adopted"
  | "approval_changed"
  | "formal_fact_count"
  | "condition_price"
  | "personal_quantity"
> & {
  action: "no_order";
  formal_eligibility: false;
  status: "SUCCEEDED";
  scope: "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED";
  research_draft: Record<
    "FUNDAMENTAL" | "COUNTER_EVIDENCE" | "EVENT",
    LiveOperatingResearchRole
  >;
};
export type OperatingResearchRoleKey =
  "FUNDAMENTAL" | "COUNTER_EVIDENCE" | "EVENT";
export type PublicOperatingResearchPartial = Omit<
  PublicOperatingResearchSuccess,
  "status" | "research_draft"
> & {
  status: "PARTIAL";
  execution_status: "FAILED";
  reason: string;
  completed_roles: OperatingResearchRoleKey[];
  pending_roles: OperatingResearchRoleKey[];
  research_draft: Partial<
    Record<OperatingResearchRoleKey, LiveOperatingResearchRole>
  >;
};
export type PublicOperatingResearchResult =
  | PublicOperatingResearchPartial
  | PublicOperatingResearchSuccess
  | {
      action: "no_order";
      formal_eligibility: false;
      symbol: string;
      status: "NOT_STARTED" | "UNASSESSABLE";
      current_capital_observation?: CurrentCapitalObservation;
      main_valuation_revalidation?: MainValuationRevalidationRecord;
      reason?: string;
      task_id?: string;
      latest_task_status?: string;
    };

export type LiveOperatingResearchHistory = {
  symbol?: string;
  items: LiveOperatingResearchTask[];
};
export type HorizonCashPolicyTask = {
  task_id: string;
  symbol: string;
  status: string;
  persisted_status?: string;
  action: "no_order";
  formal_eligibility?: false;
  workflow?:
    | "operating-horizon-task-v4-cash-policy"
    | "operating-horizon-task-v5-parent-wc-balance"
    | "operating-horizon-task-v6-split"
    | "operating-horizon-task-v7-split"
    | "operating-horizon-task-v12-2027-live"
    | "operating-horizon-task-v13-2027-live"
    | "operating-horizon-task-v14-2027-live"
    | "operating-cash-policy-task-v1"
    | "operating-horizon-task-v2"
    | "operating-horizon-task-v3";
  error_code?: string | null;
  annual_status?: string;
  cash_status?: string;
  research_result?: Record<string, unknown> | null;
  cash_policy_completeness?: {
    status:
      | "INCOMPLETE_UNKNOWN_TERMS"
      | "COMPLETE_UNAPPROVED_RESEARCH"
      | "NO_VALIDATED_RESULT";
    missing_terms: { year: string; scenario: string; term: string }[];
    source_scope: "SEALED_RESPONSE_READ_ONLY";
    task_accepted: boolean;
    formal_eligibility: false;
    action: "no_order";
  };
  sealed_response_diagnostic?: {
    status: "REJECTED_RESPONSE_DIAGNOSTIC_ONLY";
    response_binding: { path: string; sha256: string };
    missing_terms: {
      year: string;
      scenario: string;
      term: string;
      reason: "ABSENT" | "NOT_QUANTIFIED";
    }[];
    action: "no_order";
    formal_eligibility: false;
    e2_usable: false;
  };
  economic_validation?: {
    status: "REJECTED" | "NO_DETECTED_DENOMINATOR_CONFLICT";
    reason: string | null;
    actual_plan_denominator: string;
    conflicts: {
      year: string;
      scenario: string;
      term: string;
      source_id: string;
    }[];
    action: "no_order";
  };
  source_binding?: unknown;
  context_fingerprint?: string;
  usage?: Record<string, unknown>;
};

export type HorizonCashPolicyE2Input = {
  status: string;
  annual_operating_status?: string;
  annual_operating_error?: string | null;
  action: "no_order";
  formal_eligibility: false;
  condition_price: null;
  symbol?: string;
  task_id?: string;
  blockers?: string[];
  reason?: string;
  scope?: string;
};

export type ValueWorkbenchSection = {
  id:
    | "selection"
    | "profile"
    | "research"
    | "assumptions"
    | "cash"
    | "valuation"
    | "price"
    | "decision"
    | "continuity"
    | "evidence";
  title: string;
  status: string;
  summary: string;
  data: {
    native_results?: Record<string, Record<string, unknown>>;
    source_bindings?: unknown[];
    knowledge_types?: unknown[];
  } | null;
  blockers: unknown[];
};
export type ValueWorkbenchCompanies = {
  action: "no_order";
  formal_eligibility: false;
  status: string;
  scope: "REGISTERED_RESEARCH_ENTRIES_NOT_CURRENT_SHORTLIST";
  items: {
    symbol: string;
    name: string | null;
    status: "REGISTERED_NOT_YET_REVALIDATED";
    current_candidate: null;
    research_verified: false;
    action: "no_order";
    formal_eligibility: false;
  }[];
  sources: unknown[];
};
export type ValueWorkbenchResponse = {
  schema_version: "value-transparent-workbench-v1";
  symbol: string;
  action: "no_order";
  formal_eligibility: false;
  quantity: null;
  sections: ValueWorkbenchSection[];
  evidence_downloads?: {
    id: string;
    binding: { path: string; sha256: string };
  }[];
};
export type ValueWorkbenchTask = {
  result?: {
    operation: string;
    outcome: string;
    action: "no_order";
    formal_eligibility: false;
    approval_changed: false;
    current_published: false;
    new_llm_calls: 0;
    result: Record<string, unknown>;
    selection_content?: Record<string, unknown>;
  };
  module_id?: string;
  module_version?: string;
  run_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  duration_basis?: string;
  current_step?: string | null;
  retry_allowed?: boolean;
  input_sha256?: string;
  input_binding?: { path: string; sha256: string };
  current_validation?: string;
  current_validation_reason?: string | null;
  currently_consumable?: boolean;
  warnings?: string[];
  task_id: string;
  symbol: string;
  status: string;
  operation: string;
  action: "no_order";
  formal_eligibility: false;
  new_llm_calls: 0;
  native_metadata: {
    schema_version: string;
    new_llm_calls: 0;
    approval_changed: false;
    execution: string;
  };
  completed_steps?: number;
  total_steps?: number;
  resume_required?: boolean;
  error_code?: string | null;
  steps?: { name: string; status: string }[];
};
export type PreparedWorkbenchOperation = {
  module_id: string;
  operation: string;
  enabled: boolean;
  reason?: string | null;
  prepared_payload: Record<string, unknown> | null;
  user_fields: unknown[];
  network_authorization_required: boolean;
};
export type PreparedWorkbenchInputs = {
  action: "no_order";
  formal_eligibility: false;
  symbol: string;
  status: string;
  tasks_started: 0;
  operations: PreparedWorkbenchOperation[];
};
export type ValueWorkbenchTaskCreate = {
  module_id: string;
  operation: string;
  symbol: string;
  request_key: string;
  payload: Record<string, unknown>;
  timeout_seconds?: number;
};
export type ValueWorkbenchTaskHistory = {
  task_id: string;
  action: "no_order";
  formal_eligibility: false;
  history: {
    record_binding: { path: string; sha256: string };
    record: Record<string, unknown>;
  }[];
};
export const api = {
  sseResearchQueue: (signal?: AbortSignal) =>
    get<TrackingPoolView>("value-screening/sse-main/research-queue", signal),
  sseMainScreening: (
    params: { offset: number; limit: number; query: string; status: string },
    signal?: AbortSignal,
  ) =>
    get<ScreenPage>(
      "value-screening/sse-main?" +
        new URLSearchParams({
          offset: String(params.offset),
          limit: String(params.limit),
          query: params.query,
          status: params.status,
        }).toString(),
      signal,
    ),
  valueWorkbenchCompanies: (signal?: AbortSignal) =>
    get<ValueWorkbenchCompanies>("value-workbench/companies", signal),
  valueWorkbenchTaskInputs: (symbol: string, signal?: AbortSignal) =>
    get<PreparedWorkbenchInputs>(
      "value-workbench/task-inputs?symbol=" + encodeURIComponent(symbol),
      signal,
    ),
  createValueWorkbenchTask: (body: ValueWorkbenchTaskCreate) =>
    post<ValueWorkbenchTask>("value-workbench/tasks", body),
  valueWorkbenchTasks: (symbol: string, signal?: AbortSignal) =>
    getPrivate<{
      symbol: string;
      action: "no_order";
      formal_eligibility: false;
      items: ValueWorkbenchTask[];
    }>("value-workbench/tasks?symbol=" + encodeURIComponent(symbol), signal),
  valueWorkbenchTask: (id: string, signal?: AbortSignal) =>
    getPrivate<ValueWorkbenchTask>(
      "value-workbench/tasks/" + encodeURIComponent(id),
      signal,
    ),
  valueWorkbenchTaskHistory: (id: string, signal?: AbortSignal) =>
    getPrivate<ValueWorkbenchTaskHistory>(
      "value-workbench/tasks/" + encodeURIComponent(id) + "/history",
      signal,
    ),
  controlValueWorkbenchTask: (
    id: string,
    operation: "cancel" | "retry" | "resume",
  ) =>
    post<ValueWorkbenchTask>(
      "value-workbench/tasks/" + encodeURIComponent(id) + "/" + operation,
      {},
    ),

  valueWorkbench: (symbol: string, signal?: AbortSignal) =>
    get<ValueWorkbenchResponse>(
      "value-workbench?symbol=" + encodeURIComponent(symbol),
      signal,
    ),

  operatingResearchCompany: (symbol: string, signal?: AbortSignal) =>
    get<PublicOperatingResearchResult>(
      "operating-research/companies/" + encodeURIComponent(symbol),
      signal,
    ),

  operatingResearchModelStatus: (signal?: AbortSignal) =>
    get<OperatingResearchModelStatus>(
      "operating-research/model-status",
      signal,
    ),
  createOperatingResearchTask: (body: {
    symbol: string;
    request_key: string;
  }) => post<LiveOperatingResearchTask>("operating-research/tasks", body),
  operatingResearchTasks: (symbol: string, signal?: AbortSignal) =>
    getPrivate<LiveOperatingResearchHistory>(
      "operating-research/tasks?symbol=" + encodeURIComponent(symbol),
      signal,
    ),
  operatingResearchTask: (id: string, signal?: AbortSignal) =>
    getPrivate<LiveOperatingResearchTask>(
      "operating-research/tasks/" + encodeURIComponent(id),
      signal,
    ),
  cancelOperatingResearchTask: (id: string) =>
    post<LiveOperatingResearchTask>(
      "operating-research/tasks/" + encodeURIComponent(id) + "/cancel",
      {},
    ),
  finalizeOperatingResearchTask: (id: string) =>
    post<LiveOperatingResearchTask>(
      "operating-research/tasks/" + encodeURIComponent(id) + "/finalize",
      {},
    ),
  resumeOperatingResearchTask: (id: string) =>
    post<LiveOperatingResearchTask>(
      "operating-research/tasks/" + encodeURIComponent(id) + "/resume",
      {},
    ),
  createHorizonCashPolicyTask: (body: {
    symbol: string;
    request_key: string;
    years: number[];
    task_contract?:
      | "operating-horizon-task-v5-parent-wc-balance"
      | "operating-horizon-task-v6-split"
      | "operating-horizon-task-v7-split"
      | "operating-horizon-task-v11-2027-live"
      | "operating-horizon-task-v12-2027-live"
      | "operating-horizon-task-v13-2027-live"
      | "operating-horizon-task-v14-2027-live";
    source_loader_version?: "operating-q3-issuer-wc-loader-v9-600519";
  }) =>
    post<HorizonCashPolicyTask>(
      "operating-research/horizon-cash-policy-tasks",
      body,
    ),
  importV12HorizonCashPolicyTask: (body: {
    source_task_id: string;
    request_key: string;
    task_contract?:
      | "operating-horizon-task-v13-2027-live"
      | "operating-horizon-task-v14-2027-live";
  }) =>
    post<HorizonCashPolicyTask>(
      "operating-research/horizon-cash-policy-tasks/import-v12",
      body,
    ),
  horizonCashPolicyTask: (id: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyTask>(
      "operating-research/horizon-cash-policy-tasks/" + encodeURIComponent(id),
      signal,
    ),
  recentHorizonCashPolicyTasks: (signal?: AbortSignal) =>
    getPrivate<{
      action: "no_order";
      scope: "HISTORICAL_D2_TASKS_NOT_CURRENT_CANDIDATES";
      items: HorizonCashPolicyTask[];
    }>("operating-research/horizon-cash-policy-tasks/recent", signal),
  horizonCashPolicyHistory: (
    symbol: string,
    signal?: AbortSignal,
    taskContract?:
      | "operating-horizon-task-v5-parent-wc-balance"
      | "operating-horizon-task-v6-split"
      | "operating-horizon-task-v7-split"
      | "operating-horizon-task-v10-2027-live"
      | "operating-horizon-task-v11-2027-live"
      | "operating-horizon-task-v12-2027-live"
      | "operating-horizon-task-v13-2027-live"
      | "operating-horizon-task-v14-2027-live",
  ) =>
    getPrivate<{
      action: "no_order";
      symbol: string;
      items: HorizonCashPolicyTask[];
    }>(
      "operating-research/horizon-cash-policy-tasks?symbol=" +
        encodeURIComponent(symbol) +
        (taskContract
          ? "&task_contract=" + encodeURIComponent(taskContract)
          : ""),
      signal,
    ),
  horizonCashPolicyE2Input: (id: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyE2Input>(
      "operating-research/horizon-cash-policy-tasks/" +
        encodeURIComponent(id) +
        "/e2-input",
      signal,
    ),
  controlHorizonCashPolicyTask: (id: string, operation: "cancel" | "resume") =>
    post<HorizonCashPolicyTask>(
      "operating-research/horizon-cash-policy-tasks/" +
        encodeURIComponent(id) +
        "/" +
        operation,
      {},
    ),
  compactCashPolicyHistory: (symbol: string, signal?: AbortSignal) =>
    getPrivate<{
      action: "no_order";
      symbol: string;
      items: HorizonCashPolicyTask[];
    }>(
      "operating-research/cash-policy-tasks?symbol=" +
        encodeURIComponent(symbol),
      signal,
    ),
  createCompactCashPolicyTask: (body: {
    symbol: string;
    request_key: string;
    years: number[];
  }) =>
    post<HorizonCashPolicyTask>("operating-research/cash-policy-tasks", body),
  compactCashPolicyTask: (id: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyTask>(
      "operating-research/cash-policy-tasks/" + encodeURIComponent(id),
      signal,
    ),
  compactCashPolicyE2Input: (id: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyE2Input>(
      "operating-research/cash-policy-tasks/" +
        encodeURIComponent(id) +
        "/e2-input",
      signal,
    ),
  annualOperatingHistory: (symbol: string, signal?: AbortSignal) =>
    getPrivate<{
      action: "no_order";
      symbol: string;
      items: HorizonCashPolicyTask[];
    }>(
      "operating-research/horizon-tasks?symbol=" + encodeURIComponent(symbol),
      signal,
    ),
  splitD2E2Input: (cashId: string, annualId: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyE2Input>(
      "operating-research/cash-policy-tasks/" +
        encodeURIComponent(cashId) +
        "/e2-input?annual_task_id=" +
        encodeURIComponent(annualId),
      signal,
    ),
  controlCompactCashPolicyTask: (id: string, operation: "cancel" | "resume") =>
    post<HorizonCashPolicyTask>(
      "operating-research/cash-policy-tasks/" +
        encodeURIComponent(id) +
        "/" +
        operation,
      {},
    ),

  firstResearchInput: (symbol: string, signal?: AbortSignal) =>
    get<FirstResearchInputResponse>(
      "first-research-inputs/" + encodeURIComponent(symbol),
      signal,
    ),
  createAnchoredAnnualTask: (body: {
    symbol: string;
    request_key: string;
    years: number[];
  }) =>
    post<HorizonCashPolicyTask>("operating-research/horizon-v3-tasks", body),
  anchoredAnnualTask: (id: string, signal?: AbortSignal) =>
    getPrivate<HorizonCashPolicyTask>(
      "operating-research/horizon-v3-tasks/" + encodeURIComponent(id),
      signal,
    ),
  researchAssumptionDraft: (symbol: string, signal?: AbortSignal) =>
    get<OperatingAssumptionDraftResponse>(
      "research-assumption-drafts/" + encodeURIComponent(symbol),
      signal,
    ),
  companyProfile: (symbol: string, signal?: AbortSignal) =>
    get<CompanyProfile>(
      "research-profiles/" + encodeURIComponent(symbol),
      signal,
    ),
  strategySelection: (signal?: AbortSignal) =>
    get<DualStrategySelection>("strategy-selection?limit=10", signal),
  strategySelectionPage: (
    strategy: "value" | "hotspot",
    offset: number,
    query: string,
    signal?: AbortSignal,
  ) =>
    get<DualStrategySelection>(
      `strategy-selection?limit=10&${strategy}_offset=${offset}&q_${strategy}=${encodeURIComponent(query)}`,
      signal,
    ),
  privateRetrospective: (reviewDate: string, signal?: AbortSignal) =>
    getPrivate<PrivateRetrospective>(
      `private/portfolio/retrospective?review_date=${encodeURIComponent(reviewDate)}`,
      signal,
    ),
  createResearchTask: (body: ResearchTaskCreateRequest) =>
    post<ResearchTaskResponse>("research-tasks", body),
  researchTasksForSymbol: (symbol: string, signal?: AbortSignal) =>
    getPrivate<ResearchTaskHistoryResponse>(
      "research-tasks?symbol=" + encodeURIComponent(symbol),
      signal,
    ),
  researchTask: (taskId: string, signal?: AbortSignal) =>
    getPrivate<ResearchTaskResponse>(
      "research-tasks/" + encodeURIComponent(taskId),
      signal,
    ),
  cancelResearchTask: (taskId: string) =>
    post<ResearchTaskResponse>(
      "research-tasks/" + encodeURIComponent(taskId) + "/cancel",
      {},
    ),
  resumeResearchTask: (taskId: string) =>
    post<ResearchTaskResponse>(
      "research-tasks/" + encodeURIComponent(taskId) + "/resume",
      {},
    ),
  agentResearch: (symbol: string, signal?: AbortSignal, workflow?: string) =>
    getPrivate<AgentResearchResponse>(
      `agent-research/${encodeURIComponent(symbol)}${workflow ? `?workflow=${encodeURIComponent(workflow)}` : ""}`,
      signal,
    ),
  agentResearchStatus: (signal?: AbortSignal) =>
    getPrivate<AgentResearchStatusResponse>("agent-research-status", signal),
  controlPublicObservation: (
    operation: "start" | "stop",
    symbol?: string,
    sessionId?: string,
  ) =>
    post<PublicObservationResponse>(
      `condition-alerts/public-observation/${operation}`,
      operation === "start"
        ? { acknowledged: true, symbol }
        : { acknowledged: true, expected_session_id: sessionId },
    ),
  conditionAlerts: (testOnly: boolean, signal?: AbortSignal) =>
    getPrivate<ConditionAlertsResponse>(
      `condition-alerts?test_only=${testOnly}`,
      signal,
    ),
  transitionObservationAlert: (
    alertId: string,
    operation: "acknowledge" | "cancel" | "expire",
    expectedSnapshot: string,
  ) =>
    post<ConditionAlertsResponse>(
      `condition-alerts/observation/${encodeURIComponent(alertId)}/${operation}`,
      { acknowledged: true, expected_snapshot_sha256: expectedSnapshot },
    ),
  acknowledgeConditionAlert: (alertId: string, expectedSnapshot: string) =>
    post<ConditionAlertsResponse>(
      `condition-alerts/test-only/${encodeURIComponent(alertId)}/acknowledge`,
      {
        test_only: true,
        acknowledged: true,
        expected_snapshot_sha256: expectedSnapshot,
      },
    ),
  transitionConditionAlert: (
    alertId: string,
    operation: "cancel" | "expire",
    expectedSnapshot: string,
  ) =>
    post<ConditionAlertsResponse>(
      `condition-alerts/test-only/${encodeURIComponent(alertId)}/${operation}`,
      {
        test_only: true,
        acknowledged: true,
        expected_snapshot_sha256: expectedSnapshot,
      },
    ),
  updateStatus: (signal?: AbortSignal) =>
    get<{
      action: "no_order";
      status: string;
      last_run: {
        research_priority?: {
          status: string;
          as_of?: string;
          deep_research_count?: number;
          enrichment_count?: number;
          selected_enrichment_count?: number;
          execution?: {
            status: string;
            attempted_count?: number;
            reevaluated_count?: number;
            data_gap_count?: number;
            verified_adopted_fact_count?: number;
            research_inputs_updated_count?: number;
            items?: {
              symbol: string;
              company_name: string;
              extracted_candidates?: number;
              matched_candidates?: number;
              adoption?: {
                status: "VERIFIED_FACT_ADOPTION";
                adopted_fact_count: number;
                research_inputs_updated: boolean;
                quality_coverage_before: string;
                quality_coverage_after: string;
              } | null;
            }[];
          };
        };
        screening?: CurrentScreening;
        status: string;
        finished_at: string | null;
        published: boolean;
        publication_id: string | null;
        retained_publication_id: string | null;
      } | null;
    }>("daily-update-status", signal),
  daily: (signal?: AbortSignal) =>
    get<DailyResponse>("daily-decisions", signal),
  independentHotspot: (signal?: AbortSignal) =>
    get<{
      action: "no_order";
      status: string;
      publication?: { publication_id: string };
      items: Array<{ symbol: string; price_action_plan: CurrentPricePlan }>;
    }>("independent-hotspot-conditions", signal),
  packet: (signal?: AbortSignal) =>
    get<DailyPublicPacket>("daily-public-packet", signal),
  snapshot: (signal?: AbortSignal) =>
    get<DailyPublicSnapshot>("daily-public-snapshot", signal),
  runtimeIdentity: (signal?: AbortSignal) =>
    get<RuntimeIdentity>("runtime-identity", signal),
  publicEvidence: (signal?: AbortSignal) =>
    get<PublicEvidenceStatus>("public-evidence", signal),
  researchFunnel: (signal?: AbortSignal) =>
    get<ResearchFunnelStatus>("research-funnel-status", signal),
  detail: (id: string, signal?: AbortSignal, strategy?: "value" | "hotspot") =>
    get<DetailResponse>(
      `decisions/${encodeURIComponent(id)}${strategy ? `?strategy=${strategy}` : id.startsWith("hotspot-") ? "?independent_hotspot=true" : ""}`,
      signal,
    ),
  portfolio: (signal?: AbortSignal) =>
    getPrivate<PortfolioResponse>("portfolio", signal),
  accountObservations: (signal?: AbortSignal) =>
    getPrivate<PrivateAccountObservations>(
      "private/portfolio/account-observations",
      signal,
    ),
  entryThesis: (signal?: AbortSignal) =>
    getPrivate<EntryThesisView>("private/portfolio/entry-thesis", signal),
  confirmEntryThesis: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/entry-thesis/confirm", body),
  revokeEntryThesis: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/entry-thesis/revoke", body),
  risk: (signal?: AbortSignal) =>
    getPrivate<RiskResponse>("private/portfolio/risk", signal),
  committedRisk: (signal?: AbortSignal) =>
    getPrivate<CommittedRiskView>("private/portfolio/committed-risk", signal),
  confirmCommittedRisk: (body: Record<string, unknown>) =>
    post<CommittedRiskView>("private/portfolio/committed-risk/confirm", body),
  heldContinuity: (signal?: AbortSignal) =>
    getPrivate<HeldContinuityResponse>(
      "private/portfolio/held-continuity",
      signal,
    ),
  reviewHeldSell: (body: HeldSellReviewRequest) =>
    post<{
      schema_version: "private-held-sell-review-v1";
      action: "no_order";
      revision: number;
      ledger_written: false;
      broker_execution_permission: false;
      request: HeldSellReviewRequest;
      actionable_decision: import("../components/ActionableDecisionResult").ConditionalAccountDecision;
    }>("private/portfolio/held-continuity/sell-review", { ...body }),
  riskPreview: (body: HotspotSizingRequest) =>
    post<HotspotSizingResponse>("private/portfolio/risk-preview", body),
  refreshHeldContinuity: (body: {
    expected_revision: number;
    symbols: string[];
  }) =>
    post<{ status: string; failures: { symbol: string; gap_code?: string }[] }>(
      "private/portfolio/held-continuity/refresh",
      body,
    ),
  riskContext: (symbol: string, signal?: AbortSignal) =>
    getPrivate<PrivateRiskContext>(
      `private/portfolio/risk-context/${encodeURIComponent(symbol)}`,
      signal,
    ),
  confirmCosts: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/costs/confirm", body),
  confirmReconciliation: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/reconciliation/confirm", body),
  previewValuePolicy: (symbol: string, body: PolicySelection) =>
    post<PolicyPreview>(
      `value-policy-review/${encodeURIComponent(symbol)}/preview`,
      body,
    ),
  valuePolicyStatus: (symbol: string) =>
    getPrivate<PolicyStatus>(
      `value-policy-review/${encodeURIComponent(symbol)}/status`,
    ),
  valuePolicyHandoff: (
    symbol: string,
    signal?: AbortSignal,
    boundDraft = false,
  ) =>
    getPrivate<PolicyHandoff>(
      `value-policy-review/${encodeURIComponent(symbol)}/handoff${boundDraft ? "?bound_draft=true" : ""}`,
      signal,
    ),
  confirmValuePolicy: (
    symbol: string,
    body: { preview_id: string; acknowledged: true; note: string },
  ) =>
    post<PolicyRegistration>(
      `value-policy-review/${encodeURIComponent(symbol)}/confirm`,
      body,
    ),
  policy: (signal?: AbortSignal) =>
    getPrivate<PolicyResponse>("private/portfolio/policy", signal),
  preparePolicy: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/policy/prepare", body),
  confirmPolicy: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/policy/confirm", body),
  history: (signal?: AbortSignal) =>
    get<HistoryResponse>("decision-history", signal),
  historicalCases: (signal?: AbortSignal) =>
    get<HistoricalCaseListing>("historical-price-cases", signal),
  currentPriceCase: (symbol: string, signal?: AbortSignal) =>
    get<CurrentPriceCase>(
      `current-price-case/${encodeURIComponent(symbol)}`,
      signal,
    ),
  historicalCase: (symbol: string, day: string, signal?: AbortSignal) =>
    get<HistoricalPriceCase>(
      `historical-price-case/${encodeURIComponent(symbol)}/${encodeURIComponent(day)}`,
      signal,
    ),
  initializePortfolio: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/initialize", body),
  prepareFill: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/fills/prepare", body),
  confirmFill: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/fills/confirm", body),
  cancelFill: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/fills/cancel", body),
  reconcile: (body: Record<string, unknown>) =>
    post<WriteResponse>("private/portfolio/reconcile", body),
  signOut: async () => {
    const result = await post<WriteResponse>("private/session/logout", {});
    forgetSession();
    return result;
  },
};
