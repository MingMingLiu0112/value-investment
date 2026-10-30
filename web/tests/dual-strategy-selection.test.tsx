import React from "react";
import { expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state.value }));
vi.mock("../src/services/api", () => ({ api: { strategySelection: vi.fn() } }));
import {
  DualStrategySelection,
  valueChannelName,
  selectionPriceCondition,
  SwingWaitExplanation,
} from "../src/components/DualStrategySelection";
import type { SelectionRow } from "../src/types/selection";
import { readFileSync } from "node:fs";
const { renderToStaticMarkup } = require("react-dom/server");
it("shows both independent pools and keeps a dual-listed security in its strategy context", () => {
  state.value = {
    data: {
      value: {
        items: [{ symbol: "000001", company_name: "TEST_ONLY价值" }],
        coverage: { research_queue_count: 21 },
        pagination: { offset: 0, limit: 10, total: 21 },
      },
      hotspot: {
        items: [
          {
            symbol: "000001",
            name: "TEST_ONLY热点",
            selection_status: "PENDING_CONFIRMATION",
          },
        ],
        coverage: { candidate_pool: 1 },
        pagination: { offset: 0, limit: 10, total: 1 },
      },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("价值投资候选池");
  expect(html).toContain("热点波段候选池");
  expect(html).toContain("/decisions/000001?strategy=value");
  expect(html).toContain("/decisions/000001?strategy=hotspot");
  expect(html).toContain("21 家");
  expect(html).not.toContain("ant-radio-group");
});
it("a failed value lane does not hide a verified empty hotspot lane", () => {
  state.value = {
    data: {
      value: { items: [], status: "SOURCE_OR_SELECTION_UNAVAILABLE" },
      hotspot: {
        items: [],
        coverage: { candidate_pool: 0, evaluated: 0 },
        pagination: { total: 0, limit: 10, offset: 0 },
      },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("数量未知");
  expect(html).toContain("候选池 0 家");
  expect(html).toContain("暂无符合条件且来源可核验的研究候选");
});
it("places discovery before private controls and opens research before action template", () => {
  const daily = readFileSync("src/pages/DailyDecisions/index.tsx", "utf8");
  expect(daily.indexOf("<DualStrategySelection")).toBeLessThan(
    daily.indexOf('<nav className="daily-navigation"'),
  );
  const detail = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  expect(
    detail.indexOf("<ValueResearchAnalysis decision={decision}"),
  ).toBeLessThan(
    detail.indexOf("<JudgmentSummary\n              decision={decision}"),
  );
});
function waitRow(): SelectionRow {
  return {
    symbol: "TEST_ONLY",
    data_status: "CURRENT",
    selection_status: "PENDING_CONFIRMATION",
    decision_explanation: {
      state: "WAIT",
      action: "no_order",
      formal_eligibility: false,
      holding_action_eligibility: false,
      owned_entry_supplied: false,
      wait_reasons: [
        "PRIMARY_VOLUME_CONFIRMATION_NOT_MET",
        "NEXT_BAR_OR_PULLBACK_CONFIRMATION_NOT_OBSERVED",
        "INDEPENDENT_STRATEGY_ADMISSION_REVIEW_REQUIRED",
      ],
      rule_inputs: {
        daily_trend: "RANGE",
        primary_structure: "PRICE_ABOVE_VOLUME_PENDING",
        structural_distance_ratio: "1.234567",
        next_bar_confirmed: false,
        pullback_recovery_observed: false,
      },
    },
  };
}
it("explains the actual failed predicates without turning a watch case into a holding recommendation", () => {
  const html = renderToStaticMarkup(<SwingWaitExplanation row={waitRow()} />);
  for (const text of [
    "量能尚未达到原规则要求",
    "下一根完成K线",
    "独立策略验证",
    "1.234567",
    "不是预期收益",
    "不构成持仓加减仓或退出建议",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("PRIMARY_VOLUME_CONFIRMATION_NOT_MET");
});
it("does not display stale numeric conditions and distinguishes an excluded case", () => {
  const row = waitRow();
  row.data_status = "STALE";
  row.selection_status = "EXCLUDED";
  const html = renderToStaticMarkup(<SwingWaitExplanation row={row} />);
  expect(html).toContain("当前结构已排除");
  expect(html).not.toContain("1.234567");
});
it("rejects an explanation claiming ownership or holding authority", () => {
  const row = waitRow();
  (row.decision_explanation as any).owned_entry_supplied = true;
  const html = renderToStaticMarkup(<SwingWaitExplanation row={row} />);
  expect(html).toContain("无法核验");
  expect(html).not.toContain("1.234567");
});
it("renders only condition price and rule, never raw permission JSON", () => {
  expect(
    selectionPriceCondition({
      price: "42.450",
      rule: "完整60分钟收盘确认",
      formal_eligibility: false,
    }),
  ).toBe("42.450 元；完整60分钟收盘确认");
  expect(selectionPriceCondition(null)).toContain("尚未建立");
  expect(selectionPriceCondition({ price: "41.450" }, true)).toContain(
    "价格结构失效",
  );
});

it("does not show retained data as current during loading or error", () => {
  state.value = {
    loading: true,
    data: { value: { items: [{ symbol: "OLD" }] } },
  };
  let html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("正在核验");
  expect(html).not.toContain("OLD");
  state.value = { error: "failed", retry: vi.fn() };
  html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("未生成新结论");
});
it("does not call a lane failure zero candidates", () => {
  state.value = {
    data: {
      content_sha256: "a".repeat(64),
      value: {
        status: "SOURCE_OR_SELECTION_UNAVAILABLE",
        items: [],
        shortlist: [],
      },
      hotspot: { items: [] },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("无法核验，不代表零候选");
  expect(html).toContain("数量未知");
  expect(html).not.toContain("覆盖 0 家");
});
it("recognizes the actual value source failure envelope with empty coverage", () => {
  state.value = {
    data: {
      content_sha256: "a".repeat(64),
      value: {
        data_status: "SOURCE_REVALIDATION_FAILED",
        coverage: {},
        items: [],
        shortlist: [],
      },
      hotspot: { items: [] },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("数量未知");
  expect(html).not.toContain("覆盖 0 家");
});
it("distinguishes full coverage, bounded queue, observed facts and trade permission", () => {
  state.value = {
    data: {
      content_sha256: "a".repeat(64),
      value: {
        items: [
          {
            symbol: "600519",
            company_name: "贵州茅台",
            industry: "饮料",
            profile_status: "GENERAL_RESEARCH",
            observation_summary: {
              favorable: 4,
              unfavorable: 0,
              missing: 0,
              conflicting: 0,
            },
          },
        ],
        coverage: {
          universe_count: 5577,
          research_queue_count: 4977,
          observation_count: 50063,
          official_fact_admission_count: 0,
        },
        quote_date: "2026-10-22",
        data_status: "PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS",
        rule_version: "value-observation-research-priority-v1",
        blockers: [],
      },
      hotspot: { items: [] },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain("5577");
  expect(html).toContain("本页展示 1 家");
  expect(html).toContain("贵州茅台");
  expect(html).toContain("尚未成为官方核验事实");
  expect(html).toContain("适用估值");
  expect(html).toContain("供应商财务观察，非正式核验事实");
  expect(html).toContain("overflow-wrap:anywhere");
  expect(html).not.toContain("PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS");
  expect(html).toContain("/decisions/600519?strategy=value");
});

it.each([
  ["COLLECTION_FAILED", "本次全市场采集失败"],
  ["NOT_ATTEMPTED", "本次未进行全市场采集"],
  ["INCOMPLETE", "本次全市场刷新尚未完成"],
])("labels retained research separately from refresh %s", (status, message) => {
  state.value = {
    data: {
      content_sha256: "b".repeat(64),
      value: {
        items: [{ symbol: "600519", company_name: "贵州茅台" }],
        shortlist: [],
        coverage: { universe_count: 5577, observation_count: 50055 },
        snapshot_status: "RETAINED_DATED_RESEARCH",
        refresh_status: status,
        quote_date: "2026-10-23",
        available_at: "2026-10-23T12:30:22+00:00",
        latest_attempt: { finished_at: "2026-10-23T17:52:04+00:00" },
      },
      hotspot: { items: [] },
    },
  };
  const html = renderToStaticMarkup(<DualStrategySelection />);
  expect(html).toContain(message);
  expect(html).toContain("2026-10-23T12:30:22+00:00");
  expect(html).toContain("贵州茅台");
  expect(html).toContain("不提供买入或仓位资格");
  expect(html).toContain("热点波段候选池");
});

it("names value channels and keeps unknown identifiers visible", () => {
  expect(
    ["quality", "dividend_cash_return", "value", "cyclical"].map(
      valueChannelName,
    ),
  ).toEqual(["质量", "现金回报", "价值", "周期"]);
  expect(valueChannelName("future_channel")).toBe("future_channel");
});
it.each([false, true, undefined])(
  "does not present partial or unknown scope as all A: %s",
  (complete) => {
    state.value = {
      data: {
        value: {
          items: [],
          coverage: { universe_count: 5224 },
          ...(complete === undefined
            ? {}
            : {
                screening_scope: {
                  status: complete ? "COMPLETE" : "PARTIAL",
                  scope: "TEST_ONLY",
                  all_a_complete: complete,
                  covered_venues: ["SSE", "SZSE"],
                  failed_venues: complete ? [] : ["BSE"],
                },
              }),
        },
        hotspot: { items: [], coverage: { candidate_pool: 0 } },
      },
    };
    const html = renderToStaticMarkup(<DualStrategySelection />);
    if (complete === false) {
      expect(html).toContain("部分市场覆盖（非全 A）");
      expect(html).toContain("SSE、SZSE");
      expect(html).toContain("BSE");
    } else if (complete) expect(html).toContain("官方全 A 覆盖已核验");
    else expect(html).toContain("市场覆盖范围未核验");
    expect(html.includes("官方全 A 覆盖已核验")).toBe(complete === true);
    expect(html).toContain("ROIC、正常化盈利和分红持续性尚需独立研究");
  },
);
