import React from "react";
const { renderToStaticMarkup } = require("react-dom/server");
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/services/api";
const state = vi.hoisted(() => ({
  loading: false,
  error: undefined as string | undefined,
  data: { status: "NOT_REGISTERED", hasPolicyDraft: true },
}));
const loaders = vi.hoisted(() => ({
  current: undefined as ((signal: AbortSignal) => Promise<unknown>) | undefined,
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: (load: (signal: AbortSignal) => Promise<unknown>) => {
    loaders.current = load;
    return state;
  },
}));
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));
import { ConfirmationTasks } from "../src/components/ConfirmationTasks";
describe("consolidated confirmations", () => {
  beforeEach(() => {
    state.data.status = "NOT_REGISTERED";
    state.data.hasPolicyDraft = true;
    state.loading = false;
    state.error = undefined;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    loaders.current = undefined;
  });
  it.each(["NOT_REGISTERED", "REVIEW_REQUIRED"])(
    "omits unavailable draft policy tasks for %s without hiding a real G3 handoff",
    (status) => {
      state.data.status = status;
      state.data.hasPolicyDraft = false;
      const html = renderToStaticMarkup(
        <ConfirmationTasks
          connected
          decisions={[
            {
              id: "no-draft",
              symbol: "000333",
              strategy: "CORE_VALUE",
              blockers: ["G3_PENDING"],
            },
          ]}
        />,
      );
      expect(html).not.toContain("personal-value-policy");
      expect(html).toContain("value-review-handoff");
    },
  );
  it("shows no company task for a missing draft without a G3 blocker", () => {
    state.data.hasPolicyDraft = false;
    const html = renderToStaticMarkup(
      <ConfirmationTasks
        connected
        decisions={[
          { id: "no-draft", symbol: "000333", strategy: "CORE_VALUE" },
        ]}
      />,
    );
    expect(html).not.toContain("no-draft");
    expect(html).not.toContain("选择并确认本人价格政策");
  });
  it("keeps a G3 handoff discoverable after own policy registration", () => {
    state.data.status = "REGISTERED";
    const html = renderToStaticMarkup(
      <ConfirmationTasks
        connected
        decisions={[
          {
            id: "value-case",
            symbol: "600887",
            strategy: "CORE_VALUE",
            blockers: ["G3_PENDING"],
          },
        ]}
      />,
    );
    expect(html).toContain('href="/decisions/value-case#value-review-handoff"');
    expect(html).toContain("准备外部 G3 估值审核交接材料");
    expect(html).not.toContain("选择并确认本人价格政策");
  });
  it("shows recovery without exposing company tasks when authenticated status is unavailable", () => {
    state.error = "authorization required";
    const html = renderToStaticMarkup(
      <ConfirmationTasks
        connected={false}
        decisions={[
          {
            id: "value-case",
            name: "PRIVATE_COMPANY_SENTINEL",
            symbol: "600887",
            strategy: "CORE_VALUE",
            blockers: ["G3_PENDING"],
          },
        ]}
      />,
    );
    expect(html).not.toContain("PRIVATE_COMPANY_SENTINEL");
    expect(html).not.toContain("value-review-handoff");
    expect(html).toContain("确认状态读取失败，待确认事项暂未核验。");
    expect(html).toContain("重试");
    expect(html).toContain('href="/portfolio"');
  });
  it.each([
    ["a network rejection", () => Promise.reject(new Error("network down"))],
    [
      "an HTTP failure",
      () =>
        Promise.resolve({
          ok: false,
          json: async () => ({
            action: "no_order",
            status: "REVIEW_UNAVAILABLE",
          }),
        }),
    ],
  ])(
    "does not swallow %s from the policy review request",
    async (_, failure) => {
      state.data.status = "NOT_REGISTERED";
      renderToStaticMarkup(
        <ConfirmationTasks
          connected
          decisions={[
            { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
          ]}
        />,
      );
      expect(loaders.current).toBeTypeOf("function");
      vi.spyOn(api, "valuePolicyStatus").mockResolvedValue({
        action: "no_order",
        status: "NOT_REGISTERED",
        scope: "LOCAL_USER_POLICY",
        conditional_plan: null,
      });
      vi.stubGlobal("fetch", vi.fn(failure));
      await expect(
        loaders.current!(new AbortController().signal),
      ).rejects.toThrow();
    },
  );
  it("treats an unavailable review basis as no draft instead of a read failure", async () => {
    state.data.status = "NOT_REGISTERED";
    renderToStaticMarkup(
      <ConfirmationTasks
        connected
        decisions={[{ id: "600519", symbol: "600519", strategy: "CORE_VALUE" }]}
      />,
    );
    expect(loaders.current).toBeTypeOf("function");
    vi.spyOn(api, "valuePolicyStatus").mockResolvedValue({
      action: "no_order",
      status: "NOT_REGISTERED",
      scope: "LOCAL_USER_POLICY",
      conditional_plan: null,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 409,
          json: async () => ({
            action: "no_order",
            status: "REVIEW_UNAVAILABLE",
          }),
        }),
      ),
    );
    await expect(
      loaders.current!(new AbortController().signal),
    ).resolves.toMatchObject({
      status: "NOT_REGISTERED",
      hasPolicyDraft: false,
    });
  });
  it("keeps unknown private facts and research authority independent with working destinations", () => {
    const html = renderToStaticMarkup(
      <ConfirmationTasks
        connected={false}
        decisions={[
          {
            id: "600887",
            symbol: "600887",
            name: "伊利股份",
            strategy: "CORE_VALUE",
            price_action_plan: {
              action: "no_order",
              signal_state: "WATCH",
              entry_trigger_price: null,
              invalidation_price: null,
              base: "10.08",
            },
          },
        ]}
      />,
    );
    expect(html).toContain("尚未连接");
    expect(html).toContain("不批准估值");
    expect(html).toContain('href="/portfolio"');
    expect(html).toContain('href="/decisions/600887#personal-value-policy"');
    expect(html).not.toContain("生产授权与最终使用验收");
    expect(html).not.toContain("估值审查与事件");
  });
  it.each(["REGISTERED", "ERROR", "LOADING"])(
    "does not invent personal approval tasks for %s",
    (status) => {
      state.data.status = status;
      state.error = status === "ERROR" ? "not authorized" : undefined;
      state.loading = status === "LOADING";
      const html = renderToStaticMarkup(
        <ConfirmationTasks
          connected
          decisions={[
            { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
          ]}
        />,
      );
      expect(html).not.toContain("选择并确认本人价格政策");
      expect(html).not.toContain("重新复核本人价格政策");
    },
  );
});
