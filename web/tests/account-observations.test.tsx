import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({
  data: null as any,
  error: null,
  loading: false,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state }));
vi.mock("../src/services/api", () => ({
  api: { accountObservations: () => null },
}));
import { ActualAccountObservations } from "../src/components/ActualAccountObservations";

it("keeps actual observations separate from orders and current market quotes", () => {
  state.data = {
    action: "no_order",
    unavailable_count: 0,
    accounts: [
      {
        account_label: "TEST_ONLY",
        snapshot_date: "2026-10-23",
        displayed_clock_time: "09:58",
        active_trading_ledger: false,
        trade_eligible: false,
        snapshot_sha256: "a".repeat(64),
        observed_totals: { total_assets_cny: "1005", available_funds_cny: "5" },
        holdings: [],
        reconciliation: {
          header_market_value_minus_rows_cny: "0",
          total_assets_minus_header_market_value_and_available_funds_cny: "0",
        },
      },
    ],
  };
  const html = renderToStaticMarkup(<ActualAccountObservations />);
  expect(html).toContain("TEST_ONLY");
  expect(html).toContain("不是实时行情");
  expect(html).toContain("不生成可操作股数");
  state.data.accounts[0].trade_eligible = true;
  expect(renderToStaticMarkup(<ActualAccountObservations />)).not.toContain(
    "TEST_ONLY",
  );
});
it("does not treat another account contract as an observation", () => {
  state.data = { action: "no_order", cash_cny: "10000" };
  expect(renderToStaticMarkup(<ActualAccountObservations />)).toBe("");
});
