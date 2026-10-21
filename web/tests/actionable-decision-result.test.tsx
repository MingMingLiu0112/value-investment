import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
import {
  ActionableDecisionResult,
  ConditionalAccountDecision,
} from "../src/components/ActionableDecisionResult";

const baseline: ConditionalAccountDecision = {
  action: "no_order",
  decision_action: "UNASSESSABLE",
  symbol: "600519",
  strategy: "CORE_VALUE",
  decision_reason: "Missing inputs",
  blockers: ["PRIVATE_PORTFOLIO_NOT_CONNECTED"],
  review_quantity: null,
  broker_execution_permission: false,
};
it("does not turn incomplete account inputs into buy quantities", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult decision={baseline} />,
  );
  expect(html).toContain("无法评价");
  expect(html).not.toContain("NO_TRADE");
  expect(html).toContain("未给出个人可操作股数");
});
it.each(["BUY", "ADD"] as const)(
  "renders verified conditional %s separately from an order",
  (action) => {
    const html = renderToStaticMarkup(
      <ActionableDecisionResult
        decision={{
          ...baseline,
          decision_action: action,
          review_quantity: 100,
          blockers: [],
        }}
      />,
    );
    expect(html).toContain("100");
    expect(html).toContain("券商软件决定并操作");
  },
);
it("rejects conflicting positive action and veto", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{ ...baseline, decision_action: "BUY", review_quantity: 100 }}
    />,
  );
  expect(html).toContain("动作与风险结果不一致");
  expect(html).not.toContain("100");
});

it("shows server-owned prices and exit conditions without inventing missing fees", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        entry_price_or_range: "12.50",
        plan_expiry: "2026-10-21",
        exit_condition: { rule: "结构失效后重新核验" },
        expected_fees_and_slippage: { buy_fee_fraction: "0.0003" },
      }}
    />,
  );
  expect(html).toContain("12.50");
  expect(html).toContain("2026-10-21");
  expect(html).toContain("结构失效后重新核验");
  expect(html).toContain("未提供");
});
