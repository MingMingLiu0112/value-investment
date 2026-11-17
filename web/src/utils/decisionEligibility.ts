import type { DecisionItem, Eligibility } from "../types/api";

export function eligibilityText(value: Eligibility | undefined): string {
  if (value === true) return "已通过";
  if (value === false) return "未通过";
  if (value == null || value === "") return "未核验";
  const labels: Record<string, string> = {
    ELIGIBLE: "已通过",
    NOT_ELIGIBLE: "未通过",
    BLOCKED_PRIVATE_INPUT: "缺少已确认的私人输入",
    BLOCKED: "存在阻塞",
    UNKNOWN: "未核验",
    NOT_APPLICABLE: "不适用",
  };
  return labels[value] ?? value;
}

export function decisionEligibility(item: DecisionItem) {
  const plan = item.price_action_plan;
  const intent = item.action_intent ?? plan?.action_intent;
  const intents: Record<string, string> = {
    OPEN: "建仓复核",
    ADD: "加仓复核",
    REDUCE: "减仓复核",
    EXIT: "退出复核",
    WATCH: "观察",
    HOLD: "持有研究意图",
  };
  return {
    intent: intent ? (intents[intent] ?? intent) : "未提供研究意图",
    formal: eligibilityText(
      item.formal_eligibility !== undefined
        ? item.formal_eligibility
        : plan?.formal_eligibility,
    ),
    portfolio: eligibilityText(
      item.portfolio_eligibility !== undefined
        ? item.portfolio_eligibility
        : plan?.portfolio_eligibility,
    ),
  };
}
