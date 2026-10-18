import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const response = vi.hoisted(() => ({
  loading: false,
  error: undefined as string | undefined,
  retry: () => {},
  data: {
    status: "NOT_STARTED",
    test_only: false,
    monitor_running: false,
    alerts: [],
    history: [],
    detail: "实际盘中监控尚未接通",
    public_observation: undefined as any,
  },
}));
vi.mock("@umijs/max", () => ({
  useLocation: () => ({ pathname: "/alerts" }),
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => response }));
import ConditionAlerts from "../src/pages/ConditionAlerts";

it("shows honest stopped monitoring and no fabricated reminders", () => {
  const html = renderToStaticMarkup(<ConditionAlerts />);
  expect(html).toContain("监控未运行");
  expect(html).toContain("暂无可核验的条件变化记录");
  expect(html).toContain("隔离演练记录");
  expect(html).not.toContain("监控进程运行中");
});

it("cannot show a stale success after an authorization/read error", () => {
  response.error = "工作台已锁定";
  const html = renderToStaticMarkup(<ConditionAlerts />);
  expect(html).toContain("工作台已锁定");
  expect(html).not.toContain("暂无可核验的条件变化记录");
  response.error = undefined;
});

it("does not render a previous TEST_ONLY response in the normal view", () => {
  response.data.test_only = true;
  const html = renderToStaticMarkup(<ConditionAlerts />);
  expect(html).not.toContain("暂无可核验的条件变化记录");
  expect(html).not.toContain("监控未运行");
  response.data.test_only = false;
});

it("separates real public observation controls from formal alerts", () => {
  response.data.public_observation = {
    status: "STOPPED",
    monitor_running: false,
    detail: "公开观测不是投资批准",
    choices: [{ symbol: "600150", company_name: "公开候选" }],
    samples: [
      {
        sample_id: "retained",
        symbol: "600150",
        checked_at: "2026-10-18T08:00:00Z",
        status: "STALE_OR_UNAVAILABLE",
        reason: "OUTSIDE_EXCHANGE_SESSION",
        source_refs: [],
      },
    ],
  };
  const html = renderToStaticMarkup(<ConditionAlerts />);
  expect(html).toContain("公开行情观测");
  expect(html).toContain("启动观测");
  expect(html).toContain("停止观测");
  expect(html).toContain("当前不在交易时段");
  expect(html).toContain("暂停价格判断");
  expect(html).not.toContain("双源报价核验通过");
  response.data.public_observation = undefined;
});

it("shows bound reference conditions and risk review without a trade permission", () => {
  response.data.public_observation = {
    status: "STOPPED",
    monitor_running: false,
    samples: [],
    choices: [],
    symbol: "600150",
    condition_observation: {
      binding_sha256: "a".repeat(64),
      states: [
        {
          kind: "ENTRY_REFERENCE_GT",
          condition: { threshold: "36.45", operator: "GT" },
          state: {
            status: "NOT_TRIGGERED",
            reason: "EXPLICIT_PRICE_CONDITION_NOT_MATCHED",
            checked_at: "2026-10-16T02:00:00Z",
          },
        },
        {
          kind: "INVALIDATION_REFERENCE_LT",
          status: "RISK_REVIEW",
          condition: { threshold: "34.41", operator: "LT" },
          state: {
            status: "STRUCTURE_OBSERVATION",
            reason: "EXPLICIT_PRICE_CONDITION_MATCHED",
            checked_at: "2026-10-16T02:00:00Z",
          },
        },
      ],
    },
    condition_transitions: [
      {
        transition_id: "local",
        kind: "INVALIDATION_REFERENCE_LT",
        status: "RISK_REVIEW",
        threshold: "34.41",
        price: "34",
        checked_at: "2026-10-16T02:00:00Z",
        reason: "EXPLICIT_PRICE_CONDITION_MATCHED",
      },
    ],
  };
  const html = renderToStaticMarkup(<ConditionAlerts />);
  expect(html).toContain("计划参考价复核");
  expect(html).toContain("36.45");
  expect(html).toContain("34.41");
  expect(html).toContain("需风险复核");
  expect(html).toContain("停止观测后不代表当前价格");
  expect(html).toContain("本次观测的条件变化历史");
  expect(html).not.toContain("允许买入");
  response.data.public_observation = undefined;
});
