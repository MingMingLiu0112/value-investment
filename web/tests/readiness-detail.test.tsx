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
