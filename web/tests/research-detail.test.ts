import { describe, expect, it } from "vitest";
import {
  blockerText,
  formatScenarioValue,
  gateRowViews,
  gateStatusLabel,
  marginText,
  normalizeEvidenceLines,
  splitReadingOrder,
  suggestedStateText,
  uniqueBlockerTexts,
  unknownText,
} from "../src/utils/researchDetail";

describe("research detail helpers", () => {
  it("maps gate statuses to friendly labels", () => {
    expect(gateStatusLabel("PASS")).toBe("已通过");
    expect(gateStatusLabel("BLOCKED")).toBe("未通过");
    expect(gateStatusLabel("CONDITIONAL")).toBe("有条件");
    expect(gateStatusLabel(null)).toBe("未提供");
    expect(gateStatusLabel("UNKNOWN")).toBe("UNKNOWN");
  });

  it("keeps the frozen gate order and fills missing rows", () => {
    const views = gateRowViews([
      null,
      {
        key: "business_quality",
        status: "PASS",
        reason: "已绑定商业论点",
        next_action: "继续复核",
        evidence_refs: [],
      },
    ]);
    expect(views).toHaveLength(8);
    expect(views[0]).toMatchObject({
      key: "financial_facts",
      statusLabel: "未提供",
    });
    expect(views[1]).toMatchObject({
      label: "商业质量",
      statusLabel: "已通过",
      reason: "已绑定商业论点",
    });
    expect(gateRowViews(null)).toHaveLength(8);
  });

  it("rounds scenario values for display and falls back when absent", () => {
    expect(
      formatScenarioValue("9.79764118439777680597278298395676515182872214703"),
    ).toBe("9.80");
    expect(
      formatScenarioValue("10.0751373530680129477021471870066470782479712991"),
    ).toBe("10.08");
    expect(formatScenarioValue(null)).toBe("暂不可用");
    expect(formatScenarioValue(undefined)).toBe("暂不可用");
    expect(formatScenarioValue("")).toBe("暂不可用");
    expect(formatScenarioValue("not-a-number")).toBe("not-a-number");
  });

  it("shows margins only when a value is present", () => {
    expect(marginText(null)).toBeNull();
    expect(marginText(undefined)).toBeNull();
    expect(marginText("")).toBeNull();
    expect(marginText("-0.1205")).toBe("-0.1205");
  });

  it("translates the no-action state and keeps unknown values raw", () => {
    expect(suggestedStateText("NO_ACTION")).toBe("当前无合法动作候选");
    expect(suggestedStateText("no_order")).toBe("当前无合法动作候选");
    expect(suggestedStateText(null)).toBe("未提供");
    expect(suggestedStateText("WATCH")).toBe("WATCH");
  });

  it("rewrites known blockers without guessing unknown text", () => {
    expect(
      blockerText(
        "research_case:formal G3 human valuation approval not present",
      ),
    ).toBe("缺少正式 G3 人工估值批准");
    expect(blockerText("等待已验证收盘行情")).toBe("等待已验证的收盘行情");
    expect(blockerText("some new blocker")).toBe("some new blocker");
    expect(blockerText("   ")).toBe("未提供");
  });

  it("normalizes support lines from legacy and current shapes", () => {
    expect(
      normalizeEvidenceLines([
        "旧版字符串",
        {
          kind: "fact",
          text: "增长",
          evidence_refs: ["ref-1", 2],
        },
      ]),
    ).toEqual([
      { text: "旧版字符串", evidenceRefs: [] },
      { text: "增长", evidenceRefs: ["ref-1"] },
    ]);
    expect(normalizeEvidenceLines(null)).toEqual([]);
    expect(normalizeEvidenceLines({ kind: "fact" })).toEqual([]);
  });

  it("splits the reading order at the requested limit", () => {
    const rows = Array.from({ length: 10 }, (_, index) => ({
      label: `L${index}`,
      value: `V${index}`,
    }));
    const { leading, trailing } = splitReadingOrder(rows);
    expect(leading).toHaveLength(8);
    expect(trailing.map((row) => row.label)).toEqual(["L8", "L9"]);
    expect(splitReadingOrder(null).leading).toEqual([]);
    expect(splitReadingOrder(rows, 0).leading).toEqual([]);
  });

  it("renders unknown technical values without inventing them", () => {
    expect(unknownText(null)).toBe("未提供");
    expect(unknownText("text")).toBe("text");
    expect(unknownText("   ")).toBe("未提供");
    expect(unknownText({ a: 1 })).toBe('{"a":1}');
  });

  it("drops the research_case duplicate of a blocker but keeps the order", () => {
    expect(
      uniqueBlockerTexts([
        "formal G3 human valuation approval not present",
        "ROIC and incremental ROIC remain unverified",
        "research_case:formal G3 human valuation approval not present",
        "G3_估值门",
        "ROIC and incremental ROIC remain unverified",
      ]),
    ).toEqual([
      "缺少正式 G3 人工估值批准",
      "ROIC 与增量 ROIC 尚未核验",
      "G3 估值门尚未通过",
    ]);
    expect(uniqueBlockerTexts([])).toEqual([]);
  });
});
