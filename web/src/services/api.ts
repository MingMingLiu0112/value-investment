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
      record.detail ?? null,
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
  formal_eligibility: false;
  main_range_adopted: false;
  main_valuation_range: null;
  current_price: null;
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
  scenario_count: number;
  numeric_assumption_count: number;
  unknown_assumption_count: number;
  status: "REVIEW_REQUIRED" | "INSUFFICIENT_FOR_NUMERIC_SCENARIOS";
  economic_validation: "NOT_APPROVED";
};
export type LiveOperatingResearchTask = {
  research_completeness?: OperatingResearchCompleteness;
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
export type PublicOperatingResearchResult =
  | PublicOperatingResearchSuccess
  | {
      action: "no_order";
      formal_eligibility: false;
      symbol: string;
      status: "NOT_STARTED" | "UNASSESSABLE";
      reason?: string;
      task_id?: string;
      latest_task_status?: string;
    };

export type LiveOperatingResearchHistory = {
  symbol?: string;
  items: LiveOperatingResearchTask[];
};

export const api = {
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
  resumeOperatingResearchTask: (id: string) =>
    post<LiveOperatingResearchTask>(
      "operating-research/tasks/" + encodeURIComponent(id) + "/resume",
      {},
    ),

  firstResearchInput: (symbol: string, signal?: AbortSignal) =>
    get<FirstResearchInputResponse>(
      "first-research-inputs/" + encodeURIComponent(symbol),
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
