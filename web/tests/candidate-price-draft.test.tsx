import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import {
  CandidatePriceDraft,
  candidatePriceMatches,
} from "../src/components/CandidatePriceDraft";
import type { JointCapitalReview } from "../src/services/valuePolicy";

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
