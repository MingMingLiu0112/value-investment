import type {
  DailyEvaluationItem,
  StrategyReadiness,
} from "../../src/types/api";

export function readinessFixture(
  strategy: "CORE_VALUE" | "HOTSPOT_SATELLITE" = "CORE_VALUE",
): StrategyReadiness {
  const keys =
    strategy === "CORE_VALUE"
      ? [
          "screen",
          "research",
          "valuation",
          "model_validity",
          "price",
          "action_policy",
          "portfolio",
          "human_decision",
        ]
      : [
          "screen",
          "structure",
          "validation",
          "price",
          "action_policy",
          "portfolio",
          "human_decision",
        ];
  return {
    schema_version: "strategy-readiness-v1",
    strategy,
    action: "no_order",
    authorization_granted: false,
    steps: keys.map((key) => ({
      key,
      label: "",
      status:
        key === "screen"
          ? "READY"
          : key === "portfolio"
            ? "NOT_EVALUATED"
            : "PENDING",
      reason:
        key === "screen"
          ? "已列入本次展示范围，初筛不等于批准。"
          : "测试证据尚未核验。",
    })),
    primary_gap: {
      code: "MODEL_AND_EVENT_REVIEW_PENDING",
      category: strategy === "CORE_VALUE" ? "REVIEW" : "STRATEGY_VALIDATION",
      summary: "测试研究待复核，不授予操作资格。",
      next_action: "核对当前证据",
      url:
        strategy === "CORE_VALUE"
          ? "/decisions/600887#value-review-handoff"
          : "/decisions/hotspot-600887?independent_hotspot=true",
    },
    conditional_valuation: null,
    price_snapshot: null,
    independent_of_value_valuation: strategy === "HOTSPOT_SATELLITE",
  };
}

export function evaluationFixture(
  strategy: "CORE_VALUE" | "HOTSPOT_SATELLITE" = "CORE_VALUE",
): DailyEvaluationItem {
  return {
    symbol: "600887",
    company_name: "测试证券",
    strategy,
    decision_action: "UNASSESSABLE",
    decision_reason: "必要证据未完整，无法评价。",
    evaluation_status: "UNASSESSABLE",
    eligibility: false,
    readiness: readinessFixture(strategy),
  };
}
