import React from "react";
import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import type {
  FirstResearchInputResponse,
  FirstResearchScenarioKey,
} from "../src/services/api";

const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({ value: {} as any }));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state.value }));
import {
  FirstResearchInputPanel,
  FirstResearchInputView,
} from "../src/components/FirstResearchInputPanel";

function base(symbol = "000568"): FirstResearchInputResponse {
  return {
    symbol,
    status: "NOT_STARTED",
    scope: "CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
    action: "no_order",
    formal_eligibility: false,
    main_range_adopted: false,
    main_valuation_range: null,
    current_price: null,
    condition_price: null,
    personal_quantity: null,
  };
}
function example(): FirstResearchInputResponse {
  const ledger = () => ({
    funding_status: "FUNDED",
    rows10: Array.from({ length: 10 }, (_, index) => ({
      year: index + 1,
      profit: "10000000.00",
      distribution: "6000000.00",
      retained: "4000000.00",
    })),
  });
  return {
    ...base(),
    status: "SOURCE_BOUND_FIRST_INPUT_COMPILED",
    company_name: "TEST_ONLY泸州老窖",
    financial_basis: "2026-06-30",
    research_as_of: "2026-10-31",
    research_case: {
      symbol: "000568",
      name: "TEST_ONLY泸州老窖",
      thesis: "TEST_ONLY条件研究论点，不证明经济主区间",
      counter_evidence: [{ text: "TEST_ONLY渠道压力可能持续" }],
      thesis_breakers: [{ text: "TEST_ONLY经营与资本假设失效须重审" }],
      next_events: ["TEST_ONLY下一期官方披露再核验"],
    },
    annual_ledgers: { bear: ledger(), base: ledger(), bull: ledger() },
    valuation: {
      bear_value: "11.11",
      base_value: "22.22",
      bull_value: "33.33",
      confidence: "LOW",
      valuation_date: "2026-10-31",
    },
    source_bindings: [
      { path: "runtime/TEST_ONLY/first-spec.json", sha256: "a".repeat(64) },
    ],
    input_fingerprint: "b".repeat(64),
    native_fact_count: 30,
    sources: [
      {
        id: "TEST_ONLY_OFFICIAL",
        officialURL: "https://example.org/TEST_ONLY-official.pdf",
        sha256: "c".repeat(64),
      },
    ],
    operating_assumptions: {
      choice: { rationale: "TEST_ONLY共用压力假设理由" },
      scenarios: {
        bear: { rationale: "TEST_ONLY渠道压力持续理由" },
        base: { rationale: "TEST_ONLY逐步稳定理由" },
        bull: { rationale: "TEST_ONLY有条件修复理由" },
      },
    },
  };
}
it("shows verified partial cash rows without calling missing values zero or reconciled", () => {
  const data = example();
  data.parent_cash_observation = {
    status: "SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS",
    action: "no_order",
    future_cash_proven: false,
    whole_statement_reconciled: false,
    periods: [
      {
        report_period: "2026-06-30",
        rows: {
          cfo_cny: {
            label: "TEST_ONLY经营现金",
            statement_scope: "listed_parent_only",
            currency: "CNY",
            unit: "CNY",
            physical_page: 35,
            columns: [{ period: "H12026", value: "123456.78" }],
          },
        },
        unknown_fields: { fx_cny: "EMPTY_PRINTED_COLUMN" },
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("123,456.78");
  expect(html).toContain("未完成全表勾稽");
  expect(html).toContain("EMPTY_PRINTED_COLUMN");
  expect(html).not.toContain("母公司现金原件尚未完成独立核验");
  expect(html).not.toContain("TTM流量（FY");
  data.parent_cash_observation.whole_statement_reconciled = true;
  const invalid = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(invalid).toContain("部分现金观察边界不符");
  expect(invalid).not.toContain("123,456.78");
});

function visibleHtml(html: string): string {
  let depth = 0;
  return html
    .split(/(<\/?details\b[^>]*>)/)
    .map((part) => {
      if (/^<details\b/.test(part)) {
        depth++;
        return "";
      }
      if (/^<\/details\b/.test(part)) {
        depth--;
        return "";
      }
      return depth === 0 ? part : "";
    })
    .join("");
}

// Contract fixture only: no backend/live E2/F1/F2 acceptance is implied.
function directFixture(): FirstResearchInputResponse {
  return {
    ...base(),
    status: "SOURCE_BOUND_FIRST_INPUT_COMPILED",
    scope: "TEST_ONLY_DIRECT_OWNER_CASH",
    main_range_adopted: true,
    main_valuation_range: { low: "11.11", high: "33.33" },
    valuation: example().valuation,
    direct_owner_cash: {
      method: "TEST_ONLY_RI_DDM",
      valuation_basis: "TEST_ONLY_HISTORICAL_PARENT",
      scope: "TEST_ONLY_CONDITIONAL",
      annual_rows: Object.fromEntries(
        ["bear", "base", "bull"].map((name) => [
          name,
          [
            {
              year: 2027,
              direct_operating_cash_cny: "123456789.123456789",
              conditional_distribution_cny: "0",
              closing_cash_cny: "123",
              closing_book_equity_cny: "456",
              closing_debt_cny: "789",
              retention_assumption: `TEST_ONLY_${name}_RETENTION`,
            },
          ],
        ]),
      ) as NonNullable<
        FirstResearchInputResponse["direct_owner_cash"]
      >["annual_rows"],
      assumptions: [
        {
          name: "TEST_ONLY_CAPITAL",
          rationale: "TEST_ONLY_RATIONALE",
          counter_evidence: "TEST_ONLY_COUNTER",
        },
      ],
      conditional_price: {
        status: "TEST_ONLY_DRAFT",
        draft_prices: {
          entry: "7.125",
          add: "8.25",
          reduce: "9.375",
          exit: null,
        },
        reason_codes: ["TEST_ONLY_NOT_APPROVED"],
        expires_at: "2026-12-01",
        currentpricecomparison: false,
        action: "no_order",
      },
      source_refs: [{ source_sha256: "TEST_ONLY_HASH", physical_page: 7 }],
    },
  };
}

it("shows a bound remaining-year CFO split without promoting its owner calculation to a price", () => {
  const data = directFixture();
  data.receipt_binding = {
    path: "runtime/TEST_ONLY-direct.json",
    sha256: "a".repeat(64),
  };
  data.input_descriptor_sha256 = "b".repeat(64);
  data.main_range_adopted = false;
  data.direct_owner_cash!.remaining_year_review = {
    schema_version: "parent-remaining-year-review-v1",
    symbol: data.symbol,
    candidate_binding: data.receipt_binding,
    input_descriptor_sha256: data.input_descriptor_sha256,
    action: "no_order",
    formal_eligibility: false,
    successor_adopted: false,
    current_price_qualified: false,
    status: "PARTIAL_CONDITIONAL_RESEARCH",
    capital_policy_mode: "REPORTED_9M_PLUS_PRIOR_Q4",
    reported_facts: {
      period_start: "2026-01-01",
      period_end: "2026-09-30",
      period_basis: "YTD_9M",
      scope: "ISSUER_PARENT_STANDALONE",
      currency: "CNY",
      cash_fields: { cfo: { current: "39649908007.27" } },
    },
    scenarios: {
      base: {
        status: "CONDITIONAL_RECALCULATION_NOT_ADOPTED",
        annual: {
          full_year: {
            cfo: {
              fact_9m: "39649908007.27",
              forecast_q4: "-5414707226.13",
              total: "34235200781.14",
              fact_classification: "FACT",
              forecast_classification: "FORECAST_ASSUMPTION",
            },
          },
        },
        calculation: { per_share_value: "DO_NOT_RENDER_VALUE" },
        reported_9m_parent_profit: "11224391992.81",
        retained_annual_parent_profit: "12000000000",
        implied_q4_parent_profit: "775608007.19",
        economic_review: {
          classification: "RETAINED_PLAN_STRESS_NOT_NEW_EARNINGS_FORECAST",
          adopted: false,
          warnings: ["TEST_ONLY_Q4_PROFIT_STRESS_REQUIRES_REVIEW"],
          explanation: "旧计划净利不是新盈利预测",
          next_evidence: "TEST_ONLY_NEW_PARENT_REPORT",
        },
        capital_policy_changes: {
          gross_capex: {
            classification: "FORECAST_ASSUMPTION",
            fact_9m: "1410074492.50",
            assumed_q4: "281437265.21",
            rationale: "上年第四季度支出仅作条件假设",
          },
        },
      },
      bear: { status: "REJECTED", reason: "TEST_ONLY_EXACT_SOURCE_MISSING" },
      bull: { status: "REJECTED", reason: "TEST_ONLY_Q4_ASSUMPTION_INVALID" },
    },
  };
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol={data.symbol} />,
  );
  expect(html).toContain("九个月事实＋条件第四季度");
  expect(html).toContain("39,649,908,007.27");
  expect(html).toContain("-5,414,707,226.13");
  expect(html).toContain("34,235,200,781.14");
  expect(html).toContain("上年第四季度支出仅作条件假设");
  expect(html).toContain("第四季度条件 CFO 为负");
  expect(html).toContain("隐含第四季度净利 775,608,007.19 元");
  expect(html).toContain("旧全年母公司净利目标 12,000,000,000.00 元");
  expect(html).toContain("仅为保留计划压力重算，不是新的盈利预测");
  expect(html).toContain("不是已认可的 Base");
  expect(html).toContain("TEST_ONLY_Q4_PROFIT_STRESS_REQUIRES_REVIEW");
  expect(html).toContain("TEST_ONLY_NEW_PARENT_REPORT");
  expect(html).toContain("TEST_ONLY_EXACT_SOURCE_MISSING");
  expect(html).toContain("TEST_ONLY_Q4_ASSUMPTION_INVALID");
  expect(html).toContain("不是已采纳 E1、主估值区间或当前买价");
  expect(html).not.toContain("DO_NOT_RENDER_VALUE");
  data.direct_owner_cash!.remaining_year_review.candidate_binding = {
    path: data.receipt_binding.path,
    sha256: "c".repeat(64),
  };
  const mismatched = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol={data.symbol} />,
  );
  expect(mismatched).toContain("年度现金更新身份不符，停止展示");
  expect(mismatched).not.toContain("34,235,200,781.14");
});

it("shows the bound source-or-research rejection reason without scenario cash", () => {
  const data = directFixture();
  data.receipt_binding = {
    path: "runtime/TEST_ONLY-direct.json",
    sha256: "a".repeat(64),
  };
  data.input_descriptor_sha256 = "b".repeat(64);
  data.direct_owner_cash!.remaining_year_review = {
    schema_version: "parent-remaining-year-review-v1",
    symbol: data.symbol,
    candidate_binding: data.receipt_binding,
    input_descriptor_sha256: data.input_descriptor_sha256,
    status: "SOURCE_OR_RESEARCH_REJECTED",
    reason: "TEST_ONLY_EXACT_RECEIPT_SOURCE_REJECTED",
    scenarios: {},
    current_price_qualified: false,
    action: "no_order",
    successor_adopted: false,
    formal_eligibility: false,
  };
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol={data.symbol} />,
  );
  expect(html).toContain("年度现金更新来源或研究未通过核验");
  expect(html).toContain("TEST_ONLY_EXACT_RECEIPT_SOURCE_REJECTED");
  expect(html).not.toContain("九个月事实＋条件第四季度");
  expect(html).not.toContain("全年条件 CFO");
});

function successorFixture(): FirstResearchInputResponse {
  const data = directFixture();
  const receipt = {
    path: "runtime/TEST_ONLY-successor.json",
    sha256: "a".repeat(64),
  };
  const predecessor = {
    path: "runtime/TEST_ONLY-predecessor.json",
    sha256: "b".repeat(64),
  };
  data.receipt_binding = receipt;
  data.receipt_schema_version = "parent-remaining-year-successor-receipt-v1";
  data.predecessor_binding = predecessor;
  data.input_descriptor_sha256 = "c".repeat(64);
  data.main_range_adopted = false;
  data.main_valuation_range = null;
  data.current_price = null;
  data.condition_price = null;
  data.direct_owner_cash!.conditional_price = null;
  data.direct_owner_cash!.assumptions = { bear: {}, base: {}, bull: {} };
  data.direct_cash_alignment = {
    schema_version: "direct-owner-cash-alignment-v1",
    status: "BLOCKED",
    action: "no_order",
    formal_eligibility: false,
    currentpricecomparison: false,
    reason_codes: ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"],
  } as FirstResearchInputResponse["direct_cash_alignment"];
  const annual = Object.fromEntries(
    (["bear", "base", "bull"] as const).map((name) => [
      name,
      {
        symbol: data.symbol,
        action: "no_order" as const,
        formal_eligibility: false as const,
        scope: "ISSUER_PARENT_STANDALONE",
        currency: "CNY",
        current_nine_months: {
          period_start: "2026-01-01",
          period_end: "2026-09-30",
          classification: "FACT" as const,
          cfo: "40",
        },
        conditional_q4: {
          period_start: "2026-10-01",
          period_end: "2026-12-31",
          classification: "FORECAST_ASSUMPTION" as const,
          cfo: name === "base" ? "60" : "20",
        },
        full_year: {
          cfo: {
            total: name === "base" ? "100" : "60",
            fact_9m: "40",
            forecast_q4: name === "base" ? "60" : "20",
            fact_classification: "FACT" as const,
            forecast_classification: "FORECAST_ASSUMPTION" as const,
          },
        },
        annualized_nine_months: false as const,
      },
    ]),
  ) as NonNullable<FirstResearchInputResponse["annual_recalculations"]>;
  data.annual_recalculations = annual;
  data.direct_owner_cash!.remaining_year_review = {
    schema_version: "parent-remaining-year-successor-receipt-v1",
    status: "SOURCE_BOUND_CONDITIONAL_SUCCESSOR",
    symbol: data.symbol,
    candidate_binding: receipt,
    predecessor_binding: predecessor,
    input_descriptor_sha256: data.input_descriptor_sha256,
    action: "no_order",
    formal_eligibility: false,
    successor_adopted: false,
    current_price_qualified: false,
    annual_recalculations: annual,
    scenarios: { bear: {}, base: {}, bull: {} },
  };
  return data;
}

it("shows bound successor annual facts, Q4 forecast and yearly cash without a price", () => {
  const data = successorFixture();
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol={data.symbol} />,
  );
  expect(html).toContain("九个月事实＋条件第四季度：全年现金后继研究");
  expect(html).toContain("九个月经营现金事实 40.00 元");
  expect(html).toContain("第四季度条件预测 60.00 元");
  expect(html).toContain("全年条件经营现金 100.00 元");
  expect(html).toContain("逐年现金账 1 年");
  expect(html).toContain("EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING");
  expect(html).toContain("未采纳");
  expect(html).toContain("不是买价");
  expect(html).not.toContain("建仓条件价");
  expect(html).not.toContain("7.13");
});

it.each([
  "symbol",
  "candidate",
  "predecessor",
  "descriptor",
  "adoption",
  "forecast",
])(
  "rejects tampered successor %s before showing cash or valuation",
  (fault) => {
    const data = successorFixture();
    const review = data.direct_owner_cash!.remaining_year_review!;
    if (review.schema_version !== "parent-remaining-year-successor-receipt-v1")
      throw new Error("fixture schema");
    if (fault === "symbol") review.symbol = "000333";
    if (fault === "candidate")
      review.candidate_binding = {
        ...review.candidate_binding,
        sha256: "d".repeat(64),
      };
    if (fault === "predecessor")
      review.predecessor_binding = {
        ...review.predecessor_binding,
        sha256: "e".repeat(64),
      };
    if (fault === "descriptor") review.input_descriptor_sha256 = "f".repeat(64);
    if (fault === "adoption")
      (review as unknown as { successor_adopted: boolean }).successor_adopted =
        true;
    if (fault === "forecast")
      review.annual_recalculations.base.full_year.cfo.forecast_classification =
        "FACT" as "FORECAST_ASSUMPTION";
    const html = renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol={data.symbol} />,
    );
    expect(html).toMatch(/年度现金更新身份不符|年度现金更新事实或预测分类不符/);
    expect(html).not.toContain("全年条件经营现金 100.00 元");
    expect(html).not.toContain("逐年现金账 1 年");
    expect(html).not.toContain("建仓条件价");
  },
);

it.each([false, true])(
  "shows direct receipt alignment and refuses another candidate identity (successor=%s)",
  (successor) => {
    const data = directFixture();
    data.receipt_binding = {
      path: "runtime/TEST_ONLY-receipt.json",
      sha256: "a".repeat(64),
    };
    data.input_descriptor_sha256 = "b".repeat(64);
    data.financial_basis = "2025-12-31";
    if (successor)
      data.receipt_schema_version =
        "parent-owner-distribution-successor-receipt-v2";
    data.direct_cash_alignment = {
      schema_version: successor
        ? "parent-owner-distribution-alignment-v2"
        : "direct-owner-cash-alignment-v1",
      research_artifact_kind: successor
        ? "PARENT_OWNER_DISTRIBUTION_SUCCESSOR_RECEIPT"
        : "DIRECT_OWNER_CASH_RECEIPT",
      receipt_binding: data.receipt_binding,
      candidate_binding: data.receipt_binding,
      input_descriptor_sha256: data.input_descriptor_sha256,
      valuation_date: data.financial_basis,
      action: "no_order",
      formal_eligibility: false,
      status: "BLOCKED",
      currentpricecomparison: false,
      reason_codes: ["TEST_ONLY_MISSING_PERIOD_DISTRIBUTIONS"],
      checks: [
        {
          id: "distributions",
          status: "BLOCKED",
          reason_codes: ["TEST_ONLY_PERIOD_GAP"],
          explanation: "TEST_ONLY期间分配未核验",
        },
      ],
    };
    const render = () =>
      renderToStaticMarkup(
        <FirstResearchInputView data={data} symbol="000568" />,
      );
    expect(render()).toContain("TEST_ONLY期间分配未核验");
    expect(render()).not.toContain("当前研究比较口径已核验");
    data.direct_cash_alignment.candidate_binding = {
      ...data.receipt_binding,
      sha256: "c".repeat(64),
    };
    expect(render()).toContain("当前对齐证据与候选/输入/估值日期不匹配");
    expect(render()).not.toContain("TEST_ONLY期间分配未核验");
    expect(render()).toContain("TEST_ONLY_RATIONALE");
  },
);

it("shows dated financing issuance only when a source-bound review exists", () => {
  const data = directFixture();
  const render = () => {
    state.value = { loading: false, data };
    return visibleHtml(
      renderToStaticMarkup(<FirstResearchInputPanel symbol="000568" />),
    );
  };
  expect(render()).not.toContain("融资条件仍待核实");
  data.direct_owner_cash!.financing_review = {
    basis_date: "2025-12-31",
    post_basis_issuance_cny: "41500000000",
    post_basis_issue_codes: ["TEST_ONLY_ISSUE"],
    opening_debt_verified: false,
    outstanding_or_refinancing_verified: false,
    reason: "POST_BASIS_ISSUANCE_IS_NOT_OPENING_DEBT_OR_CONFIRMED_REFINANCING",
    source_refs: [{ path: "runtime/TEST_ONLY/financing.pdf" }],
    opening_debt_evidence_comparison: {
      scope: "PARENT_IDENTIFIED_BALANCE_LINES_NOT_COMPLETE_DEBT_VERIFICATION",
      period: "2025-12-31",
      forecast_opening_debt_cny: "60000000000",
      identified_parent_balance_lines_cny: "19527101262.17",
      unexplained_difference_cny: "40472898737.83",
      included_fields: ["short_term_borrowings_cny"],
      source_refs: [{ path: "runtime/TEST_ONLY/annual.pdf" }],
      completeness_verified: false,
      maturity_schedule_verified: false,
    },
    parent_financing_followup: {
      schema_version: "parent-financing-bridge-v1",
      period_start: "2025-12-31",
      period_end: "2026-06-30",
      opening_identified_balance_cny: "19527101262.17",
      closing_identified_balance_cny: "10454024794.97",
      identified_balance_change_cny: "-9073076467.20",
      reported_net_borrowing_cash_cny: "-18679564874.81",
      unallocated_reconciliation_difference_cny: "9606488407.61",
      reconciliation_status: "PARTIAL_SCOPE_NOT_BALANCED",
      complete_debt_scope_verified: false,
      maturity_schedule_verified: false,
      actual_refinancing_capacity_verified: false,
      source_refs: [{ path: "runtime/TEST_ONLY/interim.pdf" }],
    },
    first_year_no_new_borrowing_stress: {
      bear: {
        year: 2026,
        removed_assumed_new_borrowing_cny: "60000000000",
        cash_before_distribution_without_new_borrowing_cny: "-44439085119.35",
        minimum_funding_gap_to_cash_floor_cny: "57843672496.10",
        scope: "CONDITIONAL_FIRST_YEAR_NO_NEW_BORROWING_NO_DISTRIBUTION_STRESS",
      },
      base: {
        year: 2026,
        removed_assumed_new_borrowing_cny: "60000000000",
        cash_before_distribution_without_new_borrowing_cny: "-41143159088.89",
        minimum_funding_gap_to_cash_floor_cny: "54547746465.64",
        scope: "CONDITIONAL_FIRST_YEAR_NO_NEW_BORROWING_NO_DISTRIBUTION_STRESS",
      },
      bull: {
        year: 2026,
        removed_assumed_new_borrowing_cny: "60000000000",
        cash_before_distribution_without_new_borrowing_cny: "-40027622299.01",
        minimum_funding_gap_to_cash_floor_cny: "53432209675.76",
        scope: "CONDITIONAL_FIRST_YEAR_NO_NEW_BORROWING_NO_DISTRIBUTION_STRESS",
      },
    },
    annual_financing_dependency: {
      schema_version: "parent-financing-dependency-v1",
      valuation_date: "2025-12-31",
      scope: "ANNUAL_SINGLE_YEAR_COUNTERFACTUAL_HOLDING_MODELED_OPENING_STATE",
      actual_refinancing_capacity_verified: false,
      main_valuation_recomputed: false,
      followup_observation_date: "2026-06-30",
      followup_rebases_historical_valuation: false,
      scenarios: {
        bear: [],
        base: [
          {
            year: 2026,
            assumed_new_borrowing_cny: "60000000000",
            minimum_borrowing_to_preserve_cash_floor_cny: "54547746465.64",
            minimum_borrowing_to_preserve_modeled_distribution_cny:
              "60000000000",
            modeled_distribution_cny: "5452253534.36",
            assumption_dependent: true,
          },
        ],
        bull: [],
      },
    },
  };
  expect(render()).toContain("融资条件仍待核实");
  expect(render()).toContain("41,500,000,000.00");
  expect(render()).toContain("不能证明基准日母公司期初债务");
  expect(render()).toContain("54,547,746,465.64");
  expect(render()).toContain("不证明全部债务当年到期");
  expect(render()).toContain("19,527,101,262.17");
  expect(render()).toContain("列示额并非完整有息负债");
  expect(render()).toContain("9,606,488,407.61");
  expect(render()).toContain("尚未分解的对账差异");
  expect(render()).toContain("若维持原条件分配");
  expect(render()).toContain("未据半年报重算历史估值");
});

it("renders direct cash fixture through the existing panel with visible historical valuations and conditional prices", () => {
  const data = directFixture();
  const before = JSON.stringify(data);
  state.value = { loading: false, data };
  const html = renderToStaticMarkup(
    <FirstResearchInputPanel symbol="000568" />,
  );
  const visible = visibleHtml(html);
  for (const value of [
    "直接母公司经营现金→资本/债务支付→约束分配→RI/DDM",
    "11.11",
    "22.22",
    "33.33",
    "建仓条件价：7.13",
    "8.25",
    "减仓条件价：9.38",
    "退出条件价：未形成",
    "2026-10-31",
    "2026-12-01",
    "未批准",
    "不是当前买价",
    "no_order",
    "已采用（研究字段",
    "TEST_ONLY_COUNTER",
  ])
    expect(visible).toContain(value);
  expect(html).not.toContain("REJECTED");
  expect(html).not.toContain("中间条件场景未被采用");
  expect(html).not.toContain("<details open");
  expect(visible).not.toContain("123456789.123456789");
  for (const value of [
    "123456789.123456789",
    "TEST_ONLY_bear_RETENTION",
    "TEST_ONLY_base_RETENTION",
    "TEST_ONLY_bull_RETENTION",
    "TEST_ONLY_HASH",
    "期末账面权益",
    "期末债务",
  ])
    expect(html).toContain(value);
  expect(JSON.stringify(data)).toBe(before);
});

it("formats direct prices while keeping exact originals collapsed and assumptions sequential", () => {
  const data = directFixture();
  data.main_range_adopted = false;
  data.valuation!.bear_value = "1234.56789123456789";
  data.valuation!.base_value = "2345.6789123456789";
  data.valuation!.bull_value = "3456.789123456789";
  const cash = data.direct_owner_cash!;
  cash.conditional_price!.draft_prices = {
    entry: "123.456789123456",
    add: null,
    reduce: "345.678912345678",
    exit: "456.789123456789",
  };
  cash.assumptions = [
    {
      name: "假设1",
      rationale: "TEST_ONLY_FIRST",
      counter_evidence: "TEST_ONLY_COUNTER",
    },
    {
      name: "假设165",
      rationale: "TEST_ONLY_SECOND",
      counter_evidence: "TEST_ONLY_COUNTER",
    },
    {
      name: "资本投入",
      rationale: "TEST_ONLY_THIRD",
      counter_evidence: "TEST_ONLY_COUNTER",
    },
  ];
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  for (const value of [
    "1,234.57",
    "2,345.68",
    "3,456.79",
    "建仓条件价：123.46",
    "加仓条件价：未形成",
    "减仓条件价：345.68",
    "退出条件价：456.79",
    "假设1：",
    "假设2：",
    "假设3（资本投入）：",
    "未采用",
    "未批准",
    "不是当前买价",
    "不比较当前报价",
  ])
    expect(visible).toContain(value);
  for (const value of [
    "1234.56789123456789",
    "123.456789123456",
    "假设165",
    "&quot;entry&quot;",
  ]) {
    expect(visible).not.toContain(value);
    expect(html).toContain(value);
  }
  expect(html).not.toContain("<details open");
  expect(JSON.stringify(data)).toBe(before);
});

it.each([true, false, undefined])(
  "uses actual direct main range adoption %s without the old forced rejection",
  (adopted) => {
    const data = directFixture();
    Object.assign(data, { main_range_adopted: adopted });
    const html = renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    );
    expect(html).toContain(
      `主区间采用状态：${adopted === true ? "已采用" : adopted === false ? "未采用" : "未提供"}`,
    );
    expect(html).not.toContain("停止展示");
  },
);

it("shows exact refusal reasons without inventing missing valuations, prices or annual cash", () => {
  const data = directFixture();
  data.valuation = null;
  const cash = data.direct_owner_cash!;
  cash.conditional_price!.draft_prices = null;
  cash.conditional_price!.reason_codes = [
    "TEST_ONLY_F1_MISSING_SOURCE",
    "TEST_ONLY_F2_EXPIRED",
  ];
  cash.annual_rows.base = [];
  delete (
    cash.annual_rows.bear[0] as Partial<(typeof cash.annual_rows.bear)[0]>
  ).closing_cash_cny;
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  expect(visible).toContain("bear：未提供");
  for (const label of ["建仓", "加仓", "减仓", "退出"])
    expect(visible).toContain(`${label}条件价：未形成`);
  expect(visible).toContain(
    "TEST_ONLY_F1_MISSING_SOURCE、TEST_ONLY_F2_EXPIRED",
  );
  expect(html).toContain("年度现金账未提供");
  expect(html).toContain("<td>未提供</td>");
  expect(html).not.toContain("NaN");
});

it.each([{ action: "order" }, { currentpricecomparison: true }])(
  "rejects direct price authority violations %s",
  (patch) => {
    const data = directFixture();
    Object.assign(data.direct_owner_cash!.conditional_price!, patch);
    const html = renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    );
    expect(html).toContain("停止展示");
    expect(html).not.toContain("22.22");
  },
);

it.each([
  { symbol: "600519" },
  { action: "order" },
  { formal_eligibility: true },
  { status: "UNASSESSABLE", reason: "TEST_ONLY_HASH_FAILURE" },
])("keeps direct fixture behind issuer and compilation gates %s", (patch) => {
  const data = Object.assign(
    directFixture(),
    patch,
  ) as FirstResearchInputResponse;
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).not.toContain("22.22");
  expect(html).not.toContain("7.125");
});
it.each(["legacy", "direct"])(
  "shows E1 version differences for %s cash research",
  (mode) => {
    const data = mode === "direct" ? directFixture() : example();
    data.successor_update = {
      status: "SOURCE_BOUND_CONDITIONAL_SUCCESSOR",
      symbol: data.symbol,
      action: "no_order",
      formal_eligibility: false,
      main_range_adopted: false,
      price_admitted: false,
      displayed_version_role: "SUCCESSOR",
      research_as_of: "2026-11-11",
      financial_basis: "2026-06-30",
      changed_input_fields: ["assumption_binding"],
      change_rationale: "TEST_ONLY季度收入压力延续假设",
      countercase: "TEST_ONLY后续销售恢复须重开",
      predecessor_input_fingerprint: "old",
      successor_input_fingerprint: "new",
      predecessor_valuation: data.valuation,
      successor_valuation: { ...data.valuation!, bear_value: "9.45" },
    };
    const visible = visibleHtml(
      renderToStaticMarkup(
        <FirstResearchInputView data={data} symbol={data.symbol} />,
      ),
    );
    expect(visible).toContain("E1 研究版本更新");
    expect(visible).toContain("本页当前研究已是下方新版");
    expect(visible).toContain("旧版");
    expect(visible).toContain("9.45");
    expect(visible).toContain("不是当前可比较的主估值或买价");
    expect(visible).toContain("TEST_ONLY季度收入压力延续假设");
    expect(visible).toContain("TEST_ONLY后续销售恢复须重开");
  },
);
beforeEach(() => {
  state.value = { loading: false, error: undefined, retry: vi.fn() };
});

it.each(["600519", "600887"])(
  "leaves unregistered existing company %s completely invisible",
  (symbol) => {
    expect(FirstResearchInputView({ data: base(symbol), symbol })).toBeNull();
    state.value.data = base(symbol);
    expect(
      renderToStaticMarkup(<FirstResearchInputPanel symbol={symbol} />),
    ).toBe("");
  },
);

it("shows three conditional operating scenarios and annual profit/distribution without adopting a main range", () => {
  const data = example();
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  for (const text of [
    "渠道压力持续",
    "逐步稳定",
    "有条件修复",
    "TEST_ONLY渠道压力持续理由",
    "TEST_ONLY逐步稳定理由",
    "TEST_ONLY有条件修复理由",
    "2026-06-30",
    "2026-10-31",
    "TEST_ONLY渠道压力可能持续",
    "TEST_ONLY经营与资本假设失效须重审",
    "TEST_ONLY下一期官方披露再核验",
    "10,000,000.00",
    "6,000,000.00",
    "4,000,000.00",
    "REJECTED",
    "不比较当前报价",
    "不新增C第六家验收",
  ])
    expect(visible).toContain(text);
  for (const price of ["11.11", "22.22", "33.33"]) {
    expect(visible).not.toContain(price);
    expect(html).toContain(price);
  }
  expect(visible).not.toContain("base");
  expect(html).toContain("数学压力结果（非主估值区间、非买价）");
  expect(html).not.toContain("<details open");
  expect(html).not.toContain("已采用Base");
  expect(JSON.stringify(data)).toBe(before);
});

it("shows a verified historical close separately from the unadopted valuation", () => {
  const data = example();
  data.quote_observation = {
    status: "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY",
    quote_date: "2026-11-10",
    display_price: "79.99",
    bundle_sha256: "a".repeat(64),
    price_admitted: false,
    comparison_eligible: false,
  };
  const visible = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  expect(visible).toContain("收盘价 79.99 元");
  expect(visible).toContain("尚无价格比较资格");
  expect(visible).not.toContain("当前低估");
  expect(data.current_price).toBeNull();
  expect(data.condition_price).toBeNull();
});

it("reads backend rows directly as well as rows10 without recalculating or filling a missing amount with zero", () => {
  const data = example();
  for (const name of ["bear", "base", "bull"] as FirstResearchScenarioKey[]) {
    const ledger = data.annual_ledgers![name];
    ledger.rows = ledger.rows10;
    delete ledger.rows10;
    delete ledger.rows![0].retained;
  }
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("年度利润、分配与留存摘要");
  expect(html).toContain("未提供");
  expect(html).not.toContain("停止展示");
});

it.each([
  { symbol: "600519" },
  { action: "order" },
  { formal_eligibility: true },
  { scope: "MAIN_RANGE" },
  { main_range_adopted: true },
  { main_valuation_range: { base: "100" } },
  { current_price: "90" },
  { condition_price: "80" },
  { personal_quantity: 100 },
])(
  "rejects changed issuer or price/adoption/quantity authority: %s",
  (patch) => {
    const data = {
      ...example(),
      ...patch,
    } as unknown as FirstResearchInputResponse;
    const html = renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    );
    expect(html).toContain("停止展示");
    expect(html).not.toContain("TEST_ONLY条件研究论点");
    expect(html).not.toContain("22.22");
  },
);

it("keeps an actual unassessable source failure visible rather than calling it not started or zero", () => {
  const data = {
    ...base(),
    status: "UNASSESSABLE",
    reason: "TEST_ONLY_SOURCE_HASH_MISMATCH",
  } as FirstResearchInputResponse;
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("暂不可核验");
  expect(html).toContain("TEST_ONLY_SOURCE_HASH_MISMATCH");
  expect(html).toContain("不代表未开始");
  expect(html).not.toContain("年度利润");
});

it("does not render an incomplete annual compilation as a successful range", () => {
  const data = example();
  data.annual_ledgers!.base.rows10 = [];
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("年度来源绑定不完整");
  expect(html).not.toContain("22.22");
});

it("keeps loading invisible and read errors scoped to this panel", () => {
  state.value.loading = true;
  expect(
    renderToStaticMarkup(<FirstResearchInputPanel symbol="600519" />),
  ).toBe("");
  state.value = { loading: false, error: "TEST_ONLY_NETWORK", retry: vi.fn() };
  const html = renderToStaticMarkup(
    <FirstResearchInputPanel symbol="000568" />,
  );
  expect(html).toContain("读取失败");
  expect(html).toContain("重新读取首次研究输入");
});

it("only makes safe official source URLs clickable", () => {
  const data = example();
  let html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain('href="https://example.org/TEST_ONLY-official.pdf"');
  data.sources = [{ id: "TEST_ONLY_BAD", officialURL: "javascript:alert(1)" }];
  html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).not.toContain('href="javascript:');
});

it("places E2 next to C/D2 only in the existing non-hotspot value-company guard", () => {
  const page = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  const start = page.indexOf(
    '{strategy !== "hotspot" && /^[0-9]{6}$/.test(id) && (',
  );
  expect(start).toBeGreaterThan(-1);
  const guarded = page.slice(start, page.indexOf("<RemoteState", start));
  expect(guarded.indexOf("<CompanyProfilePanel")).toBeLessThan(
    guarded.indexOf("<OperatingAssumptionDraftPanel"),
  );
  expect(guarded.indexOf("<FirstResearchInputPanel")).toBeLessThan(
    guarded.indexOf("<OperatingAssumptionDraftPanel"),
  );
  expect(guarded).toContain(
    '<FirstResearchInputPanel key={"first-" + id} symbol={id}',
  );
  expect(page.match(/<FirstResearchInputPanel/g)).toHaveLength(1);
});

it("keeps actual terminal reasoning visible when the backend only provides a shared operating rationale", () => {
  const data = example();
  data.operating_assumptions = {
    choice: { rationale: "TEST_ONLY共用压力理由" },
    scenarios: {
      bear: { terminal_policy: { rationale: "TEST_ONLY压力持续终端理由" } },
      base: {
        terminal_policy: { rationale: "TEST_ONLY稳定仍有条件的终端理由" },
      },
      bull: {
        terminal_policy: { rationale: "TEST_ONLY修复未获批准的终端理由" },
      },
    },
  };
  const html = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  for (const reason of [
    "TEST_ONLY共用压力理由",
    "TEST_ONLY压力持续终端理由",
    "TEST_ONLY稳定仍有条件的终端理由",
    "TEST_ONLY修复未获批准的终端理由",
  ])
    expect(html).toContain(reason);
  expect(html).toContain("共用研究理由");
  expect(html).toContain("终端条件理由（假设）");
});

it("rounds grouped amounts for display while preserving exact raw ledger values and integer years", () => {
  const data = example();
  const rows = data.annual_ledgers!.bear.rows10!;
  rows[0].profit = "1234567.126789012345678901234567890123456789";
  rows[0].distribution = "-1234.56789";
  rows[0].retained = "not-a-number";
  rows[1].profit = "";
  rows[1].distribution = "Infinity";
  rows[1].retained = 0;
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  expect(visible).toContain("1,234,567.13");
  expect(visible).toContain("-1,234.57");
  expect(visible).toContain("0.00");
  expect(visible).toContain("未提供");
  expect(visible).not.toContain("not-a-number");
  expect(visible).not.toContain("Infinity");
  expect(visible).not.toContain("1234567.126789");
  expect(visible).not.toContain("2,026.00");
  expect(visible).toContain("展示四舍五入至两位小数");
  expect(visible).toContain("原值见完整年度账本");
  expect(html).toContain("1234567.126789012345678901234567890123456789");
  expect(JSON.stringify(data)).toBe(before);
});

it("shows source-bound parent cash flows without turning closing cash into TTM or dividends", () => {
  const data = example();
  data.parent_cash_observation = {
    status: "OBSERVED",
    whole_statement_reconciled: true,
    action: "no_order",
    future_cash_proven: false,
    periods: [
      {
        period: "H12026",
        flows: {
          cfo_cny: "35551654301.69",
          gross_capex_cny: "1235902972.58",
          borrowings_received_cny: "124697925031.54",
          debt_repaid_cny: "143377489906.35",
          mixed_distribution_interest_paid_cny: "6186835910.21",
        },
        closing_cash_and_equivalents_cny: "14939427794.14",
        source_sha256: "a".repeat(64),
        physical_pages: { cfo_cny: 57 },
      },
    ],
    ttm_flows: {
      cfo_cny: "45593027419.63",
      gross_capex_cny: "1630305033.08",
      borrowings_received_cny: "216451046343.17",
      debt_repaid_cny: "242137138123.11",
      mixed_distribution_interest_paid_cny: "9933808505.42",
    },
    limitations: ["TEST_ONLY历史观察不能推断未来分配"],
  };
  const visible = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  expect(visible).toContain("母公司历史现金观察");
  expect(visible).toContain("余额与现金变动已完整勾稽");
  expect(visible).toContain("455.93");
  expect(visible).toContain("149.39");
  expect(visible).toContain("不适用（期末存量）");
  expect(visible).toContain("混合科目，不等于股息");
  expect(visible).toContain("REJECTED");
});

it("does not display unverified parent cash amounts", () => {
  const data = example();
  data.parent_cash_observation = {
    status: "UNASSESSABLE",
    reason: "TEST_ONLY_SOURCE_HASH_MISMATCH",
  };
  const visible = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  expect(visible).toContain("母公司现金原件尚未完成独立核验");
  expect(visible).toContain("TEST_ONLY_SOURCE_HASH_MISMATCH");
  expect(visible).not.toContain("455.93");
});

it("does not display a parsed statement without full cash reconciliation", () => {
  const data = example();
  data.parent_cash_observation = {
    status: "OBSERVED",
    whole_statement_reconciled: false,
    action: "no_order",
    future_cash_proven: false,
    periods: [{ period: "FY2025", flows: { cfo_cny: "45593027419.63" } }],
    ttm_flows: { cfo_cny: "45593027419.63" },
  };
  const visible = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  expect(visible).toContain("母公司现金原件尚未完成独立核验");
  expect(visible).not.toContain("455.93");
});
