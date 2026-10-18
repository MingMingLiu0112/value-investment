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
