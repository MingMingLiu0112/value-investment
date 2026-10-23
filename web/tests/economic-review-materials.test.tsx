import React from "react";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { EconomicReviewMaterials } from "../src/components/EconomicReviewMaterials";
import { economicMaterialsMatch } from "../src/services/valuePolicy";
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
