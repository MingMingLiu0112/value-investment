import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const captured = vi.hoisted(() => ({
  accountScope: "" as string,
  equity: "9995" as string | null,
  status: "VERIFIED_LATEST_COMPLETED_CLOSE",
  riskProps: {} as Record<string, any>,
  segmented: undefined as Record<string, any> | undefined,
  sizing: undefined as Record<string, any> | undefined,
  fill: undefined as Record<string, any> | undefined,
  revision: 2,
  search: "",
  portfolioStatus: "CONNECTED",
  privateKind: "BLOCKED_PRIVATE_INPUT",
}));
const reactState = vi.hoisted(() => ({
  use: null as
    | null
    | ((initial: unknown) => [unknown, (next: unknown) => void] | undefined),
}));
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) =>
      reactState.use?.(initial) ?? actual.useState(initial),
  };
});
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  useLocation: () => ({
    search: captured.search,
    hash: "",
    pathname: "/portfolio",
  }),
}));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => ({
    kind: captured.privateKind,
    label: "已接入，风险输入不完整",
    detail: "security_attributes.missing",
    retry: vi.fn(),
    portfolio: {
      status: captured.portfolioStatus,
      revision: captured.revision,
      cash_cny: "7337",
      total_equity_cny: captured.equity,
      realized_pnl_cny: "0",
      valuation: { status: captured.status, reason: "verified" },
      blockers: [],
      positions: [],
      trades: [],
    },
    risk: {
      facts: { account_scope: captured.accountScope },
      status: "BLOCKED_PRIVATE_INPUT",
      blockers: ["security_attributes.missing"],
      engine: {
        aggregate: { total_assets_cny: "12345" },
        trade_eligible: false,
      },
    },
  }),
}));

it("labels the isolated account before showing portfolio amounts", () => {
  captured.accountScope = "TEST_ONLY_BROWSER_LOOP";
  const html = renderToStaticMarkup(<Portfolio />);
  expect(html).toContain("TEST_ONLY 隔离演练账户");
  expect(html).toContain("不是你的真实账户");
  captured.accountScope = "";
});
vi.mock("../src/components/DualSleeveRisk", () => ({
  DualSleeveRisk: (props: Record<string, any>) => {
    captured.riskProps = props;
    return null;
  },
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../src/components/FillPanel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/components/FillPanel")>()),
  FillPanel: (props: Record<string, any>) => {
    captured.fill = props;
    return null;
  },
}));
vi.mock("../src/components/PortfolioSetupForm", () => ({
  PortfolioSetupForm: () => null,
}));
vi.mock("../src/components/PositionTable", () => ({
  PositionTable: () => null,
}));
vi.mock("../src/components/PortfolioPolicyPanel", () => ({
  PortfolioPolicyPanel: () => null,
}));
vi.mock("../src/components/CommittedRiskPanel", () => ({
  CommittedRiskPanel: () => null,
}));
vi.mock("../src/components/HotspotSizingPanel", () => ({
  HotspotSizingPanel: (props: Record<string, any>) => {
    captured.sizing = props;
    return `仓位试算:${props.sleeve};`;
  },
}));
vi.mock("../src/components/PortfolioReconciliationPanel", () => ({
  PortfolioReconciliationPanel: () => null,
}));
vi.mock("../src/components/ConfirmedTrades", () => ({
  ConfirmedTrades: () => null,
}));
vi.mock("../src/components/RemoteState", () => ({ RemoteState: () => null }));
vi.mock("antd", () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => children;
  return {
    Alert: (props: {
      message?: React.ReactNode;
      description?: React.ReactNode;
    }) => (
      <div>
        {props.message}
        {props.description}
      </div>
    ),
    Segmented: (props: Record<string, any>) => {
      captured.segmented = props;
      return `策略选择:${props.value};`;
    },
    Descriptions: () => null,
    Statistic: ({ title, value }: { title: string; value: string }) =>
      `${title}:${value};`,
    Button: wrapper,
    Col: wrapper,
    Row: wrapper,
    Space: wrapper,
    Tag: wrapper,
    Typography: { Title: wrapper, Text: wrapper, Paragraph: wrapper },
  };
});
import Portfolio from "../src/pages/Portfolio";

beforeEach(() => {
  captured.accountScope = "";
  captured.segmented = undefined;
  captured.sizing = undefined;
  captured.fill = undefined;
  captured.revision = 2;
  captured.search = "";
  captured.portfolioStatus = "CONNECTED";
  captured.privateKind = "BLOCKED_PRIVATE_INPUT";
});

it("provides reachable existing forms without inventing trade inputs", () => {
  captured.search =
    "?symbol=600887&strategy=value&decision_id=value-id&research_version=research-v1&quantity=9999&price=1";
  const html = renderToStaticMarkup(<Portfolio />);
  for (const id of [
    "portfolio-positions",
    "portfolio-risk",
    "portfolio-sizing",
    "portfolio-fill",
  ]) {
    expect(html).toContain(`href="#${id}"`);
    expect(html).toContain(`id="${id}"`);
  }
  expect(html).toContain('href="/daily"');
  expect(captured.fill).toMatchObject({
    initialSymbol: "600887",
    initialSleeve: "CORE_VALUE",
    initialDecisionId: "value-id",
    initialResearchVersion: "research-v1",
  });
  expect(captured.sizing).toMatchObject({
    initialSymbol: "600887",
    sleeve: "CORE_VALUE",
  });
  expect(captured.fill?.quantity).toBeUndefined();
  expect(captured.fill?.price).toBeUndefined();
  expect(html).not.toContain("9999");
});

it("offers initialization rather than unreachable fill anchors for an unconnected account", () => {
  captured.portfolioStatus = "NOT_CONNECTED";
  const html = renderToStaticMarkup(<Portfolio />);
  expect(html).toContain('id="portfolio-setup"');
  expect(html).toContain('href="#portfolio-setup"');
  expect(html).not.toContain('href="#portfolio-fill"');
  expect(captured.fill).toBeUndefined();
});

it("routes the workbench sleeve selector to the sizing panel", () => {
  let selected = "HOTSPOT_SATELLITE";
  reactState.use = (initial) => {
    if (initial !== "HOTSPOT_SATELLITE") return undefined;
    return [
      selected,
      (next: unknown) => {
        selected =
          typeof next === "function"
            ? (next as (value: string) => string)(selected)
            : String(next);
      },
    ];
  };
  try {
    renderToStaticMarkup(<Portfolio />);
    expect(captured.segmented?.value).toBe("HOTSPOT_SATELLITE");
    expect(captured.sizing?.sleeve).toBe("HOTSPOT_SATELLITE");

    captured.segmented!.onChange("CORE_VALUE");
    renderToStaticMarkup(<Portfolio />);
    expect(captured.segmented?.value).toBe("CORE_VALUE");
    expect(captured.sizing?.sleeve).toBe("CORE_VALUE");
  } finally {
    reactState.use = null;
  }
});

it.each([
  ["VERIFIED_LATEST_COMPLETED_CLOSE", "9995"],
  ["CASH_ONLY_NO_QUOTE_REQUIRED", "10000"],
  ["VERIFIED_LATEST_COMPLETED_CLOSE", "0"],
  ["PRICE_NOT_ADMITTED", null],
])(
  "shows ledger equity independently of risk admission (%s)",
  (status, equity) => {
    captured.status = status!;
    captured.equity = equity;
    const html = renderToStaticMarkup(<Portfolio />);
    expect(html).toContain(`总权益（元，核验口径）:${equity ?? "未核验"};`);
    expect(html).not.toContain("12345");
    expect(captured.riskProps.data.blockers).toEqual([
      "security_attributes.missing",
    ]);
    expect(captured.riskProps.data.engine.trade_eligible).toBe(false);
  },
);

it("passes only current same-account and same-sleeve assumptions to the fill panel", () => {
  let selection: unknown = null;
  let symbol = "";
  let sleeve = "HOTSPOT_SATELLITE";
  reactState.use = (initial) => {
    if (initial === null)
      return [
        selection,
        (next) => {
          selection = next;
        },
      ];
    if (initial === "")
      return [
        symbol,
        (next) => {
          symbol = String(next);
        },
      ];
    if (initial === "HOTSPOT_SATELLITE")
      return [
        sleeve,
        (next) => {
          sleeve = String(next);
        },
      ];
    return undefined;
  };
  try {
    renderToStaticMarkup(<Portfolio />);
    expect(captured.fill?.riskAssumptions).toBeUndefined();
    captured.sizing!.onSymbolChange("600887");
    renderToStaticMarkup(<Portfolio />);
    const assumptions = { gap_stress_cny: "0.5" };
    captured.sizing!.onRequest({ symbol: "600887", sleeve, assumptions });
    assumptions.gap_stress_cny = "999";
    renderToStaticMarkup(<Portfolio />);
    expect(captured.fill?.riskAssumptions).toMatchObject({
      revision: 2,
      symbol: "600887",
      sleeve: "HOTSPOT_SATELLITE",
      assumptions: { gap_stress_cny: "0.5" },
    });
    captured.segmented!.onChange("CORE_VALUE");
    renderToStaticMarkup(<Portfolio />);
    expect(captured.fill?.riskAssumptions).toBeUndefined();
    sleeve = "HOTSPOT_SATELLITE";
    captured.revision = 3;
    renderToStaticMarkup(<Portfolio />);
    expect(captured.fill?.riskAssumptions).toBeUndefined();
    captured.revision = 2;
    captured.accountScope = "other-account";
    renderToStaticMarkup(<Portfolio />);
    expect(captured.fill?.riskAssumptions).toBeUndefined();
  } finally {
    reactState.use = null;
  }
});
