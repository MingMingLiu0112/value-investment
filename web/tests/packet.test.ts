import { describe, expect, it } from "vitest";
import {
  blockerText,
  excelComparisonText,
  excelNewerSideText,
  freshnessLevel,
  packetDateRows,
  snapshotCutoffLine,
  snapshotIntegrityText,
} from "../src/utils/packet";
import type { DailyPublicPacket } from "../src/types/api";

function makePacket(
  overrides: Partial<DailyPublicPacket> = {},
): DailyPublicPacket {
  return {
    schema_version: "daily-public-packet.v1",
    action: "no_order",
    packet_status: "CURRENT",
    publication_id: "pub-test",
    research_version: "research-test",
    generated_at: "2026-10-13T00:00:00Z",
    dates: {
      current_natural_date: "2026-10-13",
      latest_completed_trade_session: "2026-10-13",
      quote_trade_date: "2026-10-12",
      quote_observed_at: "2026-10-12T16:00:00+08:00",
      research_as_of: "2026-10-11",
      model_validity: { status: "UNKNOWN", valid_through: null },
      decision_published_on: "2026-10-12",
      excel_published_as_of: "2026-10-01",
      excel_quote_observation_as_of: "2026-09-30",
    },
    formal_admission_count: 0,
    pending_review_count: 2,
    research_counts: {
      universe_count: 5573,
      lead_count: 114,
      queue_count: 114,
      needs_re_research_count: 1,
      incomplete_research_count: 6,
      awaiting_verified_close_count: 5,
    },
    blockers: ["NEEDS_RE_RESEARCH:600887"],
    data_freshness: {
      quote: { status: "STALE", reason: "尚未形成最近完成交易日的收盘价" },
      research: { status: "STALE" },
      excel: { status: "SNAPSHOT" },
    },
    source_bindings_verified: true,
    company_statuses: {},
    ...overrides,
  };
}

describe("daily public packet display helpers", () => {
  it("translates bare codes and CODE:symbol pairs without inventing labels", () => {
    expect(blockerText("PRICE_NOT_ADMITTED")).toBe("尚未接入经核验的当前行情");
    expect(blockerText("NEEDS_RE_RESEARCH:600887")).toBe(
      "需要重新研究以覆盖最新已核验收盘（600887）",
    );
    expect(blockerText("BRAND_NEW_CODE")).toBe("BRAND_NEW_CODE");
    expect(blockerText("BRAND_NEW_CODE:600519")).toBe(
      "BRAND_NEW_CODE（600519）",
    );
  });

  it("renders a changed registered evidence hash in Chinese with the affected symbol", () => {
    expect(blockerText("REGISTERED_EVIDENCE_CHANGED:000333")).toBe(
      "登记证据哈希变化：该公司研究结果降级为不可核验，需重新登记证据（000333）",
    );
    // Other companies stay readable: the code is a per-symbol blocker, not a page-level failure.
    expect(blockerText("REGISTERED_EVIDENCE_CHANGED:600519")).toContain(
      "600519",
    );
  });

  it("keeps the eight packet dates ordered and marks missing ones", () => {
    const rows = packetDateRows(makePacket());
    expect(rows.map((row) => row.label)).toEqual([
      "研究截止日",
      "已登记行情日",
      "最近已完成交易日",
      "决策发布日",
      "Excel 快照时点",
    ]);
    expect(rows[0].value).toBe("2026-10-11");
    expect(rows[2].value).toBe("2026-10-13");

    const missing = packetDateRows(
      makePacket({
        dates: {
          current_natural_date: null,
          latest_completed_trade_session: null,
          quote_trade_date: null,
          quote_observed_at: null,
          research_as_of: null,
          model_validity: { status: "UNKNOWN", valid_through: null },
          decision_published_on: null,
          excel_published_as_of: null,
          excel_quote_observation_as_of: null,
        },
      }),
    );
    expect(missing.every((row) => row.value === "未提供")).toBe(true);
  });

  it("maps freshness statuses to display levels", () => {
    expect(freshnessLevel("FRESH")).toBe("ok");
    expect(freshnessLevel("STALE")).toBe("warning");
    expect(freshnessLevel("SOMETHING_NEW")).toBe("unknown");
    expect(freshnessLevel(undefined)).toBe("unknown");
  });
});

describe("daily snapshot display helpers", () => {
  it("translates the Excel comparison status without ever claiming a match", () => {
    expect(excelComparisonText({ status: "MATCHED" })).toBe(
      "与正式 Excel 一致",
    );
    expect(excelComparisonText({ status: "DIFFERENT" })).toBe(
      "与正式 Excel 不一致（转人工处理，不自动同步）",
    );
    expect(excelComparisonText({ status: "NOT_VERIFIED" })).toBe(
      "未校验（缺少可核对的哈希或文件）",
    );
    expect(excelComparisonText({ status: "NOT_RESOLVED" })).toBe(
      "未解析到正式 Excel 路径",
    );
    expect(excelComparisonText({ status: "SOMETHING_NEW" })).toBe(
      "对照状态未知：SOMETHING_NEW",
    );
    expect(excelComparisonText(undefined)).toBe("未执行只读校验");
    expect(excelComparisonText(null)).toBe("未执行只读校验");
  });

  it("reports the missing-snapshot case honestly instead of showing a version", () => {
    expect(snapshotIntegrityText(undefined)).toBe("快照状态尚未读取");
    expect(
      snapshotIntegrityText({
        status: "UNAVAILABLE",
        reason: "SNAPSHOT_POINTER_MISSING",
      }),
    ).toBe("尚无已验证快照：尚未发布过任何已验证快照");
    expect(
      snapshotIntegrityText({
        status: "INVALID",
        reason: "SNAPSHOT_ARTIFACT_HASH_MISMATCH",
      }),
    ).toContain("快照校验失败");
    expect(snapshotIntegrityText({ status: "VERIFIED", reason: null })).toBe(
      "已校验哈希（SHA-256 复核通过）",
    );
    expect(
      snapshotIntegrityText({ status: "INVALID", reason: "BRAND_NEW_CODE" }),
    ).toBe("快照校验失败：BRAND_NEW_CODE");
  });

  it("compares the two recorded Excel dates and stays silent when one is missing", () => {
    expect(
      excelNewerSideText(
        { pointer_published_as_of: "2026-10-05" },
        { excel_published_as_of: "2026-10-01" },
      ),
    ).toContain(
      "正式工作簿指针 2026-10-05 新于快照记录的 Excel 时点 2026-10-01",
    );
    expect(
      excelNewerSideText(
        { pointer_published_as_of: "2026-10-01" },
        { excel_published_as_of: "2026-10-01" },
      ),
    ).toBe("两侧记录同一 Excel 快照时点（2026-10-01）");
    expect(
      excelNewerSideText(
        { pointer_published_as_of: "2026-09-28" },
        { excel_published_as_of: "2026-10-01" },
      ),
    ).toContain(
      "快照记录的 Excel 时点 2026-10-01 新于正式工作簿指针 2026-09-28",
    );
    expect(
      excelNewerSideText(
        { pointer_published_as_of: null },
        { excel_published_as_of: "2026-10-01" },
      ),
    ).toBeNull();
    expect(excelNewerSideText(undefined, undefined)).toBeNull();
  });

  it("renders the snapshot cutoff line from the snapshot dates", () => {
    expect(
      snapshotCutoffLine({
        quote_trade_date: "2026-10-13",
        research_as_of: "2026-10-11",
        excel_published_as_of: "2026-10-01",
      }),
    ).toBe("行情 2026-10-13 · 研究截止 2026-10-11 · Excel 快照 2026-10-01");
    expect(
      snapshotCutoffLine({
        quote_trade_date: null,
        research_as_of: null,
        excel_published_as_of: null,
      }),
    ).toBe("行情 未提供 · 研究截止 未提供 · Excel 快照 未提供");
    expect(snapshotCutoffLine(null)).toBe("未提供");
  });
});
