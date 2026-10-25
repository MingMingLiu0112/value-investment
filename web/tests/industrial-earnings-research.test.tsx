import React from "react";
import { expect, it } from "vitest";
import { IndustrialEarningsResearch } from "../src/components/IndustrialEarningsResearch";
import type { IndustrialEarningsResearch as Research } from "../src/types/api";

const { renderToStaticMarkup } = require("react-dom/server");
function research(): Research {
  const row = (year: number) => ({
    year,
    currency: "CNY" as const,
    revenue_cny: "1000",
    commercial_subtotal_cny: "150",
    inventory_impairment_cny: "10",
    goodwill_impairment_cny: "20",
    other_asset_impairment_cny: "1",
    other_pbt_cny: "30",
    group_pbt_cny: "149",
    income_tax_cny: "40",
    signed_nci_cny: "-5",
    parent_profit_cny: "114",
    bridge_residual_cny: "0",
    change_from_historical_parent: {
      commercial_subtotal_change_cny: "1",
      asset_impairment_change_cny: "2",
      other_pbt_change_cny: "3",
      income_tax_change_cny: "-4",
      signed_nci_change_cny: "-5",
      parent_profit_change_cny: "-3",
      residual_cny: "0",
    },
  });
  const sources = [0, 1].map((i) => ({
    source_id: `TEST_ONLY-${i}`,
    path: `runtime/TEST_ONLY-${i}.pdf`,
    sha256: String(i + 1).repeat(64),
    source_url: `https://static.cninfo.com.cn/finalpage/TEST_ONLY-${i}.PDF`,
  }));
  const policy = {
    path: "config/TEST_ONLY-policy.json",
    sha256: "a".repeat(64),
  };
  return {
    schema_version: "industrial-earnings-research-v1",
    symbol: "600887",
    status: "CONDITIONAL_EARNINGS_RESEARCH_NOT_APPROVED",
    action: "no_order",
    confidence: "LOW",
    context_scope: "INDEPENDENT_SOURCE_BOUND_RESEARCH_NOT_CURRENT_VALUATION",
    formal_eligibility: false,
    primary_valuation_usable: false,
    price_admitted: false,
    strategy_admitted: false,
    economic_approval: false,
    normalized_parent_profit_cny: null,
    input_available_at: "2026-10-25T07:54:47Z",
    evaluated_at: "2026-10-25T08:00:00Z",
    financial_basis: "2026-06-30",
    rationale: "TEST_ONLY经营研究",
    tax_convention: "不赋予商誉税盾",
    counter_evidence: ["TEST_ONLY反证"],
    thesis_breakers: ["TEST_ONLY失效条件"],
    unknowns: ["现金仍未知"],
    policy_binding: policy,
    source_bindings: [policy, ...sources],
    official_sources: sources,
    scenarios: {
      bear: { rationale: "TEST_ONLY保守", rows: [1, 2, 3, 4, 5].map(row) },
      base: { rationale: "TEST_ONLY基准", rows: [1, 2, 3, 4, 5].map(row) },
      bull: { rationale: "TEST_ONLY乐观", rows: [1, 2, 3, 4, 5].map(row) },
    },
  };
}

it("shows explicit loss/tax/signed-NCI paths and independent countercase without admission", () => {
  const html = renderToStaticMarkup(
    <IndustrialEarningsResearch research={research()} symbol="600887" />,
  );
  expect(html).toContain("未来利润依赖什么");
  expect(html).toContain("少数股东损益");
  expect(html).toContain("商誉损失");
  expect(html).toContain("不产生买卖价");
  expect(html).toContain("前瞻经营情景");
  expect(html).toContain("TEST_ONLY基准");
  expect(html).toContain("TEST_ONLY反证");
});

it("accepts finite Decimal exponent strings returned by the real Python API", () => {
  const r = research();
  for (const scenario of Object.values(r.scenarios)) {
    for (const row of scenario.rows) {
      row.bridge_residual_cny = "0E-10";
      row.change_from_historical_parent.residual_cny = "0E-10";
    }
  }
  const html = renderToStaticMarkup(
    <IndustrialEarningsResearch research={r} symbol="600887" />,
  );
  expect(html).toContain("归母变化来源（元）");
  expect(html).not.toContain("尚未通过来源或假设核验");
});

it.each(["1E999", "0E-10junk", "NaN", "Infinity"])(
  "rejects invalid or nonfinite Decimal amount %s",
  (value) => {
    const r = research();
    r.scenarios.base.rows[0].parent_profit_cny = value;
    const html = renderToStaticMarkup(
      <IndustrialEarningsResearch research={r} symbol="600887" />,
    );
    expect(html).not.toContain("<table");
  },
);

it.each([
  "approval",
  "price",
  "source",
  "nan",
  "year",
  "future",
  "wrong-symbol",
  "residual",
])("rejects malformed or promoted research: %s", (fault) => {
  const r = research();
  if (fault === "approval") (r as any).economic_approval = true;
  if (fault === "price") (r as any).price_admitted = true;
  if (fault === "source") r.source_bindings = [r.policy_binding];
  if (fault === "nan") r.scenarios.base.rows[0].parent_profit_cny = "NaN";
  if (fault === "year") r.scenarios.bear.rows.pop();
  if (fault === "future") r.input_available_at = "2027-01-01T00:00:00Z";
  if (fault === "wrong-symbol") r.symbol = "600519";
  if (fault === "residual") r.scenarios.base.rows[0].bridge_residual_cny = "1";
  const html = renderToStaticMarkup(
    <IndustrialEarningsResearch research={r} symbol="600887" />,
  );
  expect(html).not.toContain("<table");
  expect(html).toContain("尚未通过来源或假设核验");
});
