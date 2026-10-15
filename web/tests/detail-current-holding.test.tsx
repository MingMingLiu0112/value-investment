import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PrivateStateHandle } from "../src/hooks/usePrivateState";
import type { PortfolioResponse } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");
const fixture = vi.hoisted(() => ({ state: {} as PrivateStateHandle }));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => fixture.state,
}));
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
import { CurrentHolding } from "../src/pages/DecisionDetail/CurrentHolding";
import {
  PersonalInvestmentPlan,
  PrivateValueDecision,
} from "../src/components/PrivateValueDecision";
import type { PolicyRegistration } from "../src/services/valuePolicy";

const decision = {
  id: "hotspot-current",
  symbol: "601318",
  strategy: "HOTSPOT_SATELLITE",
  research: { research_version: "bound-v7" },
} as any;
const portfolio = {
  status: "CONNECTED",
  as_of: "2026-10-15",
  cash_cny: "8765",
  positions: [
    {
      symbol: "601318",
      quantity: "300",
      average_cost_cny: "12.34",
      cost_cny: "3702",
      market_value_cny: null,
      weight_pct: null,
      sleeves: [
        {
          sleeve: "CORE_VALUE",
          quantity: "100",
          sellable_quantity: "100",
          next_sell_session: null,
        },
        {
          sleeve: "HOTSPOT_SATELLITE",
          quantity: "200",
          sellable_quantity: "0",
          next_sell_session: "2026-10-16",
        },
      ],
    },
  ],
} as PortfolioResponse;

describe("detail current personal holding", () => {
  beforeEach(() => {
    fixture.state = {
      kind: "CONNECTED",
      label: "已接入",
      detail: "",
      blockers: [],
      portfolio,
      retry: vi.fn(),
    };
  });
  it("keeps cost and both sleeves without inventing market value or sell permission", () => {
    const html = renderToStaticMarkup(<CurrentHolding decision={decision} />);
    expect(html).toContain("已确认持有 300 股");
    expect(html).toContain("3,702.00");
    expect(html).toContain("价值池");
    expect(html).toContain("情绪卫星仓");
    expect(html).toContain("可卖 0 股");
    expect(html).toContain("2026-10-16");
    expect(html).toContain("市值 未核验");
    expect(html).toContain("个人风险尚未读取成功");
    expect(html).toContain("symbol=601318");
    expect(html).toContain("strategy=hotspot");
    expect(html).toContain("decision_id=hotspot-current");
    expect(html).toContain("research_version=bound-v7");
    expect(html).not.toMatch(/(?:price|quantity)=/);
  });
  it.each(["LOCKED", "UNAVAILABLE", "LOADING", "NOT_CONNECTED"] as const)(
    "never exposes retained private facts in %s state",
    (kind) => {
      fixture.state.kind = kind;
      const html = renderToStaticMarkup(<CurrentHolding decision={decision} />);
      expect(html).toContain("当前是否持仓未知");
      expect(html).not.toContain("8,765");
      expect(html).not.toContain("已确认持有");
      expect(html).not.toContain("未记录该证券持仓");
    },
  );
  it("distinguishes a readable empty holding from an unknown ledger", () => {
    fixture.state.portfolio = { ...portfolio, positions: [] };
    const html = renderToStaticMarkup(<CurrentHolding decision={decision} />);
    expect(html).toContain("当前已确认台账未记录该证券持仓");
    expect(html).not.toContain("当前是否持仓未知");
  });
});

it("keeps personal arithmetic, observed conditions, risk eligibility and execution separate", () => {
  const registered = {
    status: "REGISTERED",
    scope: "ISOLATED_TEST",
    registered_policy: {
      draft: {
        effective_from: "2026-10-15",
        effective_through: "2026-10-30",
        rationale: "TEST_ONLY",
        dividend_coverage_risk: "待核验",
        rules: [],
      },
      draft_prices: {},
    },
    conditional_plan: {
      research_version: "bound-v7",
      model_version: "model-v2",
      decision_as_of: "2026-10-15",
      entry_condition: { triggered: true },
      add_condition: { triggered: false },
      exit_condition: { triggered: null },
      blockers: [],
    },
  } as unknown as PolicyRegistration;
  const html = renderToStaticMarkup(
    <PersonalInvestmentPlan symbol="600887" registered={registered} />,
  );
  expect(html).toContain("我的投资计划");
  expect(html).toContain("bound-v7");
  expect(html).toContain("model-v2");
  expect(html).toContain("建仓已满足价格条件，仍须独立核验资格");
  expect(html).toContain("加仓未满足价格条件");
  expect(html).toContain("退出尚未核验");
  expect(html).toContain("政策登记不代表已经成交");
  expect(html).toContain("symbol=600887");
  expect(html).toContain("research_version=bound-v7");
  expect(html).toContain('href="/history"');
});

it("does not render a personal plan or registration before an authenticated read", () => {
  const status = vi.fn();
  const html = renderToStaticMarkup(
    <PrivateValueDecision
      symbol="600887"
      transport={{ status, preview: vi.fn(), confirm: vi.fn() }}
    />,
  );
  expect(html).not.toContain("我的投资计划");
  expect(html).not.toContain("本人政策已登记");
  expect(status).not.toHaveBeenCalled();
});
