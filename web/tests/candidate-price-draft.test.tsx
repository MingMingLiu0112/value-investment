import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import {
  CandidatePriceDraft,
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
    reason_codes: ["ALIGNMENT_INCOMPLETE"],
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
  expect(html).not.toContain("当前研究比较口径已核验，仍未批准");
});
