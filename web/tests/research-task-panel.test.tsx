import React from "react";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ResearchTaskResponse } from "../src/services/api";

const hooks = vi.hoisted(() => ({ values: [] as any[], cursor: 0 }));
const calls = vi.hoisted(() => ({
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
      createResearchTask: calls.start,
      researchTask: calls.refresh,
      researchTasksForSymbol: calls.history,
      cancelResearchTask: calls.cancel,
      resumeResearchTask: calls.resume,
    },
  };
});
import { ApiError } from "../src/services/api";
import {
  ResearchTaskPanel,
  newResearchTaskRequestKey,
} from "../src/pages/DecisionDetail/ResearchTaskPanel";

function task(
  changes: Partial<ResearchTaskResponse> = {},
): ResearchTaskResponse {
  return {
    task_id: "TEST_ONLY_TASK",
    symbol: "600519",
    workflow: "company_research",
    status: "QUEUED",
    execution_mode: "SAVED_RESPONSE",
    snapshot_status: "VERIFIED",
    checkpoint_verified: false,
    error_code: null,
    attempts: 0,
    provider_requests: 0,
    usage: { prompt_tokens: 0, completion_tokens: 0 },
    usage_basis: "MOCK_PROVIDER_ACCOUNTING_NOT_NEW_LLM_USAGE",
    new_llm_calls: 0,
    record_binding: {
      path: "runtime/TEST_ONLY_TASK/record.json",
      sha256: "a".repeat(64),
    },
    action: "no_order",
    formal_eligibility: false,
    ...changes,
  };
}
function render(symbol = "600519", initialReadError?: string) {
  hooks.cursor = 0;
  return ResearchTaskPanel({ symbol, initialReadError });
}
function nodes(value: any): any[] {
  if (Array.isArray(value)) return value.flatMap(nodes);
  if (!React.isValidElement(value)) return [];
  return [value, ...nodes((value as any).props.children)];
}
function button(tree: any, label: string) {
  const result = nodes(tree).find(
    (node) =>
      node.props.children === label && typeof node.props.onClick === "function",
  );
  expect(result, label).toBeDefined();
  return result;
}
async function click(label: string) {
  const node = button(render(), label);
  expect(node.props.disabled).toBeFalsy();
  await node.props.onClick();
}
function plainText(value: any): string {
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (Array.isArray(value)) return value.map(plainText).join("");
  if (React.isValidElement(value))
    return plainText((value as any).props.children);
  return "";
}
function shown() {
  const tree = render();
  return JSON.stringify(
    nodes(tree).map((node) => ({
      children: plainText(node.props.children),
      message: node.props.message,
      items: node.props.items,
    })),
  );
}

beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  for (const call of Object.values(calls)) call.mockReset();
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("mounts without any task request or polling, behind the unchanged explicit research gate", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const tree = render();
  expect(button(tree, "手动刷新").props.disabled).toBe(true);
  expect(button(tree, "取消任务").props.disabled).toBe(true);
  expect(button(tree, "恢复任务").props.disabled).toBe(true);
  await vi.advanceTimersByTimeAsync(60000);
  for (const call of Object.values(calls)) expect(call).not.toHaveBeenCalled();
  expect(fetcher).not.toHaveBeenCalled();
  const parent = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  expect(parent).toMatch(
    /<OnDemandSection[^>]*label="加载 AI 研究材料">\s*<AgentResearchPanel/,
  );
  const material = readFileSync(
    "src/pages/DecisionDetail/AgentResearchPanel.tsx",
    "utf8",
  );
  expect(material).toContain(
    "<ResearchTaskPanel key={activeSymbol} symbol={activeSymbol}",
  );
  expect(shown()).toContain("不是新的 LLM 调用");
  expect(shown()).toContain("付费调用为 0");
});

it("starts with a unique legacy request and only refreshes, resumes and cancels on explicit clicks", async () => {
  calls.start.mockResolvedValue(task());
  calls.refresh.mockResolvedValue(
    task({
      status: "FAILED",
      error_code: "INTERRUPTED_EXPLICIT_RESUME_REQUIRED",
      attempts: 1,
    }),
  );
  calls.resume.mockResolvedValue(task({ status: "RUNNING", attempts: 2 }));
  calls.cancel.mockResolvedValue(
    task({ status: "CANCELLED", error_code: "USER_CANCELLED" }),
  );
  await click("新增任务");
  expect(calls.start).toHaveBeenCalledWith({
    symbol: "600519",
    workflow: "legacy",
    request_key: expect.stringMatching(/^[A-Za-z0-9_]{8,80}$/),
  });
  expect(calls.refresh).not.toHaveBeenCalled();
  await click("手动刷新");
  expect(calls.refresh).toHaveBeenCalledWith("TEST_ONLY_TASK");
  expect(shown()).toContain("INTERRUPTED_EXPLICIT_RESUME_REQUIRED");
  await click("恢复任务");
  expect(calls.resume).toHaveBeenCalledWith("TEST_ONLY_TASK");
  await click("取消任务");
  expect(calls.cancel).toHaveBeenCalledWith("TEST_ONLY_TASK");
  expect(shown()).toContain("已取消");
  expect(button(render(), "恢复任务").props.disabled).toBe(true);
  expect(calls.refresh).toHaveBeenCalledTimes(1);
  const firstKey = calls.start.mock.calls[0][0].request_key;
  await click("新增任务");
  expect(calls.start.mock.calls[1][0].request_key).not.toBe(firstKey);
});

it("shows verified completion, usage and record binding without granting approval", async () => {
  calls.start.mockResolvedValue(task());
  calls.refresh.mockResolvedValue(
    task({
      status: "SUCCEEDED",
      checkpoint_verified: true,
      finding_count: 3,
      attempts: 1,
      provider_requests: 3,
      usage: { prompt_tokens: 600, completion_tokens: 300 },
    }),
  );
  await click("新增任务");
  await click("手动刷新");
  expect(shown()).toContain("重放完成");
  expect(shown()).toContain("已核验");
  expect(shown()).toContain("输入 600 / 输出 300");
  expect(shown()).toContain("runtime/TEST_ONLY_TASK/record.json");
  expect(shown()).toContain("action=no_order");
  expect(shown()).toContain("非审批");
  expect(button(render(), "取消任务").props.disabled).toBe(true);
});

it("shows one local 401 hint and keeps the task controls and public research boundary intact", async () => {
  calls.start.mockRejectedValue(
    new ApiError(401, "LOCAL_SESSION_LOCKED", "TEST_ONLY"),
  );
  await click("新增任务");
  const tree = render();
  const alerts = nodes(tree).filter(
    (node) => typeof node.props.message === "string",
  );
  expect(alerts).toHaveLength(1);
  expect(alerts[0].props.message).toContain("本机授权");
  expect(alerts[0].props.message).toContain("公开研究仍可查看");
  expect(tree.type).toBe("section");
  expect(button(tree, "新增任务").props.disabled).toBe(false);
  expect(calls.refresh).not.toHaveBeenCalled();
});

it("does not accept another issuer or a response that claims new model calls", async () => {
  calls.start.mockResolvedValueOnce(task({ symbol: "600887" }));
  await click("新增任务");
  expect(button(render(), "手动刷新").props.disabled).toBe(true);
  calls.start.mockResolvedValueOnce({ ...task(), new_llm_calls: 1 });
  await click("新增任务");
  expect(button(render(), "手动刷新").props.disabled).toBe(true);
  expect(shown()).toContain("响应无法核验");
});

it("blocks double dispatch while the create response is pending", async () => {
  let finish!: (value: ResearchTaskResponse) => void;
  calls.start.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const node = button(render(), "新增任务");
  const pending = node.props.onClick();
  await node.props.onClick();
  expect(calls.start).toHaveBeenCalledTimes(1);
  finish(task());
  await pending;
  expect(shown()).toContain("TEST_ONLY_TASK");
});

it("uses crypto-only bounded request keys and hides an old symbol's task", async () => {
  const keys = new Set(Array.from({ length: 20 }, newResearchTaskRequestKey));
  expect(keys.size).toBe(20);
  for (const key of keys) expect(key).toMatch(/^[A-Za-z0-9_]{8,80}$/);
  calls.start.mockResolvedValue(task());
  await click("新增任务");
  const changed = render("600887");
  expect(button(changed, "手动刷新").props.disabled).toBe(true);
  expect(calls.refresh).not.toHaveBeenCalled();
});

it("discovers persisted tasks only on click after a page-state reset and reuses the selected task controls", async () => {
  calls.start.mockResolvedValue(task());
  await click("新增任务");
  // A fresh component instance has no selected task, just like a page reload.
  hooks.values = [];
  expect(button(render(), "手动刷新").props.disabled).toBe(true);
  expect(calls.history).not.toHaveBeenCalled();
  calls.history.mockResolvedValue({
    action: "no_order",
    symbol: "600519",
    scope: "BOUNDED_TASK_HISTORY",
    items: [
      task({
        status: "FAILED",
        error_code: "INTERRUPTED_EXPLICIT_RESUME_REQUIRED",
      }),
    ],
  });
  await click("读取已有任务");
  expect(calls.history).toHaveBeenCalledWith("600519");
  expect(calls.refresh).not.toHaveBeenCalled();
  await click("选取任务 TEST_ONLY_TASK");
  expect(button(render(), "手动刷新").props.disabled).toBe(false);
  calls.resume.mockResolvedValue(task({ status: "RUNNING", attempts: 2 }));
  await click("恢复任务");
  expect(calls.resume).toHaveBeenCalledWith("TEST_ONLY_TASK");
  expect(calls.start).toHaveBeenCalledTimes(1);
  expect(calls.history).toHaveBeenCalledTimes(1);
});

it("bounds the history and refuses bad or wrong-issuer task entries without hiding valid failed tasks", async () => {
  calls.history.mockResolvedValue({
    action: "no_order",
    symbol: "600519",
    scope: "BOUNDED_TASK_HISTORY",
    items: [
      task({ status: "FAILED", error_code: "CHECKPOINT_VALIDATION_FAILED" }),
      null,
      { task_id: "BAD_ONLY", status: "CORRUPTED" },
      task({ symbol: "600887" }),
      ...Array.from({ length: 20 }, (_, index) =>
        task({ task_id: "TEST_MORE_" + index }),
      ),
    ],
  });
  await click("读取已有任务");
  const tree = render();
  expect(nodes(tree).filter((node) => node.type === "li")).toHaveLength(20);
  expect(shown()).toContain("任务记录无法核验");
  expect(shown()).toContain("CHECKPOINT_VALIDATION_FAILED");
  expect(shown()).not.toContain("TEST_MORE_19");
  await click("选取任务 TEST_ONLY_TASK");
  expect(button(render(), "恢复任务").props.disabled).toBe(false);
  expect(calls.refresh).not.toHaveBeenCalled();
});

it("history 401 stays local and a wrong company envelope never supplies selectable tasks", async () => {
  calls.history.mockRejectedValueOnce(
    new ApiError(401, "LOCAL_SESSION_LOCKED", "TEST_ONLY"),
  );
  await click("读取已有任务");
  expect(
    nodes(render()).filter((node) => typeof node.props.message === "string"),
  ).toHaveLength(1);
  expect(shown()).toContain("公开研究仍可查看");
  calls.history.mockResolvedValueOnce({
    action: "no_order",
    symbol: "600887",
    scope: "BOUNDED_TASK_HISTORY",
    items: [task()],
  });
  await click("读取已有任务");
  expect(shown()).toContain("响应无法核验");
  expect(button(render(), "手动刷新").props.disabled).toBe(true);
  expect(calls.refresh).not.toHaveBeenCalled();
});

it("keeps controls after an initial read failure and replaces that hint with one local operation error", async () => {
  const initialReadError = "TEST_ONLY 初始研究读取失败";
  const initial = render("600519", initialReadError);
  const initialAlerts = nodes(initial).filter(
    (node) => typeof node.props.message === "string",
  );
  expect(initialAlerts).toHaveLength(1);
  expect(initialAlerts[0].props.message).toBe(initialReadError);
  expect(button(initial, "新增任务").props.disabled).toBe(false);
  expect(button(initial, "读取已有任务").props.disabled).toBe(false);
  for (const call of Object.values(calls)) expect(call).not.toHaveBeenCalled();
  calls.start.mockRejectedValue(
    new ApiError(401, "LOCAL_SESSION_LOCKED", "TEST_ONLY"),
  );
  await button(initial, "新增任务").props.onClick();
  const next = render("600519", initialReadError);
  const nextAlerts = nodes(next).filter(
    (node) => typeof node.props.message === "string",
  );
  expect(nextAlerts).toHaveLength(1);
  expect(nextAlerts[0].props.message).toContain("公开研究仍可查看");
  expect(nextAlerts[0].props.message).not.toContain(initialReadError);
  expect(button(next, "新增任务").props.disabled).toBe(false);
  expect(button(next, "读取已有任务").props.disabled).toBe(false);
  expect(calls.history).not.toHaveBeenCalled();
  expect(calls.refresh).not.toHaveBeenCalled();
});
