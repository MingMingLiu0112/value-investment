import { useCallback, useState } from "react";
import { useApi } from "../hooks/useApi";

type RowStatus = "CANDIDATE" | "EXCLUDED" | "UNASSESSABLE";
type Params = { offset: number; limit: number; query: string; status: string };
export type ScreenPage = {
  schema_version: "sse-main-screening-v1";
  action: "no_order";
  status: "VERIFIED_SCREENING" | "PARTIAL" | "UNAVAILABLE";
  scope: "SSE_MAIN_A_ONLY";
  quote_date: string | null;
  quote_date_verified: boolean;
  available_at: string | null;
  read_at: string;
  source_status: string;
  counts: {
    universe: number;
    candidate: number;
    excluded: number;
    unassessable: number;
  };
  channel_counts?: Record<string, Record<string, number>>;
  pagination: { offset: number; limit: number; total: number | null };
  items: {
    symbol: string;
    name: string;
    status: RowStatus;
    channels: string[];
    reason: string;
    gaps: string[];
    period: string | null;
    updated_at: string | null;
    channel_evaluations: { channel: string; status: string; reason: string }[];
    conditions: {
      field: string;
      value: string | number | null;
      unit: string | null;
      status: string;
      period: string | null;
    }[];
  }[];
  blockers: string[];
  rule_version: string;
  source_refs: { path: string; sha256: string }[];
  task_id?: string;
  coverage_complete: boolean;
};
export type SseMainScreeningPanelProps = {
  load: (params: Params, signal: AbortSignal) => Promise<ScreenPage>;
};
const channels: Record<string, string> = {
  quality: "质量",
  dividend_cash_return: "现金分红回报",
  value: "价值",
  cyclical: "周期",
};
const statuses: Record<string, string> = {
  CANDIDATE: "候选",
  ALL: "全部",
  EXCLUDED: "已排除",
  UNASSESSABLE: "无法判断",
  PASS: "通过初筛",
  FAIL: "未通过",
  NOT_EVALUATED: "未评估",
  REJECTED: "未通过初筛",
  DATA_GAP: "缺资料",
  CONFLICT: "资料冲突",
  UNSUPPORTED: "不适用",
  BUDGET_EXCLUDED: "已通过初筛（展示数量受限）",
  observed: "来源观察",
  missing: "缺失",
  conflicting: "存在冲突",
};
const fields: Record<string, string> = {
  roe_weighted: "加权净资产收益率",
  gross_margin: "毛利率",
  total_revenue_yoy: "营业收入同比",
  parent_net_income_yoy: "归母净利润同比",
};
const blockerLabels: Record<string, string> = {
  INITIAL_SCREENING_NOT_BUY_ADVICE: "初筛结果不是买入建议",
  PROVIDER_FINANCIAL_NOT_OFFICIAL_ADMISSION:
    "供应商财务数据仅作观察，尚未取得正式事实准入",
  QUOTE_TRADE_DATE_UNVERIFIED: "行情交易日未核验",
  HISTORICAL_SNAPSHOT_NOT_TODAY_REFRESH: "留存历史快照，不是今日重新采集",
  SOURCE_UNAVAILABLE_NOT_ZERO_CANDIDATES: "来源不可用，不等于没有候选公司",
};
const text = (value: string | number | null | undefined) =>
  value == null ? "未知" : String(value);
const object = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const count = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const nullable = (v: unknown) => v === null || typeof v === "string";
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");

export function validScreenPage(v: unknown): v is ScreenPage {
  if (
    !object(v) ||
    v.schema_version !== "sse-main-screening-v1" ||
    v.action !== "no_order" ||
    v.scope !== "SSE_MAIN_A_ONLY" ||
    !["VERIFIED_SCREENING", "PARTIAL", "UNAVAILABLE"].includes(v.status) ||
    !nullable(v.quote_date) ||
    typeof v.quote_date_verified !== "boolean" ||
    !nullable(v.available_at) ||
    typeof v.read_at !== "string" ||
    typeof v.source_status !== "string" ||
    typeof v.rule_version !== "string" ||
    typeof v.coverage_complete !== "boolean" ||
    (v.task_id !== undefined && typeof v.task_id !== "string") ||
    !strings(v.blockers) ||
    !object(v.counts) ||
    !["universe", "candidate", "excluded", "unassessable"].every((k) =>
      count(v.counts[k]),
    ) ||
    (v.channel_counts !== undefined &&
      (!object(v.channel_counts) ||
        !Object.values(v.channel_counts).every(
          (c) => object(c) && Object.values(c).every(count),
        ))) ||
    !object(v.pagination) ||
    !count(v.pagination.offset) ||
    !count(v.pagination.limit) ||
    v.pagination.limit !== 20 ||
    !(v.pagination.total === null || count(v.pagination.total)) ||
    !Array.isArray(v.source_refs) ||
    !v.source_refs.every(
      (r: unknown) =>
        object(r) &&
        typeof r.path === "string" &&
        typeof r.sha256 === "string" &&
        /^[a-f0-9]{64}$/.test(r.sha256),
    ) ||
    !Array.isArray(v.items) ||
    v.items.length > 20
  )
    return false;
  return v.items.every(
    (r: unknown) =>
      object(r) &&
      typeof r.symbol === "string" &&
      /^[0-9]{6}$/.test(r.symbol) &&
      typeof r.name === "string" &&
      ["CANDIDATE", "EXCLUDED", "UNASSESSABLE"].includes(r.status) &&
      strings(r.channels) &&
      typeof r.reason === "string" &&
      strings(r.gaps) &&
      nullable(r.period) &&
      nullable(r.updated_at) &&
      Array.isArray(r.channel_evaluations) &&
      r.channel_evaluations.every(
        (c: unknown) =>
          object(c) &&
          typeof c.channel === "string" &&
          typeof c.status === "string" &&
          typeof c.reason === "string",
      ) &&
      Array.isArray(r.conditions) &&
      r.conditions.every(
        (c: unknown) =>
          object(c) &&
          typeof c.field === "string" &&
          (nullable(c.value) ||
            (typeof c.value === "number" && Number.isFinite(c.value))) &&
          nullable(c.unit) &&
          typeof c.status === "string" &&
          nullable(c.period),
      ),
  );
}

function ChannelCoverage({ counts }: { counts: ScreenPage["channel_counts"] }) {
  const names = Array.from(
    new Set([...Object.keys(channels), ...Object.keys(counts || {})]),
  );
  return (
    <section aria-label="逐通道初筛覆盖">
      <h4>逐通道初筛覆盖（不是研究完成度）</h4>
      <p>
        缺资料或不适用不代表已完成质量研究。公司可出现在多个通道，各通道数量不可相加为公司总数。
      </p>
      {!counts && <p>来源未提供通道计数，不能认定四通道均已评估。</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>通道</th>
              <th>通过初筛（含展示数量受限）</th>
              <th>缺资料</th>
              <th>不适用</th>
              <th>其他状态</th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const values = counts?.[name];
              const other = Object.entries(values || {}).filter(
                ([status]) =>
                  ![
                    "PASS",
                    "BUDGET_EXCLUDED",
                    "DATA_GAP",
                    "UNSUPPORTED",
                  ].includes(status),
              );
              return (
                <tr key={name}>
                  <th scope="row">{channels[name] || name}</th>
                  <td>
                    {values
                      ? (values.PASS ?? 0) + (values.BUDGET_EXCLUDED ?? 0)
                      : "未提供"}
                  </td>
                  <td>{values ? (values.DATA_GAP ?? 0) : "未提供"}</td>
                  <td>{values ? (values.UNSUPPORTED ?? 0) : "未提供"}</td>
                  <td>
                    {other.length ? (
                      <details>
                        <summary>查看其他状态（{other.length}类）</summary>
                        <ul>
                          {other.map(([status, value]) => (
                            <li key={status} title={status}>
                              {statuses[status] || status}：{value}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : values ? (
                      "无其他已报告状态"
                    ) : (
                      "未提供"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SseMainScreeningPanel({ load }: SseMainScreeningPanelProps) {
  const [params, setParams] = useState<Params>({
    offset: 0,
    limit: 20,
    query: "",
    status: "CANDIDATE",
  });
  const key = JSON.stringify(params);
  const fetchPage = useCallback(
    async (signal: AbortSignal) => {
      const page = await load(params, signal);
      if (
        !validScreenPage(page) ||
        page.pagination.offset !== params.offset ||
        page.pagination.limit !== params.limit
      )
        throw new Error("初筛响应合同或分页不匹配，停止展示");
      return { page, key, loader: load };
    },
    [load, key],
  );
  const { data, loading, error, retry } = useApi(fetchPage);
  // useApi keeps prior data internally. Never expose it under a new request or failure.
  const page =
    !loading && !error && data?.key === key && data.loader === load
      ? data.page
      : undefined;
  const unavailable = page?.status === "UNAVAILABLE";
  const next =
    page &&
    !unavailable &&
    (page.pagination.total === null
      ? page.items.length === 20
      : params.offset + 20 < page.pagination.total);
  return (
    <section
      aria-label="沪市主板初筛"
      style={{ padding: 16, border: "1px solid #d9d9d9", borderRadius: 8 }}
    >
      <h3>沪市主板 A 股初筛股票池</h3>
      <p>
        来源观察为 E1，非正式财务事实；初筛不是买入建议，不生成估值或正式准入。
      </p>
      <p>
        展示数量限制不会丢弃已通过初筛的公司。股票顺序、范围和分页沿用后端，页面不再次筛选。
      </p>
      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <label>
          搜索公司或代码{" "}
          <input
            aria-label="搜索公司或代码"
            value={params.query}
            onChange={(e) =>
              setParams((p) => ({ ...p, query: e.target.value, offset: 0 }))
            }
          />
        </label>
        <label>
          筛选状态{" "}
          <select
            aria-label="筛选状态"
            value={params.status}
            onChange={(e) =>
              setParams((p) => ({ ...p, status: e.target.value, offset: 0 }))
            }
          >
            {["CANDIDATE", "ALL", "EXCLUDED", "UNASSESSABLE"].map((s) => (
              <option key={s} value={s}>
                {statuses[s]}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={retry} disabled={loading}>
          重新读取
        </button>
      </div>
      {error ? (
        <p role="alert">
          来源读取失败，不能判断股票池，不能当作零候选。{error}
        </p>
      ) : !page ? (
        <p role="status">正在读取本次筛选，旧结果暂不展示。</p>
      ) : null}
      {page && (
        <>
          <p>
            行情日期：{text(page.quote_date)}；来源可得时间：
            {text(page.available_at)}；本次读取：{page.read_at}。
          </p>
          {!page.quote_date_verified && (
            <p>行情日期未核验，不能视为当前合格报价。</p>
          )}
          <p>
            来源状态：{page.source_status}；
            {page.status === "PARTIAL"
              ? "部分资料可用"
              : unavailable
                ? "来源不可用"
                : "限定范围初筛已核验"}
            ；
            {page.coverage_complete
              ? "官方名单范围均有初筛记录，不代表资料完整"
              : "官方名单初筛记录覆盖尚未证明完整"}
            。
          </p>
          {!!page.blockers.length && (
            <ul aria-label="来源缺口">
              {page.blockers.map((b, i) => (
                <li key={i} title={blockerLabels[b] ? b : undefined}>
                  {blockerLabels[b] || b}
                </li>
              ))}
            </ul>
          )}
          {unavailable ? (
            <p role="alert">来源不可用，股票池未知，不是零候选。</p>
          ) : (
            <>
              <p>
                股票池 {page.counts.universe} 家；候选 {page.counts.candidate}{" "}
                家；已排除 {page.counts.excluded} 家；无法判断{" "}
                {page.counts.unassessable} 家。
              </p>
              <ChannelCoverage counts={page.channel_counts} />
              {!page.items.length ? (
                <p role="status">
                  {page.pagination.total === 0
                    ? "当前来源与查询条件下为 0 条记录，不代表全市场没有机会。"
                    : "本页没有记录；总数或范围以来源回执为准，不据此认定零候选。"}
                </p>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <caption>本次实际股票池（每页 20 条）</caption>
                    <thead>
                      <tr>
                        <th>公司</th>
                        <th>状态 / 通道</th>
                        <th>初筛理由 / 缺口</th>
                        <th>财务期 / 更新时间</th>
                        <th>条件明细</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((row) => (
                        <tr key={row.symbol}>
                          <td>
                            <a href={`/decisions/${row.symbol}?strategy=value`}>
                              {row.name} · {row.symbol}
                            </a>
                          </td>
                          <td>
                            {statuses[row.status]}
                            <br />
                            {row.channels
                              .map((c) => channels[c] || c)
                              .join("、") || "未提供通道"}
                          </td>
                          <td>
                            <p>{row.reason}</p>
                            {row.gaps.length ? (
                              <>
                                <ul>
                                  {row.gaps.slice(0, 2).map((g, i) => (
                                    <li key={i}>{g}</li>
                                  ))}
                                </ul>
                                {row.gaps.length > 2 && (
                                  <details>
                                    <summary>
                                      其余缺口（{row.gaps.length - 2}条）
                                    </summary>
                                    <ul>
                                      {row.gaps.slice(2).map((g, i) => (
                                        <li key={i}>{g}</li>
                                      ))}
                                    </ul>
                                  </details>
                                )}
                              </>
                            ) : (
                              "未列明缺口（不等于资料完整）"
                            )}
                          </td>
                          <td>
                            财务期：{text(row.period)}
                            <br />
                            更新时间：{text(row.updated_at)}
                          </td>
                          <td>
                            <details>
                              <summary>四通道理由与观察条件</summary>
                              <ul>
                                {row.channel_evaluations.map((c, i) => (
                                  <li key={i}>
                                    {channels[c.channel] || c.channel}：
                                    {statuses[c.status] || c.status}；{c.reason}
                                  </li>
                                ))}
                              </ul>
                              {row.conditions.length ? (
                                <ul>
                                  {row.conditions.map((c, i) => (
                                    <li key={i}>
                                      {fields[c.field] || c.field}：
                                      {text(c.value)} {c.unit || ""}；
                                      {statuses[c.status] || c.status}；财务期{" "}
                                      {text(c.period)}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p>未提供可展示条件，不补造数值。</p>
                              )}
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <nav
                aria-label="股票池分页"
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "center",
                  marginTop: 12,
                }}
              >
                <button
                  type="button"
                  disabled={params.offset === 0}
                  onClick={() =>
                    setParams((p) => ({
                      ...p,
                      offset: Math.max(0, p.offset - 20),
                    }))
                  }
                >
                  上一页
                </button>
                <span>
                  第 {Math.floor(params.offset / 20) + 1} 页；当前查询总数：
                  {text(page.pagination.total)}
                </span>
                <button
                  type="button"
                  disabled={!next}
                  onClick={() =>
                    setParams((p) => ({ ...p, offset: p.offset + 20 }))
                  }
                >
                  下一页
                </button>
              </nav>
            </>
          )}
          <details>
            <summary>规则与来源绑定</summary>
            <p>
              规则版本：{page.rule_version}；任务：{text(page.task_id)}
            </p>
            <ul>
              {page.source_refs.map((ref, i) => (
                <li key={i}>
                  {ref.path}
                  <br />
                  <code>{ref.sha256}</code>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
export default SseMainScreeningPanel;
