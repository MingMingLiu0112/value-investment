import React from "react";
import { expect, it } from "vitest";
import { AccountingBridgeReview } from "../src/components/AccountingBridgeReview";
import type { AccountingBridgeReview as Review } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");

function fixture(): Review {
  return {
    schema_version: "economic-review-bundle-v1",
    symbol: "600519",
    action: "no_order",
    status: "HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL",
    input_descriptor_sha256: "a".repeat(64),
    bundle_sha256: "b".repeat(64),
    primary_valuation_usable: false,
    economic_approval_granted: false,
    source_bindings: [{ path: "filing.pdf", sha256: "c".repeat(64) }],
    unknown_fields: ["/model_binding/forward_distribution_capacity_cny"],
    bridge_results: [
      {
        kind: "parent_cash",
        period: "FY2025",
        entity_scope: "issuer_parent_standalone",
        unit: "CNY",
        source_binding: { path: "filing.pdf", sha256: "c".repeat(64) },
        source_url: "https://example.org/filing.pdf",
        physical_pages: [25, 26],
        terms: { opening_cash_and_equivalents_cny: "100", cfo_cny: "20" },
        reported_adjustment: null,
        derived_adjustment_cny: "-10",
        computed_closing_cny: "110",
        reported_closing_cny: "110",
        difference_cny: "0",
        assurance: "BOUND_RESEARCH_ARITHMETIC_NOT_NEW_PDF_ROW_CERTIFICATION",
      },
    ],
  };
}

function render(review = fixture(), descriptor = "a".repeat(64)) {
  return renderToStaticMarkup(
    <AccountingBridgeReview
      review={review}
      symbol="600519"
      descriptor={descriptor}
    />,
  );
}

it("explains reconciled history and derived adjustments without approving economics", () => {
  const review = fixture();
  const original = structuredClone(review);
  const html = render(review);
  for (const text of [
    "2025 年度",
    "上市母公司",
    "经营现金净流量",
    "110",
    "25、26",
    "派生调节项",
    "未独立核验原文",
    "不能据此认定",
    "1 处未确定",
    "https://example.org/filing.pdf",
  ])
    expect(html).toContain(text);
  expect(review).toEqual(original);
});

it.each([
  { symbol: "600887" },
  { input_descriptor_sha256: "d".repeat(64) },
  { economic_approval_granted: true },
  { source_bindings: [] },
  { status: "PASSED" },
  { bridge_results: [] },
])(
  "does not display amounts from inconsistent review metadata %j",
  (change) => {
    const review = Object.assign(fixture(), change) as Review;
    const html = render(review);
    expect(html).toContain("暂不展示金额");
    expect(html).not.toContain("110");
  },
);

it("rejects a row detached from the verified source bindings", () => {
  const review = fixture();
  review.bridge_results[0].source_binding.sha256 = "d".repeat(64);
  expect(render(review)).toContain("暂不展示金额");
});

it("does not treat an unsupported bridge or zero unknowns as completed review", () => {
  const review = fixture();
  review.status = "NO_SUPPORTED_BOUND_BRIDGE";
  review.bridge_results = [];
  review.unknown_fields = [];
  expect(render(review)).toContain("尚无可核验");
  const supported = fixture();
  supported.unknown_fields = [];
  expect(render(supported)).toContain("不代表经济假设已获审核");
});

it("never renders an executable evidence URL", () => {
  const review = fixture();
  review.bridge_results[0].source_url = "javascript:alert(1)";
  expect(render(review)).not.toContain("javascript:");
  expect(render(review)).toContain("原文链接不可用");
});
