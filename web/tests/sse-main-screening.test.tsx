import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ScreenPage } from "../src/components/SseMainScreeningPanel";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (node: React.ReactNode) => string;
};
const hooks = vi.hoisted(() => ({
  values: [] as any[],
  cursor: 0,
  response: {} as any,
  fetch: undefined as undefined | ((signal: AbortSignal) => Promise<any>),
}));
vi.mock("react", async (original) => {
  const actual = await original<typeof import("react")>();
  return {
    ...actual,
    useCallback: (fn: any) => fn,
    useState(initial: any) {
      const i = hooks.cursor++;
      if (!(i in hooks.values)) hooks.values[i] = initial;
      return [
        hooks.values[i],
        (next: any) => {
          hooks.values[i] =
            typeof next === "function" ? next(hooks.values[i]) : next;
        },
      ];
    },
  };
});
vi.mock("../src/hooks/useApi", () => ({
  useApi: (fetch: (signal: AbortSignal) => Promise<any>) => {
    hooks.fetch = fetch;
    return hooks.response;
  },
}));
import {
  SseMainScreeningPanel,
  validScreenPage,
} from "../src/components/SseMainScreeningPanel";

const load =
  vi.fn<
    (
      params: { offset: number; limit: number; query: string; status: string },
      signal: AbortSignal,
    ) => Promise<ScreenPage>
  >();
function fixture(): ScreenPage {
  return {
    schema_version: "sse-main-screening-v1",
    action: "no_order",
    status: "PARTIAL",
    scope: "SSE_MAIN_A_ONLY",
    quote_date: "2026-10-30",
    quote_date_verified: false,
    available_at: "2026-11-01T20:00:00+08:00",
    read_at: "2026-11-02T09:00:00+08:00",
    source_status: "RETAINED_OBSERVATIONS",
    coverage_complete: false,
    counts: { universe: 100, candidate: 25, excluded: 60, unassessable: 15 },
    pagination: { offset: 0, limit: 20, total: 25 },
    items: [
      {
        symbol: "600519",
        name: "TEST_ONLY Z公司",
        status: "CANDIDATE",
        channels: ["quality", "dividend_cash_return", "value", "cyclical"],
        reason: "TEST_ONLY 展示预算外PASS，保留实际后端入选",
        gaps: ["TEST_ONLY 财务字段缺口"],
        period: "2025-FY",
        updated_at: "2026-10-31",
        channel_evaluations: [
          {
            channel: "quality",
            status: "PASS",
            reason: "TEST_ONLY 四通道原生理由",
          },
        ],
        conditions: [
          {
            field: "debt_ratio",
            value: "0.25",
            unit: "ratio",
            status: "PASS",
            period: "2025-FY",
          },
        ],
      },
    ],
    blockers: ["TEST_ONLY 未覆盖来源"],
    rule_version: "TEST_ONLY_RULE",
    source_refs: [
      { path: "runtime/TEST_ONLY/source.json", sha256: "a".repeat(64) },
    ],
  };
}
function tree() {
  hooks.cursor = 0;
  return SseMainScreeningPanel({ load });
}
function show(
  page: ScreenPage,
  options: { loading?: boolean; error?: string; key?: string } = {},
) {
  const params = hooks.values[0] || {
    offset: 0,
    limit: 20,
    query: "",
    status: "CANDIDATE",
  };
  hooks.response = {
    data: { page, key: options.key ?? JSON.stringify(params), loader: load },
    loading: options.loading ?? false,
    error: options.error,
    retry: vi.fn(),
  };
  return tree();
}
function nodes(node: React.ReactNode): React.ReactElement<any>[] {
  if (!React.isValidElement(node)) return [];
  const item = node as React.ReactElement<any>;
  return [
    item,
    ...React.Children.toArray(item.props.children).flatMap((child) =>
      nodes(child),
    ),
  ];
}
function element(node: React.ReactNode, type: string, label: string) {
  const result = nodes(node).find(
    (n) =>
      n.type === type &&
      (n.props["aria-label"] === label || n.props.children === label),
  );
  if (!result) throw new Error("Missing " + label);
  return result;
}
beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  hooks.fetch = undefined;
  hooks.response = { loading: true, retry: vi.fn() };
  load.mockReset();
});
it("loads candidate defaults with abort signal and exact 20 row page", async () => {
  tree();
  load.mockResolvedValue(fixture());
  const controller = new AbortController();
  const result = await hooks.fetch!(controller.signal);
  expect(load).toHaveBeenCalledWith(
    { offset: 0, limit: 20, query: "", status: "CANDIDATE" },
    controller.signal,
  );
  expect(result.page).toEqual(fixture());
  expect(controller.signal.aborted).toBe(false);
});
it("shows native stock reasons, missing fields, dates, four channels and exact decision link", () => {
  const html = renderToStaticMarkup(show(fixture()));
  for (const value of [
    "TEST_ONLY Z公司",
    "展示预算外PASS",
    "财务字段缺口",
    "2025-FY",
    "2026-10-31",
    "质量",
    "现金分红回报",
    "价值",
    "周期",
    "行情日期未核验",
    "来源观察为 E1",
    "非正式财务事实",
    "初筛不是买入",
    "四通道原生理由",
    "0.25",
  ])
    expect(html).toContain(value);
  expect(html).toContain('href="/decisions/600519?strategy=value"');
  expect(html).toContain("<details>");
  expect(html).not.toContain("<details open");
});
it("keeps backend order and does not remove budget-excluded PASS or other returned statuses", () => {
  const page = fixture();
  page.items.push({
    ...page.items[0],
    symbol: "600887",
    name: "TEST_ONLY A公司",
    status: "UNASSESSABLE",
  });
  const html = renderToStaticMarkup(show(page));
  expect(html.indexOf("TEST_ONLY Z公司")).toBeLessThan(
    html.indexOf("TEST_ONLY A公司"),
  );
  expect(html).toContain("无法判断");
  expect(html).toContain("展示预算外PASS");
});
it("pagination sends next offset and search/status reset it without client filtering", async () => {
  let view = show(fixture());
  element(view, "button", "下一页").props.onClick();
  tree();
  load.mockResolvedValue({
    ...fixture(),
    pagination: { offset: 20, limit: 20, total: 25 },
  });
  await hooks.fetch!(new AbortController().signal);
  expect(load.mock.calls[load.mock.calls.length - 1]![0].offset).toBe(20);
  view = tree();
  element(view, "input", "搜索公司或代码").props.onChange({
    target: { value: "600887" },
  });
  view = tree();
  expect(hooks.values[0]).toEqual({
    offset: 0,
    limit: 20,
    query: "600887",
    status: "CANDIDATE",
  });
  for (const status of ["ALL", "EXCLUDED", "UNASSESSABLE", "CANDIDATE"]) {
    element(view, "select", "筛选状态").props.onChange({
      target: { value: status },
    });
    view = tree();
    expect(hooks.values[0].offset).toBe(0);
    expect(hooks.values[0].status).toBe(status);
  }
});
it.each([
  { loading: true },
  { error: "TEST_ONLY fresh failure" },
  { key: "previous query" },
])(
  "does not display retained success on new loading, failure or a different query: %j",
  (options) => {
    const html = renderToStaticMarkup(show(fixture(), options));
    expect(html).not.toContain("TEST_ONLY Z公司");
    expect(html).not.toContain("候选 25");
    expect(html).toMatch(/正在读取|来源读取失败/);
  },
);
it("distinguishes unavailable from an actual empty query without leaking candidate rows or zero counts", () => {
  const unavailable = renderToStaticMarkup(
    show({ ...fixture(), status: "UNAVAILABLE" }),
  );
  expect(unavailable).toContain("股票池未知，不是零候选");
  expect(unavailable).not.toContain("TEST_ONLY Z公司");
  expect(unavailable).not.toContain("候选 25");
  const zero = fixture();
  zero.items = [];
  zero.pagination.total = 0;
  zero.counts = { universe: 100, candidate: 0, excluded: 100, unassessable: 0 };
  const html = renderToStaticMarkup(show(zero));
  expect(html).toContain("当前来源与查询条件下为 0 条记录");
  expect(html).toContain("候选 0");
});
it("keeps null financial period and zero values distinct, handles unknown totals without pretending completeness", () => {
  const page = fixture();
  page.pagination.total = null;
  page.items[0].period = null;
  page.items[0].updated_at = null;
  page.items[0].conditions[0].value = 0;
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("财务期：未知");
  expect(html).toContain("更新时间：未知");
  expect(html).toContain("debt_ratio：0");
  expect(html).toContain("当前查询总数：未知");
  expect(element(show(page), "button", "下一页").props.disabled).toBe(true);
});
it.each([
  { scope: "ALL_A" },
  { action: "buy" },
  { schema_version: "other" },
  { items: [{ symbol: "javascript:evil" }] },
  { counts: { universe: -1 } },
])(
  "rejects invalid responses rather than showing fabricated pool: %j",
  async (patch) => {
    const page = { ...fixture(), ...patch } as unknown as ScreenPage;
    expect(validScreenPage(page)).toBe(false);
    load.mockResolvedValue(page);
    tree();
    await expect(hooks.fetch!(new AbortController().signal)).rejects.toThrow(
      "停止展示",
    );
  },
);
it("rejects response for a different page", async () => {
  load.mockResolvedValue({
    ...fixture(),
    pagination: { offset: 20, limit: 20, total: 25 },
  });
  tree();
  await expect(hooks.fetch!(new AbortController().signal)).rejects.toThrow(
    "分页不匹配",
  );
});

it("shows each channel's actual coverage, counts budget-limited passes and preserves other statuses", () => {
  const page = fixture();
  page.channel_counts = {
    quality: { DATA_GAP: 81, UNSUPPORTED: 19 },
    value: {
      PASS: 4,
      BUDGET_EXCLUDED: 3,
      REJECTED: 20,
      CONFLICT: 2,
      NOT_EVALUATED: 1,
    },
    dividend_cash_return: { PASS: 2 },
    cyclical: { UNSUPPORTED: 5, FUTURE_NATIVE_STATUS: 6 },
  };
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("逐通道初筛覆盖（不是研究完成度）");
  expect(html).toContain(
    '<th scope="row">质量</th><td>0</td><td>81</td><td>19</td>',
  );
  expect(html).toContain(
    '<th scope="row">价值</th><td>7</td><td>0</td><td>0</td>',
  );
  expect(html).toContain("未通过初筛：20");
  expect(html).toContain("资料冲突：2");
  expect(html).toContain("未评估：1");
  expect(html).toContain("FUTURE_NATIVE_STATUS：6");
  expect(html).toContain("各通道数量不可相加");
  expect(html).toContain("展示数量限制不会丢弃已通过初筛的公司");
});
it("keeps missing channel counts unknown and rejects malformed optional counts", () => {
  expect(validScreenPage(fixture())).toBe(true);
  expect(renderToStaticMarkup(show(fixture()))).toContain("来源未提供通道计数");
  const partial = fixture();
  partial.channel_counts = { value: { PASS: 2 } };
  expect(renderToStaticMarkup(show(partial))).toContain(
    '<th scope="row">质量</th><td>未提供</td><td>未提供</td><td>未提供</td>',
  );
  for (const bad of [
    null,
    [],
    { quality: [] },
    { quality: { PASS: -1 } },
    { quality: { PASS: "7" } },
  ]) {
    expect(validScreenPage({ ...fixture(), channel_counts: bad })).toBe(false);
  }
});
it("explains coverage as records rather than data completeness and puts known blocker codes in titles only", () => {
  const page = fixture();
  page.coverage_complete = true;
  page.blockers = [
    "INITIAL_SCREENING_NOT_BUY_ADVICE",
    "PROVIDER_FINANCIAL_NOT_OFFICIAL_ADMISSION",
    "QUOTE_TRADE_DATE_UNVERIFIED",
  ];
  const html = renderToStaticMarkup(show(page));
  const visible = html.replace(/<[^>]*>/g, "");
  expect(visible).toContain("官方名单范围均有初筛记录，不代表资料完整");
  expect(visible).toContain("供应商财务数据仅作观察");
  for (const code of page.blockers) {
    expect(html).toContain('title="' + code + '"');
    expect(visible).not.toContain(code);
  }
});
it("shows first two gaps by default, retaining remaining gaps in a closed disclosure", () => {
  const page = fixture();
  page.items[0].gaps = ["缺口一", "缺口二", "缺口三", "缺口四"];
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("<ul><li>缺口一</li><li>缺口二</li></ul>");
  expect(html).toContain(
    "<details><summary>其余缺口（2条）</summary><ul><li>缺口三</li><li>缺口四</li></ul></details>",
  );
});
it("uses short Chinese metric and observation status labels without changing numeric values", () => {
  const page = fixture();
  page.items[0].conditions = [
    {
      field: "roe_weighted",
      value: "12.3",
      unit: "%",
      status: "observed",
      period: null,
    },
    {
      field: "gross_margin",
      value: null,
      unit: "%",
      status: "missing",
      period: null,
    },
    {
      field: "total_revenue_yoy",
      value: "0",
      unit: "%",
      status: "conflicting",
      period: null,
    },
    {
      field: "parent_net_income_yoy",
      value: "-2",
      unit: "%",
      status: "observed",
      period: null,
    },
  ];
  page.items[0].channel_evaluations = [
    "REJECTED",
    "DATA_GAP",
    "CONFLICT",
    "UNSUPPORTED",
    "BUDGET_EXCLUDED",
  ].map((status) => ({
    channel: "quality",
    status,
    reason: "TEST_ONLY reason",
  }));
  const html = renderToStaticMarkup(show(page));
  for (const value of [
    "加权净资产收益率：12.3",
    "毛利率：未知",
    "营业收入同比：0",
    "归母净利润同比：-2",
    "来源观察",
    "缺失",
    "存在冲突",
    "未通过初筛",
    "缺资料",
    "资料冲突",
    "不适用",
    "已通过初筛（展示数量受限）",
  ])
    expect(html).toContain(value);
});
