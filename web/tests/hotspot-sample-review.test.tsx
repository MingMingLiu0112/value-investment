import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import {
  HotspotSampleReview,
  HotspotSampleLookup,
  loadHotspotSample,
} from "../src/components/HotspotSampleReview";
import type { HotspotSampleReview as Sample } from "../src/types/api";
const base: Sample = {
  schema_version: "hotspot-symbol-retained-replay-v1",
  symbol: "300059",
  status: "COVERED",
  action: "no_order",
  formal_eligibility: false,
  strategy_validation: "NOT_PROVEN",
  trade_count: null,
  namespace: "ACTUAL",
  source_integrity: "VERIFIED",
  limitations: ["历史可得性未证明"],
  events: [],
};
const html = (sample: Sample, symbol = "300059") =>
  renderToStaticMarkup(<HotspotSampleReview sample={sample} symbol={symbol} />);

it("shows no coverage or unavailable without borrowing evidence", () => {
  expect(html({ ...base, status: "NOT_COVERED" })).toContain("NOT_COVERED");
  expect(html({ ...base, status: "UNAVAILABLE" })).toContain(
    "原候选观察仍可查看",
  );
  expect(html(base, "600150")).not.toContain("查看全部");
  expect(html({ ...base, namespace: "TEST_ONLY" as "ACTUAL" })).not.toContain(
    "查看全部",
  );
});

it("shows event inputs, censored followup, invalidation and unknown execution separately", () => {
  const value = html({
    ...base,
    rule_version: "hotspot-prior-five-completed-bars-v1",
    partitions: {
      start_date: "2026-04-13",
      development_end: "2026-06-30",
      validation_start: "2026-07-01",
      end_date: "2026-10-15",
    },
    execution_unassessable_reasons: ["DATED_COST_AND_SLIPPAGE_BASIS"],
    events: [
      {
        segment: "validation",
        cutoff: "2026-10-14 14:00:00",
        signal_state: "TRIGGER_OBSERVED",
        levels: { entry_trigger_price: "22.5", invalidation_price: "21.2" },
        completed_context: { daily: { reference_close: "22" } },
        outcome: {
          horizon_complete: false,
          observed_followup_sessions: 1,
          last_observed_bar: "2026-10-15 15:00:00",
          right_censored: true,
          first_invalidation_observed_at: "2026-10-15 10:30:00",
          failed_within_five_sessions: null,
          false_breakout_next_session_proxy: true,
          next_session_close_change_pct: "-1.2",
          fifth_session_close_change_pct: null,
          adverse_excursion_from_signal_close_pct: null,
          execution: { fill: null },
        },
      },
    ],
  });
  for (const text of [
    "hotspot-prior-five-completed-bars-v1",
    "2026-10-14 14:00:00",
    "22.5",
    "21.2",
    "2026-10-15 10:30:00",
    "右删失",
    "五日失效代理：不可评",
    "真实退出与净收益不可评",
    "缺少历史费用与滑点依据",
    "不是交易收益",
  ]) {
    expect(value).toContain(text);
  }
});

it("renders structured failure without echoing raw diagnostic paths", () => {
  const value = html({
    ...base,
    status: "UNAVAILABLE",
    reason_code: "HASH_MISMATCH",
    reason: "D:/private/user/source.json",
  });
  expect(value).toContain("HASH_MISMATCH");
  expect(value).toContain("哈希与绑定不一致");
  expect(value).toContain("原候选观察仍可查看");
  expect(value).not.toContain("D:/private");
  expect(value).not.toContain("查看全部");
});

it("opens only the requested symbol and has no eager sample request", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => base });
  vi.stubGlobal("fetch", fetcher);
  try {
    const markup = renderToStaticMarkup(<HotspotSampleLookup />);
    expect(fetcher).not.toHaveBeenCalled();
    expect(markup).toContain("/api/v1/hotspot-replay-review?symbol=300059");
    expect(markup).toContain("不会加入候选池");
    await loadHotspotSample("300059");
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/hotspot-replay-review?symbol=300059",
    );
    await expect(loadHotspotSample("600150")).rejects.toThrow(
      "样本响应不可核验",
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

it("displays rule prose and never equates censored absence with success", () => {
  const text = html({
    ...base,
    rule_definition: {
      source_functions: [],
      entry: "严格高于此前5根最高价且成交量至少1.2倍",
      invalidation: "收盘严格低于冻结失效价",
      context: "其他周期仅为背景",
      followup: "分段随访",
      censoring: "右删失不计作成功",
      exit: "实际EXIT不可评",
    },
    events: [
      {
        segment: "validation",
        cutoff: "2026-10-15 14:00:00",
        signal_state: "TRIGGER_OBSERVED",
        levels: {},
        completed_context: {},
        outcome: {
          horizon_complete: false,
          observed_followup_sessions: 0,
          last_observed_bar: null,
          right_censored: true,
          first_invalidation_observed_at: null,
          failed_within_five_sessions: null,
          false_breakout_next_session_proxy: null,
          next_session_close_change_pct: null,
          fifth_session_close_change_pct: null,
          adverse_excursion_from_signal_close_pct: null,
          execution: {},
        },
      },
    ],
  });
  expect(text).toContain("1.2倍");
  expect(text).toContain("实际EXIT不可评");
  expect(text).toContain("后续失效未知，不计作成功");
  expect(text).not.toContain("观察窗口内未见");
});
