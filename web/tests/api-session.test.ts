import { beforeEach, describe, expect, it, vi } from "vitest";

type Call = { url: string; header?: string };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("private GET session handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("sends X-Local-Session on GET /portfolio and retries once after 401", async () => {
    const calls: Call[] = [];
    let handshakes = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const headers = (init?.headers ?? {}) as Record<string, string>;
        const header = headers["X-Local-Session"];
        calls.push({ url, header });
        if (url === "/api/v1/private/session") {
          handshakes += 1;
          return json(200, {
            action: "no_order",
            status: "AUTHORIZED",
            token: "token-" + handshakes,
          });
        }
        if (header === "token-2") {
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
    expect(handshakes).toBe(2);
  });

  it("uses the token for GET /private/portfolio/risk", async () => {
    const calls: Call[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const headers = (init?.headers ?? {}) as Record<string, string>;
        calls.push({ url, header: headers["X-Local-Session"] });
        if (url === "/api/v1/private/session") {
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
    expect(
      calls.filter((call) => call.url === "/api/v1/private/session"),
    ).toHaveLength(1);
  });
});
