import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { PrivateStateHandle } from "../src/hooks/usePrivateState";
import { api } from "../src/services/api";
import { evaluationFixture } from "./fixtures/strategy-readiness";
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
  independentHotspot: {
    data: undefined as any,
    loading: false,
    error: undefined as string | undefined,
    retry: () => {},
  },
  selection: {
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
          : load === api.independentHotspot
            ? state.independentHotspot
            : load === api.strategySelection
              ? state.selection
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

it.each(["OPEN", "ADD", "HOLD", "REDUCE", "EXIT"])(
  "keeps a public %s review distinct from unknown companies and personal permission",
  (intent) => {
    state.daily.data.actionable_evaluation = {
      action: "no_order",
      scope: "PUBLISHED_COMPANIES_ONLY",
      evaluated_count: 1,
      unassessable_count: 1,
      conditional_review_count: 1,
      operation_eligible_count: 0,
      conclusion: "INCOMPLETE_EVALUATION",
      items: [
        {
          symbol: "600519",
          strategy: "CORE_VALUE",
          decision_action: "CONDITIONAL_MANUAL_REVIEW",
          public_action_intent: intent,
          decision_reason: "TEST_ONLY native security review",
          eligibility: false,
        },
        {
          symbol: "000544",
          strategy: "CORE_VALUE",
          decision_action: "UNASSESSABLE",
          decision_reason: "TEST_ONLY model unavailable",
          eligibility: false,
        },
      ],
    };
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("存在证券级条件复核");
    expect(html).toContain("不代表个人可交易");
    expect(html).toContain("TEST_ONLY native security review");
    expect(html).toContain("无法评价");
    expect(html).toContain("TEST_ONLY model unavailable");
    expect(html).not.toContain("无符合全部条件的新交易机会");
    expect(html).not.toContain("已评价后暂不新建仓");
  },
);

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
  state.independentHotspot = {
    loading: false,
    error: undefined,
    retry: () => {},
    data: undefined,
  };
  state.selection = {
    loading: false,
    error: undefined,
    retry: () => {},
    data: undefined,
  };
});

it("keeps hotspot dates and plans from the daily response instead of mixing independent requests", () => {
  state.daily.data.sections.hotspot[0].price_action_plan.market_trade_date =
    "2026-10-14";
  state.independentHotspot.data = {
    publication: { publication_id: "pub-verified" },
    items: [
      {
        symbol: "300364",
        price_action_plan: {
          action: "no_order",
          signal_state: "WATCH",
          market_trade_date: "2026-10-21",
        },
      },
    ],
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("热点已完成交易日 2026-10-14");
  expect(html).not.toContain("热点已完成交易日 2026-10-21");
});

it.each(["COVERS", "INCREMENTALLY_COVERS"])(
  "shows actual research producer enum %s and separate evidence dates",
  (status) => {
    const packet = state.packet.data;
    packet.source_bindings_verified = true;
    packet.data_freshness.research.status = status;
    packet.dates.quote_trade_date =
      status === "COVERS" ? "2026-10-11" : "2026-10-22";
    packet.generated_at = "2026-10-23T08:00:00+08:00";
    packet.company_statuses = {
      "600519": {
        symbol: "600519",
        name: "TEST_ONLY 研究样本",
        price_bridge: {
          incremental_status: "VALID",
          review_cutoff: "2026-10-22",
          blockers: [],
          incremental_validity_binding: {
            path: "TEST_ONLY/review.json",
            sha256: "a".repeat(64),
          },
        },
      },
    };
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("原研究基准");
    expect(html).toContain("2026-10-11");
    expect(html).toContain("最近机器复核");
    expect(html).toContain("尚无可核验复核回执");
    expect(html).toContain("增量复核截至 2026-10-22");
    expect(html).toContain("查询截止日不是全天覆盖证明");
    expect(html).toContain("研究日期覆盖不等于估值、事件或交易获准");
  },
);

it.each(["PARTIAL", "BLOCKED"])(
  "does not promote %s update completion time into research review",
  (status) => {
    state.update.data = {
      last_run: { status, finished_at: "2026-10-23T15:00:00+08:00" },
    };
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html).toContain("尚无可核验复核回执");
    expect(html).toContain("事件覆盖材料，暂不可用");
    expect(html).not.toContain("增量事件有效性已核验");
  },
);

it("shows same-day query as a partial snapshot rather than completed daily coverage", () => {
  const packet = state.packet.data;
  packet.source_bindings_verified = true;
  packet.dates.current_natural_date = "2026-10-24";
  packet.company_statuses = {
    "600519": {
      symbol: "600519",
      name: "TEST_ONLY 查询窗口",
      price_bridge: {
        incremental_status: "UNKNOWN",
        review_cutoff: "2026-10-24",
        blockers: [],
        incremental_validity_binding: {
          path: "TEST_ONLY/review.json",
          sha256: "a".repeat(64),
        },
        current_event_coverage: {
          required_through: "2026-10-24",
          query_through: "2026-10-24",
          covered_through: null,
          observed_at: "2026-10-24T10:20:00+08:00",
          full_calendar_window_elapsed: false,
          status: "PARTIAL_CURRENT_SNAPSHOT",
        },
      },
    },
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("局部公告快照（partial），不是全天完整覆盖");
  expect(html).toContain("2026-10-24T10:20:00+08:00");
  expect(html).toContain("未确认完整覆盖");
  expect(html).toContain("2026-10-11");
  expect(html).toContain("2026-10-14");
  expect(html).not.toContain("增量事件有效性已核验");
});

it("separates source-replayed machine review from original research and complete event coverage", () => {
  state.update.data = {
    last_run: {
      status: "PARTIAL",
      finished_at: "2026-10-23T18:00:00+08:00",
      research_review: {
        status: "SOURCE_REPLAYED",
        checked_at: "2026-10-23T16:00:00+08:00",
        review_cutoff: "2026-10-22",
        scope: "MACHINE_REVIEW_NOT_RESEARCH_APPROVAL",
        action: "no_order",
        formal_eligibility: false,
        rows: [
          {
            symbol: "600519",
            status: "UNKNOWN",
            research_as_of: "2026-10-11",
            scan_through: "2026-10-22",
            event_coverage_through: null,
            announcement_count: 3,
            facts_change_status: "UNKNOWN",
            model_validity_status: "UNKNOWN",
            model_recalculation_required: true,
            materiality_review_required: true,
            formal_eligibility: false,
          },
        ],
      },
    },
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("本次机器复核进度");
  expect(html).toContain("未确认完整覆盖");
  expect(html).toContain("模型需要重算");
  expect(html).toContain("需要事件材料性审核");
  expect(html).toContain("不是人工经济审核或正式交易准入");
  expect(html).toContain("研究基准与发布版本保持独立");
  expect(html).toContain("2026-10-11");
  state.update.error = "TEST_ONLY retry failed";
  const failed = renderToStaticMarkup(<DailyDecisions />);
  expect(failed).not.toContain("本次机器复核进度");
  expect(failed).toContain("尚无可核验复核回执");
});

it("shows evaluated no-trade reasons separately from missing value inputs", () => {
  const hotspot = {
    ...evaluationFixture("HOTSPOT_SATELLITE"),
    symbol: "300364",
    decision_action: "NO_TRADE",
    decision_reason: "日线与主周期结构冲突，本次不交易。",
  };
  const value = {
    ...evaluationFixture(),
    decision_reason: "现金流口径仍待核验，无法评价。",
  };
  state.daily.data.actionable_evaluation = {
    items: [value, hotspot],
    evaluated_count: 1,
    unassessable_count: 1,
    conclusion: "INCOMPLETE_EVALUATION",
  };
  state.daily.data.sections.value = [
    {
      id: "600887",
      symbol: "600887",
      strategy: "value",
      name: "价值输入不足测试",
    },
  ];
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("已评价，暂不新建仓");
  expect(html).toContain("已有持仓的加减仓与退出须独立复核");
  expect(html).toContain("日线与主周期结构冲突，本次不交易。");
  expect(html).toContain("输入或资格不足，无法评价");
  expect(html).toContain("现金流口径仍待核验，无法评价。");
  expect(html).toContain("不能据此判断市场没有机会");
  expect(html).toContain('href="#daily-hotspot"');
  expect(html).toContain('href="#daily-value"');
  expect(html).toContain('href="/portfolio"');
});

it("puts hotspot condition review and sizing entry in the daily confirmation queue", () => {
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("热点条件复核");
  expect(html).toContain("查看热点操作条件");
  expect(html).toContain(
    'href="/decisions/hotspot-300364?independent_hotspot=true"',
  );
  expect(html).toContain("进入风险试算与成交登记");
  expect(html).toContain("不把 WATCH 当作买入");
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
  expect(html).toContain("尚未完成，可能仍在运行或已中断");
  expect(html).not.toContain("失败，保留旧快照");
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
    expect(html).toContain("正式发布不可核验，已停止展示正式结果。");
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
    expect(html).not.toContain("正式发布不可核验，已停止展示正式结果。");
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
    expect(html).toContain("正式发布不可核验，已停止展示正式结果。");
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
    expect(html).toContain("正式发布不可核验，已停止展示正式结果。");
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

it("mounts separate readiness workflows only within the verified daily publication", () => {
  const value = evaluationFixture();
  const hotspot = evaluationFixture("HOTSPOT_SATELLITE");
  state.daily.data.actionable_evaluation = {
    items: [value, hotspot],
    conclusion: "INCOMPLETE_EVALUATION",
    evaluated_count: 0,
    unassessable_count: 2,
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain('aria-label="每日双策略流程"');
  expect(html).toContain("公司研究形成");
  expect(html).toContain("回放与策略验证");
  expect(html).toContain("无法评价");
  expect(html).toContain("independent_hotspot=true");
  state.packet.data.publication_id = "other-publication";
  expect(renderToStaticMarkup(<DailyDecisions />)).not.toContain(
    'aria-label="每日双策略流程"',
  );
});

it("keeps the old daily UI without readiness and never changes UNASSESSABLE to NO_TRADE", () => {
  const legacy = { ...evaluationFixture(), readiness: undefined };
  state.daily.data.actionable_evaluation = {
    items: [legacy],
    conclusion: "INCOMPLETE_EVALUATION",
    evaluated_count: 0,
    unassessable_count: 1,
  };
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).not.toContain('aria-label="每日双策略流程"');
  expect(html).toContain("逐公司结论与统计范围");
  expect(html).toContain("无法评价");
  expect(html).not.toContain("· 不交易");
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

function independentSelectionFixture() {
  return {
    action: "no_order",
    formal_eligibility: false,
    portfolio_eligibility: false,
    content_sha256: "a".repeat(64),
    value: {
      status: "RESEARCH_ONLY",
      data_status: "PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS",
      quote_date: "2026-10-23",
      rule_version: "TEST_ONLY-independent-source",
      coverage: {
        universe_count: 10,
        research_queue_count: 1,
        observation_count: 4,
        official_fact_admission_count: 0,
      },
      items: [
        {
          symbol: "000544",
          company_name: "TEST_ONLY 独立来源研究候选",
          profile_status: "GENERAL_RESEARCH",
          action: "no_order",
          formal_eligibility: false,
          portfolio_eligibility: false,
        },
      ],
    },
    hotspot: { items: [], coverage: {} },
  };
}

it.each([
  "daily error",
  "packet error",
  "daily unavailable",
  "packet unavailable",
  "version mismatch",
  "daily loading",
  "packet loading",
])(
  "keeps independent source research visible during %s without exposing formal results",
  (failure) => {
    state.selection.data = independentSelectionFixture();
    state.daily.data.actionable_evaluation = {
      conditional_review_count: 1,
      items: [{ decision_reason: "TEST_ONLY retained formal review" }],
    };
    if (failure === "daily error") state.daily.error = "TEST_ONLY daily failed";
    if (failure === "packet error")
      state.packet.error = "TEST_ONLY packet failed";
    if (failure === "daily unavailable")
      state.daily.data.publication.packet_status = "UNAVAILABLE";
    if (failure === "packet unavailable")
      state.packet.data.packet_status = "UNAVAILABLE";
    if (failure === "version mismatch")
      state.packet.data.publication_id = "TEST_ONLY other";
    if (failure === "daily loading") state.daily.loading = true;
    if (failure === "packet loading") state.packet.loading = true;
    const transport = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("SSR must not invoke network or order transports");
    });
    try {
      const html = renderToStaticMarkup(<DailyDecisions />);
      expect(html.match(/aria-label="双策略选股"/g)).toHaveLength(1);
      expect(html).toContain("TEST_ONLY 独立来源研究候选");
      expect(html).toContain("尚未成为官方核验事实");
      expect(html).not.toContain("TEST_ONLY retained formal review");
      expect(html).not.toContain('aria-label="明确行动结论"');
      expect(html).not.toContain('aria-label="每日双策略流程"');
      expect(html).not.toContain('aria-label="持仓今日复核"');
      expect(html).not.toContain("中文在线回归候选");
      expect(html).not.toContain("存在证券级条件复核");
      expect(html).not.toContain("记录我的实际成交");
      if (!failure.endsWith("loading")) {
        expect(html).toContain("正式发布不可核验，已停止展示正式结果。");
        expect(html.indexOf("正式发布不可核验")).toBeLessThan(
          html.indexOf('aria-label="双策略选股"'),
        );
      } else {
        expect(html.indexOf("ant-skeleton")).toBeLessThan(
          html.indexOf('aria-label="双策略选股"'),
        );
      }
      expect(transport).not.toHaveBeenCalled();
    } finally {
      transport.mockRestore();
    }
  },
);

it.each(["current", "unavailable"])(
  "hides retained independent candidates after source failure with %s publication",
  (publication) => {
    state.selection.data = independentSelectionFixture();
    state.selection.error = "TEST_ONLY independent source hash mismatch";
    if (publication === "unavailable")
      state.packet.error = "TEST_ONLY packet failed";
    const html = renderToStaticMarkup(<DailyDecisions />);
    expect(html.match(/aria-label="双策略选股"/g)).toHaveLength(1);
    expect(html).toContain("选股来源暂不可核验，未生成新结论");
    expect(html).not.toContain("TEST_ONLY 独立来源研究候选");
    expect(html).not.toContain("存在证券级条件复核");
  },
);

it("keeps an independently rejected source unknown rather than zero candidates", () => {
  state.packet.error = "TEST_ONLY packet failed";
  const selection = independentSelectionFixture();
  selection.value.status = "SOURCE_OR_SELECTION_UNAVAILABLE";
  selection.value.data_status = "SOURCE_REVALIDATION_FAILED";
  selection.value.items = [];
  selection.value.coverage = {} as typeof selection.value.coverage;
  state.selection.data = selection;
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html).toContain("无法核验，不代表零候选");
  expect(html).not.toContain("TEST_ONLY 独立来源研究候选");
  expect(html).not.toContain("覆盖 0 家");
  expect(html).not.toContain('aria-label="明确行动结论"');
});

it("keeps one independent selector after the action conclusion when both sources are available", () => {
  state.selection.data = independentSelectionFixture();
  const html = renderToStaticMarkup(<DailyDecisions />);
  expect(html.match(/aria-label="双策略选股"/g)).toHaveLength(1);
  expect(html).toContain("TEST_ONLY 独立来源研究候选");
  expect(html).toContain("中文在线回归候选");
  expect(html.indexOf('aria-label="双策略选股"')).toBeGreaterThan(
    html.indexOf('aria-label="明确行动结论"'),
  );
});
