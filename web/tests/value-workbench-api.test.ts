import { afterEach, beforeEach, expect, it, vi } from "vitest";
beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", {
    location: { hash: "", pathname: "/strategy/value", search: "" },
    sessionStorage: {
      getItem: () => "TEST_ONLY_SESSION",
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
  });
});
afterEach(() => vi.unstubAllGlobals());
it("keeps public workbench/companies/prepare reads public and task list/id/history authorized", async () => {
  const fetcher = vi.fn(
    async (_url: string, _init?: RequestInit) =>
      new Response(
        JSON.stringify({ action: "no_order", formal_eligibility: false }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  await api.valueWorkbench("TEST/ONLY");
  await api.valueWorkbenchCompanies();
  await api.valueWorkbenchTaskInputs("TEST/ONLY");
  await api.valueWorkbenchTasks("TEST/ONLY");
  await api.valueWorkbenchTask("TEST/ID");
  await api.valueWorkbenchTaskHistory("TEST/ID");
  expect(fetcher.mock.calls.map((call) => call[0])).toEqual([
    "/api/v1/value-workbench?symbol=TEST%2FONLY",
    "/api/v1/value-workbench/companies",
    "/api/v1/value-workbench/task-inputs?symbol=TEST%2FONLY",
    "/api/v1/value-workbench/tasks?symbol=TEST%2FONLY",
    "/api/v1/value-workbench/tasks/TEST%2FID",
    "/api/v1/value-workbench/tasks/TEST%2FID/history",
  ]);
  for (const [index, [, init]] of fetcher.mock.calls.entries()) {
    expect(init?.method ?? "GET").toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("X-Local-Session")).toBe(
      index >= 3 ? "TEST_ONLY_SESSION" : null,
    );
  }
});
it("sends the exact native payload and authorized cancel/retry/resume only on explicit calls", async () => {
  const fetcher = vi.fn(
    async (_url: string, _init?: RequestInit) =>
      new Response(
        JSON.stringify({ action: "no_order", formal_eligibility: false }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  const body = {
    module_id: "B",
    operation: "FRESH_PUBLIC_SCAN",
    symbol: "TEST_ONLY",
    request_key: "TEST_ONLY_REQUEST",
    payload: { network_authorized: true, max_per_channel: 10 },
  };
  await api.createValueWorkbenchTask(body);
  for (const operation of ["cancel", "retry", "resume"] as const)
    await api.controlValueWorkbenchTask("TEST/ID", operation);
  expect(fetcher.mock.calls.map((call) => call[0])).toEqual([
    "/api/v1/value-workbench/tasks",
    "/api/v1/value-workbench/tasks/TEST%2FID/cancel",
    "/api/v1/value-workbench/tasks/TEST%2FID/retry",
    "/api/v1/value-workbench/tasks/TEST%2FID/resume",
  ]);
  expect(JSON.parse(fetcher.mock.calls[0][1]?.body as string)).toEqual(body);
  for (const [, init] of fetcher.mock.calls) {
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Local-Session")).toBe(
      "TEST_ONLY_SESSION",
    );
    expect(init?.credentials).toBe("same-origin");
  }
  for (const [, init] of fetcher.mock.calls.slice(1))
    expect(JSON.parse(init?.body as string)).toEqual({});
});

it("does not require an account for public reads and refuses a locked task read once without a network loop", async () => {
  vi.stubGlobal("window", {
    location: { hash: "", pathname: "/strategy/value", search: "" },
    sessionStorage: {
      getItem: () => null,
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
  });
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({ action: "no_order", formal_eligibility: false }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const { api } = await import("../src/services/api");
  await api.valueWorkbenchCompanies();
  await api.valueWorkbenchTaskInputs("TEST_ONLY");
  expect(fetcher).toHaveBeenCalledTimes(2);
  await expect(api.valueWorkbenchTask("TEST_ONLY")).rejects.toMatchObject({
    status: 401,
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
});
