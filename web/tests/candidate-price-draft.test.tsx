import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import {
  CandidatePriceDraft,
  FinancialFinancingConflicts,
  ParentFinancingSchedule,
  candidatePriceMatches,
  candidateResearchComparisonMatches,
} from "../src/components/CandidatePriceDraft";
import type {
  CandidateNativeSourceConsumption,
  JointCapitalReview,
} from "../src/services/valuePolicy";

function fixture(): JointCapitalReview {
  return {
    symbol: "600519",
    candidate_binding: { path: "TEST_ONLY/candidate", sha256: "a".repeat(64) },
    scenarios: [
      { scenario: "bear", valuation_per_share: "100" },
      { scenario: "bull", valuation_per_share: "200" },
    ],
    conditional_price: {
      schema_version: "pending-candidate-conditional-price-v1",
      status: "researcher_proposal",
      action: "no_order",
      formal_eligibility: false,
      user_approved: false,
      formally_prepared: false,
      quantities: null,
      explanation: "TEST_ONLY 条件路径",
      value: null,
      unit: "CNY/share",
      reason_codes: [],
      sourcebindings: {
        candidate_sha256: "a".repeat(64),
        policy_artifact_sha256: "b".repeat(64),
      },
      price_comparison: {
        currentpricecomparison: false,
        status: "not_performed",
        reasons: [],
      },
      proposal_validity: {
        status: "valid",
        available_at: "2026-10-29",
        expires_at: "2026-11-05",
        current_valid: true,
        reasons: [],
      },
      draft_prices: { entry: "100", reduce: "200", add: null, exit: null },
      draft: {
        policy_id: "TEST_ONLY",
        rule_version: "v1",
        basis: {
          symbol: "600519",
          bear: "100",
          base: "150",
          bull: "200",
          valuation_date: "2026-06-30",
        },
        rationale: "TEST_ONLY 情景而非默认折扣",
        dividend_coverage_risk: "未来分配不确定",
        rules: [
          {
            action: "entry",
            scenario: "bear",
            value_fraction: "1",
            comparison: "LTE",
            rationale: "悲观路径需重新核对",
          },
          {
            action: "reduce",
            scenario: "bull",
            value_fraction: "1",
            comparison: "GTE",
            rationale: "乐观路径仍不代表卖出",
          },
        ],
      },
      reopenconditions: ["新增财报需要重新审阅"],
    },
  } as unknown as JointCapitalReview;
}
it("shows bound arithmetic draft separately from current price and approval", () => {
  const review = fixture();
  expect(candidatePriceMatches(review)).toBe(true);
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("100.00");
  expect(html).toContain("200.00");
  expect(html).toContain("尚未进行当前行情比较");
  expect(html).toContain("不是当前买卖建议");
  expect(html).toContain("加仓、退出和个人股数：未形成");
});
it("rejects stale identity and changed arithmetic, without hiding research", () => {
  for (const mutate of [
    (r: any) => (r.conditional_price.sourcebindings.candidate_sha256 = "wrong"),
    (r: any) => (r.conditional_price.draft_prices.entry = "99"),
    (r: any) => (r.conditional_price.formal_eligibility = true),
    (r: any) => (r.conditional_price.draft.rules = null),
    (r: any) => (r.conditional_price.draft.basis.symbol = "600887"),
    (r: any) => (r.conditional_price.draft.rationale = {}),
    (r: any) => (r.conditional_price.reopenconditions = {}),
    (r: any) => (r.conditional_price.proposal_validity.expires_at = {}),
  ]) {
    const review = fixture();
    mutate(review);
    expect(candidatePriceMatches(review)).toBe(false);
    expect(
      renderToStaticMarkup(<CandidatePriceDraft review={review} />),
    ).not.toContain("100.00");
  }
});
it("labels expired draft historical rather than current", () => {
  const review = fixture();
  review.conditional_price!.proposal_validity!.current_valid = false;
  expect(
    renderToStaticMarkup(<CandidatePriceDraft review={review} />),
  ).toContain("仅供历史阅读");
});

function alignmentFixture() {
  const review = fixture();
  review.input_descriptor_sha256 = "d".repeat(64);
  review.conditional_price!.alignment = {
    schema_version: "pending-candidate-alignment-v1",
    action: "no_order",
    formal_eligibility: false,
    candidate_binding: { ...review.candidate_binding },
    input_descriptor_sha256: review.input_descriptor_sha256,
    valuation_date: "2026-06-30",
    evaluated_at: "2026-10-29T22:50:00+08:00",
    status: "BLOCKED",
    currentpricecomparison: false,
    quote: {
      status: "QUALIFIED",
      current_price: "1354",
      quote_date: "2026-10-29",
      latest_completed_session: "2026-10-29",
      native_status: "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
      bundle_binding: { path: "TEST_ONLY/quote.json", sha256: "c".repeat(64) },
      reason_codes: [],
    },
    checks: [
      "quote",
      "capital_structure",
      "distributions",
      "material_events",
      "financial_updates",
    ].map((id) => ({
      id,
      status: id === "quote" ? "PASS" : "BLOCKED",
      reason_codes:
        id === "quote" ? [] : [id.toUpperCase() + "_NOT_RECONCILED"],
      explanation:
        id === "distributions"
          ? "6/26分配已在6/30账内，不重复扣减。"
          : id + " 的证据说明",
      evidence_bindings: [
        { path: "TEST_ONLY/" + id + ".json", sha256: "e".repeat(64) },
      ],
      details:
        id === "material_events"
          ? { issuer_claim_only: true, full_calendar_window_elapsed: false }
          : { current_ordinary_shares: null },
    })),
    model_validity: {
      status: "UNKNOWN",
      blockers: ["MATERIALITY_REVIEW_REQUIRED"],
    },
    price_bridge: {
      bridge_status: "STALE_MODEL",
      blockers: ["CURRENT_BASIS_NOT_ALIGNED"],
      margin_to_bear: "DO_NOT_RENDER_MARGIN",
    },
    reason_codes: [
      "ALIGNMENT_INCOMPLETE",
      "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING",
    ],
  };
  return review;
}
it("shows a qualified quote independently of blocked alignment and preserves historical thresholds", () => {
  const review = alignmentFixture();
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  for (const value of [
    "100.00",
    "200.00",
    "1354",
    "2026-06-30",
    "2026-10-29",
    "行情资格",
    "股本与公司行动",
    "期间分配与模型内含",
    "重大事件",
    "新财报与输入更新",
    "MATERIALITY_REVIEW_REQUIRED",
    "TEST_ONLY/material_events.json",
    "issuer_claim_only",
    "不重复扣减",
    "口径待核，不能进行当前价值比较",
    "缺少报价日精确股本原件。",
    "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING",
  ])
    expect(html).toContain(value);
  expect(html).toContain("报价已核验");
  expect(html).not.toContain("后端状态：");
  expect(html).not.toContain("DO_NOT_RENDER_MARGIN");
  expect(html).not.toContain("当前研究比较口径已核验");
});
it("accepts future evidence-backed cross-date alignment without hiding the unapproved draft", () => {
  const review = readyAlignmentFixture(),
    price = review.conditional_price!;
  expect(candidatePriceMatches(review)).toBe(true);
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("当前研究比较口径已核验，仍未批准");
  expect(html).toContain("100.00");
  expect(html).toContain("2026-06-30");
  expect(html).toContain("2026-10-29");
  expect(html).toContain("报价已核验");
  expect(html).not.toContain("后端状态：");
  expect(html).not.toContain("DO_NOT_RENDER_MARGIN");
  price.proposal_validity!.current_valid = false;
  const expired = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(expired).toContain("100.00");
  expect(expired).toContain("仅供历史阅读");
  expect(expired).not.toContain("当前研究比较口径已核验");
});
it("never upgrades partial, duplicate or unknown checks to aligned", () => {
  for (const mutate of [
    (a: any) => a.checks.pop(),
    (a: any) => a.checks.push(a.checks[0]),
    (a: any) => (a.checks[0].status = "FUTURE_PENDING"),
    (a: any) => (a.model_validity = null),
    (a: any) => (a.price_bridge.blockers = ["STILL_BLOCKED"]),
  ]) {
    const review = readyAlignmentFixture(),
      a = review.conditional_price!.alignment!;
    mutate(a);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).not.toContain("当前研究比较口径已核验");
    expect(html).toContain("100.00");
  }
});
it("rejects mismatched alignment while retaining a separately valid historical draft", () => {
  for (const mutate of [
    (a: any) => (a.candidate_binding.sha256 = "wrong"),
    (a: any) => (a.candidate_binding.path = "TEST_ONLY/other"),
    (a: any) => (a.input_descriptor_sha256 = "wrong"),
    (a: any) => (a.valuation_date = "2026-10-29"),
    (a: any) => (a.schema_version = "unknown"),
    (a: any) => (a.formal_eligibility = true),
  ]) {
    const review = alignmentFixture();
    mutate(review.conditional_price!.alignment);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).toContain("不匹配或字段不完整");
    expect(html).toContain("100.00");
    expect(html).not.toContain("1354");
  }
});
it("handles missing legacy fields and malformed optional diagnostics without inventing evidence", () => {
  for (const patch of [
    {
      quote: null,
      checks: undefined,
      model_validity: null,
      price_bridge: null,
    },
    {
      checks: [
        null,
        {
          id: "future_check",
          status: {},
          reason_codes: {},
          explanation: {},
          evidence_bindings: [null],
          details: null,
        },
      ],
    },
    { checks: {}, reason_codes: {}, evidence_bindings: {} },
  ]) {
    const review = alignmentFixture();
    Object.assign(review.conditional_price!.alignment!, patch);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).toContain("100.00");
    expect(html).toContain("口径待核，不能进行当前价值比较");
    expect(html).toContain("缺少检查");
  }
  const legacy = fixture();
  delete legacy.conditional_price!.price_comparison;
  expect(
    renderToStaticMarkup(<CandidatePriceDraft review={legacy} />),
  ).toContain("100.00");
});
it("does not display an unqualified or non-latest quote as the current price", () => {
  for (const patch of [
    { status: "BLOCKED" },
    { current_price: "NaN" },
    { current_price: "-1" },
    { latest_completed_session: "2026-10-30" },
  ]) {
    const review = alignmentFixture();
    Object.assign(review.conditional_price!.alignment!.quote!, patch);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).toContain("未提供合格当前报价");
    expect(html).not.toContain("1354 元/股");
    expect(html).toContain("100.00");
  }
});

function readyAlignmentFixture() {
  const review = alignmentFixture(),
    price = review.conditional_price!,
    alignment = price.alignment!;
  price.sourcebindings!.model_version = "TEST_ONLY/v4";
  alignment.quote_date = "2026-10-29";
  alignment.status = "ALIGNED_FOR_RESEARCH_COMPARISON";
  alignment.currentpricecomparison = true;
  alignment.reason_codes = [];
  alignment.checks!.forEach((check) => {
    check.status = "PASS";
    check.reason_codes = [];
  });
  alignment.model_validity = {
    status: "VALID",
    blockers: [],
    symbol: "600519",
    model_as_of: "2026-06-30",
  };
  alignment.price_bridge = {
    bridge_status: "READY",
    blockers: [],
    model_validity_status: "VALID",
    quote_status: "verified_close",
    symbol: "600519",
    quote_symbol: "600519",
    valuation_date: "2026-06-30",
    model_as_of: "2026-06-30",
    quote_date: "2026-10-29",
    current_price: "1354",
    model_version: "TEST_ONLY/v4",
    valuation_bear_value: "100",
    valuation_base_value: "150",
    margin_to_base: "DO_NOT_RENDER_MARGIN",
  };
  price.price_comparison = {
    status: "research_comparison_verified",
    currentpricecomparison: true,
    reasons: [],
  };
  return review;
}
it("requires bound bridge values and dates before labeling a current research comparison", () => {
  expect(candidateResearchComparisonMatches(readyAlignmentFixture())).toBe(
    true,
  );
  for (const [key, value] of [
    ["symbol", "600887"],
    ["quote_symbol", "600887"],
    ["quote_date", "2026-10-28"],
    ["valuation_date", "2026-10-29"],
    ["model_as_of", "2026-10-29"],
    ["current_price", "999"],
    ["valuation_bear_value", "99"],
    ["valuation_base_value", "149"],
    ["model_version", "OTHER"],
    ["quote_status", "pending"],
    ["model_validity_status", "UNKNOWN"],
    ["blockers", null],
  ]) {
    const review = readyAlignmentFixture();
    (review.conditional_price!.alignment!.price_bridge as any)[String(key)] =
      value;
    expect(candidateResearchComparisonMatches(review), String(key)).toBe(false);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).toContain("100.00");
    expect(html).not.toContain("当前研究比较口径已核验");
  }
});

const reconciliationExample = {
  status: "PARTIAL",
  opening_shares: "1250081601",
  calculated_closing_shares: "1250081601",
  closing_shares: null,
  period_cash_per_share: "0",
  distributions: [
    {
      id: "TEST_ONLY/dividend",
      record_date: "2026-06-25",
      ex_date: "2026-06-26",
      cash_payment_date: "2026-06-26",
      amount_basis: "implemented_gross_entitlement",
      verified_cash_per_share: "28.02423",
      price_deduction_applied: "0",
      period_treatment: "BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL",
      model_inclusion: "ALREADY_OUTSIDE_INTERVAL",
    },
  ],
};
function expectReconciliation(html: string) {
  for (const value of [
    "估值日股本（已消费口径）",
    "1250081601",
    "尚未核验，不能认定股本未变",
    "28.02423",
    "2026-06-26",
    "不重复扣减，未验证个人实际到账",
    "本次已应用价格扣减",
    "已列记录中归入本区间的除息权益合计",
    "不证明全期间完整覆盖",
    "不能据此认定实际期间无分红",
  ])
    expect(html).toContain(value);
}
it("explains partial source-bound share and distribution arithmetic without claiming complete coverage", () => {
  const review = alignmentFixture();
  for (const check of review.conditional_price!.alignment!.checks!) {
    if (["capital_structure", "distributions"].includes(check.id))
      check.details = { reconciliation: reconciliationExample };
  }
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expectReconciliation(html);
  expect(html).toContain("100.00");
  expect(html).toContain("1354");
});
it("shows exact in-model dividend without granting full period coverage", () => {
  const review = alignmentFixture();
  const distributions = review.conditional_price!.alignment!.checks!.find(
    (check) => check.id === "distributions",
  )!;
  distributions.details = {
    reconciliation: {
      ...reconciliationExample,
      distributions: [
        {
          ...reconciliationExample.distributions[0],
          period_treatment: "IN_PERIOD_MODEL_INCLUSION_VERIFIED",
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("此笔期间现金分配已核验并进入候选估值");
  expect(html).toContain("全期间覆盖仍需独立核验");
  expect(html).not.toContain("当前研究比较口径已核验");
});
it("explains opening cash already net of the booked dividend without proving payment", () => {
  const review = alignmentFixture();
  const distributions = review.conditional_price!.alignment!.checks!.find(
    (check) => check.id === "distributions",
  )!;
  distributions.details = {
    reconciliation: {
      ...reconciliationExample,
      opening_parent_dividend_payable: {
        conditional_opening_cash_match: {
          scope: "CONDITIONAL_NET_CASH_MATCH_NOT_PAYMENT_PROOF",
          action: "no_order",
        },
      },
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("这笔股利不应再扣一次；实际付款仍待核验。");
});
it("shows exact share evidence and rollforward conflict without enabling price comparison", () => {
  const review = alignmentFixture();
  const capital = review.conditional_price!.alignment!.checks!.find(
    (check) => check.id === "capital_structure",
  )!;
  capital.details = {
    reconciliation: {
      ...reconciliationExample,
      native_source_consumption: {
        closing_capital: {
          status: "EXACT_REPORT_DATE_SHARES_VERIFIED",
          as_of: "2026-11-17",
          anchors: [
            {
              evidence_binding: {
                path: "TEST_ONLY/closing.pdf",
                sha256: "a".repeat(64),
              },
            },
          ],
          rollforward_comparison: {
            status: "CONFLICT",
            observed_ordinary_shares: "1250081602",
            calculated_ordinary_shares: "1250081601",
          },
        },
      },
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  for (const term of [
    "2026-11-17",
    "与台账滚动值冲突",
    "1250081602",
    "1250081601",
    "TEST_ONLY/closing.pdf",
  ])
    expect(html).toContain(term);
});
const actualReceipt = resolve(
  "..",
  ".tmp/value-alignment-acceptance/600519-api.json",
);
it.skipIf(!existsSync(actualReceipt))(
  "renders the retained actual API reconciliation without replacing blocked historical prices",
  () => {
    const response = JSON.parse(readFileSync(actualReceipt, "utf8"));
    const review = response.decision.research_analysis
      .joint_capital_review as JointCapitalReview;
    const ledger = review.conditional_price!.alignment!.checks!.find(
      (check) => check.id === "capital_structure",
    )!.details!.reconciliation;
    expect(ledger?.opening_shares).toBe("1250081601");
    expect(ledger?.closing_shares).toBeNull();
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expectReconciliation(html);
    expect(html).not.toContain("估值日前已除息并支付");
    expect(html).toContain("已核验公告分配条款");
    expect(html).toContain("675.10");
    expect(html).toContain("930.01");
    expect(html).toContain("1354");
    expect(html).not.toContain("当前研究比较口径已核验");
  },
);

it("keeps the legacy price projection unchanged while independently accepting valid alignment", () => {
  const review = readyAlignmentFixture();
  const price = review.conditional_price!;
  price.currentpricecomparison = false;
  price.price_comparison = {
    status: "not_performed",
    currentpricecomparison: false,
    reasons: ["LEGACY_PRICE_PROJECTION_NOT_CURRENT_COMPARISON"],
  };
  const legacy = JSON.stringify(price.price_comparison);
  expect(candidateResearchComparisonMatches(review)).toBe(true);
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("当前研究比较口径已核验，仍未批准");
  expect(html).toContain("100.00");
  expect(JSON.stringify(price.price_comparison)).toBe(legacy);
  expect(price.currentpricecomparison).toBe(false);
  expect(price.formal_eligibility).toBe(false);
  for (const mutate of [
    (a: any) => {
      a.status = "BLOCKED";
      a.currentpricecomparison = false;
    },
    (a: any) => {
      a.checks[1].status = "BLOCKED";
    },
    (a: any) => {
      a.candidate_binding.sha256 = "wrong";
    },
    (a: any) => {
      a.price_bridge.bridge_status = "INVALID";
    },
  ]) {
    const invalid = structuredClone(review);
    mutate(invalid.conditional_price!.alignment);
    expect(candidateResearchComparisonMatches(invalid)).toBe(false);
    const rejected = renderToStaticMarkup(
      <CandidatePriceDraft review={invalid} />,
    );
    expect(rejected).not.toContain("当前研究比较口径已核验");
    expect(rejected).toContain("100.00");
  }
});

it.each(["material_events", "financial_updates"])(
  "shows %s source facts outside collapsed JSON without approving events",
  (id) => {
    const review = alignmentFixture();
    const check = review.conditional_price!.alignment!.checks!.find(
      (item) => item.id === id,
    )!;
    check.details = {
      matched_input_sources: [
        {
          title: "TEST_ONLY 半年度报告",
          published_at: "2026-08-29T00:00:00+08:00",
          source_url: "https://example.org/TEST_ONLY-report.pdf",
          status: "EXACT_FACT_SOURCE_ALREADY_CONSUMED_NOT_EVENT_APPROVAL",
          consumed_fact_fields: ["ordinary_shares", "parent_net_profit"],
          evidence_refs: [
            { path: "TEST_ONLY/report.pdf", sha256: "a".repeat(64) },
          ],
        },
      ],
      unresolved_sources: [
        {
          title: "TEST_ONLY 会计政策公告",
          published_at: "2026-10-29T00:00:00+08:00",
          status: "NOT_BOUND_TO_CURRENT_CANDIDATE_REVIEW",
          original_bytes_in_source_closure: true,
          source_url: "javascript:alert(1)",
        },
      ],
    };
    const before = JSON.stringify(review);
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    const visible = html.replace(/<details[\s\S]*?<\/details>/g, "");
    expect(visible).toContain("TEST_ONLY 半年度报告");
    expect(visible).toContain("2026-08-29T00:00:00+08:00");
    expect(visible).toContain("ordinary_shares");
    expect(visible).toContain("parent_net_profit");
    expect(visible).toContain(
      'href="https://example.org/TEST_ONLY-report.pdf"',
    );
    expect(visible).toContain("TEST_ONLY 会计政策公告");
    expect(visible).toContain("尚未绑定当前候选的复核");
    expect(visible).toContain("不代表事实已消费或事件获准");
    expect(visible).toContain("事实已消费不代表重大性复核通过");
    expect(visible).toContain("口径待核，不能进行当前价值比较");
    expect(visible).not.toContain('href="javascript:');
    expect(visible).not.toContain('href="TEST_ONLY/');
    expect(visible).not.toContain("TEST_ONLY/report.pdf");
    expect(visible).not.toContain("a".repeat(64));
    expect(html).toContain("TEST_ONLY/report.pdf");
    expect(candidateResearchComparisonMatches(review)).toBe(false);
    expect(JSON.stringify(review)).toBe(before);
  },
);

it.each([
  undefined,
  {},
  { matched_input_sources: [], unresolved_sources: [] },
  {
    matched_input_sources: [
      null,
      {},
      { status: "UNKNOWN", consumed_fact_fields: [null] },
    ],
    unresolved_sources: "invalid",
  },
])(
  "handles missing and malformed source details without inferring approval: %j",
  (details) => {
    const review = alignmentFixture();
    review.conditional_price!.alignment!.checks!.find(
      (item) => item.id === "material_events",
    )!.details = details as any;
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    const visible = html.replace(/<details[\s\S]*?<\/details>/g, "");
    expect(visible).toContain("事实已消费不代表重大性复核通过");
    expect(visible).toContain("口径待核，不能进行当前价值比较");
    expect(visible).not.toContain("原件事实已匹配当前输入");
    expect(candidateResearchComparisonMatches(review)).toBe(false);
  },
);

function nativeFixture(): CandidateNativeSourceConsumption {
  const binding = {
    path: "TEST_ONLY/native-report.pdf",
    sha256: "f".repeat(64),
  };
  return {
    status: "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE",
    reports: [
      {
        status: "NATIVE_REPORT_FIELDS_VERIFIED",
        binding,
        source_url: "https://example.org/TEST_ONLY-native.pdf",
        source_available_at: "2026-10-30T09:00:00+08:00",
        published_date: "2026-08-29",
        consumed_opening_fact: true,
        terms: {
          period_end: "2026-06-30",
          ordinary_shares: "100000",
          cancelled_shares: "123",
          cancellation_state: "DISCLOSED_BUYBACK_COMPLETED_BY_REPORT_END",
          interim_proposal_state:
            "NO_INTERIM_DISTRIBUTION_OR_CAPITALIZATION_PROPOSED",
          declared_ordinary_dividend_cny: "100.01",
        },
      },
    ],
    distribution_inclusion: {
      status: "SOURCE_AMOUNTS_COMPARED_INCLUSION_UNVERIFIED",
      comparisons: [
        {
          reported_dividend_cny: "100.01",
          implementation_total_cny: "100.00",
          difference_cny: "0.01",
          status: "AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION",
          price_deduction_applied: "0",
          report_binding: binding,
          implementation_evidence: [
            {
              binding: {
                path: "TEST_ONLY/implementation.pdf",
                sha256: "e".repeat(64),
              },
            },
          ],
        },
      ],
    },
  };
}
function renderNative(
  value: CandidateNativeSourceConsumption | null | undefined,
) {
  const review = alignmentFixture();
  for (const check of review.conditional_price!.alignment!.checks!) {
    if (["capital_structure", "distributions"].includes(check.id))
      check.details = {
        reconciliation: {
          ...reconciliationExample,
          native_source_consumption: value,
        },
      };
  }
  const before = JSON.stringify(review);
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(JSON.stringify(review)).toBe(before);
  expect(candidateResearchComparisonMatches(review)).toBe(false);
  return { html, visible: html.replace(/<details[\s\S]*?<\/details>/g, "") };
}
it("shows verified H1 facts and backend dividend difference with historical scope and folded provenance", () => {
  const { html, visible } = renderNative(nativeFixture());
  for (const value of [
    "中报原件字段已核验",
    "100000 股",
    "123 股",
    "截至报告期末已完成回购注销",
    "半年度预案不分配、不转增",
    "100.01 元",
    "100.00 元",
    "<dd>0.01 元</dd>",
    "存在金额差异，仍需对账",
    "非截至当前完整证明",
    "2026-08-29",
    "2026-10-30T09:00:00+08:00",
    "不证明后续股本连续性",
    "不代表重大性批准或当前比较获准",
    'href="https://example.org/TEST_ONLY-native.pdf"',
  ])
    expect(visible).toContain(value);
  for (const value of [
    "TEST_ONLY/native-report.pdf",
    "TEST_ONLY/implementation.pdf",
    "f".repeat(64),
  ]) {
    expect(visible).not.toContain(value);
    expect(html).toContain(value);
  }
});
it("renders supplied zero and changed differences without computing or hardcoding 0.01", () => {
  for (const difference of ["0", "-2.35"]) {
    const native = nativeFixture();
    native.distribution_inclusion!.comparisons![0].difference_cny = difference;
    native.distribution_inclusion!.comparisons![0].status =
      difference === "0"
        ? "AMOUNT_MATCH_NOT_MODEL_INCLUSION_PROOF"
        : "AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION";
    const { visible } = renderNative(native);
    expect(visible).toContain("<dd>" + difference + " 元</dd>");
    expect(visible).not.toContain("<dd>0.01 元</dd>");
    if (difference === "0")
      expect(visible).toContain("金额一致，仍不证明模型已内含");
  }
});
it("does not invent absent native facts or a dividend difference", () => {
  const native = nativeFixture();
  native.reports![0].terms = {};
  native.distribution_inclusion!.comparisons![0] = {};
  const { visible } = renderNative(native);
  expect(visible).toContain("未提供可识别的预案结果");
  expect(visible).not.toContain("半年度预案不分配、不转增");
  expect(visible).not.toContain("<dd>0.01 元</dd>");
  expect(visible).not.toContain("100000 股");
  expect(visible).toContain("未提供可识别的核对结论");
});
it.each([
  undefined,
  null,
  {},
  { reports: [null], distribution_inclusion: { comparisons: "invalid" } },
])("handles absent or malformed native consumption %j", (native) => {
  const { visible } = renderNative(
    native as CandidateNativeSourceConsumption | null | undefined,
  );
  expect(visible).not.toContain("<dd>0.01 元</dd>");
  expect(visible).not.toContain("中报原件字段已核验");
  expect(visible).toContain("口径待核，不能进行当前价值比较");
});
it("does not present unverified report terms as verified facts or link unsafe originals", () => {
  const native = nativeFixture();
  native.reports![0].status = "UNKNOWN";
  native.reports![0].source_url = "javascript:alert(1)";
  const { visible } = renderNative(native);
  expect(visible).toContain("尚未确认字段核验通过");
  expect(visible).not.toContain("100000 股");
  expect(visible).not.toContain("半年度预案不分配、不转增");
  expect(visible).not.toContain('href="javascript:');
});

it("renders source operating terms without admitting current comparison or replacing the draft", () => {
  const review = alignmentFixture();
  const check = review.conditional_price!.alignment!.checks!.find(
    (x) => x.id === "material_events",
  )!;
  check.details = {
    operating_event_research: [
      {
        title: "TEST_ONLY 正文调价",
        published_at: "2026-07-18",
        status: "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
        facts: [
          {
            binding: { path: "TEST_ONLY/price.pdf", sha256: "e".repeat(64) },
            source_available_at: "2026-10-30",
            terms: {
              summary: "零售价与合同价分别披露",
              implication: "不能替代综合实现价格",
              effective_date: "2026-07-18",
              affected_model_fields: ["revenue"],
              limitations: ["TEST_ONLY 非批准"],
            },
          },
        ],
        materiality_approved: false,
        model_inputs_changed: false,
      },
    ],
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("零售价与合同价分别披露");
  expect(html).toContain("不能替代综合实现价格");
  expect(html).toContain("候选输入未自动改写");
  expect(html).toContain("100.00");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});

it("shows an unresolved event as unknown rather than no impact", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![3].details = {
    operating_event_research: [
      {
        title: "TEST_ONLY unknown",
        status: "UNSUPPORTED_OR_UNRESOLVED",
        facts: [],
      },
    ],
  };
  expect(
    renderToStaticMarkup(<CandidatePriceDraft review={review} />),
  ).toContain("不能仅凭标题认定无影响");
});

it("separates opening authorization from executed distribution", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![1].details = {
    opening_action_research: [
      {
        title: "TEST_ONLY opening",
        status: "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
        facts: [
          {
            terms: {
              summary: "中期分配授权，不是确定方案",
              implication: "后续事项须跟踪",
            },
          },
        ],
      },
    ],
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("期初行动与分配授权");
  expect(html).toContain("中期分配授权，不是确定方案");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});

it("shows an explicit unproven interval without revoking interim authority", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![2].details = {
    basis_followup: {
      schema_version: "candidate-basis-followup-v1",
      action: "no_order",
      current_comparison_granted: false,
      latest_capital_checkpoint: {
        ordinary_shares: "100",
        as_of: "2026-06-30",
        published_date: "2026-08-15",
      },
      uncovered_capital_interval: {
        after: "2026-06-30",
        through: "2026-10-29",
      },
      interim_report_followups: [
        { published_date: "2026-08-15", conclusion: "未提出预案不撤销授权" },
      ],
      authorization_followup_required: true,
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("未提出预案不撤销授权");
  expect(html).toContain("不能把期初股数沿用为当前股数");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});
it("only renders confirmed zero-net unlocks from the F2 evidence", () => {
  const review = alignmentFixture();
  const confirmed = {
    announcement_id: "confirmed",
    classification: "ISSUER_CONFIRMED_RESTRICTED_SHARE_UNLOCK",
    effective_date: "2026-09-28",
    net_share_change: "0",
    action: "no_order",
    window_completeness_granted: false,
    issuer_reported_listing_confirmation: {},
  };
  review.conditional_price!.alignment!.checks![2].details = {
    basis_followup: {
      schema_version: "candidate-basis-followup-v1",
      action: "no_order",
      current_comparison_granted: false,
      capital_event_classifications: [
        confirmed,
        {
          ...confirmed,
          announcement_id: "nonzero",
          effective_date: "2026-09-29",
          net_share_change: "-1",
        },
        {
          ...confirmed,
          announcement_id: "pending",
          effective_date: "2026-09-30",
          issuer_reported_listing_confirmation: null,
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("2026-09-28");
  expect(html).toContain("已发行股数净变动 0 股");
  expect(html).toContain("股本全期间连续性仍需核验");
  expect(html).not.toContain("2026-09-29：发行人已确认");
  expect(html).not.toContain("2026-09-30：发行人已确认");
});
it("shows every capital checkpoint with separate ordinary, issued, treasury, and proposal meanings", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![2].details = {
    basis_followup: {
      schema_version: "candidate-basis-followup-v1",
      action: "no_order",
      current_comparison_granted: false,
      buyback_checkpoint_deltas: [
        {
          after_date: "2026-10-22",
          through: "2026-10-31",
          purchase_share_delta: 1680400,
          disclosed_cash_delta_cny: "49999397.00",
          scope: "MATCHING_DISCLOSED_PLAN_WINDOW_RESEARCH_ONLY",
          action: "no_order",
        },
      ],
      capital_checkpoints: [
        {
          ordinary_shares: "6325360667",
          classification: "DERIVED_FACT",
          derivation: "年度普通股事实 + 半年报总数及结构未变声明",
          as_of: "2026-06-30",
          published_date: "2026-08-27",
        },
        {
          ordinary_shares: null,
          issued_shares: "6325360667",
          share_scope: "TOTAL_ISSUED_SHARES",
          treasury_shares: "1800200",
          proposal_only: true,
          proposed_cash_per_share_cny: "0.42",
          classification: "FACT",
          as_of: "2026-10-22",
          published_date: "2026-10-30",
        },
      ],
      latest_capital_checkpoint: {
        ordinary_shares: null,
        as_of: "2026-10-22",
        published_date: "2026-10-30",
      },
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("推导的普通股股数：6325360667 股");
  expect(html).toContain("年度普通股事实 + 半年报总数及结构未变声明");
  expect(html).toContain("普通股股数：未核实");
  expect(html).toContain("预案所述总股本：6325360667 股");
  expect(html).toContain("回购专户库存股：1800200 股");
  expect(html).toContain("披露回购累计差额");
  expect(html).toContain("1680400 股");
  expect(html).toContain("49999397.00 元");
  expect(html).toContain("预案不是实施或注销证明");
  expect(html).toContain("每股拟派");
  expect(html).toContain("未计入已实施分配");
  expect(html).not.toContain("已核验普通股股数：未提供");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});
it("shows consumed model fields and never turns event price change into profit forecast", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![3].details = {
    candidate_event_impact: {
      schema_version: "candidate-event-impact-draft-v1",
      action: "no_order",
      materiality_approved: false,
      items: [
        {
          title: "TEST_ONLY",
          rationale: "渠道与税基未核",
          derived_price_changes: [
            {
              field: "retail_price",
              before: "100",
              after: "110",
              relative_change: "0.1",
              unit: "CNY/bottle",
            },
          ],
          derived_financial_changes: [
            {
              classification: "REPORTED_YTD_COMPARISON_NOT_FORECAST_CHANGE",
              field: "parent_profit_cny",
              unit: "CNY",
              current: "8444",
              comparative: "10000",
              relative_change: "-0.1556",
              physical_page: 8,
              period_start: "2026-01-01",
              period_end: "2026-09-30",
              comparative_start: "2025-01-01",
              comparative_end: "2025-09-30",
            },
          ],
          consumed_model_values: [
            { field: "revenue", value: "100", model_year: 1 },
          ],
          unresolved_inputs: ["实际销量未知"],
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("10.00%");
  expect(html).toContain("不是整体收入或利润增幅");
  expect(html).toContain("实际销量未知");
  expect(html).toContain("同比 -15.56%");
  expect(html).toContain("原件第 8 页。");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});

it.each([
  [
    "MATCHED_COMPLETED_BEFORE_VALUATION",
    "已与后续原件核对，确认该笔注销在估值日前完成。",
  ],
  ["CANCELLATION_NOT_UNIQUELY_RECONCILED", "注销尚未从后续原件唯一确认。"],
])(
  "renders historical purchase linkage %s and preserves the current gate",
  (status, expected) => {
    const review = alignmentFixture();
    const distribution = review.conditional_price!.alignment!.checks!.find(
      (check) => check.id === "distributions",
    )!;
    distribution.details = {
      opening_action_chain: {
        purchase_links: [
          {
            status,
            purchase_through: "2026-05-27",
            purchased_shares: 2188614,
            paid_cny: "2999933749.57",
            purchase_binding: {
              path: "runtime/purchase.pdf",
              sha256: "a".repeat(64),
            },
          },
        ],
      },
    };
    const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
    expect(html).toContain(expected);
    expect(html).toContain("2188614 股");
    expect(html).toContain("runtime/purchase.pdf");
    expect(candidateResearchComparisonMatches(review)).toBe(false);
  },
);

it("shows single model-consumed distribution without granting period alignment", () => {
  const review = alignmentFixture();
  const alignment = review.conditional_price!.alignment!;
  alignment.implemented_distribution_model_inclusion = {
    status: "PASS",
    reason_code: "IMPLEMENTED_DISTRIBUTION_INCLUDED_IN_MODEL",
    action: "no_order",
    paid_date: "2026-06-05",
    per_share_cny: "0.90",
    total_cny: "5692824600.30",
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("5692824600.30");
  expect(html).toContain("全期间分配仍须单独核验");
  alignment.candidate_binding = {
    path: "TEST_ONLY/other",
    sha256: "b".repeat(64),
  };
  expect(
    renderToStaticMarkup(<CandidatePriceDraft review={review} />),
  ).not.toContain("5692824600.30");
});

it("shows unsigned event review scope only for the current candidate", () => {
  const review = alignmentFixture();
  const alignment = review.conditional_price!.alignment!;
  const check = alignment.checks!.find((row) => row.id === "material_events")!;
  const route = {
    status: "EXACT_MATERIALITY_REVIEW_NOT_BOUND",
    unsigned_handoff: {
      human_review_required: true,
      action: "no_order",
      announcement_count: 119,
      scan_window: { scan_from: "2025-12-31", scan_to: "2026-11-18" },
    },
  };
  check.details = { materiality_review_route: route };
  const render = () =>
    renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(render()).toContain("候选重大事件待复核");
  expect(render()).toContain("2026-11-18");
  route.status = "EXISTING_AUTHENTICATED_MATERIALITY_REPLAYED";
  expect(render()).not.toContain("候选重大事件待复核");
  route.status = "EXACT_MATERIALITY_REVIEW_NOT_BOUND";
  alignment.input_descriptor_sha256 = "e".repeat(64);
  expect(render()).not.toContain("候选重大事件待复核");
});

it("renders both financing amounts only for a verified conflict", () => {
  const conflicts = [
    {
      scenario: "base",
      field: "debt_repayment",
      reported_ytd_cny: "202501881888.99",
      modeled_full_year_cny: "60000000000",
    },
  ];
  const closure = (status: string) => ({
    consumed_closure: [{ financing_comparison: { status, conflicts } }],
  });
  const html = renderToStaticMarkup(
    <FinancialFinancingConflicts value={closure("CONFLICT")} />,
  );
  expect(html).toContain("基准情景");
  expect(html).toContain("偿债支出");
  expect(html).toContain("202,501,881,888.99");
  expect(html).toContain("60,000,000,000.00");
  expect(
    renderToStaticMarkup(
      <FinancialFinancingConflicts value={closure("NOT_VERIFIED")} />,
    ),
  ).toBe("");
});

it("shows the trailing issuer listing confirmation with the comparison gate still blocked", () => {
  const review = alignmentFixture();
  review.conditional_price!.alignment!.checks![3].details = {
    operating_event_research: [
      {
        title: "TEST_ONLY 限售解禁",
        status: "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
        facts: [
          {
            terms: {
              event_type: "REPORTED_SHARE_UNLOCK_NOTICE",
              issuer_reported_listing_confirmation: {
                listing_date: "2026-09-28",
              },
            },
          },
        ],
      },
    ],
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("发行人后续报告确认上市流通");
  expect(html).toContain("2026-09-28");
  expect(html).toContain("比较日股本仍需独立核验");
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});

it("distinguishes reported parent financing and scheduled maturities", () => {
  const value = {
    schema_version: "parent-financing-schedule-v1",
    action: "no_order",
    actual_later_cash_verified: false,
    period_end: "2026-09-30",
    reported_ytd_cny: {
      borrowings_received_cny: "150",
      debt_repayments_paid_cny: "90",
    },
    later_issuance_proceeds_at_issue_price_cny: "98",
    scheduled_face_principal_by_maturity_cny: { "2026-12-29": "100" },
  };
  const html = renderToStaticMarkup(<ParentFinancingSchedule value={value} />);
  expect(html).toContain("2026-09-30");
  expect(html).toContain("2026-12-29 合同到期本金");
  expect(html).toContain("后续实际收付、剩余债务和续借条件待核验");
  expect(
    renderToStaticMarkup(
      <ParentFinancingSchedule
        value={{ ...value, actual_later_cash_verified: true }}
      />,
    ),
  ).toBe("");
});
it("shows verified publication coverage without conflating it with capital continuity", () => {
  const review = alignmentFixture();
  const capital = review.conditional_price!.alignment!.checks!.find(
    (check) => check.id === "capital_structure",
  )!;
  capital.details = {
    reconciliation: {
      ...reconciliationExample,
      cross_date_action_facts: {
        schema_version: "cross-date-action-facts-v1",
        valuation_date: "2026-06-30",
        comparison_date: "2026-11-20",
        publication_window_covered: true,
        effective_action_continuity_proven: false,
        row_proof_reconciliation: {
          status: "UNRESOLVED",
          matched_rows: [{ cash_payment_proven: false }],
          unmatched_ledger_ids: ["share-action-2"],
          unmatched_native_proofs: [{ announcement_id: "duplicate" }],
          duplicate_native_proofs: [{ announcement_id: "duplicate" }],
        },
        announcements: [
          {
            announcement_id: "example",
            published_at: "2026-08-20T00:00:00+08:00",
            title: "分红派息实施公告",
            status: "SCHEDULE_TERMS_ONLY",
          },
        ],
      },
    },
  };
  const html = renderToStaticMarkup(<CandidatePriceDraft review={review} />);
  expect(html).toContain("跨日公告逐项核验");
  expect(html).toContain("披露窗口已覆盖");
  expect(html).toContain("股本行动连续性和期间变化的估值重算仍待核验");
  expect(html).toMatch(/账本与原件双向核对：已匹配 .*1/);
  expect(html).toContain("未匹配账本 1 项");
  expect(html).toContain("未匹配原件 1 项");
  expect(html).toContain("重复引用 1 条");
  expect(html).toContain("分派安排已匹配，实际到账仍待核验。");
  expect(html).toContain("已核对分派安排，实际支付待核");
});
