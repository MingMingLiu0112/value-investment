import { useCallback } from "react";
import { useApi } from "../hooks/useApi";

export interface TrackingPoolView {
  schema_version: "sse-research-tracking-view-v1";
  action: "no_order";
  status: "AVAILABLE" | "UNAVAILABLE";
  source_status: string;
  source_available_at: string | null;
  generated_at: string | null;
  scope: "SSE_MAIN_A_ONLY";
  total_candidates: number | null;
  tracking_count: number | null;
  items: {
    symbol: string;
    name: string;
    industry: string | null;
    channels: string[];
    reason: string;
    first_seen_at: string | null;
    tracking_status: string;
    financial_period: string | null;
    accepted_fields: number;
    observed_fields?: number | null;
    required_fields: number;
    next_action: string;
    gaps: string[];
  }[];
  blockers: string[];
  queue_binding: { path: string; sha256: string } | null;
  history_available: boolean;
}
export interface ValueTrackingResearchPoolProps {
  load: (signal: AbortSignal) => Promise<TrackingPoolView>;
}
const record = (v: unknown): v is Record<string, any> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const count = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const nullableText = (v: unknown) => v === null || typeof v === "string";
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((s) => typeof s === "string");
export function validTrackingPoolView(v: unknown): v is TrackingPoolView {
  return (
    record(v) &&
    v.schema_version === "sse-research-tracking-view-v1" &&
    v.action === "no_order" &&
    v.scope === "SSE_MAIN_A_ONLY" &&
    ["AVAILABLE", "UNAVAILABLE"].includes(v.status) &&
    typeof v.source_status === "string" &&
    v.source_status.trim().length > 0 &&
    nullableText(v.source_available_at) &&
    nullableText(v.generated_at) &&
    (v.total_candidates === null || count(v.total_candidates)) &&
    (v.tracking_count === null || count(v.tracking_count)) &&
    typeof v.history_available === "boolean" &&
    strings(v.blockers) &&
    (v.queue_binding === null ||
      (record(v.queue_binding) &&
        typeof v.queue_binding.path === "string" &&
        v.queue_binding.path.length > 0 &&
        typeof v.queue_binding.sha256 === "string" &&
        /^[a-fA-F0-9]{64}$/.test(v.queue_binding.sha256))) &&
    Array.isArray(v.items) &&
    (v.tracking_count === null || v.tracking_count >= v.items.length) &&
    new Set(v.items.map((r: any) => r?.symbol)).size === v.items.length &&
    v.items.every(
      (r: unknown) =>
        record(r) &&
        typeof r.symbol === "string" &&
        /^\d{6}$/.test(r.symbol) &&
        ["name", "reason", "tracking_status", "next_action"].every(
          (k) => typeof r[k] === "string" && r[k].trim().length > 0,
        ) &&
        nullableText(r.industry) &&
        nullableText(r.first_seen_at) &&
        nullableText(r.financial_period) &&
        strings(r.channels) &&
        strings(r.gaps) &&
        count(r.accepted_fields) &&
        count(r.required_fields) &&
        (r.observed_fields == null ||
          (count(r.observed_fields) &&
            r.observed_fields <= r.required_fields)) &&
        r.accepted_fields <= r.required_fields,
    )
  );
}
const channels: Record<string, string> = {
  quality: "质量",
  dividend_cash_return: "股东现金回报",
  value: "价值线索",
  cyclical: "周期研究",
};
const stages: Record<string, string> = {
  EVIDENCE_REVIEW_PENDING: "等待补证与资料复核",
  DEEP_RESEARCH_PENDING: "等待经营与反证研究",
  DATA_UNAVAILABLE: "资料核验尚未齐（查看具体缺口）",
  EVIDENCE_ENRICHED: "已补充证据（非研究完成）",
  QUALITY_READY: "质量资料就绪（非投资准入）",
  QUALITY_EVALUATED: "已按既有规则评价质量（非投资准入）",
  DISCOVERED: "初筛线索",
  DATA_CHECK: "资料核验 / 待补证",
  EVIDENCE_ENRICHING: "补证中",
  SELECTED_FOR_DATA_CHECK: "已排入资料核验",
  SELECTED_FOR_RESEARCH: "已排入研究预算（非研究完成）",
  BUDGET_DEFERRED: "等待研究预算",
  TRACKING: "持续跟踪",
  NEW: "首次进入跟踪",
  CARRIED: "延续跟踪",
  BLOCKED: "存在阻断",
  UNASSESSABLE: "暂无法评价",
  PAUSED: "暂停跟踪",
};
const nextActions: Record<string, string> = {
  VERIFY_MISSING_FACTS: "核验尚缺的事实资料",
  VERIFY_MISSING_SAME_PERIOD_FACTS_AND_DEBT_NOTE_CLASSIFICATIONS:
    "补核同一报告期缺失事实及债务附注分类",
  RETAIN_CURRENT_RESEARCH_GATES: "继续遵守现有研究门槛，不自动升级准入",
  REOPEN_WHEN_SOURCE_OR_SCOPE_EVIDENCE_CHANGES_NO_AUTOMATIC_RETRY:
    "待来源或口径证据变化后重新复核，不自动重试",
  BOUNDED_RETRY_MAX_THREE_ATTEMPTS_WITH_BACKOFF:
    "按退避间隔有界重试，最多三次尝试",
};
const display = (v: string | number | null) =>
  v === null || v === "" ? "未知" : String(v);

export function ValueTrackingResearchPool({
  load,
}: ValueTrackingResearchPoolProps) {
  const fetchView = useCallback(
    async (signal: AbortSignal) => {
      const view = await load(signal);
      if (!validTrackingPoolView(view))
        throw new Error("研究池响应契约不匹配，停止展示");
      return { view, loader: load };
    },
    [load],
  );
  const { data, loading, error, retry } = useApi(fetchView);
  const view =
    data?.loader === load && validTrackingPoolView(data.view)
      ? data.view
      : undefined;
  return (
    <section aria-label="长期跟踪研究池">
      <h3>长期跟踪研究池</h3>
      <p>
        沪市主板A股；研究预算决定处理顺序，不是投资排名。最多展示后端返回顺序的前30个对象，不在前端筛股。
      </p>
      <p>
        研究路径：初筛 → 补证 → 画像 / 经营研究 → 估值 →
        条件价格。入池不代表后续阶段已完成，也不是买入建议；action=no_order。
      </p>
      <p>
        只读已保存研究队列；重试仅重新读取，不触发网络采集或写入。留存来源不等于今日刷新，来源可得时间也不证明行情交易日已核验。
      </p>
      {loading ? (
        <p role="status">正在读取研究池…</p>
      ) : error ? (
        <p role="alert">研究池读取失败：{error}</p>
      ) : !view ? (
        <p role="alert">尚未取得有效研究池，不能认定为零候选。</p>
      ) : (
        <>
          <p>
            来源状态：{view.source_status}；原来源可得时间：
            {display(view.source_available_at)}；队列生成时间：
            {display(view.generated_at)}
          </p>
          <p>
            {view.history_available
              ? "后端提供历史记录；当前页面展示本次跟踪状态。"
              : "历史连续性尚未提供，不宣称已完成跨轮长期跟踪。"}
          </p>
          {view.status === "UNAVAILABLE" ? (
            <p role="alert">
              研究池当前不可用，不等于零候选或零跟踪对象；不展示旧成功名单。
            </p>
          ) : (
            <>
              <p>
                初筛候选：{display(view.total_candidates)}；跟踪对象：
                {display(view.tracking_count)}；本页展示：
                {Math.min(view.items.length, 30)}。
              </p>
              {view.items.length === 0 ? (
                <p>
                  {view.tracking_count === 0
                    ? "本次已读取队列，跟踪对象为0。"
                    : "本次未返回对象明细，不能据此认定跟踪数为零。"}
                </p>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fit,minmax(min(100%,320px),1fr))",
                    gap: 12,
                  }}
                >
                  {view.items.slice(0, 30).map((row) => (
                    <article
                      key={row.symbol}
                      style={{
                        border: "1px solid #d9d9d9",
                        borderRadius: 8,
                        padding: 12,
                        minWidth: 0,
                        overflowWrap: "anywhere",
                      }}
                    >
                      <h4>
                        <a href={`/decisions/${row.symbol}?strategy=value`}>
                          {row.name}（{row.symbol}）
                        </a>
                      </h4>
                      <p>
                        行业：{display(row.industry)}；初筛通道：
                        {row.channels.map((c) => channels[c] || c).join("、") ||
                          "未提供"}
                      </p>
                      <p>入池理由：{row.reason}</p>
                      <p>
                        当前阶段：
                        <strong title={row.tracking_status}>
                          {stages[row.tracking_status] || row.tracking_status}
                        </strong>
                      </p>
                      <p title={row.next_action}>
                        下一动作：
                        {nextActions[row.next_action] || row.next_action}
                      </p>
                      <p>
                        首次记录：{display(row.first_seen_at)}；财务期：
                        {display(row.financial_period)}
                      </p>
                      <p>
                        {row.observed_fields != null && (
                          <>
                            已取得来源观察：{row.observed_fields} /{" "}
                            {row.required_fields}；
                          </>
                        )}
                        已采纳字段：{row.accepted_fields} / 所需字段：
                        {row.required_fields}；不代表完整质量、估值或投资准入。
                      </p>
                      {row.gaps.length ? (
                        <details>
                          <summary>待补缺口（{row.gaps.length}项）</summary>
                          <ul>
                            {row.gaps.map((g, i) => (
                              <li key={i}>{g}</li>
                            ))}
                          </ul>
                        </details>
                      ) : (
                        <p>未列明字段缺口，不代表下游研究已完成。</p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
          {view.blockers.length > 0 && (
            <div role="note">
              <strong>当前限制</strong>
              <ul>
                {view.blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}
          <details>
            <summary>队列来源绑定</summary>
            {view.queue_binding ? (
              <>
                <p>{view.queue_binding.path}</p>
                <code style={{ overflowWrap: "anywhere" }}>
                  {view.queue_binding.sha256}
                </code>
              </>
            ) : (
              <p>未提供队列绑定，不能据此证明来源完整。</p>
            )}
          </details>
        </>
      )}
      <button type="button" onClick={retry} disabled={loading}>
        重新读取
      </button>
    </section>
  );
}
export default ValueTrackingResearchPool;
