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
  await api.createResearchTask({
    symbol: "600519",
    workflow: "legacy",
    request_key: "rt_TEST_ONLY_123",
  });
  await api.researchTask("TEST_ONLY/id");
  await api.cancelResearchTask("TEST_ONLY/id");
  await api.resumeResearchTask("TEST_ONLY/id");
  expect(fetcher.mock.calls.map((args: any[]) => String(args[0]))).toEqual([
    "/api/v1/research-tasks",
    "/api/v1/research-tasks/TEST_ONLY%2Fid",
    "/api/v1/research-tasks/TEST_ONLY%2Fid/cancel",
    "/api/v1/research-tasks/TEST_ONLY%2Fid/resume",
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
    workflow: "legacy",
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
  const result = await api.researchTasksForSymbol("600519");
  expect(result.scope).toBe("BOUNDED_TASK_HISTORY");
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, init] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(url).toBe("/api/v1/research-tasks?symbol=600519");
  expect(init.method ?? "GET").toBe("GET");
  expect(init.body).toBeUndefined();
  expect(new Headers(init.headers).get("X-Local-Session")).toBe(
    "TEST_ONLY_SESSION",
  );
});
