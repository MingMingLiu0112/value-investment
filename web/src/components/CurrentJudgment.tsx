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
  planConditionText,
  missingPricePolicies,
} from "../utils/currentJudgment";
import { firstResearchText } from "../utils/opportunityView";
import { DetailSection } from "./DetailSection";
import { PriceChart } from "../pages/HistoricalPrice";
import { decisionEligibility } from "../utils/decisionEligibility";
import {
  formatScenarioValue,
  normalizeEvidenceLines,
} from "../utils/researchDetail";
import { formatDecimal } from "../utils/format";
import { ValuePolicyReview } from "./ValuePolicyReview";

export function JudgmentSummary({ decision }: { decision: DecisionItem }) {
  const plan = decision.price_action_plan;
  const eligibility = decisionEligibility(decision);
  const reviewConditions = new Map<string, string[]>();
  for (const [label, condition] of [
    ["退出复核", planConditionText(plan?.exit_condition)],
    ["减仓复核", planConditionText(plan?.reduce_condition)],
    [
      "结构失效",
      planConditionText(plan?.invalidation_condition) ||
        (plan?.invalidation_price != null
          ? `参考 ${plan.invalidation_price}；${priceRuleText(plan.invalidation_rule)}`
          : undefined),
    ],
  ]) {
    if (!condition) continue;
    const text = condition.trim();
    reviewConditions.set(text, [...(reviewConditions.get(text) ?? []), label!]);
  }
  const exitSummary = Array.from(
    reviewConditions,
    ([text, labels]) => `${labels.join(" / ")}：${text}`,
  ).join("；");
  const concise = (value: string) => (
    <p
      style={{
        margin: 0,
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
        overflowWrap: "anywhere",
      }}
    >
      {value}
    </p>
  );
  const rows = [
    [
      "当前判断",
      `${judgmentState(decision)}；证券资格：${eligibility.formal}；个人组合：${eligibility.portfolio}。不自动下单。`,
    ],
    [
      "观察入场条件",
      planConditionText(plan?.entry_condition) ||
        (plan?.entry_trigger_price != null
          ? `观察价 ${plan.entry_trigger_price}；${priceRuleText(plan.entry_confirmation_rule)}`
          : missingPricePolicies(decision) ||
            "尚无获准入场价，等待价格政策与条件核验"),
    ],
    [
      "退出或失效条件",
      exitSummary ||
        firstResearchText(decision.thesis_breakers) ||
        "退出与失效条件待核验，不代表个人卖出许可",
    ],
    [
      "为什么关注",
      decision.research?.thesis ||
        plan?.thesis ||
        decision.why_selected ||
        plan?.watch_reason ||
        judgmentReason(decision),
    ],
    [
      "主要风险",
      firstResearchText(
        plan?.counter ?? plan?.counter_evidence ?? decision.counter_evidence,
      ) ||
        firstResearchText(decision.thesis_breakers) ||
        confirmationText(plan?.blockers ?? decision.blockers ?? []) ||
        "主要风险待核验",
    ],
    [
      "下一步",
      firstResearchText(plan?.next_observation) ||
        firstResearchText(decision.next_events) ||
        `等待下一完成时段 ${plan?.next_session_date ?? plan?.next_completed_eligible_session ?? plan?.next_session ?? "待核验"}，复核独立门禁；成交由本人决定并记录`,
    ],
  ];
  return (
    <section aria-label="六项操作计划">
      <Descriptions
        layout="vertical"
        column={{ xs: 1, sm: 2, md: 3 }}
        size="small"
        items={rows.map(([label, text], index) => ({
          key: label,
          label: `${index + 1}. ${label}`,
          children: concise(text),
        }))}
      />
      {plan && (
        <p style={{ margin: "0 0 8px", overflowWrap: "anywhere" }}>
          参考收盘{" "}
          {plan.reference_close ?? plan.current_reference_price ?? "待核验"}（
          {plan.market_trade_date ?? "日期待核验"}）
          {["CORE_VALUE", "value"].includes(decision.strategy ?? "") && (
            <>
              ；保留研究估值：
              {formatScenarioValue(
                plan.conditional_valuation_range?.bear ?? plan.bear,
              )}{" "}
              /{" "}
              {formatScenarioValue(
                plan.conditional_valuation_range?.base ?? plan.base,
              )}{" "}
              /{" "}
              {formatScenarioValue(
                plan.conditional_valuation_range?.bull ?? plan.bull,
              )}
              （悲观 / 中性 / 乐观）；股价比较资格：
              {plan.price_comparison_eligible === true
                ? "已通过"
                : "未通过或未核验，不能据此判断买价"}
            </>
          )}
        </p>
      )}
      {["CORE_VALUE", "value"].includes(decision.strategy ?? "") &&
        decision.symbol && <ValuePolicyReview symbol={decision.symbol} />}
      <details>
        <summary>展开完整条件、风险与资格依据</summary>
        <JudgmentEvidence decision={decision} />
      </details>
    </section>
  );
}

function JudgmentEvidence({ decision }: { decision: DecisionItem }) {
  const plan = decision.price_action_plan;
  const research = decision.research;
  const eligibility = decisionEligibility(decision);
  const selection = plan?.daily_selection;
  return (
    <>
      <Descriptions
        layout="vertical"
        column={1}
        size="small"
        contentStyle={{ display: "block", overflowWrap: "anywhere" }}
        items={[
          {
            key: "why",
            label: "1. 为什么关注这只股票？",
            children: (
              <>
                {research?.thesis ||
                  plan?.thesis ||
                  decision.why_selected ||
                  plan?.watch_reason ||
                  "关注来源尚待核验"}
                {selection && (
                  <div>
                    观察序位 {selection.rank ?? "未提供"}；行业{" "}
                    {selection.industry ?? "未核验"}；行情日{" "}
                    {selection.trade_date ?? "未核验"}；行业相对涨跌{" "}
                    {formatDecimal(
                      selection.industry_relative_strength_percent,
                    )}{" "}
                    个百分点（覆盖样本）；排序规则{" "}
                    {plan?.selection_rule_version ?? "未登记"}。
                  </div>
                )}
                {plan?.market_environment && (
                  <div>
                    市场覆盖{" "}
                    {plan.market_environment.covered_securities ?? "未提供"}{" "}
                    只；等权涨跌{" "}
                    {formatDecimal(
                      plan.market_environment.equal_weight_change_percent,
                    )}
                    %（覆盖样本）；市场环境准入{" "}
                    {plan.market_environment.regime_admission === "UNKNOWN"
                      ? "未知"
                      : (plan.market_environment.regime_admission ?? "未核验")}
                    。
                  </div>
                )}
                {normalizeEvidenceLines(
                  plan?.support ?? plan?.supporting_facts ?? decision.support,
                ).map((line, index) => (
                  <div key={index}>支持：{line.text}</div>
                ))}
              </>
            ),
          },
          {
            key: "state",
            label: "2. 当前为什么出现或尚未出现条件？",
            children: (
              <>
                {judgmentState(decision)}。{judgmentReason(decision)}
                {plan?.period_structure && (
                  <div>
                    周期结构：
                    {Object.entries(plan.period_structure)
                      .map(
                        ([period, structure]) =>
                          `${period} ${({ BREAKOUT: "已观察突破", INVALIDATED: "结构失效", PRICE_ABOVE_VOLUME_PENDING: "价格突破，量能未确认", RANGE: "区间内" } as Record<string, string>)[structure] ?? structure}`,
                      )
                      .join("；")}
                    。
                  </div>
                )}
                {plan?.entry_confirmation_rule && (
                  <div>
                    规则要求：{priceRuleText(plan.entry_confirmation_rule)}
                  </div>
                )}
                {plan?.price_behavior && (
                  <div>
                    日线趋势：
                    {(
                      {
                        UPTREND: "上升（高点与低点抬高）",
                        DOWNTREND: "下降（高点与低点降低）",
                        RANGE: "震荡",
                        UNKNOWN: "已确认摆动不足",
                      } as Record<string, string>
                    )[plan.price_behavior.daily_trend] ?? "未知"}
                    ； 突破后确认：
                    {plan.price_behavior.breakout
                      .confirmed_on_next_completed_bar
                      ? "已观察"
                      : "未观察"}
                    ； 缩量回踩后恢复：
                    {plan.price_behavior.pullback_recovery.observed
                      ? "已观察"
                      : "未观察"}
                    ； 15分钟辅助突破：
                    {plan.price_behavior.auxiliary_15m.observed
                      ? "已观察"
                      : "未观察"}
                    。
                    <div>
                      确认支撑{" "}
                      {plan.price_behavior.confirmed_support?.price ?? "未形成"}
                      ；确认阻力{" "}
                      {plan.price_behavior.confirmed_resistance?.price ??
                        "未形成"}
                      。摆动点需右侧两根完整K线确认，不是盘中预知。
                    </div>
                    <div>
                      结构空间／价格风险：
                      {plan.price_behavior.risk_reward_ratio
                        ? formatDecimal(plan.price_behavior.risk_reward_ratio)
                        : "无可靠上方目标，暂不计算"}
                      。不含费用和跳空风险，不代表预期收益或正式准入。
                    </div>
                  </div>
                )}
                <div>
                  缺失确认：
                  {confirmationText(plan?.blockers ?? decision.blockers)}
                </div>
                {missingPricePolicies(decision) && (
                  <div>{missingPricePolicies(decision)}</div>
                )}
              </>
            ),
          },
          {
            key: "price",
            label: "3. 具体价位如何计算？",
            children: (
              <>
                <div>
                  参考价{" "}
                  {plan?.current_reference_price ??
                    plan?.reference_close ??
                    "未提供"}
                  ；建仓观察价 {plan?.entry_trigger_price ?? "尚无获准条件"}
                  ；结构失效参考 {plan?.invalidation_price ?? "未提供"}。
                </div>
                {(plan?.conditional_valuation_range ||
                  research?.valuation ||
                  plan?.bear != null) && (
                  <div>
                    研究估值情景：Bear{" "}
                    {formatScenarioValue(
                      plan?.conditional_valuation_range?.bear ??
                        plan?.bear ??
                        research?.valuation?.bear,
                    )}{" "}
                    / Base{" "}
                    {formatScenarioValue(
                      plan?.conditional_valuation_range?.base ??
                        plan?.base ??
                        research?.valuation?.base,
                    )}{" "}
                    / Bull{" "}
                    {formatScenarioValue(
                      plan?.conditional_valuation_range?.bull ??
                        plan?.bull ??
                        research?.valuation?.bull,
                    )}
                    ；这是研究情景，不是获准操作价。
                  </div>
                )}
                {plan?.entry_condition && (
                  <div>
                    建仓条件：
                    {planConditionText(plan.entry_condition) ??
                      "条件尚未提供可读依据"}
                  </div>
                )}
                {plan?.price_comparison_eligible !== undefined && (
                  <div>
                    现价与估值可比性：
                    {plan.price_comparison_eligible
                      ? "已通过"
                      : "未通过，参考价不能作为估值买点依据"}
                    。
                  </div>
                )}
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
              planConditionText(plan?.invalidation_condition) ||
              planConditionText(plan?.exit_condition) ||
              firstResearchText(research?.exit_conditions) ||
              firstResearchText(decision.thesis_breakers) ||
              "失效条件尚待核验",
          },
          {
            key: "risk",
            label: "5. 哪些风险使判断不成立？",
            children: (
              <>
                {normalizeEvidenceLines(
                  plan?.counter ??
                    plan?.counter_evidence ??
                    decision.counter_evidence,
                ).length
                  ? normalizeEvidenceLines(
                      plan?.counter ??
                        plan?.counter_evidence ??
                        decision.counter_evidence,
                    ).map((line, index) => <div key={index}>{line.text}</div>)
                  : research?.price?.unavailable_reason ||
                    "风险反证尚未提供，不能视为无风险"}
                {!!plan?.required_confirmations?.length && (
                  <div>
                    仍未知或待确认：
                    {confirmationText(plan.required_confirmations)}
                  </div>
                )}
              </>
            ),
          },
          {
            key: "eligible",
            label: "6. 现在是否具备正式操作资格？",
            children: (
              <>
                {judgmentState(decision)}
                <div>
                  研究意图：{eligibility.intent}；证券级正式资格：
                  {eligibility.formal}；个人组合资格：{eligibility.portfolio}。
                </div>
                系统不下单。证券级条件不代表个人加减仓资格，须核对资金池、现金、可卖股数、T+1、停牌、涨跌停、跳空、流动性及费用。
                <div>
                  加仓：{planConditionText(plan?.add_condition) ?? "未提供"}
                  ；减仓：
                  {planConditionText(plan?.reduce_condition) ?? "未提供"}
                  ；退出复核：
                  {planConditionText(plan?.exit_condition) ?? "未提供"}
                </div>
                {eligibility.intent === "退出复核" && (
                  <div>
                    结构失效仅触发证券级退出复核，不代表个人卖出许可或卖出数量。
                  </div>
                )}
                {plan?.expires_after_session && (
                  <div>
                    本轮条件有效至 {plan.expires_after_session}{" "}
                    会话；新行情完成后须重新判断。
                    {firstResearchText(plan.next_observation)}
                  </div>
                )}
              </>
            ),
          },
        ]}
      />
    </>
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
            ；量比 {formatDecimal(level.volume_ratio)}。 规则要求：
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
          <details>
            <summary>查看本周期规则窗口与计算输入</summary>
            {prior.length === level.window && last ? (
              <>
                <p>
                  以下为最后已完成 K 线之前的 {level.window}{" "}
                  根输入。按登记规则取最高价最大值为突破参考、最低价最小值为失效参考；成交量比较当根{" "}
                  {last.volume} 与以下成交量算术平均值，后台量比为{" "}
                  {formatDecimal(level.volume_ratio)}。本周期结果：
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
              <Alert
                type="warning"
                message="规则窗口输入不完整，当前不能复算"
              />
            )}
          </details>
        </>
      ) : (
        <Alert type="info" message="此周期尚无完整行情与计算结果" />
      )}
      <details>
        <summary>查看解释、支持与反证</summary>
        <DetailSection
          title="可复算解释与规则输入输出"
          value={value.price_action_plan.explanation}
        />
        <DetailSection
          title="支持依据"
          value={value.price_action_plan.support}
        />
        <DetailSection
          title="反证与未满足确认"
          value={
            value.price_action_plan.counter ?? value.price_action_plan.blockers
          }
        />
      </details>
      <details>
        <summary>查看版本、来源与计算绑定</summary>
        <DetailSection title="判断版本" value={value.price_action_plan} />
        <DetailSection title="来源与哈希" value={source} />
      </details>
    </section>
  );
}
