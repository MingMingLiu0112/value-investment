import React from "react";
import { expect, it } from "vitest";
import { ValueResearchAnalysis } from "../src/components/ValueResearchAnalysis";
import { analysisDecision } from "./fixtures/value-research-analysis";
import { readinessNumber } from "../src/utils/strategyReadiness";
const { renderToStaticMarkup } = require("react-dom/server");

it("shows a collapsed source-bound analysis with actual dates, inputs, counterevidence and bounded precision", () => {
  const decision = analysisDecision();
  const original = structuredClone(decision);
  const html = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  expect(html).toContain('<details class="value-research-analysis"');
  expect(html).not.toContain('<details open=""');
  for (const text of [
    "2026-10-11",
    "2026-10-21",
    "9.7976",
    "10.0988",
    "11.2865",
    "0.09",
    "0.20 / 0.21",
    "登记的情景端点",
    "仍需复核经济一致性",
    "竞争压力仍未排除",
    "经济假设与模型适用范围待复核",
    "source-bound-package.json",
    "a".repeat(64),
    "不是精确合理价",
    "经济假设未复核",
    "未获操作准入",
    "不代表联合情景",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("10.098818123456789");
  expect(html).not.toContain("999999");
  expect(html).toContain("该端点未形成可核验结果");
  expect(decision).toEqual(original);
});

it.each([
  { schema_version: "unknown" },
  { status: "SOURCE_OR_REPLAY_UNAVAILABLE" },
  { symbol: "600519" },
  { action: "buy" },
  { arithmetic_complete: false },
  { economic_assumptions_reviewed: true },
  { action_admitted: true },
  { price_comparison_eligible: true },
  { strategy_admitted: true },
  { source_bindings: [] },
  { source_bindings: [{ path: "source", sha256: "wrong" }] },
])(
  "hides numbers for an incompatible or unverifiable analysis %j",
  (change) => {
    const decision = analysisDecision();
    Object.assign(decision.price_action_plan!.research_analysis!, change);
    const html = renderToStaticMarkup(
      <ValueResearchAnalysis decision={decision} />,
    );
    expect(html).toContain("暂不展示计算结果");
    expect(html).not.toContain("10.0988");
  },
);

it("does not invent absent scenarios, sensitivities, counterevidence or model approval", () => {
  const decision = analysisDecision();
  Object.assign(decision.price_action_plan!.research_analysis!, {
    scenarios: [],
    sensitivity: null,
    counter_evidence: null,
    model_applicability: null,
  });
  const html = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  expect(html).toContain("输入未提供");
  expect(html).toContain("尚无可展示的敏感性结果");
  expect(html).toContain("反证未提供，不代表没有风险");
  expect(html).toContain("不能认定已通过");
});

it("preserves legacy and independent hotspot views without adding a value prerequisite", () => {
  const decision = analysisDecision();
  decision.strategy = "hotspot";
  expect(
    renderToStaticMarkup(<ValueResearchAnalysis decision={decision} />),
  ).toBe("");
  decision.strategy = "value";
  delete decision.price_action_plan!.research_analysis;
  expect(
    renderToStaticMarkup(<ValueResearchAnalysis decision={decision} />),
  ).toBe("");
});

it("formats API decimals for display without exposing false precision", () => {
  expect(readinessNumber("587.88296875291234567890123456789")).toBe("587.883");
  expect(readinessNumber("10.0988181234567890123456789")).toBe("10.0988");
  expect(readinessNumber(null)).toBe("未提供");
});
