import React from "react";
import { expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { ValueResearchAnalysis } from "../src/components/ValueResearchAnalysis";
import { analysisDecision } from "./fixtures/value-research-analysis";
import { readinessNumber } from "../src/utils/strategyReadiness";
import {
  jointRowFields,
  jointTerminalFields,
  publicJointCapitalReviewMatches,
  sourceNativeCashReviewMatches,
  nativeCashFields,
} from "../src/services/valuePolicy";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const { renderToStaticMarkup } = require("react-dom/server");

/** TEST_ONLY source-shaped contract, not a coherent financial model or approval. */
function nativeDecision() {
  const decision = analysisDecision();
  const analysis: any = decision.price_action_plan!.research_analysis!;
  const candidate = {
    path: "TEST_ONLY/native-candidate.json",
    sha256: "b".repeat(64),
  };
  const source = {
    path: "TEST_ONLY/native-source.json",
    sha256: "c".repeat(64),
  };
  const context = {
    input_descriptor_sha256: "a".repeat(64),
    research_case_sha256: "d".repeat(64),
    facts_sha256: "e".repeat(64),
    assumptions_sha256: "f".repeat(64),
    model_id: "TEST_ONLY_MODEL",
    model_version: "TEST_ONLY_V1",
    profile_id: "TEST_ONLY_PROFILE",
    research_as_of: "2026-10-24",
  };
  const timing = {
    basis_at: "2026-06-30T23:59:59+08:00",
    valuation_at: "2026-06-30T23:59:59+08:00",
  };
  Object.assign(analysis, {
    approval_changed: false,
    available_at: "2026-10-24T01:00:00Z",
    computed_at: "2026-10-24T01:00:00Z",
    research_as_of: "2026-10-24",
    valuation_date: "2026-06-30",
    input_descriptor_sha256: context.input_descriptor_sha256,
    source_bindings: [candidate, source],
    review_binding: { candidate_binding: candidate, model_context: context },
    model_applicability: {
      route: {
        profile_id: context.profile_id,
        selected_model: context.model_id,
        model_type: context.model_id,
      },
    },
    valuation: {
      symbol: decision.symbol,
      confidence: "低",
      status: "conditional_research_only",
      model_type: context.model_id,
      model_version: context.model_version,
      valuation_date: "2026-06-30",
      assumptions: { valuation_timing: timing },
    },
  });
  const inputs = {
    cost_of_equity: "0.07",
    retention: "0.10",
    terminal_growth: "0",
    terminal_roe: "0.20",
    forecast_roes: ["0.20", "0.20", "0.20", "0.20", "0.20"],
  };
  analysis.scenarios.forEach((row: any) => {
    row.inputs = structuredClone(inputs);
    analysis.valuation[`${row.scenario}_value`] = row.per_share_value;
  });
  analysis.source_native_cash_review = {
    schema_version: "source-native-economic-review-materials-v1",
    symbol: decision.symbol,
    scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_G3",
    action: "no_order",
    cash_branch: "TIMING_DELAY",
    authenticated_consumption_supported: false,
    confidence: "低",
    research_admitted: false,
    primary_registered: false,
    approval_changed: false,
    strict_contemporaneous_pit: "NOT_PROVEN",
    candidate_binding: structuredClone(candidate),
    model_context: structuredClone(context),
    source_bindings: [source],
    point_in_time: {
      available_at: analysis.available_at,
      computed_at: analysis.computed_at,
      report_period: "2026-06-30",
      research_as_of: analysis.research_as_of,
      valuation_date: analysis.valuation_date,
    },
    valuation_timing_status: "EXPLICIT_MODEL_TIMING",
    valuation_timing: {
      ...timing,
      evidence_refs: [{ ...source, id: "TEST_ONLY_NATIVE_SOURCE" }],
    },
    historical_cash_bridge: {
      unit: "CNY",
      scope: "standalone parent, NOT consolidated free cash",
      unknowns: ["TEST_ONLY historical bridge is not certified"],
    },
    joint_assumptions: {
      action: "no_order",
      horizon: 5,
      explicit_retention: "0.10",
      incremental_parent_cash_yield: "0.01",
      ke: "0.07",
      TIMING_DELAY: {
        meaning: "TEST_ONLY temporary delay",
        release:
          "all opening incremental delayed asset in year 2; no fresh withholding after year 1",
        withheld_fraction: "0.10",
        withheld_years: [1],
      },
    },
    scenarios: Object.fromEntries(
      analysis.scenarios.map((row: any) => [
        row.scenario,
        {
          inputs: structuredClone(row.inputs),
          per_share_value: row.per_share_value,
          cash_ledger: Array.from({ length: 5 }, (_, index) => ({
            ...Object.fromEntries(nativeCashFields.map((key) => [key, "0"])),
            year: index + 1,
            roe: "0.20",
            profit: "700",
            cash_close: "-12345.67",
          })),
        },
      ]),
    ),
  };
  return decision;
}

it("TEST_ONLY displays a dated low-confidence native path without calculating, fetching or approving it", () => {
  const decision = nativeDecision();
  const before = structuredClone(decision);
  expect(
    sourceNativeCashReviewMatches(
      decision.price_action_plan!.research_analysis!,
      decision.symbol!,
    ),
  ).toBe(true);
  const fetcher = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  for (const text of [
    'aria-label="原生现金路径条件研究"',
    "2026-06-30",
    "低置信度（LOW）",
    "不是今日公允价值",
    "暂时延迟",
    "永久性现金费用",
    "长期无法上划",
    "不证明其他分支成立",
    "本附录不证明历史现金桥完整",
    "当前页面仍展示待审候选",
    "研究级签名CLI已实现",
    "不能视为主估值或价格批准",
    "模型允许支付股息",
    "母公司单体权益",
    "-12,345.67",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("NO_SUPPORTED_BOUND_BRIDGE");
  expect(html).not.toContain("<table");
  expect(html).not.toMatch(/<details[^>]*\bopen/);
  expect(fetcher).not.toHaveBeenCalled();
  fetcher.mockRestore();
  expect(decision).toEqual(before);
});

it.each([
  (a: any) => {
    a.source_native_cash_review.schema_version = "UNKNOWN";
  },
  (a: any) => {
    a.source_native_cash_review.scope = "APPROVED";
  },
  (a: any) => {
    delete a.source_native_cash_review.cash_branch;
  },
  (a: any) => {
    a.source_native_cash_review.cash_branch = "PERMANENT_CASH_COST";
  },
  (a: any) => {
    a.source_native_cash_review.cash_branch = "UNKNOWN";
  },
  (a: any) => {
    a.source_native_cash_review.authenticated_consumption_supported = true;
  },
  (a: any) => {
    delete a.source_native_cash_review.authenticated_consumption_supported;
  },
  (a: any) => {
    a.source_native_cash_review.joint_assumptions.TIMING_DELAY.release = "none";
  },
  (a: any) => {
    a.source_native_cash_review.joint_assumptions.ke = "0.20";
  },
  (a: any) => {
    a.source_native_cash_review.action = "order";
  },
  (a: any) => {
    a.source_native_cash_review.confidence = "HIGH";
  },
  (a: any) => {
    a.valuation.confidence = "HIGH";
  },
  (a: any) => {
    a.source_native_cash_review.primary_registered = true;
  },
  (a: any) => {
    a.source_native_cash_review.research_admitted = true;
  },
  (a: any) => {
    a.source_native_cash_review.approval_changed = true;
  },
  (a: any) => {
    a.source_native_cash_review.symbol = "600519";
  },
  (a: any) => {
    a.source_native_cash_review.candidate_binding.sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.source_native_cash_review.model_context.input_descriptor_sha256 =
      "0".repeat(64);
  },
  (a: any) => {
    delete a.source_native_cash_review.model_context.model_version;
    delete a.review_binding.model_context.model_version;
    delete a.valuation.model_version;
  },
  (a: any) => {
    a.source_native_cash_review.point_in_time.valuation_date = "2026-10-24";
  },
  (a: any) => {
    a.source_native_cash_review.valuation_timing.valuation_at =
      "2026-02-30T00:00:00Z";
  },
  (a: any) => {
    a.source_native_cash_review.source_bindings[0].sha256 = "0".repeat(64);
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.per_share_value = "999999.1234";
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.per_share_value += "1";
  },
  (a: any) => {
    a.scenarios[0].per_share_value = "999999.1234";
  },
  (a: any) => {
    delete a.source_native_cash_review.scenarios.bull;
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.cash_ledger.pop();
  },
  (a: any) => {
    delete a.source_native_cash_review.scenarios.base.cash_ledger[0]
      .dividend_paid;
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.cash_ledger[0].cash_close =
      "NaN";
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.cash_ledger[0].roe = "0.99";
  },
  (a: any) => {
    a.source_native_cash_review.scenarios.base.inputs.terminal_growth = "0.01";
  },
])(
  "TEST_ONLY rejects native cash contract damage %# without presenting its numbers",
  (change) => {
    const decision = nativeDecision();
    const analysis = decision.price_action_plan!.research_analysis!;
    change(analysis);
    expect(sourceNativeCashReviewMatches(analysis, decision.symbol!)).toBe(
      false,
    );
    const html = renderToStaticMarkup(
      <ValueResearchAnalysis decision={decision} />,
    );
    expect(html).toContain("暂不展示本附录现金数值");
    expect(html).toContain("当前页面仍展示待审候选");
    expect(html).not.toContain("模型允许支付股息");
    expect(html).not.toContain("-12,345.67");
  },
);

it("keeps the old view byte-identical when the optional native appendix is absent", () => {
  const decision = analysisDecision();
  const before = renderToStaticMarkup(
    <ValueResearchAnalysis decision={decision} />,
  );
  decision.price_action_plan!.research_analysis!.source_native_cash_review =
    null;
  expect(
    renderToStaticMarkup(<ValueResearchAnalysis decision={decision} />),
  ).toBe(before);
});

it("TEST_ONLY matches equivalent UTC instants using the Shanghai valuation date, not the browser clock", () => {
  const decision = nativeDecision();
  const a: any = decision.price_action_plan!.research_analysis!;
  a.valuation.assumptions.valuation_timing = {
    basis_at: "2026-06-30T00:30:00+08:00",
    valuation_at: "2026-06-30T00:30:00+08:00",
  };
  Object.assign(a.source_native_cash_review.valuation_timing, {
    basis_at: "2026-06-29T16:30:00Z",
    valuation_at: "2026-06-29T16:30:00Z",
  });
  expect(sourceNativeCashReviewMatches(a, decision.symbol!)).toBe(true);
});

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "fits the source-native appendix at 320/390 using static public or TEST_ONLY data, no API",
  async () => {
    const decision = nativeDecision();
    if (process.env.PUBLIC_NATIVE_ANALYSIS) {
      const analysis = JSON.parse(
        readFileSync(process.env.PUBLIC_NATIVE_ANALYSIS, "utf8"),
      );
      decision.symbol = analysis.symbol;
      decision.price_action_plan!.research_analysis = analysis;
    }
    const output = resolve("../.tmp/source-native-cash-layout");
    mkdirSync(output, { recursive: true });
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
      const page = await context.newPage();
      await page.route("**/*", (route: any) => route.abort());
      const css = readFileSync(
        resolve("src/components/value-research-analysis.css"),
        "utf8",
      );
      const dimensions = [];
      for (const width of [320, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.setContent(
          `<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{box-sizing:border-box;width:100%;padding:16px}${css}</style><main>${renderToStaticMarkup(<ValueResearchAnalysis decision={decision} />)}</main></html>`,
        );
        await page
          .locator("details")
          .evaluateAll((items: HTMLDetailsElement[]) =>
            items.forEach((item) => {
              item.open = true;
            }),
          );
        const native = page.locator('[aria-label="原生现金路径条件研究"]');
        await native.waitFor();
        expect(await native.locator("table").count()).toBe(0);
        expect(await native.locator("details").count()).toBe(19);
        const size = await page.evaluate(() => ({
          width: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          overflowing: [...document.querySelectorAll("main *")]
            .filter((item) => {
              const r = item.getBoundingClientRect();
              return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1);
            })
            .map((item) => item.tagName),
        }));
        expect(size.scrollWidth).toBeLessThanOrEqual(width);
        expect(size.overflowing).toEqual([]);
        dimensions.push(size);
        await native.evaluate((element: HTMLElement) =>
          element.scrollIntoView({ block: "start" }),
        );
        await page.screenshot({ path: resolve(output, `${width}.png`) });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(dimensions, null, 2),
      );
    } finally {
      await context.close();
    }
  },
  90000,
);

it.skipIf(!process.env.PUBLIC_NATIVE_ANALYSIS)(
  "renders the actual explicitly branched public native receipt, no source mutation or live API",
  () => {
    const bytes = readFileSync(process.env.PUBLIC_NATIVE_ANALYSIS!);
    expect(process.env.PUBLIC_NATIVE_ANALYSIS_SHA256).toMatch(/^[a-f0-9]{64}$/);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      process.env.PUBLIC_NATIVE_ANALYSIS_SHA256,
    );
    const analysis = JSON.parse(bytes.toString("utf8"));
    expect(sourceNativeCashReviewMatches(analysis, analysis.symbol)).toBe(true);
    const decision = analysisDecision();
    decision.symbol = analysis.symbol;
    decision.price_action_plan!.research_analysis = analysis;
    const html = renderToStaticMarkup(
      <ValueResearchAnalysis decision={decision} />,
    );
    expect(html).toContain('aria-label="原生现金路径条件研究"');
    expect(html).toContain("2026-06-30");
    expect(html).toContain("低置信度（LOW）");
    expect(html).not.toContain("NO_SUPPORTED_BOUND_BRIDGE");
  },
);

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
      model_version: "TEST_ONLY_RI_V1",
      profile_id: "TEST_ONLY_PROFILE",
      research_case_sha256: "1".repeat(64),
      facts_sha256: "2".repeat(64),
      assumptions_sha256: "3".repeat(64),
      research_as_of: analysis.research_as_of,
    },
  };
  analysis.source_bindings.push(candidate, proposal, policy);
  analysis.model_applicability!.route = {
    profile_id: "TEST_ONLY_PROFILE",
    selected_model: "TEST_ONLY_RI",
    model_type: "TEST_ONLY_RI",
  };
  analysis.valuation = {
    model_type: "TEST_ONLY_RI",
    model_version: "TEST_ONLY_RI_V1",
    valuation_date: "2026-10-11",
    bear_value: "100.123456789",
    base_value: "100.123456789",
    bull_value: "100.123456789",
    assumptions: {
      valuation_timing: {
        basis_at: "2026-06-30T23:59:59+08:00",
        valuation_at: "2026-10-11T08:00:00Z",
      },
    },
  };
  analysis.scenarios.forEach((row) => {
    row.per_share_value = "100.123456789";
  });
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
  delete decision.price_action_plan!.research_analysis!.valuation!.assumptions
    .valuation_timing;
  const html = render(decision);
  expect(html).toContain("未建立定价时点");
  expect(html).toContain("不能当作当前价值");
  expect(html).not.toContain("资料基准：2026-10-22");
});

it.each([
  (a: any) => {
    a.joint_capital_review.scenarios[1].valuation_per_share = "999999";
  },
  (a: any) => {
    a.joint_capital_review.scenarios[1].valuation_per_share =
      "100.123456789000000001";
  },
  (a: any) => {
    a.scenarios[1].per_share_value = "999999";
  },
  (a: any) => {
    a.scenarios[1].per_share_value = 100.123456789;
  },
  (a: any) => {
    a.valuation.base_value = "999999";
  },
  (a: any) => {
    a.scenarios.push(a.scenarios[0]);
  },
  (a: any) => {
    a.scenarios = [];
  },
  (a: any) => {
    a.joint_capital_review.basis_at = "2027-06-30T23:59:59+08:00";
  },
  (a: any) => {
    a.joint_capital_review.valuation_at = "2020-01-01T00:00:00Z";
  },
  (a: any) => {
    a.joint_capital_review.valuation_at = "2026-02-30T08:00:00Z";
  },
  (a: any) => {
    a.joint_capital_review.valuation_at = "2026-10-11T24:00:00Z";
  },
  (a: any) => {
    a.joint_capital_review.valuation_at = "2026-10-11T08:00:00.000001Z";
  },
  (a: any) => {
    a.valuation.assumptions.valuation_timing.valuation_at =
      "2026-02-30T08:00:00Z";
    a.joint_capital_review.valuation_at = "2026-02-30T08:00:00Z";
  },
  (a: any) => {
    delete a.valuation.assumptions.valuation_timing;
  },
  (a: any) => {
    a.valuation_date = "2020-01-01";
  },
  (a: any) => {
    a.valuation.valuation_date = "2020-01-01";
  },
  (a: any) => {
    a.joint_capital_review.date_scope = "UNDATED_CONDITIONAL_MODEL";
    a.joint_capital_review.basis_at = null;
    a.joint_capital_review.valuation_at = null;
  },
  (a: any) => {
    a.review_binding.model_context = {
      input_descriptor_sha256: a.input_descriptor_sha256,
    };
  },
  (a: any) => {
    a.review_binding.model_context.model_id = "DIFFERENT_MODEL";
  },
  (a: any) => {
    a.review_binding.model_context.model_version = "DIFFERENT_VERSION";
  },
  (a: any) => {
    a.review_binding.model_context.profile_id = "DIFFERENT_PROFILE";
  },
  (a: any) => {
    delete a.review_binding.model_context.model_version;
  },
  (a: any) => {
    delete a.review_binding.model_context.facts_sha256;
  },
  (a: any) => {
    a.review_binding.model_context.assumptions_sha256 = "invalid";
  },
  (a: any) => {
    a.review_binding.model_context.research_case_sha256 = null;
  },
  (a: any) => {
    a.review_binding.model_context.research_as_of = "2026-02-30";
  },
  (a: any) => {
    a.review_binding.model_context.research_as_of = "2020-01-01";
  },
  (a: any) => {
    delete a.valuation;
  },
  (a: any) => {
    delete a.valuation.model_version;
  },
  (a: any) => {
    delete a.model_applicability.route;
  },
  (a: any) => {
    a.model_applicability.route.selected_model = "OTHER";
  },
])(
  "rejects cross-version public values, dates and model identity without an assessment %#",
  (change) => {
    const decision = jointDecision(),
      analysis = decision.price_action_plan!.research_analysis!;
    expect(analysis.economic_assessment).toBeUndefined();
    change(analysis);
    expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
      false,
    );
    expect(render(decision)).toContain("暂不可作为核验结果展示");
  },
);

it("compares exact decimal equivalents and equivalent instants without float rounding", () => {
  const decision = jointDecision(),
    analysis = decision.price_action_plan!.research_analysis!;
  analysis.joint_capital_review!.scenarios[1].valuation_per_share =
    "100123456789e-9";
  analysis.joint_capital_review!.valuation_at =
    "2026-10-11T16:00:00.000000+08:00";
  expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(true);
  analysis.joint_capital_review!.scenarios[1].valuation_per_share =
    "100.123456789000000001";
  expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
    false,
  );
});

it.each([
  [
    "2026-10-24T04:52:55.167144+14:00",
    "2026-10-23T14:52:55.167144Z",
    "2026-10-23",
  ],
  [
    "2026-10-23T16:00:00.000001Z",
    "2026-10-24T00:00:00.000001+08:00",
    "2026-10-24",
  ],
  [
    "2026-10-23T15:59:59.999999Z",
    "2026-10-24T05:59:59.999999+14:00",
    "2026-10-23",
  ],
])(
  "matches the Shanghai financial date across offset day boundaries: %s",
  (modelAt, jointAt, day) => {
    const decision = jointDecision(),
      analysis = decision.price_action_plan!.research_analysis!;
    analysis.valuation!.assumptions.valuation_timing!.valuation_at = modelAt;
    analysis.joint_capital_review!.valuation_at = jointAt;
    analysis.valuation_date = day;
    analysis.valuation!.valuation_date = day;
    expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
      true,
    );
    const wrongDay = day === "2026-10-23" ? "2026-10-24" : "2026-10-23";
    analysis.valuation_date = wrongDay;
    analysis.valuation!.valuation_date = wrongDay;
    expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
      false,
    );
  },
);

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

it("renders current economic mechanics without inventing a fade or approval", () => {
  const decision = analysisDecision();
  decision.price_action_plan!.research_analysis!.economic_assessment = {
    schema_version: "value-economic-assessment-v1",
    symbol: decision.symbol!,
    action: "no_order",
    primary_valuation_usable: false,
    economic_assumptions_reviewed: false,
    model_applicability: {
      assessment: "CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION",
      reasons: ["三情景共用权益成本", "终端仍假设超额回报持续"],
    },
    blockers: [],
  };
  const html = render(decision);
  expect(html).toContain("三情景共用权益成本");
  expect(html).toContain("终端仍假设超额回报持续");
  expect(html).toContain("不等于获批主估值");
  expect(html).not.toContain("仍需验证竞争优势与衰减");
});

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
    for (const change of [
      (a: any) => {
        a.joint_capital_review.scenarios[1].valuation_per_share = "999999";
      },
      (a: any) => {
        a.joint_capital_review.basis_at = "2027-06-30T23:59:59+08:00";
      },
      (a: any) => {
        a.joint_capital_review.valuation_at = "2020-01-01T00:00:00Z";
      },
      (a: any) => {
        a.joint_capital_review.valuation_at = "2026-02-30T08:00:00Z";
      },
      (a: any) => {
        a.review_binding.model_context.model_id = "DIFFERENT_MODEL";
      },
      (a: any) => {
        a.review_binding.model_context.model_version = "DIFFERENT_VERSION";
      },
      (a: any) => {
        a.review_binding.model_context = {
          input_descriptor_sha256: a.input_descriptor_sha256,
        };
      },
    ]) {
      const damaged = structuredClone(analysis);
      change(damaged);
      expect(publicJointCapitalReviewMatches(damaged, damaged.symbol)).toBe(
        false,
      );
    }
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
