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
  nextActionLines,
  normalizeEvidenceLines,
  researchHeadline,
  splitReadingOrder,
  suggestedStateText,
  uniqueBlockerTexts,
  unknownText,
} from "../src/utils/researchDetail";

/** TEST_ONLY mapping DTO: not a real approved company or a production READY. */
function asofTestExecution(): any {
  const scope = {
    scope: "CURRENT_AS_OF_SNAPSHOT_V1",
    action: "no_order",
    observed_at: "2026-10-24T09:10:00+08:00",
    knowledge_as_of: "2026-10-24T09:12:00+08:00",
    full_calendar_window_elapsed: false,
    strict_contemporaneous_pit: false,
    formal_eligibility: false,
    strategy_approval_granted: false,
    research_comparison_only: true,
  };
  return {
    ...scope,
    schema_version: "quote-bridge-execution-v1",
    status: "QUOTE_VERIFIED_WITH_CURRENT_ASOF_SNAPSHOT",
    price_admitted: true,
    comparison_eligible: true,
    research_day: "2026-10-11",
    quote_date: "2026-10-23",
    sources: [],
    current_snapshot_validity: {
      ...scope,
      schema_version: "current-snapshot-validity-result-v1",
      symbol: "600887",
      status: "VALID_AS_OF_SNAPSHOT",
      usable_for_research_comparison: true,
      g3_approval_granted: false,
      blockers: [],
    },
    current_event_coverage: {
      ...scope,
      status: "CURRENT_AS_OF_SNAPSHOT",
      required_through: "2026-10-24",
      query_through: "2026-10-24",
      covered_through: null,
    },
    compatibility: {
      research_compatible: { eligible: true },
      comparison_eligible: { eligible: true },
      formal_decision_eligible: { eligible: false },
    },
  };
}

describe("TEST_ONLY current-asof scope mapping, not real approval", () => {
  it("keeps knowledge/observation/research/quote dates distinct without whole-day or PIT claims", () => {
    const view = bridgeExecutionView(asofTestExecution(), "600887")!;
    expect(view.comparable).toBe(true);
    expect(view.snapshotScope?.verified).toBe(true);
    expect(view.comparableLabel).toContain("不是买卖许可");
    expect(view.rows.find((r) => r.key === "snapshot_observed")?.value).toBe(
      "2026-10-24T09:10:00+08:00",
    );
    expect(view.rows.find((r) => r.key === "snapshot_knowledge")?.value).toBe(
      "2026-10-24T09:12:00+08:00",
    );
    expect(view.rows.find((r) => r.key === "research_day")?.value).toBe(
      "2026-10-11",
    );
    expect(view.quoteDate).toBe("2026-10-23");
    expect(view.rows.some((r) => r.key === "current_event_covered")).toBe(
      false,
    );
    expect(view.snapshotScope?.notice).toContain("不是全天公告覆盖");
    expect(view.snapshotScope?.notice).toContain("不证明历史 PIT");
    expect(
      view.ladder.find((r) => r.key === "formal_decision_eligible")?.eligible,
    ).toBe(false);
    const headline = researchHeadline({
      bridge: view,
      valuation: { base: "10", valuation_date: "2026-10-20" },
    });
    expect(headline).toContain("估值日 2026-10-20");
    expect(headline).toContain("原研究截止 2026-10-11");
    expect(headline).toContain("截至已采集时点");
    expect(headline).not.toContain("行情在研究覆盖范围内");
  });

  it.each([
    [
      "missing scope",
      (v: any) => {
        delete v.scope;
      },
    ],
    [
      "unknown scope",
      (v: any) => {
        v.scope = "UNKNOWN_VERSION";
      },
    ],
    [
      "unknown schema",
      (v: any) => {
        v.schema_version = "UNKNOWN_VERSION";
      },
    ],
    [
      "missing snapshot",
      (v: any) => {
        delete v.current_snapshot_validity;
      },
    ],
    [
      "missing coverage",
      (v: any) => {
        delete v.current_event_coverage;
      },
    ],
    [
      "unknown snapshot status",
      (v: any) => {
        v.current_snapshot_validity.status = "READY";
      },
    ],
    [
      "formal authority",
      (v: any) => {
        v.formal_eligibility = true;
      },
    ],
    [
      "strategy authority",
      (v: any) => {
        v.strategy_approval_granted = true;
      },
    ],
    [
      "inner authority",
      (v: any) => {
        v.current_snapshot_validity.g3_approval_granted = true;
      },
    ],
    [
      "full day",
      (v: any) => {
        v.full_calendar_window_elapsed = true;
      },
    ],
    [
      "PIT",
      (v: any) => {
        v.strict_contemporaneous_pit = true;
      },
    ],
    [
      "covered day",
      (v: any) => {
        v.current_event_coverage.covered_through = "2026-10-24";
      },
    ],
    [
      "missing knowledge",
      (v: any) => {
        delete v.knowledge_as_of;
      },
    ],
    [
      "bad time",
      (v: any) => {
        v.observed_at = "2026-10-24";
      },
    ],
    [
      "invalid date",
      (v: any) => {
        v.observed_at = "2026-02-30T09:10:00+08:00";
      },
    ],
    [
      "mixed observation",
      (v: any) => {
        v.current_event_coverage.observed_at = "2026-10-24T09:15:00+08:00";
      },
    ],
    [
      "wrong symbol",
      (v: any) => {
        v.current_snapshot_validity.symbol = "600519";
      },
    ],
    [
      "false READY",
      (v: any) => {
        v.comparison_eligible = false;
      },
    ],
    [
      "quote not admitted",
      (v: any) => {
        v.price_admitted = false;
      },
    ],
    [
      "missing scope restriction",
      (v: any) => {
        delete v.research_comparison_only;
      },
    ],
    [
      "formal ladder",
      (v: any) => {
        v.compatibility.formal_decision_eligible.eligible = true;
      },
    ],
  ])(
    "does not turn %s into comparison/transaction eligibility",
    (_, mutate) => {
      const dto = asofTestExecution();
      mutate(dto);
      const view = bridgeExecutionView(dto, "600887")!;
      expect(view.comparable).toBe(false);
      expect(view.comparableLabel).not.toContain(
        "仅具备已采集时点研究比较资格",
      );
      expect(
        view.ladder.find((r) => r.key === "formal_decision_eligible")?.eligible,
      ).toBe(false);
      expect(
        view.ladder.find((r) => r.key === "comparison_eligible")?.eligible,
      ).toBe(false);
    },
  );

  it("accepts equivalent explicit instants and never consults a browser clock", () => {
    const dto = asofTestExecution();
    dto.current_snapshot_validity.observed_at = "2026-10-24T01:10:00Z";
    expect(bridgeExecutionView(dto, "600887")?.comparable).toBe(true);
  });
});

it("separates partial current event coverage from retained price comparison and historical model status", () => {
  const execution = {
    schema_version: "TEST_ONLY",
    status: "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
    comparison_eligible: true,
    quote_date: "2026-10-23",
    research_day: "2026-10-11",
    sources: [],
    incremental_validity: {
      status: "VALID",
      review_cutoff: "2026-10-24",
      announcement_count: 0,
      blockers: [],
    },
    current_event_coverage: {
      required_through: "2026-10-24",
      query_through: "2026-10-24",
      covered_through: null,
      observed_at: "2026-10-24T10:20:00+08:00",
      full_calendar_window_elapsed: false,
      status: "PARTIAL_CURRENT_SNAPSHOT",
    },
    historical_model_validity: { status: "VALID" },
  };
  const view = bridgeExecutionView(execution as any)!;
  expect(view.comparable).toBe(true);
  expect(view.quoteDate).toBe("2026-10-23");
  expect(view.rows.find((row) => row.key === "research_day")?.value).toBe(
    "2026-10-11",
  );
  expect(
    view.rows.find((row) => row.key === "current_event_status")?.value,
  ).toContain("partial");
  expect(
    view.rows.find((row) => row.key === "current_event_observed")?.value,
  ).toBe("2026-10-24T10:20:00+08:00");
  expect(
    view.rows.find((row) => row.key === "incremental_status")?.value,
  ).toContain("UNKNOWN");
  expect(
    view.rows.find((row) => row.key === "historical_model_validity")?.value,
  ).toBe("VALID");
  expect(
    view.rows.find((row) => row.key === "current_event_covered")?.value,
  ).toBe("未确认完整覆盖");
});

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
  const staleExecution = {
    schema_version: "quote-bridge-execution-v1",
    status: "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
    reason: "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性",
    next_step:
      "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
    price_admitted: false,
    comparison_eligible: false,
    quote_date: "2026-10-13",
    display_price: "27.77",
    collected_at: "2026-10-13T09:50:38+00:00",
    display_scope: null,
    is_historical_close: null,
    latest_completed_session: "2026-10-13",
    bundle_path: null,
    bundle_sha256: null,
    research_day: "2026-10-11",
    research_version: null,
    pointer_path: null,
    pointer_sha256: null,
    sources: [],
  };

  it("exposes the quote date and price next to the ladder", () => {
    const view = bridgeExecutionView(staleExecution);
    expect(view?.quoteDate).toBe("2026-10-13");
    expect(view?.displayPrice).toBe("27.77");
  });

  it("shows incremental coverage without upgrading pending materiality or rewriting original cutoff", () => {
    const view = bridgeExecutionView({
      ...staleExecution,
      status: "INCREMENTAL_VALIDITY_BLOCKED",
      incremental_validity: {
        status: "UNKNOWN",
        review_cutoff: "2026-10-15",
        announcement_count: 2,
        blockers: ["pending_complete_event_materiality_review"],
      },
    });
    expect(view?.comparable).toBe(false);
    expect(view?.rows.find((row) => row.key === "research_day")?.value).toBe(
      "2026-10-11",
    );
    expect(
      view?.rows.find((row) => row.key === "incremental_cutoff")?.value,
    ).toBe("2026-10-15");
    expect(
      view?.rows.find((row) => row.key === "incremental_announcements")?.value,
    ).toBe("2");
    expect(
      view?.rows.find((row) => row.key === "incremental_blockers")?.value,
    ).toContain("materiality");
  });

  it("generates the one-line conclusion from the real bridge state", () => {
    const headline = researchHeadline({
      valuation: {
        bear: "9.79764118439777680597278298395676515182872214703",
        base: "10.0751373530680129477021471870066470782479712991",
        bull: "10.3006925009950307944059171660835859543186976072",
        valuation_date: "2026-10-11",
      },
      bridge: bridgeExecutionView(staleExecution),
    });
    expect(headline).toContain("已有条件性估值研究");
    expect(headline).toContain("基准 10.08 元");
    expect(headline).toContain("2026-10-13");
    expect(headline).toContain("27.77 元");
    expect(headline).toContain("晚于研究截止日");
    expect(headline).not.toContain("安全边际：");
  });

  it("does not invent a safety margin when the price is not comparable", () => {
    const headline = researchHeadline({
      valuation: { base: "10.08", valuation_date: "2026-10-11" },
      bridge: bridgeExecutionView(staleExecution),
      marginToBase: "18%",
    });
    expect(headline).not.toContain("18%");
  });

  it("states the comparable case without upgrading it to a buy signal", () => {
    const headline = researchHeadline({
      valuation: { base: "10.08", valuation_date: "2026-10-12" },
      bridge: bridgeExecutionView({
        ...staleExecution,
        status: "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
        price_admitted: true,
        comparison_eligible: true,
        next_step: null,
      }),
      marginToBase: "-0.1205",
    });
    expect(headline).toContain("可以合法比较");
    expect(headline).toContain("安全边际：-0.1205");
    expect(headline).toContain("正式买卖仍需通过人工与决策门禁");
  });

  it("reports the honest gaps when valuation or quotes are missing", () => {
    expect(researchHeadline({ valuation: {} })).toContain("尚无可用估值研究");
    const noBridge = researchHeadline({
      valuation: { base: "10.08", valuation_date: "2026-10-11" },
    });
    expect(noBridge).toContain("尚未登记经核验的收盘行情");
  });

  it("builds the next-step list from published next_step and next_action only", () => {
    const gates = [
      {
        label: "财务事实",
        status: "PASS",
        statusLabel: "已通过",
        nextAction: "复核对应依赖证据与批准结果。",
      },
      {
        label: "估值",
        status: "CONDITIONAL",
        statusLabel: "有条件",
        nextAction: "继续核验假设、反证和模型有效性。",
      },
      {
        label: "研究门",
        status: "BLOCKED",
        statusLabel: "未通过",
        nextAction: "复核对应依赖证据与批准结果。",
      },
      {
        label: "组合门",
        status: "BLOCKED",
        statusLabel: "未通过",
        nextAction: "补齐真实 IPS 与组合输入。",
      },
    ];
    const lines = nextActionLines(
      gates,
      "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
    );
    expect(lines[0]).toContain("先完成研究重登记与事件复核");
    expect(lines).toContain("继续核验假设、反证和模型有效性。（估值）");
    expect(lines).toContain("复核对应依赖证据与批准结果。（研究门）");
    expect(lines).toContain("补齐真实 IPS 与组合输入。（组合门）");
    expect(lines.every((line) => !line.includes("财务事实"))).toBe(true);
    expect(nextActionLines([], null)).toEqual([]);
  });

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
