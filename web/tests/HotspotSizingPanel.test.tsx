import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const captured = vi.hoisted(() => ({
  fields: [] as Record<string, any>[],
  submit: undefined as
    undefined | ((form: Record<string, unknown>) => Promise<boolean>),
}));
const reactState = vi.hoisted(() => ({
  use: null as
    | null
    | ((initial: unknown) => [unknown, (next: unknown) => void] | undefined),
}));
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) =>
      reactState.use?.(initial) ?? actual.useState(initial),
  };
});
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  return {
    ProForm: Object.assign(
      (props: Record<string, any>) => {
        captured.submit = props.onFinish;
        return React.createElement("div", null, props.children);
      },
      {
        Group: (props: Record<string, any>) =>
          React.createElement("div", null, props.children),
      },
    ),
    ProFormText: (props: Record<string, any>) => {
      captured.fields.push(props);
      return null;
    },
    ProFormSelect: () => null,
  };
});
vi.mock("antd", async () => {
  const React = await import("react");
  const wrapper = (props: Record<string, any>) =>
    React.createElement("div", null, props.children);
  return {
    Alert: (props: Record<string, any>) =>
      React.createElement("div", null, props.message, props.description),
    Checkbox: wrapper,
    Descriptions: (props: Record<string, any>) =>
      React.createElement(
        "div",
        null,
        (props.items ?? []).map((item: Record<string, any>) =>
          React.createElement(
            "div",
            { key: item.key },
            item.label,
            item.children,
          ),
        ),
      ),
    Typography: { Title: wrapper, Text: wrapper },
  };
});
import {
  HotspotSizingPanel,
  type HotspotSizingResponse,
} from "../src/components/HotspotSizingPanel";
import type { PrivateRiskContext } from "../src/components/PrivateRiskContext";

beforeEach(() => {
  captured.fields.length = 0;
});

it("CORE sends only tranche and buy-cost inputs, preserving the strategy boundary", async () => {
  const onPreview = vi.fn().mockResolvedValue({
    action: "no_order",
    sizing_preview: {
      symbol: "600519",
      review_quantity: null,
      blockers: [],
    },
  });
  const html = renderToStaticMarkup(
    <HotspotSizingPanel
      sleeve="CORE_VALUE"
      initialSymbol="600519"
      onPreview={onPreview}
    />,
  );
  expect(html).toContain("价值仓分批资金上限试算");
  expect(captured.fields.some((field) => field.name === "gap_stress_cny")).toBe(
    false,
  );
  expect(
    await captured.submit!({
      symbol: "600519",
      lot_size: "100",
      max_trade_notional_cny: "1000",
      entry_slippage_cny: "0",
      buy_fee_fraction: "0",
      minimum_buy_fee_cny: "1",
      gap_stress_cny: "999",
      entry_price_cny: "1",
      formal_eligibility: true,
    }),
  ).toBe(true);
  expect(onPreview).toHaveBeenCalledWith({
    symbol: "600519",
    sleeve: "CORE_VALUE",
    assumptions: {
      lot_size: "100",
      max_trade_notional_cny: "1000",
      entry_slippage_cny: "0",
      buy_fee_fraction: "0",
      minimum_buy_fee_cny: "1",
    },
  });
});

it("renders a positive CORE scenario as simulated shares while formal sizing remains null", () => {
  const response: HotspotSizingResponse = {
    action: "no_order",
    scenario_preview: {
      namespace: "TEST_ONLY",
      status: "AVAILABLE",
      review_quantity: 300,
      blockers: [],
      engine: {
        core_quantity_review: {
          cash_required_cny: "3000",
          tranche_budget_cny: "5000",
        },
      },
    },
    sizing_preview: {
      symbol: "600519",
      review_quantity: null,
      blockers: [],
      formal_eligibility: false,
      plan_binding: null,
    },
  };
  let hook = 0;
  reactState.use = () => (hook++ === 0 ? [response, vi.fn()] : undefined);
  let html = "";
  try {
    html = renderToStaticMarkup(
      <HotspotSizingPanel
        sleeve="CORE_VALUE"
        initialSymbol="600519"
        onPreview={vi.fn()}
      />,
    );
  } finally {
    reactState.use = null;
  }
  expect(html).toContain("价值仓分批资金上限试算");
  expect(html).toContain("假设情景数量，不是正式可操作股数");
  expect(html).toContain("SIMULATED：300 股");
  expect(html).toContain("条件性数量上限（股）");
  expect(html).toContain("暂不能计算");
  expect(html).not.toContain("正式可操作：300 股");
  expect(html).not.toContain("BUY");
});

it("submits only explicit assumptions, leaving prices and eligibility to the server", async () => {
  const onPreview = vi.fn().mockResolvedValue({
    action: "no_order",
    sizing_preview: {
      symbol: "300364",
      review_quantity: null,
      blockers: ["PRICE_LIMIT_STATE_UNKNOWN"],
    },
  });
  renderToStaticMarkup(
    <HotspotSizingPanel initialSymbol="300364" onPreview={onPreview} />,
  );
  expect(
    captured.fields
      .filter((field) => field.name !== "symbol")
      .every((field) => field.initialValue === undefined),
  ).toBe(true);
  expect(
    await captured.submit!({
      symbol: "300364",
      gap_stress_cny: "0.5",
      lot_size: "100",
      entry_price_cny: "1",
      formal_eligibility: true,
    }),
  ).toBe(true);
  expect(onPreview).toHaveBeenCalledWith({
    symbol: "300364",
    assumptions: {
      gap_stress_cny: "0.5",
      lot_size: "100",
    },
  });
});

it("can request explicit missing-input review without silently filling fees", async () => {
  const onPreview = vi.fn().mockResolvedValue({
    action: "no_order",
    sizing_preview: {
      symbol: "300364",
      review_quantity: null,
      blockers: ["ASSUMPTION_MISSING:lot_size"],
    },
  });
  renderToStaticMarkup(<HotspotSizingPanel onPreview={onPreview} />);
  await captured.submit!({ symbol: "300364" });
  expect(onPreview).toHaveBeenCalledWith({ symbol: "300364", assumptions: {} });
});

it("opts into display marks only in an explicitly selected simulated scenario", async () => {
  for (const selected of [false, true]) {
    let booleanState = 0;
    reactState.use = (initial) =>
      initial === false
        ? [++booleanState === 1 ? true : selected, () => {}]
        : undefined;
    const onPreview = vi.fn().mockResolvedValue({
      action: "no_order",
      sizing_preview: { symbol: "600693", review_quantity: null, blockers: [] },
    });
    try {
      renderToStaticMarkup(
        <HotspotSizingPanel initialSymbol="600693" onPreview={onPreview} />,
      );
      expect(
        await captured.submit!({
          symbol: "600693",
          scenario_liquid: "yes",
          scenario_limit_up: "no",
          scenario_limit_down: "no",
          cyclical_600693: "no",
        }),
      ).toBe(true);
      const request = onPreview.mock.calls[0][0];
      expect(request.scenario.acknowledged).toBe(true);
      expect(request.scenario.use_verified_display_marks).toBe(
        selected ? true : undefined,
      );
      expect(request).not.toHaveProperty("use_verified_display_marks");
      expect(request.assumptions).not.toHaveProperty("price_admitted");
    } finally {
      reactState.use = null;
    }
  }
});

it("rejects an unverified or failed response", async () => {
  for (const response of [
    { action: "order", sizing_preview: {} },
    { action: "no_order" },
  ]) {
    renderToStaticMarkup(
      <HotspotSizingPanel onPreview={vi.fn().mockResolvedValue(response)} />,
    );
    expect(await captured.submit!({ symbol: "300364" })).toBe(false);
  }
});

it("folds advanced inputs and only prefills confirmed unexpired costs", () => {
  const context: PrivateRiskContext = {
    action: "no_order",
    symbol: "300364",
    revision: 4,
    policy: { hotspot_budget_cny: "2000", hotspot_single_trade_risk_pct: "1" },
    cost_profile: {
      costs: { buy_fee_fraction: "0.0003" },
      confirmed_at: "2026-10-10T00:00:00Z",
      valid_until: "2099-01-01T00:00:00Z",
      record_sha256: "a".repeat(64),
    },
    verified_rules: {},
    rule_gaps: ["交易单位未知"],
  };
  const html = renderToStaticMarkup(
    <HotspotSizingPanel
      initialSymbol="300364"
      context={context}
      onPreview={vi.fn()}
    />,
  );
  expect(html).toContain("高级参数");
  expect(html).not.toContain("<details open");
  expect(html).toContain("已确认热点资金池");
  expect(
    captured.fields.find((field) => field.name === "buy_fee_fraction")
      ?.initialValue,
  ).toBe("0.0003");
  expect(
    captured.fields.find((field) => field.name === "lot_size")?.initialValue,
  ).toBeUndefined();
  expect(
    captured.fields.find((field) => field.name === "max_trade_notional_cny")
      ?.initialValue,
  ).toBeUndefined();
  captured.fields.length = 0;
  context.cost_profile!.valid_until = "2000-01-01T00:00:00Z";
  renderToStaticMarkup(
    <HotspotSizingPanel
      initialSymbol="300364"
      context={context}
      onPreview={vi.fn()}
    />,
  );
  expect(
    captured.fields.find((field) => field.name === "buy_fee_fraction")
      ?.initialValue,
  ).toBeUndefined();
});
