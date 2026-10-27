import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../src/services/api";
import { evaluationFixture } from "./fixtures/strategy-readiness";
import { analysisDecision } from "./fixtures/value-research-analysis";
import { lifecycleFixture, lifecyclePlan } from "./fixtures/hotspot-lifecycle";
const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({
  daily: {
    data: {} as any,
    loading: false,
    error: undefined as string | undefined,
  },
  packet: {
    data: {} as any,
    loading: false,
    error: undefined as string | undefined,
  },
  detail: {
    data: {} as any,
    loading: false,
    error: undefined as string | undefined,
  },
}));
vi.mock("@umijs/max", () => ({
  useParams: () => ({ id: "600887" }),
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: (load: unknown) =>
    load === api.daily
      ? state.daily
      : load === api.packet
        ? state.packet
        : state.detail,
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: any) => <main>{children}</main>,
}));
vi.mock("../src/components/RemoteState", () => ({
  RemoteState: ({ children }: any) => children,
}));
vi.mock("../src/components/CurrentJudgment", () => ({
  JudgmentSummary: () => <p>原始操作判断</p>,
  CurrentJudgmentChart: () => null,
}));
vi.mock("../src/pages/DecisionDetail/CurrentHolding", () => ({
  CurrentHolding: () => null,
}));
vi.mock("../src/pages/DecisionDetail/AgentResearchPanel", () => ({
  AgentResearchPanel: () => null,
}));
import DecisionDetail from "../src/pages/DecisionDetail";

beforeEach(() => {
  const publication = {
    packet_status: "CURRENT",
    publication_id: "same-publication",
  };
  state.daily = {
    data: {
      action: "no_order",
      publication,
      actionable_evaluation: { items: [evaluationFixture()] },
    },
    loading: false,
    error: undefined,
  };
  state.packet = {
    data: { action: "no_order", ...publication },
    loading: false,
    error: undefined,
  };
  state.detail = {
    data: {
      action: "no_order",
      publication,
      decision: {
        id: "600887",
        symbol: "600887",
        strategy: "value",
        name: "测试证券",
      },
    },
    loading: false,
    error: undefined,
  };
});

it("mounts readiness in the actual security page before its existing judgment", () => {
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain('aria-label="策略就绪阶段"');
  expect(html.indexOf("当前阶段：")).toBeLessThan(html.indexOf("原始操作判断"));
  expect(html).toContain("未获操作批准");
});

it.each(["OPEN", "ADD", "HOLD", "REDUCE", "EXIT"])(
  "shows public %s review without personal shares",
  (intent) => {
    state.detail.data.strategy_evaluation = {
      action: "no_order",
      symbol: "600887",
      strategy: "CORE_VALUE",
      decision_action: "CONDITIONAL_MANUAL_REVIEW",
      evaluation_status: "EVALUATED_CONDITIONAL_REVIEW",
      public_action_intent: intent,
      decision_reason: "TEST_ONLY native replay",
      eligibility: false,
      review_quantity: null,
      position_range: null,
      available_cash_impact: null,
    };
    const html = renderToStaticMarkup(<DecisionDetail />);
    expect(html).toContain("证券级条件性人工复核");
    expect(html).toContain("TEST_ONLY native replay");
    expect(html).toContain("不提供个人可操作股数");
    expect(html).toContain("不是下单许可");
  },
);

it.each([
  { symbol: "600519" },
  { strategy: "HOTSPOT_SATELLITE" },
  { eligibility: true },
  { review_quantity: 100 },
  { public_action_intent: "BUY_NOW" },
  { evaluation_status: "NOT_ASSESSABLE" },
])("does not present incompatible public review %j", (change) => {
  state.detail.data.strategy_evaluation = {
    action: "no_order",
    symbol: "600887",
    strategy: "CORE_VALUE",
    decision_action: "CONDITIONAL_MANUAL_REVIEW",
    evaluation_status: "EVALUATED_CONDITIONAL_REVIEW",
    public_action_intent: "OPEN",
    decision_reason: "TEST_ONLY incompatible review",
    eligibility: false,
    review_quantity: null,
    position_range: null,
    available_cash_impact: null,
    ...change,
  };
  expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
    "证券级条件性人工复核",
  );
});

it.each(["daily", "packet", "detail"] as const)(
  "suppresses retained readiness after %s fails, reloads or changes publication",
  (source) => {
    state[source].error = "failed";
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      'aria-label="策略就绪阶段"',
    );
    state[source].error = undefined;
    state[source].loading = true;
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      'aria-label="策略就绪阶段"',
    );
    state[source].loading = false;
    if (source === "packet") state[source].data.publication_id = "old";
    else
      state[source].data.publication = {
        packet_status: "CURRENT",
        publication_id: "old",
      };
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      'aria-label="策略就绪阶段"',
    );
  },
);

it("does not reuse value readiness in the same security's hotspot page", () => {
  state.detail.data.decision.strategy = "hotspot";
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).not.toContain('aria-label="策略就绪阶段"');
  expect(html).toContain("原始操作判断");
});

it("preserves the old detail when readiness is absent", () => {
  state.daily.data.actionable_evaluation.items[0].readiness = undefined;
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).not.toContain('aria-label="策略就绪阶段"');
  expect(html).toContain("原始操作判断");
});

it("mounts verified conditional analysis in the existing detail page", () => {
  state.detail.data.decision = analysisDecision();
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain('aria-label="条件研究分析"');
  expect(html).toContain("10.0988");
  expect(html).toContain("未获操作准入");
  state.detail.error = "refresh failed";
  expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
    'aria-label="条件研究分析"',
  );
});

it("mounts verified standalone research while the formal publication is unavailable", () => {
  const nested = analysisDecision();
  state.detail.data.publication = { packet_status: "UNAVAILABLE" };
  state.detail.data.decision = {
    ...nested,
    action: "no_order",
    price_action_plan: null,
    research_analysis: nested.price_action_plan?.research_analysis,
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain('aria-label="条件研究分析"');
  expect(html).toContain("10.0988");
  expect(html).toContain("未获操作准入");
});

it("reads lifecycle from the top-level detail payload in the existing hotspot card", () => {
  state.detail.data.decision = {
    id: "hotspot-600519",
    symbol: "600519",
    strategy: "hotspot",
    price_action_plan: lifecyclePlan(),
  };
  state.detail.data.hotspot_lifecycle_review = lifecycleFixture();
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("波段结构连续性复核");
  expect(html).toContain("未提供原入场，仅当前结构观察");
  expect(html).toContain("12.3400");
  expect(html.indexOf("原始操作判断")).toBeLessThan(
    html.indexOf("波段结构连续性复核"),
  );
  state.detail.error = "TEST_ONLY failed refresh";
  const failed = renderToStaticMarkup(<DecisionDetail />);
  expect(failed).toContain("暂不可评价");
  expect(failed).not.toContain("12.3400");
  state.detail.error = undefined;
  state.detail.loading = true;
  expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain("12.3400");
});

it("does not borrow lifecycle from a nested decision or infer an entry from earlier candidates", () => {
  state.detail.data.decision = {
    id: "hotspot-600519",
    symbol: "600519",
    strategy: "hotspot",
    price_action_plan: lifecyclePlan(),
    hotspot_lifecycle_review: lifecycleFixture(),
  };
  expect(renderToStaticMarkup(<DecisionDetail />)).toContain(
    "尚未接入或当前不可核验",
  );
});

/** TEST_ONLY future as-of DTO; the actual 600887 policy is not approved. */
function mountTestOnlyAsOfResearch() {
  const scope = {
    scope: "CURRENT_AS_OF_SNAPSHOT_V1",
    action: "no_order",
    observed_at: "2026-10-24T09:10:00+08:00",
    knowledge_as_of: "2026-10-24T09:12:00+08:00",
    full_calendar_window_elapsed: false,
    strict_contemporaneous_pit: false,
    formal_eligibility: false,
    strategy_approval_granted: false,
    research_comparison_only: true,
  };
  state.detail.data.decision.research = {
    symbol: "600887",
    decision_cutoff: "2026-10-11",
    gates: [],
    valuation: {
      bear: "8",
      base: "10",
      bull: "12",
      valuation_date: "2026-10-20",
    },
    price: { current_price: "9", price_as_of: "2026-10-23" },
    price_bridge_execution: {
      ...scope,
      schema_version: "quote-bridge-execution-v1",
      status: "QUOTE_VERIFIED_WITH_CURRENT_ASOF_SNAPSHOT",
      price_admitted: true,
      comparison_eligible: true,
      research_day: "2026-10-11",
      quote_date: "2026-10-23",
      sources: [],
      current_snapshot_validity: {
        ...scope,
        schema_version: "current-snapshot-validity-result-v1",
        symbol: "600887",
        status: "VALID_AS_OF_SNAPSHOT",
        usable_for_research_comparison: true,
        g3_approval_granted: false,
        blockers: [],
      },
      current_event_coverage: {
        ...scope,
        status: "CURRENT_AS_OF_SNAPSHOT",
        required_through: "2026-10-24",
        query_through: "2026-10-24",
        covered_through: null,
      },
    },
  };
}

it("TEST_ONLY maps future as-of scope in the existing detail without pretending a real approval", () => {
  mountTestOnlyAsOfResearch();
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("公告快照取得时间（非重新计算时间）");
  expect(html).toContain("知识可得上界（全部输入可得时点）");
  for (const date of [
    "2026-10-24T09:10:00+08:00",
    "2026-10-24T09:12:00+08:00",
    "2026-10-11",
    "2026-10-20",
    "2026-10-23",
  ])
    expect(html).toContain(date);
  expect(html).toContain("不是全天公告覆盖");
  expect(html).toContain("不证明历史 PIT");
  expect(html).toContain("不授予策略资格或买卖许可");
  expect(html).not.toContain("已核验收盘行情在研究覆盖范围内");
  expect(html).toContain("overflow-wrap:anywhere");
  expect(html).toContain("原始操作判断");
  expect(html).not.toMatch(/(?:price|quantity)=/);
});

it("TEST_ONLY refuses an incomplete future scope and leaves the legacy view unchanged", () => {
  mountTestOnlyAsOfResearch();
  delete state.detail.data.decision.research.price_bridge_execution
    .knowledge_as_of;
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("快照范围未核验，暂不可比较");
  expect(html).not.toContain("仅具备已采集时点研究比较资格");
  delete state.detail.data.decision.research;
  const legacy = renderToStaticMarkup(<DecisionDetail />);
  expect(legacy).not.toContain("知识可得上界");
  expect(legacy).toContain("原始操作判断");
});
