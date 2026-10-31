import { afterEach, beforeEach, expect, it, vi } from "vitest";
beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it("cold-reads the registered first input through one public GET without auth, LLM/task calls or writes", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          symbol: "000568",
          status: "NOT_STARTED",
          action: "no_order",
          formal_eligibility: false,
          main_range_adopted: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("window", {
    location: { hash: "" },
    sessionStorage: {
      getItem: () => {
        throw new Error(
          "First input read must not touch private session state",
        );
      },
    },
  });
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  const controller = new AbortController();
  await api.firstResearchInput("000568", controller.signal);
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [path, options] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(path).toBe("/api/v1/first-research-inputs/000568");
  expect(options.method ?? "GET").toBe("GET");
  expect(options.body).toBeUndefined();
  expect(options.signal).toBe(controller.signal);
  expect(new Headers(options.headers).has("X-Local-Session")).toBe(false);
});
