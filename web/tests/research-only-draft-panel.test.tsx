import React from "react";
import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import type { ResearchOnlyDraft } from "../src/types/api";

const { renderToStaticMarkup } = require("react-dom/server");

vi.mock("antd", () => ({
  Alert: ({ message, description }: any) => (
    <div>
      {message}
      {description}
    </div>
  ),
  Tag: ({ children }: any) => <span>{children}</span>,
  Descriptions: ({ items }: any) => (
    <dl>
      {items.map((r: any) => (
        <div key={r.key}>
          <dt>{r.label}</dt>
          <dd>{r.children}</dd>
        </div>
      ))}
    </dl>
  ),
  Typography: {
    Title: ({ children }: any) => <h3>{children}</h3>,
    Text: ({ children }: any) => <span>{children}</span>,
    Paragraph: ({ children }: any) => <p>{children}</p>,
  },
}));

import { ResearchDraftPanel } from "../src/pages/DecisionDetail/ResearchDraftPanel";

const draft: ResearchOnlyDraft = {
  schema_version: "public-research-only-draft-v1",
  research_mode: "research_only_v1",
  action: "no_order",
  symbol: "000544",
  company_name: "TEST_ONLY environmental company",
  run_id: "TEST_ONLY",
  research_version: "TEST_ONLY-v1",
  status: "RESEARCH_DRAFT_NOT_APPROVED",
  research_as_of: "2026-10-24",
  available_at: "2026-10-24T13:00:00Z",
  financial_period: "2026-06-30",
  assessment_status: "UNASSESSABLE",
  native_status: "UNSUPPORTED",
  issuer_identity_status: "NOT_READY",
  confidence: "LOW",
  observations_verified: false,
  summary: "TEST_ONLY 模型不适用，不能把资料不足说成不交易。",
  thesis: "TEST_ONLY PPP现金分类需核对",
  return_driver: "尚未证明可持续现金回报",
  mispricing_hypothesis: "尚未建立",
  valuation: null,
  model_validity: null,
  quote_fact: null,
  price_bridge: null,
  gates: null,
  observations: [
    {
      field_name: "operating_cash_flow",
      value: "-1.25",
      prior_value: null,
      period_label: "2026-06-30",
      unit: "CNY",
      statement_scope: "consolidated",
      evidence_refs: ["TEST_ONLY_SOURCE"],
    },
    {
      field_name: "TEST_ONLY_zero",
      value: "0",
      prior_value: "0",
      evidence_refs: ["TEST_ONLY_SOURCE"],
    },
  ],
  research_topics: [
    {
      id: "CONCESSION",
      status: "UNASSESSED",
      explanation: "TEST_ONLY PPP资金与重述风险",
      evidence_refs: ["TEST_ONLY_SOURCE"],
      missing: ["维护与增长投入未分离"],
    },
  ],
  evidence: [
    {
      id: "TEST_ONLY_SOURCE",
      sha256: "a".repeat(64),
      url: "https://static.cninfo.com.cn/TEST_ONLY.pdf",
      page: 1,
      retrieved_at: "2026-10-24T12:00:00Z",
      available_at: "2026-10-24T12:00:00Z",
      published_date: "2026-08-01",
    },
  ],
  counter_evidence: ["同期比较数据已重述，不能直接计算TTM"],
  thesis_breakers: [],
  next_events: [],
  blockers: ["MODEL_APPLICABILITY_UNASSESSED_RESEARCH_ONLY"],
  boundary: "非原始历史PIT证明；非买卖建议。",
  research_input_binding: {
    package: { path: "runtime/TEST_ONLY.json", sha256: "b".repeat(64) },
    input_sha256: "c".repeat(64),
  },
  input_verification: {
    status: "SOURCE_INPUTS_MATCH_NO_VALUATION",
    source_contract_status:
      "SOURCE_CUTOFF_VALIDATED_NO_SCENARIOS_OR_FACT_ADMISSION",
    input_sha256: "c".repeat(64),
    computed_at: "2026-10-24T13:00:00Z",
    cutoff_at: "2026-10-24T12:00:00Z",
    economic_approval: false,
  },
};

describe("explicit research-only draft", () => {
  it.each([
    "matching_bad_input_hashes",
    "package_hash",
    "hash_trailing_newline",
    "evidence_hash",
    "unknown_ref",
    "empty_refs",
    "duplicate_ref",
    "duplicate_evidence",
    "conflicting_evidence",
  ])(
    "withholds observations when source display closure is invalid: %s",
    (mutation) => {
      const value = structuredClone(draft);
      if (mutation === "matching_bad_input_hashes") {
        value.input_verification.input_sha256 = "BAD";
        value.research_input_binding.input_sha256 = "BAD";
      } else if (mutation === "hash_trailing_newline")
        value.research_input_binding.package.sha256 += "\n";
      else if (mutation === "package_hash")
        value.research_input_binding.package.sha256 = "BAD";
      else if (mutation === "evidence_hash") value.evidence[0].sha256 = "BAD";
      else if (mutation === "unknown_ref")
        value.observations[0].evidence_refs = ["DOES_NOT_EXIST"];
      else if (mutation === "empty_refs")
        value.observations[0].evidence_refs = [];
      else if (mutation === "duplicate_ref")
        value.observations[0].evidence_refs.push("TEST_ONLY_SOURCE");
      else if (mutation === "duplicate_evidence")
        value.evidence.push({ ...value.evidence[0] });
      else
        value.evidence.push({ ...value.evidence[0], sha256: "d".repeat(64) });
      const html = renderToStaticMarkup(<ResearchDraftPanel draft={value} />);
      expect(html).toContain("不可核验");
      expect(html).not.toContain("-1.25");
      expect(html).not.toContain("TEST_ONLY_zero");
    },
  );
  it("shows unknown financial research, not scenarios, quotes, quantities or a sufficient-evidence rejection", () => {
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={draft} />);
    for (const text of [
      "UNASSESSABLE",
      "官方原文观测",
      "未准入",
      "PPP",
      "重述",
      "-1.25",
      "缺失（不补零）",
      "TEST_ONLY_zero",
      "知识截止",
      "SHA-256",
    ])
      expect(html).toContain(text);
    for (const text of [
      "NO_TRADE",
      "每股合理价值",
      "当前价格",
      "建议买入",
      "目标仓位",
    ])
      expect(html).not.toContain(text);
    expect(html).toContain("min-width:0");
    expect(html).toContain("overflow-wrap:anywhere");
    expect(html).toContain("overflow-x:auto");
  });
  it.each([
    { schema_version: "public-research-only-draft-v999" },
    { research_mode: "research_only_v999" },
    { assessment_status: "NO_TRADE" },
    { observations_verified: true },
    { valuation: { scenarios: [] } },
    { quote_fact: { current_price: "10" } },
    { gates: { results: { G3: true } } },
    { action: "buy" },
    {
      input_verification: {
        ...draft.input_verification,
        economic_approval: true,
      },
    },
    {
      input_verification: {
        ...draft.input_verification,
        input_sha256: "d".repeat(64),
      },
    },
  ])(
    "does not display numbers from unknown or promoted variants: %j",
    (change) => {
      const html = renderToStaticMarkup(
        <ResearchDraftPanel draft={{ ...draft, ...change } as any} />,
      );
      expect(html).toMatch(/无法核验|不可核验/);
      expect(html).not.toContain("-1.25");
    },
  );
});

it.skipIf(!process.env.RESEARCH_ONLY_DRAFT_HTTP_OUTPUT)(
  "renders actual TestClient 000544 official observations without a valuation",
  () => {
    const body = JSON.parse(
      fs.readFileSync(process.env.RESEARCH_ONLY_DRAFT_HTTP_OUTPUT!, "utf8"),
    );
    const value = body.research_draft as ResearchOnlyDraft;
    expect(value.symbol).toBe("000544");
    expect(value.observations).toHaveLength(10);
    expect(value.input_verification.status).toBe(
      "SOURCE_INPUTS_MATCH_NO_VALUATION",
    );
    expect(value.assessment_status).toBe("UNASSESSABLE");
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={value} />);
    for (const text of [
      "中原环保",
      "565688707.32",
      "-410384337.63",
      "2479153339.63",
      "654665565.45",
      "PPP",
      "重述",
      "55bac5078b18dfe1c7ff5bf79c90bf985e2635a7432c1aed2de579a63fe55002",
      "cf21f807e2c4f1d085dbfb6ec20151f0f0e54d58752dbebfea5f3f51271af958",
    ])
      expect(html).toContain(text);
    expect(value.quote_fact).toBeNull();
    expect(value.valuation).toBeNull();
    expect(body.decision.status).toBe("PENDING_RESEARCH");
  },
);
