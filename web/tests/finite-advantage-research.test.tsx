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
    if (research.product_continuation) {
      expect(html).toContain("945.9748");
      expect(html).toContain("915.1998");
      expect(html).toContain("55.0%");
      if (research.product_continuation.sensitivity_cases?.length) {
        expect(html).toContain("936.6761");
        expect(html).toContain("819.2926");
        expect(html).toContain("811.713");
        expect(html).toContain("不是预测或买入价");
      }
    }
  },
);
it("shows conditional values and cash rejection without approved price claims", () => {
  const html = render(input());
  expect(html).toContain("483.0198");
  expect(html).toContain("现金低于研究储备底线");
  expect(html).toContain("不是买入价");
});

function withCenter(): Research {
  const r = input();
  r.product_continuation = {
    status: "SOURCE_BOUND_PRODUCT_CONTINUATION_NOT_APPROVED",
    action: "no_order",
    confidence: "LOW",
    formal_eligibility: false,
    economic_approval: false,
    price_admission: false,
    primary_valuation_changed: false,
    input_available_at: "2026-10-25T12:02:44Z",
    source_bindings: [{ path: "TEST_ONLY/center", sha256: "b".repeat(64) }],
    scenarios: ["bear", "base", "bull"].flatMap((scenario) =>
      ["FLAT_PRODUCT_CONTINUATION", "REALIZATION_AND_COST_CHALLENGE"].map(
        (branch) => ({
          scenario,
          branch,
          result: {
            status: "CONDITIONAL_PRODUCT_CONTINUATION_RESEARCH",
            action: "no_order",
            formal_eligibility: false,
            economic_approval: false,
            price_admission: false,
            primary_valuation_changed: false,
            valuation: {
              usable: true,
              per_share_cny:
                branch === "FLAT_PRODUCT_CONTINUATION"
                  ? "945.9748"
                  : "915.1998",
              terminal_value_pv_share: "0.550087",
              ri_ddm_residual_cny: "0E-35",
            },
            cash_rows: [
              {
                year: 1,
                legacy_profit_cny: "100",
                incremental_cash_income_cny: "0",
                profit_cny: "100",
                distribution_cny: "90",
                closing_cash_cny: "10",
              },
            ],
            blockers: [],
          },
        }),
      ),
    ),
  };
  return r;
}
it("keeps product-centered research separate from total-ROE fade challenges", () => {
  const html = render(withCenter());
  expect(html).toContain("经营延续中心假说");
  expect(html).toContain("945.9748");
  expect(html).toContain("55.0%");
  expect(html).toContain("483.0198");
});
it.each([
  "source",
  "future",
  "cash",
  "duplicate",
  "approval",
  "constructor",
  "toString",
])(
  "rejects bad center while preserving independent finite research: %s",
  (damage) => {
    const r = withCenter(),
      center = r.product_continuation!;
    if (damage === "source") center.source_bindings![0].sha256 = "x";
    if (damage === "future") center.input_available_at = "2999-01-01T00:00:00Z";
    if (damage === "cash")
      center.scenarios[0].result.cash_rows[0].profit_cny = "NaN";
    if (damage === "duplicate") center.scenarios[0] = center.scenarios[1];
    if (damage === "approval") center.formal_eligibility = true;
    if (["constructor", "toString"].includes(damage))
      center.scenarios[0].scenario = damage;
    const html = render(r);
    expect(html).toContain("暂不展示新金额");
    expect(html).not.toContain("945.9748");
    expect(html).toContain("483.0198");
  },
);
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
