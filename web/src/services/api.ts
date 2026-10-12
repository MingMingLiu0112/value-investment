import type {
  DailyResponse,
  DetailResponse,
  HistoryResponse,
  PortfolioResponse,
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

async function post<T>(
  path: string,
  body: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await read(response)) as T;
}

export const api = {
  daily: (signal?: AbortSignal) =>
    get<DailyResponse>("daily-decisions", signal),
  detail: (id: string, signal?: AbortSignal) =>
    get<DetailResponse>(`decisions/${encodeURIComponent(id)}`, signal),
  portfolio: (signal?: AbortSignal) =>
    get<PortfolioResponse>("portfolio", signal),
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
};
