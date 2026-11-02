import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const hooks = vi.hoisted(() => ({
  response: {} as any,
  fetch: undefined as any,
}));
vi.mock("react", async (original) => ({
  ...(await original<typeof import("react")>()),
  useCallback: (fn: any) => fn,
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: (fetch: any) => {
    hooks.fetch = fetch;
    return hooks.response;
  },
}));
import {
  ValueTrackingResearchPool,
  validTrackingPoolView,
  type TrackingPoolView,
} from "../src/components/ValueTrackingResearchPool";
const { renderToStaticMarkup } = require("react-dom/server");
const load = vi.fn<(signal: AbortSignal) => Promise<TrackingPoolView>>();
function fixture(): TrackingPoolView {
  return {
    schema_version: "sse-research-tracking-view-v1",
    action: "no_order",
    status: "AVAILABLE",
    scope: "SSE_MAIN_A_ONLY",
    source_status: "HISTORICAL_SNAPSHOT_SOURCE_REVALIDATED",
    source_available_at: "2026-11-01T01:00:00+08:00",
    generated_at: "2026-11-02T01:00:00+08:00",
    total_candidates: 51,
    tracking_count: 1,
    history_available: false,
    queue_binding: {
      path: "runtime/TEST_ONLY/queue.json",
      sha256: "a".repeat(64),
    },
    blockers: ["TEST_ONLY 交易日未核验"],
    items: [
      {
        symbol: "600001",
        name: "TEST_ONLY 来源对象",
        industry: "TEST_ONLY 行业",
        channels: ["value"],
        reason: "TEST_ONLY 原生入池理由",
        first_seen_at: "2026-11-01",
        tracking_status: "DATA_CHECK",
        financial_period: "2025-FY",
        accepted_fields: 1,
        required_fields: 9,
        next_action: "TEST_ONLY 获取官方附注",
        gaps: ["TEST_ONLY 完整融资范围未证"],
      },
    ],
  };
}
function render(view = fixture(), extra = {}) {
  hooks.response = {
    data: { view, loader: load },
    loading: false,
    retry: vi.fn(),
    ...extra,
  };
  return renderToStaticMarkup(<ValueTrackingResearchPool load={load} />);
}
beforeEach(() => {
  load.mockReset();
  hooks.response = { loading: true, retry: vi.fn() };
});
it("renders backend fields, stages, next actions and exact value link without granting downstream completion", () => {
  const view = fixture(),
    before = structuredClone(view);
  expect(validTrackingPoolView(view)).toBe(true);
  const html = render(view);
  for (const text of [
    "TEST_ONLY 来源对象",
    "TEST_ONLY 获取官方附注",
    "资料核验 / 待补证",
    "TEST_ONLY 完整融资范围未证",
    "2025-FY",
    "初筛候选：51",
    "跟踪对象：1",
    "研究预算决定处理顺序，不是投资排名",
    "入池不代表后续阶段已完成",
    "不是买入建议",
    "action=no_order",
    "留存来源不等于今日刷新",
    "历史连续性尚未提供",
    'href="/decisions/600001?strategy=value"',
    "原来源可得时间：2026-11-01",
    "不触发网络采集或写入",
  ])
    expect(html).toContain(text);
  expect(view).toEqual(before);
  expect(load).not.toHaveBeenCalled();
});
it("passes the AbortSignal to the sole read loader and validates its response", async () => {
  render();
  const controller = new AbortController();
  const view = fixture();
  load.mockResolvedValue(view);
  expect((await hooks.fetch(controller.signal)).view).toEqual(view);
  expect(load).toHaveBeenCalledTimes(1);
  expect(load).toHaveBeenCalledWith(controller.signal);
});
it("keeps unavailable distinct from zero and suppresses supplied old rows and counts", () => {
  const view = fixture();
  view.status = "UNAVAILABLE";
  const html = render(view);
  expect(html).toContain("不等于零候选");
  expect(html).not.toContain("TEST_ONLY 来源对象");
  expect(html).not.toContain("初筛候选：51");
  expect(html).toContain("TEST_ONLY 交易日未核验");
});
it("distinguishes explicit zero from unknown counts and dates", () => {
  const view = fixture();
  view.items = [];
  view.tracking_count = 0;
  view.total_candidates = 0;
  expect(render(view)).toContain("跟踪对象为0");
  view.tracking_count = null;
  view.total_candidates = null;
  view.source_available_at = null;
  view.generated_at = null;
  view.queue_binding = null;
  const html = render(view);
  expect(validTrackingPoolView(view)).toBe(true);
  expect(html).toContain("初筛候选：未知");
  expect(html).toContain("跟踪对象：未知");
  expect(html).toContain("原来源可得时间：未知");
  expect(html).not.toContain("跟踪对象为0");
});
it("shows only the first 30 native rows without sorting or filtering and preserves server counts", () => {
  const view = fixture();
  view.items = Array.from({ length: 31 }, (_, i) => ({
    ...view.items[0],
    symbol: String(600100 - i),
    name: "TEST_ONLY_NATIVE_" + i,
  }));
  view.tracking_count = 31;
  const html = render(view);
  expect(html).toContain("跟踪对象：31");
  expect(html).toContain("本页展示：30");
  expect(html).toContain("TEST_ONLY_NATIVE_29");
  expect(html).not.toContain("TEST_ONLY_NATIVE_30");
  expect(html.indexOf("TEST_ONLY_NATIVE_0")).toBeLessThan(
    html.indexOf("TEST_ONLY_NATIVE_1"),
  );
});
it.each(["loading", "error", "different_loader"])(
  "never exposes prior successful rows during %s",
  (state) => {
    const view = fixture();
    const extra =
      state === "loading"
        ? { loading: true }
        : state === "error"
          ? { error: "TEST_ONLY failure" }
          : { data: { view, loader: vi.fn() } };
    expect(render(view, extra)).not.toContain("TEST_ONLY 来源对象");
  },
);
it("retains unknown server stages and null industry rather than inventing classification", () => {
  const view = fixture();
  view.items[0].tracking_status = "TEST_ONLY_FUTURE_STAGE";
  view.items[0].industry = null;
  view.items[0].first_seen_at = null;
  view.items[0].gaps = [];
  view.history_available = true;
  const html = render(view);
  expect(html).toContain("TEST_ONLY_FUTURE_STAGE");
  expect(html).toContain("行业：未知");
  expect(html).toContain("首次记录：未知");
  expect(html).toContain("不代表下游研究已完成");
});
it.each([
  "version",
  "scope",
  "action",
  "source_false",
  "history_type",
  "negative_count",
  "count_string",
  "items_type",
  "symbol_path",
  "accepted_string",
  "accepted_over_required",
  "gaps_type",
  "next_action_type",
  "hash",
  "duplicate",
])("rejects malformed payload before display: %s", async (damage) => {
  const v: any = fixture();
  if (damage === "version") v.schema_version = "v2";
  if (damage === "scope") v.scope = "ALL_A";
  if (damage === "action") v.action = "BUY";
  if (damage === "source_false") v.source_status = false;
  if (damage === "history_type") v.history_available = "false";
  if (damage === "negative_count") v.tracking_count = -1;
  if (damage === "count_string") v.total_candidates = "51";
  if (damage === "items_type") v.items = {};
  if (damage === "symbol_path") v.items[0].symbol = "../private";
  if (damage === "accepted_string") v.items[0].accepted_fields = "1";
  if (damage === "accepted_over_required") v.items[0].accepted_fields = 10;
  if (damage === "gaps_type") v.items[0].gaps = false;
  if (damage === "next_action_type") v.items[0].next_action = null;
  if (damage === "hash") v.queue_binding.sha256 = "bad";
  if (damage === "duplicate") {
    v.items.push(v.items[0]);
    v.tracking_count = 2;
  }
  expect(validTrackingPoolView(v)).toBe(false);
  expect(render(v)).not.toContain("TEST_ONLY 来源对象");
  load.mockResolvedValue(v);
  await expect(hooks.fetch(new AbortController().signal)).rejects.toThrow(
    "停止展示",
  );
});

it.each([
  ["EVIDENCE_REVIEW_PENDING", "等待补证与资料复核"],
  ["DEEP_RESEARCH_PENDING", "等待经营与反证研究"],
  ["DATA_UNAVAILABLE", "资料核验尚未齐（查看具体缺口）"],
  ["EVIDENCE_ENRICHED", "已补充证据（非研究完成）"],
  ["QUALITY_READY", "质量资料就绪（非投资准入）"],
  ["QUALITY_EVALUATED", "已按既有规则评价质量（非投资准入）"],
])("explains actual research stage %s", (code, label) => {
  const view = fixture();
  view.items[0].tracking_status = code;
  expect(render(view)).toContain(">" + label + "</strong>");
});
it.each([
  ["VERIFY_MISSING_FACTS", "核验尚缺的事实资料"],
  [
    "VERIFY_MISSING_SAME_PERIOD_FACTS_AND_DEBT_NOTE_CLASSIFICATIONS",
    "补核同一报告期缺失事实及债务附注分类",
  ],
  ["RETAIN_CURRENT_RESEARCH_GATES", "继续遵守现有研究门槛，不自动升级准入"],
  [
    "REOPEN_WHEN_SOURCE_OR_SCOPE_EVIDENCE_CHANGES_NO_AUTOMATIC_RETRY",
    "待来源或口径证据变化后重新复核，不自动重试",
  ],
  [
    "BOUNDED_RETRY_MAX_THREE_ATTEMPTS_WITH_BACKOFF",
    "按退避间隔有界重试，最多三次尝试",
  ],
  ["TEST_ONLY_UNKNOWN_ACTION", "TEST_ONLY_UNKNOWN_ACTION"],
  ["进入经营与反证研究", "进入经营与反证研究"],
])("explains native next action without guessing: %s", (code, label) => {
  const view = fixture();
  view.items[0].next_action = code;
  const html = render(view);
  expect(html).toContain("下一动作：" + label + "</p>");
  expect(html).toContain('title="' + code + '"');
});

it("distinguishes obtained source observations from admitted facts", () => {
  const view = fixture();
  view.items[0].observed_fields = 8;
  expect(validTrackingPoolView(view)).toBe(true);
  const html = render(view);
  expect(html).toContain("已取得来源观察");
  expect(html).toContain("已采纳字段");
  view.items[0].observed_fields = 10;
  expect(validTrackingPoolView(view)).toBe(false);
  view.items[0].observed_fields = -1;
  expect(validTrackingPoolView(view)).toBe(false);
});
