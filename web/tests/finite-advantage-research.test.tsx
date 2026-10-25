import React from "react";
import { expect, it } from "vitest";
import { FiniteAdvantageResearch } from "../src/components/FiniteAdvantageResearch";
import type { FiniteAdvantageResearch as Research } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");

function input(): Research {
  return {
    schema_version: "finite-advantage-research-v1",
    symbol: "600519",
    status: "SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED",
    action: "no_order",
    scope: "ordinary_owner_equivalent_cash_mapping",
    currency: "CNY",
    confidence: "LOW",
    formal_eligibility: false,
    economic_approval: false,
    price_admission: false,
    input_available_at: "2026-10-25T11:25:48Z",
    basis_date: "2026-06-30",
    primary_valuation_changed: false,
    price_condition_cny: null,
    source_bindings: [
      { path: "TEST_ONLY/source.json", sha256: "a".repeat(64) },
    ],
    branches: [
      {
        scenario: "base",
        branch: "BALANCED_NET_MAINTENANCE",
        fade_years: 5,
        net_maintenance_gap_cny: "0",
        result: {
          status: "CONDITIONAL_RESEARCH_VALUATION",
          action: "no_order",
          formal_eligibility: false,
          economic_approval: false,
          price_admission: false,
          blockers: [],
          valuation: {
            usable: true,
            per_share_cny: "483.0198",
            ri_ddm_residual_cny: "-1E-37",
          },
          rows: [
            {
              year: 1,
              profit_cny: "100",
              distribution_cny: "90",
              closing_cash_cny: "30",
              closing_book_cny: "110",
            },
          ],
        },
      },
      {
        scenario: "base",
        branch: "PERSISTENT_10_PERCENT_UNREMITTED",
        fade_years: 5,
        net_maintenance_gap_cny: "0",
        result: {
          status: "VALUATION_UNSUPPORTED",
          action: "no_order",
          formal_eligibility: false,
          economic_approval: false,
          price_admission: false,
          blockers: ["YEAR_5_CASH_FLOOR"],
          valuation: {
            usable: false,
            per_share_cny: null,
            ri_ddm_residual_cny: null,
          },
          rows: [],
        },
      },
    ],
  };
}
const render = (r: Research) =>
  renderToStaticMarkup(
    <FiniteAdvantageResearch research={r} symbol="600519" />,
  );

it.skipIf(!process.env.FINITE_ADVANTAGE_API_JSON)(
  "renders actual retained-source API research",
  () => {
    const packet = JSON.parse(
      require("node:fs").readFileSync(
        process.env.FINITE_ADVANTAGE_API_JSON!,
        "utf-8",
      ),
    );
    const research = packet.decision.price_action_plan.research_analysis
      .finite_advantage_research as Research;
    const html = render(research);
    expect(html).toContain("483.0198");
    expect(html).toContain("559.5433");
    expect(html).toContain("现金低于研究储备底线");
    expect(html).not.toContain("暂不展示金额");
  },
);
it("shows conditional values and cash rejection without approved price claims", () => {
  const html = render(input());
  expect(html).toContain("483.0198");
  expect(html).toContain("现金低于研究储备底线");
  expect(html).toContain("不是买入价");
});
it.each([
  "symbol",
  "currency",
  "approved",
  "source",
  "future",
  "residual",
  "status",
  "basis_date",
])("rejects invalid research %s", (damage) => {
  const r = input();
  if (damage === "symbol") r.symbol = "000333";
  if (damage === "currency") r.currency = "USD";
  if (damage === "approved") r.formal_eligibility = true;
  if (damage === "source") r.source_bindings![0].sha256 = "x";
  if (damage === "future") r.input_available_at = "2999-01-01T00:00:00Z";
  if (damage === "residual")
    r.branches[0].result.valuation.ri_ddm_residual_cny = "0.1";
  if (damage === "status") r.branches[0].result.status = "APPROVED";
  if (damage === "basis_date") r.basis_date = "2026-02-31";
  const html = render(r);
  expect(html).toContain("暂不展示金额");
  expect(html).not.toContain("483.0198");
});
