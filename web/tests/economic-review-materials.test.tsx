import React from "react";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { EconomicReviewMaterials } from "../src/components/EconomicReviewMaterials";
import {
  economicMaterialsMatch,
  jointCapitalReviewMatches,
  jointRowFields,
  jointTerminalFields,
} from "../src/services/valuePolicy";
import type { PolicyHandoff } from "../src/services/valuePolicy";
const { renderToStaticMarkup } = require("react-dom/server");

type Handoff = Extract<
  PolicyHandoff,
  { status: "EXTERNAL_SIGNATURE_REQUIRED" }
>;

function fixture(): Handoff {
  const candidate = {
    path: "TEST_ONLY/candidate.json",
    sha256: "a".repeat(64),
  };
  const source = { path: "TEST_ONLY/filing.json", sha256: "b".repeat(64) };
  const context = {
    input_descriptor_sha256: "c".repeat(64),
    model_id: "TEST_ONLY_RI",
  };
  const valuation = "d".repeat(64);
  const reviewBinding = {
    candidate_binding: candidate,
    model_context: context,
    valuation_artifact_sha256: valuation,
  };
  const groups = [
    "EARNINGS",
    "DURATION",
    "DISTRIBUTION",
    "COST_TERMINAL",
    "EVENT_MODEL",
  ].map((id) => ({
    id,
    title: `TEST_ONLY ${id}`,
    field_paths: [`/TEST_ONLY/${id}`],
    verified_observations: [`TEST_ONLY ${id} 来源算术观察`],
    conditional_assumptions: [`TEST_ONLY ${id} 条件假设`],
    counter_evidence: [`TEST_ONLY ${id} 反证`],
    judgment_questions: [`TEST_ONLY ${id} 未决问题`],
    evidence_refs: [source],
  }));
  return {
    action: "no_order",
    symbol: "600519",
    status: "EXTERNAL_SIGNATURE_REQUIRED",
    ...reviewBinding,
    review_questions: groups.map(({ id, field_paths }) => ({
      id,
      field_paths,
    })),
    unsigned_response: {
      namespace: "TEST_ONLY",
      untouched: "TEST_ONLY_ORIGINAL_UNSIGNED",
    },
    authorization: {
      pinned_root_count: 0,
      status: "AUTHORIZED_IDENTITY_REQUIRED",
    },
    steps: [],
    verification: { approval_changed: false, research_admitted: false },
    commands: {
      draft_preview: "TEST_ONLY preview",
      consume_signed_response: "TEST_ONLY consume",
    },
    economic_review_materials: {
      schema_version: "value-economic-review-materials-v1",
      symbol: "600519",
      action: "no_order",
      status: "PENDING_ECONOMIC_JUDGMENT",
      ...reviewBinding,
      input_descriptor_sha256: context.input_descriptor_sha256,
      assessment_sha256: "e".repeat(64),
      materials_sha256: "f".repeat(64),
      primary_valuation_usable: false,
      approval_changed: false,
      groups,
      source_bindings: [source],
      economic_assessment: {
        schema_version: "value-economic-assessment-v1",
        symbol: "600519",
        action: "no_order",
        input_descriptor_sha256: context.input_descriptor_sha256,
        assessment_sha256: "e".repeat(64),
        review_binding: {
          candidate_binding: candidate,
          model_context: context,
          package_binding: source,
          workbench_binding: source,
          review_packet_binding: source,
        },
        primary_valuation_usable: false,
        approval_changed: false,
        economic_assumptions_reviewed: false,
        action_admitted: false,
        strategy_admitted: false,
        model_applicability: {
          assessment: "CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION",
        },
        blockers: ["TEST_ONLY not admitted"],
        accounting_bridge_review: {
          schema_version: "economic-review-bundle-v1",
          symbol: "600519",
          action: "no_order",
          status: "HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL",
          input_descriptor_sha256: context.input_descriptor_sha256,
          bundle_sha256: "1".repeat(64),
          primary_valuation_usable: false,
          economic_approval_granted: false,
          source_bindings: [source],
          unknown_fields: ["TEST_ONLY liquidity"],
          bridge_results: [
            {
              kind: "parent_cash",
              period: "FY2025",
              entity_scope: "issuer_parent_standalone",
              unit: "CNY",
              source_binding: source,
              source_url: "https://example.org/TEST_ONLY.pdf",
              physical_pages: [25],
              terms: { cfo_cny: "20" },
              reported_adjustment: null,
              derived_adjustment_cny: "-10",
              computed_closing_cny: "110",
              reported_closing_cny: "110",
              difference_cny: "0",
              assurance:
                "BOUND_RESEARCH_ARITHMETIC_NOT_NEW_PDF_ROW_CERTIFICATION",
            },
          ],
        },
      },
    },
  };
}

const render = (handoff: PolicyHandoff = fixture(), symbol = "600519") =>
  renderToStaticMarkup(
    <EconomicReviewMaterials handoff={handoff} symbol={symbol} />,
  );

function jointFixture(): Handoff {
  const handoff = fixture();
  const material = handoff.economic_review_materials!;
  const proposal = { path: "TEST_ONLY/proposal.json", sha256: "2".repeat(64) };
  const policy = { path: "TEST_ONLY/policy.json", sha256: "3".repeat(64) };
  material.source_bindings.push(proposal, policy);
  material.joint_capital_review = {
    schema_version: "joint-capital-review-v1",
    symbol: "600519",
    action: "no_order",
    status: "CONDITIONAL_PATH_NOT_APPROVED",
    scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS",
    candidate_binding: structuredClone(material.candidate_binding),
    proposal_binding: structuredClone(proposal),
    policy_binding: structuredClone(policy),
    input_descriptor_sha256: material.input_descriptor_sha256,
    selected_choice: "TEST_ONLY_CONDITIONAL",
    date_scope: "DATED_CONDITIONAL_MODEL",
    basis_at: "2026-06-30T23:59:59+08:00",
    valuation_at: "2026-10-11T08:00:00Z",
    scenarios: (["bear", "base", "bull"] as const).map((scenario) => ({
      scenario,
      valuation_per_share: "123.456789",
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
        scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS",
        limitations: ["TEST_ONLY cash conversion remains unapproved"],
        cash_funding_status: "PASS",
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
  return handoff;
}

describe("joint capital read-only presentation", () => {
  it("shows three scenarios and all five future rows without changing the handoff", () => {
    const handoff = jointFixture(),
      before = structuredClone(handoff),
      html = render(handoff);
    expect(jointCapitalReviewMatches(handoff, "600519")).toBe(true);
    for (const text of [
      "谨慎情景",
      "中性条件情景",
      "乐观情景",
      "第 5 年",
      "未来假设",
      "新增经营资本",
      "新增流动资本",
      "期末权益",
      "期末现金代理",
      "终端 ROE 假设（非已验证 ROIC）",
      "proxy",
      "不代表可分红能力",
      "TEST_ONLY cash conversion",
      "123456789.123456789",
    ])
      expect(html).toContain(text);
    expect(html).not.toContain("<button");
    expect(handoff).toEqual(before);
  });
  it("preserves a negative cash shortfall and FAIL, not a zero or a pass", () => {
    const handoff = jointFixture(),
      ledger =
        handoff.economic_review_materials!.joint_capital_review!.scenarios[0]
          .ledger;
    ledger.cash_funding_status = "FAIL";
    ledger.rows[0].cash_funding_status = "FAIL";
    ledger.rows[0].cash_close = "-123456789.123456789";
    const html = render(handoff);
    expect(html).toContain("FAIL：假设路径存在现金资金缺口");
    expect(html).toContain("-1.23 亿元");
    expect(html).toContain("-123456789.123456789");
  });
  it("leaves undated models explicitly undated, never fills the calculation time", () => {
    const handoff = jointFixture(),
      review = handoff.economic_review_materials!.joint_capital_review!;
    review.date_scope = "UNDATED_CONDITIONAL_MODEL";
    review.basis_at = null;
    review.valuation_at = null;
    expect(jointCapitalReviewMatches(handoff, "600519")).toBe(true);
    expect(render(handoff)).toContain("未建立定价时点");
    expect(render(handoff)).toContain("不能当作当前价值");
  });
  it.each([
    (r: any) => {
      r.symbol = "600887";
    },
    (r: any) => {
      r.schema_version = "v2";
    },
    (r: any) => {
      r.action = "order";
    },
    (r: any) => {
      r.status = "APPROVED";
    },
    (r: any) => {
      r.scope = "VERIFIED_FACTS";
    },
    (r: any) => {
      r.candidate_binding = {
        path: "TEST_ONLY/other.json",
        sha256: "a".repeat(64),
      };
    },
    (r: any) => {
      r.input_descriptor_sha256 = "0".repeat(64);
    },
    (r: any) => {
      r.proposal_binding.sha256 = "0".repeat(64);
    },
    (r: any) => {
      r.policy_binding.path = "../policy.json";
    },
    (r: any) => {
      delete r.selected_choice;
    },
    (r: any) => {
      r.date_scope = "UNKNOWN";
    },
    (r: any) => {
      r.basis_at = null;
    },
    (r: any) => {
      r.date_scope = "UNDATED_CONDITIONAL_MODEL";
    },
    (r: any) => {
      r.scenarios.pop();
    },
    (r: any) => {
      r.scenarios[1].scenario = "bear";
    },
    (r: any) => {
      r.scenarios[0].valuation_per_share = "Infinity";
    },
    (r: any) => {
      r.scenarios[0].drivers.retention = true;
    },
    (r: any) => {
      r.scenarios[0].drivers.years[0].cost_ratio = "NaN";
    },
    (r: any) => {
      r.scenarios[0].ledger.rows[0].cash_close = Infinity;
    },
    (r: any) => {
      delete r.scenarios[0].ledger.rows[0].profit;
    },
    (r: any) => {
      r.scenarios[0].ledger.rows[4].year = 1;
    },
    (r: any) => {
      r.scenarios[0].ledger.terminal_roe = "1e9999";
    },
    (r: any) => {
      r.scenarios[0].ledger.cash_funding_status = "APPROVED";
    },
  ])(
    "rejects corrupt or mismatched ledger %# while keeping older economic materials readable",
    (change) => {
      const handoff = jointFixture();
      change(handoff.economic_review_materials!.joint_capital_review);
      expect(jointCapitalReviewMatches(handoff, "600519")).toBe(false);
      const html = render(handoff);
      expect(html).toContain("暂不可展示为核验账本");
      expect(html).not.toContain("123456789.123456789");
      expect(html).toContain("经济判断审核材料");
    },
  );
  it.skipIf(!process.env.JOINT_CAPITAL_HANDOFF)(
    "accepts actual backend-revalidated CC1 projection",
    () => {
      const handoff = JSON.parse(
        readFileSync(process.env.JOINT_CAPITAL_HANDOFF!, "utf8"),
      ) as Handoff;
      const before = structuredClone(handoff);
      expect(jointCapitalReviewMatches(handoff, handoff.symbol)).toBe(true);
      expect(render(handoff, handoff.symbol)).toContain("三情景五年条件演算");
      expect(handoff).toEqual(before);
    },
  );
  it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
    "fits fully expanded ledgers inside 320/390 pixels",
    async () => {
      const output = resolve("../.tmp/joint-capital-layout");
      mkdirSync(output, { recursive: true });
      const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
      const context = await chromium.launchPersistentContext(
        resolve(output, "browser-profile"),
        {
          executablePath: process.env.READINESS_BROWSER_PATH,
          headless: true,
          downloadsPath: output,
        },
      );
      const measurements: unknown[] = [];
      try {
        const page = await context.newPage();
        await page.route("**/*", (route: any) => route.abort());
        const handoff = process.env.JOINT_CAPITAL_HANDOFF
          ? (JSON.parse(
              readFileSync(process.env.JOINT_CAPITAL_HANDOFF, "utf8"),
            ) as Handoff)
          : jointFixture();
        for (const width of [320, 390]) {
          await page.setViewportSize({ width, height: 900 });
          await page.setContent(
            `<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{box-sizing:border-box;width:100%;padding:16px}</style><main>${render(handoff, handoff.symbol)}</main></html>`,
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
                const bounds = element.getBoundingClientRect();
                return (
                  bounds.width > 0 &&
                  (bounds.right > innerWidth + 1 || bounds.left < -1)
                );
              })
              .map((element) => element.tagName),
          }));
          expect(size.scrollWidth).toBeLessThanOrEqual(width);
          expect(size.overflowing).toEqual([]);
          measurements.push(size);
          await page.screenshot({
            path: resolve(output, `${width}.png`),
            fullPage: true,
          });
          await page.screenshot({
            path: resolve(output, `${width}-viewport.png`),
            fullPage: false,
          });
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
});

describe("read-only economic review materials", () => {
  it("renders only actual groups, with facts, assumptions, counterevidence, questions and source identities", () => {
    const handoff = fixture();
    const original = structuredClone(handoff);
    const html = render(handoff);
    for (const title of [
      "可持续盈利",
      "竞争优势与衰减",
      "现金分配能力",
      "权益成本与终值",
      "事件与模型有效性",
      "来源与算术核验观察（非经济批准）",
      "当前条件假设（未获批准）",
      "反证与冲突",
      "需要审核人回答的问题",
      "TEST_ONLY EARNINGS 来源算术观察",
      "TEST_ONLY DISTRIBUTION 条件假设",
      "TEST_ONLY DURATION 反证",
      "TEST_ONLY EVENT_MODEL 未决问题",
      "TEST_ONLY/filing.json",
      "历史现金与权益核验",
      "2025 年度",
      "110",
      "读取、下载不改变批准状态",
      "当前主估值尚不可用",
    ])
      expect(html).toContain(title);
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<input");
    expect(html).not.toContain("TEST_ONLY_ORIGINAL_UNSIGNED");
    expect(handoff).toEqual(original);
  });

  it("never fabricates missing groups or suppresses empty evidence", () => {
    const handoff = fixture();
    const material = handoff.economic_review_materials!;
    material.groups = material.groups.slice(0, 1);
    material.groups[0].counter_evidence = [];
    material.groups[0].evidence_refs = [];
    handoff.review_questions = material.groups.map(({ id, field_paths }) => ({
      id,
      field_paths,
    }));
    const html = render(handoff);
    expect(html).toContain("可持续盈利");
    expect(html).not.toContain("<summary>竞争优势与衰减</summary>");
    expect(html).toContain("本版未提供，仍待补证与判断");
    expect(html).toContain("本组尚未提供独立出处");
  });

  it("warns stress-only cannot serve as a neutral primary valuation", () => {
    const handoff = fixture();
    handoff.economic_review_materials!.status = "STRESS_ONLY_NOT_PRIMARY";
    handoff.economic_review_materials!.economic_assessment.model_applicability =
      { assessment: "STRESS_ONLY" };
    expect(render(handoff)).toContain("当前为压力情景，不能充当中性主估值");
  });

  it("accepts JSON context key ordering differences", () => {
    const handoff = fixture();
    handoff.economic_review_materials!.model_context = {
      model_id: "TEST_ONLY_RI",
      input_descriptor_sha256: "c".repeat(64),
    };
    expect(economicMaterialsMatch(handoff, "600519")).toBe(true);
  });

  it.each([
    (h: Handoff) => {
      h.symbol = "600887";
    },
    (h: Handoff) => {
      h.action = "order" as "no_order";
    },
    (h: Handoff) => {
      h.verification.approval_changed = true as false;
    },
    (h: Handoff) => {
      h.economic_review_materials!.symbol = "600887";
    },
    (h: Handoff) => {
      h.economic_review_materials!.schema_version = "v2" as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.action = "order" as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.status = "PASSED" as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.candidate_binding = {
        path: "TEST_ONLY/other.json",
        sha256: "a".repeat(64),
      };
    },
    (h: Handoff) => {
      h.economic_review_materials!.candidate_binding = {
        path: "../escape.json",
        sha256: "a".repeat(64),
      };
    },
    (h: Handoff) => {
      h.economic_review_materials!.model_context = {
        input_descriptor_sha256: "c".repeat(64),
        model_id: "WRONG",
      };
    },
    (h: Handoff) => {
      h.economic_review_materials!.input_descriptor_sha256 = "0".repeat(64);
    },
    (h: Handoff) => {
      h.economic_review_materials!.valuation_artifact_sha256 = "0".repeat(64);
    },
    (h: Handoff) => {
      h.economic_review_materials!.assessment_sha256 = "0".repeat(64);
    },
    (h: Handoff) => {
      h.economic_review_materials!.materials_sha256 = "missing";
    },
    (h: Handoff) => {
      h.economic_review_materials!.primary_valuation_usable = true as false;
    },
    (h: Handoff) => {
      h.economic_review_materials!.approval_changed = true as false;
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment = null as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment.action_admitted =
        true as false;
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment.symbol = "600887";
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment.review_binding =
        {} as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment.input_descriptor_sha256 =
        "0".repeat(64);
    },
    (h: Handoff) => {
      h.economic_review_materials!.economic_assessment.model_applicability = {
        assessment: "STRESS_ONLY",
      };
    },
    (h: Handoff) => {
      h.economic_review_materials!.groups[0].field_paths = ["WRONG"];
    },
    (h: Handoff) => {
      h.economic_review_materials!.groups.push(
        h.economic_review_materials!.groups[0],
      );
    },
    (h: Handoff) => {
      h.economic_review_materials!.groups[0].evidence_refs = [
        { path: "TEST_ONLY/forged.json", sha256: "0".repeat(64) },
      ];
    },
    (h: Handoff) => {
      h.economic_review_materials!.groups[0].verified_observations = [
        null,
      ] as any;
    },
    (h: Handoff) => {
      h.economic_review_materials!.source_bindings = [];
    },
  ])("refuses mismatched or authority-changing materials %#", (change) => {
    const handoff = fixture();
    change(handoff);
    expect(economicMaterialsMatch(handoff, "600519")).toBe(false);
    const html = render(handoff);
    expect(html).toContain("暂不展示");
    expect(html).not.toContain("TEST_ONLY EARNINGS 来源算术观察");
    expect(html).not.toContain("110");
  });

  it("keeps older handoffs without optional materials readable", () => {
    const handoff = fixture();
    delete handoff.economic_review_materials;
    expect(render(handoff)).toBe("");
  });

  it.skipIf(!process.env.VALUE_ECONOMIC_RECEIPT)(
    "renders actual source-verified backend handoffs without invented inner valuation hash",
    () => {
      const receipt = JSON.parse(
        readFileSync(process.env.VALUE_ECONOMIC_RECEIPT!, "utf8"),
      );
      expect(receipt.action).toBe("no_order");
      expect(
        receipt.cases.map((item: { symbol: string }) => item.symbol),
      ).toEqual(["600519", "600887"]);
      for (const item of receipt.cases) {
        const handoff = item.handoff as Handoff;
        const original = JSON.stringify(handoff);
        expect(
          handoff.economic_review_materials!.economic_assessment.review_binding,
        ).not.toHaveProperty("valuation_artifact_sha256");
        expect(economicMaterialsMatch(handoff, item.symbol)).toBe(true);
        const html = render(handoff, item.symbol);
        expect(html).toContain("经济判断审核材料");
        expect(html).not.toContain("暂不展示；请重新读取");
        expect(html).toContain(
          handoff.economic_review_materials!.materials_sha256,
        );
        if (
          handoff.economic_review_materials!.status ===
          "STRESS_ONLY_NOT_PRIMARY"
        )
          expect(html).toContain("不能充当中性主估值");
        expect(JSON.stringify(handoff)).toBe(original);
        const wrong = structuredClone(handoff);
        wrong.valuation_artifact_sha256 = "0".repeat(64);
        expect(economicMaterialsMatch(wrong, item.symbol)).toBe(false);
      }
    },
  );

  it("escapes untrusted text and wraps long evidence tokens without fixed widths", () => {
    const handoff = fixture();
    handoff.economic_review_materials!.groups[0].judgment_questions = [
      "<script>TEST_ONLY</script>",
      "X".repeat(500),
    ];
    const html = render(handoff);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("overflow-wrap:anywhere");
    expect(html).toContain("min-width:0");
  });
});

import {
  JOINT_CASH_SCHEMA,
  JOINT_CASH_V3_SCHEMA,
  jointCashPolicyFields,
  jointCashRowFields,
  jointCashOperatingFields,
  jointCashTerminalFields,
  publicJointCapitalReviewMatches,
} from "../src/services/valuePolicy";
import { PublicJointCapitalReview } from "../src/components/JointCapitalReview";
import { analysisFixture } from "./fixtures/value-research-analysis";

function jointCashFixture(): Handoff {
  const handoff = jointFixture();
  const review = handoff.economic_review_materials!.joint_capital_review!;
  review.schema_version = "joint-capital-cash-review-v2";
  review.input_mode = JOINT_CASH_SCHEMA;
  const policy = {
    target_payout_ratio: ".9",
    accessible_profit_ratio: ".8",
    reserve_ratio: ".1",
    net_maintenance_cash_cny: "12.34567890123456789",
    operating_wc_cash_cny: "-2",
    commitment_cash_cny: "3",
  };
  const row = (year: number) => ({
    ...Object.fromEntries(jointCashRowFields.map((key) => [key, "100"])),
    year,
    forecast_roe: ".1",
    retention: year % 2 ? ".2" : ".4",
    funding_shortfall: "0",
    funding_status: "FUNDED",
    clean_surplus_residual: "0",
    capital_identity_residual: "0",
    net_maintenance_cash_cny: policy.net_maintenance_cash_cny,
    operating_wc_cash_cny: policy.operating_wc_cash_cny,
    commitment_cash_cny: policy.commitment_cash_cny,
    cash_policy: { ...policy },
  });
  review.scenarios.forEach((scenario) => {
    scenario.drivers = {
      operating_allocation: ".5",
      new_operating_return: ".1",
      new_liquidity_return: ".01",
      years: Array.from({ length: 10 }, (_, i) => ({
        year: i + 1,
        revenue_growth: ".01",
        cost_ratio: ".2",
        ...policy,
      })),
    };
    scenario.ledger = {
      version: "joint-capital-cash-path-v2",
      action: "no_order",
      status: "CONDITIONAL_RESEARCH_NOT_APPROVED",
      scope: "ordinary_owner_equivalent_cash_mapping",
      currency: "CNY",
      limitations: ["TEST_ONLY 未上划不自动释放；维护需求仍可能低估"],
      funding_status: "FUNDED",
      forecast_roe: Array(10).fill(".1"),
      forecast_retentions: Array.from({ length: 10 }, (_, i) =>
        i % 2 ? ".4" : ".2",
      ),
      rows: Array.from({ length: 10 }, (_, i) => ({
        ...row(i + 1),
        ...Object.fromEntries(
          jointCashOperatingFields.map((key) => [key, "123456789.123456789"]),
        ),
        expenses: { surcharges: "1", selling: "2", admin: "3", research: "4" },
      })),
      terminal: row(11),
      terminal_policy: {
        ...policy,
        profit_scale: "1",
        rationale: "TEST_ONLY 持续终端必要支出",
      },
      terminal_roe: ".1",
      terminal_retention: ".2",
      terminal_growth: ".02",
      terminal_profit: "100",
      terminal_distribution: "100",
      terminal_book: "100",
    };
  });
  return handoff;
}

function jointCashV3Fixture(): Handoff {
  const handoff = jointCashFixture();
  const review = handoff.economic_review_materials!
    .joint_capital_review! as any;
  review.schema_version = "joint-capital-cash-review-v3";
  review.input_mode = JOINT_CASH_V3_SCHEMA;
  review.explicit_years = 10;
  review.distribution_scope =
    "ANNUAL_CASH_AND_CAPACITY_CONSTRAINED_NOT_APPROVED";
  review.terminal_scope =
    "RECURSIVE_CAPITAL_USE_AND_OWNER_DISTRIBUTION_NOT_GROWTH_PERPETUITY";
  review.scenarios.forEach((scenario: any) => {
    const policy = scenario.ledger.terminal_policy;
    Object.assign(policy, {
      terminal_mechanism: "recursive_capital_use_and_owner_distribution_v1",
      terminal_start_year: 11,
      first_distribution_timing: "end_of_terminal_year_1",
      legacy_profit_dynamics: "constant_after_profit_scale_transition",
      commitment_occurrences: null,
      restricted_cash_release_cny: "0",
      restricted_cash_release_year: null,
      convergence_tolerance_cny: "0.000001",
      max_tail_years: 2000,
    });
    scenario.ledger.version = "joint-capital-cash-path-v3";
    scenario.ledger.terminal_growth_status =
      "NON_AUTHORITATIVE_ACCOUNTING_DIAGNOSTIC";
    scenario.ledger.terminal_economic_contract = {
      opening_book: "100",
      opening_cash: "20",
      opening_unremitted: "5",
      opening_distribution_capacity: "100",
      opening_operating_capital: "80",
      opening_productive_capital: "10",
      opening_cash_reference: "20",
      cash_floor: "10",
      legacy_profit: "20",
      operating_allocation: ".5",
      productive_marginal_return: ".1",
      liquidity_return: ".01",
      policy: jointCashPolicyFields.map((key) => [key, policy[key]]),
      commitment_occurrences: null,
      restricted_cash_release_cny: "0",
      restricted_cash_release_year: null,
      convergence_tolerance_cny: "0.000001",
      max_tail_years: 2000,
      rationale: policy.rationale,
    };
    scenario.actual_calculation_inputs = {
      terminal_contract_version: "terminal-economic-contract-v1",
      terminal_mechanism: "recursive_capital_use_and_owner_distribution",
    };
    scenario.terminal_economics = {
      mechanism: "recursive_capital_use_and_owner_distribution",
      terminal_contract_version: "terminal-economic-contract-v1",
      explicit_distribution_pv_cny: "5000000000",
      terminal_value_at_year_10_cny: "20000000000",
      terminal_distribution_value_cny: "19999999999.99",
      terminal_convergence_residual_cny: "0.01",
      terminal_years_evaluated: 321,
      ri_ddm_difference_cny: "0.01",
      limitations: [
        "Terminal value is conditional on the declared capital-use mechanism.",
        "Restricted funds release only when explicitly declared and only once.",
      ],
    };
  });
  return handoff;
}

it("strictly renders v3 terminal mechanism and value contributions", () => {
  const handoff = jointCashV3Fixture();
  expect(jointCapitalReviewMatches(handoff, "600519")).toBe(true);
  const html = render(handoff);
  for (const text of [
    "账面留存不会自动转化为终端增长",
    "显式十年股东分配现值",
    "第10年末尾期经济价值",
    "尾期股东分配价值",
    "RI／股东分配交叉检查差额",
    "terminal-economic-contract-v1",
    "主要限制",
  ])
    expect(html).toContain(text);
});

it.each([
  (review: any) => {
    review.scenarios[0].terminal_economics.mechanism = "unknown-v3";
  },
  (review: any) => {
    delete review.scenarios[0].terminal_economics.terminal_value_at_year_10_cny;
  },
  (review: any) => {
    review.scenarios[0].ledger.terminal_policy.terminal_mechanism = "unknown";
  },
  (review: any) => {
    review.terminal_scope = "OLD_GROWTH_PERPETUITY";
  },
  (review: any) => {
    const policy = review.scenarios[0].ledger.terminal_economic_contract.policy;
    policy[policy.length - 1] = [...policy[0]];
  },
])("fails closed for unknown or incomplete v3 terminal contracts", (damage) => {
  const handoff = jointCashV3Fixture();
  damage(handoff.economic_review_materials!.joint_capital_review);
  expect(jointCapitalReviewMatches(handoff, "600519")).toBe(false);
  expect(render(handoff)).toContain("暂不可展示为核验账本");
});

function publicCashFixture(handoff = jointCashFixture()) {
  const analysis = analysisFixture();
  const material = handoff.economic_review_materials!;
  const review = structuredClone(material.joint_capital_review!);
  review.symbol = analysis.symbol;
  analysis.approval_changed = false;
  analysis.input_descriptor_sha256 = review.input_descriptor_sha256;
  analysis.review_binding = {
    candidate_binding: review.candidate_binding,
    model_context: {
      input_descriptor_sha256: review.input_descriptor_sha256,
      model_id: "TEST_ONLY_RI",
      model_version: "residual-income-equity-path-v2",
      profile_id: "TEST_ONLY_PROFILE",
      research_case_sha256: "1".repeat(64),
      facts_sha256: "2".repeat(64),
      assumptions_sha256: "3".repeat(64),
      research_as_of: analysis.research_as_of,
    },
  };
  analysis.source_bindings = [
    review.candidate_binding,
    review.proposal_binding,
    review.policy_binding,
  ];
  analysis.joint_capital_review = review;
  analysis.model_applicability!.route = {
    selected_model: "TEST_ONLY_RI",
    model_type: "TEST_ONLY_RI",
    profile_id: "TEST_ONLY_PROFILE",
  };
  analysis.valuation = {
    model_type: "TEST_ONLY_RI",
    model_version: "residual-income-equity-path-v2",
    valuation_date: analysis.valuation_date!,
    bear_value: "123.456789",
    base_value: "123.456789",
    bull_value: "123.456789",
    assumptions: {
      valuation_timing: {
        basis_at: review.basis_at!,
        valuation_at: review.valuation_at!,
      },
    },
  };
  analysis.scenarios.forEach((row) => {
    row.per_share_value = "123.456789";
  });
  delete analysis.economic_assessment;
  return analysis;
}

describe("versioned ten-year joint cash review", () => {
  it.each(["schema", "mode", "both"])(
    "accepts explicit %s version with ten-year cash fields only",
    (marker) => {
      const handoff = jointCashFixture();
      const review = handoff.economic_review_materials!.joint_capital_review!;
      if (marker === "schema") delete review.input_mode;
      if (marker === "mode") review.schema_version = "joint-capital-review-v1";
      const before = structuredClone(handoff);
      expect(jointCapitalReviewMatches(handoff, handoff.symbol)).toBe(true);
      const html = render(handoff);
      for (const text of [
        "10年",
        "第 10 年",
        "经营",
        "现金约束",
        "条件分配",
        "留存",
        "资金演算",
        "持续终端",
        "净维护现金",
        "营运资金 WC",
        "承诺现金",
        "条件估值",
        "反证",
        "未批准",
        "action=no_order",
        "12.34567890123456789",
        "-2",
        "TEST_ONLY 持续终端",
      ])
        expect(html).toContain(text);
      expect(html).not.toContain("三情景五年");
      expect(html).not.toContain("<button");
      expect(handoff).toEqual(before);
      const analysis = publicCashFixture(handoff);
      expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
        true,
      );
      expect(
        renderToStaticMarkup(
          <PublicJointCapitalReview
            analysis={analysis}
            symbol={analysis.symbol}
          />,
        ),
      ).toContain("第 10 年");
    },
  );

  it("keeps shortfall and negative cash visible without approval", () => {
    const handoff = jointCashFixture();
    const ledger =
      handoff.economic_review_materials!.joint_capital_review!.scenarios[0]
        .ledger;
    ledger.funding_status = ledger.rows[0].funding_status = "SHORTFALL";
    ledger.rows[0].funding_shortfall = "100";
    ledger.rows[0].closing_cash = "-123456789.123456789";
    expect(jointCapitalReviewMatches(handoff, handoff.symbol)).toBe(true);
    expect(render(handoff)).toContain("SHORTFALL：资金约束存在缺口");
    expect(render(handoff)).toContain("-1.23 亿元");
    expect(render(handoff)).toContain("-123456789.123456789");
  });

  it.each([
    ...jointCashRowFields.map(
      (key) =>
        [
          "missing row " + key,
          (r: any) => {
            delete r.scenarios[0].ledger.rows[0][key];
          },
        ] as const,
    ),
    ...jointCashPolicyFields.map(
      (key) =>
        [
          "missing terminal " + key,
          (r: any) => {
            delete r.scenarios[0].ledger.terminal_policy[key];
          },
        ] as const,
    ),
    ...jointCashTerminalFields.map(
      (key) =>
        [
          "missing terminal result " + key,
          (r: any) => {
            delete r.scenarios[0].ledger[key];
          },
        ] as const,
    ),
    ["nine rows", (r: any) => r.scenarios[0].ledger.rows.pop()],
    [
      "duplicate year",
      (r: any) => {
        r.scenarios[0].ledger.rows[9].year = 9;
      },
    ],
    [
      "five drivers",
      (r: any) => {
        r.scenarios[0].drivers.years.length = 5;
      },
    ],
    [
      "null",
      (r: any) => {
        r.scenarios[0].ledger.rows[0].distribution = null;
      },
    ],
    [
      "NaN",
      (r: any) => {
        r.scenarios[0].ledger.rows[0].retention = "NaN";
      },
    ],
    [
      "infinity",
      (r: any) => {
        r.scenarios[0].ledger.terminal.profit = "Infinity";
      },
    ],
    [
      "numeric not string",
      (r: any) => {
        r.scenarios[0].ledger.rows[0].profit = 100;
      },
    ],
    [
      "retention mismatch",
      (r: any) => {
        r.scenarios[0].ledger.forecast_retentions[9] = ".9";
      },
    ],
    [
      "retention missing",
      (r: any) => {
        r.scenarios[0].ledger.forecast_retentions.pop();
      },
    ],
    [
      "unknown funding",
      (r: any) => {
        r.scenarios[0].ledger.funding_status = "PASS";
      },
    ],
    [
      "terminal mismatch",
      (r: any) => {
        r.scenarios[0].ledger.terminal_policy.commitment_cash_cny = "0";
      },
    ],
    [
      "currency",
      (r: any) => {
        r.scenarios[0].ledger.currency = "USD";
      },
    ],
    [
      "no counterevidence",
      (r: any) => {
        r.scenarios[0].ledger.limitations = [];
      },
    ],
    [
      "unknown schema",
      (r: any) => {
        r.schema_version = "other";
      },
    ],
    [
      "wrong mode",
      (r: any) => {
        r.input_mode = "other";
      },
    ],
    [
      "approval",
      (r: any) => {
        r.approval_changed = true;
      },
    ],
    [
      "order",
      (r: any) => {
        r.action = "buy";
      },
    ],
    [
      "binding",
      (r: any) => {
        r.policy_binding.sha256 = "0".repeat(64);
      },
    ],
    [
      "first payment",
      (r: any) => {
        r.valuation_at = "2027-06-30T23:59:59+08:00";
      },
    ],
  ] as [string, (r: any) => void][])(
    "rejects %s without replacing missing data with zero",
    (_name, mutate) => {
      const handoff = jointCashFixture();
      (mutate as (r: any) => void)(
        handoff.economic_review_materials!.joint_capital_review,
      );
      expect(jointCapitalReviewMatches(handoff, handoff.symbol)).toBe(false);
      const html = render(handoff);
      expect(html).toContain("暂不可展示");
      expect(html).not.toContain("第 10 年");
      const analysis = publicCashFixture();
      analysis.joint_capital_review = structuredClone(
        handoff.economic_review_materials!.joint_capital_review!,
      );
      analysis.joint_capital_review.symbol = analysis.symbol;
      expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
        false,
      );
    },
  );

  it("retains public model identity and precise valuation binding", () => {
    const analysis = publicCashFixture();
    analysis.valuation!.base_value = "123.45678900000000001";
    expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
      false,
    );
    analysis.valuation!.base_value = "123.456789";
    analysis.review_binding!.model_context.model_version = "legacy";
    expect(publicJointCapitalReviewMatches(analysis, analysis.symbol)).toBe(
      false,
    );
  });
});
