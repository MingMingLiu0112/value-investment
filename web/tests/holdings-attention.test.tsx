import React from "react";
import { expect, it, vi } from "vitest";
import type { PrivateStateHandle } from "../src/hooks/usePrivateState";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) =>
    React.createElement("a", { href: to }, children),
}));
import { HoldingsAttention } from "../src/components/HoldingsAttention";
import type { DecisionItem } from "../src/types/api";

it("surfaces observed conditional reduction only for verified current held securities", () => {
  const state = {
    portfolio: {
      status: "CONNECTED",
      cash_cny: "100",
      positions: [{ symbol: "300059" }],
    },
    risk: { blockers: [] },
  } as unknown as PrivateStateHandle;
  const item = {
    id: "hotspot-300059",
    symbol: "300059",
    strategy: "HOTSPOT_SATELLITE",
    price_action_plan: {
      action: "no_order",
      signal_state: "WATCH",
      conditional_action_rules: { REDUCE: { observed: true } },
    },
  } as DecisionItem;
  const view = (decisions: DecisionItem[], verified = true) =>
    renderToStaticMarkup(
      <HoldingsAttention
        state={state}
        decisions={decisions}
        decisionsVerified={verified}
      />,
    );
  expect(view([item])).toContain("已出现策略退出或减仓复核事项");
  expect(view([item])).toContain("/decisions/hotspot-300059");
  expect(view([item], false)).not.toContain("已出现策略退出或减仓复核事项");
  expect(view([{ ...item, symbol: "600887" }])).not.toContain(
    "已出现策略退出或减仓复核事项",
  );
  expect(
    view([
      {
        ...item,
        price_action_plan: {
          ...item.price_action_plan!,
          signal_state: "STALE",
        },
      },
    ]),
  ).not.toContain("已出现策略退出或减仓复核事项");
});

it("locked state does not imply empty or healthy portfolio", () => {
  const state = {
    kind: "LOCKED",
    label: "已锁定",
    retry: () => {},
  } as PrivateStateHandle;
  const html = renderToStaticMarkup(
    <HoldingsAttention state={state} decisions={[]} />,
  );
  expect(html).toContain("连接我的持仓");
  expect(html).toContain("不能判断你的仓位或风险");
  expect(html).not.toContain("持仓正常");
});
it("missing model evidence alone does not become a sell alert", () => {
  const state = {
    portfolio: {
      status: "CONNECTED",
      cash_cny: "100",
      positions: [{ symbol: "600887" }],
    },
    risk: { blockers: ["MODEL_VALIDITY_UNKNOWN"] },
  } as unknown as PrivateStateHandle;
  const html = renderToStaticMarkup(
    <HoldingsAttention
      state={state}
      decisionsVerified={true}
      decisions={[{ id: "600887", symbol: "600887", status: "BLOCKED" }]}
    />,
  );
  expect(html).toContain("缺少研究数据不等于应当卖出");
  expect(html).not.toContain("已出现策略退出或减仓复核事项");
});
it("unverified public decisions do not imply no exit review", () => {
  const state = {
    portfolio: { status: "CONNECTED", cash_cny: "100", positions: [] },
    risk: { blockers: [] },
  } as unknown as PrivateStateHandle;
  const html = renderToStaticMarkup(
    <HoldingsAttention state={state} decisions={[]} />,
  );
  expect(html).toContain("策略复核未知");
  expect(html).not.toContain("未发现新增退出复核");
});

it("retains a held security outside all daily candidates with sellability and data gaps", () => {
  const state = {
    portfolio: {
      status: "CONNECTED",
      cash_cny: "100",
      positions: [{ symbol: "300364" }],
    },
    risk: { blockers: [] },
    heldContinuity: {
      action: "no_order",
      items: [
        {
          symbol: "300364",
          quantity: "200",
          sellable_quantity: "100",
          selected_today: false,
          review_priority: 0,
          review_reasons: ["INVALIDATION_OR_EXIT_REVIEW"],
          data_gaps: ["CURRENT_STRATEGY_PLAN_UNAVAILABLE"],
          strategy_plan: null,
        },
      ],
    },
  } as unknown as PrivateStateHandle;
  const html = renderToStaticMarkup(
    <HoldingsAttention state={state} decisions={[]} decisionsVerified />,
  );
  expect(html).toContain("不在今日榜单，继续按实际持仓跟踪");
  expect(html).toContain("优先复核减仓/退出");
  expect(html).toContain("当前结构数据未覆盖");
  expect(html).toContain("/portfolio?symbol=300364");
  expect(html).toContain("不能认定持仓正常。");
  expect(html).not.toContain("未发现新增退出复核");
});
