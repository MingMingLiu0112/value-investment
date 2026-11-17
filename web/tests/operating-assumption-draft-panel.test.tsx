import React from "react";
import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import type {
  OperatingAssumptionDraftResponse,
  OperatingAssumptionScenario,
} from "../src/services/api";

const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({
  value: {
    data: undefined,
    loading: false,
    error: undefined,
    retry: vi.fn(),
  } as any,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state.value }));
import {
  OperatingAssumptionDraftPanel,
  OperatingAssumptionDraftView,
} from "../src/components/OperatingAssumptionDraftPanel";

function scenario(): OperatingAssumptionScenario {
  return {
    drivers: { annual: ["TEST_ONLY_ANNUAL_DETAIL"] },
    operating_capital_path: Array.from({ length: 10 }, (_, index) => ({
      year: index + 1,
      operating_capital: "TEST_ONLY_RECOMPUTED_CAPITAL_YEAR_" + (index + 1),
    })),
    terminal_policy: { capital: "TEST_ONLY_TERMINAL_DETAIL" },
    cost_of_equity: "0.10",
    classification: "RESEARCH_ASSUMPTION",
    evidence_ref: {
      path: "config/TEST_ONLY-assumptions.json",
      sha256: "a".repeat(64),
      field_path: ["scenarios", "TEST_ONLY_BRANCH", "base"],
    },
  };
}
function example(): OperatingAssumptionDraftResponse {
  return {
    schema_version: "operating-assumption-draft-v1",
    symbol: "600519",
    status: "SOURCE_BOUND_D2_DRAFT",
    company_name: "TEST_ONLY公司",
    as_of: "2026-06-30",
    available_at: "2026-10-26T18:43:53+08:00",
    branches: [1, 2, 3].map((number) => ({
      branch_id: "TEST_ONLY_" + number,
      title: "研究分支" + number,
      economic_rationale: "TEST_ONLY经济理由" + number,
      proposal_rationale: "TEST_ONLY方案理由" + number,
      counter_evidence: [
        "TEST_ONLY关键反证" + number,
        "TEST_ONLY另一反例" + number,
      ],
      scenarios: { bear: scenario(), base: scenario(), bull: scenario() },
      classification: "ASSUMPTION",
      confidence: "LOW",
    })),
    historical_observations: [
      {
        field: "TEST_ONLY_HISTORY",
        value: "100",
        verification_status: "NOT_NORMALIZED_FORECAST",
      },
    ],
    unknowns: [
      {
        field: "normalized_parent_profit_cny",
        value: null,
        status: "UNKNOWN_NOT_ZERO",
      },
    ],
    invalidation_conditions: [
      "TEST_ONLY来源变化须重审",
      "TEST_ONLY经营路径反证出现",
    ],
    limitations: ["TEST_ONLY上划与终端资本约束未解决"],
    source_bindings: [
      { path: "config/TEST_ONLY-assumptions.json", sha256: "a".repeat(64) },
    ],
    input_fingerprint: "b".repeat(64),
    action: "no_order",
    formal_eligibility: false,
    valuation_computed: false,
    assumptions_approved: false,
    research_admitted: false,
    approval_changed: false,
    e2_new_company_compilation: false,
  };
}
function visibleText(value: any): string {
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (Array.isArray(value)) return value.map(visibleText).join("");
  if (!React.isValidElement(value) || value.type === "details") return "";
  return visibleText((value as any).props.children);
}
beforeEach(() => {
  state.value = {
    data: undefined,
    loading: false,
    error: undefined,
    retry: vi.fn(),
  };
});

it("shows dates, all three branch reasons, counterevidence and invalidation before closed annual details", () => {
  const data = example();
  const view = OperatingAssumptionDraftView({ data, symbol: "600519" });
  const visible = visibleText(view);
  for (const text of [
    "2026-06-30",
    "2026-10-26T18:43:53+08:00",
    "不调用新LLM",
    "不计算估值",
    "不审批",
    "D2不代表E2首次编译完成",
    "TEST_ONLY来源变化须重审",
    "TEST_ONLY上划与终端资本约束未解决",
  ])
    expect(visible).toContain(text);
  for (const number of [1, 2, 3])
    for (const prefix of [
      "研究分支",
      "TEST_ONLY经济理由",
      "TEST_ONLY方案理由",
      "TEST_ONLY关键反证",
      "TEST_ONLY另一反例",
    ])
      expect(visible).toContain(prefix + number);
  expect(visible).not.toContain("TEST_ONLY_ANNUAL_DETAIL");
  expect(visible).not.toContain("TEST_ONLY_TERMINAL_DETAIL");
  const html = renderToStaticMarkup(view);
  expect(html).toContain("TEST_ONLY_ANNUAL_DETAIL");
  expect(html).toContain("TEST_ONLY_TERMINAL_DETAIL");
  expect(html).toContain("情景字段来源绑定");
  expect(html).not.toContain("<details open");
  expect(html).toContain("草案输入指纹");
});

it("keeps unknown normalized earnings explicit without filling zero", () => {
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftView data={example()} symbol="600519" />,
  );
  expect(html).toContain("正常化归母利润");
  expect(html).toContain("未知（不填0）");
  expect(html).not.toContain("正常化归母利润：0");
});

it.each([
  { symbol: "600887" },
  { action: "order" },
  { formal_eligibility: true },
  { valuation_computed: true },
  { assumptions_approved: true },
  { e2_new_company_compilation: true },
])(
  "withdraws draft assumptions for mismatched issuer or changed authority: %s",
  (patch) => {
    const data = {
      ...example(),
      ...patch,
    } as unknown as OperatingAssumptionDraftResponse;
    const html = renderToStaticMarkup(
      <OperatingAssumptionDraftView data={data} symbol="600519" />,
    );
    expect(html).toContain("停止展示");
    expect(html).not.toContain("TEST_ONLY经济理由");
  },
);

it.each(["MISSING_SOURCE", "UNASSESSABLE"] as const)(
  "renders %s without inventing branches or numeric output",
  (status) => {
    const data = {
      ...example(),
      status,
      missing_sources: [
        { path: "runtime/TEST_ONLY-missing.json", sha256: null },
      ],
    };
    const html = renderToStaticMarkup(
      <OperatingAssumptionDraftView data={data} symbol="600519" />,
    );
    expect(html).toContain(
      status === "MISSING_SOURCE" ? "来源缺失" : "暂不可评估",
    );
    expect(html).toContain("runtime/TEST_ONLY-missing.json");
    expect(html).not.toContain("TEST_ONLY经济理由");
    expect(html).not.toContain("上调估值");
  },
);

it("stops an incomplete source-bound draft without fabricating scenario inputs", () => {
  const data = { ...example(), branches: [] };
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftView data={data} symbol="600519" />,
  );
  expect(html).toContain("分支或来源绑定不完整");
  expect(html).not.toContain("TEST_ONLY经济理由");
});

it("keeps loading and failed public reads local to D2 with an explicit retry", () => {
  state.value.loading = true;
  expect(
    renderToStaticMarkup(<OperatingAssumptionDraftPanel symbol="600519" />),
  ).toContain("正在读取D2");
  state.value = {
    data: undefined,
    loading: false,
    error: "TEST_ONLY_NETWORK",
    retry: vi.fn(),
  };
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftPanel symbol="600519" />,
  );
  expect(html).toContain("经营假设草案来源暂不可核验");
  expect(html).toContain("重新读取草案");
  expect(html).not.toContain("TEST_ONLY经济理由");
});

it("mounts D2 immediately after the profile only inside the existing non-hotspot public guard", () => {
  const detail = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  const start = detail.indexOf(
    '{strategy !== "hotspot" && /^[0-9]{6}$/.test(id) && (',
  );
  expect(start).toBeGreaterThan(-1);
  const guarded = detail.slice(start, detail.indexOf("<RemoteState", start));
  expect(guarded).toContain("<CompanyProfilePanel symbol={id}");
  expect(guarded).toContain(
    "<OperatingAssumptionDraftPanel key={id} symbol={id}",
  );
  expect(guarded.indexOf("<CompanyProfilePanel")).toBeLessThan(
    guarded.indexOf("<OperatingAssumptionDraftPanel"),
  );
  expect(detail.match(/<OperatingAssumptionDraftPanel/g)).toHaveLength(1);
});

function withoutClosedDetails(html: string): string {
  let depth = 0;
  return html
    .split(/(<\/?details\b[^>]*>)/)
    .map((part) => {
      if (/^<details\b/.test(part)) {
        depth++;
        return "";
      }
      if (/^<\/details\b/.test(part)) {
        depth--;
        return "";
      }
      return depth === 0 ? part : "";
    })
    .join("");
}

it("shows backend Chinese unknown reasons and translates unproven values while keeping technical fields collapsed", () => {
  const data = example();
  data.unknowns = [
    {
      field: "investment_income.after_tax_parent_adjustment_cny",
      value: null,
      status: "ECONOMIC_ATTRIBUTION_NOT_ESTABLISHED",
      reason:
        "单项税后归母归属、重复项或加回资格未证实；不表示情景没有税率或归属假设",
    },
    {
      field: "investment_income.recurrence",
      value: "NOT_ESTABLISHED",
      status: "RECURRENCE_NOT_ESTABLISHED",
      reason: "历史项目的持续性及情景稳定性未证实",
    },
    {
      field: "normalized_parent_profit_cny",
      value: null,
      status: "NORMALIZATION_NOT_ESTABLISHED",
      reason: "历史重算不等于正常化盈利或区间已被证明",
    },
  ];
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftView data={data} symbol="600519" />,
  );
  const visible = withoutClosedDetails(html);
  for (const item of data.unknowns as { reason: string }[])
    expect(visible).toContain(item.reason);
  expect(visible).toContain("尚未证明");
  expect(visible).not.toContain("NOT_ESTABLISHED");
  expect(visible).not.toContain(
    "investment_income.after_tax_parent_adjustment_cny",
  );
  expect(visible).not.toContain("investment_income.recurrence");
  expect(html).toContain("investment_income.after_tax_parent_adjustment_cny");
  expect(html).toContain("字段与状态明细");
  expect(visible).not.toContain("归属假设缺失");
});

it("keeps the backend's actual ten-year operating capital output in closed annual details alongside its drivers", () => {
  const data = example();
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftView data={data} symbol="600519" />,
  );
  expect(html).toContain("经营与资本路径（后端重算，非估值）");
  expect(html).toContain("TEST_ONLY_RECOMPUTED_CAPITAL_YEAR_10");
  expect(html).toContain("TEST_ONLY_ANNUAL_DETAIL");
  expect(withoutClosedDetails(html)).not.toContain(
    "TEST_ONLY_RECOMPUTED_CAPITAL_YEAR_",
  );
  expect(html).not.toContain("<details open");
  expect(JSON.stringify(data)).toBe(before);
});

it.each(["MISSING_SOURCE", "UNASSESSABLE"] as const)(
  "limits %s to existing packages without falling back to first compilation",
  (status) => {
    const data = {
      ...example(),
      symbol: "000568",
      status,
      missing_sources: [{ path: "TEST_ONLY-broken-source", sha256: null }],
    };
    const html = renderToStaticMarkup(
      <OperatingAssumptionDraftView data={data} symbol="000568" />,
    );
    expect(html).toContain("既有研究包");
    expect(html).toContain("TEST_ONLY-broken-source");
    expect(html).not.toContain("尚无可显示的来源绑定草案");
    if (status === "MISSING_SOURCE") {
      expect(html).toContain("请查看独立的首次条件压力研究区");
      expect(html).toContain("不以首编结果替代");
    } else {
      expect(html).toContain("来源异常须核验修复");
      expect(html).toContain("不以独立首编区结果替代");
      expect(html).not.toContain("请查看");
    }
    expect(html).not.toContain("TEST_ONLY经济理由");
  },
);

it("deduplicates only full JSON unknown items and preserves different fields, reasons and raw normalization items", () => {
  const data = example();
  const original = {
    field: "TEST_ONLY_FIELD_A",
    reason: "TEST_ONLY_SAME_REASON",
    status: "NOT_ESTABLISHED",
  };
  data.unknowns = [
    ...Array.from({ length: 100 }, () => ({ ...original })),
    { ...original, field: "TEST_ONLY_FIELD_B" },
    { ...original, reason: "TEST_ONLY_DIFFERENT_REASON" },
    { ...original, status: "UNKNOWN_NOT_ZERO" },
  ];
  data.normalization_open_items = data.unknowns;
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <OperatingAssumptionDraftView data={data} symbol="600519" />,
  );
  const unknownSection = html
    .split("<h4>未知与待补证</h4>")[1]
    .split("<h4>失效与重审条件</h4>")[0];
  expect(unknownSection).toContain("原 103 条，展示 4 条");
  expect(unknownSection).toContain("合并相同项99 条");
  expect((unknownSection.match(/<li>/g) || []).length).toBe(4);
  expect(unknownSection).toContain("TEST_ONLY_FIELD_A");
  expect(unknownSection).toContain("TEST_ONLY_FIELD_B");
  expect(unknownSection).toContain("TEST_ONLY_DIFFERENT_REASON");
  expect(html).toContain("正常化待解决事项");
  expect(JSON.stringify(data)).toBe(before);
});
