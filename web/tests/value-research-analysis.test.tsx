import React from "react";
import { expect, it } from "vitest";
import { ValueResearchAnalysis } from "../src/components/ValueResearchAnalysis";
import { analysisDecision } from "./fixtures/value-research-analysis";
import { readinessNumber } from "../src/utils/strategyReadiness";
import {
  jointRowFields,
  jointTerminalFields,
  publicJointCapitalReviewMatches,
} from "../src/services/valuePolicy";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
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

function jointDecision() {
  const decision = analysisDecision();
  const analysis = decision.price_action_plan!.research_analysis!;
  const candidate = {
    path: "TEST_ONLY/candidate.json",
    sha256: "b".repeat(64),
  };
  const proposal = { path: "TEST_ONLY/proposal.json", sha256: "c".repeat(64) };
  const policy = { path: "TEST_ONLY/policy.json", sha256: "d".repeat(64) };
  analysis.input_descriptor_sha256 = "e".repeat(64);
  analysis.review_binding = {
    candidate_binding: structuredClone(candidate),
    model_context: {
      input_descriptor_sha256: analysis.input_descriptor_sha256,
      model_id: "TEST_ONLY_RI",
    },
  };
  analysis.source_bindings.push(candidate, proposal, policy);
  analysis.joint_capital_review = {
    schema_version: "joint-capital-review-v1",
    symbol: analysis.symbol,
    action: "no_order",
    status: "CONDITIONAL_PATH_NOT_APPROVED",
    scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS",
    candidate_binding: structuredClone(candidate),
    proposal_binding: structuredClone(proposal),
    policy_binding: structuredClone(policy),
    input_descriptor_sha256: analysis.input_descriptor_sha256,
    selected_choice: "TEST_ONLY_CONDITIONAL",
    date_scope: "DATED_CONDITIONAL_MODEL",
    basis_at: "2026-06-30T23:59:59+08:00",
    valuation_at: "2026-10-11T08:00:00Z",
    scenarios: (["bear", "base", "bull"] as const).map((scenario) => ({
      scenario,
      valuation_per_share: "100.123456789",
      drivers: {
        years: Array.from({ length: 5 }, (_, i) => ({
          year: i + 1,
          revenue_growth: "0.01",
          cost_ratio: "0.2",
        })),
        retention: "0.1",
        operating_allocation: "0.9",
        new_operating_return: "0.1",
        new_liquidity_return: "0.01",
        parent_cash_conversion: "1",
        terminal_growth: "0.01",
        terminal_profit_scale: "1",
      },
      ledger: {
        ...Object.fromEntries(jointTerminalFields.map((key) => [key, "0.1"])),
        forecast_roe: Array(5).fill("0.1"),
        cash_funding_status: "PASS",
        scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS",
        limitations: ["TEST_ONLY unapproved cash conversion"],
        rows: Array.from({ length: 5 }, (_, i) => ({
          ...Object.fromEntries(
            jointRowFields.map((key) => [key, "123456789.123456789"]),
          ),
          year: i + 1,
          cash_funding_status: "PASS",
        })),
      },
    })),
  };
  return decision;
}

const render = (decision = jointDecision()) =>
  renderToStaticMarkup(<ValueResearchAnalysis decision={decision} />);

it("shows the public three-scenario five-year ledger without signing context or requests", () => {
  const decision = jointDecision(),
    before = structuredClone(decision),
    html = render(decision);
  expect(
    publicJointCapitalReviewMatches(
      decision.price_action_plan!.research_analysis!,
      decision.symbol!,
    ),
  ).toBe(true);
  for (const text of [
    "公开联合经营与资本年度账",
    "前瞻假设",
    "LOW",
    "未批准",
    "不是正常化事实",
    "谨慎情景",
    "中性条件情景",
    "乐观情景",
    "第 5 年",
    "未来假设",
    "经营资本",
    "流动资本",
    "现金代理",
    "终端 ROE 假设（非已验证 ROIC）",
    "2026-06-30T23:59:59+08:00",
    "2026-10-11T08:00:00Z",
    "TEST_ONLY/proposal.json",
    "123456789.123456789",
    "不代表可分红能力",
  ])
    expect(html).toContain(text);
  for (const text of [
    "EXTERNAL_SIGNATURE_REQUIRED",
    "unsigned_response",
    "pinned_root",
    "五组待审材料",
    "<button",
    "<form",
    "<input",
  ])
    expect(html).not.toContain(text);
  expect(decision).toEqual(before);
});

it("keeps FAIL and negative cash visible in the public path", () => {
  const decision = jointDecision();
  const ledger =
    decision.price_action_plan!.research_analysis!.joint_capital_review!
      .scenarios[0].ledger;
  ledger.cash_funding_status = "FAIL";
  ledger.rows[0].cash_funding_status = "FAIL";
  ledger.rows[0].cash_close = "-123456789.123456789";
  expect(render(decision)).toContain("FAIL：假设路径存在现金资金缺口");
  expect(render(decision)).toContain("-1.23 亿元");
  expect(render(decision)).toContain("-123456789.123456789");
});

it("preserves undated conditional models without borrowing computed_at", () => {
  const decision = jointDecision(),
    review =
      decision.price_action_plan!.research_analysis!.joint_capital_review!;
  review.date_scope = "UNDATED_CONDITIONAL_MODEL";
  review.basis_at = null;
  review.valuation_at = null;
  const html = render(decision);
  expect(html).toContain("未建立定价时点");
  expect(html).toContain("不能当作当前价值");
  expect(html).not.toContain("资料基准：2026-10-22");
});

it.each([
  (a: any) => {
    delete a.review_binding;
  },
  (a: any) => {
    a.review_binding.candidate_binding.path = "TEST_ONLY/another.json";
  },
  (a: any) => {
    a.review_binding.candidate_binding.sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.review_binding.model_context.input_descriptor_sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.review_binding.model_context = null;
  },
  (a: any) => {
    a.review_binding.model_context.bad = Infinity;
  },
  (a: any) => {
    delete a.input_descriptor_sha256;
  },
  (a: any) => {
    a.source_bindings = a.source_bindings.slice(0, 1);
  },
  (a: any) => {
    a.source_bindings[2].sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.joint_capital_review.symbol = "600519";
  },
  (a: any) => {
    a.joint_capital_review.action = "order";
  },
  (a: any) => {
    a.joint_capital_review.schema_version = "other";
  },
  (a: any) => {
    a.joint_capital_review.status = "APPROVED";
  },
  (a: any) => {
    a.joint_capital_review.scope = "NORMALIZED_FACTS";
  },
  (a: any) => {
    a.joint_capital_review.candidate_binding.path = "../escape.json";
  },
  (a: any) => {
    a.joint_capital_review.input_descriptor_sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.joint_capital_review.policy_binding.sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.joint_capital_review.proposal_binding.path = "TEST_ONLY/another.json";
  },
  (a: any) => {
    a.joint_capital_review.date_scope = "UNKNOWN";
  },
  (a: any) => {
    a.joint_capital_review.basis_at = null;
  },
  (a: any) => {
    a.joint_capital_review.valuation_at = "invalid";
  },
  (a: any) => {
    a.joint_capital_review.scenarios.pop();
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].ledger.rows[1].year = 1;
  },
  (a: any) => {
    delete a.joint_capital_review.scenarios[0].ledger.rows[0].profit;
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].ledger.rows[0].cash_close = "NaN";
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].ledger.terminal_roe = "Infinity";
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].drivers.retention = null;
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].ledger.forecast_roe[0] = true;
  },
  (a: any) => {
    a.joint_capital_review.scenarios[0].valuation_per_share = "1e9999";
  },
  (a: any) => {
    a.economic_assessment = {
      symbol: "600887",
      action: "no_order",
      input_descriptor_sha256: a.input_descriptor_sha256,
      primary_valuation_usable: false,
      economic_assumptions_reviewed: false,
      review_binding: {
        ...a.review_binding,
        model_context: {
          input_descriptor_sha256: a.input_descriptor_sha256,
          model_id: "OTHER",
        },
      },
    };
  },
])(
  "fails closed on public ledger contract mismatch %# without hiding legacy research",
  (change) => {
    const decision = jointDecision(),
      analysis = decision.price_action_plan!.research_analysis!;
    change(analysis);
    expect(publicJointCapitalReviewMatches(analysis, decision.symbol!)).toBe(
      false,
    );
    const html = render(decision);
    expect(html).not.toContain("123456789.123456789");
    expect(html).toContain("暂不可作为核验结果展示");
  },
);

it("keeps legacy analyses without the optional ledger unchanged", () => {
  const decision = jointDecision();
  delete decision.price_action_plan!.research_analysis!.joint_capital_review;
  expect(render(decision)).not.toContain("公开联合经营与资本年度账");
  expect(render(decision)).toContain("单因素敏感性");
});

it.skipIf(!process.env.PUBLIC_JOINT_ANALYSIS)(
  "renders the actual source-revalidated static CC1 analysis without a live API",
  () => {
    const analysis = JSON.parse(
      readFileSync(process.env.PUBLIC_JOINT_ANALYSIS!, "utf8"),
    );
    const decision = jointDecision();
    decision.symbol = analysis.symbol;
    decision.price_action_plan!.research_analysis = analysis;
    const before = structuredClone(decision);
    expect(publicJointCapitalReviewMatches(analysis, decision.symbol!)).toBe(
      true,
    );
    expect(render(decision)).toContain("公开联合经营与资本年度账");
    expect(render(decision)).toContain(
      analysis.joint_capital_review.proposal_binding.sha256,
    );
    expect(decision).toEqual(before);
  },
);

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "fits the public actual CC1 analysis at 320 and 390 without a server",
  async () => {
    const output = resolve("../.tmp/public-joint-capital-layout");
    mkdirSync(output, { recursive: true });
    const decision = jointDecision();
    if (process.env.PUBLIC_JOINT_ANALYSIS) {
      const analysis = JSON.parse(
        readFileSync(process.env.PUBLIC_JOINT_ANALYSIS, "utf8"),
      );
      decision.symbol = analysis.symbol;
      decision.price_action_plan!.research_analysis = analysis;
    }
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const context = await chromium.launchPersistentContext(
      resolve(output, "profile"),
      {
        executablePath: process.env.READINESS_BROWSER_PATH,
        headless: true,
        downloadsPath: output,
      },
    );
    try {
      const page = await context.newPage(),
        measurements: unknown[] = [];
      await page.route("**/*", (route: any) => route.abort());
      const css = readFileSync(
        resolve("src/components/value-research-analysis.css"),
        "utf8",
      );
      for (const width of [320, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.setContent(
          `<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{box-sizing:border-box;width:100%;padding:16px}${css}</style><main>${render(decision)}</main></html>`,
        );
        await page
          .locator("details")
          .evaluateAll((elements: HTMLDetailsElement[]) =>
            elements.forEach((element) => {
              element.open = true;
            }),
          );
        const size = await page.evaluate(() => ({
          width: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          overflowing: [...document.querySelectorAll("main *")]
            .filter((element) => {
              const box = element.getBoundingClientRect();
              return (
                box.width > 0 && (box.right > innerWidth + 1 || box.left < -1)
              );
            })
            .map((element) => element.tagName),
        }));
        expect(size.scrollWidth).toBeLessThanOrEqual(width);
        expect(size.overflowing).toEqual([]);
        measurements.push(size);
        await page
          .locator('[aria-label="公开联合经营与资本年度账"]')
          .evaluate((element: HTMLElement) =>
            element.scrollIntoView({ block: "start" }),
          );
        await page.screenshot({ path: resolve(output, `${width}.png`) });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(measurements, null, 2),
      );
    } finally {
      await context.close();
    }
  },
  90000,
);
