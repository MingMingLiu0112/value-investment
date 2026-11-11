import React from "react";
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import type { ParentFundingReview } from "../src/services/api";
import { ParentFundingResearchPanel } from "../src/components/ParentFundingResearchPanel";
const { renderToStaticMarkup } = require("react-dom/server");

function fixture(): ParentFundingReview {
  const source = {
    sha256: "a".repeat(64),
    path: "runtime/TEST_ONLY-original.pdf",
    available_at: "2026-08-29T09:00:00+08:00",
  };
  const fact = (field: string, value: string) => ({
    field,
    value,
    scope: "parent",
    unit: "CNY",
    period_end: "2026-06-30",
    source_id: "TEST_ONLY_SOURCE",
    physical_page: 40,
  });
  return {
    status: "HISTORICAL_PARENT_REVIEW",
    symbol: "000568",
    action: "no_order",
    formal_eligibility: false,
    current_capacity_proven: false,
    review: {
      period: "2026-06-30",
      action: "no_order",
      native_sha256: "b".repeat(64),
      evidence: [
        fact("parent_cash_equivalents", "23517780000.00"),
        fact("parent_dividend_payable", "6501570000.00"),
        fact("parent_retained_profit", "23214184665.64"),
      ],
      sources: { TEST_ONLY_SOURCE: source },
      result: {
        static_after_declared_dividend: "17016210000.00",
        conditional_distribution_ceiling: null,
        conditional_shortfall: null,
        status: "INCOMPLETE_OBLIGATIONS",
        current_capacity_proven: false,
        approved: false,
        action: "no_order",
      },
      debt_review: {
        parent_current_noncurrent_liabilities: "1510049088.62",
        other_payables_ex_dividend: "5809966323.44",
        other_payables_cash_timing: "UNKNOWN",
        principal_interest_split: null,
        consolidated_current_principal: "1508700000.00",
      },
      historical_capex: {
        source,
        physical_page: 44,
        amount: "413,591,845.80",
        excerpt: "TEST_ONLY_CAPEX_ORIGINAL",
      },
      post_h1_bridge: {
        status: "IMPLEMENTATION_ARRANGEMENT",
        fiscal_attribution: "FY2025",
        scheduled_date: "2026-08-28",
        additional_cash_deduction: "0",
        current_parent_cash: null,
        action: "no_order",
      },
      unknowns: ["operating_reserve", "necessary_investment"],
      future_necessary_investment: "UNKNOWN",
      legal_adjustments: "UNKNOWN",
    },
  };
}
function html(value = fixture()) {
  return renderToStaticMarkup(
    <ParentFundingResearchPanel value={value} symbol="000568" />,
  );
}
function visible(raw: string) {
  return raw.split("<details>")[0];
}

it("displays source facts and backend historical static remainder without claiming current distributable cash", () => {
  const value = fixture(),
    before = JSON.stringify(value),
    raw = html(value),
    shown = visible(raw);
  for (const text of [
    "2026-06-30",
    "母公司期末现金及现金等价物",
    "期末现金及现金等价物－已宣派股利：静态余量",
    "235.1778",
    "65.0157",
    "170.1621",
    "母公司未分配利润",
    "非今日可分配现金",
    "绝非今日可分配钱",
    "条件分配上限：未知（保持空）",
    "条件缺口：未知（保持空）",
    "当前可分配能力未证明",
    "不是现金或已核定的法定分配上限",
  ])
    expect(shown).toContain(text);
  expect(raw).toContain("TEST_ONLY_CAPEX_ORIGINAL");
  expect(shown).not.toContain("TEST_ONLY_CAPEX_ORIGINAL");
  expect(raw).toContain("a".repeat(64));
  expect(JSON.stringify(value)).toBe(before);
});
it("keeps principal/interest and cash timing unknown and does not double-deduct capex or dividend implementation", () => {
  const raw = html();
  for (const text of [
    "15.1005",
    "58.0997",
    "本金与利息拆分未知",
    "现金支付时点：未知",
    "合并口径本金、利息与租赁拆分不能归给母公司",
    "历史资本开支已包含在期末现金，不能再扣一次",
    "cash_floor默认为0不等于无需经营准备金",
    "FY2025",
    "2026-08-28",
    "本次新增现金扣减：0元",
    "当前母公司现金：未知（保持空）",
    "实施安排不等于账户到账",
    "不重复扣除",
  ])
    expect(raw).toContain(text);
  expect(visible(raw)).not.toContain("1,508,700,000");
});
it("uses the backend remainder rather than hardcoding the example or recalculating a capacity", () => {
  const value = fixture();
  value.review!.result.static_after_declared_dividend = "12300000000";
  const shown = visible(html(value));
  expect(shown).toContain("123.0000");
  expect(shown).not.toContain("170.1621");
  expect(shown).toContain("未知（保持空）");
  for (const status of [
    "AMOUNT_EQUAL_NOT_MAPPING_VERIFIED",
    "AMOUNT_DIFFERENT",
    "NOT_ASSESSABLE",
  ] as const) {
    value.cash_input_comparison = {
      status,
      source_mapping_verified: false,
      scope: "AMOUNT_COMPARISON_NOT_SOURCE_MAPPING_OR_LEGAL_CAPACITY",
      source_static_remainder_cny: "12300000000",
      model_opening_cash_cny: "12300000000",
      model_financial_basis: "2026-06-30",
      model_scope: "owner_equivalent",
    };
    const comparison = visible(html(value));
    expect(comparison).toContain(status);
    expect(comparison).toContain(
      status === "AMOUNT_EQUAL_NOT_MAPPING_VERIFIED"
        ? "历史静态余额与模型现金输入金额相等；不证明自动派生或来源映射"
        : status === "AMOUNT_DIFFERENT"
          ? "金额不同，须核查"
          : "金额不可评估",
    );
    expect(comparison).toContain(
      "不证明owner-equivalent映射/经营准备金/到期义务或法律分配能力",
    );
    expect(comparison).toContain("条件分配上限：未知（保持空）");
    expect(comparison).not.toContain("来源已核验进入模型");
    expect(comparison).not.toContain("现金输入已证");
    if (status === "AMOUNT_EQUAL_NOT_MAPPING_VERIFIED")
      expect(comparison).toContain("不证明自动派生或来源映射");
  }
});
it.each(["NOT_STARTED", "UNASSESSABLE"] as const)(
  "keeps %s local without erasing sibling public research or inventing zero capacity",
  (status) => {
    const value: ParentFundingReview = {
      status,
      action: "no_order",
      formal_eligibility: false,
      ...(status === "NOT_STARTED"
        ? { current_capacity_proven: false as const }
        : {}),
      reason: "TEST_ONLY_PARENT_REASON",
    };
    const raw = renderToStaticMarkup(
      <>
        <p>TEST_ONLY_EXISTING_D2_AND_CASH</p>
        <ParentFundingResearchPanel value={value} symbol="000568" />
      </>,
    );
    expect(raw).toContain("TEST_ONLY_EXISTING_D2_AND_CASH");
    expect(raw).toContain(
      status === "NOT_STARTED" ? "尚无母公司历史资金研究包" : "原件暂不可核验",
    );
    expect(raw).toContain("TEST_ONLY_PARENT_REASON");
    expect(raw).not.toContain("170.1621");
  },
);
it("stops parent/consolidated scope mixing or unexpected approved capacity at this panel boundary", () => {
  const value = fixture();
  value.review!.evidence[0].scope = "consolidated";
  expect(html(value)).toContain("证据或未知义务边界不完整");
  expect(html(value)).not.toContain("235.1778");
  const unexpected = fixture();
  unexpected.review!.result.conditional_distribution_ceiling = "100";
  expect(html(unexpected)).toContain("不能展示可分配上限");
  const wrong = fixture();
  wrong.symbol = "600519";
  expect(html(wrong)).toContain("身份或边界不符");
});
it("remains pure display and is conditionally embedded without modifying existing Q3 logic or adding requests", () => {
  const component = readFileSync(
    "src/components/ParentFundingResearchPanel.tsx",
    "utf8",
  );
  expect(component).not.toMatch(
    /fetch\(|useEffect|useState|localStorage|api\./,
  );
  const live = readFileSync(
    "src/components/LiveOperatingResearchPanel.tsx",
    "utf8",
  );
  expect(live).toContain('from "./ParentFundingResearchPanel"');
  expect(live).toMatch(
    /task\.parent_funding_review &&[\s\S]*?<ParentFundingResearchPanel/,
  );
});
