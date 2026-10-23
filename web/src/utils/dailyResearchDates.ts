import type { DailyMachineResearchReview } from "../types/api";

/** Display only: coverage labels never grant investment or execution authority. */
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export function dailyMachineResearchReview(lastRun: unknown) {
  const raw = record(lastRun) ? lastRun.research_review : undefined;
  const empty = {
    checkedAt: null as string | null,
    reviewCutoff: null as string | null,
    rows: [] as DailyMachineResearchReview["rows"],
    label: "尚无可核验复核回执；不能由行情更新或软件发布时间推定",
  };
  if (!record(raw)) return empty;
  if (
    raw.status !== "SOURCE_REPLAYED" ||
    raw.action !== "no_order" ||
    raw.formal_eligibility !== false ||
    raw.scope !== "MACHINE_REVIEW_NOT_RESEARCH_APPROVAL" ||
    typeof raw.checked_at !== "string" ||
    !/(?:Z|[+-]\d{2}:\d{2})$/.test(raw.checked_at) ||
    Number.isNaN(new Date(raw.checked_at).getTime()) ||
    !Array.isArray(raw.rows) ||
    raw.rows.some(
      (row) =>
        !record(row) ||
        row.formal_eligibility !== false ||
        typeof row.symbol !== "string" ||
        !/^\d{6}$/.test(row.symbol),
    )
  )
    return {
      ...empty,
      label: "机器复核回执未通过来源核验，日期与逐证券结果暂不可用",
    };
  const rows: DailyMachineResearchReview["rows"] = raw.rows.map((row) => {
    const complete =
      row.event_coverage_status === "COMPLETE" &&
      !!day(row.event_coverage_through);
    return {
      symbol: row.symbol,
      status: typeof row.status === "string" ? row.status : "UNKNOWN",
      research_as_of: day(row.research_as_of),
      scan_through: day(row.scan_through),
      event_coverage_status: complete ? "COMPLETE" : "UNCONFIRMED",
      event_coverage_through: complete ? day(row.event_coverage_through) : null,
      announcement_count:
        Number.isInteger(row.announcement_count) && row.announcement_count >= 0
          ? row.announcement_count
          : null,
      facts_change_status:
        !complete && row.facts_change_status === "NONE"
          ? "UNKNOWN"
          : typeof row.facts_change_status === "string"
            ? row.facts_change_status
            : null,
      model_validity_status:
        !complete &&
        row.model_validity_status === "REVIEWED_NO_MODEL_INVALIDATION"
          ? "UNKNOWN"
          : typeof row.model_validity_status === "string"
            ? row.model_validity_status
            : null,
      model_recalculation_required:
        typeof row.model_recalculation_required === "boolean"
          ? row.model_recalculation_required
          : null,
      materiality_review_required:
        typeof row.materiality_review_required === "boolean"
          ? row.materiality_review_required
          : null,
      formal_eligibility: false,
    };
  });
  return {
    checkedAt: raw.checked_at,
    reviewCutoff: day(raw.review_cutoff),
    rows,
    label: "仅机器来源重放，不是人工经济审核或正式交易准入",
  };
}

function day(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
    ? value
    : null;
}

const coverage: Record<string, string> = {
  COVERS: "研究基准覆盖已登记报价；事件有效性仍须逐公司核验",
  INCREMENTALLY_COVERS: "增量复核支持条件性价格比较；原研究基准未改变",
  INCREMENTAL_REVIEW_PENDING: "已接入增量复核，尚有事件、模型或证据缺口",
  STALE: "研究尚未覆盖报价，须完成研究或有效事件复核",
  UNKNOWN: "研究覆盖未知，暂不可用",
};

export function dailyResearchDates(packet: unknown) {
  const value = record(packet) ? packet : {};
  const dates = record(value.dates) ? value.dates : {};
  const freshness = record(value.data_freshness) ? value.data_freshness : {};
  const research = record(freshness.research) ? freshness.research : {};
  const verified =
    value.action === "no_order" &&
    value.packet_status === "CURRENT" &&
    value.source_bindings_verified === true;
  const researchStatus =
    typeof research.status === "string" ? research.status : "UNKNOWN";
  const researchAsOf = day(dates.research_as_of);
  const quoteDate = day(dates.quote_trade_date);
  const companies = record(value.company_statuses)
    ? value.company_statuses
    : {};
  const events = Object.entries(companies).flatMap(([symbol, item]) => {
    if (!record(item) || item.symbol !== symbol) return [];
    const bridge = record(item.price_bridge) ? item.price_bridge : {};
    const binding = record(bridge.incremental_validity_binding)
      ? bridge.incremental_validity_binding
      : {};
    const cutoff = day(bridge.review_cutoff);
    const bound =
      typeof binding.path === "string" &&
      !!binding.path &&
      typeof binding.sha256 === "string" &&
      /^[a-f0-9]{64}$/.test(binding.sha256);
    const valid =
      verified &&
      bound &&
      !!cutoff &&
      bridge.incremental_status === "VALID" &&
      Array.isArray(bridge.blockers) &&
      bridge.blockers.length === 0;
    return [
      {
        symbol,
        name: typeof item.name === "string" ? item.name : symbol,
        cutoff: verified && bound ? cutoff : null,
        label: valid
          ? "增量事件有效性已核验"
          : "事件覆盖尚未完成有效核验，暂不可用",
      },
    ];
  });
  const researchCovered =
    verified &&
    !!researchAsOf &&
    !!quoteDate &&
    ((researchStatus === "COVERS" && researchAsOf >= quoteDate) ||
      (researchStatus === "INCREMENTALLY_COVERS" &&
        events.some(
          (event) =>
            event.label === "增量事件有效性已核验" &&
            !!event.cutoff &&
            event.cutoff >= quoteDate,
        )));
  return {
    researchAsOf,
    quoteDate,
    researchCovered,
    coverageLabel: !verified
      ? "研究来源未核验，覆盖状态暂不可用"
      : researchStatus === "COVERS" && !researchCovered
        ? "研究日期与覆盖状态不一致，暂不可用"
        : researchStatus === "INCREMENTALLY_COVERS" && !researchCovered
          ? "增量覆盖缺少有效事件版本或日期，暂不可用"
          : (coverage[researchStatus] ?? "研究覆盖状态未识别，暂不可用"),
    // The existing packet contains coverage cutoffs, not an actual review receipt time.
    latestReviewLabel: "尚无可核验复核回执；不能由行情更新或软件发布时间推定",
    events,
  };
}
