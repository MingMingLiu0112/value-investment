import { beforeEach, describe, expect, it, vi } from "vitest";

type Call = { url: string; header?: string; body?: string };

const SECRET = "unlock-secret-0123456789abcdef";
const UNLOCK_URL = "/api/v1/private/session/unlock";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubWindow(hash: string) {
  const store = new Map<string, string>();
  const location = { hash, pathname: "/daily", search: "" };
  const replaceState = vi.fn(() => {
    location.hash = "";
  });
  vi.stubGlobal("window", {
    location,
    history: { replaceState },
    sessionStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
    } as unknown as Storage,
  });
  return { store, replaceState, location };
}

describe("private session unlock handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("requests the independent hotspot detail without changing value or private contracts", async () => {
    stubWindow("").store.set("vi-local-session", "private-session");
    const fetcher = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        json(200, { action: "no_order" }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { api } = await import("../src/services/api");
    await api.detail("hotspot-600519");
    await api.detail("000333");
    expect(fetcher.mock.calls.map((call) => String(call[0]))).toEqual([
      "/api/v1/decisions/hotspot-600519?independent_hotspot=true",
      "/api/v1/decisions/000333",
    ]);
    for (const call of fetcher.mock.calls) {
      expect(new Headers(call[1]?.headers).has("X-Local-Session")).toBe(false);
    }
  });

  it("reads external review handoff with the current private session", async () => {
    stubWindow("").store.set("vi-local-session", "handoff-session");
    const fetcher = vi.fn(async () =>
      json(200, { action: "no_order", status: "EXTERNAL_SIGNATURE_REQUIRED" }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { api } = await import("../src/services/api");
    await api.valuePolicyHandoff("600887");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/value-policy-review/600887/handoff",
      expect.objectContaining({
        credentials: "same-origin",
        headers: { "X-Local-Session": "handoff-session" },
      }),
    );
    await api.valuePolicyHandoff("000333", undefined, true);
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/value-policy-review/000333/handoff?bound_draft=true",
      expect.objectContaining({
        credentials: "same-origin",
        headers: { "X-Local-Session": "handoff-session" },
      }),
    );
  });

  it("never requests private handoff anonymously", async () => {
    stubWindow("");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const { api } = await import("../src/services/api");
    await expect(api.valuePolicyHandoff("600887")).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("exchanges the unlock fragment once without retaining it for later requests", async () => {
    const { replaceState } = stubWindow(`#unlock=${SECRET}`);
    const calls: Call[] = [];
    let unlocks = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const headers = (init?.headers ?? {}) as Record<string, string>;
        calls.push({
          url,
          header: headers["X-Local-Session"],
          body: typeof init?.body === "string" ? init.body : undefined,
        });
        if (url === UNLOCK_URL) {
          unlocks += 1;
          expect(JSON.parse(String(init?.body))).toEqual({
            bootstrap_token: SECRET,
          });
          return json(200, {
            action: "no_order",
            status: "AUTHORIZED",
            token: "token-" + unlocks,
          });
        }
        if (headers["X-Local-Session"] === "token-1") {
          return json(200, { action: "no_order", status: "NOT_CONNECTED" });
        }
        return json(401, {
          action: "no_order",
          status: "LOCAL_AUTHORIZATION_REQUIRED",
          detail: null,
        });
      }),
    );
    const { api } = await import("../src/services/api");
    const body = await api.portfolio();
    expect(body.status).toBe("NOT_CONNECTED");
    const reads = calls.filter((call) => call.url === "/api/v1/portfolio");
    expect(reads.map((call) => call.header)).toEqual(["token-1"]);
    expect(unlocks).toBe(1);
    expect(replaceState).toHaveBeenCalledWith(null, "", "/daily");
  });

  it("reuses the stored session token for the private risk read", async () => {
    const { store } = stubWindow(`#unlock=${SECRET}`);
    const calls: Call[] = [];
    let unlocks = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const headers = (init?.headers ?? {}) as Record<string, string>;
        calls.push({ url, header: headers["X-Local-Session"] });
        if (url === UNLOCK_URL) {
          unlocks += 1;
          return json(200, {
            action: "no_order",
            status: "AUTHORIZED",
            token: "token-1",
          });
        }
        return json(200, {
          action: "no_order",
          status: "NOT_CONNECTED",
          blockers: ["PRIVATE_PORTFOLIO_NOT_CONNECTED"],
          engine: null,
          facts: null,
        });
      }),
    );
    const { api } = await import("../src/services/api");
    const body = await api.risk();
    expect(body.blockers).toEqual(["PRIVATE_PORTFOLIO_NOT_CONNECTED"]);
    expect(
      calls.filter((call) => call.url === "/api/v1/private/portfolio/risk"),
    ).toEqual([{ url: "/api/v1/private/portfolio/risk", header: "token-1" }]);
    expect(unlocks).toBe(1);
    expect(store.get("vi-local-session")).toBe("token-1");
  });

  it("fails closed when the page was opened without an unlock link", async () => {
    stubWindow("");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(401, { action: "no_order", status: "LOCKED" })),
    );
    const { api } = await import("../src/services/api");
    await expect(api.portfolio()).rejects.toMatchObject({
      code: "LOCAL_SESSION_LOCKED",
    });
  });

  it("renews a stale stored session before all concurrent private reads", async () => {
    const { store, location } = stubWindow(`#unlock=${SECRET}`);
    store.set("vi-local-session", "expired-token");
    let unlocks = 0;
    const used: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === UNLOCK_URL) {
          unlocks += 1;
          return json(200, { action: "no_order", token: "fresh-token" });
        }
        used.push(new Headers(init?.headers).get("X-Local-Session") ?? "");
        return json(200, { action: "no_order", status: "NOT_CONNECTED" });
      }),
    );
    const { api } = await import("../src/services/api");
    await Promise.all([
      api.portfolio(),
      api.risk(),
      api.valuePolicyHandoff("600519"),
    ]);
    expect(unlocks).toBe(1);
    expect(used).toEqual(["fresh-token", "fresh-token", "fresh-token"]);
    expect(store.get("vi-local-session")).toBe("fresh-token");
    expect(location.hash).toBe("");
  });

  it("does not let a late expired read discard a newly unlocked session", async () => {
    const { store, location } = stubWindow("");
    store.set("vi-local-session", "expired-token");
    let rejectOld: (response: Response) => void = () => {
      throw new Error("Old request not started");
    };
    let started: () => void = () => {};
    const oldStarted = new Promise<void>((resolve) => {
      started = resolve;
    });
    let unlocks = 0;
    const used: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === UNLOCK_URL) {
          unlocks += 1;
          return json(200, { action: "no_order", token: "fresh-token" });
        }
        const token = new Headers(init?.headers).get("X-Local-Session") ?? "";
        used.push(token);
        if (token === "expired-token") {
          return new Promise<Response>((resolve) => {
            rejectOld = resolve;
            started();
          });
        }
        return json(200, { action: "no_order", status: "NOT_CONNECTED" });
      }),
    );
    const { api } = await import("../src/services/api");
    const old = api.portfolio();
    await oldStarted;
    location.hash = `#unlock=${SECRET}`;
    await api.risk();
    rejectOld(
      json(401, { action: "no_order", status: "LOCAL_AUTHORIZATION_REQUIRED" }),
    );
    await old;
    expect(unlocks).toBe(1);
    expect(used).toEqual(["expired-token", "fresh-token", "fresh-token"]);
    expect(store.get("vi-local-session")).toBe("fresh-token");
    await api.valuePolicyHandoff("600519");
    expect(used[used.length - 1]).toBe("fresh-token");
  });

  it("refuses an expired stored token without a fresh launcher link", async () => {
    const { store } = stubWindow("");
    store.set("vi-local-session", "expired-token");
    const fetcher = vi.fn(async () =>
      json(401, { action: "no_order", status: "LOCAL_AUTHORIZATION_REQUIRED" }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { api } = await import("../src/services/api");
    await expect(api.portfolio()).rejects.toMatchObject({
      code: "LOCAL_SESSION_LOCKED",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(store.has("vi-local-session")).toBe(false);
  });
});
