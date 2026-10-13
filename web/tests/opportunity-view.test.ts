import { describe, expect, it } from "vitest";
import {
  firstResearchText,
  publicBlockerText,
  strategyCounts,
} from "../src/utils/opportunityView";

describe("strategyCounts", () => {
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
