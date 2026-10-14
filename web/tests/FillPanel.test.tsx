import React from "react";
import { beforeEach, expect, it, vi } from "vitest";

const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};

const captured = vi.hoisted(() => ({
  fields: [] as Record<string, any>[],
  submit: undefined as
    undefined | ((form: Record<string, unknown>) => Promise<void>),
  prepare: vi.fn().mockResolvedValue({}),
}));
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  const field = (props: Record<string, any>) => {
    captured.fields.push(props);
    return null;
  };
  return {
    ProForm: (props: Record<string, any>) => {
      captured.submit = props.onFinish;
      return React.createElement("div", null, props.children);
    },
    ProFormText: field,
    ProFormSelect: field,
    ProFormTextArea: field,
    ProFormDatePicker: field,
    ProFormDateTimePicker: field,
  };
});
vi.mock("../src/services/api", () => ({
  ApiError: class extends Error {},
  api: { prepareFill: captured.prepare },
}));
import { FillPanel, fillContextFromSearch } from "../src/components/FillPanel";

beforeEach(() => {
  captured.fields.length = 0;
  captured.prepare.mockClear();
});

it("reads candidate identity and strategy without accepting execution hints", () => {
  expect(
    fillContextFromSearch(
      "?symbol=600887&strategy=hotspot&decision_id=d1&research_version=v5&price_cny=25&quantity=100",
    ),
  ).toEqual({
    symbol: "600887",
    strategy: "HOTSPOT_SATELLITE",
    decision_id: "d1",
    research_version: "v5",
  });
  expect(
    fillContextFromSearch("?symbol=bad&strategy=bad").symbol,
  ).toBeUndefined();
  expect(fillContextFromSearch("?strategy=CORE_VALUE").strategy).toBe(
    "CORE_VALUE",
  );
});

it("requires actual execution inputs and submits the unchanged research reference", async () => {
  const done = vi.fn();
  renderToStaticMarkup(
    React.createElement(FillPanel, {
      revision: 4,
      draft: null,
      onDone: done,
      initialSymbol: "600887",
      initialSleeve: "HOTSPOT_SATELLITE",
      initialDecisionId: "d1",
      initialResearchVersion: "published-v5",
    }),
  );
  for (const name of ["price_cny", "quantity", "fees_cny", "trade_date"]) {
    const field = captured.fields.find((item) => item.name === name)!;
    expect(field.initialValue).toBeUndefined();
    expect(
      field.rules.some((rule: Record<string, unknown>) => rule.required),
    ).toBe(true);
  }
  expect(
    captured.fields.find((item) => item.name === "side")?.initialValue,
  ).toBeUndefined();
  expect(
    captured.fields.find((item) => item.name === "trading_unit")?.initialValue,
  ).toBeUndefined();
  await captured.submit!({
    transaction_id: "TEST",
    side: "BUY",
    sleeve: "HOTSPOT_SATELLITE",
    symbol: "600887",
    exchange: "SSE",
    quantity: "100",
    price_cny: "20",
    fees_cny: "0",
    trade_date: "2026-10-12",
    next_sell_session: "2026-10-13",
    trading_unit: "100",
  });
  expect(captured.prepare.mock.calls[0][0]).toMatchObject({
    expected_revision: 4,
    fill: {
      symbol: "600887",
      sleeve: "HOTSPOT_SATELLITE",
      decision_id: "d1",
      research_version: "published-v5",
      price_cny: "20",
      quantity: "100",
      fees_cny: "0",
      trade_date: "2026-10-12",
    },
  });
  expect(done).toHaveBeenCalledOnce();
});
