import { Alert, Descriptions, Segmented, Table } from "antd";
import { useCallback, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { DecisionItem } from "../types/api";
import {
  currentCaseMatches,
  judgmentReason,
  judgmentState,
  priceRuleText,
  confirmationText,
} from "../utils/currentJudgment";
import { firstResearchText } from "../utils/opportunityView";
import { DetailSection } from "./DetailSection";
import { PriceChart } from "../pages/HistoricalPrice";

export function JudgmentSummary({ decision }: { decision: DecisionItem }) {
  const plan = decision.price_action_plan;
  const research = decision.research;
  return (
    <Descriptions
      column={1}
      size="small"
      contentStyle={{ display: "block", overflowWrap: "anywhere" }}
      items={[
        {
          key: "why",
          label: "1. 为什么关注这只股票？",
          children:
            research?.thesis ||
            decision.why_selected ||
            plan?.watch_reason ||
            "关注来源尚待核验",
        },
        {
          key: "state",
          label: "2. 当前为什么出现或尚未出现条件？",
          children: (
            <>
              {judgmentState(decision)}。{judgmentReason(decision)}
              {plan?.entry_confirmation_rule && (
                <div>
                  规则要求：{priceRuleText(plan.entry_confirmation_rule)}
                </div>
              )}
              <div>
                缺失确认：
                {confirmationText(plan?.blockers ?? decision.blockers)}
              </div>
            </>
          ),
        },
        {
          key: "price",
          label: "3. 具体价位如何计算？",
          children: (
            <>
              <div>
                已核验参考价 {plan?.current_reference_price ?? "未提供"}
                ；建仓观察价 {plan?.entry_trigger_price ?? "尚无获准条件"}
                ；结构失效参考 {plan?.invalidation_price ?? "未提供"}。
              </div>
              <div>
                {(plan?.model_or_rule_version ===
                "hotspot-prior-five-completed-bars-v1"
                  ? "取最后已完成 K 线之前五根的最高价最大值作为突破观察价、最低价最小值作为失效参考；成交量以这五根的算术均量比较。"
                  : firstResearchText(plan?.explanation)) ||
                  (research
                    ? `估值模型 ${research.valuation?.model_type ?? "未提供"}；估值日期 ${research.valuation?.valuation_date ?? "未提供"}；Bear/Base/Bull 及假设见下方研究依据。估值情景不自动成为买入阈值。`
                    : "各周期输入、规则和输出见下方价格计算依据；缺少输入时不能复算。")}
              </div>
            </>
          ),
        },
        {
          key: "exit",
          label: "4. 什么时候判断失效？",
          children:
            priceRuleText(plan?.invalidation_rule) ||
            firstResearchText(plan?.exit_condition) ||
            firstResearchText(research?.exit_conditions) ||
            firstResearchText(decision.thesis_breakers) ||
            "失效条件尚待核验",
        },
        {
          key: "risk",
          label: "5. 哪些风险使判断不成立？",
          children:
            firstResearchText(plan?.counter) ||
            firstResearchText(decision.counter_evidence) ||
            research?.price?.unavailable_reason ||
            "风险反证尚未提供，不能视为无风险",
        },
        {
          key: "eligible",
          label: "6. 现在是否具备正式操作资格？",
          children: (
            <>
              {judgmentState(decision)}
              ；系统不下单。证券级条件不代表个人加减仓资格，须核对资金池、现金、可卖股数、T+1、停牌、涨跌停、跳空、流动性及费用。
              <div>
                加仓：{plan?.add_condition ?? "未提供"}；减仓：
                {plan?.reduce_condition ?? "未提供"}
              </div>
            </>
          ),
        },
      ]}
    />
  );
}

export function CurrentJudgmentChart({ decision }: { decision: DecisionItem }) {
  const [period, setPeriod] = useState<"daily" | "60m" | "15m">("60m");
  const load = useCallback(
    (signal: AbortSignal) =>
      api.currentPriceCase(decision.symbol || "", signal),
    [decision.symbol],
  );
  const result = useApi(load);
  if (result.loading) return <p>正在核验当前价格依据…</p>;
  if (
    result.error ||
    !result.data ||
    !currentCaseMatches(decision, result.data)
  )
    return (
      <Alert
        type="warning"
        showIcon
        message="当前图表数据不可用或与判断版本不一致"
        description={
          result.error || "请刷新判断；历史图表不会替代当前价格依据。"
        }
      />
    );
  const value = result.data;
  const level = value.levels?.[period];
  const bars = value.bars?.[period] ?? [];
  const lastIndex = level
    ? bars.findIndex((bar) => bar.time === level.last_bar)
    : -1;
  const prior =
    level && lastIndex >= level.window
      ? bars.slice(lastIndex - level.window, lastIndex)
      : [];
  const last = lastIndex >= 0 ? bars[lastIndex] : null;
  const source = value.source_bindings?.[period];
  return (
    <section aria-label="当前价格计算依据">
      <h3>当前价格计算依据</h3>
      <p>
        行情截至 {value.market_trade_date}{" "}
        已完成交易时段；收盘后生成的条件用于下一可交易时段观察，不表示盘中可提前执行。下一时段：
        {value.price_action_plan.next_session_date ??
          value.price_action_plan.next_completed_eligible_session ??
          value.price_action_plan.next_session ??
          "待核验"}
        。
      </p>
      <Segmented
        value={period}
        onChange={(next) => setPeriod(next as typeof period)}
        options={[
          { label: "日线", value: "daily" },
          { label: "60 分钟", value: "60m" },
          { label: "15 分钟", value: "15m" },
        ]}
      />
      {level && bars.length ? (
        <>
          <p>
            本周期观察价 {level.entry_trigger_price}；失效参考{" "}
            {level.invalidation_price}；最近已完成收盘 {level.reference_close}
            ；量比 {level.volume_ratio}。
            {priceRuleText(level.entry_confirmation_rule)}
            {priceRuleText(level.invalidation_rule)}
          </p>
          <PriceChart
            bars={bars}
            period={period}
            trigger={Number(level.entry_trigger_price)}
            invalidation={Number(level.invalidation_price)}
            reference={
              value.current_reference_price == null
                ? null
                : Number(value.current_reference_price)
            }
            scope="已完成行情与未来条件观察"
          />
          <p>
            TradingView Lightweight Charts™ ·{" "}
            <a
              href="https://www.tradingview.com/"
              target="_blank"
              rel="noreferrer"
            >
              TradingView
            </a>
          </p>
          <p>
            周期规则 {level.rule_version}；窗口 {level.window} 根；最后已完成 K
            线 {level.last_bar}。单周期成立不代表多周期或正式准入。
          </p>
          {prior.length === level.window && last ? (
            <>
              <p>
                以下为最后已完成 K 线之前的 {level.window}{" "}
                根输入。按登记规则取最高价最大值为突破参考、最低价最小值为失效参考；成交量比较当根{" "}
                {last.volume} 与以下成交量算术平均值，后台量比为{" "}
                {level.volume_ratio}。本周期结果：
                {level.breakout_observed
                  ? "已观察到规则触发"
                  : "价格与量能未同时满足"}
                。
              </p>
              <Table
                size="small"
                pagination={false}
                rowKey="time"
                scroll={{ x: 600 }}
                dataSource={prior}
                columns={[
                  { title: "已完成时间", dataIndex: "time" },
                  { title: "最高价", dataIndex: "high" },
                  { title: "最低价", dataIndex: "low" },
                  { title: "收盘", dataIndex: "close" },
                  { title: "成交量", dataIndex: "volume" },
                ]}
              />
            </>
          ) : (
            <Alert type="warning" message="规则窗口输入不完整，当前不能复算" />
          )}
        </>
      ) : (
        <Alert type="info" message="此周期尚无完整行情与计算结果" />
      )}
      <DetailSection
        title="可复算解释与规则输入输出"
        value={value.price_action_plan.explanation}
      />
      <DetailSection title="支持依据" value={value.price_action_plan.support} />
      <DetailSection
        title="反证与未满足确认"
        value={
          value.price_action_plan.counter ?? value.price_action_plan.blockers
        }
      />
      <details>
        <summary>查看版本、来源与计算绑定</summary>
        <DetailSection title="判断版本" value={value.price_action_plan} />
        <DetailSection title="来源与哈希" value={source} />
      </details>
    </section>
  );
}
