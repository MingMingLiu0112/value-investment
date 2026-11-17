import React from "react";
import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import {
  SimulatedHotspotLifecycleReview,
  verifiedSimulatedHotspotLifecycle,
} from "../src/components/SimulatedHotspotLifecycleReview";
const { renderToStaticMarkup } = require("react-dom/server");
const permissions = {
  action: "no_order",
  namespace: "SIMULATED",
  actual_account_used: false,
  actual_owned_entry_created: false,
  formal_eligibility: false,
  broker_execution_permission: false,
  trade_eligible: false,
  position_guidance: null,
  strategy_validation: "NOT_PROVEN",
};
const binding = {
  path: "runtime/TEST_ONLY/receipt.json",
  sha256: "a".repeat(64),
};
const fixture = () => ({
  schema_version: "hotspot-simulated-lifecycle-read-v1",
  ...permissions,
  verified: true,
  status: "VERIFIED_HISTORICAL_SIMULATION",
  verification_scope: "HASH_NATIVE_REPLAY_AND_SIMULATED_ACCOUNTING_ONLY",
  historical_only: true,
  current_signal: false,
  current_pit: false,
  verified_at: "2026-10-24T04:30:00+08:00",
  receipt_binding: binding,
  source_file_count: 8,
  report: {
    schema_version: "hotspot-simulated-lifecycle-v1",
    ...permissions,
    scope: "RETAINED_SOURCE_RETROSPECTIVE_NOT_PIT_OOS_OR_SHADOW",
    symbol: "300750",
    generated_at: "2026-10-24T04:09:36+08:00",
    market_source_scope: "TEST_ONLY",
    simulated_fill_count: 1,
    followup_fill_count: 0,
    entry_freeze_sha256: "b".repeat(64),
    entry_reference: {
      symbol: "300750",
      assumed_entry_at: "2026-10-22T18:00:00+08:00",
      reference_close: "220.410",
      original_protection_price: "218.450",
      entry_origin: "DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED",
      fill_scope:
        "HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL",
    },
    journal_receipt: {
      ...binding,
      namespace: "SIMULATED",
      retained: true,
      record_count: 3,
      confirmation_idempotent: true,
      unchanged_by_followup: true,
      restart_verified: true,
    },
    simulated_accounting: { cash_cny: "9995.000" },
    steps: [
      {
        namespace: "SIMULATED",
        action: "no_order",
        lifecycle_review: {
          symbol: "300750",
          evaluated_at: "2026-10-23T21:00:00+08:00",
          action: "no_order",
          price_comparability: { status: "UNKNOWN" },
          decision_explanation: {
            selected_review: "UNKNOWN",
            decision_path: [
              {
                check: "ORIGINAL_PROTECTION",
                values: {
                  original_protection_price: "218.450",
                  current_rolling_protection_price: "216.510",
                },
              },
            ],
          },
        },
        intentions: Object.fromEntries(
          ["ADD", "REDUCE", "EXIT"].map((intent) => [
            intent,
            {
              status: "REVIEW_ONLY_NO_SIMULATED_FOLLOWUP_FILL",
              observed: intent === "REDUCE",
              blockers: [
                "SIMULATED_ENTRY_IS_NOT_VERIFIED_OWNERSHIP",
                "INDEPENDENT_STRATEGY_ADMISSION_NOT_PROVEN",
              ],
              action: "no_order",
            },
          ]),
        ),
      },
    ],
  },
});

it("explains original protection and raw observations without implying an executable current action", () => {
  const data = fixture(),
    before = structuredClone(data);
  expect(verifiedSimulatedHotspotLifecycle(data)).toBe(true);
  const html = renderToStaticMarkup(
    <SimulatedHotspotLifecycleReview value={data} />,
  );
  for (const text of [
    "合成测试来源",
    "218.450",
    "216.510",
    "无法评估可执行动作",
    "不是策略触发",
    "不是当前候选",
    "后续成交0笔",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("<button");
  expect(data).toEqual(before);
});
it.each([
  "formal_eligibility",
  "actual_account_used",
  "current_signal",
  "current_pit",
])("rejects an authority upgrade of %s", (field) => {
  expect(
    verifiedSimulatedHotspotLifecycle({ ...fixture(), [field]: true }),
  ).toBe(false);
});
it("rejects changed accounting scope, invented future dates and malformed observed fields", () => {
  const amount = fixture();
  amount.report.followup_fill_count = 1;
  expect(verifiedSimulatedHotspotLifecycle(amount)).toBe(false);
  const date = fixture();
  date.report.steps[0].lifecycle_review.evaluated_at =
    "2099-10-23T21:00:00+08:00";
  expect(verifiedSimulatedHotspotLifecycle(date)).toBe(false);
  const field = fixture();
  (field.report.steps[0].intentions.ADD as any).observed = {};
  expect(verifiedSimulatedHotspotLifecycle(field)).toBe(false);
  expect(
    renderToStaticMarkup(
      <SimulatedHotspotLifecycleReview value={{ status: "UNAVAILABLE" }} />,
    ),
  ).toContain("暂不可核验");
});
it.skipIf(!process.env.HOTSPOT_SIMULATED_READ_JSON)(
  "renders the actual reverified retained source/ledger response",
  () => {
    const value = JSON.parse(
      readFileSync(process.env.HOTSPOT_SIMULATED_READ_JSON!, "utf8"),
    );
    expect(verifiedSimulatedHotspotLifecycle(value)).toBe(true);
    const html = renderToStaticMarkup(
      <SimulatedHotspotLifecycleReview value={value} />,
    );
    expect(html).toContain("218.450");
    expect(html).toContain("216.510");
    expect(html).toContain("未独立认证");
  },
);
