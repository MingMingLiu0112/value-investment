import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import { OperatingEarningsBridge } from "../src/components/OperatingEarningsBridge";
import { analysisFixture } from "./fixtures/value-research-analysis";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { readinessNumber } from "../src/utils/strategyReadiness";

function fixture() {
  const analysis = analysisFixture();
  analysis.input_descriptor_sha256 = "a".repeat(64);
  analysis.review_binding = {
    model_context: {
      input_descriptor_sha256: analysis.input_descriptor_sha256,
    },
    candidate_binding: {
      path: "TEST_ONLY/candidate.json",
      sha256: "b".repeat(64),
    },
  };
  analysis.economic_assessment = {
    schema_version: "value-economic-assessment-v1",
    symbol: analysis.symbol,
    action: "no_order",
    economic_assumptions_reviewed: false,
    primary_valuation_usable: false,
    blockers: [],
    earnings: {
      historical_ex_nonrecurring_ttm_cny: "100",
      normalization_status: "NOT_ESTABLISHED",
      operating_quality_bridge: {
        status: "SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED",
        schema_version: "operating-earnings-quality-bridge-v1",
        symbol: analysis.symbol,
        action: "no_order",
        input_descriptor_sha256: analysis.input_descriptor_sha256,
        candidate_binding: analysis.review_binding!.candidate_binding,
        g3_changed: false,
        price_admitted: false,
        strategy_admitted: false,
        normalized_earnings_admitted: false,
        normalized_parent_profit_cny: null,
        normalized_range: null,
        historical_ttm_cny: "100",
        commercial_subtotal: { change_cny: "50" },
        annual_change: { computed_change_cny: "20" },
        h1_change: {
          period: "H12026_VS_H12025",
          computed_change_cny: "-10",
          arithmetic_residual_cny: "0.00",
          rows: [
            {
              field: "asset_impairment",
              current_cny: "-20",
              comparative_cny: "-10",
              contribution_cny: "-10",
              fact_refs: [
                {
                  field: "asset_impairment",
                  label: "资产减值损失",
                  source_id: "TEST_ONLY",
                  source_url: "https://example.test/filing.pdf",
                  physical_page: 52,
                  sha256: "c".repeat(64),
                  excerpt: "TEST_ONLY_SOURCE_EXCERPT",
                },
              ],
            },
          ],
        },
      },
    },
  };
  return analysis;
}

it("explains source-bound drivers without creating normalized earnings or buying permission", () => {
  const html = renderToStaticMarkup(
    <OperatingEarningsBridge analysis={fixture()} />,
  );
  for (const text of [
    "利润为什么变化",
    "商业小计不是正常化利润",
    "不能直接把税前损失加回",
    "正常化盈利仍未知",
    "资产减值",
    "example.test/filing.pdf",
    "TEST_ONLY_SOURCE_EXCERPT",
    "残差为零仅证明",
  ])
    expect(html).toContain(text);
});

it.each([
  "symbol",
  "descriptor",
  "candidate",
  "approval",
  "normalized",
  "unavailable",
])("hides figures on %s mismatch", (fault) => {
  const analysis = fixture();
  const review: any =
    analysis.economic_assessment!.earnings!.operating_quality_bridge!;
  if (fault === "symbol") review.symbol = "600519";
  if (fault === "descriptor") review.input_descriptor_sha256 = "d".repeat(64);
  if (fault === "candidate")
    review.candidate_binding = {
      ...review.candidate_binding,
      path: "TEST_ONLY/other.json",
    };
  if (fault === "approval") review.g3_changed = true;
  if (fault === "normalized") review.normalized_parent_profit_cny = "999";
  if (fault === "unavailable") review.status = "SOURCE_REVALIDATION_FAILED";
  const html = renderToStaticMarkup(
    <OperatingEarningsBridge analysis={analysis} />,
  );
  expect(html).toContain("暂不展示金额");
  expect(html).not.toContain("TEST_ONLY_SOURCE_EXCERPT");
  expect(html).not.toContain("filing.pdf");
});

it.skipIf(!process.env.OPERATING_BRIDGE_ANALYSIS)(
  "renders the exact actual public application result without fixture substitution",
  () => {
    const raw = readFileSync(process.env.OPERATING_BRIDGE_ANALYSIS!);
    expect(createHash("sha256").update(raw).digest("hex")).toBe(
      process.env.OPERATING_BRIDGE_ANALYSIS_SHA256,
    );
    const analysis = JSON.parse(raw.toString("utf8"));
    const review =
      analysis.economic_assessment.earnings.operating_quality_bridge;
    const html = renderToStaticMarkup(
      <OperatingEarningsBridge analysis={analysis} />,
    );
    expect(html).toContain("利润为什么变化");
    expect(html).toContain(
      readinessNumber(review.h1_change.computed_change_cny),
    );
    expect(html).toContain("static.cninfo.com.cn");
    expect(html).toContain("正常化盈利仍未知");
    expect(review.g3_changed).toBe(false);
    expect(review.normalized_parent_profit_cny).toBeNull();
  },
);
