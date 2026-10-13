import { describe, expect, it } from "vitest";
import {
  blockerText,
  freshnessLevel,
  packetDateRows,
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
