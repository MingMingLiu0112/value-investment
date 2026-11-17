import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import { EconomicReviewResult } from "../src/components/SourceNativeEconomicReview";
import { verifiedEconomicReview } from "../src/services/sourceNativeEconomicReview";
import { economicFixture, economicRef } from "./fixtures/sourceNativeEconomic";
import { readFileSync } from "node:fs";

function fixture() {
  const parent = economicFixture();
  parent.point_in_time = { report_period: "2026-06-30" };
  parent.evaluated_at = "2026-10-24T13:00:01+00:00";
  const replacement = {
    path: "runtime/TEST_ONLY/replacement.json",
    sha256: "b".repeat(64),
  };
  const evidence = {
    path: "runtime/TEST_ONLY/inputs.json",
    sha256: "c".repeat(64),
  };
  parent.source_bindings.push(replacement, evidence);
  parent.replacement_bear = {
    schema_version: "source-native-replacement-bear-comparison-v1",
    status: "VERIFIED_BOUND_RESEARCH_COMPARISON",
    symbol: "600519",
    confidence: "LOW",
    action: "no_order",
    scope: "CONDITIONAL_OPERATING_EROSION_NOT_FULL_DOWNSIDE_OR_ENTRY_PRICE",
    baseline_candidate_binding: { ...economicRef },
    replacement_candidate_binding: replacement,
    evidence_binding: evidence,
    observed_at: "2026-10-24T13:00:00+00:00",
    replacement_generated_at: "2026-10-24T13:00:00+00:00",
    input_available_at: "2026-10-24T13:00:00+00:00",
    base_bull_exactly_preserved: true,
    normalized_parent_profit_cny: null,
    research_admitted: false,
    price_admitted: false,
    formal_eligibility: false,
    strategy_approved: false,
    original_bear: { per_historical_share_cny: "100" },
    replacement_bear: { per_historical_share_cny: "80" },
    difference_per_historical_share_cny: "-20",
    negative_conditions: ["TEST_ONLY seasonality counter-evidence"],
    derived_historical_ratios: {
      mixed_realization_factor: ".97",
      h1_cost_ratio: ".1",
    },
    operating_rows: Array.from({ length: 5 }, (_, i) => ({
      year: i + 1,
      revenue: "1000",
      legacy_ex_parent: "100",
    })),
    annual_cash_rows: Array.from({ length: 5 }, (_, i) => ({
      year: i + 1,
      profit: "101",
      cash_close: "200",
      book_close: "1000",
      dividend_paid: "90",
    })),
    source_bindings: [replacement, evidence],
  };
  return parent;
}

it("renders the optional comparison separately from baseline and persistent withholding", () => {
  const value = fixture();
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(true);
  const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
  for (const text of [
    "经营侵蚀替代 bear",
    "不是纯售价",
    "季节性",
    "base/bull",
    "不是完整下行",
    "次年回款",
    "第5年",
    "新旧候选绑定",
  ])
    expect(html).toContain(text);
});

it.each([
  "null",
  "unknown",
  "baseline",
  "formal",
  "price",
  "source",
  "same_path",
  "delta",
  "missing_year",
  "ratio",
  "invalid_date",
  "unknown_profit",
  "future_observation",
  "invalid_calendar",
  "wrong_basis",
  "wrong_generated",
  "wrong_available",
])("rejects malformed optional comparison %s", (damage) => {
  const value = fixture(),
    v = value.replacement_bear;
  if (damage === "null") value.replacement_bear = null;
  else if (damage === "unknown") v.status = "UNKNOWN";
  else if (damage === "baseline")
    v.baseline_candidate_binding = { ...economicRef, sha256: "d".repeat(64) };
  else if (damage === "formal") v.formal_eligibility = true;
  else if (damage === "price") v.price_admitted = true;
  else if (damage === "source")
    v.source_bindings = [{ ...v.evidence_binding, sha256: "d".repeat(64) }];
  else if (damage === "same_path")
    v.replacement_candidate_binding = {
      ...economicRef,
      sha256: "d".repeat(64),
    };
  else if (damage === "delta") v.difference_per_historical_share_cny = "20";
  else if (damage === "missing_year") v.annual_cash_rows.pop();
  else if (damage === "ratio")
    v.derived_historical_ratios.mixed_realization_factor = "1.5";
  else if (damage === "invalid_date") v.observed_at = "not-a-date";
  else if (damage === "future_observation")
    v.observed_at = "2099-01-01T00:00:00+00:00";
  else if (damage === "invalid_calendar")
    v.observed_at = "2026-02-30T00:00:00+00:00";
  else if (damage === "wrong_basis")
    value.share_basis.financial_basis = "2025-06-30";
  else if (damage === "wrong_generated")
    v.replacement_generated_at = "2020-01-01T00:00:00+00:00";
  else if (damage === "wrong_available")
    v.input_available_at = "2020-01-01T00:00:00+00:00";
  else v.normalized_parent_profit_cny = "100";
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(false);
  expect(
    renderToStaticMarkup(<EconomicReviewResult value={value} />),
  ).not.toContain("新旧候选绑定");
});

it("keeps a missing optional appendix compatible", () => {
  expect(verifiedEconomicReview(economicFixture(), "600519", economicRef)).toBe(
    true,
  );
});

it("compares observation timestamps as instants rather than timezone strings", () => {
  const value = fixture();
  value.replacement_bear.observed_at = "2026-10-24T21:00:00+08:00";
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(true);
  value.replacement_bear.observed_at = "2026-10-24T13:00:00.000001+00:00";
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(false);
});

it("rejects impossible financial dates without a replacement appendix", () => {
  const value = economicFixture();
  value.point_in_time = { report_period: "2026-02-30" };
  value.share_basis.financial_basis = "2026-02-30";
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(false);
});

it.each(["2099-01-01T00:00:00+00:00", "2026-02-30T00:00:00+00:00"])(
  "rejects coordinated future or impossible timestamps %s",
  (timestamp) => {
    const value = fixture();
    Object.assign(value.replacement_bear, {
      observed_at: timestamp,
      replacement_generated_at: timestamp,
      input_available_at: timestamp,
    });
    value.evaluated_at = timestamp;
    expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(false);
  },
);

it("rejects a malformed parent scenario container without throwing", () => {
  const value = fixture();
  value.scenarios = {};
  expect(verifiedEconomicReview(value, "600519", economicRef)).toBe(false);
});

it.skipIf(!process.env.ECONOMIC_COMPARISON_JSON)(
  "validates and renders actual official-input HTTP response",
  () => {
    const value = JSON.parse(
      readFileSync(process.env.ECONOMIC_COMPARISON_JSON!, "utf-8"),
    );
    expect(
      verifiedEconomicReview(value, "600519", value.candidate_binding),
    ).toBe(true);
    const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
    expect(html).toContain("新旧候选绑定");
    expect(html).toContain("次年回款");
  },
);
