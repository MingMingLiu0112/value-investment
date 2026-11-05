import { afterEach, beforeEach, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", {
    location: { hash: "", pathname: "/daily", search: "" },
    sessionStorage: {
      getItem: () => "TEST_ONLY_SESSION",
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
  });
});
afterEach(() => vi.unstubAllGlobals());

it("sends exact authenticated task create/read/cancel/resume requests only when invoked", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          task_id: "TEST_ONLY",
          status: "QUEUED",
          action: "no_order",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  await api.createOperatingResearchTask({
    symbol: "600519",
    request_key: "rt_TEST_ONLY_123",
  });
  await api.operatingResearchTask("TEST_ONLY/id");
  await api.cancelOperatingResearchTask("TEST_ONLY/id");
  await api.resumeOperatingResearchTask("TEST_ONLY/id");
  expect(fetcher.mock.calls.map((args: any[]) => String(args[0]))).toEqual([
    "/api/v1/operating-research/tasks",
    "/api/v1/operating-research/tasks/TEST_ONLY%2Fid",
    "/api/v1/operating-research/tasks/TEST_ONLY%2Fid/cancel",
    "/api/v1/operating-research/tasks/TEST_ONLY%2Fid/resume",
  ]);
  const calls = fetcher.mock.calls as unknown as [string, RequestInit][];
  expect(calls.map(([, init]) => init.method ?? "GET")).toEqual([
    "POST",
    "GET",
    "POST",
    "POST",
  ]);
  expect(JSON.parse(calls[0][1].body as string)).toEqual({
    symbol: "600519",
    request_key: "rt_TEST_ONLY_123",
  });
  expect(calls[1][1].body).toBeUndefined();
  expect(JSON.parse(calls[2][1].body as string)).toEqual({});
  expect(JSON.parse(calls[3][1].body as string)).toEqual({});
  for (const [, init] of calls) {
    expect(new Headers(init.headers).get("X-Local-Session")).toBe(
      "TEST_ONLY_SESSION",
    );
    expect(init.credentials).toBe("same-origin");
  }
});

it("lists one company's bounded task history using an explicit authenticated GET", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          action: "no_order",
          symbol: "600519",
          items: [],
          scope: "BOUNDED_TASK_HISTORY",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  const result = await api.operatingResearchTasks("600519");
  expect(result.items).toEqual([]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, init] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(url).toBe("/api/v1/operating-research/tasks?symbol=600519");
  expect(init.method ?? "GET").toBe("GET");
  expect(init.body).toBeUndefined();
  expect(new Headers(init.headers).get("X-Local-Session")).toBe(
    "TEST_ONLY_SESSION",
  );
});

it("reads public model status without local authorization or starting tasks", async () => {
  vi.stubGlobal("window", {
    location: { hash: "" },
    sessionStorage: {
      getItem: () => {
        throw new Error("No auth on public status");
      },
    },
  });
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          action: "no_order",
          status: "MODEL_AUTHORIZATION_REQUIRED",
          model_id: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  const result = await api.operatingResearchModelStatus();
  expect(result.status).toBe("MODEL_AUTHORIZATION_REQUIRED");
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, init] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(url).toBe("/api/v1/operating-research/model-status");
  expect(init.method ?? "GET").toBe("GET");
  expect(new Headers(init.headers).has("X-Local-Session")).toBe(false);
  expect(init.body).toBeUndefined();
});

it("reads company latest result through public GET without local session, private history, network provider or task writes", async () => {
  vi.stubGlobal("window", {
    location: { hash: "" },
    sessionStorage: {
      getItem: () => {
        throw new Error("Public company result must not read auth");
      },
    },
  });
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          action: "no_order",
          formal_eligibility: false,
          symbol: "600519",
          status: "NOT_STARTED",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  const controller = new AbortController();
  await api.operatingResearchCompany("600519", controller.signal);
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, init] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(url).toBe("/api/v1/operating-research/companies/600519");
  expect(init.method ?? "GET").toBe("GET");
  expect(init.body).toBeUndefined();
  expect(init.signal).toBe(controller.signal);
  expect(new Headers(init.headers).has("X-Local-Session")).toBe(false);
});
