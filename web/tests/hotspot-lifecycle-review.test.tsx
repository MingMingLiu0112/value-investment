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

it("does not translate a true OPEN trigger with insufficient full structure into an absent price trigger", () => {
  // TEST_ONLY producer contract mirroring the observed Oct23 OPEN/ACTIVE_ONLY combination.
  const review = lifecycleFixture();
  review.decision_explanation.decision_path.push(
    {
      check: "CURRENT_OPEN",
      outcome: "OBSERVED",
      values: { observed: true, price: "137.20" },
      evidence_bindings: [review.current_case_binding],
    },
    {
      check: "STRUCTURE_QUALITY",
      outcome: "UNKNOWN",
      values: { observation_quality: "UNKNOWN" },
      evidence_bindings: [review.current_case_binding],
    },
    {
      check: "OPPORTUNITY_QUALITY",
      outcome: "ACTIVE_ONLY",
      values: { structure_tier: "ACTIVE_ONLY" },
      evidence_bindings: [review.current_case_binding],
    },
  );
  const before = structuredClone(review);
  const html = render(review);
  expect(html).toContain("完整开仓结构尚未通过，不能据此认定价格触发未成立");
  expect(html).toContain("当前开仓结构条件</strong>：已观察到条件");
  expect(html).toContain("价格行为质量</strong>：未知");
  expect(html).toContain("多周期机会分级</strong>：仅活跃观察");
  expect(html).toContain("本次观察：<strong>继续观察</strong>");
  expect(html).not.toContain("当前开仓结构尚不满足观察条件");
  expect(review).toEqual(before);
});

it("explains positive input-time checks without upgrading historical PIT or OOS assurance", () => {
  const review = lifecycleFixture();
  review.current_pit = true;
  review.decision_explanation.decision_path[0].values.current_pit = true;
  const before = structuredClone(review),
    html = render(review);
  expect(html).toContain("本次输入时点检查");
  expect(html).toContain("仅指输入不晚于本次评估");
  expect(html).toContain("历史 PIT／样本外仍须另行审查");
  expect(html).not.toContain("当前 PIT 标志");
  expect(review).toEqual(before);
  expect(review.formal_eligibility).toBe(false);
  expect(review.trade_eligible).toBe(false);
});

it.each([
  [
    "ENTRY_TRIGGER_NOT_OBSERVED",
    false,
    "RESEARCH_ONLY",
    "ACTIVE_ONLY",
    "本次单周期开仓价格触发尚未观察到",
  ],
  [
    "ENTRY_BEHAVIOR_QUALITY_NOT_USABLE",
    true,
    "UNKNOWN",
    "ACTIVE_ONLY",
    "价格行为质量尚不足以支持完整开仓结构观察",
  ],
  [
    "ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED",
    true,
    "RESEARCH_ONLY",
    "ACTIVE_ONLY",
    "完整多周期结构分级尚未达标",
  ],
] as const)(
  "translates producer reason %s without changing the observed OPEN state",
  (basis, open, quality, tier, phrase) => {
    const review = lifecycleFixture();
    review.decision_explanation.basis_code = basis;
    review.decision_explanation.why_not_add = [
      basis,
      "OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW",
    ];
    review.decision_explanation.decision_path.push(
      {
        check: "CURRENT_OPEN",
        outcome: open ? "OBSERVED" : "NOT_OBSERVED",
        values: { observed: open, price: "137.20" },
        evidence_bindings: [review.current_case_binding],
      },
      {
        check: "STRUCTURE_QUALITY",
        outcome: quality,
        values: { observation_quality: quality },
        evidence_bindings: [review.current_case_binding],
      },
      {
        check: "OPPORTUNITY_QUALITY",
        outcome: tier,
        values: { structure_tier: tier },
        evidence_bindings: [review.current_case_binding],
      },
    );
    const before = structuredClone(review),
      plan = lifecyclePlan(),
      originalPlan = structuredClone(plan),
      html = render(review, plan);
    expect(html).toContain(phrase);
    expect(html).toContain(
      "缺少原入场依据，当前仅作结构观察，不能推断持有或加仓",
    );
    expect(html).toContain(
      `当前开仓结构条件</strong>：${open ? "已观察到条件" : "本次未观察到条件"}`,
    );
    expect(html).toContain("本次观察：<strong>继续观察</strong>");
    expect(html).not.toContain(basis);
    expect(review).toEqual(before);
    expect(plan).toEqual(originalPlan);
  },
);

it("keeps quality and multi-period why-not-add reasons neutral when the trigger itself was not observed", () => {
  const review = lifecycleFixture();
  review.decision_explanation.basis_code = "ENTRY_TRIGGER_NOT_OBSERVED";
  review.decision_explanation.why_not_add = [
    "ENTRY_TRIGGER_NOT_OBSERVED",
    "ENTRY_BEHAVIOR_QUALITY_NOT_USABLE",
    "ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED",
    "OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW",
  ];
  const html = render(review);
  expect(html).toContain("本次单周期开仓价格触发尚未观察到");
  expect(html).toContain("价格行为质量尚不足以支持完整开仓结构观察");
  expect(html).not.toContain("开仓触发已观察到，但");
});

it("does not turn a false input-time flag into a positive assurance", () => {
  const review = lifecycleFixture(),
    before = structuredClone(review),
    html = render(review);
  expect(html).toMatch(/本次输入时点检查<\/dt><dd[^>]*>否/);
  expect(html).not.toContain("仅指输入不晚于本次评估");
  expect(html).toContain("历史");
  expect(html).toContain("样本外、策略或交易准入");
  expect(review).toEqual(before);
});

it("does not add a new behavior-quality gate to a producer-supplied ENTRY_OBSERVATION", () => {
  const review = lifecycleFixture();
  review.observed_review = "ENTRY_OBSERVATION";
  review.decision_explanation.selected_review = "ENTRY_OBSERVATION";
  review.decision_explanation.basis_code = "ENTRY_STRUCTURE_OBSERVED";
  review.decision_explanation.decision_path.push(
    {
      check: "CURRENT_OPEN",
      outcome: "OBSERVED",
      values: { observed: true },
      evidence_bindings: [review.current_case_binding],
    },
    {
      check: "STRUCTURE_QUALITY",
      outcome: "UNKNOWN",
      values: {},
      evidence_bindings: [review.current_case_binding],
    },
    {
      check: "OPPORTUNITY_QUALITY",
      outcome: "STRUCTURE_QUALIFIED_OBSERVATION",
      values: {},
      evidence_bindings: [review.current_case_binding],
    },
  );
  const before = structuredClone(review),
    html = render(review);
  expect(html).toContain("本次观察：<strong>开仓结构观察</strong>");
  expect(html).not.toContain("状态互相矛盾");
  expect(review).toEqual(before);
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
  review.price_comparability = { status: "UNKNOWN" };
  review.decision_explanation.decision_path.find(
    (step) => step.check === "PRICE_COMPARABILITY",
  )!.outcome = "UNKNOWN";
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
    review.status = "NOT_ASSESSABLE";
    review.observed_review = "UNKNOWN";
    review.decision_explanation.selected_review = "UNKNOWN";
    review.price_comparability = { status };
    review.decision_explanation.basis_code = `PRICE_BASIS_${status}`;
    review.decision_explanation.decision_path.find(
      (step) => step.check === "PRICE_COMPARABILITY",
    )!.outcome = status;
    const html = render(review);
    expect(html).toContain(
      status === "UNKNOWN" ? "公司行动覆盖未核验" : "不复权价格不能直接比较",
    );
  },
);

it("shows stale unknown assessment rather than filling prices or treating unevaluated as false", () => {
  const review = lifecycleFixture();
  review.current_data_status = "STALE";
  review.status = "NOT_ASSESSABLE";
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

it("rejects stale parent with a current child but retains only clearly historical explanation", () => {
  const plan = lifecyclePlan();
  plan.signal_state = "STALE";
  const html = render(lifecycleHeldFixture(), plan);
  expect(html).toContain("状态互相矛盾，暂不可评价");
  expect(html).toContain("原报告历史说明（不作为当前动作）");
  expect(html).toContain("11.00");
  expect(html).toContain("2026-10-20T11:30:00+08:00");
  expect(html).not.toContain("本次观察：");
  expect(html).not.toContain("价格观察（元）：12.3400");
});

it.each([
  "HOLD_STRUCTURE_OBSERVATION",
  "ADD_STRUCTURE_REVIEW",
  "REDUCE_STRUCTURE_REVIEW",
  "EXIT_STRUCTURE_REVIEW",
])(
  "rejects %s without reference entry, confirmed comparability or a completed assessment",
  (selected) => {
    for (const change of [
      (r: Review) => {
        r.entry_case_binding = null;
        r.entry_at = null;
      },
      (r: Review) => {
        r.entry_at = null;
      },
      (r: Review) => {
        r.price_comparability = { status: "UNKNOWN" };
      },
      (r: Review) => {
        r.price_comparability = { status: "INCOMPARABLE" };
      },
      (r: Review) => {
        r.status = "NOT_ASSESSABLE";
      },
      (r: Review) => {
        r.current_data_status = "STALE";
      },
      (r: Review) => {
        r.decision_explanation.decision_path.find(
          (s) => s.check === "ENTRY_REFERENCE",
        )!.outcome = "UNVERIFIED";
      },
      (r: Review) => {
        r.decision_explanation.decision_path.find(
          (s) => s.check === "PRICE_COMPARABILITY",
        )!.outcome = "NOT_EVALUATED";
      },
    ]) {
      const review = lifecycleHeldFixture();
      review.observed_review = selected;
      review.decision_explanation.selected_review = selected;
      change(review);
      const html = render(review);
      expect(html).toContain("状态互相矛盾，暂不可评价");
      expect(html).not.toContain("本次观察：");
    }
  },
);

it.each([
  "HOLD_STRUCTURE_OBSERVATION",
  "ADD_STRUCTURE_REVIEW",
  "REDUCE_STRUCTURE_REVIEW",
  "EXIT_STRUCTURE_REVIEW",
])("does not display public no-entry observations as %s", (selected) => {
  const review = lifecycleFixture();
  review.observed_review = selected;
  review.decision_explanation.selected_review = selected;
  expect(render(review)).toContain("状态互相矛盾，暂不可评价");
});

it.each([
  "HOLD_STRUCTURE_OBSERVATION",
  "ADD_STRUCTURE_REVIEW",
  "REDUCE_STRUCTURE_REVIEW",
  "EXIT_STRUCTURE_REVIEW",
])(
  "accepts consistent reference-only %s without claiming owned holdings",
  (selected) => {
    const review = lifecycleHeldFixture();
    review.observed_review = selected;
    review.decision_explanation.selected_review = selected;
    if (selected !== "EXIT_STRUCTURE_REVIEW") {
      review.original_entry_comparison!.first_breach_at = null;
      review.original_entry_comparison!.first_breach_close = null;
      review.original_entry_comparison!.breach_count = 0;
    }
    review.decision_explanation.decision_path.find(
      (s) => s.check === "ORIGINAL_PROTECTION",
    )!.outcome =
      selected === "EXIT_STRUCTURE_REVIEW" ? "BREACHED" : "NO_OBSERVED_BREACH";
    if (selected === "ADD_STRUCTURE_REVIEW")
      review.decision_explanation.decision_path.find(
        (s) => s.check === "CURRENT_ADD",
      )!.outcome = "OBSERVED";
    if (selected === "REDUCE_STRUCTURE_REVIEW")
      review.decision_explanation.decision_path.find(
        (s) => s.check === "CURRENT_REDUCE",
      )!.outcome = "OBSERVED";
    const html = render(review);
    expect(html).toContain("本次观察：");
    expect(html).toContain("不授予个人加仓或交易权限");
    expect(html).toContain("不等于真实持仓");
  },
);

it("does not require no-entry candidates to have a confirmed price-comparability review", () => {
  const review = lifecycleFixture();
  expect(review.price_comparability).toBeNull();
  expect(render(review)).toContain("未提供原入场，仅当前结构观察");
  expect(render(review)).not.toContain("状态互相矛盾");
});

it("requires assessed action conditions, but preserves an exit breach despite incomplete subsequent coverage", () => {
  const review = lifecycleHeldFixture();
  review.original_entry_comparison!.coverage = "INCOMPLETE";
  review.decision_explanation.decision_path.find(
    (s) => s.check === "CONTINUITY_COVERAGE",
  )!.outcome = "INCOMPLETE";
  expect(render(review)).toContain("本次观察：<strong>退出结构复核</strong>");
  review.observed_review = "ADD_STRUCTURE_REVIEW";
  review.decision_explanation.selected_review = "ADD_STRUCTURE_REVIEW";
  expect(render(review)).toContain("状态互相矛盾");
  review.original_entry_comparison!.coverage = "COMPLETE";
  review.decision_explanation.decision_path.find(
    (s) => s.check === "CONTINUITY_COVERAGE",
  )!.outcome = "COMPLETE";
  review.decision_explanation.decision_path.find(
    (s) => s.check === "CURRENT_ADD",
  )!.outcome = "NOT_EVALUATED";
  expect(render(review)).toContain("状态互相矛盾");
});
