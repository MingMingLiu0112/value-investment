import React from "react";
import { expect, it } from "vitest";
import { HotspotLifecycleReview } from "../src/components/HotspotLifecycleReview";
import type {
  HotspotLifecycleReview as Review,
  CurrentPricePlan,
} from "../src/types/api";
import {
  lifecycleFixture,
  lifecycleHeldFixture,
  lifecyclePlan,
} from "./fixtures/hotspot-lifecycle";
const { renderToStaticMarkup } = require("react-dom/server");

const render = (
  review: Review | null | undefined = lifecycleFixture(),
  plan: CurrentPricePlan = lifecyclePlan(),
  available = true,
) =>
  renderToStaticMarkup(
    <HotspotLifecycleReview
      review={review}
      symbol="600519"
      plan={plan}
      available={available}
    />,
  );

it("shows no-entry current observations, real dates and explanatory steps without ownership or action claims", () => {
  const fixture = lifecycleFixture();
  const before = structuredClone(fixture);
  const html = render(fixture);
  for (const phrase of [
    "未提供原入场，仅当前结构观察",
    "不是持有或加仓结论",
    "中文判定步骤与实际输入",
    "当前行情证据",
    "当前加仓结构条件",
    "未评估（不等于未触发）",
    "本次未观察到条件",
    "12.3400",
    "2026-10-22",
    "2026-10-22T16:14:00+08:00",
    "最近已完成收盘，仅供展示",
    "为何不能据此加仓",
    "核验真实持仓归属",
    "核验公司行动",
    "独立策略准入",
    "复核事件风险",
    "复核组合容量",
    "可卖数量、T+1",
    "不授予个人加仓或交易权限",
    "原件引用与 Hash",
  ])
    expect(html).toContain(phrase);
  expect(html).not.toContain("<button");
  expect(html).not.toContain("<input");
  expect(fixture).toEqual(before);
});

it("preserves original protection and first breach despite recovery or a lower rolling level", () => {
  const html = render(lifecycleHeldFixture());
  for (const value of [
    "原始参考保护价（元）",
    "11.00",
    "当前滚动保护价（元）",
    "9.00",
    "首次收盘破位时点",
    "2026-10-20T11:30:00+08:00",
    "首次破位收盘价（元）",
    "10.00",
    "后来恢复不能抹去破位",
  ])
    expect(html).toContain(value);
  expect(html).not.toContain("可以加仓");
});

it("keeps a raw unadjusted ADD record out of the effective conclusion when price basis is unknown", () => {
  const review = lifecycleHeldFixture();
  review.status = "NOT_ASSESSABLE";
  review.observed_review = "UNKNOWN";
  review.decision_explanation.selected_review = "UNKNOWN";
  review.decision_explanation.basis_code = "PRICE_BASIS_UNKNOWN";
  review.unadjusted_structural_observation = {
    observed_review: "ADD_STRUCTURE_REVIEW",
    action: "no_order",
  };
  const html = render(review);
  expect(html).toContain("本次观察：<strong>未知</strong>");
  expect(html).toContain("不将其作为有效持有、加仓或退出结论");
  expect(html).not.toContain("本次观察：<strong>加仓结构复核</strong>");
});

it.each(["UNKNOWN", "INCOMPARABLE"])(
  "explains %s price comparability without changing the supplied decision",
  (status) => {
    const review = lifecycleHeldFixture();
    review.decision_explanation.basis_code = `PRICE_BASIS_${status}`;
    review.decision_explanation.decision_path.push({
      check: "PRICE_COMPARABILITY",
      outcome: status,
      values: { status },
      evidence_bindings: [],
    });
    const html = render(review);
    expect(html).toContain(
      status === "UNKNOWN" ? "公司行动覆盖未核验" : "不复权价格不能直接比较",
    );
  },
);

it("shows stale unknown assessment rather than filling prices or treating unevaluated as false", () => {
  const review = lifecycleFixture();
  review.current_data_status = "STALE";
  review.observed_review = "UNKNOWN";
  review.decision_explanation.selected_review = "UNKNOWN";
  review.decision_explanation.basis_code = "CURRENT_DATA_UNAVAILABLE";
  review.decision_explanation.current_price_observation = null;
  review.decision_explanation.decision_path = [
    {
      check: "CURRENT_ADD",
      outcome: "NOT_EVALUATED",
      values: {},
      evidence_bindings: [],
    },
  ];
  const html = render(review);
  expect(html).toContain("行情状态：已过期");
  expect(html).toContain("价格观察（元）：未知");
  expect(html).toContain("未评估（不等于未触发）");
  expect(html).not.toContain("本次未观察到条件");
});

it.each([
  (r: Review) => {
    r.schema_version = "v1" as any;
  },
  (r: Review) => {
    r.symbol = "600887";
  },
  (r: Review) => {
    r.action = "order" as any;
  },
  (r: Review) => {
    r.personal_action = "BUY" as any;
  },
  (r: Review) => {
    r.trade_eligible = true as false;
  },
  (r: Review) => {
    r.formal_eligibility = true as false;
  },
  (r: Review) => {
    r.risk_review_eligible = true as false;
  },
  (r: Review) => {
    r.position_guidance = { target: "20%" } as any;
  },
  (r: Review) => {
    r.current_case_binding = {
      path: "runtime/TEST_ONLY/other.json",
      sha256: "a".repeat(64),
    };
  },
  (r: Review) => {
    r.decision_explanation.action = "order" as any;
  },
  (r: Review) => {
    r.decision_explanation.selected_review = "ADD_STRUCTURE_REVIEW";
  },
  (r: Review) => {
    r.decision_explanation.current_price_observation!.as_of = "2026-10-21";
  },
  (r: Review) => {
    r.decision_explanation.decision_path[0].evidence_bindings = [
      { path: "../escape", sha256: "x" },
    ];
  },
])("refuses mismatched or permission-changing payload %#", (change) => {
  const review = lifecycleFixture();
  change(review);
  expect(render(review)).toContain("不匹配，暂不可评价");
  expect(render(review)).not.toContain("12.3400");
});

it.each(["BLOCKED", "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"])(
  "cannot revive a rejected parent plan %s",
  (status) => {
    const plan = lifecyclePlan();
    if (status === "BLOCKED") plan.signal_state = status;
    else plan.candidate_lifecycle = status;
    expect(render(lifecycleFixture(), plan)).toContain("不匹配，暂不可评价");
  },
);

it("missing material and failed/reloading responses cannot imply zero opportunities", () => {
  expect(render(null)).toContain("尚未接入或当前不可核验");
  expect(render(lifecycleFixture(), lifecyclePlan(), false)).toContain(
    "暂不可评价",
  );
  expect(render(null)).toContain("不等于没有机会或未触发风险");
});
