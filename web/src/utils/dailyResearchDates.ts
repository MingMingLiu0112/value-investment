import type { DailyMachineResearchReview } from "../types/api";

/** Display only: coverage labels never grant investment or execution authority. */
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

function observedTime(value: unknown): string | null {
  return typeof value === "string" &&
    !!day(value.slice(0, 10)) &&
    /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
    ? value
    : null;
}

/** Source-declared window completeness only; never consult the browser clock. */
export function eventCoverageDates(value: unknown, requiredDay?: unknown) {
  const bridge = record(value) ? value : {};
  const explicit = record(bridge.current_event_coverage)
    ? bridge.current_event_coverage
    : null;
  const incremental = record(bridge.incremental_validity)
    ? bridge.incremental_validity
    : {};
  const requiredThrough = day(requiredDay) ?? day(explicit?.required_through);
  const queryThrough = day(
    explicit
      ? explicit.query_through
      : (incremental.review_cutoff ?? bridge.review_cutoff),
  );
  const observedAt = observedTime(
    explicit ? explicit.observed_at : incremental.observed_at,
  );
  const flag = explicit
    ? explicit.full_calendar_window_elapsed
    : incremental.full_calendar_window_elapsed;
  const full = flag === true;
  const declaredCovered = explicit
    ? day(explicit.covered_through)
    : full
      ? queryThrough
      : null;
  const status = explicit?.status;
  const consistent = explicit
    ? (typeof incremental.full_calendar_window_elapsed !== "boolean" ||
        incremental.full_calendar_window_elapsed === flag) &&
      !!requiredThrough &&
      day(explicit.required_through) === requiredThrough &&
      !!queryThrough &&
      !!observedAt &&
      (status === "FULL_WINDOW"
        ? full &&
          declaredCovered === queryThrough &&
          queryThrough === requiredThrough
        : status === "PARTIAL_CURRENT_SNAPSHOT"
          ? flag === false &&
            explicit.covered_through === null &&
            queryThrough === requiredThrough
          : status === "CLOSED_WINDOW_NOT_CURRENT"
            ? full &&
              declaredCovered === queryThrough &&
              queryThrough < requiredThrough
            : status === "SNAPSHOT_NOT_CURRENT"
              ? flag === false &&
                explicit.covered_through === null &&
                queryThrough < requiredThrough
              : false)
    : true;
  const currentComplete =
    consistent &&
    full &&
    !!observedAt &&
    !!queryThrough &&
    queryThrough === requiredThrough &&
    (!explicit || status === "FULL_WINDOW");
  const coveredThrough = consistent && full ? declaredCovered : null;
  const label = !consistent
    ? "公告窗口字段缺失或矛盾，完整覆盖未确认"
    : currentComplete
      ? "后端确认当前所需日期的完整公告窗口；事件影响及模型批准仍须另审"
      : requiredThrough && queryThrough && queryThrough < requiredThrough
        ? "旧查询窗口未覆盖当前所需日期；不能作为当前日完整覆盖"
        : flag === false
          ? "局部公告快照（partial），不是全天完整覆盖"
          : full
            ? "仅确认已结束的查询窗口，当前日完整覆盖未确认"
            : "未提供完整窗口证明，当前日覆盖未知";
  return {
    requiredThrough,
    queryThrough,
    observedAt,
    coveredThrough,
    currentComplete,
    label,
    fullCalendarWindowElapsed: typeof flag === "boolean" ? flag : null,
  };
}

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
      row.full_calendar_window_elapsed !== false &&
      !!day(row.event_coverage_through);
    const modelStatus =
      ["VALID", "STALE", "UNKNOWN"].includes(row.model_validity_status) &&
      (complete || row.model_validity_status !== "VALID")
        ? row.model_validity_status
        : "UNKNOWN";
    return {
      symbol: row.symbol,
      status: typeof row.status === "string" ? row.status : "UNKNOWN",
      research_as_of: day(row.research_as_of),
      scan_through: day(row.scan_through),
      observed_at: observedTime(row.observed_at),
      full_calendar_window_elapsed:
        typeof row.full_calendar_window_elapsed === "boolean"
          ? row.full_calendar_window_elapsed
          : null,
      event_coverage_status: complete ? "COMPLETE" : "UNCONFIRMED",
      event_coverage_through: complete ? day(row.event_coverage_through) : null,
      announcement_count:
        Number.isInteger(row.announcement_count) && row.announcement_count >= 0
          ? row.announcement_count
          : null,
      facts_change_status:
        !complete &&
        ["NONE", "REVIEWED_NO_MODEL_INVALIDATION"].includes(
          row.facts_change_status,
        )
          ? "UNKNOWN"
          : typeof row.facts_change_status === "string"
            ? row.facts_change_status
            : null,
      model_validity_status: modelStatus,
      model_recalculation_required:
        row.model_recalculation_required === false && modelStatus !== "VALID"
          ? null
          : typeof row.model_recalculation_required === "boolean"
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
    const currentCoverage = eventCoverageDates(
      verified && bound ? bridge : undefined,
      verified && bound ? dates.current_natural_date : undefined,
    );
    return [
      {
        symbol,
        name: typeof item.name === "string" ? item.name : symbol,
        cutoff: verified && bound ? cutoff : null,
        priceComparisonCovered: valid,
        ...currentCoverage,
        label:
          verified && bound
            ? currentCoverage.label +
              (valid ? "" : "；增量事件模型有效性尚未核验，暂不可用")
            : "事件覆盖尚未完成来源核验，暂不可用",
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
            event.priceComparisonCovered &&
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
