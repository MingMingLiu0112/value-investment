import { blockerText } from "../utils/packet";
import { planConditionText } from "../utils/currentJudgment";
import type { PlanCondition } from "../types/api";

export interface ConditionalAccountDecision {
  action: "no_order";
  decision_action: "BUY" | "ADD" | "NO_TRADE" | "UNASSESSABLE";
  symbol: string;
  strategy: string;
  decision_reason: string;
  blockers: string[];
  review_quantity: number | null;
  broker_execution_permission: false;
  data_trade_date?: string | null;
  decision_generated_at?: string | null;
  current_verified_reference_price?: string | null;
  entry_price_or_range?: string | null;
  plan_expiry?: string | null;
  available_cash_impact?: string | null;
  entry_condition?: PlanCondition | null;
  add_condition?: PlanCondition | null;
  reduce_condition?: PlanCondition | null;
  exit_condition?: PlanCondition | null;
  invalidation_condition?: PlanCondition | null;
  risk_sizing?: Record<string, string | number | boolean | null> | null;
  expected_fees_and_slippage?: Record<string, string | null> | null;
}

export function ActionableDecisionResult({
  decision,
}: {
  decision: ConditionalAccountDecision;
}) {
  if (
    decision.action !== "no_order" ||
    decision.broker_execution_permission !== false
  )
    return <p role="alert">决策响应无法核验，不提供操作结论。</p>;
  const positive = ["BUY", "ADD"].includes(decision.decision_action);
  if (
    positive &&
    (decision.blockers.length > 0 ||
      !Number.isInteger(decision.review_quantity) ||
      (decision.review_quantity ?? 0) <= 0)
  )
    return <p role="alert">动作与风险结果不一致，不提供可操作股数。</p>;
  return (
    <section aria-label="账户条件性行动结论">
      <h3>
        {decision.decision_action === "BUY"
          ? "条件性新建仓复核"
          : decision.decision_action === "ADD"
            ? "条件性加仓复核"
            : decision.decision_action === "UNASSESSABLE"
              ? "无法评价 · 必要证据或个人风险输入不完整"
              : "NO_TRADE · 本次不形成新交易动作"}
      </h3>
      <p>
        {decision.symbol} ·{" "}
        {decision.strategy === "CORE_VALUE" ? "价值策略" : "热点策略"}
      </p>
      {positive ? (
        <p>
          当前条件下复核数量：{decision.review_quantity}{" "}
          股；操作前仍须确认计划、报价与账户没有变化。
        </p>
      ) : (
        <p>未给出个人可操作股数。</p>
      )}
      <dl>
        {[
          ["行情交易日", decision.data_trade_date],
          ["判断生成时间", decision.decision_generated_at],
          ["已核验参考价（元）", decision.current_verified_reference_price],
          ["入场条件价（元）", decision.entry_price_or_range],
          ["计划有效期", decision.plan_expiry],
          [
            "预计现金占用（元）",
            positive ? decision.available_cash_impact : null,
          ],
          ["建仓条件", planConditionText(decision.entry_condition)],
          ["加仓条件", planConditionText(decision.add_condition)],
          ["减仓条件", planConditionText(decision.reduce_condition)],
          ["退出条件", planConditionText(decision.exit_condition)],
          ["失效条件", planConditionText(decision.invalidation_condition)],
        ].map(([label, value]) => (
          <div
            key={label}
            style={{ overflowWrap: "anywhere", marginBottom: 6 }}
          >
            <dt>{label}</dt>
            <dd style={{ marginLeft: 0 }}>{value ?? "未形成可用结果"}</dd>
          </div>
        ))}
      </dl>
      {!!decision.expected_fees_and_slippage && (
        <details>
          <summary>本次费用与滑点假设</summary>
          <ul>
            {[
              ["买入费用比率", "buy_fee_fraction"],
              ["卖出费用比率", "sell_fee_fraction"],
              ["最低买入费用（元）", "minimum_buy_fee_cny"],
              ["最低卖出费用（元）", "minimum_sell_fee_cny"],
              ["买入滑点（元/股）", "entry_slippage_cny"],
              ["卖出滑点（元/股）", "exit_slippage_cny"],
              ["跳空压力（元/股）", "gap_stress_cny"],
            ].map(([label, key]) => (
              <li key={key}>
                {label}：
                {decision.expected_fees_and_slippage?.[key] ?? "未提供"}
              </li>
            ))}
          </ul>
        </details>
      )}
      {decision.blockers.length ? (
        <ul>
          {decision.blockers.map((code) => (
            <li key={code}>{blockerText(code)}</li>
          ))}
        </ul>
      ) : (
        <p>{decision.decision_reason}</p>
      )}
      <p>实际买卖由本人在券商软件决定并操作，随后登记真实成交。</p>
    </section>
  );
}
