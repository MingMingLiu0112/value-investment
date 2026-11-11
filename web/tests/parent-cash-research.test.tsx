import React from "react";
import { expect, it } from "vitest";
import { ParentCashResearch } from "../src/components/ParentCashResearch";
import type { ParentCashResearch as Research } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");

function fixture(): Research {
  const sources = ["1", "2"].map((n) => ({
    path: `runtime/TEST_ONLY-${n}.pdf`,
    sha256: n.repeat(64),
    source_url: `https://static.cninfo.com.cn/finalpage/TEST_ONLY-${n}.PDF`,
  }));
  const statements = [
    ["FY2025", "FY2024"],
    ["H12026", "H12025"],
  ].map((periods, i) => ({
    symbol: "600887",
    periods,
    statement_scope: "listed_parent_only" as const,
    source_binding: sources[i],
    balances: periods.map((period) => ({
      period,
      opening_cash_and_equivalents_cny: "100",
      closing_cash_and_equivalents_cny: "110",
      cfo_cny: "20",
      cfi_cny: "-5",
      cff_cny: "-6",
      fx_cny: "1",
      reported_net_change_cny: "10",
      mixed_distribution_interest_paid_cny: "6",
      cash_residual_cny: "0E-10",
      movement_residual_cny: "0",
    })),
  }));
  return {
    schema_version: "parent-cash-research-v1",
    symbol: "600887",
    status: "SOURCE_REPLAYED_HISTORICAL_PARENT_CASH",
    action: "no_order",
    formal_eligibility: false,
    economic_approval: false,
    primary_valuation_usable: false,
    price_admitted: false,
    strategy_admitted: false,
    distribution_capacity_status: "UNKNOWN",
    future_distributable_cash_cny: null,
    ordinary_dividends_paid_cny: null,
    upstream_dividends_received_cny: null,
    parent_restricted_cash_cny: null,
    evaluated_at: "2026-10-25T08:00:00Z",
    continuity_status: "PASS",
    historical_cash_reconciliation_status: "PASS",
    source_bindings: sources,
    historical_statements: statements,
  };
}

it.each(["1E-999", "-1E-999"])(
  "does not round nonzero residual %s to zero",
  (value) => {
    const r = fixture();
    r.historical_statements[0].balances[0].cash_residual_cny = value;
    const html = renderToStaticMarkup(
      <ParentCashResearch research={r} symbol="600887" />,
    );
    expect(html).not.toContain("<table");
  },
);

it("rejects an altered comparative period even when balance labels match it", () => {
  const r = fixture();
  r.historical_statements[0].periods[1] = "FY2030";
  r.historical_statements[0].balances[1].period = "FY2030";
  expect(
    renderToStaticMarkup(<ParentCashResearch research={r} symbol="600887" />),
  ).not.toContain("<table");
});

it.each([
  "2099-01-01T00:00:00Z",
  "2026-02-30T00:00:00Z",
  "2026-10-25T25:00:00Z",
  "2026-10-25T08:00:00",
])("rejects invalid/future/unzoned revalidation time %s", (value) => {
  const r = fixture();
  r.evaluated_at = value;
  expect(
    renderToStaticMarkup(<ParentCashResearch research={r} symbol="600887" />),
  ).not.toContain("<table");
});

it("shows historical standalone cash without claiming payout capacity", () => {
  const html = renderToStaticMarkup(
    <ParentCashResearch research={fixture()} symbol="600887" />,
  );
  expect(html).toContain("母公司历史现金对账（元）");
  expect(html).toContain("半年现金流不年化");
  expect(html).toContain("分红能力仍未知");
  expect(html).toContain("不能全部算作普通股分红");
  expect(html).toContain("TEST_ONLY-1.PDF");
});

it.each([
  "symbol",
  "scope",
  "hash",
  "approval",
  "cash",
  "residual",
  "nan",
  "period",
  "empty",
])("rejects malformed or promoted cash %s", (fault) => {
  const r = fixture();
  if (fault === "symbol") r.symbol = "600519";
  if (fault === "scope")
    (r.historical_statements[0] as any).statement_scope = "consolidated";
  if (fault === "hash") r.source_bindings = [];
  if (fault === "approval") (r as any).economic_approval = true;
  if (fault === "cash") (r as any).future_distributable_cash_cny = "110";
  if (fault === "residual")
    r.historical_statements[0].balances[0].cash_residual_cny = "1";
  if (fault === "nan") r.historical_statements[0].balances[0].cfo_cny = "1E999";
  if (fault === "period")
    r.historical_statements[0].balances[0].period = "H12026";
  if (fault === "empty") r.historical_statements = [];
  const html = renderToStaticMarkup(
    <ParentCashResearch research={r} symbol="600887" />,
  );
  expect(html).not.toContain("<table");
  expect(html).toContain("未通过核验");
});
