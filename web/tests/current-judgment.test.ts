import { describe, expect, it } from "vitest";
import type {
  CurrentPriceCase,
  CurrentPricePlan,
  DecisionItem,
} from "../src/types/api";
import {
  currentCaseMatches,
  fillLink,
  judgmentGroup,
  hotspotOpportunityQuality,
  publicationVersionsMatch,
  planConditionText,
} from "../src/utils/currentJudgment";

const plan: CurrentPricePlan = {
  action: "no_order",
  signal_state: "TRIGGER_OBSERVED",
  action_eligibility: false,
  entry_trigger_price: "12.30",
  invalidation_price: "11.20",
  current_reference_price: "12.50",
  market_trade_date: "2026-10-13",
  decision_id: "case/1",
  research_version: "version/1",
};
const item: DecisionItem = {
  id: "case/1",
  symbol: "000001",
  strategy: "HOTSPOT_SATELLITE",
  price_action_plan: plan,
};
const value: CurrentPriceCase = {
  action: "no_order",
  symbol: "000001",
  market_trade_date: "2026-10-13",
  current_reference_price: "12.50",
  bars: {},
  levels: {},
  price_action_plan: plan,
};

describe("independent thesis and price conditions", () => {
  it.each([false, null, true])(
    "keeps price %s separate from a triggered thesis",
    (triggered) => {
      const text = planConditionText({
        kind: "POLICY_PRICE_REVIEW",
        price: "120",
        comparison: "GTE",
        triggered,
        thesis_review: {
          kind: "THESIS_REVIEW",
          triggered: true,
          reasons: ["核心论点已破坏", "现金回收假设失效"],
        },
      });
      expect(text).toContain("不低于 120");
      expect(text).toContain("独立论点条件已触发复核");
      expect(text).toContain("核心论点已破坏");
      expect(text).toContain("现金回收假设失效");
      expect(text).toContain("不是卖出指令");
      expect(text).toContain(
        triggered === true
          ? "价格条件已触发"
          : triggered === false
            ? "价格条件未触发"
            : "价格条件尚不能判断",
      );
    },
  );

  it("does not invent a thesis trigger for an untriggered or malformed condition", () => {
    const text = planConditionText({
      price: "120",
      triggered: true,
      thesis_review: {
        kind: "THESIS_REVIEW",
        triggered: false,
        reasons: ["原退出条件尚未发生"],
      },
    });
    expect(text).toContain("独立论点条件未触发");
    expect(text).not.toContain("论点条件已触发");
    expect(
      planConditionText({
        price: "120",
        thesis_review: { triggered: true, reasons: ["unbound"] },
      }),
    ).not.toContain("unbound");
  });
});

describe("backend current judgment boundaries", () => {
  it.each([
    ["下降趋势", { daily_trend: "DOWNTREND" }, {}, "A"],
    ["空间不足", { observation_quality: "INSUFFICIENT_UPPER_SPACE" }, {}, "A"],
    [
      "量能不满足",
      {},
      { period_structure: { "60m": "PRICE_ABOVE_VOLUME_PENDING" } },
      "C",
    ],
    ["等待确认", {}, {}, "B"],
    [
      "有效条件计划",
      { breakout: { confirmed_on_next_completed_bar: true } },
      {},
      "D",
    ],
    ["回踩恢复", { pullback_recovery: { observed: true } }, {}, "D"],
    ["已失效", {}, { signal_state: "TRIGGER_REJECTED" }, "E"],
    ["保护结构失效", { structural_invalidation: true }, {}, "E"],
    [
      "过期",
      { breakout: { confirmed_on_next_completed_bar: true } },
      { signal_state: "STALE" },
      null,
    ],
    ["空间未知", { observation_quality: "UNKNOWN" }, {}, null],
    ["日线未知", { daily_trend: "UNKNOWN" }, {}, null],
    ["计划阻塞", {}, { signal_state: "BLOCKED" }, null],
  ])(
    "classifies %s using existing observations without granting BUY",
    (_label, behavior, patch, expected) => {
      const candidate = {
        ...item,
        price_action_plan: {
          ...plan,
          ...patch,
          price_behavior: {
            daily_trend: "UPTREND",
            observation_quality: "RESEARCH_ONLY",
            ...behavior,
          },
        },
      } as DecisionItem;
      const before = JSON.stringify(candidate);
      expect(hotspotOpportunityQuality(candidate)?.code).toBe(expected);
      expect(JSON.stringify(candidate)).toBe(before);
      expect(candidate.price_action_plan?.action_eligibility).toBe(false);
    },
  );
  it("requires both price boundaries for D and does not classify value research", () => {
    expect(
      hotspotOpportunityQuality({ ...item, strategy: "CORE_VALUE" }),
    ).toBeNull();
    expect(
      hotspotOpportunityQuality({
        ...item,
        price_action_plan: {
          ...plan,
          invalidation_price: null,
          price_behavior: {
            daily_trend: "UPTREND",
            observation_quality: "RESEARCH_ONLY",
            breakout: { confirmed_on_next_completed_bar: true },
          } as any,
        },
      })?.code,
    ).not.toBe("D");
  });
  it("does not present a local breakout against a declining daily trend as an entry candidate", () => {
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          price_behavior: {
            daily_trend: "DOWNTREND",
          } as CurrentPricePlan["price_behavior"],
        },
      }),
    ).toBe(5);
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          price_behavior: {
            observation_quality: "INSUFFICIENT_UPPER_SPACE",
          } as CurrentPricePlan["price_behavior"],
        },
      }),
    ).toBe(5);
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          signal_state: "STALE",
          price_behavior: {
            daily_trend: "DOWNTREND",
          } as CurrentPricePlan["price_behavior"],
        },
      }),
    ).toBe(4);
  });
  it("blocks interleaved daily and packet responses until publication identities match", () => {
    expect(publicationVersionsMatch("pub-new", "pub-old")).toBe(false);
    expect(publicationVersionsMatch(null, null)).toBe(false);
    expect(publicationVersionsMatch(undefined, undefined)).toBe(false);
    expect(publicationVersionsMatch("", "")).toBe(false);
    expect(publicationVersionsMatch("pub-new", "pub-new")).toBe(true);
  });
  it("keeps observed triggers separate from all-gate admission", () => {
    expect(
      judgmentGroup({
        ...item,
        status: "FORMALLY_ADMITTED_REVIEW",
        candidate_action: "BUY",
      }),
    ).toBe(1);
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          signal_state: "ACTION_ELIGIBLE",
          action_eligibility: false,
        },
      }),
    ).toBe(4);
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          signal_state: "ACTION_ELIGIBLE",
          action_eligibility: true,
        },
      }),
    ).toBe(0);
    expect(
      judgmentGroup({ id: "legacy", status: "FORMALLY_ADMITTED_REVIEW" }),
    ).toBe(3);
  });
  it("keeps unavailable, historical and rejected observations out of current admission", () => {
    for (const signal_state of [
      "HISTORICAL_OBSERVATION_NOT_ADMITTED",
      "STALE",
      "BLOCKED",
      "TRIGGER_REJECTED",
      "INVALIDATED",
    ]) {
      expect(
        judgmentGroup({
          ...item,
          price_action_plan: {
            ...plan,
            signal_state,
            action_eligibility: true,
          },
        }),
      ).toBe(4);
    }
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: {
          ...plan,
          signal_state: "WATCH",
          entry_trigger_price: null,
        },
      }),
    ).toBe(3);
    expect(
      judgmentGroup({
        ...item,
        price_action_plan: { ...plan, signal_state: "TRIGGER_PENDING" },
      }),
    ).toBe(2);
  });
  it("requires exact security, session, judgment, version and prices before showing chart", () => {
    expect(currentCaseMatches(item, value)).toBe(true);
    expect(currentCaseMatches(item, { ...value, symbol: "600887" })).toBe(
      false,
    );
    expect(
      currentCaseMatches(item, { ...value, market_trade_date: "2026-09-01" }),
    ).toBe(false);
    for (const change of [
      { research_version: "old" },
      { decision_id: "other" },
      { entry_trigger_price: "13" },
      { current_reference_price: "13" },
      { signal_state: "HISTORICAL_OBSERVATION_NOT_ADMITTED" },
    ]) {
      expect(
        currentCaseMatches(item, {
          ...value,
          price_action_plan: { ...plan, ...change },
        }),
      ).toBe(false);
    }
  });
  it("links the existing fill workflow using identity only, with no actual-fill defaults", () => {
    const query = new URLSearchParams(fillLink(item).split("?")[1]);
    expect(Object.fromEntries(query)).toEqual({
      symbol: "000001",
      strategy: "hotspot",
      decision_id: "case/1",
      research_version: "version/1",
    });
    expect(
      new URLSearchParams(
        fillLink({ id: "unknown", strategy: "unsupported" }).split("?")[1],
      ).has("strategy"),
    ).toBe(false);
  });
  it("preserves stable hotspot identifiers and does not substitute the symbol", () => {
    const stable = {
      ...item,
      id: "hotspot-000001",
      price_action_plan: { ...plan, decision_id: "hotspot-000001" },
    };
    expect(
      new URLSearchParams(fillLink(stable).split("?")[1]).get("decision_id"),
    ).toBe("hotspot-000001");
    expect(
      currentCaseMatches(stable, {
        ...value,
        price_action_plan: stable.price_action_plan,
      }),
    ).toBe(true);
  });
});
