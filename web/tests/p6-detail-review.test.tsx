import React from "react";
import { describe, expect, it, vi } from "vitest";
import type { DecisionItem } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server");
const state = vi.hoisted(() => ({
  data: null as any,
  error: null as string | null,
  loading: false,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => state }));
vi.mock("../src/pages/HistoricalPrice", () => ({ PriceChart: () => null }));
vi.mock("../src/components/DetailSection", () => ({
  DetailSection: ({ title, value }: any) => (
    <div>
      {title}
      {JSON.stringify(value)}
    </div>
  ),
}));
vi.mock("antd", () => ({
  Alert: ({ message, description }: any) => (
    <div>
      {message}
      {description}
    </div>
  ),
  Descriptions: ({ items }: any) => (
    <dl>
      {items.map((item: any) => (
        <div key={item.key}>
          <dt>{item.label}</dt>
          <dd>{item.children}</dd>
        </div>
      ))}
    </dl>
  ),
  Segmented: () => null,
  Table: () => null,
}));
import { JudgmentSummary } from "../src/components/CurrentJudgment";
import { ValuePolicyReview } from "../src/components/ValuePolicyReview";
import { HotspotReplayReview } from "../src/components/HotspotReplayReview";

describe("detail operation plan boundaries", () => {
  it("keeps current judgment, prices and core risk visible before personal context and policy", () => {
    state.data = null;
    const html = renderToStaticMarkup(
      <JudgmentSummary
        decision={{
          id: "value-600887",
          symbol: "600887",
          strategy: "CORE_VALUE",
          price_action_plan: {
            action: "no_order",
            signal_state: "WATCH",
            entry_trigger_price: null,
            invalidation_price: null,
            reference_close: "27.96",
            market_trade_date: "2026-10-15",
            counter: ["模型有效性尚未通过"],
          },
        }}
        personalContext={<section>当前个人持仓摘要</section>}
      />,
    );
    expect(html.indexOf("本人当前价格政策")).toBeLessThan(
      html.indexOf("查看待确认价格政策"),
    );
    const visible = html.split("<details>")[0];
    expect(visible).toContain("当前判断：");
    expect(visible).toContain("关键价格：");
    expect(visible).toContain("27.96");
    expect(visible).toContain("核心风险：");
    expect(visible).toContain("模型有效性尚未通过");
    expect(html.indexOf("核心风险：")).toBeLessThan(
      html.indexOf("当前个人持仓摘要"),
    );
    expect(html.indexOf("当前个人持仓摘要")).toBeLessThan(
      html.indexOf("本人当前价格政策"),
    );
    expect(html).toContain("外部估值审核交接");
    expect(html).not.toContain("本人政策已登记");
    expect(html).toContain("<details><summary>公共研究计划与资格");
  });
  it("renders four hotspot actions with observation and holding restrictions", () => {
    const rules = Object.fromEntries(
      ["OPEN", "ADD", "REDUCE", "EXIT"].map((action) => [
        action,
        {
          rule: `${action}后端规则`,
          price: action === "REDUCE" ? null : "12.30",
          observed: action === "EXIT",
          requires_existing_holding: action !== "OPEN",
        },
      ]),
    );
    const html = renderToStaticMarkup(
      <JudgmentSummary
        decision={{
          id: "hotspot",
          strategy: "HOTSPOT_SATELLITE",
          price_action_plan: {
            action: "no_order",
            signal_state: "WATCH",
            entry_trigger_price: null,
            invalidation_price: null,
            conditional_action_rules: rules,
            price_behavior: {
              observation_quality: "INSUFFICIENT_UPPER_SPACE",
              breakout: {},
              pullback_recovery: {},
              auxiliary_15m: {},
            },
          } as any,
        }}
      />,
    );
    for (const action of ["OPEN", "ADD", "REDUCE", "EXIT"])
      expect(html).toContain(`${action}后端规则`);
    expect(html).toContain("无适用价格");
    expect(html).toContain("已观察，仍非操作许可");
    expect(html).toContain("仅适用于已有持仓");
    expect(html).toContain("当前上方结构空间不足");
  });
  it.each([true, false])(
    "merges identical exit and invalidation text but retains distinct review conditions (same=%s)",
    (same) => {
      const exit = "后续完成收盘低于24.700时，重新研究";
      const invalidation = same ? exit : "原投资论点被新证据推翻";
      const html = renderToStaticMarkup(
        <JudgmentSummary
          decision={{
            id: "hotspot-300364",
            symbol: "300364",
            strategy: "hotspot",
            price_action_plan: {
              action: "no_order",
              signal_state: "WATCH",
              action_eligibility: false,
              entry_trigger_price: "27.880",
              invalidation_price: "24.700",
              exit_condition: exit,
              invalidation_condition: invalidation,
              hold_condition: "现金转换与品牌力不恶化则维持原论点",
              reduce_condition: "组合风险超限须单独复核",
            },
          }}
        />,
      );
      const summary = html.split("展开完整条件")[0];
      expect(summary.split(exit)).toHaveLength(2);
      expect(summary).toContain(
        same ? "退出复核 / 结构失效" : "结构失效：原投资论点被新证据推翻",
      );
      expect(summary).toContain("减仓复核：组合风险超限须单独复核");
      expect(summary).toContain("持有条件：现金转换与品牌力不恶化则维持原论点");
      expect(summary).toContain("证券资格：未核验");
      expect(summary).toContain("个人组合：未核验");
    },
  );

  it("orders six questions and keeps observed trigger separate from formal and personal eligibility", () => {
    const decision: DecisionItem = {
      id: "test",
      symbol: "300308",
      strategy: "HOTSPOT_SATELLITE",
      price_action_plan: {
        action: "no_order",
        signal_state: "TRIGGER_OBSERVED",
        action_eligibility: false,
        formal_eligibility: false,
        portfolio_eligibility: null,
        entry_trigger_price: "100",
        invalidation_price: "90",
        next_session_date: "2026-10-15",
      },
    };
    const html = renderToStaticMarkup(<JudgmentSummary decision={decision} />);
    const labels = [
      "1. 当前判断",
      "2. 观察入场条件",
      "3. 退出或失效条件",
      "4. 为什么关注",
      "5. 主要风险",
      "6. 下一步",
    ];
    labels.forEach((label, index) => {
      expect(html).toContain(label);
      if (index)
        expect(html.indexOf(label)).toBeGreaterThan(
          html.indexOf(labels[index - 1]),
        );
    });
    expect(html).toContain("证券资格：未通过");
    expect(html).toContain("个人组合：未核验");
    expect(html).toContain("2026-10-15");
    expect(html).toContain("观察价 100");
    expect(html).not.toMatch(/<details[^>]*\bopen/);
  });

  it("does not turn valuation scenarios into entry prices when no policy exists", () => {
    const html = renderToStaticMarkup(
      <JudgmentSummary
        decision={{
          id: "value",
          strategy: "CORE_VALUE",
          price_action_plan: {
            action: "no_order",
            signal_state: "WATCH",
            action_eligibility: false,
            entry_trigger_price: null,
            invalidation_price: null,
            bear: "9.8",
            base: "10.1",
            bull: "10.3",
          },
        }}
      />,
    );
    expect(html.split("展开完整条件")[0]).toContain("尚无获准入场价");
    expect(html.split("展开完整条件")[0]).not.toContain("观察价 10.1");
  });
});

describe("read-only policy and replay review", () => {
  it("shows model, validity and rationale while four unselected action prices remain unknown", () => {
    state.error = null;
    state.data = {
      action: "no_order",
      model_review: { findings: [] },
      draft: {
        rationale: "由本人选择明确比例",
        basis: { model_version: "registered-v2" },
        effective_from: "2026-10-15",
        effective_through: "2026-11-14",
      },
      preparation: {
        status: "BLOCKED",
        draft_prices: { open: null, add: null, reduce: null, exit: null },
      },
    };
    const html = renderToStaticMarkup(<ValuePolicyReview symbol="600887" />);
    expect(html).toContain("查看待确认价格政策");
    expect(html).toContain("registered-v2");
    expect(html).toContain("2026-11-14");
    expect(html.match(/未形成（待明确动作规则与比例）/g)).toHaveLength(4);
    expect(html).not.toMatch(/<details[^>]*\bopen/);
    expect(html).toContain("读取本人授权的审核交接材料");
    expect(html).not.toContain("本人确认并不可变登记");
  });

  it("does not expose stale draft data after a binding error", () => {
    state.error = "hash mismatch";
    const html = renderToStaticMarkup(<ValuePolicyReview symbol="600887" />);
    expect(html).toContain("不能据此生成操作价");
    expect(html).not.toContain("registered-v2");
    state.error = null;
    state.data = null;
  });

  it("keeps proxy replay secondary and never invents a shadow session count", () => {
    const html = renderToStaticMarkup(<HotspotReplayReview />);
    expect(html).toContain("非实际成交");
    expect(html).toContain("不能当作个人真实成交亏损");
    expect(html).not.toContain("累计观察会话为 0");
    expect(html).not.toMatch(/<details[^>]*\bopen/);
  });

  it("shows retained signal followups separately from unverified trades", () => {
    state.error = null;
    state.data = {
      action: "no_order",
      computed_at: "2026-10-14",
      items: [],
      limitations: [],
      retained_validation: {
        partitions: {
          start_date: "2026-08-31",
          validation_start: "2026-09-14",
          end_date: "2026-10-14",
        },
        evaluated_at: "2026-10-21",
        items: [],
        signal_event_count: 161,
        mature_five_session_count: 150,
        right_censored_count: 11,
        trade_count: null,
        formal_eligibility: false,
        strategy_validation: "NOT_PROVEN",
      },
    };
    const html = renderToStaticMarkup(<HotspotReplayReview />);
    expect(html).toContain("161 次触发");
    expect(html).toContain("150 次完整五日随访");
    expect(html).toContain("11 次随访窗口尚未完整");
    expect(html).toContain("实际成交数：未核验");
    expect(html).toContain("不能据此判断策略净收益或批准买入");
    expect(html).toContain("下表仅列冻结验证窗口");
    expect(html).toContain("2026-09-14");
    state.error = "source drift";
    expect(renderToStaticMarkup(<HotspotReplayReview />)).not.toContain(
      "161 次触发",
    );
    state.data = null;
    state.error = null;
  });
});
