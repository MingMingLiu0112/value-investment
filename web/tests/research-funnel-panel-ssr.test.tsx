import React from "react";
import { expect, it } from "vitest";
import { ResearchFunnelAuditPanel } from "../src/components/ResearchFunnelAuditPanel";
import type { ResearchFunnelStatus } from "../src/types/api";

const { renderToStaticMarkup } = require("react-dom/server");

const verified: ResearchFunnelStatus = {
  schema_version: "public-research-funnel-status-v1",
  action: "no_order",
  status: "VERIFIED",
  reason: null,
  task_id: "W6-FUNNEL-AUDIT-V1",
  as_of: "2026-10-12",
  audit_sha256: "a".repeat(64),
  review: { status: "HUMAN_REVIEW_PENDING", approved: false },
  universe: {
    securities: 5573,
    industries_mapped: 5573,
    market_snapshots: 5573,
    leads: 114,
  },
  evidence: {
    financial_symbols: 873,
    financial_points: 21277,
    dividend_evidence_count: 3622,
    same_period_complete_symbols: 0,
    quality_pass: 0,
    quality_data_gap: 4677,
    quality_insufficient_evidence: 775,
    capital_return_status: "UNAVAILABLE",
    capital_return_reason: "没有可接受的资本回报事实",
  },
  quote: {
    date: "2026-10-12",
    trade_date_verified: false,
    verified_count: 0,
    unverified_count: 5573,
  },
  queue: {
    entry_count: 114,
    selected_count: 10,
    deferred_count: 104,
    selected_symbols: ["000151"],
  },
  channels: [],
  sample: [
    {
      symbol: "000151",
      name: "示例公司",
      industry: "制造业",
      channels: ["value"],
      research_state: "DATA_CHECK",
      gaps: [],
    },
  ],
  blockers: ["QUALITY_ZERO_PASS"],
  source_files: {},
  artifacts: null,
};

it("renders verified audit facts without a second per-symbol task list", () => {
  const html = renderToStaticMarkup(
    <ResearchFunnelAuditPanel
      funnel={verified}
      loading={false}
      retry={() => {}}
    />,
  );

  expect(html).toContain("只读审计，不构成买卖建议");
  expect(html).toContain("5573 只证券");
  expect(html).toContain("当前快照没有通过质量门禁的证券");
  expect(html).not.toContain("待补数据研究样本");
  expect(html).not.toContain("示例公司");
});

it("fails closed without counts when the audit is invalid", () => {
  const html = renderToStaticMarkup(
    <ResearchFunnelAuditPanel
      funnel={{
        ...verified,
        status: "INVALID",
        reason: "FUNNEL_OUTPUT_HASH_MISMATCH",
      }}
      loading={false}
      retry={() => {}}
    />,
  );

  expect(html).toContain("审计文件校验失败，已停止展示");
  expect(html).toContain("FUNNEL_OUTPUT_HASH_MISMATCH");
  expect(html).not.toContain("5573 只证券");
});

it("shows a retry action rather than retained counts after a network error", () => {
  const html = renderToStaticMarkup(
    <ResearchFunnelAuditPanel
      funnel={verified}
      loading={false}
      error="network failed"
      retry={() => {}}
    />,
  );

  expect(html).toContain("漏斗审计读取失败：network failed");
  expect(html).toMatch(/重\s*试/);
  expect(html).not.toContain("5573 只证券");
});
