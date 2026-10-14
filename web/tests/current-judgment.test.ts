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
  publicationVersionsMatch,
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

describe("backend current judgment boundaries", () => {
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
