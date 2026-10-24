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
  update: {
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
        : load === api.updateStatus
          ? state.update
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
  state.update = {
    loading: false,
    error: undefined,
    retry: () => {},
    data: undefined,
  };
});

it("keeps unvalued company research reachable without claiming there are no value leads", () => {
  state.daily.data.sections.value = [
    {
      id: "600887",
      symbol: "600887",
      name: "伊利股份",
      strategy: "value",
      action: "no_order",
      status: "PENDING_RESEARCH",
    },
  ];
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain('aria-label="价值研究快捷入口"');
  expect(html).toContain('href="/decisions/600887"');
  expect(html).toContain("尚无可用的价值投资操作价");
  expect(html).not.toContain("当前没有可展示的价值投资线索");
  expect(html).not.toContain("正式可买入");
  state.packet.data.publication_id = "wrong-publication";
  expect(renderToStaticMarkup(<DailyDecisions />)).not.toContain(
    'aria-label="价值研究快捷入口"',
  );
});

it("shows an explicit unfinished-update message when finished_at is null", () => {
  state.update.data = {
    action: "no_order",
    status: "RECORDED",
    last_run: {
      status: "BLOCKED",
      finished_at: null,
      published: false,
      publication_id: null,
      retained_publication_id: "pub-verified",
    },
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("更新尚未完成，暂无完成时间");
  expect(html).not.toContain("1970");
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

it.each(["gate_code", "blockers", "reason"])(
  "prioritizes an unavailable source receipt from %s over a missing publication version",
  (field) => {
    const code = "VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE";
    state.daily.data.status = "UNAVAILABLE";
    state.daily.data.publication = {
      packet_status: "UNAVAILABLE",
      publication_id: null,
    };
    state.daily.data.reason = "VALUE_DISCOVERY_RECEIPT_UNAVAILABLE";
    state.daily.data.publication_source =
      "D:\\private-source-root\\missing-receipt.json";
    if (field === "blockers") {
      state.daily.data.blockers = [
        `${code}:D:\\private-source-root\\missing-receipt.json`,
      ];
      state.daily.data.reason =
        "Source missing at D:\\private-source-root\\missing-receipt.json";
    } else if (field === "gate_code") state.daily.data.gate_code = code;
    state.packet.data.chain_error = "PUBLICATION_CHAIN_UNAVAILABLE";
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("价值投资初筛的来源回执缺失或未通过核验");
    expect(html).toContain("当前结果不可核验，已停止展示候选。");
    expect(html).not.toContain("判断与快照版本不一致");
    expect(html).not.toContain("发布链不可用（哈希或结构校验未通过）");
    expect(html).not.toContain("private-source-root");
    expect(html).not.toContain("missing-receipt.json");
    expect(html).not.toContain("中文在线回归候选");
    expect(html).not.toContain('aria-label="价值研究快捷入口"');
  },
);

it.each([
  [null, "pub-verified"],
  [undefined, "pub-verified"],
  ["", "pub-verified"],
  [" ", "pub-verified"],
  ["pub-verified", null],
  ["pub-verified", undefined],
  ["pub-verified", ""],
  [null, null],
])(
  "does not call missing version identities a mismatch (%s, %s)",
  (daily, packet) => {
    state.daily.data.publication.publication_id = daily;
    state.packet.data.publication_id = packet;
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("正式发布链尚未就绪。");
    expect(html).not.toContain("判断与快照版本不一致");
    expect(html).not.toContain("中文在线回归候选");
  },
);

it("reports a version mismatch only between two current nonempty publications", () => {
  state.packet.data.publication_id = "pub-other";
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("判断与快照版本不一致，请刷新后重试。");
  expect(html).not.toContain("中文在线回归候选");
});

it.each(["daily", "packet"] as const)(
  "translates known %s dependency codes and omits diagnostic paths",
  (source) => {
    const diagnostic =
      "PUBLICATION_CHAIN_UNAVAILABLE:D:\\private-source-root\\missing.json";
    if (source === "daily") {
      state.daily.data.status = "UNAVAILABLE";
      state.daily.data.gate_code = diagnostic;
      state.daily.data.publication.publication_id = null;
    } else {
      state.packet.data.packet_status = "UNAVAILABLE";
      state.packet.data.chain_error = diagnostic;
    }
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("发布链不可用（哈希或结构校验未通过）");
    expect(html).not.toContain("判断与快照版本不一致");
    expect(html).not.toContain("private-source-root");
    expect(html).not.toContain("中文在线回归候选");
  },
);

it("uses a safe dependency fallback for an unrecognized backend diagnostic", () => {
  state.daily.data.status = "UNAVAILABLE";
  state.daily.data.publication.publication_id = null;
  state.daily.data.reason =
    "Missing source at /private-source-root/missing-receipt.json";
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("当前结果所需的来源依赖缺失或未通过核验。");
  expect(html).not.toContain("private-source-root");
  expect(html).not.toContain("判断与快照版本不一致");
  expect(html).not.toContain("中文在线回归候选");
});

it("labels frozen freshness as verification at publication time", () => {
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("发布时已核验");
  expect(html).not.toContain("行情状态 <strong>最近完成交易日");
});

it("never calls incomplete evaluation a market with no opportunities", () => {
  state.daily.data.actionable_evaluation = {
    conclusion: "INCOMPLETE_EVALUATION",
    evaluated_count: 1,
    unassessable_count: 2,
    operation_eligible_count: 0,
    items: [
      {
        symbol: "000333",
        strategy: "CORE_VALUE",
        decision_action: "UNASSESSABLE",
        decision_reason: "经济假设未批准",
      },
    ],
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("不能据此判断市场没有机会");
  expect(html).toContain("无法评价");
  expect(html).not.toContain("· 不交易");
  expect(html).toContain("经济假设未批准");
  expect(html).not.toContain("本次已评价范围内，无符合全部条件的新交易机会。");
});

it("keeps today's screening leads distinct from published research and actions", () => {
  state.update.data = {
    last_run: {
      status: "SUCCESS",
      finished_at: "2026-10-20T14:00:00Z",
      screening: {
        status: "VERIFIED_RESEARCH_SCAN",
        as_of: "2026-10-20",
        universe_count: 5575,
        lead_count: 111,
        channel_counts: { quality: 0 },
        quote_date_verification: "UNVERIFIED_PROVIDER_TRADE_DATE",
      },
    },
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("本次全市场初筛（尚非交易机会）");
  expect(html).toContain("5575");
  expect(html).toContain("111");
  expect(html).toContain("全市场行情日期仍需独立核验");
});

it("shows research scheduling separately from successful enrichment and approvals", () => {
  state.update.data = {
    last_run: {
      status: "SUCCESS",
      finished_at: "2026-10-21T01:00:00Z",
      research_priority: {
        status: "VERIFIED_RESEARCH_PRIORITY",
        as_of: "2026-10-20",
        deep_research_count: 0,
        enrichment_count: 111,
        selected_enrichment_count: 10,
        execution: {
          status: "VERIFIED_RESEARCH_EXECUTION",
          attempted_count: 2,
          reevaluated_count: 2,
          data_gap_count: 2,
          items: [
            {
              symbol: "000589",
              company_name: "贵州轮胎",
              extracted_candidates: 16,
              matched_candidates: 15,
            },
          ],
        },
      },
    },
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("研究推进");
  expect(html).toContain("111");
  expect(html).toContain("不代表补证成功、估值获准或交易资格");
  expect(html).toContain("实际执行补证");
  expect(html).toContain("贵州轮胎");
  expect(html).toContain("匹配不代表新增事实准入");
});

it("unverified holdings decisions cannot become either an exit alert or a no-exit conclusion", () => {
  const connected = {
    portfolio: {
      status: "CONNECTED",
      cash_cny: "100",
      total_equity_cny: null,
      positions: [
        {
          symbol: "300364",
          sleeves: [{ sleeve: "HOTSPOT_SATELLITE", quantity: "100" }],
        },
      ],
    },
    risk: { blockers: [] },
  } as unknown as PrivateStateHandle;
  const decisions = [
    {
      id: "hotspot-300364",
      symbol: "300364",
      strategy: "HOTSPOT_SATELLITE",
      action_intent: "EXIT",
    },
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
