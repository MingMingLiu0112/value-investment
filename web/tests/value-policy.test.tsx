import React from "react";
const { renderToStaticMarkup } = require("react-dom/server");
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createValuePolicyTransport,
  fractionFromPercent,
} from "../src/services/valuePolicy";
import {
  RegisteredPolicySummary,
  ValuePolicyEditor,
} from "../src/components/ValuePolicyEditor";
import type { PolicyRegistration } from "../src/services/valuePolicy";

afterEach(() => vi.unstubAllGlobals());

describe("private value policy", () => {
  it("retains the registered base 80% choice when G3 leaves domain action price null", () => {
    const registered: PolicyRegistration = {
      action: "no_order",
      status: "REGISTERED",
      scope: "ISOLATED_TEST",
      preview_id: "x",
      formal_eligibility: false,
      portfolio_eligibility: null,
      research_approval_changed: false,
      production_published: false,
      registered_policy: {
        price_scope: "PRIVATE_POLICY_ARITHMETIC_NOT_ADMITTED",
        draft: {
          effective_from: "2026-10-15",
          effective_through: "2026-11-15",
          rationale: "本人明确选择",
          dividend_coverage_risk: "分红待核验",
          rules: [
            {
              action: "entry",
              scenario: "base",
              value_fraction: "0.80",
              comparison: "LTE",
              rationale: "现金流恶化时复核",
            },
          ],
        },
        draft_prices: { entry: "8.060109882454410357" },
      },
      conditional_plan: {
        entry_trigger_price: null,
        blockers: ["formal G3 human valuation approval not present"],
      },
    };
    const html = renderToStaticMarkup(
      <RegisteredPolicySummary registered={registered} />,
    );
    expect(html).toContain("8.0601");
    expect(html).toContain("80%");
    expect(html).toContain("基准");
    expect(html).toContain("现金流恶化时复核");
    expect(html).toContain("G3 人工估值审核尚未通过");
    expect(html).toContain("研究或价格条件不足，尚无适用价");
    expect(html).toContain("草稿算术价，未获正式动作资格");
  });
  it("converts explicit percentages exactly without default thresholds", () => {
    expect(fractionFromPercent("93")).toBe("0.93");
    expect(fractionFromPercent("107.012345")).toBe("1.07012345");
    expect(fractionFromPercent("0.000001")).toBe("0.00000001");
    for (const value of ["", "0", "NaN", "Infinity", "-3", "1e2"])
      expect(() => fractionFromPercent(value)).toThrow();
  });

  it("uses existing session headers and never sends actor authority", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ action: "no_order", status: "REGISTERED" }),
    });
    vi.stubGlobal("fetch", fetcher);
    const transport = createValuePolicyTransport(async () => ({
      "X-Local-Session": "synthetic",
    }));
    await transport.confirm("600887", {
      preview_id: "digest",
      acknowledged: true,
      note: "owner note",
    });
    const [url, request] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/value-policy-review/600887/confirm");
    expect(request.credentials).toBe("same-origin");
    expect(request.headers["X-Local-Session"]).toBe("synthetic");
    expect(JSON.parse(request.body)).toEqual({
      preview_id: "digest",
      acknowledged: true,
      note: "owner note",
    });
  });

  it("surfaces recoverable authorization errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ action: "no_order", detail: "请重新授权" }),
      }),
    );
    const transport = createValuePolicyTransport(async () => ({}));
    await expect(
      transport.confirm("600887", {
        preview_id: "x",
        acknowledged: true,
        note: "note",
      }),
    ).rejects.toThrow("请重新授权");
  });

  it("reads own status through authentication without caching", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        action: "no_order",
        status: "NOT_REGISTERED",
        conditional_plan: null,
      }),
    });
    vi.stubGlobal("fetch", fetcher);
    const transport = createValuePolicyTransport(async () => ({
      "X-Local-Session": "synthetic",
    }));
    expect((await transport.status("600887")).status).toBe("NOT_REGISTERED");
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/v1/value-policy-review/600887/status",
    );
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      cache: "no-store",
      headers: { "X-Local-Session": "synthetic" },
    });
  });

  it("starts with no selected rules and no confirmation before preview", () => {
    const transport = createValuePolicyTransport(async () => ({}));
    const html = renderToStaticMarkup(
      <ValuePolicyEditor symbol="600887" transport={transport} initial={{}} />,
    );
    expect(html).toContain("预览本人政策草稿");
    expect(html).not.toContain("本人确认并不可变登记");
    expect(html).not.toContain("checked");
    expect(html).not.toContain('value="93"');
  });
});
