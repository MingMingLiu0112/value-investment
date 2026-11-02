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
    "资料或核验未齐",
    "资料冲突",
    "不适用",
    "已通过初筛（展示数量受限）",
  ])
    expect(html).toContain(value);
});

function diagnostics(): NonNullable<
  ScreenPage["items"][number]["financial_data"]
> {
  return {
    required_count: 9,
    available_count: 8,
    missing_count: 1,
    verified_count: 2,
    fields: [
      {
        field: "revenue",
        label: "营业收入",
        status: "AVAILABLE_PENDING_VERIFICATION",
        value: "123.45",
        unit: "亿元",
        reason: "TEST_ONLY 已取得原始观察，尚待正式核验",
      },
      {
        field: "cashflow",
        label: "经营现金流",
        status: "MISSING",
        value: null,
        unit: "亿元",
        reason: "TEST_ONLY 原始字段尚未取得",
      },
      {
        field: "scope",
        label: "口径限定字段",
        status: "PARTIAL_SCOPE",
        value: "0",
        unit: "元",
        reason: "TEST_ONLY 只有部分报表范围",
      },
      {
        field: "equity",
        label: "净资产",
        status: "VERIFIED",
        value: "8",
        unit: "亿元",
        reason: "TEST_ONLY 已完成限定字段核验",
      },
      {
        field: "profit",
        label: "归母利润",
        status: "CONFLICT",
        value: "3",
        unit: "亿元",
        reason: "TEST_ONLY 来源之间存在差异",
      },
    ],
  };
}
it("distinguishes raw financial availability from missing originals and formal verification", () => {
  const page = fixture();
  page.items[0].financial_data = diagnostics();
  expect(validScreenPage(page)).toBe(true);
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("已取得8/9项；真正缺1项；已核验2项");
  for (const value of [
    "原始数据取得不等于通过正式事实准入",
    "已取得，待核验",
    "原始数据缺失",
    "口径/适用性受限",
    "字段已核验",
    "数据冲突待核验",
    "123.45",
    "只有部分报表范围",
  ])
    expect(html).toContain(value);
  expect(html).toContain("<td>未知 亿元</td>");
  expect(html).toContain("<td>0 元</td>");
  expect(html).toContain(
    "<details><summary>逐字段取得与核验状态（5项）</summary>",
  );
});
it.each([
  ["bank", "银行"],
  ["insurer", "保险"],
  ["broker", "证券"],
  ["financial_group", "金融机构"],
])(
  "uses %s specialist requirements rather than ordinary-company completion scores",
  (kind, label) => {
    const page = fixture();
    page.items[0].financial_data = diagnostics();
    page.items[0].applicability = {
      kind,
      label: label + "专用研究",
      reason: "TEST_ONLY 行业指标需单独核验",
      required_metrics: ["TEST_ONLY 专用指标甲", "TEST_ONLY 专用指标乙"],
      provisional: true,
    };
    expect(validScreenPage(page)).toBe(true);
    const html = renderToStaticMarkup(show(page));
    expect(html).toContain("需" + label + "专用指标");
    expect(html).toContain("普通企业方法不适用");
    expect(html).toContain("这不是公司不好或没有财报");
    expect(html).toContain("初步识别，待核验");
    expect(html).toContain("TEST_ONLY 专用指标甲");
    expect(html).not.toContain("已取得8/9项");
    expect(html).not.toContain("真正缺1项");
    expect(html).toContain("以下仅展示返回的原始字段");
  },
);
it("supports ordinary applicability and respects the backend denominator instead of hardcoding nine", () => {
  const page = fixture();
  page.items[0].financial_data = { ...diagnostics(), required_count: 12 };
  page.items[0].applicability = {
    kind: null,
    label: "普通企业",
    reason: "TEST_ONLY 普通企业范围",
    required_metrics: [],
    provisional: false,
  };
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("已取得8/12项");
  expect(html).not.toContain("初步识别，待核验");
  expect(html).not.toContain("需对应行业专用指标");
});
it("keeps absent diagnostics backward-compatible and missing counts unknown", () => {
  const page = fixture();
  expect(validScreenPage(page)).toBe(true);
  const old = renderToStaticMarkup(show(page));
  expect(old).not.toContain("已取得0/");
  expect(old).not.toContain("逐字段取得与核验状态");
  page.items[0].applicability = {
    kind: "bank",
    label: "银行",
    reason: "TEST_ONLY",
    required_metrics: [],
    provisional: true,
  };
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("数量未知");
  expect(html).toContain("未提供具体专用指标清单");
  expect(html).not.toContain("已核验0项");
});
it.each([
  "null_data",
  "negative",
  "missing_count",
  "unknown_status",
  "numeric_value",
  "bad_applicability",
])("rejects malformed optional diagnostic contract: %s", (damage) => {
  const page = fixture();
  const row = page.items[0] as any;
  row.financial_data = diagnostics();
  if (damage === "null_data") row.financial_data = null;
  if (damage === "negative") row.financial_data.available_count = -1;
  if (damage === "missing_count") delete row.financial_data.verified_count;
  if (damage === "unknown_status")
    row.financial_data.fields[0].status = "APPROVED";
  if (damage === "numeric_value") row.financial_data.fields[0].value = 0;
  if (damage === "bad_applicability")
    row.applicability = {
      kind: "bank",
      label: "银行",
      reason: "",
      required_metrics: "not-a-list",
      provisional: true,
    };
  expect(validScreenPage(page)).toBe(false);
});

it("does not conflate DATA_GAP with missing originals or unsupported methods with company quality", () => {
  const page = fixture();
  page.channel_counts = { quality: { DATA_GAP: 100, UNSUPPORTED: 3 } };
  page.items[0].financial_data = diagnostics();
  page.items[0].channel_evaluations = [
    { channel: "quality", status: "DATA_GAP", reason: "TEST_ONLY 等待核验" },
    { channel: "quality", status: "UNSUPPORTED", reason: "TEST_ONLY 专用指标" },
  ];
  const visible = renderToStaticMarkup(show(page)).replace(/<[^>]*>/g, "");
  expect(visible).toContain("资料或核验未齐不等于原始数据缺失");
  expect(visible).toContain("金融机构需要金融专用指标");
  expect(visible).toContain("普通企业方法不适用，不是公司不好");
  expect(visible).toContain("已取得，待核验");
  expect(visible).toContain("原始数据缺失");
  expect(visible).toContain("口径/适用性受限");
  expect(visible).toContain("已取得8/9项；真正缺1项；已核验2项");
  expect(visible).not.toContain("缺资料");
});

function crosscheck(): NonNullable<
  ScreenPage["items"][number]["financial_crosscheck"]
> {
  return {
    matched_count: 2,
    conflict_count: 1,
    assurance: "E1_TWO_PROVIDER_COMPARISON_NOT_OFFICIAL_ADMISSION",
    fields: [
      {
        field: "cash",
        label: "现金",
        status: "MATCHED",
        primary_value: "100.00",
        secondary_value: "100.00",
        unit: "元",
        reason: "TEST_ONLY 同期同口径数值一致",
      },
      {
        field: "ratio",
        label: "负债率",
        status: "MATCHED",
        primary_value: "0",
        secondary_value: "0",
        unit: "%",
        reason: "TEST_ONLY 原始零值",
      },
      {
        field: "net_profit",
        label: "净利润",
        status: "CONFLICT",
        primary_value: "25.30",
        secondary_value: "25.31",
        unit: "元",
        reason: "TEST_ONLY 两源数值不同",
      },
      {
        field: "cashflow",
        label: "经营现金流",
        status: "ONE_SOURCE_ONLY",
        primary_value: "10",
        secondary_value: null,
        unit: "元",
        reason: "TEST_ONLY 第二来源未取得",
      },
      {
        field: "margin",
        label: "利润率",
        status: "NOT_COMPARABLE",
        primary_value: null,
        secondary_value: null,
        unit: "%",
        reason: "TEST_ONLY 非正分母口径不可比",
      },
    ],
  };
}
function debt(): NonNullable<ScreenPage["items"][number]["debt_details"]> {
  return {
    identified_total: "123.456789",
    complete_debt_verified: false,
    reason: "TEST_ONLY 已识别项目范围有限，应付债券尚未取得",
    components: [
      {
        field: "loan",
        label: "借款",
        value: "120.456789",
        unit: "元",
        status: "AVAILABLE_PENDING_VERIFICATION",
        reason: "TEST_ONLY 原始观察待核验",
      },
      {
        field: "lease",
        label: "租赁负债",
        value: "3",
        unit: "元",
        status: "PARTIAL_SCOPE",
        reason: "TEST_ONLY 只有已返回口径",
      },
      {
        field: "bond",
        label: "应付债券",
        value: null,
        unit: "元",
        status: "MISSING",
        reason: "TEST_ONLY 真实缺项",
      },
    ],
  };
}
it("renders actual comparable count, conflict, incomplete comparison and raw provider differences without admission", () => {
  const page = fixture();
  page.items[0].financial_crosscheck = crosscheck();
  expect(validScreenPage(page)).toBe(true);
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("已完成实际双源比对3项；冲突1项（一致2项）");
  expect(html).toContain("仅取得一源1项；口径不可比1项");
  expect(html).toContain("一致不等于正式核验或官方事实准入");
  expect(html).toContain("更不是买入依据");
  expect(html).toContain("<details><summary>双源原始值与差异（5项）</summary>");
  for (const value of [
    "100.00",
    "25.30",
    "25.31",
    "两源冲突",
    "仅取得一源",
    "口径不具可比性",
    "第二来源未取得",
    "非正分母口径不可比",
    "不升级已有正式事实核验状态",
  ])
    expect(html).toContain(value);
  expect(html).toContain("<td>0 %</td>");
  expect(html).toContain("<td>未知 元</td>");
});
it("shows identified debt exactly, keeps missing components accessible and never claims complete debt", () => {
  const page = fixture();
  page.items[0].debt_details = debt();
  expect(validScreenPage(page)).toBe(true);
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("已识别借款、租赁等金额：123.456789");
  expect(html).toContain("不是完整有息负债");
  expect(html).toContain("完整有息负债尚未核验");
  expect(html).toContain("应付债券尚未取得");
  expect(html).toContain(
    "<details><summary>债务项目与识别范围（3项）</summary>",
  );
  expect(html).toContain("120.456789");
  expect(html).toContain("真实缺项");
  expect(html).toContain("<td>未知 元</td>");
  expect(html).toContain("单位及来源口径");
});
it("supports old responses and keeps unknown identified debt unknown rather than zero", () => {
  const page = fixture();
  expect(validScreenPage(page)).toBe(true);
  expect(renderToStaticMarkup(show(page))).not.toContain("已完成实际双源比对");
  expect(renderToStaticMarkup(show(page))).not.toContain("已识别借款");
  page.items[0].debt_details = {
    ...debt(),
    identified_total: null,
    components: [],
  };
  const html = renderToStaticMarkup(show(page));
  expect(html).toContain("已识别借款、租赁等金额：未知");
  expect(html).toContain("未提供债务项目明细");
  expect(html).not.toContain("已识别借款、租赁等金额：0");
});
it.each([
  "null_comparison",
  "bad_assurance",
  "negative_count",
  "wrong_count",
  "unknown_comparison_status",
  "numeric_provider_value",
  "missing_reason",
  "null_debt",
  "debt_verified_true",
  "numeric_total",
  "numeric_component",
  "invalid_components",
  "missing_debt_scope",
])(
  "fails closed for malformed dual-source/debt response: %s",
  async (damage) => {
    const page = fixture();
    const row = page.items[0] as any;
    row.financial_crosscheck = crosscheck();
    row.debt_details = debt();
    if (damage === "null_comparison") row.financial_crosscheck = null;
    if (damage === "bad_assurance")
      row.financial_crosscheck.assurance = "OFFICIAL_ADMISSION";
    if (damage === "negative_count")
      row.financial_crosscheck.matched_count = -1;
    if (damage === "wrong_count") row.financial_crosscheck.conflict_count = 99;
    if (damage === "unknown_comparison_status")
      row.financial_crosscheck.fields[0].status = "VERIFIED";
    if (damage === "numeric_provider_value")
      row.financial_crosscheck.fields[0].primary_value = 100;
    if (damage === "missing_reason")
      delete row.financial_crosscheck.fields[0].reason;
    if (damage === "null_debt") row.debt_details = null;
    if (damage === "debt_verified_true")
      row.debt_details.complete_debt_verified = true;
    if (damage === "numeric_total") row.debt_details.identified_total = 123;
    if (damage === "numeric_component")
      row.debt_details.components[0].value = 0;
    if (damage === "invalid_components") row.debt_details.components = {};
    if (damage === "missing_debt_scope") delete row.debt_details.reason;
    expect(validScreenPage(page)).toBe(false);
    tree();
    load.mockResolvedValue(page);
    await expect(hooks.fetch!(new AbortController().signal)).rejects.toThrow(
      "停止展示",
    );
  },
);

function officialDebt() {
  return {
    ...debt(),
    official_evidence_count: 2,
    official_components: [
      {
        field: "short_loan",
        label: "TEST_ONLY 官方短借",
        value: "100",
        unit: "元",
        page: 39,
        excerpt: "TEST_ONLY 短期借款原文",
        source_url: "https://example.com/official.pdf",
        sha256: "a".repeat(64),
      },
      {
        field: "bond",
        label: "TEST_ONLY 官方债券",
        value: null,
        unit: "元",
        page: 40,
        excerpt: "TEST_ONLY 金额待核",
        source_url: "http://example.com/official.pdf",
        sha256: "b".repeat(64),
      },
    ],
  };
}
it("shows bound official notes separately without summing or replacing supplier debt", () => {
  const page = fixture();
  page.items[0].debt_details = officialDebt();
  expect(validScreenPage(page)).toBe(true);
  const html = renderToStaticMarkup(show(page));
  for (const value of [
    "已补2条官方附注构成",
    "原文第39页",
    "TEST_ONLY 短期借款原文",
    "原文第40页",
    "TEST_ONLY 金额待核",
    "未知 元",
    'href="https://example.com/official.pdf"',
    "123.456789",
    "不能相加或替代完整有息负债总额",
    "融资分类仍未完整核验",
  ])
    expect(html).toContain(value);
  expect(html).not.toContain("223.456789");
  expect(html.indexOf("官方附注构成")).toBeGreaterThan(
    html.indexOf("债务项目与识别范围"),
  );
});
it("keeps optional official count and rows unknown when omitted", () => {
  const page = fixture();
  page.items[0].debt_details = { ...debt(), official_evidence_count: 0 };
  expect(validScreenPage(page)).toBe(true);
  expect(renderToStaticMarkup(show(page))).toContain("不推定金额为零");
  page.items[0].debt_details = {
    ...debt(),
    official_components: officialDebt().official_components,
  };
  expect(validScreenPage(page)).toBe(true);
  expect(renderToStaticMarkup(show(page))).toContain("条数未提供");
  page.items[0].debt_details = debt();
  expect(renderToStaticMarkup(show(page))).not.toContain("官方附注构成");
});
it.each([
  "count",
  "null_rows",
  "page",
  "fractional_page",
  "value",
  "hash",
  "url",
  "excerpt",
])("rejects malformed official debt evidence: %s", async (damage) => {
  const page = fixture();
  const details: any = officialDebt();
  page.items[0].debt_details = details;
  if (damage === "count") details.official_evidence_count = "2";
  if (damage === "null_rows") details.official_components = null;
  if (damage === "page") details.official_components[0].page = 0;
  if (damage === "fractional_page") details.official_components[0].page = 1.5;
  if (damage === "value") details.official_components[0].value = 100;
  if (damage === "hash") details.official_components[0].sha256 = "bad";
  if (damage === "url")
    details.official_components[0].source_url = "javascript:alert(1)";
  if (damage === "excerpt") details.official_components[0].excerpt = null;
  expect(validScreenPage(page)).toBe(false);
  tree();
  load.mockResolvedValue(page);
  await expect(hooks.fetch!(new AbortController().signal)).rejects.toThrow(
    "停止展示",
  );
});
