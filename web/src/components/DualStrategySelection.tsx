import { useState } from "react";
import { Alert, Button, Input, Radio, Table, Tag } from "antd";
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
};
const explain = (code: string) =>
  reasons[code] || blockerText(describeCode(code));

const fields: Record<string, string> = {
  roe_weighted: "加权 ROE",
  gross_margin: "毛利率",
  total_revenue_yoy: "营业收入同比",
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
export function DualStrategySelection() {
  const result = useApi(api.strategySelection);
  const [mode, setMode] = useState<"value" | "hotspot">("value");
  const [query, setQuery] = useState("");
  if (result.loading)
    return (
      <section aria-label="双策略选股">
        <p>正在核验双策略选股来源…</p>
      </section>
    );
  if (result.error || !result.data)
    return (
      <section aria-label="双策略选股">
        <Alert type="warning" message="选股来源暂不可核验，未生成新结论" />
        <Button onClick={result.retry}>重试</Button>
      </section>
    );
  const lane = result.data[mode];
  const unavailable =
    ["SOURCE_OR_SELECTION_UNAVAILABLE", "UNASSESSABLE"].includes(
      lane.status || "",
    ) || !lane.coverage;
  const rows = lane.items.filter((row) =>
    `${row.symbol} ${row.company_name || row.name || ""} ${row.industry || ""}`.includes(
      query.trim(),
    ),
  );
  const count = lane.coverage || {};
  return (
    <section aria-label="双策略选股" style={{ marginBlock: 24 }}>
      <h2>双策略选股</h2>
      <Radio.Group
        value={mode}
        onChange={(event) => setMode(event.target.value)}
        optionType="button"
        options={[
          { label: "价值研究队列", value: "value" },
          { label: "热点结构候选", value: "hotspot" },
        ]}
      />
      <p>
        {mode === "value"
          ? "全市场 → 来源核验 → 多通道初筛 → 财务观察 → 研究优先队列 → 公司研究与适用估值 → 人工复核"
          : "完整交易日 → 行业活跃度与流动性 → 跨行业候选池 → 已完成多周期结构 → 策略验证与账户风控 → 人工复核"}
      </p>
      <Alert
        type="info"
        showIcon
        message={
          mode === "value"
            ? "下列排序仅分配研究注意力。供应商财务观察尚未成为官方核验事实，也不代表主估值或买入准入。"
            : "活跃不等于上涨预测。结构入选仍需独立策略验证、费用与账户风控；零入选也是有效结果。"
        }
      />
      <p>
        数据日期：{lane.quote_date || lane.trade_date || "未核验"} ·{" "}
        {lane.data_status || lane.status} · 规则：{lane.rule_version}
      </p>
      <p>
        {unavailable
          ? "来源无法核验，覆盖与候选数量未知，不能判断是否有候选。"
          : mode === "value"
            ? `覆盖 ${count.universe_count ?? 0} 家；财务观察 ${count.observation_count ?? 0} 项；研究队列 ${count.research_queue_count ?? 0} 家；正式事实准入 ${count.official_fact_admission_count ?? 0} 家。当前展示前 ${lane.items.length} 家。`
            : `全市场 ${count.market_securities ?? 0} 家；候选池 ${count.candidate_pool ?? 0} 家；已评估 ${count.evaluated ?? 0} 家；入选 ${count.selected ?? 0} 家；排除 ${count.excluded ?? 0} 家；资料不足 ${count.unknown ?? 0} 家；待确认 ${count.pending_confirmation ?? 0} 家。`}
      </p>
      {unavailable && <Button onClick={result.retry}>重新核验选股来源</Button>}
      <Input.Search
        aria-label="搜索选股结果"
        placeholder="代码、公司或行业"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        style={{ maxWidth: 360, marginBlock: 12 }}
        allowClear
      />
      <Table<SelectionRow>
        rowKey="symbol"
        dataSource={rows}
        size="small"
        pagination={{ pageSize: 10 }}
        scroll={{ x: 700 }}
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
                {row.company_name || row.name || row.symbol}
                <br />
                <code>{row.symbol}</code>
              </>
            ),
          },
          { title: "行业", dataIndex: "industry" },
          {
            title: "研究判断",
            render: (_, row) =>
              mode === "value" ? (
                <>
                  {states[row.profile_status || ""] || row.profile_status}
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
            <div>
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
                          {item.channel} · {item.status} ·{" "}
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
                  <p>
                    进入条件：
                    {JSON.stringify(row.entry_condition ?? "尚未建立")}
                  </p>
                  <p>
                    失效条件：
                    {JSON.stringify(row.invalidation_condition ?? "尚未建立")}
                  </p>
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
