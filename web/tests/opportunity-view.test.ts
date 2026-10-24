import { describe, expect, it } from "vitest";
import {
  firstResearchText,
  hasValuationResult,
  publicBlockerText,
  strategyCounts,
} from "../src/utils/opportunityView";

describe("strategyCounts", () => {
  it("groups retained valuation results by data rather than symbol or research status", () => {
    const plan = {
      action: "no_order" as const,
      signal_state: "WATCH",
      entry_trigger_price: null,
      invalidation_price: null,
      conditional_valuation_range: { bear: "9.8", base: "10.08", bull: "10.3" },
    };
    expect(
      hasValuationResult({
        id: "new-company",
        symbol: "123456",
        price_action_plan: plan,
      }),
    ).toBe(true);
    expect(
      hasValuationResult({
        id: "600887",
        price_action_plan: { ...plan, conditional_valuation_range: null },
      }),
    ).toBe(false);
    expect(
      hasValuationResult({
        id: "bad",
        price_action_plan: {
          ...plan,
          conditional_valuation_range: {
            bear: "9.8",
            base: "NaN",
            bull: "10.3",
          },
        },
      }),
    ).toBe(false);
    expect(
      hasValuationResult({
        id: "new-contract",
        price_action_plan: {
          ...plan,
          conditional_valuation_range: null,
          bear: "9.8",
          base: "10.08",
          bull: "10.3",
        },
      }),
    ).toBe(true);
  });
  it("never promotes research or a price observation to formal action", () => {
    expect(
      strategyCounts([
        { id: "a", status: "RESEARCH_ONLY", candidate_action: "BUY_CANDIDATE" },
        { id: "b", status: "TRIGGER_PENDING" },
        { id: "c", status: "FORMALLY_ADMITTED_REVIEW" },
      ]),
    ).toEqual({ formal: 1, pending: 1, watch: 1 });
  });
});

describe("compact research text", () => {
  it("reads only statement text, not evidence metadata", () => {
    expect(
      firstResearchText([{ text: "现金流需要核验", evidence_refs: ["e1"] }]),
    ).toBe("现金流需要核验");
    expect(firstResearchText([{ evidence_refs: ["e1"] }])).toBeNull();
  });

  it("keeps unknown gate codes off the public card", () => {
    expect(publicBlockerText("RUN_DATA_HEALTH_INCOMPLETE")).toBeNull();
    expect(publicBlockerText("待核验分红记录")).toBe("待核验分红记录");
  });
});
