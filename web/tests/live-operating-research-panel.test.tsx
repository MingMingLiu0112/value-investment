import { OperatingCashConsumptionView } from "../src/components/LiveOperatingResearchPanel";
import React from "react";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type {
  LiveOperatingResearchTask,
  OperatingDriverBridge,
  OperatingDriverKey,
  CurrentCapitalObservation,
  FiscalDistributionReview,
} from "../src/services/api";

const hooks = vi.hoisted(() => ({
  values: [] as any[],
  cursor: 0,
  effects: [] as { deps?: unknown[]; cleanup?: () => void }[],
}));
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
    useEffect(effect: () => void | (() => void), deps: unknown[]) {
      const index = hooks.cursor++;
      const previous = hooks.effects[index];
      if (previous && deps.every((v, i) => Object.is(v, previous.deps?.[i])))
        return;
      previous?.cleanup?.();
      hooks.effects[index] = { deps, cleanup: effect() || undefined };
    },
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
  CurrentCapitalObservationView,
  FiscalDistributionReviewView,
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
  for (const effect of hooks.effects) effect?.cleanup?.();
  hooks.effects = [];
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
afterEach(() => {
  for (const effect of hooks.effects) effect?.cleanup?.();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

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
  expect(button("恢复当前任务").props.disabled).toBeTruthy();
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
  calls.history.mockResolvedValue({ items: [task({ status: "FAILED" })] });
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
it("tracks selected running task and stops after terminal response without a model call", async () => {
  vi.useFakeTimers();
  await click("新Agent经营研究");
  calls.history.mockResolvedValue({ items: [task({ status: "RUNNING" })] });
  await click("读取已有经营研究任务");
  calls.refresh.mockResolvedValue(task({ status: "SUCCEEDED" }));
  render();
  await vi.advanceTimersByTimeAsync(3000);
  render();
  await vi.advanceTimersByTimeAsync(9000);
  expect(calls.refresh).toHaveBeenCalledTimes(1);
  expect(calls.start).not.toHaveBeenCalled();
  expect(calls.resume).not.toHaveBeenCalled();
});
it("pauses polling on authorization failure and preserves task for manual refresh", async () => {
  vi.useFakeTimers();
  await click("新Agent经营研究");
  calls.history.mockResolvedValue({ items: [task({ status: "RUNNING" })] });
  await click("读取已有经营研究任务");
  calls.refresh.mockRejectedValue(
    new ApiError(401, "AUTH_REQUIRED", "TEST_ONLY"),
  );
  render();
  await vi.advanceTimersByTimeAsync(3000);
  expect(shown()).toContain("自动读取已暂停");
  await vi.advanceTimersByTimeAsync(9000);
  expect(calls.refresh).toHaveBeenCalledTimes(1);
  expect(button("刷新当前任务").props.disabled).toBeFalsy();
});
it("retries a publishing lock without marking the task missing", async () => {
  vi.useFakeTimers();
  await click("新Agent经营研究");
  calls.history.mockResolvedValue({ items: [task({ status: "RUNNING" })] });
  await click("读取已有经营研究任务");
  calls.refresh
    .mockRejectedValueOnce(new ApiError(503, "LIVE_STATE_BUSY", "TEST_ONLY"))
    .mockResolvedValue(task({ status: "SUCCEEDED" }));
  render();
  await vi.advanceTimersByTimeAsync(3000);
  expect(shown()).not.toContain("自动读取已暂停");
  await vi.advanceTimersByTimeAsync(3000);
  render();
  expect(calls.refresh).toHaveBeenCalledTimes(2);
  expect(calls.start).not.toHaveBeenCalled();
});
it("does not block task controls on a slow economic replay", async () => {
  calls.publicRead.mockReturnValue(new Promise(() => {}));
  await click("新Agent经营研究");
  expect(button("启动新研究").props.disabled).toBeFalsy();
  expect(button("读取已有经营研究任务").props.disabled).toBeFalsy();
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
  // Active-task GET polling is allowed; never use intervals or local state as
  // the authority for durable task execution.
  expect(panel).not.toMatch(/setInterval|localStorage/);
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
it("shows a compiled full year and missing horizon without inventing a cash path", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={task({
        status: "SUCCEEDED",
        cash_consumption: {
          earnings_input_compilation: {
            scenarios: {
              base: {
                period_start: "2027-01-01",
                period_end: "2027-12-31",
                model_year: 2,
                candidates: { margin_lower: {} },
                missing_calendar_years: [2026, 2028],
              },
            },
          },
          current_blockers: [
            { code: "COMPLETE_TEN_YEAR_OPERATING_PATH_REQUIRED" },
          ],
        },
      })}
    />,
  );
  expect(html).toContain("完整年度输入已编译，尚未选择主预测");
  expect(html).toContain("2026、2028");
  expect(html).toContain("不能把一年复制十次");
  expect(html).not.toContain("当前是2027H1");
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

function capitalObservation(): CurrentCapitalObservation {
  return {
    schema_version: "current-capital-observations-v1",
    symbol: "600519",
    status: "VERIFIED",
    action: "no_order",
    formal_eligibility: false,
    current_capital_continuity: "NOT_PROVEN",
    source_bound_observations: [
      {
        source_index: 0,
        status: "VERIFIED",
        source_id: "TEST_ONLY_SOURCE",
        source: {
          path: "runtime/TEST_ONLY.pdf",
          sha256: "c".repeat(64),
          source_url:
            "https://static.cninfo.com.cn/finalpage/2026-08-29/123456789.PDF",
          available_at: "2026-08-29T10:00:00+08:00",
          report_period: "2026-06-30",
          kind: "interim",
        },
        observation: {
          status: "VERIFIED",
          symbol: "600519",
          issuer_name: "TEST_ONLY_ISSUER",
          report_period: "2026-06-30",
          ordinary_shares: "1470000000",
          shares_before: "1471000000",
          cancelled_shares: "1000000",
          cancellation_date: "2026-05-10",
          cancellation_state:
            "REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED_BY_PERIOD_END",
          report_approved_date: "2026-08-28",
          declared_ordinary_dividend_cny: "8000000000",
          dividend_fiscal_year: "2025",
          interim_proposal_state:
            "REPORTED_NO_INTERIM_DIVIDEND_OR_CAPITALIZATION_PLANNED",
          payment_completion_state: "UNKNOWN",
          dividend_policy: {
            status: "VERIFIED",
            policies: [
              {
                fiscal_year: 2026,
                minimum_payout_ratio: "0.70",
                minimum_distribution_cny: "8500000000",
                currency: "CNY",
                scope: "consolidated_parent",
              },
            ],
          },
          evidence_refs: [
            {
              field: "ordinary_shares",
              physical_page: 99,
              excerpt: "TEST_ONLY_ORIGINAL_EXCERPT",
            },
          ],
        },
      },
    ],
    source_results: [],
    current_financial_coverage: {
      status: "REGISTERED_SOURCES_ONLY",
      report_periods: ["2026-06-30", "2026-09-30"],
      latest_report_period: "2026-09-30",
      complete_current_coverage: false,
    },
  };
}
function fiscalReview(): FiscalDistributionReview {
  const row = {
    status: "CONDITIONAL_FISCAL_POLICY_DIAGNOSTIC" as const,
    fiscal_year: 2026,
    reported_h1_parent_profit_cny: "3000000000",
    assumed_h2_parent_profit_cny: "2000000000",
    conditional_fy_parent_profit_cny: "5000000000",
    ratio_target_cny: "3500000000",
    disclosed_floor_cny: "8500000000",
    policy_target_cny: "8500000000",
    target_above_current_year_positive_earnings_cny: "3500000000",
    dominant_constraint: "ABSOLUTE_FLOOR" as const,
    funding_status: "NOT_ASSESSED" as const,
    payment_status: "NOT_ASSESSED" as const,
    policy_compliance: "NOT_ASSESSED" as const,
  };
  return {
    schema_version: "operating-distribution-review-v1",
    symbol: "600519",
    status: "SOURCE_BOUND_FISCAL_POLICY_REVIEW",
    action: "no_order",
    formal_eligibility: false,
    main_range_adopted: false,
    condition_price: null,
    personal_quantity: null,
    financial_basis: "2026-06-30",
    scenarios: { bear: { ...row }, base: { ...row }, bull: { ...row } },
    source_binding: [capitalObservation().source_bound_observations![0].source],
    review_fingerprint: "d".repeat(64),
    fiscal_payment_alignment: "NOT_ASSESSED",
    current_observations: capitalObservation(),
    financial_update_review: {
      status: "NEWER_REPORT_REQUIRES_MODEL_REVALIDATION",
      model_financial_basis: "2026-06-30",
      latest_registered_report_period: "2026-09-30",
      current_model_validity: "NOT_GRANTED",
    },
    limitations: ["TEST_ONLY_FISCAL_LIMITATION"],
  };
}
it("shows source report/availability dates and share quantities while distinguishing a dividend scheme from payment", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = capitalObservation(),
    before = JSON.stringify(value);
  const html = renderToStaticMarkup(
    <CurrentCapitalObservationView value={value} symbol="600519" />,
  );
  const visible = visibleDriverHtml(html);
  for (const text of [
    "2026-06-30",
    "2026-08-29",
    "2026-08-29T10:00:00+08:00",
    "2026-08-28",
    "1,470,000,000",
    "1,000,000",
    "方案归属财政年度：2025",
    "80.0000",
    "2026财政年度",
    "85.0000",
    "这是方案金额，不是已付款金额",
    "实际付款完成：未知，不能推定",
    "拟不进行中期现金分红",
    "不等于全年政策取消",
    "当前资本连续性：尚未证明",
    "不使用人民币股本金额换算股数",
    "不授予当前价格资格",
  ])
    expect(visible).toContain(text);
  expect(visible).not.toContain("TEST_ONLY_ORIGINAL_EXCERPT");
  expect(html).toContain("TEST_ONLY_ORIGINAL_EXCERPT");
  expect(html).toContain(
    'href="https://static.cninfo.com.cn/finalpage/2026-08-29/123456789.PDF"',
  );
  expect(JSON.stringify(value)).toBe(before);
});
it("preserves verified capital sources alongside explicit partial failure and never fills unknown share quantity from monetary capital", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = capitalObservation();
  value.status = "PARTIAL";
  value.source_results = [
    {
      source_index: 1,
      status: "UNASSESSABLE",
      error_code: "TEST_ONLY_ORIGINAL_HASH_MISMATCH",
    },
  ];
  value.source_bound_observations![0].observation.ordinary_shares = "UNKNOWN";
  const html = renderToStaticMarkup(
    <CurrentCapitalObservationView value={value} symbol="600519" />,
  );
  expect(html).toContain("仅部分原件通过");
  expect(html).toContain("TEST_ONLY_ORIGINAL_HASH_MISMATCH");
  expect(html).toContain("2026-08-29");
  expect(html).toContain("未提供，不补零");
  expect(html).not.toContain("1,470,000,000");
});
it("shows fiscal H1 fact plus exact-derived H2 and CNY-8.5-billion policy target without calling excess earnings a cash deficit or default", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = fiscalReview(),
    before = JSON.stringify(value);
  const visible = visibleDriverHtml(
    renderToStaticMarkup(
      <FiscalDistributionReviewView value={value} symbol="600519" />,
    ),
  );
  for (const text of [
    "H1实际与H2条件派生",
    "2026",
    "30.0000",
    "20.0000",
    "50.0000",
    "85.0000",
    "35.0000",
    "滚动首年减同一2027H1 witness",
    "不是另设一份利润预测",
    "不把2026H2+2027H1滚动年度套用财政年度政策下限",
    "不是资金缺口，不证明违约",
    "资金能力：未评估",
    "实际付款：未评估",
    "政策履约：未评估",
    "财政年度付款归属对齐：未评估",
    "已登记更新财报，模型当前使用需重验",
    "2026-09-30",
    "主研究区间未采用",
    "不生成条件价",
  ])
    expect(visible).toContain(text);
  expect(visible).not.toContain("TEST_ONLY_FISCAL_LIMITATION");
  expect(JSON.stringify(value)).toBe(before);
});
it("shows capital and fiscal public supplements while locked, without requesting private tasks or new model calls", async () => {
  calls.status.mockResolvedValue({
    status: "MODEL_AUTHORIZATION_REQUIRED",
    model_id: null,
  });
  calls.publicRead.mockResolvedValue({
    ...publicSuccess(),
    current_capital_observation: capitalObservation(),
    fiscal_distribution_review: fiscalReview(),
  });
  await click("新Agent经营研究");
  const shownValue = shown();
  expect(shownValue).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(shownValue).toContain("current_capital_observation");
  expect(shownValue).toContain("fiscal_distribution_review");
  expect(calls.publicRead).toHaveBeenCalledTimes(1);
  for (const call of [
    calls.start,
    calls.history,
    calls.refresh,
    calls.cancel,
    calls.resume,
  ])
    expect(call).not.toHaveBeenCalled();
});
it("isolates failed observation/fiscal diagnostics without hiding existing operating or cash results, and reuses nested observations once", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = {
    ...publicSuccess(),
    current_capital_observation: {
      status: "UNASSESSABLE" as const,
      action: "no_order" as const,
      formal_eligibility: false as const,
      reason: "TEST_ONLY_BAD_ORIGINAL",
    },
    fiscal_distribution_review: {
      status: "UNASSESSABLE" as const,
      action: "no_order" as const,
      formal_eligibility: false as const,
      reason: "TEST_ONLY_FISCAL_PERIOD_FAILURE",
    },
    cash_consumption: {
      status: "SOURCE_BOUND_EARNINGS_CONSUMED_CASH_INPUTS_INCOMPLETE",
      annual_followup: {
        status: "UNASSESSABLE",
        reason: "TEST_ONLY_CASH_REMAINS",
      },
    },
  };
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={value} symbol="600519" />,
  );
  for (const text of [
    "TEST_ONLY_BAD_ORIGINAL",
    "TEST_ONLY_FISCAL_PERIOD_FAILURE",
    "TEST_ONLY_PUBLIC_BUSINESS",
    "TEST_ONLY_CASH_REMAINS",
  ])
    expect(html).toContain(text);
  const nested = renderToStaticMarkup(
    <LiveOperatingResearchDraft
      task={{ ...publicSuccess(), fiscal_distribution_review: fiscalReview() }}
    />,
  );
  expect(
    (nested.match(/aria-label="来源绑定的公开资本观察"/g) || []).length,
  ).toBe(1);
});
it("stops mismatched identity/hash and fiscal basis locally without showing unverified figures", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const observation = capitalObservation();
  observation.source_bound_observations![0].source.sha256 = "broken";
  const html = renderToStaticMarkup(
    <CurrentCapitalObservationView value={observation} symbol="600519" />,
  );
  expect(html).toContain("Hash绑定不符");
  expect(html).not.toContain("1,470,000,000");
  const fiscal = fiscalReview();
  fiscal.scenarios!.base!.fiscal_year = 2027;
  const invalid = renderToStaticMarkup(
    <FiscalDistributionReviewView value={fiscal} symbol="600519" />,
  );
  expect(invalid).toContain("财政年度政策诊断暂不可核验");
  expect(invalid).not.toContain("85.0000");
  expect(
    renderToStaticMarkup(
      <CurrentCapitalObservationView
        value={capitalObservation()}
        symbol="600887"
      />,
    ),
  ).toContain("身份或边界不符");
});
it("keeps old public responses without the optional observations or fiscal fields unchanged", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView value={publicSuccess()} symbol="600519" />,
  );
  expect(html).toContain("TEST_ONLY_PUBLIC_BUSINESS");
  expect(html).not.toContain("公开资本与分配观察");
  expect(html).not.toContain("财政年度政策目标与利润诊断");
});

it("shows actual implementation and unlock notice schedules as source observations, never account payment or new cancellation", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = capitalObservation();
  const row = value.source_bound_observations![0];
  row.observation.kind = "dividend_implementation";
  row.observation.record_date = "2026-07-01";
  row.observation.ex_date = "2026-07-02";
  row.observation.agency_payment_date = "2026-07-02";
  row.observation.observation_date = "2026-06-26";
  row.observation.distribution_base_shares = "1460000000";
  row.observation.excluded_repurchase_shares = "10000000";
  row.observation.dividend_per_10_shares_cny = "55.00";
  row.observation.share_effective_date = "2026-09-10";
  row.observation.share_observation_state =
    "SCHEDULED_CLASS_TRANSFER_SUBJECT_TO_CSDC_STRUCTURE";
  row.observation.historical_cancelled_shares = "1000000";
  row.observation.historical_cancellation_date = "2026-05-10";
  row.observation.share_table_qualification = "TEST_ONLY中国结算结构表为准";
  const html = renderToStaticMarkup(
    <CurrentCapitalObservationView value={value} symbol="600519" />,
  );
  for (const text of [
    "分红派息实施公告",
    "分红实施安排（不是到账证明）",
    "2026-07-01",
    "2026-07-02",
    "2026-06-26",
    "1,460,000,000",
    "10,000,000",
    "55.00",
    "不等于账户到账",
    "不能算入另一年度政策目标",
    "2026-09-10",
    "拟解除限售的股份类别转移",
    "不是新增注销",
    "TEST_ONLY中国结算结构表为准",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("已完成付款");
});
it("shows Q3 year-to-date facts separately from the frozen H1 model and works with report_kind alias", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = capitalObservation(),
    row = value.source_bound_observations![0];
  row.source.report_period = "2026-09-30";
  row.observation.report_period = "2026-09-30";
  row.observation.report_kind = "q3";
  delete row.observation.kind;
  row.observation.financial_update = {
    status: "VERIFIED",
    period_start: "2026-01-01",
    period_end: "2026-09-30",
    period_basis: "YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER",
    fields: {
      revenue_cny: {
        value: "10000000000",
        unit: "CNY",
        scope: "consolidated",
        physical_page: 2,
        excerpt: "TEST_ONLY_Q3_REVENUE",
      },
      parent_profit_cny: {
        value: "4000000000",
        unit: "CNY",
        scope: "consolidated_parent",
        physical_page: 2,
        excerpt: "TEST_ONLY_Q3_PROFIT",
      },
    },
  };
  const html = renderToStaticMarkup(
    <CurrentCapitalObservationView value={value} symbol="600519" />,
  );
  for (const text of [
    "第三季度报告",
    "后续财报实际观察",
    "2026-01-01",
    "2026-09-30",
    "年初累计九个月，不是第三季度单季，也不是全年",
    "100.0000",
    "40.0000",
    "不自动覆盖原研究或授予当前价格资格",
  ])
    expect(html).toContain(text);
});

function q3FiscalReview(): FiscalDistributionReview {
  const value = fiscalReview();
  value.scenarios!.base!.conditional_fy_parent_profit_cny = "5392390000";
  value.financial_update_review!.comparison_source = {
    ...value.source_binding![0],
    report_period: "2026-09-30",
    source_url:
      "https://static.cninfo.com.cn/finalpage/2026-10-30/123456790.PDF",
    available_at: "2026-10-30T09:00:00+08:00",
  };
  value.financial_update_review!.comparisons = {
    base: {
      status: "ACTUAL_UPDATE_COMPARED_WITH_FROZEN_CONDITIONAL_PATH",
      fiscal_year: 2026,
      reported_ytd_parent_profit_cny: "5671060000",
      unchanged_conditional_fy_parent_profit_cny: "5392390000",
      implied_q4_parent_profit_cny: "-278670000",
      implied_q4_start: "2026-10-01",
      implied_q4_end: "2026-12-31",
      implication: "IMPLIED_Q4_LOSS_REQUIRES_EXPLICIT_REVIEW",
      model_revalidated: false,
      action: "no_order",
      formal_eligibility: false,
      condition_price: null,
      source_anchor: {
        value: "5671060000",
        scope: "consolidated_parent",
        unit: "CNY",
        physical_page: 2,
        excerpt: "TEST_ONLY_ACTUAL_YTD_ANCHOR",
      },
    },
  };
  return value;
}
it("compares Q3 actual with unchanged conditional FY as an implied Q4 requirement rather than a realised loss, new forecast or rejection", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = q3FiscalReview(),
    before = JSON.stringify(value);
  const html = renderToStaticMarkup(
    <FiscalDistributionReviewView value={value} symbol="600519" />,
  );
  const visible = visibleDriverHtml(html);
  for (const text of [
    "Q3累计实际对原条件全年值的隐含要求",
    "56.7106",
    "53.9239",
    "-2.7867",
    "2026-10-01",
    "2026-12-31",
    "不是已发生亏损或新预测",
    "不自动拒绝或改值",
    "隐含Q4亏损要求，须显式复核",
    "模型尚未重验",
    "2026-10-30T09:00:00+08:00",
    "政策目标超过当年正利润金额",
  ])
    expect(visible).toContain(text);
  expect(html).toContain("TEST_ONLY_ACTUAL_YTD_ANCHOR");
  expect(visible).not.toContain("TEST_ONLY_ACTUAL_YTD_ANCHOR");
  expect(JSON.stringify(value)).toBe(before);
});
it("renders a nonnegative implied Q4 requirement honestly and keeps older fiscal responses without comparisons compatible", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = q3FiscalReview(),
    row = value.financial_update_review!.comparisons!.base!;
  row.implied_q4_parent_profit_cny = "0";
  row.implication = "IMPLIED_Q4_PROFIT_REQUIRES_EXPLICIT_REVIEW";
  const html = renderToStaticMarkup(
    <FiscalDistributionReviewView value={value} symbol="600519" />,
  );
  expect(html).toContain("隐含Q4非负利润要求，仍须复核");
  expect(html).toContain("0.0000");
  const old = renderToStaticMarkup(
    <FiscalDistributionReviewView value={fiscalReview()} symbol="600519" />,
  );
  expect(old).not.toContain("Q3累计实际对原条件全年值的隐含要求");
  expect(old).toContain("当年政策目标");
});
it("isolates unverified Q3 comparison binding without hiding fiscal policy diagnostics or promoting current model validity", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = q3FiscalReview();
  value.financial_update_review!.comparison_source!.sha256 = "broken";
  const html = renderToStaticMarkup(
    <FiscalDistributionReviewView value={value} symbol="600519" />,
  );
  expect(html).toContain("Q3比较来源或期间未核验，仅本表不展示");
  expect(html).not.toContain("-2.7867");
  expect(html).toContain("85.0000");
  expect(html).toContain("实际付款：未评估");
  expect(html).toContain("模型当前使用需重验");
});

it("shows annual supplement as an estimate without upgrading cash or approval", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const value = {
    status: "PARTIAL",
    annual_research_supplement: {
      status: "ANNUAL_SUPPLEMENT_COMPILED_NOT_CASH_POLICY",
      task_id: "TEST_ONLY_SUPPLEMENT",
      research_as_of: "2026-11-05T04:00:00Z",
      years: {
        "2026": {
          estimate_kind: "CURRENT_FY_ESTIMATE",
          counter_evidence: "特许期可能终止",
          reopen_condition: "正式续期公告",
          earnings: {
            base: {
              witnesses: {
                growth_lower: { parent_profit_cny: "100.00" },
              },
            },
          },
        },
      },
    },
  };
  const html = renderToStaticMarkup(
    <OperatingCashConsumptionView value={value} />,
  );
  expect(html).toContain("当年全年估计");
  expect(html).toContain("非实际财报");
  expect(html).toContain("100.00");
  expect(html).toContain("特许期可能终止");
  expect(html).toContain("不等同可分配现金或主估值");
  expect(html).toContain("action=no_order");
});
