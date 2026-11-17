import React from "react";
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
  useLocation: () => ({ pathname: "/strategy/value" }),
}));
vi.mock("../src/components/LiveOperatingResearchPanel", () => ({
  Readable: ({ value }: any) => (
    <div>{typeof value === "string" ? value : "TEST_ONLY_READABLE_DETAIL"}</div>
  ),
  OperatingDriverBridgeView: ({ bridge }: any) => (
    <p>TEST_ONLY_DRIVER_BRIDGE:{bridge.version}</p>
  ),
  OperatingCashConsumptionView: () => <p>TEST_ONLY_CASH_CONSUMER</p>,
  LiveOperatingResearchPanel: () => <button>原有授权经营研究入口</button>,
}));
import { ValueWorkbenchSections } from "../src/components/ValueWorkbenchSections";
import {
  CandidateChoices,
  selectWorkbenchCompany,
} from "../src/pages/ValueWorkbench";
import type {
  ValueWorkbenchResponse,
  ValueWorkbenchSection,
} from "../src/services/api";
function section(
  id: ValueWorkbenchSection["id"],
  changes: Partial<ValueWorkbenchSection> = {},
): ValueWorkbenchSection {
  return {
    id,
    title: "TEST_ONLY_" + id,
    status: "SOURCE_BOUND_RESULTS",
    summary: "TEST_ONLY_SUMMARY",
    data: { native_results: {} },
    blockers: [],
    ...changes,
  };
}
function result(sections: ValueWorkbenchSection[]): ValueWorkbenchResponse {
  return {
    schema_version: "value-transparent-workbench-v1",
    symbol: "TEST_ONLY",
    action: "no_order",
    formal_eligibility: false,
    quantity: null,
    sections,
  };
}
it("routes the existing value menu directly into the workbench and keeps project as module map", () => {
  const route = readFileSync(".umirc.ts", "utf8");
  expect(route).toContain(
    '{ path: "/strategy/value", component: "./ValueWorkbench" }',
  );
  expect(route).toContain(
    '{ path: "/project", component: "./StrategyArchitecture/Value" }',
  );
  expect(route).toContain(
    '{ path: "/strategy/hotspot", component: "./StrategyArchitecture/Hotspot" }',
  );
  const page = readFileSync("src/pages/ValueWorkbench/index.tsx", "utf8");
  expect(page).toContain("value.shortlist");
  expect(page).toContain("registered[0]?.symbol");
  expect(page).toContain("已登记研究（非当前入池）");
  expect(page).toContain("按证券代码排序，不是推荐顺序");
  expect(page).toContain("api.valueWorkbenchCompanies");
  expect(page).toContain('to="/project"');
  expect(page).not.toMatch(
    /000568|600519|600887|localStorage|placeholder=.*代码/,
  );
});
it("renders actual candidate companies and activates the selected row without asking for a code", () => {
  const select = vi.fn();
  const tree = CandidateChoices({
    items: [
      { symbol: "TEST_ONLY_ONE", company_name: "测试候选甲" },
      { symbol: "TEST_ONLY_TWO", company_name: "测试候选乙" },
    ],
    selected: "TEST_ONLY_ONE",
    onSelect: select,
  });
  const nodes = (v: any): any[] =>
    Array.isArray(v)
      ? v.flatMap(nodes)
      : React.isValidElement(v)
        ? [v, ...nodes((v as any).props.children)]
        : [];
  const buttons = nodes(tree).filter(
    (v) => typeof v.props.onClick === "function",
  );
  expect(buttons).toHaveLength(2);
  buttons[1].props.onClick();
  expect(select).toHaveBeenCalledWith("TEST_ONLY_TWO");
  expect(renderToStaticMarkup(tree)).toContain("无需输入证券代码");
  expect(
    renderToStaticMarkup(<CandidateChoices items={[]} onSelect={select} />),
  ).toContain("不补造公司列表");
});
it("shows all ten real sections with independent missing/private states and no fake investment completion", () => {
  const ids = [
    "selection",
    "profile",
    "research",
    "assumptions",
    "cash",
    "valuation",
    "price",
    "decision",
    "continuity",
    "evidence",
  ] as const;
  const html = renderToStaticMarkup(
    <ValueWorkbenchSections
      symbol="TEST_ONLY"
      value={result(ids.map((id) => section(id)))}
    />,
  );
  for (const id of ids) expect(html).toContain("value-" + id);
  for (const text of [
    "当前价格不可比",
    "个人数量为空",
    "不下单",
    "未批准主区间",
    "不读取账户",
    "没有可核验估值",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("<pre");
});
it("suppresses a damaged section but preserves other independent explanations", () => {
  const value = result([
    section("research", {
      status: "UNASSESSABLE",
      data: {
        native_results: {
          live: {
            research_draft: { FUNDAMENTAL: { draft: "SHOULD_NOT_SHOW" } },
          },
        },
      },
      blockers: [{ source: "live", reason: "SOURCE_CHANGED" }],
    }),
    section("continuity"),
  ]);
  const html = renderToStaticMarkup(
    <ValueWorkbenchSections symbol="TEST_ONLY" value={value} />,
  );
  expect(html).not.toContain("SHOULD_NOT_SHOW");
  expect(html).toContain("SOURCE_CHANGED");
  expect(html).toContain("不读取账户");
  expect(html).toContain("其他独立环节仍可阅读");
});
it.each([
  { symbol: "OTHER" },
  { action: "order" },
  { formal_eligibility: true },
  { quantity: 1 },
  { schema_version: "UNKNOWN" },
])(
  "rejects incorrect identity or authority instead of showing stale data: %j",
  (change) => {
    const value = {
      ...result([section("research")]),
      ...change,
    } as ValueWorkbenchResponse;
    const html = renderToStaticMarkup(
      <ValueWorkbenchSections symbol="TEST_ONLY" value={value} />,
    );
    expect(html).toContain("停止展示");
    expect(html).not.toContain("TEST_ONLY_SUMMARY");
  },
);
it("reuses the native bridge and cash consumers instead of recalculating values or dumping JSON", () => {
  const value = result([
    section("assumptions", {
      data: {
        native_results: {
          live: { operating_driver_bridge: { version: "TEST_ONLY_BRIDGE" } },
        },
      },
    }),
    section("cash", {
      data: { native_results: { operating_cash: { status: "SOURCE_BOUND" } } },
    }),
  ]);
  const html = renderToStaticMarkup(
    <ValueWorkbenchSections symbol="TEST_ONLY" value={value} />,
  );
  expect(html).toContain("TEST_ONLY_DRIVER_BRIDGE:TEST_ONLY_BRIDGE");
  expect(html).toContain("TEST_ONLY_CASH_CONSUMER");
  expect(html).toContain("0.10表示10%");
  expect(html).toContain("所得税与少数股东归属");
  const source = readFileSync(
    "src/components/ValueWorkbenchSections.tsx",
    "utf8",
  );
  expect(source).not.toMatch(/JSON.stringify|<pre|fetch\(|setInterval/);
});

it("defaults to a registered company even when it is not in the current shortlist, without inventing research verification", () => {
  const registered = [{ symbol: "TEST_ONLY_REGISTERED" }],
    candidates = [{ symbol: "TEST_ONLY_CURRENT" }];
  expect(selectWorkbenchCompany(undefined, registered, candidates, false)).toBe(
    "TEST_ONLY_REGISTERED",
  );
  expect(
    selectWorkbenchCompany("TEST_ONLY_CURRENT", registered, candidates, false),
  ).toBe("TEST_ONLY_CURRENT");
  expect(selectWorkbenchCompany(undefined, registered, [], false)).toBe(
    "TEST_ONLY_REGISTERED",
  );
  expect(
    selectWorkbenchCompany(undefined, [], candidates, true),
  ).toBeUndefined();
  expect(selectWorkbenchCompany(undefined, [], [], false)).toBeUndefined();
});
