import React from "react";
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import {
  ProductContinuationCandidate,
  verifiedProductContinuationCandidate,
} from "../src/components/ProductContinuationCandidate";
import type { ProductContinuationCandidateReview } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");
const detailState = vi.hoisted(() => ({
  data: null as any,
  loading: false,
  error: undefined as string | undefined,
  retry: () => {},
}));
vi.mock("@umijs/max", () => ({
  useParams: () => ({ id: "600519" }),
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => detailState }));
// Keep this SSR check focused on the real detail mount and candidate; shell
// widgets and unrelated research panels have their own suites.
vi.mock("antd", () => {
  const Box = ({ children }: any) => <div>{children}</div>;
  const Alert = ({ message, description }: any) => (
    <div>
      {message}
      {description}
    </div>
  );
  return {
    Alert,
    Button: Box,
    Collapse: Box,
    Descriptions: Box,
    List: Box,
    Space: Box,
    Table: () => null,
    Tag: Box,
    Typography: { Title: Box, Text: Box, Paragraph: Box, Link: Box },
  };
});
vi.mock("../src/components/ValueResearchAnalysis", () => ({
  ValueResearchAnalysis: () => null,
}));
vi.mock("../src/components/HotspotLifecycleReview", () => ({
  HotspotLifecycleReview: () => null,
}));
vi.mock("../src/components/StrategyReadiness", () => ({
  StrategyReadinessPanel: () => null,
}));
vi.mock("../src/pages/DecisionDetail/ResearchDraftPanel", () => ({
  ResearchDraftPanel: () => null,
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: any) => <main>{children}</main>,
}));
vi.mock("../src/components/CurrentJudgment", () => ({
  JudgmentSummary: () => null,
  CurrentJudgmentChart: () => null,
}));
vi.mock("../src/pages/DecisionDetail/CurrentHolding", () => ({
  CurrentHolding: () => null,
}));
vi.mock("../src/pages/DecisionDetail/AgentResearchPanel", () => ({
  AgentResearchPanel: () => null,
}));
import DecisionDetail from "../src/pages/DecisionDetail";

// Source-dependent verification is opt-in. Never check runtime financial data
// into this fixture or silently substitute TEST_ONLY amounts for actual data.
const actualApiPath = process.env.PRODUCT_CONTINUATION_API_FIXTURE;
it.skipIf(!actualApiPath)(
  "SSR verifies the explicitly selected actual API candidate and detail",
  () => {
    const actual = JSON.parse(readFileSync(actualApiPath!, "utf8"));
    const value = actual.product_continuation_candidate;
    expect(actual.action).toBe("no_order");
    expect(verifiedProductContinuationCandidate(value, "600519")).toBe(true);
    expect(value.financial_periods).toEqual(["FY2025", "H1_2025", "H1_2026"]);
    const before = JSON.stringify(actual);
    const html = render(value);
    expect(html).toContain("FY2025 / H1_2025 / H1_2026");
    for (const s of value.scenarios) {
      expect(html).toContain(s.per_share_value);
      expect(s.cash_rows).toHaveLength(10);
      expect(s.operating_rows).toHaveLength(10);
      expect(html).toContain(s.cash_rows[9].closing_cash_cny);
      expect(html).toContain(s.terminal.terminal_equity_cash_value_cny);
    }
    expect(html.match(/<th scope="row">10<\/th>/g)).toHaveLength(3);
    detailState.data = actual;
    try {
      const detail = renderToStaticMarkup(<DecisionDetail />);
      expect(detail).toContain("600519 十年产品延续候选研究");
      expect(detail).toContain(value.scenarios[0].per_share_value);
    } finally {
      detailState.data = null;
    }
    expect(JSON.stringify(actual)).toBe(before);
  },
);

// TEST_ONLY structure, not a financial forecast or an economic approval.
function fixture(): ProductContinuationCandidateReview {
  const amounts = (keys: string[]) =>
    Object.fromEntries(keys.map((key) => [key, "1.234567890123456789"]));
  const binding = {
    path: "runtime/TEST_ONLY/candidate.json",
    sha256: "a".repeat(64),
  };
  return {
    schema_version: "product-continuation-candidate-review-v1",
    symbol: "600519",
    action: "no_order",
    status: "PENDING_ECONOMIC_REVIEW",
    confidence: "LOW",
    formal_eligibility: false,
    approval_changed: false,
    primary_approved: false,
    position_guidance: null,
    price_comparison_eligible: false,
    candidate_binding: binding,
    financial_basis: "2026-06-30",
    valuation_date: "2026-10-23",
    research_as_of: "2026-10-26",
    financial_periods: ["FY2025", "H12026"],
    economic_explanation: {
      strongest_counter_evidence: "TEST有依据的最强反证（非首项）",
      rationale: "TEST十年延续",
      cash_return_rationale: "TEST现金回报",
      terminal_rationale: "TEST终值理由",
      counter_evidence: ["TEST首项反证", "TEST另一反证"],
    },
    cash_conditions: {
      maintenance_rationale: "TEST维护",
      capacity_rationale: "TEST能力",
      cash_mapping_rationale: "TEST映射",
      terminal_distribution_rationale: "TEST分配条件",
    },
    research_case: {
      thesis: "TEST论点",
      return_driver: "TEST驱动",
      mispricing_hypothesis: "TEST错价假说",
      counter_evidence: [{ text: "TEST研究反证" }],
      thesis_breakers: [{ text: "TEST失效" }],
      next_events: [{ text: "TEST下一事件" }],
    },
    scenarios: (["bear", "base", "bull"] as const).map((scenario, i) => ({
      scenario,
      per_share_value: ["101.1234567890123456789", "202.2", "303.3"][i],
      cost_of_equity: ".07",
      operating_rows: Array.from({ length: 10 }, (_, i) => ({
        year: i + 1,
        ...amounts([
          "revenue",
          "cost",
          "other_pre_tax_balance",
          "legacy_pre_tax_profit",
          "effective_tax_rate",
          "parent_share",
          "net_parent_nonrecurring_difference",
          "legacy_ex_parent",
        ]),
        product_revenue_cny: amounts(["moutai", "series", "other"]),
        opening_product_reference_revenue_cny: amounts([
          "moutai",
          "series",
          "other",
        ]),
        expenses: amounts([
          "taxes_surcharges",
          "selling",
          "administration",
          "research",
        ]),
        drivers: amounts([
          "moutai_volume_growth",
          "moutai_realization_growth",
          "series_volume_growth",
          "series_realization_growth",
          "other_revenue_growth",
          "cost_ratio",
        ]),
      })),
      cash_rows: Array.from({ length: 10 }, (_, i) => ({
        year: i + 1,
        profit_cny: "400",
        distribution_cny: "360",
        opening_book_cny: "1000",
        closing_book_cny: "1040",
        opening_cash_cny: "600",
        closing_cash_cny: "640",
      })),
      terminal: {
        ...amounts([
          "legacy_profit_cny",
          "incremental_cash_income_cny",
          "next_profit_cny",
          "next_distribution_cny",
          "next_cash_cny",
          "next_book_cny",
          "terminal_ri_cny",
          "terminal_equity_cash_value_cny",
          "first_year_ri_cny",
        ]),
        status: "CONDITIONAL_TERMINAL_SUPPORTED",
        reasons: [],
        checks: Object.fromEntries(
          [
            "explicit_method",
            "explicit_product_continuation",
            "positive_product_and_total_profit",
            "no_unremitted_assets",
            "no_unpaid_selected_commitments",
            "no_new_funding",
            "net_maintenance_gap_zero",
            "no_recurring_wc_release_or_investment",
            "net_maintenance_wc_balanced",
            "full_funds_conversion",
            "supported_full_distribution",
            "cash_floor",
            "capacity_non_depleting",
          ].map((key) => [key, true]),
        ),
        policy: {
          method: "STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT",
          operating_continuation:
            "FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT",
          rationale: "TEST政策理由",
          distribution_constraint_rationale: "TEST终值分配约束",
          capital_cash_row: {
            year: 11,
            scope: "ordinary_owner_equivalent_cash_mapping",
            rationale: "TEST维护",
            funding_treatment:
              "NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING",
            maintenance_basis: "EXPLICIT_NET_GAP_ASSUMPTION",
            net_maintenance_gap_cny: "0",
            ...Object.fromEntries(
              [
                "project_cash_cny",
                "maintenance_project_overlap_cny",
                "operating_wc_increase_cny",
                "fund_call_cny",
                "other_noncash_adjustment_cny",
                "net_financing_cny",
              ].map((key) => [key, "0"]),
            ),
          },
          distribution_row: {
            year: 11,
            payout_ratio: "1",
            newly_withheld_fraction: "0",
            release_fraction: "0",
            reserve_transfer_fraction: "0",
            reserve_policy_rationale: "TEST留存",
            capacity_mapping_rationale: "TEST能力",
          },
        },
      },
    })),
    price_draft: null,
    price_draft_status: "NOT_PREPARED_ECONOMIC_OR_PRICE_BASIS_INSUFFICIENT",
    blockers: [
      "TEST经济现金依据不足",
      "TEST价格对齐未准入",
      "EXPLICIT_THRESHOLD_RATIONALE_AND_VALIDITY_NOT_SELECTED",
    ],
    source_bindings: [binding],
  };
}
const render = (value: unknown, symbol = "600519") =>
  renderToStaticMarkup(
    <ProductContinuationCandidate value={value} symbol={symbol} />,
  );

it("direct SSR shows all three original values, ten-year rows, terminal and evidence without an account", () => {
  const value = fixture();
  expect(verifiedProductContinuationCandidate(value, "600519")).toBe(true);
  const before = JSON.stringify(value);
  const html = render(value);
  for (const text of [
    "101.1234567890123456789",
    "202.2",
    "303.3",
    "LOW",
    "FY2025 / H12026",
    "2026-06-30",
    "2026-10-23",
    "2026-10-26",
    "不是批准主估值",
    "也不代表当前便宜",
    "公共研究展示不依赖账户",
    "TEST首项反证",
    "TEST有依据的最强反证（非首项）",
    "TEST研究反证",
    "TEST失效",
    "TEST下一事件",
    "TEST维护",
    "TEST能力",
    "TEST映射",
    "TEST分配条件",
    "为何没有价格草案",
    "terminal_equity_cash_value_cny",
    "next_distribution_cny",
    "distribution_constraint_rationale",
    "EXPLICIT_THRESHOLD_RATIONALE_AND_VALIDITY_NOT_SELECTED",
    "经济现金依据不足",
    "股本、财务期间、分配事件与当前报价尚未对齐",
    "未选定具体价格阈值、理由与有效期",
    "runtime/TEST_ONLY/candidate.json",
    "a".repeat(64),
  ])
    expect(html).toContain(text);
  expect(html.match(/<table>/g)).toHaveLength(3);
  expect(html.match(/<th scope="row">10<\/th>/g)).toHaveLength(3);
  expect(html.match(/<td>640<\/td>/g)).toHaveLength(30);
  expect(html).toContain("<details><summary>悲观：展开十年逐年经营与现金表");
  expect(html).not.toMatch(/<button|<input|数量/);
  expect(html).not.toContain("经济基础和价格基准均未获批准");
  expect(html).not.toContain("没有获批的显式价值到价格政策");
  expect(html).not.toContain("首项反证：");
  expect(JSON.stringify(value)).toBe(before);
});

it("formats only the display, keeps full precision in wrapped raw details and contains wide tables", () => {
  const value = fixture();
  value.scenarios[0].cash_rows[0].profit_cny = "1234567.891234567890123456789";
  const html = render(value);
  const table = html.match(/<table>[\s\S]*?<\/table>/)![0];
  expect(table).toContain("1,234,567.891");
  expect(table).toContain("<td>1.235</td>");
  expect(table).not.toContain("1234567.891234567890123456789");
  expect(table).not.toContain("1.234567890123456789");
  expect(html).toContain("悲观条件每股值：101.123");
  expect(html).toContain("1234567.891234567890123456789");
  expect(html).toContain("101.1234567890123456789");
  expect(html).toContain('style="overflow-x:auto;max-width:100%"');
  expect(html).toContain(
    'style="white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%"',
  );
  delete value.economic_explanation.strongest_counter_evidence;
  const unranked = render(value);
  expect(unranked).toContain("未排序反证");
  expect(unranked).not.toContain("最强反证");
  expect(unranked).not.toContain("首项反证：");
});

it.each([
  [
    "symbol",
    (v: any) => {
      v.symbol = "600887";
    },
  ],
  ...[
    "formal_eligibility",
    "approval_changed",
    "primary_approved",
    "price_comparison_eligible",
  ].map(
    (key) =>
      [
        key,
        (v: any) => {
          v[key] = true;
        },
      ] as const,
  ),
  [
    "action",
    (v: any) => {
      v.action = "buy";
    },
  ],
  [
    "status",
    (v: any) => {
      v.status = "APPROVED";
    },
  ],
  [
    "confidence",
    (v: any) => {
      v.confidence = "HIGH";
    },
  ],
  [
    "position",
    (v: any) => {
      v.position_guidance = { shares: 100 };
    },
  ],
  [
    "price",
    (v: any) => {
      v.price_draft = {};
    },
  ],
  [
    "price status",
    (v: any) => {
      v.price_draft_status = "READY";
    },
  ],
  [
    "obsolete price status",
    (v: any) => {
      v.price_draft_status = "NOT_PREPARED_ECONOMIC_AND_PRICE_BASIS_UNAPPROVED";
    },
  ],
  [
    "schema",
    (v: any) => {
      v.schema_version = "other-v1";
    },
  ],
  [
    "bad number",
    (v: any) => {
      v.scenarios[0].cash_rows[0].profit_cny = "NaN";
    },
  ],
  [
    "bad value",
    (v: any) => {
      v.scenarios[0].per_share_value = "Infinity";
    },
  ],
  [
    "numeric coercion",
    (v: any) => {
      v.scenarios[0].cash_rows[0].profit_cny = true;
    },
  ],
  [
    "bad Ke",
    (v: any) => {
      v.scenarios[0].cost_of_equity = "1";
    },
  ],
  [
    "bad operating",
    (v: any) => {
      v.scenarios[0].operating_rows[0].revenue = "0xFF";
    },
  ],
  [
    "missing ten years",
    (v: any) => {
      v.scenarios[0].cash_rows.pop();
    },
  ],
  [
    "missing operating year",
    (v: any) => {
      v.scenarios[0].operating_rows.pop();
    },
  ],
  [
    "duplicate year",
    (v: any) => {
      v.scenarios[0].cash_rows[9].year = 9;
    },
  ],
  [
    "duplicate scenario",
    (v: any) => {
      v.scenarios[1].scenario = "bear";
    },
  ],
  [
    "missing scenario",
    (v: any) => {
      v.scenarios.pop();
    },
  ],
  [
    "missing terminal field",
    (v: any) => {
      delete v.scenarios[0].terminal.next_book_cny;
    },
  ],
  [
    "bad terminal number",
    (v: any) => {
      v.scenarios[0].terminal.next_cash_cny = "1e999";
    },
  ],
  [
    "terminal failed check",
    (v: any) => {
      v.scenarios[0].terminal.checks.cash_floor = false;
    },
  ],
  [
    "terminal policy missing",
    (v: any) => {
      v.scenarios[0].terminal.policy.capital_cash_row = {};
    },
  ],
  [
    "terminal policy bad number",
    (v: any) => {
      v.scenarios[0].terminal.policy.distribution_row.payout_ratio = "NaN";
    },
  ],
  [
    "missing evidence",
    (v: any) => {
      v.source_bindings = [];
    },
  ],
  [
    "bad hash",
    (v: any) => {
      v.candidate_binding.sha256 = "fake";
    },
  ],
  [
    "bad date",
    (v: any) => {
      v.financial_basis = "2026-02-30";
    },
  ],
  [
    "no periods",
    (v: any) => {
      v.financial_periods = [];
    },
  ],
  [
    "missing counter",
    (v: any) => {
      v.economic_explanation.counter_evidence = [];
    },
  ],
  [
    "no breaker",
    (v: any) => {
      v.research_case.thesis_breakers = [];
    },
  ],
  [
    "bad event",
    (v: any) => {
      v.research_case.next_events = [null];
    },
  ],
] as [string, (v: any) => void][])("fails closed for %s", (_, mutate) => {
  const value = fixture();
  mutate(value);
  expect(verifiedProductContinuationCandidate(value, "600519")).toBe(false);
  const html = render(value);
  expect(html).toContain("不可核验");
  expect(html).not.toContain("101.1234567890123456789");
  expect(html).not.toContain("<table");
});

it("does not render absent candidates or accept another detail symbol", () => {
  expect(render(null)).toBe("");
  expect(render(undefined)).toBe("");
  expect(render(fixture(), "600887")).toContain("不可核验");
  expect(render([])).toContain("不可核验");
});

it("accepts matching legal symbols through the same generic contract", () => {
  const value = fixture();
  value.symbol = "600887";
  expect(verifiedProductContinuationCandidate(value, "600887")).toBe(true);
  expect(render(value, "600887")).toContain("600887 十年产品延续候选研究");
  for (const symbol of ["", "60088", "6008870", "ABCDEF"]) {
    value.symbol = symbol;
    expect(verifiedProductContinuationCandidate(value, symbol)).toBe(false);
  }
});

it("mounts the top-level API candidate in the existing detail even with no private account or price plan", () => {
  detailState.data = {
    action: "no_order",
    decision: { id: "600519", symbol: "600519", strategy: "CORE_VALUE" },
    product_continuation_candidate: fixture(),
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("600519 十年产品延续候选研究");
  expect(html).toContain("101.1234567890123456789");
  detailState.data.action = "buy";
  expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
    "十年产品延续候选研究",
  );
  detailState.data.action = "no_order";
  detailState.data.decision.symbol = "600887";
  expect(renderToStaticMarkup(<DecisionDetail />)).toContain("不可核验");
  detailState.data = null;
});
