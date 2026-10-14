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
  };
});
import { HotspotSizingPanel } from "../src/components/HotspotSizingPanel";

beforeEach(() => {
  captured.fields.length = 0;
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
