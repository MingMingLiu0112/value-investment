import { afterEach, beforeEach, expect, it, vi } from "vitest";

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it("uses a pure public GET with an abort signal, without auth bootstrap or writes", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          symbol: "600519",
          status: "MISSING_SOURCE",
          action: "no_order",
          formal_eligibility: false,
          valuation_computed: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("window", {
    location: { hash: "" },
    sessionStorage: {
      getItem: () => {
        throw new Error("D2 must not read account/session state");
      },
    },
  });
  const { api } = await import("../src/services/api");
  expect(fetcher).not.toHaveBeenCalled();
  const controller = new AbortController();
  await api.researchAssumptionDraft("600519", controller.signal);
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [path, options] = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0];
  expect(path).toBe("/api/v1/research-assumption-drafts/600519");
  expect(options.method ?? "GET").toBe("GET");
  expect(options.body).toBeUndefined();
  expect(options.signal).toBe(controller.signal);
  expect(new Headers(options.headers).has("X-Local-Session")).toBe(false);
});
