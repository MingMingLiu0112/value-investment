import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("@ant-design/icons", () => ({ ArrowRightOutlined: () => null }));
import { DecisionCard } from "../src/components/DecisionCard";
import { evaluationFixture } from "./fixtures/strategy-readiness";

it("preserves a rejection reason without treating it as a sell or a missing valuation", () => {
  const evaluation = {
    ...evaluationFixture("HOTSPOT_SATELLITE"),
    decision_action: "NO_TRADE" as const,
    decision_reason: "多周期结构冲突，暂不新建仓。",
  };
  const item = {
    id: "hotspot-600887",
    symbol: "600887",
    strategy: "hotspot",
    price_action_plan: {
      action: "no_order" as const,
      signal_state: "TRIGGER_REJECTED",
      entry_trigger_price: null,
      invalidation_price: null,
    },
  };
  const html = renderToStaticMarkup(
    <DecisionCard item={item} evaluation={evaluation} />,
  );
  expect(html).toContain("已评价，暂不新建仓");
  expect(html).toContain(evaluation.decision_reason);
  expect(html).not.toContain("估值未就绪");
  expect(html).not.toContain("decision-state-formal");
  for (const change of [{ symbol: "600519" }, { strategy: "CORE_VALUE" }]) {
    expect(
      renderToStaticMarkup(
        <DecisionCard item={item} evaluation={{ ...evaluation, ...change }} />,
      ),
    ).not.toContain(evaluation.decision_reason);
  }
});

it.each([false, true])(
  "keeps independent risk review separate from trading permission (%s)",
  (ready) => {
    const html = renderToStaticMarkup(
      <DecisionCard
        item={{
          id: "independent",
          symbol: "000333",
          strategy: "HOTSPOT_SATELLITE",
          price_action_plan: {
            action: "no_order",
            signal_state: "WATCH",
            entry_trigger_price: null,
            invalidation_price: null,
            formal_eligibility: false,
            risk_review_eligible: ready,
            independent_admission: {
              status: ready ? "RISK_REVIEW_ELIGIBLE" : "OBSERVATION_ONLY",
              review_status: ready ? "VERIFIED" : "MISSING",
              risk_review_eligible: ready,
              blockers: [],
              action: "no_order",
            },
          },
        }}
      />,
    );
    expect(html).toContain(ready ? "尚无交易许可" : "当前仅观察");
    expect(html).not.toContain("decision-state-formal");
  },
);

it("shows second-layer quality even when a local trigger was observed against a downtrend", () => {
  const html = renderToStaticMarkup(
    <DecisionCard
      item={{
        id: "current",
        symbol: "601318",
        strategy: "HOTSPOT_SATELLITE",
        price_action_plan: {
          action: "no_order",
          signal_state: "TRIGGER_OBSERVED",
          entry_trigger_price: "12",
          invalidation_price: "11",
          price_behavior: { daily_trend: "DOWNTREND" } as any,
        },
      }}
    />,
  );
  expect(html).toContain("A · 活跃观察，结构不满足");
  expect(html).toContain("日线下降，局部触发不构成入场条件");
  expect(html).not.toContain("decision-state-formal");
  expect(html).toContain('href="/decisions/current?independent_hotspot=true"');
});

it("never upgrades a backend active-only observation to a qualified structure", () => {
  const html = renderToStaticMarkup(
    <DecisionCard
      item={{
        id: "current",
        symbol: "600030",
        strategy: "HOTSPOT_SATELLITE",
        price_action_plan: {
          action: "no_order",
          signal_state: "TRIGGER_OBSERVED",
          entry_trigger_price: "20",
          invalidation_price: "19",
          price_behavior: {
            daily_trend: "UPTREND",
            observation_quality: "RESEARCH_ONLY",
            breakout: { confirmed_on_next_completed_bar: true },
          } as any,
          opportunity_quality: {
            rule_version: "hotspot-opportunity-quality-v1",
            activity_tier: "ACTIVE_OBSERVATION",
            structure_tier: "ACTIVE_ONLY",
            structure_reasons: ["STRUCTURE_CONFIRMATION_PENDING"],
            assessed_trade_date: "2026-10-16",
            expires_after_session: "2026-10-19",
            formal_eligibility: false,
            action: "no_order",
          },
        },
      }}
    />,
  );
  expect(html).not.toContain("D · 条件性结构计划");
  expect(html).not.toContain("decision-state-formal");
});
