import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const response = vi.hoisted(() => ({
  loading: false,
  error: undefined,
  retry: () => {},
  data: {
    status: "NOT_CONNECTED",
    reason: "无已登记材料",
    findings: [],
    sources: [],
  } as any,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => response }));
import { AgentResearchPanel } from "../src/pages/DecisionDetail/AgentResearchPanel";

it("shows absence without inventing an AI conclusion", () => {
  const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
  expect(html).toContain("暂无已绑定的 AI 研究材料");
  expect(html).not.toContain("材料绑定已核验");
});

it("separates missing financial work from the retained event draft", () => {
  response.data = {
    status: "NOT_CONNECTED",
    reason: "WORKFLOW_NOT_REGISTERED",
    workflow: "financial",
    available_workflows: ["event"],
    findings: [],
    sources: [],
  };
  const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
  expect(html).toContain("研究材料类型");
  expect(html).toContain("公告事件");
  expect(html).toContain("财报");
  expect(html).toContain("其他研究材料不会代替此项");
  expect(html).not.toContain("材料绑定已核验");
});

it("labels retained mock research and separates citations from authority", () => {
  response.data = {
    status: "VERIFIED",
    mode: "MOCK",
    research_as_of: "2026-10-09",
    findings: [
      {
        finding_id: "one",
        role: "COUNTER_EVIDENCE",
        claim: "测试反证",
        evidence_refs: ["annual-report"],
        counter_evidence_refs: ["event"],
        proposed_follow_up: "核对最新公告",
      },
    ],
    sources: [
      {
        evidence_id: "event",
        title: "原始公告",
        sha256: "a".repeat(64),
        available_at: "2026-10-08",
      },
    ],
  };
  const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
  expect(html).toContain("Mock 模拟研究（历史材料）");
  expect(html).toContain("研究草案待复核");
  expect(html).toContain("不代表当前研究结论、正式批准或交易许可");
  expect(html).toContain("反面证据");
  expect(html).toContain("核对最新公告");
});
