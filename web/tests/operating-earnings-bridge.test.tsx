import React from "react";
import { expect, it } from "vitest";
import { ValueResearchAnalysis } from "../src/components/ValueResearchAnalysis";
const { renderToStaticMarkup } = require("react-dom/server");
import { OperatingEarningsBridge } from "../src/components/OperatingEarningsBridge";
import {
  analysisFixture,
  analysisDecision,
} from "./fixtures/value-research-analysis";
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

function independentFixture() {
  const analysis = fixture();
  const review = structuredClone(
    analysis.economic_assessment!.earnings!.operating_quality_bridge!,
  );
  delete review.candidate_binding;
  delete review.input_descriptor_sha256;
  Object.assign(review, {
    context_scope: "INDEPENDENT_RETAINED_FILINGS_V1",
    scope: "HISTORICAL_EARNINGS_DRIVERS_NOT_FORWARD_NORMALIZED_EARNINGS",
    availability_scope:
      "RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF",
    read_at: "2026-10-24T14:00:00Z",
    report_periods: [
      ["FY2025", "FY2024"],
      ["H12026", "H12025"],
    ],
    execution_bindings: Array.from({ length: 4 }, (_, i) => ({
      path: `TEST_ONLY/parser-${i}.py`,
      sha256: "d".repeat(64),
    })),
    action_admitted: false,
    approval_changed: false,
    primary_valuation_usable: false,
    source_spec_binding: {
      path: "TEST_ONLY/sources.json",
      sha256: "e".repeat(64),
    },
    source_bindings: [
      {
        source_id: "TEST_ONLY_ANNUAL",
        path: "TEST_ONLY/annual.pdf",
        sha256: "f".repeat(64),
        source_url: "https://example.test/annual.pdf",
        published_date: "2026-04-30",
        original_acquired_at: null,
      },
      {
        source_id: "TEST_ONLY",
        path: "TEST_ONLY/interim.pdf",
        sha256: "c".repeat(64),
        source_url: "https://example.test/filing.pdf",
        published_date: "2026-08-27",
        original_acquired_at: null,
      },
    ],
  });
  review.h1_change!.rows[0].fact_refs[0].path = "TEST_ONLY/interim.pdf";
  analysis.status = "SOURCE_OR_REPLAY_UNAVAILABLE";
  analysis.arithmetic_complete = false;
  analysis.scenarios = [];
  analysis.source_bindings = [];
  delete analysis.economic_assessment;
  analysis.historical_operating_review = review;
  const decision = analysisDecision();
  decision.price_action_plan!.research_analysis = analysis;
  return decision;
}

it("shows independently bound historical drivers before the old valuation early return", () => {
  const decision = independentFixture();
  const html = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  for (const text of [
    "暂不展示计算结果",
    "利润为什么变化",
    "独立财报解释",
    "未知（不补造）",
    "TEST_ONLY_SOURCE_EXCERPT",
    "本次读取核验",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("三情景与实际模型输入");
  expect(html).not.toContain("已完成计算，经济假设未复核");
});

it.each([
  "symbol",
  "spec_hash",
  "source_hash",
  "ref_path",
  "execution_hash",
  "read_at",
  "candidate",
  "normalized",
  "permission",
  "period",
])("hides independent numbers on %s mismatch", (fault) => {
  const decision = independentFixture();
  const analysis = decision.price_action_plan!.research_analysis!;
  const review = analysis.historical_operating_review!;
  if (fault === "symbol") analysis.symbol = "600519";
  if (fault === "spec_hash") review.source_spec_binding!.sha256 = "BAD";
  if (fault === "source_hash")
    review.source_bindings![1].sha256 = "a".repeat(64);
  if (fault === "ref_path")
    review.h1_change!.rows[0].fact_refs[0].path = "TEST_ONLY/wrong.pdf";
  if (fault === "execution_hash") review.execution_bindings![0].sha256 = "BAD";
  if (fault === "read_at") delete review.read_at;
  if (fault === "candidate")
    review.candidate_binding = {
      path: "TEST_ONLY/old-candidate.json",
      sha256: "a".repeat(64),
    };
  if (fault === "normalized")
    (review as any).normalized_parent_profit_cny = "100";
  if (fault === "permission") (review as any).action_admitted = true;
  if (fault === "period")
    review.report_periods = [
      ["FY2024", "FY2023"],
      ["H12026", "H12025"],
    ];
  const html = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  expect(html).not.toContain("TEST_ONLY_SOURCE_EXCERPT");
  expect(html).not.toContain("利润为什么变化");
  expect(html).not.toContain("三情景与实际模型输入");
});

it.skipIf(!process.env.RETAINED_OPERATING_CONSUMER_OUTPUT)(
  "renders real native public HTTP failure plus independent official bridge",
  () => {
    const output = JSON.parse(
      readFileSync(process.env.RETAINED_OPERATING_CONSUMER_OUTPUT!, "utf8"),
    );
    const decision = output.isolated_http.decision;
    const analysis = decision.price_action_plan.research_analysis;
    expect(analysis.status).toBe("SOURCE_OR_REPLAY_UNAVAILABLE");
    expect(analysis.arithmetic_complete).toBe(false);
    expect(analysis.scenarios).toEqual([]);
    const html = renderToStaticMarkup(
      <ValueResearchAnalysis decision={decision} />,
    );
    expect(html).toContain("利润为什么变化");
    expect(html).toContain("static.cninfo.com.cn");
    expect(html).toContain("正常化盈利仍未知");
    expect(html).toContain("旧估值候选绑定的是旧程序版本");
    expect(html).not.toContain("三情景与实际模型输入");
  },
);

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
