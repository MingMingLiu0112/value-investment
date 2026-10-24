import React from "react";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { expect, it, vi } from "vitest";
import {
  EconomicReviewResult,
  SourceNativeEconomicReview,
} from "../src/components/SourceNativeEconomicReview";
import { verifiedEconomicReview } from "../src/services/sourceNativeEconomicReview";
const { renderToStaticMarkup } = require("react-dom/server");

import {
  economicRef as ref,
  economicFixture as fixture,
} from "./fixtures/sourceNativeEconomic";

it("renders separate terminal conventions and conditional historical-share limits", () => {
  const value = fixture();
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(true);
  const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
  for (const text of [
    "历史普通股分母",
    "未来股利终值",
    "RI终端剩余收益",
    "70%",
    "50%",
    "不是长期安全阈值",
    "不是当前目标价",
    "正常化利润未在此确认",
  ])
    expect(html).toContain(text);
});

it("opening the existing company page does not issue implicit new requests", () => {
  const spy = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(
    <SourceNativeEconomicReview symbol="600519" candidate={ref} />,
  );
  expect(html).toContain("读取经济复核");
  expect(spy).not.toHaveBeenCalled();
  spy.mockRestore();
});

function jointCounterexample() {
  return {
    status: "INHERITED_PAYOUT_INFEASIBLE",
    scope: "MECHANICAL_COUNTEREXAMPLE_NOT_FORECAST_OR_ACCOUNTING_FACT",
    action: "no_order",
    disclosed_annual_growth: "-0.04",
    first_cash_failure_year: 1,
    first_retained_profit_failure_year: null,
    terminal_status: "UNSUPPORTED_NO_RELEASE_NO_FULL_PAYOUT_TERMINAL",
    rows: [
      {
        year: 1,
        P: "100",
        M: "90",
        U: "10",
        C: "30",
        B: "200",
        D: "90",
        cash_floor: "40",
        cash_margin: "-10",
        retained_profit: "50",
        status: "UNFUNDED_PLAN",
        D_scope: "PLANNED_NOT_PAID_NO_AUTOMATIC_DIVIDEND_CUT",
        cash_constraint_failed: true,
        retained_constraint_failed: false,
      },
    ],
  };
}

it("shows a computed joint counterexample without turning it into a forecast or paid dividend", () => {
  const value = fixture();
  value.joint_adverse_cash = jointCounterexample();
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(true);
  const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
  for (const text of [
    "联合逆境反例",
    "不是盈利预测",
    "第1年首次",
    "非实际已支付股息",
    "不计算新估值或入场价",
  ])
    expect(html).toContain(text);
});

it.each([
  "number",
  "sequence",
  "paid",
  "terminal",
  "failure",
  "wrongConstraint",
  "cashContradiction",
  "marginMismatch",
  "retainedContradiction",
])("rejects malformed joint diagnostic: %s", (fault) => {
  const value = fixture();
  value.joint_adverse_cash = jointCounterexample();
  const cash = value.joint_adverse_cash;
  if (fault === "number") cash.rows[0].C = "NaN";
  else if (fault === "sequence") cash.rows[0].year = 3;
  else if (fault === "paid") cash.rows[0].D_scope = "PAID";
  else if (fault === "terminal") cash.terminal_status = "VALUED";
  else if (fault === "wrongConstraint")
    cash.first_retained_profit_failure_year = 1;
  else if (fault === "cashContradiction") {
    cash.status = "FIVE_YEAR_CONDITIONAL_PLAN_FEASIBLE";
    cash.first_cash_failure_year = null;
    cash.rows = Array.from({ length: 5 }, (_, i) => ({
      ...cash.rows[0],
      year: i + 1,
      status: "CONDITIONAL_PLAN_FEASIBLE",
      cash_constraint_failed: false,
    }));
  } else if (fault === "marginMismatch")
    cash.rows[0].cash_margin = "-9.99999999999999999999999999999999";
  else if (fault === "retainedContradiction")
    cash.rows[0].retained_profit = "-0.00000000000000000000000000001";
  else cash.first_cash_failure_year = null;
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(false);
});

it.each([
  "symbol",
  "candidate",
  "approval",
  "price",
  "normalization",
  "shares",
  "number",
  "duplicate",
  "group",
  "source",
])("rejects stale or promoted economic response: %s", (fault) => {
  const value = fixture();
  if (fault === "symbol") value.symbol = "600887";
  else if (fault === "candidate")
    value.candidate_binding.sha256 = "f".repeat(64);
  else if (fault === "approval") value.research_admitted = true;
  else if (fault === "price") value.price_admitted = true;
  else if (fault === "normalization")
    value.normalized_parent_profit_cny = "100";
  else if (fault === "shares") value.share_basis.current_shares = "10000";
  else if (fault === "number")
    value.scenarios[0].original.ddm_terminal_fraction = "NaN";
  else if (fault === "duplicate") value.scenarios[2].scenario = "bear";
  else if (fault === "group") value.five_groups[0].approval_status = "APPROVED";
  else value.source_bindings[0].path = "../private/account.json";
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(false);
});

it("unsupported challenges remain explicit instead of displaying a made-up number", () => {
  const value = fixture();
  value.scenarios[1].ke_plus_200bp = {
    status: "UNSUPPORTED",
    delta_basis_points: 200,
    alternative_candidate_verified: false,
  };
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(true);
  expect(
    renderToStaticMarkup(<EconomicReviewResult value={value} />),
  ).toContain("现有内核不支持此挑战");
});

it.skipIf(!process.env.NATIVE_ECONOMIC_REVIEW_JSON)(
  "consumes actual public-source HTTP economic diagnostics",
  () => {
    const file = resolve(process.env.NATIVE_ECONOMIC_REVIEW_JSON!);
    expect(relative(resolve(process.cwd(), "..", ".tmp"), file)).not.toMatch(
      /^(?:\.\.|[A-Za-z]:|[\\/])/,
    );
    const bytes = readFileSync(file);
    const receipt = JSON.parse(
      readFileSync(resolve(dirname(file), "receipt.json"), "utf8"),
    );
    expect(receipt.scope).toBe(
      "ACTUAL_PUBLIC_REFERENCES_LOCAL_TESTCLIENT_NOT_LIVE_8001",
    );
    expect(receipt.status).toBe("PASS");
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      receipt.result_sha256,
    );
    const value = JSON.parse(bytes.toString("utf8"));
    expect(
      verifiedEconomicReview(value, "600519", receipt.candidate_binding),
    ).toBe(true);
    const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
    expect(html).toContain("不能直接形成买入或加仓资格");
    if (
      value.joint_adverse_cash &&
      value.joint_adverse_cash.status !== "UNSUPPORTED"
    ) {
      expect(html).toContain("联合逆境反例");
      expect(html).toContain("非实际已支付股息");
      expect(html).toContain(
        `第${value.joint_adverse_cash.first_cash_failure_year}年首次`,
      );
      expect(value.joint_adverse_cash.first_cash_failure_year).toBe(5);
    }
  },
);
