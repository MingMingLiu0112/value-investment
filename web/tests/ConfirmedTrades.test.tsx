import React from "react";
import { expect, it, vi } from "vitest";
import type { PortfolioTrade } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const captured = vi.hoisted(() => ({
  table: undefined as Record<string, any> | undefined,
}));
vi.mock("@umijs/max", async () => {
  const React = await import("react");
  return {
    Link: (props: Record<string, any>) =>
      React.createElement("a", { href: props.to }, props.children),
  };
});
vi.mock("antd", async () => {
  const React = await import("react");
  return {
    Table: (props: Record<string, any>) => {
      captured.table = props;
      return null;
    },
    Tag: (props: Record<string, any>) =>
      React.createElement("span", null, props.children),
    Descriptions: (props: Record<string, any>) =>
      React.createElement(
        "div",
        null,
        props.items.map((row: any) =>
          React.createElement("div", { key: row.key }, row.label, row.children),
        ),
      ),
  };
});
vi.mock("../src/components/PositionTable", () => ({
  sleeveLabel: (value: string) => value,
}));
import { ConfirmedTrades } from "../src/components/ConfirmedTrades";

it("retains original execution facts and research binding when opening current review", () => {
  const trade: PortfolioTrade = {
    transaction_id: "isolated-only",
    symbol: "300364",
    exchange: "SZSE",
    side: "BUY",
    sleeve: "HOTSPOT_SATELLITE",
    quantity: "100",
    price_cny: "26.60",
    fees_cny: "5",
    trade_date: "2026-10-14",
    next_sell_session: "2026-10-15",
    confirmed_at: "2026-10-14T18:00:00+08:00",
    decision_id: "hotspot-300364",
    research_version: "original-frozen-version",
    record_sha256: "a".repeat(64),
  };
  const rows = [trade];
  renderToStaticMarkup(React.createElement(ConfirmedTrades, { trades: rows }));
  expect(captured.table!.dataSource).toEqual(rows);
  expect(captured.table!.dataSource).not.toBe(rows);
  const html = renderToStaticMarkup(
    captured.table!.expandable.expandedRowRender(trade),
  );
  expect(html).toContain("original-frozen-version");
  expect(html).toContain("/decisions/hotspot-300364");
  expect(html).toContain("不代表成交时版本");
  expect(html).toContain("原记录未提供");
  expect(rows[0].price_cny).toBe("26.60");
});
