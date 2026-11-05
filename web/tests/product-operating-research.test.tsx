import React from "react";
import { expect, it } from "vitest";
import { EconomicReviewResult } from "../src/components/SourceNativeEconomicReview";
import { verifiedProductOperatingResearch } from "../src/services/sourceNativeEconomicReview";
import { economicFixture } from "./fixtures/sourceNativeEconomic";
const { renderToStaticMarkup } = require("react-dom/server");

function fixture() {
  const parent = economicFixture();
  const policy = {
    path: "config/TEST_ONLY-policy.json",
    sha256: "b".repeat(64),
  };
  const source = {
    path: "runtime/TEST_ONLY-report.pdf",
    sha256: "c".repeat(64),
  };
  parent.source_bindings.push(policy, source);
  const drivers = Array.from({ length: 5 }, () => ({
    moutai_volume_growth: ".01",
    moutai_realization_growth: "0",
    series_volume_growth: "0",
    series_realization_growth: "-.05",
    other_revenue_growth: "0",
    cost_ratio: ".1",
  }));
  parent.product_operating_research = {
    schema_version: "product-operating-research-v1",
    status: "CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED",
    symbol: "600519",
    confidence: "LOW",
    action: "no_order",
    formal_eligibility: false,
    research_admitted: false,
    price_admitted: false,
    normalized_parent_profit_cny: null,
    assumption_scope: "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST",
    input_available_at: "2026-10-24T12:00:00+00:00",
    evaluated_at: "2026-10-24T13:00:00+00:00",
    policy_binding: policy,
    source_bindings: [policy, source],
    product_source: {
      period: "H12026",
      physical_page: 8,
      source_binding: source,
      source_url:
        "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF",
      product_revenue_cny: { moutai: "100", series: "20", other: "1" },
    },
    annual_drivers: { bear: drivers, base: drivers, bull: drivers },
    scenarios: ["bear", "base", "bull"].map((scenario) => ({
      scenario,
      per_historical_share_cny: "91",
      ke_plus_200bp_per_historical_share_cny: "71",
      cash_replay_scope: "ALL_TRANSITIONS_VERIFIED_BY_EXISTING_NATIVE_KERNEL",
      operating_rows: Array.from({ length: 5 }, (_, i) => ({
        year: i + 1,
        revenue: "1000000000",
        legacy_ex_parent: "400000000",
      })),
      annual_cash_rows: Array.from({ length: 5 }, (_, i) => ({
        year: i + 1,
        profit: "410000000",
        cash_close: "600000000",
        dividend_paid: "369000000",
        book_close: "2000000000",
      })),
    })),
  };
  return parent;
}

it("shows product assumptions, recomputed profit/cash and conditions in the existing review", () => {
  const parent = fixture();
  expect(
    verifiedProductOperatingResearch(parent.product_operating_research, parent),
  ).toBe(true);
  const html = renderToStaticMarkup(<EconomicReviewResult value={parent} />);
  for (const text of [
    "产品经营路径",
    "单位实现额",
    "归母利润假设",
    "母公司期末现金",
    "实际TTM产品收入仍未知",
    "复核触发",
  ])
    expect(html).toContain(text);
  expect(html).toContain("未成为正式估值或操作价格");
});

it.each([
  "approved",
  "missing_year",
  "duplicate_scenario",
  "fake_source",
  "future",
  "nan",
  "other_issuer",
])(
  "withholds new economic values with invalid research contract: %s",
  (fault) => {
    const parent = fixture();
    const value = parent.product_operating_research;
    if (fault === "approved") value.formal_eligibility = true;
    if (fault === "missing_year") value.scenarios[0].annual_cash_rows.pop();
    if (fault === "duplicate_scenario") value.scenarios[1].scenario = "bear";
    if (fault === "fake_source") parent.source_bindings.pop();
    if (fault === "future")
      value.input_available_at = "2099-01-01T00:00:00+00:00";
    if (fault === "nan") value.scenarios[1].per_historical_share_cny = "NaN";
    if (fault === "other_issuer") parent.symbol = "600887";
    expect(verifiedProductOperatingResearch(value, parent)).toBe(false);
    const html = renderToStaticMarkup(<EconomicReviewResult value={parent} />);
    expect(html).not.toContain("产品经营与现金联动研究");
  },
);
