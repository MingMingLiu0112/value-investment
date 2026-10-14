import { expect, it } from "vitest";
import { decisionEligibility } from "../src/utils/decisionEligibility";
import {
  confirmationText,
  judgmentGroup,
  missingPricePolicies,
  planConditionText,
} from "../src/utils/currentJudgment";
import type { DecisionItem } from "../src/types/api";

const item: DecisionItem = {
  id: "hotspot-300364",
  action_intent: "OPEN",
  formal_eligibility: false,
  portfolio_eligibility: null,
  price_action_plan: {
    action: "no_order",
    signal_state: "TRIGGER_OBSERVED",
    action_eligibility: false,
    entry_trigger_price: "12",
    invalidation_price: "10",
  },
};

it("keeps research intent, observed trigger, formal and personal admission independent", () => {
  expect(decisionEligibility(item)).toEqual({
    intent: "建仓复核",
    formal: "未通过",
    portfolio: "未核验",
  });
  expect(judgmentGroup(item)).toBe(1);
  expect(
    decisionEligibility({
      ...item,
      formal_eligibility: true,
      portfolio_eligibility: "BLOCKED_PRIVATE_INPUT",
    }),
  ).toEqual({
    intent: "建仓复核",
    formal: "已通过",
    portfolio: "缺少已确认的私人输入",
  });
  expect(
    decisionEligibility({ id: "missing", candidate_action: "BUY" }).intent,
  ).toBe("未提供研究意图");
});

it("explicit null is never upgraded by a plan fallback", () => {
  expect(
    decisionEligibility({
      ...item,
      price_action_plan: {
        ...item.price_action_plan!,
        portfolio_eligibility: true,
      },
    }).portfolio,
  ).toBe("未核验");
});

it("explains registered condition objects and missing value policies without manufacturing prices", () => {
  expect(planConditionText(null)).toBeUndefined();
  expect(planConditionText({ price: "20", rule: "registered rule" })).toBe(
    "条件价 20；registered rule",
  );
  expect(
    planConditionText({ price: null, reasons: ["投资论点发生变化"] }),
  ).toBe("投资论点发生变化");
  expect(
    confirmationText([
      "VALUE_PRICE_COMPARISON_NOT_ELIGIBLE",
      "VALUE_MODEL_EVENT_SCAN_DOES_NOT_COVER_QUOTE",
      "VALUE_DECISION_REQUIRES_HUMAN_CONFIRMATION",
    ]),
  ).toBe(
    "现价与估值尚不具备合法可比性；模型事件扫描尚未覆盖该行情日期；价值操作判断仍需本人确认",
  );
  expect(
    missingPricePolicies({
      id: "value",
      blockers: [
        "VALUE_ENTRY_PRICE_POLICY_MISSING_OR_INAPPLICABLE",
        "VALUE_EXIT_PRICE_POLICY_MISSING_OR_INAPPLICABLE",
      ],
    }),
  ).toBe(
    "建仓价格政策未登记或不适用；退出价格政策未登记或不适用；暂无相应获准价位，估值情景不替代操作政策。",
  );
});

it("keeps expired and blocked candidates secondary despite intent or old eligibility", () => {
  for (const signal_state of [
    "INVALIDATED",
    "EXPIRED",
    "STALE",
    "BLOCKED",
    "TRIGGER_REJECTED",
  ])
    expect(
      judgmentGroup({
        ...item,
        formal_eligibility: true,
        price_action_plan: {
          ...item.price_action_plan!,
          signal_state,
          action_eligibility: true,
        },
      }),
    ).toBe(4);
  expect(judgmentGroup({ id: "no-plan", status: "EXPIRED" })).toBe(4);
  expect(
    judgmentGroup({
      ...item,
      price_action_plan: {
        ...item.price_action_plan!,
        signal_state: "ACTION_ELIGIBLE",
        action_eligibility: true,
      },
    }),
  ).toBe(4);
});
