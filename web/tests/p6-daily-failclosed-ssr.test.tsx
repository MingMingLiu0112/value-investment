import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { PrivateStateHandle } from "../src/hooks/usePrivateState";
import { api } from "../src/services/api";
const { renderToStaticMarkup } = require("react-dom/server");

const state = vi.hoisted(() => ({
  daily: {
    data: undefined as any,
    loading: false,
    error: undefined as string | undefined,
    retry: () => {},
  },
  packet: {
    data: undefined as any,
    loading: false,
    error: undefined as string | undefined,
    retry: () => {},
  },
}));
vi.mock("@umijs/max", () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("../src/hooks/useApi", () => ({
  useApi: (load: unknown) =>
    load === api.daily
      ? state.daily
      : load === api.packet
        ? state.packet
        : {
            data: undefined,
            loading: false,
            error: undefined,
            retry: () => {},
          },
}));
vi.mock("../src/hooks/usePrivateState", () => ({
  usePrivateState: () => ({
    kind: "LOCKED",
    label: "私人台账未解锁",
    retry: () => {},
  }),
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: { children: React.ReactNode }) => (
    <main>{children}</main>
  ),
}));
import DailyDecisions from "../src/pages/DailyDecisions";
import { HoldingsAttention } from "../src/components/HoldingsAttention";

beforeEach(() => {
  state.daily = {
    loading: false,
    error: undefined,
    retry: () => {},
    data: {
      action: "no_order",
      publication: { packet_status: "CURRENT", publication_id: "pub-verified" },
      sections: {
        value: [],
        holdings: [],
        hotspot: [
          {
            id: "hotspot-300364",
            symbol: "300364",
            name: "中文在线回归候选",
            strategy: "hotspot",
            price_action_plan: {
              action: "no_order",
              signal_state: "WATCH",
              entry_trigger_price: "27.880",
              market_trade_date: "2026-10-14",
            },
          },
        ],
      },
    },
  };
  state.packet = {
    loading: false,
    error: undefined,
    retry: () => {},
    data: {
      action: "no_order",
      packet_status: "CURRENT",
      publication_id: "pub-verified",
      dates: { research_as_of: "2026-10-11", quote_trade_date: "2026-10-14" },
      data_freshness: {
        quote: { status: "FRESH" },
        research: { status: "STALE" },
      },
    },
  };
});

it.each(["daily", "packet", "both"] as const)(
  "hides retained successful data after %s refresh fails",
  (failed) => {
    const render = () => renderToStaticMarkup(<DailyDecisions />);
    expect(render()).toContain("中文在线回归候选");
    const retainedDaily = state.daily.data;
    const retainedPacket = state.packet.data;
    // useApi deliberately retains these successful payloads when a retry rejects.
    if (failed !== "packet") state.daily.error = "daily refresh failed";
    if (failed !== "daily") state.packet.error = "packet refresh failed";
    const html = render();
    expect(state.daily.data).toBe(retainedDaily);
    expect(state.packet.data).toBe(retainedPacket);
    expect(html).not.toContain("中文在线回归候选");
    expect(html).not.toContain("持仓今日复核");
    expect(html).toContain("当前结果不可核验，已停止展示候选。");
    expect(html).toContain(
      failed === "packet" ? "packet refresh failed" : "daily refresh failed",
    );
  },
);

it.each(["daily", "packet"] as const)(
  "does not show retained candidates while %s refresh is pending",
  (pending) => {
    state[pending].loading = true;
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).not.toContain("中文在线回归候选");
    expect(html).not.toContain("当前结果不可核验，已停止展示候选。");
  },
);

it.each(["daily unavailable", "packet unavailable", "different publication"])(
  "rejects %s despite retained candidate rows",
  (reason) => {
    if (reason === "daily unavailable")
      state.daily.data.publication.packet_status = "UNAVAILABLE";
    if (reason === "packet unavailable")
      state.packet.data.packet_status = "UNAVAILABLE";
    if (reason === "different publication")
      state.packet.data.publication_id = "pub-other";
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).not.toContain("中文在线回归候选");
    expect(html).toContain("当前结果不可核验，已停止展示候选。");
  },
);

it("labels frozen freshness as verification at publication time", () => {
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("发布时已核验");
  expect(html).not.toContain("行情状态 <strong>最近完成交易日");
});

it("unverified holdings decisions cannot become either an exit alert or a no-exit conclusion", () => {
  const connected = {
    portfolio: {
      status: "CONNECTED",
      cash_cny: "100",
      total_equity_cny: null,
      positions: [{ symbol: "300364" }],
    },
    risk: { blockers: [] },
  } as unknown as PrivateStateHandle;
  const decisions = [
    { id: "hotspot-300364", symbol: "300364", action_intent: "EXIT" },
  ];
  const html = renderToStaticMarkup(
    <HoldingsAttention state={connected} decisions={decisions} />,
  );
  expect(html).toContain("策略复核未知");
  expect(html).not.toContain("已出现策略退出或减仓复核事项");
  expect(html).not.toContain("未发现新增退出复核");
  const verified = renderToStaticMarkup(
    <HoldingsAttention
      state={connected}
      decisions={decisions}
      decisionsVerified
    />,
  );
  expect(verified).toContain("已出现策略退出或减仓复核事项");
});
