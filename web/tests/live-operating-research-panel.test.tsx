import React from "react";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type {
  LiveOperatingResearchTask,
  OperatingDriverBridge,
  OperatingDriverKey,
} from "../src/services/api";

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
  OperatingDriverBridgeView,
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

function publicPartial() {
  const success = publicSuccess();
  const { EVENT, ...draft } = success.research_draft;
  return {
    ...success,
    status: "PARTIAL" as const,
    execution_status: "FAILED" as const,
    reason: "DAILY_BUDGET_EXHAUSTED_BEFORE_CALL",
    completed_roles: ["FUNDAMENTAL", "COUNTER_EVIDENCE"] as (
      "FUNDAMENTAL" | "COUNTER_EVIDENCE" | "EVENT"
    )[],
    pending_roles: ["EVENT"] as (
      "FUNDAMENTAL" | "COUNTER_EVIDENCE" | "EVENT"
    )[],
    research_draft: draft,
  };
}
it("shows current source-bound partial F/C only with explicit Event budget gap and failed execution", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={publicPartial()} symbol="600519" />,
  );
  for (const text of [
    "TEST_ONLY_PUBLIC_BUSINESS",
    "TEST_ONLY_PUBLIC_COUNTER",
    "三角色未全部完成",
    "执行状态为失败",
    "事件研究待预算",
    "调用前预算预留被拒",
    "本轮已停止于每日预算预留，事件待继续",
    "正式事实新增 0",
    "经济主区间未采用",
    "不发起新调用",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("TEST_ONLY_PUBLIC_GAP");
  expect(html).not.toContain("事件与后续核验草案");
  expect(html).not.toContain("任务完成仅表示流程完成");
});
it("keeps current public partial visible without model configuration or private history permission and never calls model", async () => {
  calls.status.mockResolvedValue({
    status: "MODEL_AUTHORIZATION_REQUIRED",
    model_id: null,
  });
  calls.publicRead.mockResolvedValue(publicPartial());
  await click("新Agent经营研究");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shown()).toContain("PARTIAL");
  expect(button("启动新研究").props.disabled).toBe(true);
  expect(calls.start).not.toHaveBeenCalled();
  expect(calls.history).not.toHaveBeenCalled();
  calls.history.mockRejectedValue(
    new ApiError(401, "AUTH_REQUIRED", "TEST_ONLY"),
  );
  await click("读取已有经营研究任务");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_COUNTER");
  expect(calls.resume).not.toHaveBeenCalled();
});
it.each([
  { execution_status: "SUCCEEDED" },
  {
    completed_roles: ["FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"],
    pending_roles: [],
  },
  { completed_roles: ["FUNDAMENTAL", "FUNDAMENTAL"], pending_roles: ["EVENT"] },
  { completed_roles: ["FUNDAMENTAL"], pending_roles: ["EVENT"] },
  { scope: "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH" },
  { action: "order" },
  { formal_eligibility: true },
  { approval_changed: true },
  { main_range_adopted: true },
  { formal_fact_count: 1 },
  { condition_price: "1" },
  { personal_quantity: 1 },
  { source_binding: { sha256: "broken" } },
  { context_fingerprint: "broken" },
  {
    research_draft: {
      ...publicPartial().research_draft,
      EVENT: publicSuccess().research_draft.EVENT,
    },
  },
  {
    research_draft: {
      ...publicPartial().research_draft,
      FUNDAMENTAL: {
        ...publicPartial().research_draft.FUNDAMENTAL,
        source_bindings: [{ pdf_sha256: "broken" }],
      },
    },
  },
])("stops partial with invalid role/source/no-order boundary %j", (change) => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = { ...publicPartial(), ...change };
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={value as any} symbol="600519" />,
  );
  expect(html).toContain("停止展示");
  expect(html).not.toContain("TEST_ONLY_PUBLIC_BUSINESS");
});
it("replaces an earlier public success with the latest partial without reusing old Event", async () => {
  calls.publicRead.mockResolvedValue(publicSuccess());
  await click("新Agent经营研究");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_GAP");
  calls.publicRead.mockResolvedValue(publicPartial());
  await click("刷新模型状态");
  expect(shown()).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shown()).not.toContain("TEST_ONLY_PUBLIC_GAP");
});

it("shows optional independent-review warning without changing role draft or adopting a disputed counterclaim", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const review = {
    status: "REVIEW_REQUIRED_NOT_APPROVAL" as const,
    findings: [
      {
        priority: "P2",
        role: "COUNTER_EVIDENCE" as const,
        claim_index: 5,
        reason: "称F混用公司/渠道库存，但F已明确区分；这条反证不能直接采用",
      },
    ],
  };
  for (const input of [publicSuccess(), publicPartial()]) {
    const value = { ...input, independent_review: review };
    const before = JSON.stringify(value);
    const html = renderToStaticMarkup(
      <PublicOperatingResearchView value={value} symbol="600519" />,
    );
    for (const text of [
      "独立复核待处理，不代表批准",
      "反证也可能有误述",
      "任务成功不等于研究可信",
      "P2",
      "原始条目索引 5",
      review.findings[0].reason,
      "TEST_ONLY_PUBLIC_BUSINESS",
      "TEST_ONLY_PUBLIC_COUNTER",
    ])
      expect(html).toContain(text);
    expect(JSON.stringify(value)).toBe(before);
  }
});
it("keeps old results without independent review compatible and scopes the partial budget message to this run", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={publicPartial()} symbol="600519" />,
  );
  expect(html).not.toContain("独立复核待处理");
  expect(html).toContain("本轮已停止于每日预算预留，事件待继续");
  expect(html).not.toContain("今日不再发起付费调用");
});

it("hides stale independent review when its binding is invalid on public and private results", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const review = {
    status: "REVIEW_REQUIRED_NOT_APPROVAL" as const,
    findings: [
      {
        priority: "P2",
        role: "COUNTER_EVIDENCE" as const,
        claim_index: 5,
        reason: "TEST_ONLY_STALE_REVIEW_MUST_NOT_RENDER",
      },
    ],
  };
  for (const input of [
    task({ status: "SUCCEEDED" }),
    publicSuccess(),
    publicPartial(),
  ]) {
    const value = {
      ...input,
      independent_review: review,
      independent_review_status: "REVIEW_BINDING_INVALID" as const,
    };
    const before = JSON.stringify(value);
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={value} />,
    );
    expect(html).toContain("独立经济复核绑定失效，旧复核内容不予展示");
    expect(html).not.toContain("TEST_ONLY_STALE_REVIEW_MUST_NOT_RENDER");
    expect(html).not.toContain("独立复核待处理");
    expect(html).not.toContain("尚无独立经济复核");
    expect(JSON.stringify(value)).toBe(before);
  }
});
it("distinguishes successful research without independent review from review-binding failure", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  for (const value of [task({ status: "SUCCEEDED" }), publicSuccess()]) {
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={value} />,
    );
    expect(html).toContain("尚无独立经济复核");
    expect(html).not.toContain("独立经济复核绑定失效");
  }
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={{
        ...publicSuccess(),
        independent_review_status: "REVIEW_BINDING_INVALID",
      }}
    />,
  );
  expect(html).toContain("独立经济复核绑定失效");
  expect(html).not.toContain("尚无独立经济复核");
});
it("labels task settlement as an estimate rather than actual provider billing", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft task={task({ settled_cost: "7.33345" })} />,
  );
  expect(html).toContain("估算结算费用（人民币元）：7.33345");
  expect(html).toContain("非服务商账单");
  expect(html).not.toContain("已结算费用");
});

function driverBridge(): OperatingDriverBridge {
  const assumption = (lower: string, upper: string) => ({
    lower,
    upper,
    rationale: "TEST_ONLY_DRIVER_REASON",
    evidence_ids: ["TEST_ONLY_EVIDENCE"],
  });
  const fields = Object.fromEntries(
    [
      "revenue",
      "cost",
      "surcharges",
      "selling",
      "admin",
      "research",
      "pre_tax_profit",
    ].map((key) => [
      key,
      {
        value: "1000000.123456789012345678901234567890",
        evidence_id: "TEST_ONLY_" + key,
      },
    ]),
  ) as OperatingDriverBridge["basis"]["baselines"][string]["fields"];
  const baseline = {
    period_basis: "H1",
    scope: "CONSOLIDATED",
    currency: "CNY",
    fields,
    opex_cny: "100",
    other_pretax_cny: "-12",
    pretax_margin: "0.55",
    surcharge_ratio: "0.12",
    evidence_ids: ["TEST_ONLY_EVIDENCE"],
  };
  const inputs = {} as OperatingDriverBridge["inputs"],
    paths = {} as OperatingDriverBridge["paths"];
  for (const name of ["bear", "base", "bull"] as const) {
    const drivers = Object.fromEntries(
      [
        "volume_change",
        "realization_mix_change",
        "unit_cost_change",
        "fixed_cogs_share",
        "opex_change",
        "surcharge_ratio",
        "other_pretax_cny",
      ].map((key) => [key, assumption("-0.02", "0.03")]),
    ) as Record<OperatingDriverKey, ReturnType<typeof assumption>>;
    const corner = {
      revenue_cny: "1234567.1267890123456789",
      cogs_cny: "400000",
      opex_cny: "200000",
      surcharges_cny: "100000",
      other_pretax_cny: "-5000",
      pretax_profit_cny: "529567.126789",
      drivers: { volume_change: "-0.02", realization_mix_change: "0.03" },
    };
    inputs[name] = {
      baseline_period: "2026-H1",
      period_start: "2027-01-01",
      period_end: "2027-06-30",
      drivers,
      capital_assumptions: { investment: "UNKNOWN", funding_access: "UNKNOWN" },
    };
    paths[name] = {
      growth_range: { lower: "-0.1234", upper: "0.2345" },
      margin_range: { lower: "0.41", upper: "0.59" },
      baseline,
      comparison_basis: "TEST_ONLY_SAME_H1_BASELINE",
      extrema: {
        growth_lower: corner,
        growth_upper: { ...corner, revenue_cny: "2345678.129" },
        margin_lower: { ...corner, pretax_profit_cny: "100000" },
        margin_upper: { ...corner, pretax_profit_cny: "900000" },
      },
      limitations: ["TEST_ONLY_LIMITATION"],
      period_start: "2027-01-01",
      period_end: "2027-06-30",
      scope: "CONSOLIDATED",
      period_basis: "H1",
    };
  }
  return {
    version: "TEST_ONLY_DRIVER_V1",
    basis: {
      baselines: { "2026-H1": baseline },
      comparisons: [
        {
          field: "revenue",
          current_period: "2026-H1",
          prior_period: "2025-H1",
          period_basis: "H1",
          current_value: "10472000000",
          prior_value: "16454000000",
          change_ratio: "-0.3635",
          status: "COMPARABLE",
          evidence_ids: ["TEST_ONLY_EVIDENCE"],
        },
      ],
      gaps: ["TEST_ONLY_NO_CHANNEL_VOLUME"],
    },
    inputs,
    paths,
    thresholds: [
      {
        scenario: "base",
        metric: "margin",
        direction: "ABOVE",
        threshold: "0.59",
        period_start: "2027-01-01",
        period_end: "2027-06-30",
        baseline_period: "2026-H1",
        period_basis: "H1",
        scope: "CONSOLIDATED",
        comparison_basis: "TEST_ONLY_SAME_H1_BASELINE",
        meaning: "TEST_ONLY_SAME_BOUNDS_REVIEW",
      },
    ],
  };
}
function visibleDriverHtml(html: string) {
  let depth = 0;
  return html
    .split(/(<\/?details\b[^>]*>)/)
    .map((part) => {
      if (/^<details\b/.test(part)) {
        depth++;
        return "";
      }
      if (/^<\/details\b/.test(part)) {
        depth--;
        return "";
      }
      return depth === 0 ? part : "";
    })
    .join("");
}
it("shows source-period comparisons and each scenario driver inputs, backend paths and cost transmission by default without recomputing", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const bridge = driverBridge(),
    before = JSON.stringify(bridge);
  const html = renderToStaticMarkup(
    <OperatingDriverBridgeView bridge={bridge} />,
  );
  const visible = visibleDriverHtml(html);
  for (const text of [
    "同期间历史比较",
    "2026-H1",
    "2025-H1",
    "-0.3635",
    "2027-01-01",
    "2027-06-30",
    "CONSOLIDATED",
    "10,472,000,000.00",
    "16,454,000,000.00",
    "-0.1234 ～ 0.2345",
    "0.4100 ～ 0.5900",
    "活动量指数变化",
    "实现价与产品组合变化",
    "整体营业成本水平变化（假设）",
    "基期营业成本的非活动量敏感份额（假设）",
    "期间费用变化",
    "税金及附加占收入比率",
    "其他税前残差（元）",
    "TEST_ONLY_DRIVER_REASON",
    "TEST_ONLY_EVIDENCE",
    "1,234,567.13",
    "2,345,678.13",
    "400,000.00",
    "200,000.00",
    "100,000.00",
    "-5,000.00",
    "529,567.13",
    "900,000.00",
    "TEST_ONLY_LIMITATION",
    "同一bounds生成的重审阈值",
    "严格高于",
    "0.5900",
    "TEST_ONLY_SAME_BOUNDS_REVIEW",
  ])
    expect(visible).toContain(text);
  for (const name of [
    "压力条件情景",
    "中间条件情景（未采用主区间）",
    "修复条件情景",
  ])
    expect(visible).toContain(name);
  expect(visible).not.toContain("TEST_ONLY_NO_CHANNEL_VOLUME");
  expect(html).toContain("TEST_ONLY_NO_CHANNEL_VOLUME");
  expect(html).toContain("1234567.1267890123456789");
  expect(html).not.toContain("<details open");
  expect(JSON.stringify(bridge)).toBe(before);
});
it("states conditional index/mix/fixed-share/residual and strict matching-period threshold limits without inventing trigger or valuation", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = visibleDriverHtml(
    renderToStaticMarkup(<OperatingDriverBridgeView bridge={driverBridge()} />),
  );
  for (const text of [
    "活动量指数不是酒吨数",
    "不是纯涨价",
    "固定份额仅为敏感性假设",
    "128角点压力包络不是概率分布",
    "其他税前残差不等于经常性盈利",
    "不是正式净利、股东现金或估值",
    "等于阈值不触发",
    "跨历史基线不等于越界",
    "不判断已触发",
    "各指标极值可能来自不同角点",
    "不将全年与半年拼成同比",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("已触发重审");
  expect(html).not.toContain("经济批准通过");
});
it("consumes the optional bridge on private tasks, public success and partial without promoting any role or E2", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  for (const input of [task(), publicSuccess(), publicPartial()]) {
    const value = {
      ...input,
      operating_driver_bridge: driverBridge(),
      independent_review: {
        status: "REVIEW_REQUIRED_NOT_APPROVAL" as const,
        findings: [
          {
            priority: "P2",
            role: "COUNTER_EVIDENCE" as const,
            claim_index: 2,
            reason:
              "TEST_ONLY经济采用拒绝，经营驱动一致性尚未证明，不能生成买价",
          },
        ],
      },
    };
    const before = JSON.stringify(value);
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={value} />,
    );
    expect(html).toContain("经营驱动与成本传导桥");
    expect(html).toContain("独立复核待处理，不代表批准");
    expect(html).toContain(value.independent_review.findings[0].reason);
    expect(html).toContain("经济主区间未采用");
    expect(html).toContain("正式事实新增 0");
    expect(html).not.toMatch(/建议买价|目标买价|买入价格|已采用主估值/);
    expect(value.condition_price).toBeNull();
    expect(value.personal_quantity).toBeNull();
    expect(value.main_range_adopted).toBe(false);
    expect(value.approval_changed).toBe(false);
    expect(JSON.stringify(value)).toBe(before);
  }
});
it("keeps legacy responses without bridge unchanged and does not pretend they have a driver chain", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  for (const input of [task(), publicSuccess(), publicPartial()]) {
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={input} />,
    );
    expect(html).not.toContain("经营驱动与成本传导桥");
    expect(html).not.toContain("128角点");
  }
});
it("stops malformed bridge summaries and preserves missing numeric inputs rather than filling zero", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const bridge = driverBridge();
  delete (bridge.paths as any).base;
  const html = renderToStaticMarkup(
    <OperatingDriverBridgeView bridge={bridge} />,
  );
  expect(html).toContain("经营驱动桥字段不完整");
  expect(html).not.toContain("后端收入增长区间");
  const missing = driverBridge();
  missing.inputs.base.drivers.volume_change.lower = null;
  missing.paths.base.extrema.margin_lower.cogs_cny = null;
  const view = visibleDriverHtml(
    renderToStaticMarkup(<OperatingDriverBridgeView bridge={missing} />),
  );
  expect(view).toContain("未提供，不补零");
});

it("labels cost-level sensitivity as multiplying all COGS without asserting accounting fixed costs", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const bridge = driverBridge();
  bridge.paths.base.comparison_basis =
    "CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY";
  bridge.thresholds[0].comparison_basis =
    "CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY";
  bridge.thresholds[0].meaning = "REOPEN_RESEARCH_ONLY_NOT_AUTOMATIC_REVISION";
  const html = visibleDriverHtml(
    renderToStaticMarkup(<OperatingDriverBridgeView bridge={bridge} />),
  );
  for (const text of [
    "整体营业成本水平变化（假设）",
    "基期营业成本的非活动量敏感份额（假设）",
    "不是已证实的会计固定成本拆分",
    "成本水平变化作用于固定与活动量敏感份额组成的全部营业成本",
    "相对历史基线的累计变化，不是逐年同比",
    "仅重开研究，不自动修订假设或批准",
    "严格高于",
    "仅原始精确值可用于判断",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("单位变动成本变化");
  expect(html).not.toContain("固定营业成本份额（假设）");
});

it("distinguishes structured driver inputs from code-derived growth and margin counts", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  for (const input of [task(), publicSuccess(), publicPartial()]) {
    const value = {
      ...input,
      operating_driver_bridge: driverBridge(),
      research_completeness: {
        scenario_count: 3,
        numeric_assumption_count: 9,
        unknown_assumption_count: 6,
        status: "REVIEW_REQUIRED" as const,
        economic_validation: "NOT_APPROVED" as const,
        structured_driver_range_count: 21,
        derived_scenario_metric_count: 6,
        numeric_basis:
          "GROWTH_AND_PROFIT_ARE_CODE_DERIVED_NOT_MODEL_ENTERED" as const,
      },
    };
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={value} />,
    );
    expect(html).toContain("21项经营驱动范围");
    expect(html).toContain("6项增长/税前利润率由代码派生，不是模型直接填值");
    expect(html).not.toContain("数值假设数：9");
    expect(html).not.toContain("9个LLM预测");
    expect(html).toContain("经济有效性尚未批准");
  }
});
it("preserves old numeric completeness labels without bridge or optional derivation counts", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const completeness = {
    scenario_count: 3,
    numeric_assumption_count: 9,
    unknown_assumption_count: 6,
    status: "REVIEW_REQUIRED" as const,
    economic_validation: "NOT_APPROVED" as const,
  };
  for (const extra of [{}, { operating_driver_bridge: driverBridge() }]) {
    const value = {
      ...publicSuccess(),
      ...extra,
      research_completeness: completeness,
    };
    const html = renderToStaticMarkup(
      <LiveOperatingResearchDraft task={value} />,
    );
    expect(html).toContain("数值假设数：9");
    expect(html).not.toContain("项经营驱动范围");
    expect(html).not.toContain("由代码派生，不是模型直接填值");
  }
});

it("cash consumption shows new conditional calculation without promoting a buy price", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={task({
        status: "SUCCEEDED",
        cash_consumption: {
          task_id: "TEST_ONLY_CASH_CONSUMPTION",
          consumption_fingerprint: "test-only",
          historical_parent_cash: [
            {
              period: "2026-06-30",
              period_basis: "H1",
              parent_cfo: "100",
              investment_cash: "20",
              gross_cash_capex: "10",
              cash_proxy_cny: "110",
            },
          ],
          current_blockers: [{ code: "MAIN_ECONOMIC_RANGE_NOT_ADOPTED" }],
          annual_followup: {
            status: "CONDITIONAL_STRESS_CONSUMED",
            financial_basis: "2026-06-30",
            rationale: "TEST_ONLY explicit stress, not main value",
            countercase: "TEST_ONLY cash risk",
            input_descriptor_sha256: "test-only",
            valuation: { bear_value: "1", base_value: "2", bull_value: "3" },
            annual_ledgers: {
              base: {
                rows: [
                  {
                    year: 1,
                    period_start: "2026-07-01",
                    period_end: "2027-06-30",
                    profit: "100",
                    accessible_profit: "50",
                    mandatory_cash: "20",
                    distribution: "30",
                    closing_cash: "90",
                    closing_book: "170",
                  },
                ],
              },
            },
          },
        },
      })}
    />,
  );
  expect(html).toContain("条件压力经营");
  expect(html).toContain("股东现金");
  expect(html).toContain("共享估值已接通");
  expect(html).toContain("不是当前合理价值或买价");
  expect(html).toContain("逐年股东现金、分配和权益账");
  expect(html).toContain("2026-07-01");
  expect(html).toContain("主研究区间未采纳");
  expect(html).not.toContain("当前未调用年度估值内核");
  expect(calls.start).not.toHaveBeenCalled();
});
it("cash mapping failure remains readable alongside public operating research", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={task({
        status: "SUCCEEDED",
        research_draft: publicSuccess().research_draft,
        cash_consumption: {
          status: "SOURCE_BOUND_EARNINGS_CONSUMED_CASH_INPUTS_INCOMPLETE",
          annual_followup: {
            status: "UNASSESSABLE",
            reason: "SOURCE_HASH_CHANGED",
          },
        },
      })}
    />,
  );
  expect(html).toContain("SOURCE_HASH_CHANGED");
  expect(html).toContain("经营基本面草案");
  expect(html).not.toContain("共享估值已接通");
});
