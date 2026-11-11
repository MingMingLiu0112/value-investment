import { describe, expect, it } from "vitest";
import type { ResearchComparison } from "../src/types/api";
import { comparisonSummary, shortDigest } from "../src/utils/history";

describe("history comparison wording", () => {
  it("stays honest when nothing changed", () => {
    const comparison: ResearchComparison = {
      status: "COMPARED",
      observation: "UNCHANGED",
      changed_fields: [],
    };
    expect(comparisonSummary(comparison)).toBe("已比较：未发现字段变化");
  });

  it("reports the mechanical count of changed fields", () => {
    const comparison: ResearchComparison = {
      status: "COMPARED",
      observation: "EVIDENCE_UPDATED",
      changed_fields: ["income_growth", "choices"],
    };
    expect(comparisonSummary(comparison)).toBe("已比较：发现 2 个字段变化");
  });

  it("never claims a comparison when only one version exists", () => {
    const comparison: ResearchComparison = {
      status: "PREVIOUS_UNAVAILABLE",
      observation: "UNKNOWN",
    };
    expect(comparisonSummary(comparison)).toBe(
      "只有一个可复算版本，暂无法比较",
    );
  });

  it("shortens digests to twelve characters without padding short input", () => {
    expect(shortDigest("a".repeat(64))).toBe("a".repeat(12));
    expect(shortDigest("abc")).toBe("abc");
    expect(shortDigest(null)).toBeNull();
  });
});
