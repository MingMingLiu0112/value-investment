import React from "react";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { LiveOperatingResearchTask } from "../src/services/api";

const hooks = vi.hoisted(() => ({ values: [] as any[], cursor: 0 }));
const calls = vi.hoisted(() => ({
  status: vi.fn(),
  publicRead: vi.fn(),
  start: vi.fn(),
  history: vi.fn(),
  refresh: vi.fn(),
  cancel: vi.fn(),
  resume: vi.fn(),
}));
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState(initial: any) {
      const index = hooks.cursor++;
      if (!(index in hooks.values))
        hooks.values[index] =
          typeof initial === "function" ? initial() : initial;
      return [
        hooks.values[index],
        (next: any) => {
          hooks.values[index] =
            typeof next === "function" ? next(hooks.values[index]) : next;
        },
      ];
    },
    useRef(initial: any) {
      const index = hooks.cursor++;
      if (!(index in hooks.values)) hooks.values[index] = { current: initial };
      return hooks.values[index];
    },
  };
});
vi.mock("../src/services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/services/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      operatingResearchModelStatus: calls.status,
      operatingResearchCompany: calls.publicRead,
      createOperatingResearchTask: calls.start,
      operatingResearchTask: calls.refresh,
      operatingResearchTasks: calls.history,
      cancelOperatingResearchTask: calls.cancel,
      resumeOperatingResearchTask: calls.resume,
    },
  };
});
import { ApiError } from "../src/services/api";
import {
  LiveOperatingResearchPanel,
  LiveOperatingResearchDraft,
  PublicOperatingResearchView,
} from "../src/components/LiveOperatingResearchPanel";

function task(
  changes: Partial<LiveOperatingResearchTask> = {},
): LiveOperatingResearchTask {
  return {
    task_id: "TEST_ONLY_LIVE",
    symbol: "600519",
    status: "QUEUED",
    scope: "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED",
    model_id: "TEST_ONLY_MODEL",
    currency: "CNY",
    new_llm_calls: 0,
    usage: {},
    reserved_cost: "1",
    settled_cost: "0",
    source_binding: { sha256: "a".repeat(64) },
    context_fingerprint: "b".repeat(64),
    research_as_of: null,
    main_range_adopted: false,
    approval_changed: false,
    formal_fact_count: 0,
    condition_price: null,
    personal_quantity: null,
    ...changes,
  };
}
function render() {
  hooks.cursor = 0;
  return LiveOperatingResearchPanel({ symbol: "600519" });
}
function nodes(value: any): any[] {
  if (Array.isArray(value)) return value.flatMap(nodes);
  if (!React.isValidElement(value)) return [];
  return [value, ...nodes((value as any).props.children)];
}
function button(label: string) {
  const node = nodes(render()).find(
    (x) => x.props.children === label && typeof x.props.onClick === "function",
  );
  expect(node, label).toBeDefined();
  return node;
}
async function click(label: string) {
  const node = button(label);
  expect(node.props.disabled).toBeFalsy();
  await node.props.onClick();
}
function shown() {
  return JSON.stringify(render());
}
const ready = {
  status: "READY",
  currency: "CNY",
  model_id: "TEST_ONLY_MODEL",
  max_run_cost: "1",
  daily_cost_limit: "10",
};
beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  for (const call of Object.values(calls)) call.mockReset();
  vi.stubGlobal("crypto", webcrypto);
  calls.status.mockResolvedValue(ready);
  calls.publicRead.mockResolvedValue({
    symbol: "600519",
    action: "no_order",
    formal_eligibility: false,
    status: "NOT_STARTED",
  });
});
afterEach(() => vi.unstubAllGlobals());

it("has no first-screen request, opens status only on click and never polls", async () => {
  vi.useFakeTimers();
  render();
  await vi.advanceTimersByTimeAsync(60000);
  for (const call of Object.values(calls)) expect(call).not.toHaveBeenCalled();
  await click("新Agent经营研究");
  expect(calls.status).toHaveBeenCalledTimes(1);
  expect(calls.start).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(60000);
  expect(calls.status).toHaveBeenCalledTimes(1);
  expect(shown()).toContain("每日费用上限（人民币元）");
  expect(shown()).toContain("非账单");
  vi.useRealTimers();
});
it.each(["MODEL_AUTHORIZATION_REQUIRED", "MODEL_CREDENTIAL_REQUIRED"])(
  "blocks start and resume when %s",
  async (status) => {
    calls.status.mockResolvedValue({ ...ready, status, model_id: null });
    await click("新Agent经营研究");
    expect(button("启动新研究").props.disabled).toBe(true);
    await button("启动新研究").props.onClick();
    expect(calls.start).not.toHaveBeenCalled();
    expect(shown()).toContain("不能启动");
  },
);
it("starts with unique keys then manually refreshes cancels resumes and reads history", async () => {
  await click("新Agent经营研究");
  calls.start.mockResolvedValue(task());
  await click("启动新研究");
  const first = calls.start.mock.calls[0][0];
  expect(first.symbol).toBe("600519");
  expect(first.request_key).toMatch(/^[a-zA-Z0-9_]{8,80}$/);
  calls.refresh.mockResolvedValue(
    task({ status: "RUNNING", new_llm_calls: 1 }),
  );
  await click("刷新当前任务");
  expect(calls.refresh).toHaveBeenCalledWith("TEST_ONLY_LIVE");
  calls.cancel.mockResolvedValue(task({ status: "CANCELLED" }));
  await click("取消当前任务");
  calls.resume.mockResolvedValue(task({ status: "QUEUED" }));
  await click("恢复当前任务");
  calls.cancel.mockResolvedValue(task({ status: "CANCELLED" }));
  await click("取消当前任务");
  await click("启动新研究");
  expect(calls.start.mock.calls[1][0].request_key).not.toBe(first.request_key);
  calls.history.mockResolvedValue({
    items: [task(), task({ symbol: "600887" })],
  });
  await click("读取已有经营研究任务");
  expect(shown()).toContain("不能选择");
});
it("recovers a discovered task without creating another", async () => {
  await click("新Agent经营研究");
  calls.history.mockResolvedValue({ items: [task({ status: "CANCELLED" })] });
  await click("读取已有经营研究任务");
  const select = nodes(render()).find(
    (x) =>
      typeof x.props.onClick === "function" &&
      Array.isArray(x.props.children) &&
      x.props.children.includes("选择任务 "),
  );
  expect(select).toBeDefined();
  select.props.onClick();
  expect(button("恢复当前任务").props.disabled).toBeFalsy();
  expect(calls.start).not.toHaveBeenCalled();
});
it("keeps local authorization failures in a single local alert", async () => {
  await click("新Agent经营研究");
  calls.start.mockRejectedValue(
    new ApiError(401, "AUTH_REQUIRED", "TEST_ONLY"),
  );
  await click("启动新研究");
  expect(shown()).toContain("需要本机授权");
  expect(shown()).toContain("公开研究仍可查看");
});
it.each([
  { symbol: "600887" },
  { main_range_adopted: true },
  { approval_changed: true },
  { formal_fact_count: 1 },
  { condition_price: "1" },
  { personal_quantity: 1 },
  { currency: "USD" },
  { scope: "SAVED_RESPONSE" },
])("rejects task boundary mismatch %j", async (change) => {
  await click("新Agent经营研究");
  calls.start.mockResolvedValue(task(change as any));
  await click("启动新研究");
  expect(shown()).toContain("响应边界无法核验");
  expect(shown()).not.toContain("新Agent经营研究结果");
});
it("renders readable draft sections and distinguishes test contract from real research", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={task({
        scope: "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH",
        research_draft: {
          FUNDAMENTAL: { thesis: "TEST_ONLY经营判断" },
          COUNTER_EVIDENCE: [{ text: "TEST_ONLY反证" }],
          EVENT: { next_events: ["TEST_ONLY事件"] },
        },
      })}
    />,
  );
  for (const text of [
    "经营基本面草案",
    "反证与失效草案",
    "事件与后续核验草案",
    "TEST_ONLY经营判断",
    "TEST_ONLY反证",
    "TEST_ONLY事件",
    "不是真实模型研究",
    "正式事实新增 0",
    "非服务商账单",
  ])
    expect(html).toContain(text);
});
it("mounts only beside existing value company panels and adds no timers or automatic tasks", () => {
  const index = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  const panel = readFileSync(
    "src/components/LiveOperatingResearchPanel.tsx",
    "utf8",
  );
  expect(index).toMatch(
    /strategy !== "hotspot"[\s\S]*?<LiveOperatingResearchPanel/,
  );
  expect(panel).not.toMatch(/setInterval|setTimeout|localStorage/);
  expect(panel).not.toContain("SAVED_RESPONSE");
});

it("shows missing authorization from the minimal public status response without guessing a provider", async () => {
  calls.status.mockResolvedValue({
    status: "MODEL_AUTHORIZATION_REQUIRED",
    model_id: null,
  });
  await click("新Agent经营研究");
  expect(shown()).toContain("模型接口、模型或调用配置尚未齐备，不能启动");
  expect(shown()).toContain("已授权每日人民币10元");
  expect(shown()).not.toContain("缺少模型调用授权");
  expect(button("启动新研究").props.disabled).toBe(true);
  expect(calls.start).not.toHaveBeenCalled();
});
it("renders the actual source-bound role envelope as readable economic sections", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={task({
        research_draft: {
          FUNDAMENTAL: {
            draft: {
              business_drivers: [
                { text: "TEST_ONLY_BUSINESS", evidence_ids: ["E1"] },
              ],
              scenarios: {
                base: [
                  {
                    dimension: "growth",
                    classification: "UNKNOWN",
                    lower: null,
                    rationale: "TEST_ONLY_NOT_PROVEN",
                  },
                ],
              },
            },
            source_bindings: [],
          },
          COUNTER_EVIDENCE: {
            draft: {
              counterevidence: [{ text: "TEST_ONLY_CHALLENGE" }],
              invalidation: [{ text: "TEST_ONLY_BREAKER" }],
            },
          },
          EVENT: {
            draft: { seen_events: [], uncovered: [{ text: "TEST_ONLY_GAP" }] },
          },
        },
      })}
    />,
  );
  for (const text of [
    "经营驱动",
    "中间条件情景（未采用主区间）",
    "增长",
    "未知，未证明",
    "TEST_ONLY_NOT_PROVEN",
    "TEST_ONLY_CHALLENGE",
    "TEST_ONLY_BREAKER",
    "TEST_ONLY_GAP",
  ])
    expect(html).toContain(text);
});

function publicSuccess() {
  const role = (draft: Record<string, unknown>) => ({
    model_id: "TEST_ONLY_MODEL",
    generated_at: "2026-10-31T10:00:00Z",
    source_bindings: [{ id: "TEST_ONLY_SOURCE", pdf_sha256: "a".repeat(64) }],
    draft,
  });
  const { currency, reserved_cost, settled_cost, usage, ...publicTask } = task({
    status: "SUCCEEDED",
    new_llm_calls: 3,
  });
  return {
    ...publicTask,
    action: "no_order" as const,
    formal_eligibility: false as const,
    status: "SUCCEEDED" as const,
    scope: "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" as const,
    research_draft: {
      FUNDAMENTAL: role({
        business_drivers: [
          { text: "TEST_ONLY_PUBLIC_BUSINESS", evidence_ids: ["E1"] },
        ],
        scenarios: {},
      }),
      COUNTER_EVIDENCE: role({
        counterevidence: [{ text: "TEST_ONLY_PUBLIC_COUNTER" }],
        invalidation: [],
      }),
      EVENT: role({
        seen_events: [],
        uncovered: [{ text: "TEST_ONLY_PUBLIC_GAP" }],
      }),
    },
  };
}
it("loads public result and model status in parallel only after opening, without private task reads", async () => {
  let resolveModel: (value: any) => void = () => {};
  calls.status.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveModel = resolve;
      }),
  );
  calls.publicRead.mockResolvedValue(publicSuccess());
  const pending = button("新Agent经营研究").props.onClick();
  expect(calls.status).toHaveBeenCalledTimes(1);
  expect(calls.publicRead).toHaveBeenCalledWith("600519");
  expect(calls.history).not.toHaveBeenCalled();
  expect(calls.refresh).not.toHaveBeenCalled();
  resolveModel({ status: "MODEL_AUTHORIZATION_REQUIRED", model_id: null });
  await pending;
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(button("启动新研究").props.disabled).toBe(true);
});
it("keeps public research readable even when model status or private history fails", async () => {
  calls.status.mockRejectedValue(new Error("TEST_ONLY_STATUS_FAILURE"));
  calls.publicRead.mockResolvedValue(publicSuccess());
  await click("新Agent经营研究");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  calls.history.mockRejectedValue(
    new ApiError(401, "AUTH_REQUIRED", "TEST_ONLY"),
  );
  await click("读取已有经营研究任务");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shown()).toContain("需要本机授权");
});
it("replaces old public success with latest unassessable result or transport failure without fallback", async () => {
  calls.publicRead.mockResolvedValue(publicSuccess());
  await click("新Agent经营研究");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  calls.publicRead.mockResolvedValue({
    symbol: "600519",
    action: "no_order",
    formal_eligibility: false,
    status: "UNASSESSABLE",
    reason: "TEST_ONLY_LATEST_FAILED",
  });
  await click("刷新模型状态");
  expect(shown()).not.toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shown()).toContain("TEST_ONLY_LATEST_FAILED");
  calls.publicRead.mockRejectedValue(new Error("TEST_ONLY_SOURCE_INVALID"));
  await click("刷新模型状态");
  expect(shown()).not.toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shown()).toContain("不回退展示旧结果");
});
it("renders only source-bound real public success, preserving readable three roles", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = publicSuccess();
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={value} symbol="600519" />,
  );
  for (const text of [
    "TEST_ONLY_PUBLIC_BUSINESS",
    "TEST_ONLY_PUBLIC_COUNTER",
    "TEST_ONLY_PUBLIC_GAP",
    "不发起新调用",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("预留费用");
});
it.each([
  { symbol: "600887" },
  { scope: "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH" },
  { main_range_adopted: true },
  { approval_changed: true },
  { formal_fact_count: 1 },
  { condition_price: "1" },
  { research_draft: { FUNDAMENTAL: { draft: {} } } },
  { new_llm_calls: 0 },
])("blocks invalid public success %j", (change) => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = { ...publicSuccess(), ...change };
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={value as any} symbol="600519" />,
  );
  expect(html).toContain("停止展示");
  expect(html).not.toContain("TEST_ONLY_PUBLIC_BUSINESS");
});
it.each(["NOT_STARTED", "UNASSESSABLE"] as const)(
  "does not invent public result for %s",
  (status) => {
    const { renderToStaticMarkup } = require("react-dom/server");
    const html = renderToStaticMarkup(
      <PublicOperatingResearchView
        value={{
          symbol: "600519",
          action: "no_order",
          formal_eligibility: false,
          status,
          reason: "TEST_ONLY_LATEST_INVALID",
        }}
        symbol="600519"
      />,
    );
    expect(html).toContain(
      status === "NOT_STARTED" ? "尚无已生成" : "不回退展示旧成功结果",
    );
    expect(html).not.toContain("经营基本面草案");
  },
);

it.each(["REVIEW_REQUIRED", "INSUFFICIENT_FOR_NUMERIC_SCENARIOS"] as const)(
  "shows optional completeness %s without promoting successful tasks into sufficient research",
  (status) => {
    const { renderToStaticMarkup } = require("react-dom/server");
    const completeness = {
      scenario_count: 3,
      numeric_assumption_count: 4,
      unknown_assumption_count: 11,
      status,
      economic_validation: "NOT_APPROVED" as const,
    };
    for (const value of [
      task({ status: "SUCCEEDED", research_completeness: completeness }),
      { ...publicSuccess(), research_completeness: completeness },
    ]) {
      const html = renderToStaticMarkup(
        <LiveOperatingResearchDraft task={value} />,
      );
      expect(html).toContain("情景数：3");
      expect(html).toContain("数值假设数：4");
      expect(html).toContain("未知假设数：11");
      expect(html).toContain(
        status === "REVIEW_REQUIRED"
          ? "研究完整度仍需复核"
          : "数值情景依据不足",
      );
      expect(html).toContain("经济有效性尚未批准");
      expect(html).toContain("不代表经营或估值研究充分");
    }
  },
);
it("keeps legacy responses without completeness compatible and never assumes sufficiency", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft task={task({ status: "SUCCEEDED" })} />,
  );
  expect(html).toContain("尚未提供研究完整度统计，不推定研究充分");
  expect(html).not.toContain("情景数：");
});
