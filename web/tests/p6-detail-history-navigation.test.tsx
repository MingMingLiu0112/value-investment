import React from "react";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({ data: {} as any }));
vi.mock("@umijs/max", () => ({
  useParams: () => ({ id: "600887" }),
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({ data: state.data, loading: false, error: null }),
}));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => ({
    kind: "LOCKED",
    label: "私人台账未解锁",
    detail: "实际成交未知",
  }),
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: any) => <main>{children}</main>,
}));
vi.mock("../src/components/RemoteState", () => ({
  RemoteState: ({ children }: any) => children,
}));
vi.mock("../src/components/CurrentJudgment", () => ({
  JudgmentSummary: () => <section>六项操作计划</section>,
  CurrentJudgmentChart: () => <section>当前图表</section>,
}));
vi.mock("../src/components/HotspotReplayReview", () => ({
  HotspotReplayReview: () => (
    <details>
      <summary>非实际成交历史信号检验</summary>
    </details>
  ),
}));
import DecisionDetail from "../src/pages/DecisionDetail";
import DecisionHistory from "../src/pages/DecisionHistory";

it.skipIf(!process.env.FUNDING_PUBLIC_API_JSON)(
  "renders the real source-bound issuer financing supplement",
  () => {
    const file = resolve(process.env.FUNDING_PUBLIC_API_JSON!);
    expect(relative(resolve(process.cwd(), "..", ".tmp"), file)).not.toMatch(
      /^(?:\.\.|[A-Za-z]:|[\\/])/,
    );
    const receipt = JSON.parse(
      readFileSync(resolve(dirname(file), "receipt.json"), "utf8"),
    );
    expect(receipt.status).toBe("PASS");
    expect(receipt.scope).toBe("ACTUAL_PUBLIC_HTTP_TESTCLIENT_NOT_LIVE_8001");
    const raw = readFileSync(file);
    expect(createHash("sha256").update(raw).digest("hex")).toBe(
      receipt.results["600519"].sha256,
    );
    state.data = JSON.parse(raw.toString("utf8"));
    try {
      const html = renderToStaticMarkup(<DecisionDetail />);
      for (const text of [
        "财务补证已回流研究",
        "金融融资范围仍需核验",
        "180.38",
        "原件第58页",
        "未采纳为完整债务",
      ])
        expect(html).toContain(text);
      expect(state.data.financial_progress.adopted_fact_count).toBe(2);
      expect(state.data.financial_progress.formal_eligibility).toBe(false);
    } finally {
      state.data = {};
    }
  },
);

it("links verified unchanged research replay to external review without admitting it", () => {
  state.data = {
    decision: { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
    review_replay: {
      status: "VERIFIED_EXACT_INPUT_REPLAY",
      symbol: "600887",
      action: "no_order",
      formal_eligibility: false,
      approval_changed: false,
      research_admitted: false,
      price_admitted: false,
      scope: "UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY",
      research_as_of: "2026-10-11",
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("原研究已按当前程序核验重放");
  expect(html).toContain("2026-10-11");
  expect(html).toContain("未获经济或买卖批准");
  expect(html).toContain('href="#value-review-handoff"');
  for (const mutation of [
    { symbol: "600519" },
    { formal_eligibility: true },
    { approval_changed: true },
    { research_admitted: true },
    { price_admitted: true },
  ]) {
    const original = state.data.review_replay;
    state.data.review_replay = { ...original, ...mutation };
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      "原研究已按当前程序核验重放",
    );
    state.data.review_replay = original;
  }
  state.data = {};
});

it("shows a new consumed input version as review material without borrowing approval", () => {
  state.data = {
    decision: { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
    review_replay: {
      status: "VERIFIED_NEW_INPUT_CANDIDATE",
      symbol: "600887",
      action: "no_order",
      formal_eligibility: false,
      approval_changed: false,
      research_admitted: false,
      price_admitted: false,
      scope: "UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY",
      research_as_of: "2026-10-21",
      valuation_basis_date: "2026-10-20",
      valuation_basis_scope: "EX_POST_PRIOR_COMPLETED_SESSION",
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("新来源版本已完成研究消费");
  expect(html).toContain("2026-10-20");
  expect(html).toContain("事后估计，不代表当前行情有效");
  expect(html).toContain("2026-10-21");
  expect(html).toContain("未获经济或买卖批准");
  expect(html).toContain('href="#value-review-handoff"');
  expect(html).not.toContain("原研究已按当前程序核验重放");
  state.data.review_replay.status = "SOURCE_UNAVAILABLE";
  const invalid = renderToStaticMarkup(<DecisionDetail />);
  expect(invalid).not.toContain("新来源版本已完成研究消费");
  expect(invalid).toContain("研究审核材料当前核验未通过");
  state.data = {};
});

it("shows verified financial input progress separately from economic approval", () => {
  state.data = {
    decision: { id: "600887", symbol: "600887", strategy: "CORE_VALUE" },
    financial_progress: {
      status: "VERIFIED_FACT_ADOPTION",
      action: "no_order",
      symbol: "600887",
      adopted_fact_count: 1,
      research_inputs_updated: true,
      quality_coverage_before: "0.5556",
      quality_coverage_after: "0.6667",
      formal_eligibility: false,
      adopted_metrics: [
        {
          field_name: "revenue_yoy",
          value: "-1.206",
          unit: "percent",
          period_label: "2025-12-31",
        },
        {
          field_name: "net_income_yoy",
          value: "-4.532",
          unit: "percent",
          period_label: "2025-12-31",
        },
        {
          field_name: "debt_ratio",
          value: "999",
          unit: "CNY",
          period_label: "2025-12-31",
        },
        {
          field_name: "net_income",
          value: "123456.78",
          unit: "CNY",
          period_label: "2025-12-31",
        },
        {
          field_name: "net_income",
          value: "87654321",
          unit: "percent",
          period_label: "2025-12-31",
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).toContain("财务补证已回流研究");
  expect(html).toContain("55.6");
  expect(html).toContain("66.7");
  expect(html).toContain("投资资格仍独立核验");
  expect(html).toContain("营业收入同比");
  expect(html).toContain("-1.21");
  expect(html).toContain("归母净利润同比");
  expect(html).toContain("-4.53");
  expect(html).not.toContain("999.00");
  expect(html).toContain("123456.78");
  expect(html).toContain(" 元");
  expect(html).not.toContain("123456.78%");
  expect(html).not.toContain("87654321");
  for (const mutation of [
    { symbol: "600519" },
    { formal_eligibility: true },
    { adopted_fact_count: 0 },
    { quality_coverage_after: "" },
  ]) {
    const original = state.data.financial_progress;
    state.data.financial_progress = { ...original, ...mutation };
    expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
      "财务补证已回流研究",
    );
    state.data.financial_progress = original;
  }
});

it("separates observed financial funding from admitted growth and complete debt", () => {
  const observation = {
    field_name: "financial_deposits_and_interbank",
    value: "18038383776.30",
    period_label: "2025-12-31",
    unit: "CNY",
    currency: "CNY",
    statement_scope: "consolidated",
    page: 58,
    excerpt: "TEST_ONLY binding of deposit amount",
  };
  const funding = {
    status: "FINANCIAL_FUNDING_REVIEW_REQUIRED",
    symbol: "600519",
    period_label: "2025-12-31",
    action: "no_order",
    financial_fact_admitted: false,
    required_fields: [observation.field_name],
    unresolved_fields: [observation.field_name],
    observations: [observation],
    source_binding: {
      path: "runtime/TEST_ONLY/annual.pdf",
      sha256: "a".repeat(64),
      source_url:
        "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
      available_at: "2026-10-24T00:00:00+00:00",
    },
  };
  state.data = {
    decision: {
      id: "600519",
      symbol: "600519",
      strategy: "CORE_VALUE",
      research: {
        symbol: "600519",
        evidence_refs: [
          {
            id: "TEST_ONLY-official",
            path: funding.source_binding.path,
            sha256: funding.source_binding.sha256,
          },
        ],
      },
    },
    financial_progress: {
      status: "VERIFIED_FACT_ADOPTION",
      action: "no_order",
      symbol: "600519",
      adopted_fact_count: 2,
      research_inputs_updated: true,
      formal_eligibility: false,
      quality_coverage_before: "0",
      quality_coverage_after: "0.2222",
      source_financial_funding_scope: funding,
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  for (const text of [
    "金融融资范围仍需核验",
    "吸收存款及同业存放",
    "180.38",
    "未采纳为完整债务",
    "非本金拆分",
    "空白项目不等于零",
  ])
    expect(html).toContain(text);
  const cashContext = {
    schema_version: "funding-cash-research-observations-v1",
    symbol: "600519",
    period_label: funding.period_label,
    action: "no_order",
    financial_fact_admitted: false,
    formal_eligibility: false,
    source_binding: funding.source_binding,
    observations: [
      ["financial_deposits_and_interbank", "18038383776.30", "consolidated"],
      [
        "controlling_group_deposits",
        "8330698318.34",
        "financial_subsidiary_depositor",
      ],
      ["consolidated_cash_and_equivalents", "126425609447.72", "consolidated"],
      ["issuer_parent_cash_and_equivalents", "84730758118.65", "issuer_parent"],
    ].map(([field_name, value, statement_scope]) => ({
      ...observation,
      field_name,
      value,
      statement_scope,
      symbol: "600519",
      observation_id: `TEST_ONLY:${field_name}`,
      source_binding: funding.source_binding,
    })),
    derivations: [
      {
        field_name: "controlling_group_deposit_concentration",
        value: "0.46183174",
        unit: "ratio",
        symbol: "600519",
        period_label: funding.period_label,
        input_observation_ids: [
          "TEST_ONLY:controlling_group_deposits",
          "TEST_ONLY:financial_deposits_and_interbank",
        ],
        source_binding: funding.source_binding,
      },
    ],
  };
  state.data.financial_progress.source_financial_funding_scope = {
    ...funding,
    research_context: cashContext,
  };
  const cashHtml = renderToStaticMarkup(<DecisionDetail />);
  for (const text of [
    "46.18%",
    "上市公司母公司现金及现金等价物",
    "84,730,758,118.65",
    "126,425,609,447.72",
    "不可相加",
    "单期观察不代表跨期变化",
  ])
    expect(cashHtml).toContain(text);
  for (const fault of ["hash", "period", "scope", "ratioInputs"]) {
    const context = structuredClone(cashContext);
    if (fault === "hash")
      context.source_binding = {
        ...context.source_binding,
        sha256: "b".repeat(64),
      };
    else if (fault === "period") context.period_label = "2026-06-30";
    else if (fault === "scope")
      context.observations[3].statement_scope = "consolidated";
    else context.derivations[0].input_observation_ids = ["forged", "forged"];
    state.data.financial_progress.source_financial_funding_scope = {
      ...funding,
      research_context: context,
    };
    const rejected = renderToStaticMarkup(<DecisionDetail />);
    if (fault === "scope") expect(rejected).not.toContain("84,730,758,118.65");
    else expect(rejected).not.toContain("46.18%");
  }
  for (const fault of [
    "company",
    "amount",
    "date",
    "hash",
    "validWrongHash",
    "scope",
  ]) {
    const invalid = structuredClone(funding);
    if (fault === "company") invalid.symbol = "600887";
    else if (fault === "amount") invalid.observations[0].value = "NaN";
    else if (fault === "date")
      invalid.observations[0].period_label = "2026-06-30";
    else if (fault === "hash") invalid.source_binding.sha256 = "invalid";
    else if (fault === "validWrongHash")
      invalid.source_binding.sha256 = "b".repeat(64);
    else invalid.observations[0].statement_scope = "parent";
    state.data.financial_progress.source_financial_funding_scope = invalid;
    const rejected = renderToStaticMarkup(<DecisionDetail />);
    expect(rejected).not.toContain("180.38");
    expect(rejected).toContain("不能据此认定没有该项义务");
  }
  state.data.financial_progress.source_financial_funding_scope = {
    ...funding,
    unresolved_fields: [],
  };
  expect(renderToStaticMarkup(<DecisionDetail />)).not.toContain(
    "金融融资范围已显式分类",
  );
  state.data = {};
});

it("keeps research collapsed and trade navigation ahead of the current chart without autofilling execution prices", () => {
  state.data = {
    decision: {
      id: "hotspot-300364",
      symbol: "300364",
      name: "中文在线",
      strategy: "hotspot",
      price_action_plan: { research_version: "real-version" },
    },
  };
  const html = renderToStaticMarkup(<DecisionDetail />);
  expect(html.indexOf("六项操作计划")).toBeLessThan(
    html.indexOf("记录我的实际成交"),
  );
  expect(html.indexOf("记录我的实际成交")).toBeLessThan(
    html.indexOf("当前图表"),
  );
  expect(html).toContain("research_version=real-version");
  expect(html).not.toMatch(/(?:price|quantity)=/);
  expect(html).toContain("展开研究底稿、估值与历史资格核验");
  expect(html).not.toMatch(/<details[^>]*\bopen/);
});

it("prioritizes actual trades over research and proxy replay while a locked ledger stays unknown", () => {
  state.data = { items: [], counts: {} };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html.indexOf("我的实际成交与原判断版本")).toBeLessThan(
    html.indexOf("研究快照与判断变化"),
  );
  expect(html.indexOf("研究快照与判断变化")).toBeLessThan(
    html.indexOf("非实际成交历史信号检验"),
  );
  expect(html).toContain("实际成交未知");
  expect(html).not.toContain("无实际成交");
});

it("shows verified retained observation changes without upgrading trading permission", () => {
  state.data = {
    items: [],
    observation_changes: {
      status: "SOURCE_REVALIDATED",
      completed_session: "2026-10-20",
      items: [
        {
          symbol: "000333",
          transition: "continue",
          trend_strengthened: true,
          selected_today: false,
          market_trade_date: "2026-10-19",
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html).toContain("/decisions/hotspot-000333");
  expect(html).toContain("继续观察");
  expect(html).toContain("保留观察历史");
  expect(html).toContain("不代表交易批准");
  expect(html).toContain("趋势增强");
  state.data.observation_changes = { status: "UNAVAILABLE", items: [] };
  expect(renderToStaticMarkup(<DecisionHistory />)).toContain("不等于没有变化");
});

it("offers keyboard-accessible snapshot choices and keeps the selected audit collapsed", () => {
  state.data = {
    items: [
      {
        id: "600887",
        symbol: "600887",
        status: "RESEARCH_ONLY",
        latest_version_label: "真实研究版本",
        comparison: {},
        versions: [],
      },
    ],
    counts: {},
  };
  const html = renderToStaticMarkup(<DecisionHistory />);
  expect(html).toContain('role="button"');
  expect(html).toContain('tabindex="0"');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain("研究快照不等于实际执行");
  expect(html).toContain("展开所选研究的依据、版本与变化");
  expect(html).not.toMatch(/<details[^>]*\bopen/);
});

it("shows source-verified research judgment before account workflow only for the same publication", () => {
  state.data = {
    publication_id: "pub-current",
    publication: { publication_id: "pub-current" },
    company_statuses: {
      "600887": {
        decision_chain: {
          gaps: [],
          research_conclusion: {
            evidence_verified: true,
            summary: "压力情景不能作为可靠合理价",
          },
        },
      },
    },
    decision: { id: "600887", symbol: "600887", strategy: "value" },
  };
  let html = renderToStaticMarkup(<DecisionDetail />);
  expect(html.indexOf("压力情景不能作为可靠合理价")).toBeLessThan(
    html.indexOf("六项操作计划"),
  );
  state.data.publication.publication_id = "pub-old";
  html = renderToStaticMarkup(<DecisionDetail />);
  expect(html).not.toContain("压力情景不能作为可靠合理价");
});
