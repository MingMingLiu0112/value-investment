import { describe, expect, it } from "vitest";
import { reconciliationView } from "../src/utils/codes";
import { dailyStatus } from "../src/utils/status";
import type { DailyResponse } from "../src/types/api";

describe("reconciliationView", () => {
  it("returns null when the portfolio reports no reconciliation block", () => {
    expect(reconciliationView(null)).toBeNull();
    expect(reconciliationView(undefined)).toBeNull();
  });

  it("explains a superseded snapshot and an internal-only scope", () => {
    const view = reconciliationView({
      status: "PENDING_RECONCILIATION",
      superseded: true,
      reason: "SUPERSEDED_BY_NEWER_FILL",
      state_version: 4,
      snapshot_version: 3,
      scope: "INTERNAL_JOURNAL_REPLAY",
      reconciled_at: "2026-10-13T01:00:00+00:00",
    });
    expect(view).toEqual({
      statusText: "尚未执行对账",
      scopeText: "系统内部流水重算（不等于券商对账）",
      reasonText: "新的已确认成交晚于上次对账，旧快照不再代表当前持仓",
      reconciledAt: "2026-10-13T01:00:00+00:00",
    });
  });

  it("never invents a meaning for unknown codes", () => {
    const view = reconciliationView({
      status: "SOMETHING_NEW",
      superseded: false,
      reason: "NEW_REASON",
      state_version: 1,
      snapshot_version: 1,
      scope: "NEW_SCOPE",
      reconciled_at: null,
    });
    expect(view).toEqual({
      statusText: "SOMETHING_NEW",
      scopeText: "NEW_SCOPE",
      reasonText: "NEW_REASON",
      reconciledAt: null,
    });
  });

  it("labels a reconciled external statement without a reason line", () => {
    const view = reconciliationView({
      status: "RECONCILED",
      superseded: false,
      reason: null,
      state_version: 2,
      snapshot_version: 2,
      scope: "EXTERNAL_ACCOUNT_STATEMENT",
      reconciled_at: "2026-10-12T01:00:00+00:00",
    });
    expect(view?.statusText).toBe("已完成对账");
    expect(view?.scopeText).toBe("外部账户对账凭证");
    expect(view?.reasonText).toBeNull();
  });
});

describe("dailyStatus with unavailable counts", () => {
  it("reports a missing publication as no candidate instead of zero rows", () => {
    const data = {
      summary: { universe_count: null, formal_count: 0, watch_count: null },
    } as unknown as DailyResponse;
    expect(dailyStatus(data)).toEqual({
      formalCount: 0,
      watchCount: null,
      noFormalCandidate: true,
    });
  });
});
