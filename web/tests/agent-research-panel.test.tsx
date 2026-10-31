import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const harness = vi.hoisted(() => ({ calls: 0 }));
const response = vi.hoisted(() => ({
  loading: false,
  error: undefined as string | undefined,
  retry: () => {},
  data: {
    status: "NOT_CONNECTED",
    reason: "无已登记材料",
    findings: [],
    sources: [],
  } as any,
}));
const queue = vi.hoisted(() => ({
  loading: false,
  error: undefined as string | undefined,
  retry: () => {},
  data: {
    action: "no_order",
    status: "NOT_CONNECTED",
    failures: [],
    review_queue: [],
    review_queue_count: 0,
  } as any,
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: () => (harness.calls++ % 2 === 0 ? response : queue),
}));
import { AgentResearchPanel } from "../src/pages/DecisionDetail/AgentResearchPanel";

beforeEach(() => {
  harness.calls = 0;
  response.error = undefined;
  queue.error = undefined;
  queue.data = {
    action: "no_order",
    status: "NOT_CONNECTED",
    failures: [],
    review_queue: [],
    review_queue_count: 0,
  };
});

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
  expect(html).toContain("热点");
  expect(html).toContain("测试复盘");
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

it("shows an explicit empty human-review queue", () => {
  const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
  expect(html).toContain("待人工复核队列");
  expect(html).toContain("暂无待人工复核的已登记研究草稿");
  expect(html).toContain("仅展示已登记且绑定核验通过、仍待人工复核的研究草案");
});

it("shows cross-company scope labels without treating mock research as formal evidence", () => {
  queue.data = {
    action: "no_order",
    status: "VERIFIED",
    failures: [],
    review_queue_count: 2,
    review_queue: [
      {
        symbol: "600519",
        name: "示例公司",
        workflow: "event",
        status: "PENDING_HUMAN_REVIEW",
        verification_status: "VERIFIED",
        research_as_of: "2026-10-08",
        available_at: "2026-10-08T10:00:00+08:00",
        source_available_at: "2026-10-07",
        source_scope: {
          scope: "MOCK_LLM_RESEARCH_NOT_ADMITTED",
          data_scope: null,
          mode: "MOCK",
          classification: "TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE",
          test_only: true,
          formal_evidence: false,
          excerpt_origin: null,
        },
        packet_binding: { path: "runtime/event.json", sha256: "a".repeat(64) },
        registration_binding: {
          path: "config/current-agent-research.json",
          sha256: "b".repeat(64),
        },
        review_reason: "VERIFIED_RESEARCH_FINDINGS_PENDING_HUMAN_REVIEW",
        review_reason_text: "Pending human review",
        next_action: "OPEN_REGISTERED_DRAFT_FOR_HUMAN_REVIEW",
        next_action_text: "Review only",
        pending_findings_count: 3,
        action: "no_order",
        approval_unchanged: true,
        formal_eligibility_unchanged: true,
        decision_changed: false,
      },
      {
        symbol: "600000",
        name: null,
        workflow: "hotspot",
        status: "PENDING_HUMAN_REVIEW",
        verification_status: "VERIFIED",
        research_as_of: "2026-10-08",
        available_at: "2026-10-08T11:00:00+08:00",
        source_available_at: "2026-10-08",
        source_scope: {
          scope: "MOCK_LLM_RESEARCH_NOT_ADMITTED",
          data_scope: "PUBLIC_RESEARCH",
          mode: "MOCK",
          classification: "TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE",
          test_only: true,
          formal_evidence: false,
          excerpt_origin: "DERIVED_FROM_VERIFIED_PLAN",
        },
        packet_binding: {
          path: "runtime/hotspot.json",
          sha256: "c".repeat(64),
        },
        registration_binding: {
          path: "config/current-agent-research.json",
          sha256: "d".repeat(64),
        },
        review_reason: "VERIFIED_RESEARCH_FINDINGS_PENDING_HUMAN_REVIEW",
        review_reason_text: "Pending human review",
        next_action: "OPEN_REGISTERED_DRAFT_FOR_HUMAN_REVIEW",
        next_action_text: "Review only",
        pending_findings_count: 3,
        action: "no_order",
        approval_unchanged: true,
        formal_eligibility_unchanged: true,
        decision_changed: false,
      },
    ],
  };
  const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
  expect(html).toContain("待复核 2");
  expect(html).toContain("2 项跨公司研究草稿待人工复核");
  expect(html).toContain("示例公司（600519）");
  expect(html).toContain("600000");
  expect(html).toContain("PUBLIC_RESEARCH");
  expect(html).toContain("DERIVED_FROM_VERIFIED_PLAN");
  expect(html).toContain("Mock/测试材料，非正式证据");
  expect(html).toContain("action=no_order");
  expect(html).toContain("审批保持不变");
  expect(html).toContain("正式资格保持不变");
  expect(html).toContain("runtime/event.json");
  expect(html).toContain("runtime/hotspot.json");
  expect(html).toContain("config/current-agent-research.json");
  expect(html).toContain("打开该研究草稿");
  expect(html).not.toContain("代理审批");
});

it("retains all D1 controls and exactly one hint when both initial research reads fail identically", () => {
  const sharedError = "TEST_ONLY 初始研究读取需要本机授权";
  response.error = sharedError;
  queue.error = sharedError;
  const fetcher = vi.spyOn(globalThis, "fetch");
  try {
    const html = renderToStaticMarkup(<AgentResearchPanel symbol="600519" />);
    for (const label of [
      "读取已有任务",
      "新增任务",
      "手动刷新",
      "取消任务",
      "恢复任务",
    ])
      expect(html).toContain(label);
    expect(html.split(sharedError)).toHaveLength(2);
    expect(html).toContain("SAVED_RESPONSE");
    expect(html).toContain("不审批");
    expect(html).not.toContain("待人工复核队列");
    expect(fetcher).not.toHaveBeenCalled();
  } finally {
    fetcher.mockRestore();
  }
});
