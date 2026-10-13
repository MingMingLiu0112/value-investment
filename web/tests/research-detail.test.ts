import { describe, expect, it } from "vitest";
import {
  blockerText,
  bridgeExecutionView,
  bridgeStatusLabel,
  compatibilityLadder,
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

describe("price bridge execution view", () => {
  it("translates the shared admission status without hiding the code", () => {
    const view = bridgeExecutionView({
      schema_version: "quote-bridge-execution-v1",
      status: "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
      reason: "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性",
      next_step:
        "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
      price_admitted: false,
      comparison_eligible: false,
      quote_date: "2026-10-12",
      display_price: "27.96",
      collected_at: "2026-10-12T09:23:13+00:00",
      display_scope: "LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
      is_historical_close: true,
      latest_completed_session: "2026-10-12",
      bundle_path: "runtime/quote-sessions/x/bundle.json",
      bundle_sha256: "a".repeat(64),
      research_day: "2026-10-11",
      research_version: "pending-600887-2026-10-11-x",
      pointer_path: "config/current-quote-bridge.json",
      pointer_sha256: "b".repeat(64),
      sources: [
        {
          provider: "tencent",
          source_url: "https://qt.gtimg.cn/q=sh600887",
          fetched_at: "2026-10-12T09:23:12+00:00",
          sha256: "c".repeat(64),
        },
      ],
    });
    expect(view?.statusLabel).toBe("行情已核验，但晚于研究截止日");
    expect(view?.comparableLabel).toBe("尚不具备比较资格");
    expect(view?.rows).toContainEqual({
      key: "display_price",
      label: "已核验收盘价",
      value: "27.96 元",
    });
    expect(view?.rows).toContainEqual({
      key: "research_day",
      label: "研究截止日",
      value: "2026-10-11",
    });
    expect(view?.sources).toEqual([
      {
        label: "tencent",
        url: "https://qt.gtimg.cn/q=sh600887",
        sha256: "c".repeat(64),
      },
    ]);
  });

  it("keeps unknown statuses verbatim and reports missing fields explicitly", () => {
    expect(bridgeStatusLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(bridgeStatusLabel(null)).toBe("未提供");
    const view = bridgeExecutionView({
      schema_version: "quote-bridge-execution-v1",
      status: "POINTER_UNAVAILABLE",
      reason: null,
      next_step: null,
      price_admitted: false,
      comparison_eligible: false,
      quote_date: null,
      display_price: null,
      collected_at: null,
      display_scope: null,
      is_historical_close: null,
      latest_completed_session: null,
      bundle_path: null,
      bundle_sha256: null,
      research_day: null,
      research_version: null,
      pointer_path: null,
      pointer_sha256: null,
      sources: [],
    });
    expect(view?.statusLabel).toBe("未登记当前行情绑定");
    expect(view?.rows.every((row) => row.value === "未提供")).toBe(true);
    expect(view?.sources).toEqual([]);
    expect(bridgeExecutionView(null)).toBeNull();
  });

  it("marks a comparison eligible only when the shared bridge says so", () => {
    const view = bridgeExecutionView({
      schema_version: "quote-bridge-execution-v1",
      status: "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
      reason: null,
      next_step: null,
      price_admitted: true,
      comparison_eligible: true,
      quote_date: "2026-10-12",
      display_price: "27.96",
      collected_at: null,
      display_scope: null,
      is_historical_close: false,
      latest_completed_session: null,
      bundle_path: null,
      bundle_sha256: null,
      research_day: "2026-10-12",
      research_version: null,
      pointer_path: null,
      pointer_sha256: null,
      sources: [],
    });
    expect(view?.comparable).toBe(true);
    expect(view?.comparableLabel).toBe("已具备比较资格");
  });

  it("keeps the compatibility ladder steps separate and hides absent ones", () => {
    const ladder = compatibilityLadder({
      verified_quote: { eligible: true, reason: "双源核验通过" },
      research_compatible: { eligible: false, reason: "报价晚于研究截止日" },
      comparison_eligible: { eligible: false, reason: "尚未准入" },
      formal_decision_eligible: { eligible: false, reason: "需人工门" },
    });
    expect(ladder.map((row) => row.key)).toEqual([
      "verified_quote",
      "research_compatible",
      "comparison_eligible",
      "formal_decision_eligible",
    ]);
    expect(ladder[0].eligible).toBe(true);
    expect(ladder[1].reason).toBe("报价晚于研究截止日");
    expect(compatibilityLadder(null)).toEqual([]);
    expect(compatibilityLadder(undefined)).toEqual([]);
  });
});
