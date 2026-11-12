import React from "react";
import { webcrypto } from "node:crypto";
import { beforeEach, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({ values: [] as any[], cursor: 0 }));
const calls = vi.hoisted(() => ({ create: vi.fn(), importV12: vi.fn(), repairV16: vi.fn() }));
vi.mock("react", async (original) => {
  const actual = await original<typeof import("react")>();
  return {
    ...actual,
    useEffect: vi.fn(),
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
vi.mock("../src/services/api", async (original) => {
  const actual = await original<typeof import("../src/services/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      createHorizonCashPolicyTask: calls.create,
      importV12HorizonCashPolicyTask: calls.importV12,
      repairV16HorizonCashPolicyTask: calls.repairV16,
    },
  };
});
import { HorizonCashPolicyPanel } from "../src/components/HorizonCashPolicyPanel";

function nodes(value: any): any[] {
  return Array.isArray(value)
    ? value.flatMap(nodes)
    : React.isValidElement(value)
      ? [value, ...nodes((value as any).props.children)]
      : [];
}
function render(symbol: string) {
  hooks.cursor = 0;
  return nodes(HorizonCashPolicyPanel({ symbol }));
}
function button(rows: any[], label: string) {
  const found = rows.find(
    (row) =>
      row.props.children === label && typeof row.props.onClick === "function",
  );
  expect(found, label).toBeDefined();
  return found;
}

beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  calls.create.mockReset();
  calls.importV12.mockReset();
  calls.repairV16.mockReset();
  vi.stubGlobal("crypto", webcrypto);
});

it("requires an explicit 600519 action and sends the pinned D2 WC source version", async () => {
  const entry = render("600519");
  expect(calls.create).not.toHaveBeenCalled();
  button(entry, "D2 股东现金政策研究").props.onClick();
  calls.create.mockResolvedValue({
    task_id: "rt-" + "a".repeat(32),
    symbol: "600519",
    status: "WAITING_EVIDENCE",
    action: "no_order",
    formal_eligibility: false,
  });
  await button(
    render("600519"),
    "启动2027两阶段V13研究（含母公司余额证据，可能计费）",
  ).props.onClick();
  expect(calls.create).toHaveBeenCalledWith(
    expect.objectContaining({
      symbol: "600519",
      years: [2027],
      task_contract: "operating-horizon-task-v13-2027-live",
      source_loader_version: "operating-q3-issuer-wc-loader-v9-600519",
    }),
  );
  expect(button(render("600519"), "读取当前任务")).toBeDefined();
});

it("does not offer the issuer-specific source for another company", () => {
  button(render("600887"), "D2 股东现金政策研究").props.onClick();
  const labels = nodes(HorizonCashPolicyPanel({ symbol: "600887" })).map(
    (row) => row.props.children,
  );
  expect(labels).not.toContain(
    "启动2027两阶段V13研究（含母公司余额证据，可能计费）",
  );
  expect(calls.create).not.toHaveBeenCalled();
});

it("continues only a sealed V12 annual stage with a stable idempotency key", async () => {
  button(render("600519"), "D2 股东现金政策研究").props.onClick();
  const sourceId = "rt-" + "b".repeat(32);
  hooks.values[1] = {
    task_id: sourceId,
    symbol: "600519",
    status: "FAILED",
    workflow: "operating-horizon-task-v12-2027-live",
    annual_status: "SETTLED_VALIDATED",
    action: "no_order",
  };
  hooks.values[3] = "v12";
  calls.importV12.mockResolvedValue({
    task_id: "rt-" + "c".repeat(32),
    symbol: "600519",
    status: "QUEUED",
    workflow: "operating-horizon-task-v13-2027-live",
    annual_status: "IMPORTED_V12",
    action: "no_order",
  });
  await button(
    render("600519"),
    "复用已核验年度研究，继续V13现金政策（可能计费）",
  ).props.onClick();
  expect(calls.importV12).toHaveBeenCalledWith({
    source_task_id: sourceId,
    request_key: "cash_import_v13_" + "b".repeat(32),
    task_contract: "operating-horizon-task-v13-2027-live",
  });
  expect(calls.create).not.toHaveBeenCalled();
  expect(hooks.values[3]).toBe("v13");
});

it("offers V15 only for validated V12 annual research and keeps its own workflow", async () => {
  button(render("600519"), "D2 股东现金政策研究").props.onClick();
  const sourceId = "rt-" + "d".repeat(32);
  hooks.values[1] = {
    task_id: sourceId,
    symbol: "600519",
    status: "FAILED",
    workflow: "operating-horizon-task-v12-2027-live",
    annual_status: "SETTLED_VALIDATED",
    action: "no_order",
  };
  hooks.values[3] = "v12";
  calls.importV12.mockResolvedValue({
    task_id: "rt-" + "e".repeat(32),
    symbol: "600519",
    status: "QUEUED",
    workflow: "operating-horizon-task-v15-2027-live",
    action: "no_order",
  });
  await button(
    render("600519"),
    "复用已核验年度研究，按V15条件现金合同继续（可能计费）",
  ).props.onClick();
  expect(calls.importV12).toHaveBeenCalledWith({
    source_task_id: sourceId,
    request_key: "cash_import_v15_" + "d".repeat(32),
    task_contract: "operating-horizon-task-v15-2027-live",
  });
  expect(hooks.values[3]).toBe("v15");
  expect(calls.create).not.toHaveBeenCalled();
});

it("shows a successful V15 task as economically incomplete when cash paths remain unknown", () => {
  button(render("600519"), "D2 股东现金政策研究").props.onClick();
  hooks.values[1] = {
    task_id: "rt-" + "f".repeat(32),
    symbol: "600519",
    status: "SUCCEEDED",
    action: "no_order",
    annual_status: "IMPORTED_V12",
    cash_status: "SETTLED_VALIDATED",
    research_result: {
      cash_policy_v15: {
        cash_policy_appendix_status: "INCOMPLETE_UNKNOWN_TERMS",
      },
    },
  };
  hooks.values[3] = "v15";
  const alerts = render("600519").filter((row) => row.props.type === "warning");
  expect(alerts.map((row) => row.props.message)).toContain(
    "V15任务已完成，股东现金研究尚未准入",
  );
});

it("starts source-bound V16 while preserving V15 history on explicit click", async () => {
  const label = "用已核验历史分红原件启动V16年度与现金研究（可能计费）";
  button(render("600519"), "D2 股东现金政策研究").props.onClick();
  expect(calls.create).not.toHaveBeenCalled();
  calls.create.mockResolvedValue({
    task_id: "rt-" + "e".repeat(32),
    symbol: "600519",
    status: "WAITING_EVIDENCE",
    action: "no_order",
    formal_eligibility: false,
  });
  await button(render("600519"), label).props.onClick();
  expect(calls.create).toHaveBeenCalledWith(
    expect.objectContaining({
      symbol: "600519",
      years: [2027],
      task_contract: "operating-horizon-task-v16-2027-live",
      source_loader_version:
        "operating-q3-issuer-dividend-split-loader-v9-600519",
    }),
  );
  expect(button(render("600519"), "读取当前任务")).toBeDefined();
  expect(button(render("600519"), "读取2027 V15封存任务")).toBeDefined();
  hooks.values = [];
  button(render("600887"), "D2 股东现金政策研究").props.onClick();
  expect(
    nodes(HorizonCashPolicyPanel({ symbol: "600887" })).map(
      (row) => row.props.children,
    ),
  ).not.toContain(label);
});

it("continues only an explicitly selected failed V16 task as V17 cash-only", async () => {
  button(render("600519"), "D2 股东现金政策研究").props.onClick();
  const sourceId = "rt-" + "a".repeat(32);
  hooks.values[1] = {
    task_id: sourceId, symbol: "600519", status: "FAILED",
    error_code: "V16_ANNUAL_RESPONSE_REJECTED", action: "no_order",
  };
  hooks.values[3] = "v16";
  const label = "封存V16年度响应结构修复后仅继续现金研究（可能计费）";
  calls.repairV16.mockResolvedValue({
    task_id: "rt-" + "b".repeat(32), symbol: "600519", status: "QUEUED",
    workflow: "operating-horizon-task-v17-2027-cash-repair",
    action: "no_order", formal_eligibility: false,
  });
  await button(render("600519"), label).props.onClick();
  expect(calls.repairV16).toHaveBeenCalledWith({
    source_task_id: sourceId,
    request_key: "cash_repair_v17_" + "a".repeat(32),
  });
  expect(calls.create).not.toHaveBeenCalled();
  expect(hooks.values[3]).toBe("v17");
});
