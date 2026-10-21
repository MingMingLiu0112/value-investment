import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({ data: {} as any }));
vi.mock("@umijs/max", () => ({
  useParams: () => ({ id: "600887" }),
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({ data: state.data, loading: false, error: null }),
}));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => ({
    kind: "LOCKED",
    label: "私人台账未解锁",
    detail: "实际成交未知",
  }),
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: any) => <main>{children}</main>,
}));
vi.mock("../src/components/RemoteState", () => ({
  RemoteState: ({ children }: any) => children,
}));
vi.mock("../src/components/CurrentJudgment", () => ({
  JudgmentSummary: () => <section>六项操作计划</section>,
  CurrentJudgmentChart: () => <section>当前图表</section>,
}));
vi.mock("../src/components/HotspotReplayReview", () => ({
  HotspotReplayReview: () => (
    <details>
      <summary>非实际成交历史信号检验</summary>
    </details>
  ),
}));
import DecisionDetail from "../src/pages/DecisionDetail";
import DecisionHistory from "../src/pages/DecisionHistory";

it("shows verified financial input progress separately from economic approval", () => {
  state.data = {
    decision: { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
    financial_progress: {
      status: "VERIFIED_FACT_ADOPTION",
      action: "no_order",
      symbol: "600887",
      adopted_fact_count: 1,
      research_inputs_updated: true,
      quality_coverage_before: "0.5556",
      quality_coverage_after: "0.6667",
      formal_eligibility: false,
      adopted_metrics: [
        {
          field_name: "revenue_yoy",
          value: "-1.206",
          unit: "percent",
          period_label: "2025-12-31",
        },
        {
          field_name: "net_income_yoy",
          value: "-4.532",
          unit: "percent",
          period_label: "2025-12-31",
        },
        {
          field_name: "debt_ratio",
          value: "999",
          unit: "CNY",
          period_label: "2025-12-31",
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("财务补证已回流研究");
  expect(html).toContain("55.6");
  expect(html).toContain("66.7");
  expect(html).toContain("投资资格仍独立核验");
  expect(html).toContain("营业收入同比");
  expect(html).toContain("-1.21");
  expect(html).toContain("归母净利润同比");
  expect(html).toContain("-4.53");
  expect(html).not.toContain("999.00");
  for (const mutation of [
    { symbol: "600519" },
    { formal_eligibility: true },
    { adopted_fact_count: 0 },
    { quality_coverage_after: "" },
  ]) {
    const original = state.data.financial_progress;
    state.data.financial_progress = { ...original, ...mutation };
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      "财务补证已回流研究",
    );
    state.data.financial_progress = original;
  }
});

it("keeps research collapsed and trade navigation ahead of the current chart without autofilling execution prices", () => {
  state.data = {
    decision: {
      id: "hotspot-300364",
      symbol: "300364",
      name: "中文在线",
      strategy: "hotspot",
      price_action_plan: { research_version: "real-version" },
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html.indexOf("六项操作计划")).toBeLessThan(
    html.indexOf("记录我的实际成交"),
  );
  expect(html.indexOf("记录我的实际成交")).toBeLessThan(
    html.indexOf("当前图表"),
  );
  expect(html).toContain("research_version=real-version");
  expect(html).not.toMatch(/(?:price|quantity)=/);
  expect(html).toContain("展开研究底稿、估值与历史资格核验");
  expect(html).not.toMatch(/<details[^>]*\bopen/);
});

it("prioritizes actual trades over research and proxy replay while a locked ledger stays unknown", () => {
  state.data = { items: [], counts: {} };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html.indexOf("我的实际成交与原判断版本")).toBeLessThan(
    html.indexOf("研究快照与判断变化"),
  );
  expect(html.indexOf("研究快照与判断变化")).toBeLessThan(
    html.indexOf("非实际成交历史信号检验"),
  );
  expect(html).toContain("实际成交未知");
  expect(html).not.toContain("无实际成交");
});

it("shows verified retained observation changes without upgrading trading permission", () => {
  state.data = {
    items: [],
    observation_changes: {
      status: "SOURCE_REVALIDATED",
      completed_session: "2026-10-20",
      items: [
        {
          symbol: "000333",
          transition: "continue",
          trend_strengthened: true,
          selected_today: false,
          market_trade_date: "2026-10-19",
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html).toContain("/decisions/hotspot-000333");
  expect(html).toContain("继续观察");
  expect(html).toContain("保留观察历史");
  expect(html).toContain("不代表交易批准");
  expect(html).toContain("趋势增强");
  state.data.observation_changes = { status: "UNAVAILABLE", items: [] };
  expect(renderToStaticMarkup(<DecisionHistory />)).toContain("不等于没有变化");
});

it("offers keyboard-accessible snapshot choices and keeps the selected audit collapsed", () => {
  state.data = {
    items: [
      {
        id: "600887",
        symbol: "600887",
        status: "RESEARCH_ONLY",
        latest_version_label: "真实研究版本",
        comparison: {},
        versions: [],
      },
    ],
    counts: {},
  };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html).toContain('role="button"');
  expect(html).toContain('tabindex="0"');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain("研究快照不等于实际执行");
  expect(html).toContain("展开所选研究的依据、版本与变化");
  expect(html).not.toMatch(/<details[^>]*\bopen/);
});

it("shows source-verified research judgment before account workflow only for the same publication", () => {
  state.data = {
    publication_id: "pub-current",
    publication: { publication_id: "pub-current" },
    company_statuses: {
      "600887": {
        decision_chain: {
          gaps: [],
          research_conclusion: {
            evidence_verified: true,
            summary: "压力情景不能作为可靠合理价",
          },
        },
      },
    },
    decision: { id: "600887", symbol: "600887", strategy: "value" },
  };
  let html = renderToStaticMarkup(<DecisionDetail />);
  expect(html.indexOf("压力情景不能作为可靠合理价")).toBeLessThan(
    html.indexOf("六项操作计划"),
  );
  state.data.publication.publication_id = "pub-old";
  html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).not.toContain("压力情景不能作为可靠合理价");
});
