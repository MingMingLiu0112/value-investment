import React from "react";
import { describe, expect, it, vi } from "vitest";
import type {
  DecisionItem,
  PacketCompanyStatus,
  StrategyReadiness,
} from "../src/types/api";
import {
  evaluationFixture,
  readinessFixture,
} from "./fixtures/strategy-readiness";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));
import {
  DailyStrategyReadiness,
  StrategyReadinessPanel,
} from "../src/components/StrategyReadiness";
import {
  readinessActionUrl,
  readinessDetailUrl,
  readinessSteps,
  verifiedReadiness,
} from "../src/utils/strategyReadiness";

const planDecision: DecisionItem = {
  id: "600887",
  symbol: "600887",
  strategy: "value",
  price_action_plan: {
    action: "no_order",
    signal_state: "WATCH",
    entry_trigger_price: "25.750",
    invalidation_price: "20.250",
    market_trade_date: "2026-10-21",
    add_condition: { price: "23.000", rule: "另行核验" },
    reduce_condition: { price: "35.500", rule: "仅已核验持仓" },
    exit_condition: { price: "41.250", rule: "仍须人工复核" },
  },
};

describe("explicit readiness contract", () => {
  it("fills omitted steps as NOT_EVALUATED without deriving READY from prose", () => {
    const readiness = readinessFixture();
    readiness.steps = [
      {
        key: "screen",
        label: "候选入选",
        status: "READY",
        reason: "范围已核验",
      },
      {
        key: "valuation",
        label: "情景估值",
        status: "PASS" as any,
        reason: "READY all approved",
      },
    ];
    const steps = readinessSteps(readiness, "CORE_VALUE");
    expect(steps).toHaveLength(8);
    expect(
      steps.filter((step) => step.status === "READY").map((step) => step.key),
    ).toEqual(["screen"]);
    expect(steps.find((step) => step.key === "valuation")?.status).toBe(
      "NOT_EVALUATED",
    );
    const duplicate = {
      ...readiness,
      steps: [...readiness.steps, readiness.steps[0]],
    };
    expect(readinessSteps(duplicate, "CORE_VALUE")[0].status).toBe(
      "NOT_EVALUATED",
    );
  });

  it.each([
    { schema_version: "future" },
    { action: "buy" },
    { authorization_granted: true },
    { authorization_granted: undefined },
    { strategy: "HOTSPOT_SATELLITE" },
    { steps: null },
  ])("rejects incompatible contract %j", (mutation) => {
    const item = evaluationFixture();
    item.readiness = { ...item.readiness, ...mutation } as StrategyReadiness;
    expect(verifiedReadiness(item.readiness, "CORE_VALUE")).toBeNull();
    const html = renderToStaticMarkup(
      <StrategyReadinessPanel item={item} decision={planDecision} />,
    );
    expect(html).toContain("就绪信息无法核验");
    expect(html).not.toContain("25.750");
    expect(html).not.toContain('data-status="READY"');
  });

  it("keeps the legacy surface when all readiness is absent and explains a partially missing response", () => {
    const legacy = { ...evaluationFixture(), readiness: undefined };
    expect(
      renderToStaticMarkup(
        <DailyStrategyReadiness items={[legacy]} decisions={[]} />,
      ),
    ).toBe("");
    const html = renderToStaticMarkup(
      <DailyStrategyReadiness
        items={[legacy, evaluationFixture("HOTSPOT_SATELLITE")]}
        decisions={[]}
      />,
    );
    expect(html).toContain("各阶段未核验");
    expect(html).toContain("无法评价");
    expect(html).not.toContain("已评价，本次不交易");
  });

  it("preserves known conditional numbers and their unapproved scopes", () => {
    const item = evaluationFixture();
    item.readiness!.conditional_valuation = {
      bear: "31.000",
      base: "39.500",
      bull: "44.750",
      currency: "CNY",
      as_of: "2026-09-30",
      scope: "UNAPPROVED_RESEARCH_ONLY",
    };
    item.readiness!.price_snapshot = {
      value: "27.960",
      date: "2026-10-21",
      usage: "DISPLAY_ONLY",
    };
    const html = renderToStaticMarkup(
      <StrategyReadinessPanel item={item} decision={planDecision} />,
    );
    for (const value of [
      "31.00",
      "39.50",
      "44.75",
      "27.96",
      "25.75",
      "23.00",
      "20.25",
      "35.50",
      "41.25",
      "2026-09-30",
      "2026-10-21",
    ])
      expect(html).toContain(value);
    expect(html).toContain("条件估值 · 未获批准");
    expect(html).toContain("参考行情 · 仅供展示");
    expect(html).toContain("条件操作价 · 观察用，未获批准");
    expect(html).toContain("有效期 未提供，需重新核验");
    expect(html).toContain('href="/decisions/600887#value-review-handoff"');
    expect(item.decision_action).toBe("UNASSESSABLE");
    expect(item.eligibility).toBe(false);
  });

  it("does not synthesize prices, dates, valuations or private capacity when absent", () => {
    const html = renderToStaticMarkup(
      <StrategyReadinessPanel item={evaluationFixture()} />,
    );
    expect(html).toContain("尚无可展示的条件估值");
    expect(html).toContain("尚无用途已核验的行情快照");
    expect(html).toContain("尚无可核验的条件操作价");
    expect(html).toContain("个人组合容量");
    expect(html).toContain("未核验");
    expect(html).not.toContain("0.00");
    expect(html).not.toContain("已连接");
  });

  it.each(["NOT_READY", "UNDER_REVIEW"])(
    "explains %s separately from model execution",
    (code) => {
      const html = renderToStaticMarkup(
        <StrategyReadinessPanel
          item={evaluationFixture()}
          company={
            {
              symbol: "600887",
              valuation_status: { code },
            } as PacketCompanyStatus
          }
        />,
      );
      expect(html).toContain(code);
      expect(html).toContain(
        code === "NOT_READY" ? "不代表模型从未运行" : "已有情景也不代表获准",
      );
      expect(html).toContain("不能由缺少估值或审核状态推断");
      expect(html).not.toContain("模型运行：明确未运行");
    },
  );

  it.each([
    ["MODEL_NOT_RUN", "模型尚未运行"],
    ["DISPLAY_ONLY", "行情仅供展示"],
    ["STRATEGY_VALIDATION", "策略验证存在缺口"],
    ["NOT_READY", "前置条件未就绪"],
    ["UNDER_REVIEW", "审核进行中"],
  ])("separates explicit gap category %s", (category, label) => {
    const item = evaluationFixture();
    item.readiness!.primary_gap!.category = category;
    const html = renderToStaticMarkup(<StrategyReadinessPanel item={item} />);
    expect(html).toContain(label);
  });

  it("never grants authorization even when every reported step is READY", () => {
    const item = evaluationFixture();
    item.readiness!.steps = item.readiness!.steps.map((step) => ({
      ...step,
      status: "READY",
    }));
    item.readiness!.primary_gap = null;
    const html = renderToStaticMarkup(<StrategyReadinessPanel item={item} />);
    expect(html).toContain("阶段核验完成，仍未授予操作批准");
    expect(html).toContain("不能认定缺口已经清除");
    expect(html).not.toContain("可以交易");
  });

  it("isolates hotspot steps and prices from the value sleeve of the same security", () => {
    const item = evaluationFixture("HOTSPOT_SATELLITE");
    item.readiness!.conditional_valuation = {
      bear: "31.000",
      base: "39.500",
      bull: "44.750",
      currency: "CNY",
      as_of: "2026-09-30",
      scope: "UNAPPROVED_RESEARCH_ONLY",
    };
    const html = renderToStaticMarkup(
      <StrategyReadinessPanel item={item} decision={planDecision} />,
    );
    expect(html).toContain("价值估值不是前置");
    expect(html).toContain("回放与策略验证");
    expect(html).not.toContain("条件估值");
    expect(html).not.toContain("公司研究形成");
    expect(html).not.toContain("25.750");
    expect(html).not.toContain("31.000");
    expect(html).toContain("independent_hotspot=true");
  });

  it("makes both strategies and securities keyboard accessible via native disclosure controls", () => {
    const html = renderToStaticMarkup(
      <DailyStrategyReadiness
        items={[evaluationFixture(), evaluationFixture("HOTSPOT_SATELLITE")]}
        decisions={[planDecision]}
      />,
    );
    expect(html.match(/<details/g)).toHaveLength(4);
    expect(html.match(/<summary/g)).toHaveLength(4);
    expect(html).toContain("价值投资");
    expect(html).toContain("热点波段");
    expect(html.match(/无法评价/g)).toHaveLength(4);
  });

  it("uses the exact decision id and independent hotspot detail", () => {
    expect(
      readinessDetailUrl(evaluationFixture("HOTSPOT_SATELLITE"), {
        id: "hotspot-600887-v2",
        symbol: "600887",
        strategy: "hotspot",
      }),
    ).toBe("/decisions/hotspot-600887-v2?independent_hotspot=true");
    expect(
      readinessDetailUrl(evaluationFixture("HOTSPOT_SATELLITE"), planDecision),
    ).toBe("/decisions/hotspot-600887?independent_hotspot=true");
  });

  it.each([
    "javascript:alert(1)",
    "//external.test",
    "https://external.test",
    "/\\external.test",
    "/api/v1/private/reset",
    "/unknown",
    "/%2fexternal.test",
    "/decisions/a\nb",
  ])("rejects non-workbench action URL %s", (url) => {
    expect(readinessActionUrl(url)).toBeNull();
  });
});
