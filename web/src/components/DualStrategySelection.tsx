import { useCallback, useState } from "react";
import { Alert, Button, Input, Table, Tag } from "antd";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { SelectionCondition, SelectionRow } from "../types/selection";
import { describeCode } from "../utils/codes";
import { blockerText } from "../utils/packet";

const reasons: Record<string, string> = {
  DAILY_DOWNTREND_CONFLICT: "日线处于下行结构，与新建仓方向冲突",
  INSUFFICIENT_UPPER_SPACE: "距离上方阻力的空间不足",
  PRIMARY_STRUCTURE_INVALIDATED: "主要交易周期结构已失效",
  SUPPORTING_STRUCTURE_INVALIDATED: "日线或辅助周期结构已失效",
  COMPLETED_MULTIPERIOD_CASE_MISSING: "缺少已完成的多周期行情证据",
  WATCH_POOL_STALE: "候选池日期已过期，需要更新后重评",
  DAILY_AND_PRIMARY_STRUCTURE_CONFIRMED:
    "日线及主要周期结构确认，仍待策略与账户准入",
  DAILY_TREND_NOT_ESTABLISHED: "日线趋势尚未满足原规则条件",
  UPPER_TRADE_SPACE_NOT_ESTABLISHED:
    "尚不能确认上方结构空间，无法评估结构距离比",
  PRIMARY_PRICE_OR_VOLUME_BREAKOUT_NOT_MET:
    "主要周期的价格或量能突破条件尚未同时满足",
  PRIMARY_VOLUME_CONFIRMATION_NOT_MET:
    "价格已越过参考高点，但量能尚未达到原规则要求",
  PRIMARY_CLOSE_NOT_ABOVE_PRIOR_HIGH: "主要周期完成收盘价尚未超过前高",
  NEXT_BAR_OR_PULLBACK_CONFIRMATION_NOT_OBSERVED:
    "尚未观察到下一根完成K线或回踩恢复确认",
  INDEPENDENT_STRATEGY_ADMISSION_REVIEW_REQUIRED: "独立策略验证和准入仍未完成",
  STRUCTURE_CONFIRMATION_PENDING: "多周期结构仍待确认",
};
const explain = (code: string) =>
  reasons[code] || blockerText(describeCode(code));
const researchAmount = (value: unknown) =>
  value !== null &&
  value !== undefined &&
  value !== "" &&
  Number.isFinite(Number(value))
    ? Number(value).toFixed(2)
    : "未提供";

const fields: Record<string, string> = {
  roe_weighted: "加权 ROE",
  gross_margin: "毛利率",
  total_revenue_yoy: "营业总收入同比",
  parent_net_income_yoy: "归母净利润同比",
};
const states: Record<string, string> = {
  SELECTED: "结构入选，仍待策略准入",
  EXCLUDED: "结构排除",
  UNKNOWN: "资料不足",
  PENDING_CONFIRMATION: "待确认",
  SPECIALIZED_RESEARCH_REQUIRED: "需行业专用研究",
  GENERAL_RESEARCH: "一般企业研究",
};
export const valueChannelName = (channel: string): string =>
  (
    ({
      quality: "质量",
      dividend_cash_return: "现金回报",
      value: "价值",
      cyclical: "周期",
    }) as Record<string, string>
  )[channel] || channel;

const dataStates: Record<string, string> = {
  STALE: "历史快照已过期，不能作为当前结构结论",
  CURRENT: "来源已核验",
  PARTIAL: "部分来源或周期尚未就绪",
  PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS: "供应商财务观察，非正式核验事实",
  SOURCE_REVALIDATION_FAILED: "来源重新核验失败",
};
function safeSource(url?: string) {
  if (!url) return undefined;
  try {
    return ["https:", "http:"].includes(new URL(url).protocol)
      ? url
      : undefined;
  } catch {
    return undefined;
  }
}
export function selectionPriceCondition(value: unknown, invalidation = false) {
  if (!value || typeof value !== "object") return "尚未建立可核验的条件";
  const condition = value as { price?: unknown; rule?: unknown };
  const price =
    typeof condition.price === "string" || typeof condition.price === "number"
      ? `${condition.price} 元`
      : "价位未形成";
  const rule = invalidation
    ? "后续已完成收盘价低于前五根最低价时，价格结构失效，需重新复核。"
    : typeof condition.rule === "string"
      ? condition.rule
      : "规则尚未形成";
  return `${price}；${rule}`;
}
function Condition({ item }: { item: SelectionCondition }) {
  return (
    <li>
      <strong>{fields[item.field] || item.field}</strong> · {item.period} ·{" "}
      {item.status}
      {" · "}
      {item.value ?? "缺失"} {item.unit}
      {" · 研究观察条件："}
      {item.operator} {item.threshold} {item.unit}
      {" · "}
      {item.stale
        ? "数据已陈旧"
        : item.favorable === true
          ? "满足观察条件"
          : item.favorable === false
            ? "不满足观察条件"
            : "无法比较"}
      {item.evidence?.map((ref, i) => (
        <div key={i}>
          {safeSource(ref.source_url) && (
            <a
              href={safeSource(ref.source_url)}
              target="_blank"
              rel="noreferrer"
            >
              原始来源
            </a>
          )}
          {" · 可得时间："}
          {ref.available_at || "未知"}
          {" · SHA-256："}
          <code style={{ overflowWrap: "anywhere" }}>
            {ref.raw_file_hash || "缺失"}
          </code>
        </div>
      ))}
    </li>
  );
}
export function SwingWaitExplanation({ row }: { row: SelectionRow }) {
  const review = row.decision_explanation;
  if (!review) return null;
  if (
    review.state !== "WAIT" ||
    review.action !== "no_order" ||
    review.formal_eligibility !== false ||
    review.holding_action_eligibility !== false ||
    review.owned_entry_supplied !== false
  )
    return <p>波段条件解释无法核验，未生成操作建议。</p>;
  const labels: Record<string, string> = {
    UPTREND: "上行",
    DOWNTREND: "下行",
    RANGE: "震荡区间",
    BREAKOUT: "价量突破",
    PRICE_ABOVE_VOLUME_PENDING: "价格突破、量能待确认",
  };
  const inputs = row.data_status === "CURRENT" ? review.rule_inputs : undefined;
  const observed = (value: boolean | undefined) =>
    value === true ? "已观察" : value === false ? "尚未观察" : "未知";
  return (
    <section aria-label="波段等待原因">
      <p>
        {row.selection_status === "EXCLUDED"
          ? "当前结构已排除"
          : row.selection_status === "UNKNOWN"
            ? "当前资料不足"
            : "当前仍需等待"}
        ，原因如下：
      </p>
      <ul>
        {review.wait_reasons.map((reason) => (
          <li key={reason}>{explain(reason)}</li>
        ))}
      </ul>
      {inputs && (
        <dl>
          <dt>日线趋势 / 主要周期结构</dt>
          <dd>
            {labels[inputs.daily_trend] ?? inputs.daily_trend} /{" "}
            {labels[inputs.primary_structure] ?? inputs.primary_structure}
          </dd>
          <dt>上下结构距离比（未计费用，不是预期收益）</dt>
          <dd>{inputs.structural_distance_ratio ?? "无法评估"}</dd>
          <dt>后续完成K线确认 / 回踩恢复</dt>
          <dd>
            {observed(inputs.next_bar_confirmed)} /{" "}
            {observed(inputs.pullback_recovery_observed)}
          </dd>
        </dl>
      )}
      <p>
        仅为结构条件观察；未核验个人原始入场逻辑，不构成持仓加减仓或退出建议。
      </p>
    </section>
  );
}
export function DualStrategySelection() {
  return (
    <section
      aria-label="双策略选股"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 480px), 1fr))",
        gap: 24,
      }}
    >
      <SelectionPool mode="value" />
      <SelectionPool mode="hotspot" />
    </section>
  );
}
function SelectionPool({ mode }: { mode: "value" | "hotspot" }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const load = useCallback(
    (signal: AbortSignal) =>
      api.strategySelectionPage(mode, (page - 1) * 10, query, signal),
    [mode, page, query],
  );
  const result = useApi(
    page === 1 && query === "" ? api.strategySelection : load,
  );
  const title = mode === "value" ? "价值投资候选池" : "热点波段候选池";
  if (result.loading)
    return (
      <section aria-label={title}>
        <h2>{title}</h2>
        <p>正在核验双策略选股来源…</p>
      </section>
    );
  if (result.error || !result.data)
    return (
      <section aria-label={title}>
        <h2>{title}</h2>
        <Alert type="warning" message="选股来源暂不可核验，未生成新结论" />
        <Button onClick={result.retry}>重试</Button>
      </section>
    );
  const lane = result.data[mode];
  const unavailable =
    ["SOURCE_OR_SELECTION_UNAVAILABLE", "UNASSESSABLE"].includes(
      lane.status || "",
    ) ||
    lane.data_status === "SOURCE_REVALIDATION_FAILED" ||
    !lane.coverage ||
    Object.keys(lane.coverage).length === 0;
  const rows = lane.items.filter((row) =>
    `${row.symbol} ${row.company_name || row.name || ""} ${row.industry || ""}`.includes(
      query.trim(),
    ),
  );
  const count = lane.coverage || {};
  return (
    <section
      aria-label={title}
      style={{ marginBlock: 24, minWidth: 0, overflowWrap: "anywhere" }}
    >
      <h2>{title}</h2>
      <p>
        {mode === "value"
          ? "已覆盖市场 → 来源核验 → 多通道初筛 → 财务观察 → 研究优先队列 → 公司研究与适用估值 → 人工复核"
          : "完整交易日 → 行业活跃度与流动性 → 跨行业候选池 → 已完成多周期结构 → 策略验证与账户风控 → 人工复核"}
      </p>
      {mode === "value" && (
        <p>
          队列排序：观察条件满足数优先，再比较不满足数、缺失数及既有初筛通道数；相同条件以证券代码排序，不按预期收益排名。
        </p>
      )}
      <Alert
        type="info"
        showIcon
        message={
          mode === "value"
            ? "下列排序仅分配研究注意力。供应商财务观察尚未成为官方核验事实，也不代表主估值或买入准入。"
            : "活跃不等于上涨预测。结构入选仍需独立策略验证、费用与账户风控；零入选也是有效结果。"
        }
      />
      <p style={{ overflowWrap: "anywhere" }}>
        数据日期：{lane.quote_date || lane.trade_date || "未核验"} ·{" "}
        {dataStates[lane.data_status || ""] || lane.data_status || lane.status}{" "}
        · 规则：{lane.rule_version}
      </p>
      {lane.snapshot_status === "RETAINED_DATED_RESEARCH" && (
        <Alert
          type="warning"
          showIcon
          message={
            lane.refresh_status === "COLLECTION_FAILED"
              ? "本次全市场采集失败；下列为重新核验通过的历史研究队列，不是今日刷新结果。"
              : lane.refresh_status === "INCOMPLETE"
                ? "本次全市场刷新尚未完成；下列为重新核验通过的历史研究队列。"
                : "本次未进行全市场采集；下列为重新核验通过的历史研究队列。"
          }
          description={`原筛选生成时间：${lane.available_at || "未提供"}；最近运行：${lane.latest_attempt?.finished_at || lane.latest_attempt?.started_at || "未完成"}。只用于安排研究，不提供买入或仓位资格。`}
        />
      )}
      {lane.data_status === "STALE" && (
        <Alert
          type="warning"
          message="历史参考：本池不是今日刷新结果，原结构条件须重新核验，不提供当前入场资格。"
        />
      )}
      <p>
        {unavailable
          ? "来源无法核验，覆盖与候选数量未知，不能判断是否有候选。"
          : mode === "value"
            ? `覆盖 ${count.universe_count ?? 0} 家；财务观察 ${count.observation_count ?? 0} 项；研究队列 ${count.research_queue_count ?? 0} 家；正式事实准入 ${count.official_fact_admission_count ?? 0} 家。本页展示 ${lane.items.length} 家，筛选范围共 ${lane.pagination?.total ?? lane.items.length} 家。`
            : `本次来源市场 ${count.market_securities ?? 0} 家（非官方全 A 覆盖认证）；候选池 ${count.candidate_pool ?? 0} 家；已评估 ${count.evaluated ?? 0} 家；入选 ${count.selected ?? 0} 家；排除 ${count.excluded ?? 0} 家；资料不足 ${count.unknown ?? 0} 家；待确认 ${count.pending_confirmation ?? 0} 家。`}
      </p>
      {mode === "value" && (
        <p>
          {lane.screening_scope
            ? lane.screening_scope.all_a_complete
              ? "官方全 A 覆盖已核验"
              : "部分市场覆盖（非全 A）：已覆盖 " +
                lane.screening_scope.covered_venues.join("、") +
                "；缺失 " +
                (lane.screening_scope.failed_venues.join("、") || "未提供") +
                "。"
            : "市场覆盖范围未核验，不能宣称全 A 覆盖。"}
          四通道仅为初筛线索与研究排序；ROIC、正常化盈利和分红持续性尚需独立研究。
        </p>
      )}
      {unavailable && <Button onClick={result.retry}>重新核验选股来源</Button>}
      <Input.Search
        aria-label={`搜索${title}`}
        placeholder="代码、公司或行业"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setPage(1);
        }}
        style={{ maxWidth: 360, marginBlock: 12 }}
        allowClear
      />
      <Table<SelectionRow>
        rowKey="symbol"
        dataSource={rows}
        size="small"
        pagination={{
          pageSize: 10,
          current: page,
          total: lane.pagination?.total ?? rows.length,
          showSizeChanger: false,
          onChange: setPage,
          showTotal: (total, range) =>
            `展示 ${range[0]}–${range[1]} / ${total} 家`,
        }}
        scroll={{ x: 1000, y: 480 }}
        locale={{
          emptyText: unavailable
            ? "无法核验，不代表零候选"
            : "暂无符合条件且来源可核验的研究候选",
        }}
        columns={[
          {
            title: "公司",
            render: (_, row) => (
              <>
                <a
                  href={`/decisions/${encodeURIComponent(row.symbol)}?strategy=${mode}`}
                >
                  {row.company_name || row.name || row.symbol}
                </a>
                <br />
                <code>{row.symbol}</code>
              </>
            ),
          },
          {
            title: "行业",
            render: (_, row) => row.industry || "未提供行业/主题",
          },
          {
            title: "入池依据 / 主要缺口",
            render: (_, row) => (
              <>
                <div>
                  {mode === "value"
                    ? row.channel_evaluations
                        ?.filter((item) =>
                          ["PASS", "BUDGET_EXCLUDED"].includes(item.status),
                        )
                        .map(
                          (item) =>
                            `${valueChannelName(item.channel)}：${explain(item.reason)}`,
                        )
                        .join("；") || "财务观察进入研究优先队列，尚待深度研究"
                    : row.reasons?.map(explain).join("；") ||
                      "行业活跃度初筛，结构待核验"}
                </div>
                <div>{row.blockers?.slice(0, 2).map(explain).join("；")}</div>
              </>
            ),
          },
          {
            title: "条件研究",
            render: (_, row) =>
              mode === "value" ? (
                row.research_summary?.status === "CONDITIONAL_RESEARCH" ? (
                  <>
                    <div>
                      未批准条件估值（元/股）：
                      {researchAmount(
                        row.research_summary.valuation?.bear_value,
                      )}{" "}
                      /{" "}
                      {researchAmount(
                        row.research_summary.valuation?.base_value,
                      )}{" "}
                      /{" "}
                      {researchAmount(
                        row.research_summary.valuation?.bull_value,
                      )}
                    </div>
                    <div>
                      估值基准：
                      {row.research_summary.valuation_date || "未提供"}
                      ；非当前低估结论
                    </div>
                  </>
                ) : row.research_summary?.status ===
                  "RESEARCH_SOURCE_UNAVAILABLE" ? (
                  "研究来源核验失败，条件估值不可展示"
                ) : (
                  "尚未形成可核验条件估值；当前为初筛观察"
                )
              ) : (
                <>
                  {selectionPriceCondition(row.entry_condition)}
                  <br />
                  失效：
                  {selectionPriceCondition(row.invalidation_condition, true)}
                </>
              ),
          },
          {
            title: "资料日期",
            render: () => lane.quote_date || lane.trade_date || "未提供",
          },
          {
            title: "详情",
            render: (_, row) => (
              <a
                href={`/decisions/${encodeURIComponent(row.symbol)}?strategy=${mode}`}
              >
                {mode === "value" ? "查看研究" : "查看跟踪"}
              </a>
            ),
          },
          {
            title: "研究判断",
            render: (_, row) =>
              mode === "value" ? (
                <>
                  {states[row.profile_status || ""] || row.profile_status}
                  <br />
                  {row.research_summary?.status === "CONDITIONAL_RESEARCH"
                    ? "已有条件研究，经济假设待复核"
                    : row.research_summary?.status ===
                        "RESEARCH_SOURCE_UNAVAILABLE"
                      ? "研究资料待恢复核验"
                      : "初筛研究队列，待深度研究"}
                  <br />
                  {row.observation_summary &&
                    `观察条件满足 ${row.observation_summary.favorable}；不满足 ${row.observation_summary.unfavorable}；缺失 ${row.observation_summary.missing}；冲突 ${row.observation_summary.conflicting}`}
                </>
              ) : (
                <Tag>
                  {states[row.selection_status || ""] || row.selection_status}
                </Tag>
              ),
          },
        ]}
        expandable={{
          expandedRowRender: (row) => (
            <div
              style={{
                maxWidth: "min(100%, calc(100vw - 64px))",
                overflowWrap: "anywhere",
              }}
            >
              {mode === "value" ? (
                <>
                  <p>
                    周期口径：{row.cycle_status}
                    。满足观察条件不等于已证明企业质量。
                  </p>
                  <details>
                    <summary>四通道初筛依据与未完成事项</summary>
                    <ul>
                      {row.channel_evaluations?.map((item) => (
                        <li key={item.channel}>
                          {valueChannelName(item.channel)} · {item.status} ·{" "}
                          {explain(item.reason)}
                        </li>
                      ))}
                    </ul>
                    <ul>
                      {row.blockers?.map((reason) => (
                        <li key={reason}>{explain(reason)}</li>
                      ))}
                    </ul>
                  </details>
                  <ul>
                    {row.conditions?.map((item) => (
                      <Condition key={item.field} item={item} />
                    ))}
                  </ul>
                </>
              ) : (
                <>
                  <p>
                    结构状态：{row.structure_status} · 数据状态：
                    {row.data_status}
                  </p>
                  <p>缺失周期：{row.missing_periods?.join("、") || "无"}</p>
                  <ul>
                    {row.reasons?.map((reason) => (
                      <li key={reason}>{explain(reason)}</li>
                    ))}
                  </ul>
                  <SwingWaitExplanation row={row} />
                  <p>
                    进入条件：
                    {selectionPriceCondition(row.entry_condition)}
                  </p>
                  <p>
                    失效条件：
                    {selectionPriceCondition(row.invalidation_condition, true)}
                  </p>
                  <p>
                    有效交易日：{row.valid_from_session || "未知"} 至{" "}
                    {row.expires_after_session || "未知"}；资料可得时间：
                    {row.source_available_at || "未知"}。
                  </p>
                  <details>
                    <summary>结构证据指纹</summary>
                    <ul>
                      {row.evidence_refs?.map((ref) => (
                        <li key={ref}>
                          <code style={{ overflowWrap: "anywhere" }}>
                            {ref}
                          </code>
                        </li>
                      ))}
                    </ul>
                  </details>
                </>
              )}
              <p>
                选股不授予下单或仓位权限。个人建议仍需已确认账户、持仓原始逻辑和共享风险预算。
              </p>
            </div>
          ),
        }}
      />
      <details>
        <summary>本次核验标识与待办</summary>
        <code style={{ overflowWrap: "anywhere" }}>
          {result.data.content_sha256}
        </code>
        <ul>
          {lane.blockers?.map((reason) => (
            <li key={reason}>{explain(reason)}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
