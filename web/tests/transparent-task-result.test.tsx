import React from "react";
import { expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import type { ValueWorkbenchTask } from "../src/services/api";
vi.mock("../src/components/MainValuationRevalidationPanel", () => ({
  MainValuationRevalidationPanel: ({ value, symbol }: any) => (
    <p>
      TEST_ONLY_MAIN:{symbol}:{value.marker}
    </p>
  ),
}));
import {
  TransparentTaskResult,
  taskFailure,
} from "../src/components/TransparentTaskControls";
import { ApiError } from "../src/services/api";
const { renderToStaticMarkup } = require("react-dom/server");
function task(
  operation: string,
  result: Record<string, unknown>,
): ValueWorkbenchTask {
  return {
    task_id: "rt-" + "a".repeat(32),
    symbol: "000568",
    operation,
    status: "SUCCESS",
    action: "no_order",
    formal_eligibility: false,
    new_llm_calls: 0,
    current_validation: "VERIFIED",
    currently_consumable: true,
    native_metadata: {
      schema_version: "transparent-task-v1",
      execution: "NATIVE_ORIGIN_SERVICE",
      new_llm_calls: 0,
      approval_changed: false,
    },
    result: {
      operation,
      outcome: "SUCCESS",
      result,
      action: "no_order",
      formal_eligibility: false,
      approval_changed: false,
      current_published: false,
      new_llm_calls: 0,
    },
  };
}
it("renders simulation model values, exact RI/DDM difference, changes, reason and ledger with missing baseline explicit", () => {
  const value = task("SIMULATE_ASSUMPTIONS", {
    scope: "SOURCE_BOUND_USER_ASSUMPTION_SIMULATION_NOT_ADOPTED",
    action: "no_order",
    formal_eligibility: false,
    main_range_adopted: false,
    changes: [{ field: "annual.2.target_payout_ratio", value: "0.10" }],
    rationale: "TEST_ONLY_EXPLICIT_RATIONALE",
    calculation: {
      per_share_value: "1234.56789",
      conditional_equity_value_cny: "3000000",
      dividend_crosscheck_equity_value_cny: "3000000",
      dividend_crosscheck_difference_cny: "1E-38",
    },
    ledger: {
      rows: [
        {
          year: 2,
          period_start: "TEST_ONLY_START",
          period_end: "TEST_ONLY_END",
          profit: "100",
          accessible_profit: "90",
          mandatory_cash: "20",
          distribution: "50",
          closing_cash: "120",
          closing_book: "200",
        },
      ],
    },
  });
  const html = renderToStaticMarkup(<TransparentTaskResult task={value} />);
  for (const text of [
    "1,234.57",
    "3,000,000.00",
    "1E-38",
    "同版本基线",
    "未提供",
    "条件分配比例",
    "0.10",
    "第2模型年",
    "TEST_ONLY_EXPLICIT_RATIONALE",
    "TEST_ONLY_START",
    "50.00",
    "本次独立条件模拟",
    "未采用",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("<pre");
  expect(html).not.toContain("已采用主区间");
});
it("delegates the actual independent main payload to the existing verified valuation presenter", () => {
  const html = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("RECALCULATE_MAIN", {
        symbol: "000568",
        marker: "TEST_ONLY_INDEPENDENT",
      })}
    />,
  );
  expect(html).toContain("TEST_ONLY_MAIN:000568:TEST_ONLY_INDEPENDENT");
});
it("shows actual run_once coverage, channel counts and dates without claiming whole-A or current publication", () => {
  const html = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("FRESH_PUBLIC_SCAN", {
        generated_at: "TEST_ONLY_GENERATED",
        as_of: "TEST_ONLY_ASOF",
        quote_date: "TEST_ONLY_QUOTE",
        quote_date_verification: "UNVERIFIED_PROVIDER_TRADE_DATE",
        data_health: {
          universe_count: 5224,
          matched_quote_count: 5200,
          missing_quote_count: 24,
          price_conflict_count: 2,
        },
        channel_counts: { quality: 0, value: 20 },
        screening_scope: {
          covered_venues: ["SSE", "SZSE"],
          failed_venues: ["BSE"],
          all_a_complete: false,
        },
      })}
    />,
  );
  for (const text of [
    "5224",
    "5200",
    "24",
    "TEST_ONLY_GENERATED",
    "TEST_ONLY_ASOF",
    "TEST_ONLY_QUOTE",
    "质量初筛",
    "20",
    "BSE",
    "未证明全A覆盖完整",
    "任务响应尚未提供已核验的候选内容",
  ])
    expect(html).toContain(text);
});
it("reads replay selection content and explicitly rejects path-only output as a candidate explanation", () => {
  const body = {
    status: "PARTIAL",
    selection_content: {
      quote_date: "TEST_ONLY_DATE",
      coverage: { universe_count: 3 },
      shortlist: [
        {
          symbol: "TEST_ONLY_SYMBOL",
          name: "TEST_ONLY_COMPANY",
          reasons: ["TEST_ONLY_REASON"],
          blockers: ["TEST_ONLY_GAP"],
        },
      ],
    },
  };
  const html = renderToStaticMarkup(
    <TransparentTaskResult task={task("REPLAY_SELECTION", body)} />,
  );
  for (const text of [
    "TEST_ONLY_COMPANY",
    "TEST_ONLY_REASON",
    "TEST_ONLY_GAP",
    "独立历史筛选重放",
  ])
    expect(html).toContain(text);
  const absent = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("REPLAY_SELECTION", {
        status: "PARTIAL",
        output_manifest: { items: [{ path: "selection.json" }] },
      })}
    />,
  );
  expect(absent).toContain("缺少selection内容");
  expect(absent).not.toContain("候选明细0条");
});
it("shows the actual verification file/hash scope and review opinion/target version as non-G3", () => {
  const hash = "b".repeat(64);
  const verify = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("VERIFY_EVIDENCE", {
        bundle_status: "VERIFIED",
        source_bindings: [
          { path: "TEST_ONLY_FILE_ONE", sha256: hash },
          { path: "TEST_ONLY_FILE_TWO", sha256: hash },
        ],
      })}
    />,
  );
  expect(verify).toContain("文件数：2");
  expect(verify).toContain(hash);
  expect(verify).toContain("不证明完整财报");
  const review = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("REVIEW_NOTE", {
        symbol: "000568",
        scope: "COMMENT_NOT_G3_APPROVAL",
        action: "no_order",
        formal_eligibility: false,
        approval_changed: false,
        signed: false,
        opinion: "TEST_ONLY_NOTE",
        recorded_at: "TEST_ONLY_RECORDED",
        target_binding: { path: "TEST_ONLY_TARGET", sha256: hash },
      })}
    />,
  );
  for (const text of ["TEST_ONLY_NOTE", "TEST_ONLY_RECORDED", hash, "非G3批准"])
    expect(review).toContain(text);
});
it.each([
  { current_validation: "UNASSESSABLE" },
  { currently_consumable: false },
])(
  "hides private output unless current source validation is consumable: %j",
  (change) => {
    const value = {
      ...task("FRESH_PUBLIC_SCAN", { generated_at: "SHOULD_NOT_RENDER" }),
      ...change,
    };
    const html = renderToStaticMarkup(<TransparentTaskResult task={value} />);
    expect(html).not.toContain("SHOULD_NOT_RENDER");
    expect(html).toContain("不展示旧结果正文");
  },
);
it("rejects operation/authority mismatches even if task status is success and constrains 390px layout locally", () => {
  const value = task("FRESH_PUBLIC_SCAN", {
    generated_at: "SHOULD_NOT_RENDER",
  });
  value.result!.operation = "REVIEW_NOTE";
  expect(
    renderToStaticMarkup(<TransparentTaskResult task={value} />),
  ).not.toContain("SHOULD_NOT_RENDER");
  const css = readFileSync("src/pages/ValueWorkbench/workbench.css", "utf8");
  expect(css).toContain("overflow-wrap: anywhere");
  expect(css).toContain(".task-result-scroll");
  expect(css).toContain("overflow-x: auto");
  expect(css).toContain("margin-inline-start: 0");
});

it("fresh native candidates link to value context without inventing a current buy", () => {
  const html = renderToStaticMarkup(
    <TransparentTaskResult
      task={task("FRESH_PUBLIC_SCAN", {
        shortlist: [
          {
            symbol: "000568",
            company_name: "TEST_ONLY_COMPANY",
            channel: "value",
            reasons: ["TEST_ONLY_REASON"],
          },
        ],
      })}
    />,
  );
  expect(html).toContain("/decisions/000568?strategy=value");
  expect(html).toContain("TEST_ONLY_REASON");
  expect(html).toContain("不是当前入池或买入名单");
});
it("retains the exact native failure reason while unauthorized reads stay generic", () => {
  expect(
    taskFailure(
      new ApiError(422, "UNASSESSABLE", "TASK_CHANGED_DURING_PUBLIC_READ"),
    ),
  ).toContain("TASK_CHANGED_DURING_PUBLIC_READ");
  expect(
    taskFailure(
      new ApiError(401, "AUTHORIZATION_REQUIRED", "TEST_ONLY_PRIVATE_DETAIL"),
    ),
  ).not.toContain("TEST_ONLY_PRIVATE_DETAIL");
});
