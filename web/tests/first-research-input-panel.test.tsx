import React from "react";
import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import type {
  FirstResearchInputResponse,
  FirstResearchScenarioKey,
} from "../src/services/api";

const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({ value: {} as any }));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state.value }));
import {
  FirstResearchInputPanel,
  FirstResearchInputView,
} from "../src/components/FirstResearchInputPanel";

function base(symbol = "000568"): FirstResearchInputResponse {
  return {
    symbol,
    status: "NOT_STARTED",
    scope: "CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
    action: "no_order",
    formal_eligibility: false,
    main_range_adopted: false,
    main_valuation_range: null,
    current_price: null,
    condition_price: null,
    personal_quantity: null,
  };
}
function example(): FirstResearchInputResponse {
  const ledger = () => ({
    funding_status: "FUNDED",
    rows10: Array.from({ length: 10 }, (_, index) => ({
      year: index + 1,
      profit: "10000000.00",
      distribution: "6000000.00",
      retained: "4000000.00",
    })),
  });
  return {
    ...base(),
    status: "SOURCE_BOUND_FIRST_INPUT_COMPILED",
    company_name: "TEST_ONLY泸州老窖",
    financial_basis: "2026-06-30",
    research_as_of: "2026-10-31",
    research_case: {
      symbol: "000568",
      name: "TEST_ONLY泸州老窖",
      thesis: "TEST_ONLY条件研究论点，不证明经济主区间",
      counter_evidence: [{ text: "TEST_ONLY渠道压力可能持续" }],
      thesis_breakers: [{ text: "TEST_ONLY经营与资本假设失效须重审" }],
      next_events: ["TEST_ONLY下一期官方披露再核验"],
    },
    annual_ledgers: { bear: ledger(), base: ledger(), bull: ledger() },
    valuation: {
      bear_value: "11.11",
      base_value: "22.22",
      bull_value: "33.33",
      confidence: "LOW",
      valuation_date: "2026-10-31",
    },
    source_bindings: [
      { path: "runtime/TEST_ONLY/first-spec.json", sha256: "a".repeat(64) },
    ],
    input_fingerprint: "b".repeat(64),
    native_fact_count: 30,
    sources: [
      {
        id: "TEST_ONLY_OFFICIAL",
        officialURL: "https://example.org/TEST_ONLY-official.pdf",
        sha256: "c".repeat(64),
      },
    ],
    operating_assumptions: {
      choice: { rationale: "TEST_ONLY共用压力假设理由" },
      scenarios: {
        bear: { rationale: "TEST_ONLY渠道压力持续理由" },
        base: { rationale: "TEST_ONLY逐步稳定理由" },
        bull: { rationale: "TEST_ONLY有条件修复理由" },
      },
    },
  };
}
function visibleHtml(html: string): string {
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
beforeEach(() => {
  state.value = { loading: false, error: undefined, retry: vi.fn() };
});

it.each(["600519", "600887"])(
  "leaves unregistered existing company %s completely invisible",
  (symbol) => {
    expect(FirstResearchInputView({ data: base(symbol), symbol })).toBeNull();
    state.value.data = base(symbol);
    expect(
      renderToStaticMarkup(<FirstResearchInputPanel symbol={symbol} />),
    ).toBe("");
  },
);

it("shows three conditional operating scenarios and annual profit/distribution without adopting a main range", () => {
  const data = example();
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  for (const text of [
    "渠道压力持续",
    "逐步稳定",
    "有条件修复",
    "TEST_ONLY渠道压力持续理由",
    "TEST_ONLY逐步稳定理由",
    "TEST_ONLY有条件修复理由",
    "2026-06-30",
    "2026-10-31",
    "TEST_ONLY渠道压力可能持续",
    "TEST_ONLY经营与资本假设失效须重审",
    "TEST_ONLY下一期官方披露再核验",
    "10,000,000.00",
    "6,000,000.00",
    "4,000,000.00",
    "REJECTED",
    "不比较当前报价",
    "不新增C第六家验收",
  ])
    expect(visible).toContain(text);
  for (const price of ["11.11", "22.22", "33.33"]) {
    expect(visible).not.toContain(price);
    expect(html).toContain(price);
  }
  expect(visible).not.toContain("base");
  expect(html).toContain("数学压力结果（非主估值区间、非买价）");
  expect(html).not.toContain("<details open");
  expect(html).not.toContain("已采用Base");
  expect(JSON.stringify(data)).toBe(before);
});

it("reads backend rows directly as well as rows10 without recalculating or filling a missing amount with zero", () => {
  const data = example();
  for (const name of ["bear", "base", "bull"] as FirstResearchScenarioKey[]) {
    const ledger = data.annual_ledgers![name];
    ledger.rows = ledger.rows10;
    delete ledger.rows10;
    delete ledger.rows![0].retained;
  }
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("年度利润、分配与留存摘要");
  expect(html).toContain("未提供");
  expect(html).not.toContain("停止展示");
});

it.each([
  { symbol: "600519" },
  { action: "order" },
  { formal_eligibility: true },
  { scope: "MAIN_RANGE" },
  { main_range_adopted: true },
  { main_valuation_range: { base: "100" } },
  { current_price: "90" },
  { condition_price: "80" },
  { personal_quantity: 100 },
])(
  "rejects changed issuer or price/adoption/quantity authority: %s",
  (patch) => {
    const data = {
      ...example(),
      ...patch,
    } as unknown as FirstResearchInputResponse;
    const html = renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    );
    expect(html).toContain("停止展示");
    expect(html).not.toContain("TEST_ONLY条件研究论点");
    expect(html).not.toContain("22.22");
  },
);

it("keeps an actual unassessable source failure visible rather than calling it not started or zero", () => {
  const data = {
    ...base(),
    status: "UNASSESSABLE",
    reason: "TEST_ONLY_SOURCE_HASH_MISMATCH",
  } as FirstResearchInputResponse;
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("暂不可核验");
  expect(html).toContain("TEST_ONLY_SOURCE_HASH_MISMATCH");
  expect(html).toContain("不代表未开始");
  expect(html).not.toContain("年度利润");
});

it("does not render an incomplete annual compilation as a successful range", () => {
  const data = example();
  data.annual_ledgers!.base.rows10 = [];
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain("年度来源绑定不完整");
  expect(html).not.toContain("22.22");
});

it("keeps loading invisible and read errors scoped to this panel", () => {
  state.value.loading = true;
  expect(
    renderToStaticMarkup(<FirstResearchInputPanel symbol="600519" />),
  ).toBe("");
  state.value = { loading: false, error: "TEST_ONLY_NETWORK", retry: vi.fn() };
  const html = renderToStaticMarkup(
    <FirstResearchInputPanel symbol="000568" />,
  );
  expect(html).toContain("读取失败");
  expect(html).toContain("重新读取首次研究输入");
});

it("only makes safe official source URLs clickable", () => {
  const data = example();
  let html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).toContain('href="https://example.org/TEST_ONLY-official.pdf"');
  data.sources = [{ id: "TEST_ONLY_BAD", officialURL: "javascript:alert(1)" }];
  html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  expect(html).not.toContain('href="javascript:');
});

it("places E2 next to C/D2 only in the existing non-hotspot value-company guard", () => {
  const page = readFileSync("src/pages/DecisionDetail/index.tsx", "utf8");
  const start = page.indexOf(
    '{strategy !== "hotspot" && /^[0-9]{6}$/.test(id) && (',
  );
  expect(start).toBeGreaterThan(-1);
  const guarded = page.slice(start, page.indexOf("<RemoteState", start));
  expect(guarded.indexOf("<CompanyProfilePanel")).toBeLessThan(
    guarded.indexOf("<OperatingAssumptionDraftPanel"),
  );
  expect(guarded.indexOf("<OperatingAssumptionDraftPanel")).toBeLessThan(
    guarded.indexOf("<FirstResearchInputPanel"),
  );
  expect(guarded).toContain(
    '<FirstResearchInputPanel key={"first-" + id} symbol={id}',
  );
  expect(page.match(/<FirstResearchInputPanel/g)).toHaveLength(1);
});

it("keeps actual terminal reasoning visible when the backend only provides a shared operating rationale", () => {
  const data = example();
  data.operating_assumptions = {
    choice: { rationale: "TEST_ONLY共用压力理由" },
    scenarios: {
      bear: { terminal_policy: { rationale: "TEST_ONLY压力持续终端理由" } },
      base: {
        terminal_policy: { rationale: "TEST_ONLY稳定仍有条件的终端理由" },
      },
      bull: {
        terminal_policy: { rationale: "TEST_ONLY修复未获批准的终端理由" },
      },
    },
  };
  const html = visibleHtml(
    renderToStaticMarkup(
      <FirstResearchInputView data={data} symbol="000568" />,
    ),
  );
  for (const reason of [
    "TEST_ONLY共用压力理由",
    "TEST_ONLY压力持续终端理由",
    "TEST_ONLY稳定仍有条件的终端理由",
    "TEST_ONLY修复未获批准的终端理由",
  ])
    expect(html).toContain(reason);
  expect(html).toContain("共用研究理由");
  expect(html).toContain("终端条件理由（假设）");
});

it("rounds grouped amounts for display while preserving exact raw ledger values and integer years", () => {
  const data = example();
  const rows = data.annual_ledgers!.bear.rows10!;
  rows[0].profit = "1234567.126789012345678901234567890123456789";
  rows[0].distribution = "-1234.56789";
  rows[0].retained = "not-a-number";
  rows[1].profit = "";
  rows[1].distribution = "Infinity";
  rows[1].retained = 0;
  const before = JSON.stringify(data);
  const html = renderToStaticMarkup(
    <FirstResearchInputView data={data} symbol="000568" />,
  );
  const visible = visibleHtml(html);
  expect(visible).toContain("1,234,567.13");
  expect(visible).toContain("-1,234.57");
  expect(visible).toContain("0.00");
  expect(visible).toContain("未提供");
  expect(visible).not.toContain("not-a-number");
  expect(visible).not.toContain("Infinity");
  expect(visible).not.toContain("1234567.126789");
  expect(visible).not.toContain("2,026.00");
  expect(visible).toContain("展示四舍五入至两位小数");
  expect(visible).toContain("原值见完整年度账本");
  expect(html).toContain("1234567.126789012345678901234567890123456789");
  expect(JSON.stringify(data)).toBe(before);
});
