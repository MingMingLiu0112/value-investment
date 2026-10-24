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
it("shows source-bound thesis and counter evidence without granting a trade", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        logic_card: {
          source_status: "BOUND_TO_REVERIFIED_PLAN",
          research_as_of: "2026-10-22",
          thesis: "cash generation",
          counter_evidence: ["demand weakens"],
          thesis_breakers: ["cash deteriorates"],
          source_bindings: [{ path: "facts.json", sha256: "a".repeat(64) }],
        },
      }}
    />,
  );
  expect(html).toContain("cash generation");
  expect(html).toContain("demand weakens");
  expect(html).toContain("cash deteriorates");
  expect(html).toContain("facts.json");
  expect(html).toContain("未给出个人可操作股数");
});
it("does not present unbound prose as verified investment logic", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        logic_card: {
          source_status: "NOT_SOURCE_BOUND",
          thesis: "unverified claim",
        },
      }}
    />,
  );
  expect(html).not.toContain("unverified claim");
});
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
          ownership_verified: true,
          held_quantity: "100",
          entry_thesis_record_sha256: "a".repeat(64),
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

it.each(["HOLD", "REDUCE", "EXIT"] as const)("refuses unowned %s", (action) => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        decision_action: action,
        blockers: [],
        review_quantity: action === "HOLD" ? null : 100,
      }}
    />,
  );
  expect(html).toContain("持仓动作依据不完整");
});

it.each(["HOLD", "REDUCE", "EXIT"] as const)(
  "renders owned %s only with lawful quantities",
  (action) => {
    const html = renderToStaticMarkup(
      <ActionableDecisionResult
        decision={{
          ...baseline,
          decision_action: action,
          blockers: [],
          review_quantity: action === "HOLD" ? null : 100,
          ownership_verified: true,
          held_quantity: "200",
          sellable_quantity: "100",
          entry_thesis_record_sha256: "a".repeat(64),
          decision_reason: "Original thesis comparison",
        }}
      />,
    );
    expect(html).toContain("Original thesis comparison");
    expect(html).not.toContain("NO_TRADE");
    expect(html).not.toContain("不提供操作结论");
  },
);

it("refuses a T+1 exit beyond sellable shares", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        decision_action: "EXIT",
        blockers: [],
        review_quantity: 200,
        ownership_verified: true,
        held_quantity: "200",
        sellable_quantity: "100",
        entry_thesis_record_sha256: "a".repeat(64),
      }}
    />,
  );
  expect(html).toContain("可卖数量不符");
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

it("distinguishes entry consistency from a newer broken thesis", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        original_thesis: "Original cash-flow thesis",
        entry_consistency_status: "CONSISTENT",
        consistency_status: "BROKEN",
      }}
    />,
  );
  expect(html).toContain("买入绑定时的一致性：原逻辑仍一致");
  expect(html).toContain("原逻辑与当前证据对比：原逻辑已破坏，需复核");
});

it("never presents original consistency as a current review", () => {
  const html = renderToStaticMarkup(
    <ActionableDecisionResult
      decision={{
        ...baseline,
        original_thesis: "Original cash-flow thesis",
        entry_consistency_status: "CONSISTENT",
      }}
    />,
  );
  expect(html).toContain("原逻辑与当前证据对比：尚未完成当前证据核验");
});
