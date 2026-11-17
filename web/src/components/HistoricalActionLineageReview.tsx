type Ref = { path: string; sha256: string; url?: string };
const record = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const day = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v;
const stamp = (v: unknown): v is string =>
  typeof v === "string" &&
  day(v.slice(0, 10)) &&
  /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
  Number.isFinite(Date.parse(v));
const ref = (v: unknown): v is Ref =>
  record(v) &&
  typeof v.path === "string" &&
  !!v.path &&
  !/^(?:[\\/]|[a-z]+:)/i.test(v.path) &&
  !v.path.split(/[\\/]/).includes("..") &&
  /^[a-f0-9]{64}$/.test(v.sha256);
const originalUrl = (value: unknown, published: string): value is string => {
  try {
    if (typeof value !== "string") return false;
    const url = new URL(value);
    const page = /^\/finalpage\/(\d{4}-\d{2}-\d{2})\/\d+\.pdf$/i.exec(
      url.pathname,
    );
    return (
      url.protocol === "https:" &&
      url.hostname === "static.cninfo.com.cn" &&
      !url.port &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      page?.[1] === published
    );
  } catch {
    return false;
  }
};

export function verifiedHistoricalActionLineage(value: unknown): boolean {
  if (
    !record(value) ||
    value.schema_version !== "historical-official-action-lineage-v1" ||
    value.status !== "HISTORICAL_SOURCE_REPLAYED" ||
    value.action !== "no_order" ||
    value.scope !==
      "HISTORICAL_FILING_RELATION_NOT_CURRENT_CANDIDATE_OR_TRADE" ||
    !/^\d{6}$/.test(value.symbol) ||
    !stamp(value.evaluated_at) ||
    !stamp(value.source_available_at) ||
    Date.parse(value.source_available_at) > Date.parse(value.evaluated_at) ||
    !record(value.filing_window) ||
    !day(value.filing_window.start) ||
    !day(value.filing_window.end) ||
    value.filing_window.start > value.filing_window.end ||
    !ref(value.observation_binding) ||
    value.complete_chain_proven !== false ||
    value.comparison_allowed !== false ||
    value.historical_pit_proven !== false ||
    value.formal_eligibility !== false ||
    value.strategy_validation !== "NOT_PROVEN" ||
    !Array.isArray(value.evidence_bindings) ||
    !value.evidence_bindings.length ||
    value.evidence_bindings.length > 64 ||
    !value.evidence_bindings.every(ref)
  )
    return false;
  const bound = (r: unknown) =>
    ref(r) &&
    value.evidence_bindings.some(
      (v: Ref) => v.path === r.path && v.sha256 === r.sha256,
    );
  const lineage = value.lineage_review;
  const originalBound = (r: unknown, published: string) =>
    ref(r) &&
    bound(r) &&
    originalUrl(r.url, published) &&
    lineage.evidence_bindings.some(
      (v: Ref) => v.path === r.path && v.sha256 === r.sha256 && v.url === r.url,
    );
  return (
    bound(value.observation_binding) &&
    record(lineage) &&
    lineage.schema_version === "hotspot-source-action-lineage-v1" &&
    lineage.action === "no_order" &&
    lineage.complete_chain_proven === false &&
    lineage.comparison_allowed === false &&
    lineage.historical_availability_proven === false &&
    Array.isArray(lineage.evidence_bindings) &&
    lineage.evidence_bindings.length <= 64 &&
    lineage.evidence_bindings.every(bound) &&
    Array.isArray(lineage.links) &&
    lineage.links.length <= 16 &&
    Array.isArray(lineage.unresolved) &&
    lineage.links.every(
      (row: any) =>
        record(row) &&
        row.action === "no_order" &&
        row.relation_status === "EXPLICIT_TARGET_MATCH" &&
        row.complete_chain_proven === false &&
        row.comparison_allowed === false &&
        typeof row.original_number === "string" &&
        typeof row.amendment_number === "string" &&
        (row.changed_section == null ||
          typeof row.changed_section === "string") &&
        day(row.original_published_date) &&
        day(row.amendment_published_date) &&
        row.original_published_date <= row.amendment_published_date &&
        row.original_published_date >= value.filing_window.start &&
        row.amendment_published_date <= value.filing_window.end &&
        originalBound(row.original_binding, row.original_published_date) &&
        originalBound(row.amendment_binding, row.amendment_published_date) &&
        ((row.effect_status === "CORRECTION_DECLARED" &&
          row.cancellation_asserted_by_this_document === false) ||
          (row.effect_status === "CANCELLATION_DECLARED" &&
            row.cancellation_asserted_by_this_document === true) ||
          (["UNKNOWN", "COMPOUND_CHANGE_REQUIRES_REVIEW"].includes(
            row.effect_status,
          ) &&
            row.cancellation_asserted_by_this_document === null)),
    )
  );
}

export function HistoricalActionLineageReview({ value }: { value?: unknown }) {
  if (value == null) return null;
  if (!verifiedHistoricalActionLineage(value))
    return (
      <p role="alert">
        历史公司行动原件或关联暂不可核验；不采纳为当前保护位或持仓结论。
      </p>
    );
  const data = value as Record<string, any>;
  const effects: Record<string, string> = {
    CORRECTION_DECLARED: "更正声明",
    CANCELLATION_DECLARED: "撤销声明",
    COMPOUND_CHANGE_REQUIRES_REVIEW: "复合变更，待复核",
    UNKNOWN: "原文效应尚不确定",
  };
  return (
    <section
      aria-label="历史公司行动更正原件"
      style={{ minWidth: 0, overflowWrap: "anywhere", marginBlock: 16 }}
    >
      <h4>历史公司行动更正原件 · {data.symbol}</h4>
      <p>
        公告范围 {data.filing_window.start} 至 {data.filing_window.end}
        ；原件取得 {data.source_available_at}
        。不是取得日前的历史PIT，也不是当前候选、持仓或交易信号。
      </p>
      {data.lineage_review.links.length ? (
        data.lineage_review.links.map((row: any, i: number) => (
          <div key={i}>
            <p>
              <strong>
                {row.original_number} → {row.amendment_number}
              </strong>
              ：{effects[row.effect_status]}。
            </p>
            <p>
              更正章节：{row.changed_section || "尚待核验"}
              ；本文件是否明确撤销：
              {row.cancellation_asserted_by_this_document === true
                ? "是"
                : row.cancellation_asserted_by_this_document === false
                  ? "否"
                  : "不确定"}
              。
            </p>
            <a href={row.original_binding.url} target="_blank" rel="noreferrer">
              原实施公告
            </a>
            {" · "}
            <a
              href={row.amendment_binding.url}
              target="_blank"
              rel="noreferrer"
            >
              后续公告原文
            </a>
          </div>
        ))
      ) : (
        <p>未形成明确关联，不代表不存在其他更正或撤销。</p>
      )}
      <p>
        明确关联不等于完整修订链已核清。期初行动状态、非现金条款和价格口径仍需复核，不改原保护位，不据此自动持有、加仓或退出。
      </p>
      <p>
        待核验关联 {data.lineage_review.unresolved.length}{" "}
        项；策略有效性仍未证明。
      </p>
      <details>
        <summary>该历史例的原件绑定</summary>
        <ul>
          {data.evidence_bindings.map((r: Ref, i: number) => (
            <li key={i}>
              <code>{r.path}</code>
              <br />
              <code>{r.sha256}</code>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
