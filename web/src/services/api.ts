import type {
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
  PortfolioResponse,
  PolicyResponse,
  RiskResponse,
  HeldContinuityResponse,
  WriteResponse,
} from "../types/api";
import type {
  HotspotSizingRequest,
  HotspotSizingResponse,
} from "../components/HotspotSizingPanel";
import type { PrivateRiskContext } from "../components/PrivateRiskContext";
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
  if (sessionToken) return sessionToken;
  const stored = readStoredToken();
  if (stored) {
    sessionToken = stored;
    return stored;
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
  const send = async (): Promise<Response> =>
    fetch(`/api/v1/${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        [SESSION_HEADER]: await operatorToken(),
      },
      body: JSON.stringify(body),
    });
  let response = await send();
  if (response.status === 401) {
    // The session token expired or the service restarted; a rejected request
    // never touched the ledger, so one re-handshake and one retry is safe.
    forgetSession();
    response = await send();
  }
  return (await read(response)) as T;
}

async function getPrivate<T>(path: string, signal?: AbortSignal): Promise<T> {
  const send = async (): Promise<Response> =>
    fetch("/api/v1/" + path, {
      signal,
      credentials: "same-origin",
      headers: { [SESSION_HEADER]: await operatorToken() },
    });
  let response = await send();
  if (response.status === 401) {
    // Same re-handshake pattern as POST: the refused read never reached the
    // ledger, so one fresh token and one retry is safe.
    forgetSession();
    response = await send();
  }
  return (await read(response)) as T;
}

export const api = {
  updateStatus: (signal?: AbortSignal) =>
    get<{
      action: "no_order";
      status: string;
      last_run: {
        status: string;
        finished_at: string | null;
        published: boolean;
        publication_id: string | null;
        retained_publication_id: string | null;
      } | null;
    }>("daily-update-status", signal),
  daily: (signal?: AbortSignal) =>
    get<DailyResponse>("daily-decisions", signal),
  packet: (signal?: AbortSignal) =>
    get<DailyPublicPacket>("daily-public-packet", signal),
  snapshot: (signal?: AbortSignal) =>
    get<DailyPublicSnapshot>("daily-public-snapshot", signal),
  runtimeIdentity: (signal?: AbortSignal) =>
    get<RuntimeIdentity>("runtime-identity", signal),
  researchFunnel: (signal?: AbortSignal) =>
    get<ResearchFunnelStatus>("research-funnel-status", signal),
  detail: (id: string, signal?: AbortSignal) =>
    get<DetailResponse>(`decisions/${encodeURIComponent(id)}`, signal),
  portfolio: (signal?: AbortSignal) =>
    getPrivate<PortfolioResponse>("portfolio", signal),
  risk: (signal?: AbortSignal) =>
    getPrivate<RiskResponse>("private/portfolio/risk", signal),
  heldContinuity: (signal?: AbortSignal) =>
    getPrivate<HeldContinuityResponse>(
      "private/portfolio/held-continuity",
      signal,
    ),
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
  valuePolicyHandoff: (symbol: string, signal?: AbortSignal) =>
    getPrivate<PolicyHandoff>(
      `value-policy-review/${encodeURIComponent(symbol)}/handoff`,
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
