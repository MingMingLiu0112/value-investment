import type {
  DailyResponse,
  DetailResponse,
  HistoryResponse,
  PortfolioResponse,
  RiskResponse,
  WriteResponse,
} from "../types/api";

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
let sessionToken: string | null = null;
let handshake: Promise<string> | null = null;

function forgetSession(): void {
  sessionToken = null;
  handshake = null;
}

async function openSession(): Promise<string> {
  const response = await fetch("/api/v1/private/session", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  let body: Record<string, unknown> | null = null;
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = null;
  }
  if (
    !response.ok ||
    !body ||
    typeof body.token !== "string" ||
    body.token.length === 0
  ) {
    throw new ApiError(
      response.status,
      String(body?.status ?? "LOCAL_AUTHORIZATION_REQUIRED"),
      body?.detail ?? null,
    );
  }
  return body.token;
}

async function operatorToken(): Promise<string> {
  if (sessionToken) return sessionToken;
  if (!handshake) {
    handshake = openSession()
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
  daily: (signal?: AbortSignal) =>
    get<DailyResponse>("daily-decisions", signal),
  detail: (id: string, signal?: AbortSignal) =>
    get<DetailResponse>(`decisions/${encodeURIComponent(id)}`, signal),
  portfolio: (signal?: AbortSignal) =>
    getPrivate<PortfolioResponse>("portfolio", signal),
  risk: (signal?: AbortSignal) =>
    getPrivate<RiskResponse>("private/portfolio/risk", signal),
  history: (signal?: AbortSignal) =>
    get<HistoryResponse>("decision-history", signal),
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
