import React from "react";
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import type {
  ValueWorkbenchTask,
  PreparedWorkbenchOperation,
} from "../src/services/api";
const hooks = vi.hoisted(() => ({ values: [] as any[], cursor: 0 }));
const calls = vi.hoisted(() => ({
  start: vi.fn(),
  list: vi.fn(),
  read: vi.fn(),
  control: vi.fn(),
  history: vi.fn(),
  prepare: vi.fn(),
}));
vi.mock("react", async (original) => {
  const actual = await original<typeof import("react")>();
  return {
    ...actual,
    useEffect: vi.fn(),
    useState(initial: any) {
      const i = hooks.cursor++;
      if (!(i in hooks.values))
        hooks.values[i] = typeof initial === "function" ? initial() : initial;
      return [
        hooks.values[i],
        (next: any) => {
          hooks.values[i] =
            typeof next === "function" ? next(hooks.values[i]) : next;
        },
      ];
    },
    useRef(initial: any) {
      const i = hooks.cursor++;
      if (!(i in hooks.values)) hooks.values[i] = { current: initial };
      return hooks.values[i];
    },
  };
});
vi.mock("../src/services/api", async (original) => {
  const actual = await original<typeof import("../src/services/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      createValueWorkbenchTask: calls.start,
      valueWorkbenchTasks: calls.list,
      valueWorkbenchTask: calls.read,
      controlValueWorkbenchTask: calls.control,
      valueWorkbenchTaskHistory: calls.history,
      valueWorkbenchTaskInputs: calls.prepare,
    },
  };
});
import { ApiError } from "../src/services/api";
import {
  TransparentTaskControls,
  watchWorkbenchTask,
  preparedTaskPayload,
  TaskRunFeedback,
} from "../src/components/TransparentTaskControls";
const binding = { path: "TEST_ONLY_PUBLIC_ARTIFACT", sha256: "c".repeat(64) };
function preparedRows(): PreparedWorkbenchOperation[] {
  return [
    [
      "B",
      "FRESH_PUBLIC_SCAN",
      { network_authorized: false, max_per_channel: 50 },
    ],
    [
      "B",
      "REPLAY_SELECTION",
      { manifest_binding: binding, evaluation_at: "TEST_ONLY_TIME", limit: 50 },
    ],
    [
      "F1",
      "RECALCULATE_MAIN",
      { registry_binding: binding, spec_binding: binding },
    ],
    [
      "F1",
      "SIMULATE_ASSUMPTIONS",
      {
        registry_binding: binding,
        spec_binding: binding,
        scenario: "base",
        changes: [],
        rationale: "",
      },
    ],
    ["A", "VERIFY_EVIDENCE", { bundle_binding: binding }],
    ["G2", "REVIEW_NOTE", { target_binding: binding, opinion: "" }],
  ].map(([module_id, operation, payload]) => ({
    module_id: String(module_id),
    operation: String(operation),
    prepared_payload: payload as Record<string, unknown>,
    enabled: true,
    user_fields: [],
    network_authorization_required: operation === "FRESH_PUBLIC_SCAN",
  }));
}
const ID = "rt-" + "a".repeat(32),
  CHILD = "rt-" + "b".repeat(32);
function task(change: Partial<ValueWorkbenchTask> = {}): ValueWorkbenchTask {
  return {
    retry_allowed: ["FAILED", "BLOCKED", "CANCELLED"].includes(
      change.status || "QUEUED",
    ),
    task_id: ID,
    symbol: "000568",
    status: "QUEUED",
    operation: "FRESH_PUBLIC_SCAN",
    action: "no_order",
    formal_eligibility: false,
    new_llm_calls: 0,
    native_metadata: {
      schema_version: "transparent-task-v1",
      new_llm_calls: 0,
      approval_changed: false,
      execution: "NATIVE_ORIGIN_SERVICE",
    },
    completed_steps: 0,
    total_steps: 3,
    ...change,
  };
}
function render() {
  hooks.cursor = 0;
  return TransparentTaskControls({ symbol: "000568" });
}
function nodes(v: any): any[] {
  return Array.isArray(v)
    ? v.flatMap(nodes)
    : React.isValidElement(v)
      ? [v, ...nodes((v as any).props.children)]
      : [];
}
function button(label: string) {
  const n = nodes(render()).find(
    (n) => n.props.children === label && typeof n.props.onClick === "function",
  );
  expect(n, label).toBeDefined();
  return n;
}
async function click(label: string) {
  const n = button(label);
  expect(n.props.disabled).toBeFalsy();
  await n.props.onClick();
}
function authorize() {
  nodes(render())
    .find((n) => n.props.type === "checkbox")
    .props.onChange({ target: { checked: true } });
}
async function select(status = "FAILED", resume_required = false) {
  calls.list.mockResolvedValue({
    symbol: "000568",
    action: "no_order",
    formal_eligibility: false,
    items: [task({ status, resume_required })],
  });
  await click("读取任务列表");
  const n = nodes(render()).find(
    (n) =>
      typeof n.props.onClick === "function" &&
      Array.isArray(n.props.children) &&
      n.props.children.includes(ID),
  );
  expect(n).toBeDefined();
  n.props.onClick();
}
beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  for (const call of Object.values(calls)) call.mockReset();
  vi.stubGlobal("crypto", webcrypto);
  calls.prepare.mockResolvedValue({
    symbol: "000568",
    action: "no_order",
    formal_eligibility: false,
    tasks_started: 0,
    operations: preparedRows(),
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it("does not request on mount and requires explicit network authorization for a fresh public task", async () => {
  vi.useFakeTimers();
  render();
  await vi.advanceTimersByTimeAsync(30000);
  for (const call of Object.values(calls)) expect(call).not.toHaveBeenCalled();
  const n = button("执行所选操作");
  expect(n.props.disabled).toBe(true);
  await n.props.onClick();
  expect(calls.start).not.toHaveBeenCalled();
});
it("posts the actual route/native payload only once for duplicate clicks", async () => {
  await click("读取可执行操作与绑定");
  authorize();
  let complete!: (v: any) => void;
  calls.start.mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const n = button("执行所选操作");
  const first = n.props.onClick();
  await n.props.onClick();
  expect(calls.start).toHaveBeenCalledTimes(1);
  expect(calls.start.mock.calls[0][0]).toMatchObject({
    module_id: "B",
    operation: "FRESH_PUBLIC_SCAN",
    symbol: "000568",
    payload: { network_authorized: true, max_per_channel: 10 },
  });
  expect(calls.start.mock.calls[0][0].request_key).toMatch(
    /^[A-Za-z0-9_]{8,80}$/,
  );
  complete(task());
  await first;
  expect(JSON.stringify(render())).toContain(ID);
});
it("reads history and existing task, retries to a new child and cancels through real controls", async () => {
  await select();
  calls.read.mockResolvedValue(task({ status: "FAILED" }));
  await click("刷新所选任务");
  expect(calls.read).toHaveBeenCalledWith(ID);
  calls.history.mockResolvedValue({
    task_id: ID,
    action: "no_order",
    formal_eligibility: false,
    history: [
      {
        record_binding: { path: "TEST_ONLY", sha256: "c".repeat(64) },
        record: { version: 1, status: "FAILED" },
      },
    ],
  });
  await click("查看所选任务历史");
  expect(calls.history).toHaveBeenCalledWith(ID);
  calls.control.mockResolvedValueOnce(
    task({ task_id: CHILD, status: "RUNNING" }),
  );
  await click("重试所选任务");
  expect(calls.control).toHaveBeenCalledWith(ID, "retry");
  calls.control.mockResolvedValueOnce(
    task({ task_id: CHILD, status: "CANCELLED" }),
  );
  await click("取消所选任务");
  expect(calls.control).toHaveBeenCalledWith(CHILD, "cancel");
});
it("resumes only when the service explicitly marks interrupted work, not ordinary failures", async () => {
  await select("FAILED");
  expect(button("恢复所选任务").props.disabled).toBe(true);
  await select("BLOCKED", true);
  expect(button("重试所选任务").props.disabled).toBe(true);
  calls.control.mockResolvedValue(task({ status: "QUEUED" }));
  await click("恢复所选任务");
  expect(calls.control).toHaveBeenCalledWith(ID, "resume");
});
it("isolates 401 from public research and rejects mismatched/unsafe task results", async () => {
  calls.list.mockRejectedValue(new ApiError(401, "AUTH_REQUIRED", null));
  await click("读取任务列表");
  expect(JSON.stringify(render())).toContain("仍可阅读公开研究");
  await click("读取可执行操作与绑定");
  authorize();
  calls.start.mockResolvedValue(task({ formal_eligibility: true as any }));
  await click("执行所选操作");
  expect(JSON.stringify(render())).not.toContain("所选任务：");
});
it("polls a selected real task without overlapping and stops on terminal state", async () => {
  vi.useFakeTimers();
  let complete!: (v: any) => void;
  calls.read
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    )
    .mockResolvedValueOnce(task({ status: "SUCCESS" }));
  const value = vi.fn(),
    error = vi.fn(),
    stop = watchWorkbenchTask("000568", ID, value, error);
  expect(calls.read).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(15000);
  expect(calls.read).toHaveBeenCalledTimes(1);
  complete(task({ status: "RUNNING" }));
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(3000);
  await vi.advanceTimersByTimeAsync(30000);
  expect(value).toHaveBeenCalledTimes(2);
  expect(calls.read).toHaveBeenCalledTimes(2);
  expect(error).not.toHaveBeenCalled();
  expect(calls.start).not.toHaveBeenCalled();
  stop();
});
it("aborts and discards late polling after selection change or unmount", async () => {
  vi.useFakeTimers();
  let complete!: (v: any) => void;
  calls.read.mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const value = vi.fn(),
    error = vi.fn(),
    stop = watchWorkbenchTask("000568", ID, value, error);
  await vi.advanceTimersByTimeAsync(3000);
  const signal = calls.read.mock.calls[0][1];
  stop();
  expect(signal.aborted).toBe(true);
  complete(task());
  await vi.advanceTimersByTimeAsync(30000);
  expect(value).not.toHaveBeenCalled();
  expect(error).not.toHaveBeenCalled();
});
it.each([
  () => Promise.reject(new ApiError(401, "AUTH_REQUIRED", null)),
  () => Promise.resolve(task({ symbol: "600519" })),
])("stops failed or misbound polling without auto-retry", async (read) => {
  vi.useFakeTimers();
  calls.read.mockImplementation(read);
  const value = vi.fn(),
    error = vi.fn(),
    stop = watchWorkbenchTask("000568", ID, value, error);
  await vi.advanceTimersByTimeAsync(60000);
  expect(error).toHaveBeenCalledTimes(1);
  expect(calls.read).toHaveBeenCalledTimes(1);
  expect(value).not.toHaveBeenCalled();
  stop();
});
it("keeps unsupported actions disabled with exact reasons, and cleans up tracking on dependencies", () => {
  const source = readFileSync(
    "src/components/TransparentTaskControls.tsx",
    "utf8",
  );
  expect(source).toContain("return watchWorkbenchTask");
  expect(source).toMatch(/task\?\.status,\s*following,\s*busy/);
  expect(source).toContain("服务端自动选择并核验来源");
  expect(source).toContain("追加人工复核意见（非批准）");
  expect(source).not.toContain("operating-research");
  expect(source).not.toContain("localStorage");
});

it.each(["REPLAY_SELECTION", "RECALCULATE_MAIN", "VERIFY_EVIDENCE"])(
  "posts prepared %s inputs without asking for raw paths or hashes",
  async (operation) => {
    await click("读取可执行操作与绑定");
    nodes(render())
      .find((n) => n.type === "select")
      .props.onChange({ target: { value: operation } });
    calls.start.mockResolvedValue(task({ status: "SUCCESS", operation }));
    await click("执行所选操作");
    expect(calls.start.mock.calls[0][0]).toMatchObject({
      symbol: "000568",
      operation,
      payload: preparedRows().find((row) => row.operation === operation)!
        .prepared_payload,
    });
  },
);
it("keeps source bindings immutable when constructing explicit scenario simulation or review opinion", () => {
  const options = {
    network: false,
    limit: 10,
    scenario: "bear",
    field: "annual.2.target_payout_ratio",
    value: "0.10",
    rationale: "TEST_ONLY_SOURCE_ANCHOR",
    opinion: "TEST_ONLY_REVIEW",
  };
  const sim = preparedRows().find(
    (row) => row.operation === "SIMULATE_ASSUMPTIONS",
  )!;
  const result = preparedTaskPayload(sim, options);
  expect(result).toMatchObject({
    registry_binding: binding,
    spec_binding: binding,
    scenario: "bear",
    changes: [{ field: "annual.2.target_payout_ratio", value: "0.10" }],
    rationale: "TEST_ONLY_SOURCE_ANCHOR",
  });
  expect(sim.prepared_payload?.changes).toEqual([]);
  const review = preparedRows().find((row) => row.operation === "REVIEW_NOTE")!;
  expect(preparedTaskPayload(review, options)).toEqual({
    target_binding: binding,
    opinion: "TEST_ONLY_REVIEW",
  });
  expect(review.prepared_payload?.opinion).toBe("");
});
it("disables unavailable preparation with the precise native reason and blocks unwhitelisted simulation", async () => {
  calls.prepare.mockResolvedValue({
    symbol: "000568",
    action: "no_order",
    formal_eligibility: false,
    tasks_started: 0,
    operations: [
      {
        ...preparedRows()[0],
        enabled: false,
        reason: "REGISTERED_SCAN_MISSING",
        prepared_payload: null,
      },
    ],
  });
  await click("读取可执行操作与绑定");
  authorize();
  expect(button("执行所选操作").props.disabled).toBe(true);
  expect(JSON.stringify(render())).toContain("REGISTERED_SCAN_MISSING");
  const sim = preparedRows().find(
    (row) => row.operation === "SIMULATE_ASSUMPTIONS",
  )!;
  expect(() =>
    preparedTaskPayload(sim, {
      network: false,
      limit: 10,
      scenario: "base",
      field: "source.cash",
      value: "1",
      rationale: "TEST_ONLY",
      opinion: "",
    }),
  ).toThrow("白名单");
});

it("submits explicit Chinese-form simulation values against the server baseline without source/hash inputs", async () => {
  await click("读取可执行操作与绑定");
  nodes(render())
    .find((n) => n.type === "select")
    .props.onChange({ target: { value: "SIMULATE_ASSUMPTIONS" } });
  expect(button("执行所选操作").props.disabled).toBe(true);
  nodes(render())
    .find((n) => n.type === "input" && n.props.placeholder === "填写明确小数")
    .props.onChange({ target: { value: "0.10" } });
  nodes(render())
    .find((n) => n.type === "textarea")
    .props.onChange({ target: { value: "TEST_ONLY_SCENARIO_REASON" } });
  calls.start.mockResolvedValue(
    task({ status: "SUCCESS", operation: "SIMULATE_ASSUMPTIONS" }),
  );
  await click("执行所选操作");
  const request = calls.start.mock.calls[0][0];
  expect(request).toMatchObject({
    module_id: "F1",
    operation: "SIMULATE_ASSUMPTIONS",
    payload: {
      registry_binding: binding,
      spec_binding: binding,
      scenario: "bear",
      changes: [{ field: "cost_of_equity", value: "0.10" }],
      rationale: "TEST_ONLY_SCENARIO_REASON",
    },
  });
  expect(Object.keys(request)).not.toContain("approved");
});
it("posts a review opinion bound by the server without editable actor or approval", async () => {
  await click("读取可执行操作与绑定");
  nodes(render())
    .find((n) => n.type === "select")
    .props.onChange({ target: { value: "REVIEW_NOTE" } });
  nodes(render())
    .find((n) => n.type === "textarea")
    .props.onChange({ target: { value: "TEST_ONLY_COMMENT_NOT_APPROVAL" } });
  calls.start.mockResolvedValue(
    task({ status: "SUCCESS", operation: "REVIEW_NOTE" }),
  );
  await click("执行所选操作");
  expect(calls.start.mock.calls[0][0].payload).toEqual({
    target_binding: binding,
    opinion: "TEST_ONLY_COMMENT_NOT_APPROVAL",
  });
  expect(Object.keys(calls.start.mock.calls[0][0])).not.toContain(
    "actor_context",
  );
  expect(JSON.stringify(render())).not.toContain("已批准");
});

it("renders actual server feedback and leaves unknown clocks/identities unknown without fake progress", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const known = task({
    module_id: "F1",
    module_version: "TEST_ONLY_VERSION",
    run_id: "TEST_ONLY_RUN",
    input_binding: { path: "TEST_ONLY", sha256: "d".repeat(64) },
    started_at: "TEST_ONLY_START",
    finished_at: "TEST_ONLY_END",
    duration_seconds: 12.5,
    current_step: "VERIFY_OUTPUT",
    retry_allowed: false,
  });
  const html = renderToStaticMarkup(<TaskRunFeedback task={known} />);
  for (const text of [
    "F1",
    "TEST_ONLY_VERSION",
    "TEST_ONLY_RUN",
    "TEST_ONLY_START",
    "TEST_ONLY_END",
    "12.5",
    "VERIFY_OUTPUT",
    "服务端不允许",
  ])
    expect(html).toContain(text);
  const missing = renderToStaticMarkup(<TaskRunFeedback task={task()} />);
  expect(missing).toContain("未提供");
  expect(missing).toContain("未开始");
  expect(missing).not.toContain("100%");
  expect(
    renderToStaticMarkup(
      <TaskRunFeedback
        task={task({
          current_validation: "UNASSESSABLE",
          current_validation_reason: "TEST_ONLY_SOURCE_CHANGED",
        })}
      />,
    ),
  ).toContain("不能当作当前有效成果");
});

it("defaults to bounded automatic refresh when the backend advertises it", async () => {
  const auto: PreparedWorkbenchOperation = {
    module_id: "B",
    operation: "VALUE_RESEARCH_REFRESH",
    enabled: true,
    prepared_payload: {
      source_mode: "FRESH",
      network_authorized: false,
      tracking_budget: 30,
      enrichment_batches: 1,
      comparison_batches: 1,
      operating_budget: 0,
    },
    user_fields: [],
    network_authorization_required: true,
  };
  calls.prepare.mockResolvedValue({
    symbol: "000568",
    action: "no_order",
    formal_eligibility: false,
    tasks_started: 0,
    operations: [...preparedRows(), auto],
  });
  await click("读取可执行操作与绑定");
  authorize();
  calls.start.mockResolvedValue(task({ operation: "VALUE_RESEARCH_REFRESH" }));
  await click("执行所选操作");
  expect(calls.start).toHaveBeenCalledTimes(1);
  expect(calls.start.mock.calls[0][0]).toMatchObject({
    operation: "VALUE_RESEARCH_REFRESH",
    timeout_seconds: 1800,
    payload: {
      source_mode: "FRESH",
      network_authorized: true,
      tracking_budget: 30,
      enrichment_batches: 1,
      operating_budget: 0,
    },
  });
});
