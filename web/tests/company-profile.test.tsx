import React from "react";
import { expect, it } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (node: React.ReactNode) => string;
};
import {
  CompanyProfileView,
  type CompanyProfile,
} from "../src/components/CompanyProfilePanel";
const example = (): CompanyProfile => ({
  schema_version: "company-research-profile-v1",
  symbol: "600519",
  status: "CONDITIONAL_RESEARCH",
  action: "no_order",
  formal_eligibility: false,
  as_of: "2026-06-30",
  business_model: "TEST_ONLY 产品收入与股东现金路径",
  profile: { profile_id: "quality_compounder" },
  route: {
    status: "SUPPORTED",
    selected_model: "residual_income_or_equity_value",
    required_inputs: ["shares"],
  },
  evidence_refs: [
    {
      id: "TEST_ONLY",
      source_url: "https://example.org/official.pdf",
      sha256: "a".repeat(64),
    },
  ],
  counter_evidence: ["TEST_ONLY 资金上划有约束"],
  invalidation_conditions: ["TEST_ONLY 收入结构改变"],
  blockers: ["HUMAN_APPROVAL_PENDING"],
});
it("explains actual route, dates, counter evidence and limits without a buy claim", () => {
  const html = renderToStaticMarkup(
    <CompanyProfileView data={example()} symbol="600519" />,
  );
  for (const value of [
    "剩余收益／股东权益价值",
    "2026-06-30",
    "资金上划有约束",
    "收入结构改变",
    "不授予",
    "https://example.org/official.pdf",
  ])
    expect(html).toContain(value);
});
it.each([
  { symbol: "600887" },
  { action: "order" },
  { formal_eligibility: true },
])("rejects mixed identity or granted authority %s", (patch) => {
  const data = { ...example(), ...patch } as CompanyProfile;
  const html = renderToStaticMarkup(
    <CompanyProfileView data={data} symbol="600519" />,
  );
  expect(html).toContain("停止展示");
  expect(html).not.toContain("TEST_ONLY 产品");
});
it("keeps unknown economics visible and never invents a model", () => {
  const data = {
    ...example(),
    profile: null,
    route: null,
    business_model: null,
    evidence_refs: [],
  };
  const html = renderToStaticMarkup(
    <CompanyProfileView data={data} symbol="600519" />,
  );
  expect(html).toContain("不能确定适用模型");
  expect(html).toContain("未形成可核验证据");
});
it("does not make hostile source schemes clickable", () => {
  const data = {
    ...example(),
    evidence_refs: [{ id: "x", source_url: "javascript:alert(1)" }],
  };
  expect(
    renderToStaticMarkup(<CompanyProfileView data={data} symbol="600519" />),
  ).not.toContain('href="javascript:');
});
