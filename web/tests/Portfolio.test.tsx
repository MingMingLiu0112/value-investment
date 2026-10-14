import React from "react";
import { expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const captured = vi.hoisted(() => ({
  equity: "9995" as string | null,
  status: "VERIFIED_LATEST_COMPLETED_CLOSE",
  riskProps: {} as Record<string, any>,
}));
vi.mock("@umijs/max", () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  useSearchParams: () => [new URLSearchParams()],
}));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => ({
    kind: "BLOCKED_PRIVATE_INPUT",
    label: "已接入，风险输入不完整",
    detail: "security_attributes.missing",
    retry: vi.fn(),
    portfolio: {
      status: "CONNECTED",
      revision: 2,
      cash_cny: "7337",
      total_equity_cny: captured.equity,
      realized_pnl_cny: "0",
      valuation: { status: captured.status, reason: "verified" },
      blockers: [],
      positions: [],
      trades: [],
    },
    risk: {
      status: "BLOCKED_PRIVATE_INPUT",
      blockers: ["security_attributes.missing"],
      engine: {
        aggregate: { total_assets_cny: "12345" },
        trade_eligible: false,
      },
    },
  }),
}));
vi.mock("../src/components/DualSleeveRisk", () => ({
  DualSleeveRisk: (props: Record<string, any>) => {
    captured.riskProps = props;
    return null;
  },
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../src/components/FillPanel", () => ({
  FillPanel: () => null,
  fillContextFromSearch: () => ({}),
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
vi.mock("../src/components/HotspotSizingPanel", () => ({
  HotspotSizingPanel: () => null,
}));
vi.mock("../src/components/ConfirmedTrades", () => ({
  ConfirmedTrades: () => null,
}));
vi.mock("../src/components/RemoteState", () => ({ RemoteState: () => null }));
vi.mock("antd", () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => children;
  return {
    Alert: () => null,
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
