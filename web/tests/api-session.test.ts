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
  const replaceState = vi.fn();
  vi.stubGlobal("window", {
    location: { hash, pathname: "/daily", search: "" },
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
  return { store, replaceState };
}

describe("private session unlock handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("exchanges the unlock fragment once and retries a refused read once", async () => {
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
        if (headers["X-Local-Session"] === "token-2") {
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
    expect(reads.map((call) => call.header)).toEqual(["token-1", "token-2"]);
    expect(unlocks).toBe(2);
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
});
