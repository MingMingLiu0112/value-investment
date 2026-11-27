import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FundingContinuationPanel } from "../src/components/FundingContinuationPanel";
import subject from "../src/config/valueCloseEvidence.v1.json";

const { renderToStaticMarkup } = require("react-dom/server");

// Follow the hook harness used by the live operating research panel tests.
const hooks = vi.hoisted(() => ({ slots: [] as any[], cursor: 0 }));
vi.mock("react", async (load) => ({
  ...(await load<typeof import("react")>()),
  useState(initial: unknown) {
    const i = hooks.cursor++;
    if (!(i in hooks.slots)) hooks.slots[i] = initial;
    return [
      hooks.slots[i],
      (next: any) => {
        hooks.slots[i] =
          typeof next === "function" ? next(hooks.slots[i]) : next;
      },
    ];
  },
  useEffect(effect: () => void | (() => void), deps: unknown[]) {
    const i = hooks.cursor++;
    const last = hooks.slots[i];
    if (last && deps.every((x, n) => x === last.deps[n])) return;
    last?.cleanup?.();
    hooks.slots[i] = { deps, cleanup: effect() };
  },
}));

const props = {
  task: "rt-" + "a".repeat(32),
  receipt: subject.parent_receipt,
  symbol: subject.symbol,
};
const url =
  "/api/v1/operating-research/parent-cash-tasks/v3/" +
  props.task +
  "/funding-revisions/" +
  props.receipt +
  "/replay?symbol=" +
  props.symbol;
const versionUrl = url + "&version=maturity-v1";
const installmentUrl = url + "&version=installment-v1";
const multiyearUrl = url + "&version=multiyear-v1";
const hash = (ch: string) => ch.repeat(64);
const fetcher = vi.fn<(url: string, init: RequestInit) => Promise<Response>>();
const json = (body: object, status = 200) =>
  new Response(JSON.stringify({ action: "no_order", ...body }), { status });
const absent = () => json({ status: "CONTINUATION_NOT_SEALED" }, 404);
function reset() {
  for (const slot of hooks.slots) slot?.cleanup?.();
  hooks.slots = [];
  hooks.cursor = 0;
}
function nodes(x: unknown): React.ReactElement<any>[] {
  if (Array.isArray(x)) return x.flatMap(nodes);
  if (!React.isValidElement<any>(x)) return [];
  return [x, ...nodes(x.props.children)];
}
function mountPanel(input = props) {
  reset();
  const panel = () => {
    hooks.cursor = 0;
    return FundingContinuationPanel(input);
  };
  const root = panel();
  expect(nodes(root).filter((n) => typeof n.type === "function")).toHaveLength(
    0,
  );
  const target = { open: true };
  root.props.onToggle({ target, currentTarget: target });
  return nodes(panel()).filter(
    (n) => typeof n.type === "function" && n.props.task === input.task,
  );
}
function mountContent(version: boolean | "installment" | "multiyear") {
  const panels = mountPanel();
  const legacyType = panels.find(
    (panel) => panel.props.maturity === true,
  )!.type;
  const element = panels.find((panel) =>
    typeof version === "string"
      ? panel.type !== legacyType &&
        Boolean(panel.props.multiyear) === (version === "multiyear")
      : panel.type === legacyType && Boolean(panel.props.maturity) === version,
  );
  expect(element).toBeDefined();
  reset();
  return () => {
    hooks.cursor = 0;
    return (element!.type as React.FunctionComponent)(
      element!.props,
    ) as React.ReactElement;
  };
}
function click(view: React.ReactElement, label: string) {
  const b = nodes(view).find(
    (n) => n.type === "button" && n.props.children === label,
  );
  expect(b, label).toBeDefined();
  b!.props.onClick();
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
function receipt() {
  const year = 2032;
  const financing_rows = [
    {
      year,
      known_principal_cny: "200000000",
      opening_proxy_residual_cny: "300000000",
      assumed_proxy_repayment_cny: "150000000",
      closing_proxy_residual_cny: "150000000",
      new_borrowing_cny: "0",
      payment_status: "CALCULATED_CONDITIONAL",
      interest_cny: "14000000",
    },
  ];
  const ok = {
    status: "CALCULATED",
    first_failed_year: null,
    financing_rows_basis: "CONDITIONAL_PAYMENT_PLAN",
    per_share_value: "29.1234",
    financing_rows,
  };
  const fail = {
    status: "REJECTED",
    first_failed_year: year,
    financing_rows_basis: "CONDITIONAL_PAYMENT_PLAN",
    reason: "TEST_ONLY_CASH_FLOOR",
    financing_rows: [
      { ...financing_rows[0], payment_status: "NOT_COMPLETED" },
      { ...financing_rows[0], year: year + 1, payment_status: "NOT_REACHED" },
    ],
    ledger: {
      year,
      cash_before_distribution_cny: "500000000",
      floor_cny: "650000000",
      shortfall_cny: "150000000",
    },
  };
  return {
    status: "REPLAYED",
    task_id: props.task,
    receipt_sha256: props.receipt,
    symbol: props.symbol,
    continuation_version: "maturity-v1",
    action: "no_order",
    formal_eligibility: false,
    current_comparable: false,
    new_llm_calls: 0,
    completed_at: "2031-12-15",
    paid_task_status: "FAILED",
    continuation_sha256: hash("d"),
    valuation_date: "2031-12-01",
    reassessment_spec_sha256: hash("e"),
    maturity_recheck: {
      schema_version: "parent-cash-maturity-recheck-v1",
      task_id: props.task,
      parent_receipt: props.receipt,
      predecessor_input: hash("e"),
      symbol: props.symbol,
      valuation_date: "2031-12-01",
      action: "no_order",
      formal_eligibility: false,
      current_comparable: false,
      current_research_range_adopted: false,
      status: "REJECTED",
      scenario_basis: "FULL_PROXY_REPAYMENT_IN_BOUNDARY_YEAR",
      alternative_basis:
        "KNOWN_ONLY_THEN_FULL_PROXY_REPAYMENT_NEXT_YEAR_STRESS",
      scenarios: { bear: fail, base: ok, bull: ok },
      alternative_scenarios: { bear: ok, base: ok, bull: ok },
      maturity_evidence: {
        year,
        known_principal_cny: "200000000",
        proxy_residual_cny: "300000000",
        proxy_repayment_min_cny: "0",
        proxy_repayment_max_cny: "300000000",
        actual_unknown_maturity_cny: null as string | null,
        actual_total_principal_upper_cny: null as string | null,
        opening_reported_debt_cny: "400000000",
        reported_9m_borrowing_cny: "100000000",
        reported_9m_repayment_cny: "200000000",
        q3_carrying_basket_cny: "275000000",
        q3_basket_components_cny: {
          短借: "250000000",
          其他流动负债: "25000000",
        },
        proxy_minus_basket_cny: "25000000",
        q3_short_borrowing_cny: "250000000",
        short_borrowing_window_start: "2031-10-01",
        short_borrowing_window_end: "2032-09-30",
        registration_ceiling_cny: "1000000000",
        observed_issuance_cny: "350000000",
        assumed_future_borrowing_cny: "0",
        sources: {
          FY25: "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac",
          "9M26":
            "e165e6ee19441a1c0a59199991016bbf78098073981c469f3432e533cb3ce7a0",
          mtn: "edabd3c9460cc610c00b271f9b93b7c21badddfe33d9b3e3cd87afb90fca93e3",
        },
        zero_new_borrowing_from_year: year,
        first_year: year - 1,
        first_year_issue_proceeds_assumed_at_par_cny: "350000000",
        first_year_contractual_maturities_cny: "150000000",
        total_repayment_min_cny: "200000000",
        total_repayment_max_cny: "500000000",
        source_matrix_sha256: hash("a"),
      },
    },
  };
}
it("links only the matching issuer, source slot and PDF digest to each physical page", async () => {
  const match = receipt();
  const stale = receipt();
  stale.maturity_recheck.maturity_evidence.sources.FY25 = hash("9");
  stale.maturity_recheck.maturity_evidence.sources.mtn =
    match.maturity_recheck.maturity_evidence.sources["9M26"];
  fetcher.mockResolvedValueOnce(json(match)).mockResolvedValueOnce(json(stale));
  const render = mountContent(true);
  render();
  await settle();
  const html = renderToStaticMarkup(render());
  expect(html).toContain("静态链接目录");
  for (const [file, pages] of [
    ["2026-04-30/1225259562.PDF", [74, 75]],
    ["2026-10-30/1225644500.PDF", [12, 14]],
    ["2026-10-30/1225644498.PDF", [1]],
  ] as const) {
    for (const page of pages)
      expect(html).toContain(
        'href="https://static.cninfo.com.cn/finalpage/' +
          file +
          "#page=" +
          page +
          '"',
      );
  }
  click(render(), "刷新偿债期限历史");
  render();
  await settle();
  const refreshed = renderToStaticMarkup(render());
  expect(refreshed).toContain(hash("9"));
  expect(refreshed).not.toContain("1225259562.PDF");
  expect(refreshed).not.toContain("1225644498.PDF");
  expect(refreshed).toContain("1225644500.PDF#page=14");
  expect(html.match(/<summary>(悲观|基准|乐观) · /g)).toHaveLength(6);
});

it("renders the bound F2 snapshot's accounting reconciliation and constant-share assumption with their receipts", () => {
  const accounting = subject.ordinary_dividend_cash_reconciliation,
    market = subject.market_cap_continuity_check;
  const html = renderToStaticMarkup(FundingContinuationPanel(props));
  const amount = (v: string) =>
    Number(v).toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  expect(html).toContain("静态收盘证据快照");
  expect(subject.public_event_followup.length).toBeGreaterThanOrEqual(3);
  for (const { summary, source_url } of subject.public_event_followup) {
    expect(html).toContain(summary);
    expect(html).toContain('href="' + source_url + '"');
  }
  expect(subject.registered_shares).toBeNull();
  expect(subject.settled).toBeNull();
  expect(accounting.route_settlement_cny).toEqual({
    issuer_direct: null,
    china_clear_shanghai: null,
  });
  expect(subject.material_event_review).toMatchObject({
    complete_through: "2026-11-26",
    full_day_elapsed: true,
    cninfo_day_count: 0,
    sse_day_count: 0,
    matched_originals: 123,
    candidate_approved: 0,
  });
  expect(subject.gates.map(({ id, status }) => [id, status])).toEqual([
    ["quote", "PASS"],
    ["capital_structure", "BLOCKED"],
    ["distributions", "BLOCKED"],
    ["material_events", "BLOCKED"],
    ["financial_updates", "BLOCKED"],
  ]);
  expect(html).toContain("目录完整覆盖至 2026-11-26");
  expect(html).toContain(subject.report_sha256.slice(0, 12));
  for (const v of [
    accounting.period_end,
    amount(accounting.cash_decrease_cny),
    amount(accounting.minority_dividend_cash_paid_cny),
    amount(accounting.ordinary_share_cash_cny),
    accounting.source_url,
    accounting.receipt_sha256.slice(0, 12),
    market.from_date,
    market.through_date,
    market.sessions + " 个交易日",
    market.constant_total_shares.toLocaleString("zh-CN"),
    market.constant_float_shares.toLocaleString("zh-CN"),
    market.receipt_sha256.slice(0, 12),
    "两种口径差额 " + accounting.reconciliation_difference_cny + " 元",
    "公司自发 未核定",
    "代发 未核定",
    "尚缺本候选材料性批准 " +
      subject.material_event_review.without_candidate_approval +
      " 份",
    "财务报表勾稽",
    "仍需分渠道付款凭证",
    "恒定分母假设",
    "逐日登记股数仍待登记凭证核验",
  ])
    expect(html).toContain(v);
  const events = subject.material_event_review;
  if (events.full_day_elapsed) {
    expect(html).toContain("当日已结束。");
    expect(html).not.toContain("最早完整日复核时间");
    expect(html).not.toContain(events.earliest_full_day_recheck);
  } else {
    expect(html).toContain("当日尚未结束，最早完整日复核时间");
    expect(html).toContain(events.earliest_full_day_recheck);
    expect(html).not.toContain("当日已结束。");
  }
  expect(fetcher).not.toHaveBeenCalled();
});

beforeEach(() => {
  vi.stubGlobal("window", {
    location: { hash: "" },
    sessionStorage: { getItem: () => "TEST_ONLY_SESSION" },
  });
  fetcher.mockReset();
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => {
  reset();
  vi.unstubAllGlobals();
});

it("offers the versioned panel only for the bound receipt and symbol and keeps the fixed-payment panel", () => {
  const [fixed, installment, multiyear, maturity] = mountPanel();
  expect(mountPanel()).toHaveLength(4);
  expect(multiyear.type).toBe(installment.type);
  expect(multiyear.props.multiyear).toBe(true);
  expect(maturity.type).toBe(fixed.type);
  expect(maturity.props.maturity).toBe(true);
  expect(fixed.props.maturity).toBeUndefined();
  expect(installment.type).not.toBe(fixed.type);
  expect(installment.props).toEqual(props);
  for (const change of [{ symbol: "000001" }, { receipt: hash("b") }])
    expect(
      mountPanel({ ...props, ...change }).map((e) => [
        e.type,
        e.props.maturity,
      ]),
    ).toEqual([[fixed.type, undefined]]);
  expect(fetcher).not.toHaveBeenCalled();
});

it("loads, explicitly seals and refreshes the installment panel through its own authenticated endpoint", async () => {
  const { maturity_recheck: source, ...parent } = receipt();
  const fixed = {
    ...parent,
    continuation_version: "installment-v1",
    installment_recheck: {
      schema_version: "parent-cash-installment-recheck-v1",
      task_id: source.task_id,
      parent_receipt: source.parent_receipt,
      predecessor_input: source.predecessor_input,
      symbol: source.symbol,
      valuation_date: source.valuation_date,
      status: source.status,
      action: "no_order",
      formal_eligibility: false,
      current_comparable: false,
      current_research_range_adopted: false,
      base_basis: "TEST_ONLY 经营现金约束首笔分期",
      scenarios: source.scenarios,
    },
  };
  const refreshed = {
    ...fixed,
    continuation_sha256: hash("f"),
    installment_recheck: {
      ...fixed.installment_recheck,
      base_basis: "TEST_ONLY 刷新后复算依据",
    },
  };
  fetcher
    .mockResolvedValueOnce(absent())
    .mockResolvedValueOnce(json(fixed))
    .mockResolvedValueOnce(json(refreshed));
  const render = mountContent("installment");
  render();
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(renderToStaticMarkup(render())).toContain("按经营现金分期续算并封存");

  click(render(), "按经营现金分期续算并封存");
  await settle();
  const html = renderToStaticMarkup(render());
  for (const text of [
    "分期偿债研究",
    fixed.installment_recheck.base_basis,
    "2032 年资金约束未通过，距现金底线 1.50 亿元",
    "条件估值 29.1234 元/股",
    "期限未明本金假设偿还 1.50 亿元",
    fixed.continuation_sha256,
  ])
    expect(html).toContain(text);

  // The installment panel refreshes by mounting again, so it must read the seal.
  const reopened = mountContent("installment");
  reopened();
  await settle();
  const afterRefresh = renderToStaticMarkup(reopened());
  expect(afterRefresh).toContain(refreshed.continuation_sha256);
  expect(afterRefresh).toContain(refreshed.installment_recheck.base_basis);
  expect(afterRefresh).not.toContain(fixed.continuation_sha256);
  expect(afterRefresh).not.toContain("按经营现金分期续算并封存");
  expect(
    fetcher.mock.calls.map(([request, init]) => [
      request,
      init.method ?? "GET",
      init.body,
    ]),
  ).toEqual([
    [installmentUrl, "GET", undefined],
    [installmentUrl, "POST", "{}"],
    [installmentUrl, "GET", undefined],
  ]);
  for (const [, init] of fetcher.mock.calls) {
    expect(new Headers(init.headers).get("X-Local-Session")).toBe(
      "TEST_ONLY_SESSION",
    );
    expect(init.credentials).toBe("same-origin");
  }
});

it("GET, explicit POST, refresh and reopen use only the versioned authenticated replay", async () => {
  const first = receipt();
  const latest = receipt();
  latest.continuation_sha256 = hash("f");
  latest.maturity_recheck.maturity_evidence.actual_total_principal_upper_cny =
    "720000000";
  latest.maturity_recheck.maturity_evidence.actual_unknown_maturity_cny =
    "520000000";
  fetcher
    .mockResolvedValueOnce(absent())
    .mockResolvedValueOnce(json(first))
    .mockResolvedValueOnce(json(latest))
    .mockResolvedValueOnce(json(latest));
  const render = mountContent(true);
  render();
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);
  click(render(), "从已封存输入复算偿债期限");
  await settle();
  const html = renderToStaticMarkup(render());
  for (const s of [
    "2032 年偿债本金区间",
    "上限 未核定",
    "200,000,000",
    "池内条件还本合计 200,000,000 至 500,000,000",
    "300,000,000",
    "期初报告债务 400,000,000",
    "2032-09-30",
    "其他流动负债",
    "25,000,000",
    "2033 年偿清",
    "自2032年起假设零新增融资",
    "拒绝年度及之后列出的还本均为未获现金支持的计划，期末零不代表已还清",
    "支付未完成",
    "未执行",
    "悲观 · 已拒绝",
    "TEST_ONLY_CASH_FLOOR",
    "缺口 1.50",
    "29.1234",
    "当前研究区间未采用",
    hash("a"),
    first.continuation_sha256,
  ])
    expect(html).toContain(s);
  click(render(), "刷新偿债期限历史");
  render();
  await settle();
  expect(renderToStaticMarkup(render())).toContain("上限 720,000,000");
  const reopened = mountContent(true);
  reopened();
  await settle();
  expect(renderToStaticMarkup(reopened())).toContain(
    latest.continuation_sha256,
  );
  expect(
    fetcher.mock.calls.map(([u, init]) => [u, init.method ?? "GET", init.body]),
  ).toEqual([
    [versionUrl, "GET", undefined],
    [versionUrl, "POST", "{}"],
    [versionUrl, "GET", undefined],
    [versionUrl, "GET", undefined],
  ]);
  for (const [, init] of fetcher.mock.calls) {
    expect(new Headers(init.headers).get("X-Local-Session")).toBe(
      "TEST_ONLY_SESSION",
    );
    expect(init.credentials).toBe("same-origin");
  }
});

function multiyearReceipt() {
  const { maturity_recheck: source, ...parent } = receipt();
  const installments = source.scenarios.base.financing_rows[0];
  const plan = (end: number) => {
    const annual_rows = Array.from({ length: 10 }, (_, i) => ({
      year: 2026 + i,
      closing_cash_cny: "111000000",
      closing_debt_cny: "120000000",
    }));
    return {
      ...source.scenarios.base,
      annual_rows,
      financing_rows: annual_rows.slice(1).map(({ year }) => ({
        ...installments,
        year,
        assumed_proxy_repayment_cny: year <= end ? "1000000" : "0",
      })),
    };
  };
  const bear = plan(2034),
    base = plan(2033);
  const failed = {
    ...source.scenarios.bear,
    first_failed_year: 2028,
    reason: "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2028",
  };
  return {
    ...parent,
    continuation_version: "multiyear-v1",
    new_model_cost_cny: 0,
    multiyear_recheck: {
      ...source,
      status: "CALCULATED",
      schema_version: "parent-cash-multiyear-recheck-v1",
      base_basis: "TEST_ONLY 多年度条件",
      scenarios: { bear, base, bull: base },
      financing_condition_verified: false,
      unverified_financing_fallback_status: "REJECTED",
      original_installment_stress: { bear: failed, base, bull: base },
      early_maturity_stress: { bear: failed, base: failed, bull: failed },
    },
  };
}

it("replays and reopens multiyear with every year, cost, extension conditions and separate rejected stresses", async () => {
  const result = multiyearReceipt();
  fetcher
    .mockResolvedValueOnce(absent())
    .mockResolvedValueOnce(json(result))
    .mockResolvedValueOnce(json(result));
  const render = mountContent("multiyear");
  render();
  await settle();
  click(render(), "按多年经营现金续算并封存");
  await settle();
  const html = renderToStaticMarkup(render());
  for (const text of [
    "基准（Base）至 2033 年",
    "承压（Bear）至 2034 年",
    "连续展期条件",
    "展期条件未核实 · 提前到期回退结果已拒绝",
    "新增模型费用 0 元",
    "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2028",
    "距现金底线 1.50 亿元",
    "当前研究区间未采用",
    "602.15 亿元",
    "65e1b00158579b76.pdf#page=130",
    "1225511409.PDF#page=189",
    "P020260915489390859483.pdf#page=2",
  ])
    expect(html).toContain(text);
  for (let year = 2026; year <= 2035; year++)
    expect(html).toContain('<th scope="row">' + year + "</th>");
  const reopened = mountContent("multiyear");
  reopened();
  await settle();
  expect(renderToStaticMarkup(reopened())).toContain(
    result.continuation_sha256,
  );
  expect(
    fetcher.mock.calls.map(([path, init]) => [
      path,
      init.method ?? "GET",
      init.body,
    ]),
  ).toEqual([
    [multiyearUrl, "GET", undefined],
    [multiyearUrl, "POST", "{}"],
    [multiyearUrl, "GET", undefined],
  ]);
  for (const [, init] of fetcher.mock.calls) {
    expect(new Headers(init.headers).get("X-Local-Session")).toBe(
      "TEST_ONLY_SESSION",
    );
    expect(init.credentials).toBe("same-origin");
  }
});

it("shows a terminal principal rejection without inventing a cash shortfall", async () => {
  const result = multiyearReceipt();
  const terminal = {
    ...result.multiyear_recheck.original_installment_stress.bear,
    first_failed_year: 2036,
    reason: "MULTIYEAR_TERMINAL_PRINCIPAL_REMAINS",
    ledger: { remaining_proxy_principal_cny: "200000000" },
  };
  fetcher.mockResolvedValueOnce(
    json({
      ...result,
      multiyear_recheck: {
        ...result.multiyear_recheck,
        status: "REJECTED",
        scenarios: { ...result.multiyear_recheck.scenarios, base: terminal },
      },
    }),
  );
  const render = mountContent("multiyear");
  render();
  await settle();
  const html = renderToStaticMarkup(render());
  expect(html).toContain("MULTIYEAR_TERMINAL_PRINCIPAL_REMAINS");
  expect(html).toContain("终值前尚余本金 2.00 亿元");
  expect(html).not.toContain("NaN");
});

it.each(["schema", "cost", "parent", "wrong version", "stress missing"])(
  "fails closed for multiyear %s",
  async (fault) => {
    const record = multiyearReceipt();
    if (fault === "schema")
      record.multiyear_recheck.schema_version =
        "parent-cash-installment-recheck-v1";
    if (fault === "cost") record.new_model_cost_cny = 1;
    if (fault === "parent") record.multiyear_recheck.parent_receipt = hash("f");
    if (fault === "wrong version")
      record.continuation_version = "installment-v1";
    if (fault === "stress missing")
      Reflect.deleteProperty(
        record.multiyear_recheck,
        "original_installment_stress",
      );
    fetcher.mockResolvedValueOnce(json(record));
    const render = mountContent("multiyear");
    render();
    await settle();
    const html = renderToStaticMarkup(render());
    expect(html).toContain("无法核验");
    expect(html).not.toContain("条件估值");
    expect(fetcher).toHaveBeenCalledTimes(1);
  },
);

it("preserves the unversioned GET and POST", async () => {
  const fixed = {
    status: "REPLAYED",
    task_id: props.task,
    receipt_sha256: props.receipt,
    new_llm_calls: 0,
    continuation_sha256: hash("c"),
    fixed_payment_recheck: {
      status: "CALCULATED",
      predecessor_shortfall_cny: "0",
      source_payment: { through: "2032-01", paid_cny: "315" },
      scenarios: Object.fromEntries(
        ["bear", "base", "bull"].map((n) => [
          n,
          { status: "CALCULATED", per_share_value: "12.34" },
        ]),
      ),
    },
  };
  fetcher.mockResolvedValueOnce(absent()).mockResolvedValueOnce(json(fixed));
  const render = mountContent(false);
  render();
  await settle();
  click(render(), "从已封存阶段续跑 V3 现金复核");
  await settle();
  expect(renderToStaticMarkup(render())).toContain("315");
  expect(
    fetcher.mock.calls.map(([u, init]) => [u, init.method ?? "GET", init.body]),
  ).toEqual([
    [url, "GET", undefined],
    [url, "POST", "{}"],
  ]);
});

it.each([
  "wrong version",
  "wrong task",
  "wrong symbol",
  "wrong body binding",
  "missing body",
  "missing inputs",
])(
  "rejects %s on history read without a POST or stale figures",
  async (issue) => {
    const result = receipt();
    if (issue === "wrong version")
      result.continuation_version = "fixed-payment-v1";
    if (issue === "wrong task") result.task_id = "rt-other";
    if (issue === "wrong symbol") result.symbol = "000001";
    if (issue === "wrong body binding")
      result.maturity_recheck.predecessor_input = hash("f");
    if (issue === "missing body")
      Reflect.deleteProperty(result, "maturity_recheck");
    fetcher.mockResolvedValueOnce(
      issue === "missing inputs"
        ? json({ status: "CONTINUATION_INPUT_MISSING" }, 404)
        : json(result),
    );
    const render = mountContent(true);
    render();
    await settle();
    const html = renderToStaticMarkup(render());
    expect(html).toContain("无法核验");
    expect(html).not.toContain("复算偿债期限");
    expect(html).not.toContain("29.1234");
    expect(fetcher).toHaveBeenCalledTimes(1);
  },
);
it("recovers from a conflicting run by reading the newly sealed history", async () => {
  fetcher
    .mockResolvedValueOnce(absent())
    .mockResolvedValueOnce(json({ status: "CONTINUATION_IN_PROGRESS" }, 409))
    .mockResolvedValueOnce(json(receipt()));
  const render = mountContent(true);
  render();
  await settle();
  click(render(), "从已封存输入复算偿债期限");
  await settle();
  expect(renderToStaticMarkup(render())).toContain("同版本正在复算");
  click(render(), "刷新偿债期限历史");
  render();
  await settle();
  expect(renderToStaticMarkup(render())).toContain("当前研究区间未采用");
  expect(fetcher.mock.calls.map(([, init]) => init.method ?? "GET")).toEqual([
    "GET",
    "POST",
    "GET",
  ]);
});
