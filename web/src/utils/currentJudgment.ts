import type { CurrentPriceCase, DecisionItem } from "../types/api";
import { firstResearchText } from "./opportunityView";
import { uniqueBlockerTexts } from "./researchDetail";

export const judgmentGroups = [
  "已通过全部准入的辅助判断",
  "已观察到价格触发，仍待复核",
  "价格触发待发生",
  "研究观察，尚无有效价位",
  "失效或数据不足",
] as const;

export function publicationVersionsMatch(
  daily: string | null | undefined,
  packet: string | null | undefined,
): boolean {
  return typeof daily === "string" && daily.length > 0 && daily === packet;
}

export function judgmentGroup(item: DecisionItem): number {
  const plan = item.price_action_plan;
  if (!plan) return 3;
  if (plan.action !== "no_order") return 4;
  if (
    plan.signal_state === "ACTION_ELIGIBLE" &&
    plan.action_eligibility === true
  )
    return 0;
  if (plan.signal_state === "TRIGGER_OBSERVED") return 1;
  if (plan.signal_state === "TRIGGER_PENDING") return 2;
  if (plan.signal_state === "WATCH")
    return plan.entry_trigger_price != null ? 2 : 3;
  return 4;
}

export function priceRuleText(
  rule: string | null | undefined,
): string | undefined {
  if (
    rule ===
    "completed_close > prior_5_high AND volume >= 1.2 * prior_5_mean_volume"
  )
    return "已完成收盘价高于前五根最高价，且当根成交量不少于前五根均量的 1.2 倍。";
  if (
    rule ===
    "subsequent completed close < prior_5_low; research review required"
  )
    return "后续已完成收盘价低于前五根最低价时，价格结构失效，须重新研究。";
  return rule ?? undefined;
}

export function confirmationText(blockers: string[] | undefined): string {
  const labels: Record<string, string> = {
    INTRADAY_SINGLE_PROVIDER: "分钟行情只有单一来源",
    VALUE_GATE_NOT_PROVEN: "价值门禁尚未通过",
    EVENT_AND_RISK_GATES_NOT_PROVEN: "事件与风险门禁尚未通过",
    PIT_OOS_COST_SHADOW_NOT_PROVEN:
      "信息时点、样本外、成本与 Shadow 检验尚未完成",
    CORPORATE_ACTION_REVIEW_NOT_PROVEN: "复权与公司行动复核尚未完成",
  };
  const items = uniqueBlockerTexts(
    (blockers ?? []).map((item) => labels[item] ?? item),
  );
  return items.length
    ? items.slice(0, 4).join("；") +
        (items.length > 4 ? `；另有 ${items.length - 4} 项确认待完成` : "")
    : "未提供完整确认清单";
}

export function judgmentState(item: DecisionItem): string {
  const state = item.price_action_plan?.signal_state;
  if (state === "HISTORICAL_OBSERVATION_NOT_ADMITTED")
    return "历史观察，不是当前判断";
  return judgmentGroups[judgmentGroup(item)];
}

export function judgmentReason(item: DecisionItem): string {
  return (
    firstResearchText(item.price_action_plan?.explanation) ||
    item.reason ||
    item.why_selected ||
    item.candidate_explanation ||
    "关注理由尚待核验"
  );
}

export function currentCaseMatches(
  item: DecisionItem,
  value: CurrentPriceCase,
): boolean {
  const plan = item.price_action_plan;
  const candidate = value.price_action_plan;
  return (
    !!plan &&
    !!candidate &&
    value.action === "no_order" &&
    candidate.action === "no_order" &&
    value.symbol === item.symbol &&
    !!plan.market_trade_date &&
    value.market_trade_date === plan.market_trade_date &&
    !!plan.decision_id &&
    plan.decision_id === item.id &&
    candidate.decision_id === plan.decision_id &&
    !!plan.research_version &&
    candidate.research_version === plan.research_version &&
    candidate.signal_state !== "HISTORICAL_OBSERVATION_NOT_ADMITTED" &&
    candidate.entry_trigger_price === plan.entry_trigger_price &&
    candidate.invalidation_price === plan.invalidation_price &&
    candidate.current_reference_price === plan.current_reference_price
  );
}

export function fillLink(item: DecisionItem): string {
  const params = new URLSearchParams();
  if (item.symbol) params.set("symbol", item.symbol);
  const strategy =
    item.strategy === "hotspot" || item.strategy === "HOTSPOT_SATELLITE"
      ? "hotspot"
      : item.strategy === "value" || item.strategy === "CORE_VALUE"
        ? "value"
        : null;
  if (strategy) params.set("strategy", strategy);
  params.set("decision_id", item.id);
  const version =
    item.price_action_plan?.research_version ?? item.research?.research_version;
  if (version) params.set("research_version", version);
  return `/portfolio?${params.toString()}`;
}
