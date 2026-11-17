import React from "react";
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { PublicOperatingResearchView } from "../src/components/LiveOperatingResearchPanel";
import { MainValuationRevalidationPanel } from "../src/components/MainValuationRevalidationPanel";
import type { MainValuationRevalidationRecord } from "../src/services/api";
const { renderToStaticMarkup } = require("react-dom/server");
function fixture(): MainValuationRevalidationRecord {
  const actual = {
    kind: "DERIVED_FACT",
    period_start: "2026-07-01",
    period_end: "2026-09-30",
    group_pbt_cny: "100000000.123456789",
    income_tax_cny: "25000000",
    signed_nci_cny: "1000",
  };
  const forecast = {
    kind: "FORECAST_ASSUMPTION",
    period_start: "2026-10-01",
    period_end: "2026-12-31",
    group_pbt_cny: "90000000",
    rationale: "TEST_ONLY_SEASONAL_ASSUMPTION",
  };
  const h1 = {
    ...forecast,
    period_start: "2027-01-01",
    period_end: "2027-06-30",
  };
  const scenarios = Object.fromEntries(
    ["bear", "base", "bull"].map((name) => [
      name,
      { q4_forecast: forecast, h1_next_forecast: h1, model_years: [] },
    ]),
  );
  const ledgers = Object.fromEntries(
    ["bear", "base", "bull"].map((name) => [
      name,
      {
        rows: Array.from({ length: 10 }, (_, i) => ({
          year: i + 1,
          period_start: 2026 + i + "-07-01",
          period_end: 2027 + i + "-06-30",
          profit: "100000000",
          accessible_profit: "50000000",
          mandatory_cash: "20000000",
          distribution: "30000000",
          closing_cash: "100000000",
          closing_book: "200000000",
        })),
      },
    ]),
  );
  return {
    schema_version: "main-valuation-revalidation-v1",
    symbol: "000568",
    status: "CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW",
    as_of: "2026-11-01",
    financial_basis: "2026-06-30",
    latest_actual_period: "2026-09-30",
    confidence: "low",
    policy_not_fully_modelled: true,
    action: "no_order",
    formal_eligibility: false,
    approval_changed: false,
    formal_fact_count: 0,
    current_comparable: false,
    quantity: null,
    personal_quantity: null,
    main_range_adopted: false,
    condition_price: null,
    period_assembly: { q3_actual: actual, scenarios },
    annual_ledgers: ledgers,
    valuation: {
      bear_value: "1.11",
      base_value: "2.22",
      bull_value: "3.33",
      valuation_date: "2026-11-01",
      confidence: "low",
    },
    cash_input_basis: {
      net_maintenance_ex_rou_proxy_cny: "1000000",
      wc_ex_payables_proxy_cny: "2000000",
      classification: "EXPLICIT_HYPOTHESIS_NOT_MAINTENANCE_FACT",
    },
    dated_research_review_thresholds: {
      status: "NOT_PREPARED",
      valuation_basis_date: "2026-06-30",
      reason: "ECONOMIC_REVIEW_THRESHOLD_RULES_NOT_SELECTED",
      rules: [],
      draft_prices: null,
      economic_approval: false,
      current_action_price: false,
    },
    parent_obligations: {
      effective_cash_floor: {
        cash_floor_cny: "20000000",
        current_capacity_proven: false,
      },
      per_scenario: {
        bear: {
          debt_book_reserve_cny: "10000000",
          reason: "TEST_ONLY_PARENT_OBLIGATION",
        },
      },
    },
    price_policy: { status: "NOT_PREPARED", rules: [], draft_prices: null },
    counter_evidence: ["TEST_ONLY_COUNTER_EVIDENCE"],
    unknowns: ["TEST_ONLY_CAPITAL_UNKNOWN"],
    source_spec: { path: "TEST_ONLY_spec.json", sha256: "a".repeat(64) },
    input_descriptor_sha256: "b".repeat(64),
  };
}
function render(value = fixture()) {
  return renderToStaticMarkup(
    <MainValuationRevalidationPanel value={value} symbol="000568" />,
  );
}
it("renders the coordinated source-bound candidate schema readably with Q3 actual, seasonal forecasts, ten-year cash and valuation while preserving no approval", () => {
  const value = fixture(),
    before = JSON.stringify(value),
    html = render(value);
  for (const text of [
    "条件研究工作候选，待人工经济复核；主区间尚未采用",
    "formal=false",
    "no_order",
    "current_comparable=false",
    "quantity=null",
    "Q3实际（9M－H1）",
    "由已报告期间差额派生（非预测）",
    "条件预测假设",
    "2026-09-30",
    "TEST_ONLY_SEASONAL_ASSUMPTION",
    "实际回传 10 行年度现金账",
    "归母利润（元）",
    "现金约束",
    "1.11",
    "2.22",
    "3.33",
    "置信度：低",
    "TEST_ONLY_PARENT_OBLIGATION",
    "TEST_ONLY_COUNTER_EVIDENCE",
    "TEST_ONLY_CAPITAL_UNKNOWN",
    "不证明当前可分配能力",
  ])
    expect(html).toContain(text);
  expect((html.match(/实际回传 10 行年度现金账/g) || []).length).toBe(3);
  expect(html).not.toContain("9.03");
  expect(html).toContain("带日期研究复核阈值（非当前行动价格）");
  expect(html).toContain("不扣使用权折旧的净维护代理");
  expect(html).toContain("显式假设，不是维护资本开支事实");
  expect(html).toContain("分红政策尚未完整建模，不能据此判断政策履约或违约");
  expect(JSON.stringify(value)).toBe(before);
});
it("does not invent thresholds when the actual coordinated first schema is NOT_PREPARED", () => {
  const html = render();
  expect(html).toContain("价格政策尚未准备");
  expect(html).toContain("没有阈值规则与理由，不补造条件价");
  expect(html).not.toContain("以下仅为带日期未批准条件阈值");
});
it.each([
  { action: "order" },
  { formal_eligibility: true },
  { approval_changed: true },
  { formal_fact_count: 1 },
  { symbol: "600519" },
  { current_comparable: true },
  { quantity: 100 },
  { personal_quantity: 100 },
  { main_range_adopted: true },
  { condition_price: "1" },
])(
  "rejects mismatched revalidation boundary %j without exposing its values",
  (change) => {
    const html = render({ ...fixture(), ...change });
    expect(html).toContain("停止展示");
    expect(html).not.toContain("1.11");
    expect(html).not.toContain("TEST_ONLY_SEASONAL_ASSUMPTION");
  },
);
it.each(["NOT_STARTED", "UNASSESSABLE"])(
  "keeps %s local and does not erase sibling D2 or cash content",
  (status) => {
    const html = renderToStaticMarkup(
      <>
        <p>TEST_ONLY_OLD_D2_CASH</p>
        <MainValuationRevalidationPanel
          value={{
            ...fixture(),
            status,
            reason: "TEST_ONLY_REVALIDATION_REASON",
          }}
          symbol="000568"
        />
      </>,
    );
    expect(html).toContain("TEST_ONLY_OLD_D2_CASH");
    expect(html).toContain(
      status === "NOT_STARTED"
        ? "尚无新的估值重验结果"
        : "新的估值重验暂不可核验",
    );
    expect(html).toContain("TEST_ONLY_REVALIDATION_REASON");
    expect(html).not.toContain("1.11");
  },
);
it("does not fill missing monetary values or cash years with zero and never recalculates model output", () => {
  const value = fixture();
  value.valuation = { bear_value: "123.456789", base_value: null };
  value.annual_ledgers = { bear: { rows: [] }, base: {}, bull: {} };
  const html = render(value);
  expect(html).toContain("123.46");
  expect(html).toContain("未知/空，不补零");
  expect(html).toContain("实际回传 0 行年度现金账");
  expect(html).not.toContain("实际回传 10 行年度现金账");
});
it("is pure display and stays under the existing explicit live-research entry", () => {
  const panel = readFileSync(
    "src/components/MainValuationRevalidationPanel.tsx",
    "utf8",
  );
  expect(panel).not.toMatch(/fetch\(|useEffect|useState|localStorage|api\./);
  const live = readFileSync(
    "src/components/LiveOperatingResearchPanel.tsx",
    "utf8",
  );
  expect(live).toContain('from "./MainValuationRevalidationPanel"');
  expect(live).toMatch(
    /task\.main_valuation_revalidation &&[\s\S]*?<MainValuationRevalidationPanel/,
  );
});

it("keeps an independent fresh candidate visible when saved live research is unavailable or never started", () => {
  for (const status of ["NOT_STARTED", "UNASSESSABLE"] as const) {
    const html = renderToStaticMarkup(
      <PublicOperatingResearchView
        symbol="000568"
        value={{
          symbol: "000568",
          action: "no_order",
          formal_eligibility: false,
          status,
          reason: "TEST_ONLY_OLD_LIVE_UNAVAILABLE",
          main_valuation_revalidation: fixture(),
        }}
      />,
    );
    expect(html).toContain("新的经营—现金—估值研究候选");
    expect(html).toContain("1.11");
    expect(html).toContain(
      status === "NOT_STARTED"
        ? "尚无已生成的公开经营研究"
        : "不回退展示旧成功结果",
    );
  }
});
it("leaves saved live empty-state unchanged when the optional independent candidate is absent", () => {
  const html = renderToStaticMarkup(
    <PublicOperatingResearchView
      symbol="000568"
      value={{
        symbol: "000568",
        action: "no_order",
        formal_eligibility: false,
        status: "NOT_STARTED",
      }}
    />,
  );
  expect(html).toContain("尚无已生成的公开经营研究");
  expect(html).not.toContain("新的经营—现金—估值研究候选");
});

it("shows actual settlement-schema totals as model-year assumptions separate from new shareholder distributions", () => {
  const value = fixture(),
    parent = value.parent_obligations as Record<string, unknown>;
  parent.per_scenario = Object.fromEntries(
    ["bear", "base", "bull"].map((name) => [
      name,
      {
        effective_cash_floor_cny: "11993444651.33",
        settlement_schedule: {
          classification: "NONPRODUCTIVE_LIABILITY_SETTLEMENT",
          initial_outstanding_cny: "11013375072.53",
          terminal_outstanding_cny: "0.00",
          new_shareholder_distribution: false,
          productive_capital_addition: false,
          maturity_dates_proven: false,
          rows: [
            {
              year: 1,
              opening_outstanding_cny: "11013375072.53",
              payment_cny: "11013375072.53",
              closing_outstanding_cny: "0.00",
              items: [
                {
                  obligation_id: "short_term_borrowings",
                  opening_balance_cny: "3001758333.34",
                  payment_cny: "3001758333.34",
                  closing_balance_cny: "0.00",
                },
                {
                  obligation_id: "current_noncurrent_liabilities",
                  opening_balance_cny: "1510049088.62",
                  payment_cny: "1510049088.62",
                  closing_balance_cny: "0.00",
                },
                {
                  obligation_id: "dividend_payable",
                  opening_balance_cny: "6501567650.57",
                  payment_cny: "6501567650.57",
                  closing_balance_cny: "0.00",
                },
              ],
            },
            {
              year: 2,
              opening_outstanding_cny: "0.00",
              payment_cny: "0.00",
              closing_outstanding_cny: "0.00",
              items: [],
            },
          ],
        },
      },
    ]),
  );
  const html = render(value);
  for (const text of [
    "11,013,375,072.53",
    "模型年1假定支付",
    "付款年是研究假设",
    "不是新分红或CapEx",
    "不与年度新distribution相加作为股东回报",
    "逐项与逐年清偿（opening/payment/closing）",
    "非生产性负债清偿",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("<details open");
  expect(html.indexOf("模型估值区间")).toBeLessThan(
    html.indexOf("新Q3实际与季节性条件预测"),
  );
  expect(html.indexOf("模型估值区间")).toBeLessThan(
    html.indexOf("十年现金与权益账"),
  );
  const live = readFileSync(
    "src/components/LiveOperatingResearchPanel.tsx",
    "utf8",
  );
  expect(live.indexOf("task.main_valuation_revalidation &&")).toBeLessThan(
    live.indexOf("task.cash_consumption &&"),
  );
  expect(live).toContain("无投资批准，主研究区间未采用，不生成条件价。");
});
it("shows partial scenario failures without inventing a complete valuation interval", () => {
  const value = fixture();
  value.status = "PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW";
  value.valuation = null;
  value.scenario_failures = {
    base: { status: "UNASSESSABLE", reason: "TEST_ONLY_INSUFFICIENT_CASH" },
  };
  const html = render(value);
  expect(html).toContain("整包未形成完整研究候选");
  expect(html).toContain("TEST_ONLY_INSUFFICIENT_CASH");
  expect(html).not.toContain("模型估值区间");
  expect(html).not.toContain("1.11");
});
it("shows real-engine draft metadata without numeric rules as an unapproved dated draft, not an available buy price", () => {
  const value = fixture();
  value.price_policy = {
    status: "NOT_PREPARED",
    rules: [],
    draft_prices: null,
    registered: false,
    formal_eligibility: false,
    economic_approval: false,
    current_action_prices: null,
    draft: {
      status: "DRAFT",
      action: "no_order",
      registered: false,
      effective_from: "2026-11-01",
      effective_through: "2026-12-31",
      rationale: "TEST_ONLY_DRAFT_REASONS",
      rules: [],
    },
    diagnostic_preview_prices: { BUY: null },
  };
  value.dated_research_review_thresholds = {
    status: "NOT_PREPARED",
    rules: [],
    draft_prices: null,
  };
  value.valuation = { ...(value.valuation as object), confidence: "��" };
  const html = render(value);
  for (const text of [
    "未批准、未注册草案",
    "2026-11-01",
    "2026-12-31",
    "TEST_ONLY_DRAFT_REASONS",
    "尚未选择数值规则，无当前买价",
    "不把估值区间复制为价格阈值",
    "估值置信度：低",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("��");
});
