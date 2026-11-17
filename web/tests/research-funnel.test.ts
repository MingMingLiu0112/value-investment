import { describe, expect, it } from "vitest";
import type { ResearchFunnelStatus } from "../src/types/api";
import {
  funnelBlockerText,
  funnelChannelRows,
  funnelEvidenceRows,
  funnelStatusText,
} from "../src/utils/research-funnel";

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
  channels: [
    {
      key: "quality",
      pass_count: 0,
      data_gap_count: 4677,
      insufficient_evidence_count: 775,
      rejected_count: 0,
      not_evaluated_count: 0,
      budget_excluded_count: 0,
      unsupported_count: 121,
      top_reason: "缺少同一报告期证据",
    },
  ],
  sample: [],
  blockers: ["QUOTE_DATE_UNVERIFIED", "QUALITY_ZERO_PASS"],
  source_files: {},
  artifacts: null,
};

describe("research funnel display helpers", () => {
  it("keeps audit verification separate from investment advice", () => {
    expect(funnelStatusText("VERIFIED")).toBe("审计文件哈希复核通过");
    expect(funnelBlockerText("QUALITY_ZERO_PASS")).toBe(
      "当前快照没有通过质量门禁的证券",
    );
    expect(funnelBlockerText("BRAND_NEW_CODE")).toBe("BRAND_NEW_CODE");
  });

  it("renders counts without calling queue selection a buy signal", () => {
    const rows = funnelEvidenceRows(verified);
    expect(rows.find((row) => row.label === "初筛结果")?.value).toContain(
      "待补数据 10 个",
    );
    expect(rows.find((row) => row.label === "行情日期")?.value).toContain(
      "未验证 5573 条",
    );
  });

  it("projects channel gaps into readable Chinese labels", () => {
    expect(funnelChannelRows(verified)).toEqual([
      {
        key: "quality",
        channel: "质量",
        passed: 0,
        gap: "缺数据 4677 · 缺证据 775 · 画像未支持 121",
        reason: "缺少同一报告期证据",
      },
    ]);
  });

  it("returns no invented rows when the audit is unavailable", () => {
    expect(
      funnelEvidenceRows({ ...verified, status: "INVALID", universe: null }),
    ).toEqual([]);
  });
});
