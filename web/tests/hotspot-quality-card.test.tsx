import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("@ant-design/icons", () => ({ ArrowRightOutlined: () => null }));
import { DecisionCard } from "../src/components/DecisionCard";

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
  expect(html).toContain('href="/decisions/current"');
});
