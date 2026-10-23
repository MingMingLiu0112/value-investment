import React from "react";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it, vi } from "vitest";
import {
  ActionableDecisionResult,
  type ConditionalAccountDecision,
} from "../src/components/ActionableDecisionResult";
import { lifecycleHeldFixture } from "./fixtures/hotspot-lifecycle";
import type { OwnedHotspotLifecycle } from "../src/components/OwnedHotspotEntryReview";
const { renderToStaticMarkup } = require("react-dom/server");

/** SIMULATED / TEST_ONLY: no authenticated account, actual fill or ownership claim. */
function fixture(): ConditionalAccountDecision {
  const ref = lifecycleHeldFixture();
  return {
    action: "no_order",
    decision_action: "UNASSESSABLE",
    symbol: "600519",
    strategy: "HOTSPOT_SATELLITE",
    decision_reason: "TEST_ONLY execution continuity unknown",
    blockers: ["OWNED_HOTSPOT_EXECUTION_CONTINUITY_UNPROVEN"],
    review_quantity: null,
    broker_execution_permission: false,
    ownership_verified: true,
    held_quantity: "200",
    entry_thesis_record_sha256: "c".repeat(64),
    original_thesis: "TEST_ONLY 原始投资论据",
    data_trade_date: "2026-10-22",
    owned_hotspot_lifecycle: {
      status: "NOT_ASSESSABLE",
      ownership_verified: true,
      ownership_scope: "INHERITED_AUTHENTICATED_JOURNAL_CONTEXT",
      pretrade_proven: false,
      personal_add_permission: false,
      formal_eligibility: false,
      position_guidance: null,
      action: "no_order",
      blockers: ["EXACT_EXECUTION_TIME_NOT_PROVEN"],
      items: [
        {
          status: "NOT_ASSESSABLE",
          source_reference_status: "SOURCE_REPLAYED",
          pretrade_proven: false,
          personal_add_permission: false,
          formal_eligibility: false,
          action: "no_order",
          blockers: ["EXACT_EXECUTION_TIME_NOT_PROVEN"],
          fill_record_sha256: "d".repeat(64),
          entry_id: "TEST_ONLY_ENTRY",
          entry_artifact_id: "TEST_ONLY_ENTRY_ARTIFACT",
          original_case_binding: ref.entry_case_binding!,
          original_evaluated_at: ref.entry_at!,
          snapshot_recorded_at: "2026-10-19T16:10:00+08:00",
          trade_date: "2026-10-19",
          execution_at: null,
          scope: "ORIGINAL_RESEARCH_REFERENCE_NOT_EXECUTION_CONTINUITY",
          research_reference: ref,
        },
      ],
    },
  };
}
const render = (decision = fixture()) =>
  renderToStaticMarkup(<ActionableDecisionResult decision={decision} />);

it("shows only source-replayed research references, dates, original protection and unresolved execution gaps", () => {
  const value = fixture(),
    before = structuredClone(value),
    html = render(value);
  for (const label of [
    "原始波段入场依据核验",
    "原始买入逻辑：TEST_ONLY 原始投资论据",
    "TEST_ONLY_ENTRY",
    "来源可重放，非成交连续性证明",
    "原始结构评估时点",
    "2026-10-19T16:00:00+08:00",
    "当期行情日期",
    "2026-10-22",
    "原始参考保护位",
    "11.00",
    "首次收盘破位时点",
    "2026-10-20T11:30:00+08:00",
    "原始／当期来源",
    "runtime/TEST_ONLY/entry-case.json",
    "runtime/TEST_ONLY/current-case.json",
    "交易前已知信息和精确成交时点尚未证明",
    "不能单独支持继续持有或加仓数量",
    "个人加仓许可：未授予",
  ])
    expect(html).toContain(label);
  expect(html).toContain("未给出个人可操作股数");
  expect(html).not.toContain("当前条件下复核数量");
  expect(html).not.toContain("<button");
  expect(html).not.toContain("<input");
  expect(value).toEqual(before);
});

it("does not render or fetch private material without its optional authorized decision attachment", () => {
  const value = fixture();
  delete value.owned_hotspot_lifecycle;
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  try {
    expect(render(value)).not.toContain("原始波段入场依据核验");
    expect(fetcher).not.toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

it.each(["UNVERIFIED", "REFERENCE_ONLY"] as const)(
  "does not turn %s into a completed entry review",
  (status) => {
    const value = fixture();
    value.owned_hotspot_lifecycle!.items[0].source_reference_status = status;
    const html = render(value);
    expect(html).toContain("原入场来源未核验、仅参考或版本不一致");
    expect(html).not.toContain("TEST_ONLY_ENTRY_ARTIFACT");
    expect(html).not.toContain("2026-10-19T16:00:00+08:00");
    expect(html).not.toContain("来源可重放，非成交连续性证明");
  },
);

it.each([
  (m: OwnedHotspotLifecycle) => {
    m.pretrade_proven = true as false;
  },
  (m: OwnedHotspotLifecycle) => {
    m.personal_add_permission = true as false;
  },
  (m: OwnedHotspotLifecycle) => {
    m.formal_eligibility = true as false;
  },
  (m: OwnedHotspotLifecycle) => {
    m.action = "order" as any;
  },
  (m: OwnedHotspotLifecycle) => {
    m.position_guidance = { percent: 20 } as any;
  },
  (m: OwnedHotspotLifecycle) => {
    m.items = [null] as any;
  },
])(
  "rejects corrupted or authority-changing attachment %# without mutating the parent action",
  (change) => {
    const value = fixture();
    change(value.owned_hotspot_lifecycle!);
    const html = render(value);
    expect(html).toContain("材料缺失、损坏或与当前只读合同不一致");
    expect(html).toContain("无法评价");
    expect(html).not.toContain("TEST_ONLY_ENTRY_ARTIFACT");
    expect(value.decision_action).toBe("UNASSESSABLE");
  },
);

it.each([
  (m: OwnedHotspotLifecycle) => {
    m.items[0].research_reference!.symbol = "600887";
  },
  (m: OwnedHotspotLifecycle) => {
    m.items[0].original_case_binding = {
      path: "runtime/TEST_ONLY/other.json",
      sha256: "a".repeat(64),
    };
  },
  (m: OwnedHotspotLifecycle) => {
    m.items[0].research_reference!.trade_eligible = true as false;
  },
  (m: OwnedHotspotLifecycle) => {
    m.items[0].original_evaluated_at = "wrong-time";
  },
  (m: OwnedHotspotLifecycle) => {
    m.items[0].research_reference!.current_case_binding.sha256 = "invalid";
  },
  (m: OwnedHotspotLifecycle) => {
    m.items[0].research_reference = null;
  },
])(
  "degrades mismatched reference %# without showing source identities",
  (change) => {
    const value = fixture();
    change(value.owned_hotspot_lifecycle!);
    expect(render(value)).toContain("原件与日期暂不可采信");
    expect(render(value)).not.toContain("TEST_ONLY_ENTRY_ARTIFACT");
  },
);

it("does not let inherited ownership manufacture authentication or source verification", () => {
  const value = fixture();
  value.ownership_verified = false;
  expect(render(value)).toContain("持仓归属来源尚未核验");
  expect(render(value)).not.toContain("TEST_ONLY_ENTRY_ARTIFACT");
  value.strategy = "CORE_VALUE";
  expect(render(value)).not.toContain("原始波段入场依据核验");
});

it("never renders internal confirmed-fill records or raw diagnostics", () => {
  const value = fixture();
  const material = value.owned_hotspot_lifecycle! as any;
  material.confirmed_fill_records = [
    { secret: "TEST_ONLY_RAW_FILL_DO_NOT_DISPLAY" },
  ];
  material.items[0].confirmed_fill_records = material.confirmed_fill_records;
  material.items[0].research_reference.confirmed_fill_records =
    material.confirmed_fill_records;
  material.blockers.push("OSError: C:/private-account/raw-secret-record.json");
  const html = render(value);
  expect(html).not.toContain("confirmed_fill_records");
  expect(html).not.toContain("TEST_ONLY_RAW_FILL_DO_NOT_DISPLAY");
  expect(html).not.toContain("raw-secret-record.json");
  expect(html).toContain("未确认缺口");
});

it("preserves a separately validated thesis-breaker exit without claiming price continuity passed", () => {
  const value = fixture();
  value.decision_action = "EXIT";
  value.consistency_status = "BROKEN";
  value.advisory = { review_basis: "VERIFIED_THESIS_BREAKER" };
  value.decision_reason = "TEST_ONLY separately verified thesis breaker";
  value.blockers = [];
  value.review_quantity = 100;
  value.sellable_quantity = "100";
  const html = render(value);
  expect(html).toContain("条件性退出复核");
  expect(html).toContain("当前条件下复核数量：100");
  expect(html).toContain("退出复核来自服务端原始 Thesis 破坏判断");
  expect(html).toContain("不是本材料证明了价格连续性");
  expect(value.owned_hotspot_lifecycle!.pretrade_proven).toBe(false);
});

it("does not infer a verified thesis-breaker cause merely from BROKEN consistency", () => {
  const value = fixture();
  value.decision_action = "EXIT";
  value.consistency_status = "BROKEN";
  value.blockers = [];
  value.review_quantity = 100;
  value.sellable_quantity = "100";
  const html = render(value);
  expect(html).toContain("条件性退出复核");
  expect(html).not.toContain("退出复核来自服务端原始 Thesis 破坏判断");
});

it("keeps unknown comparability and incomplete coverage as research gaps, not holding or add authority", () => {
  const value = fixture();
  const ref = value.owned_hotspot_lifecycle!.items[0].research_reference!;
  ref.status = "NOT_ASSESSABLE";
  ref.price_comparability = { status: "UNKNOWN" };
  ref.original_entry_comparison!.coverage = "INCOMPLETE";
  ref.blockers = [
    "PRICE_BASIS_UNKNOWN",
    "ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE",
  ];
  const html = render(value);
  expect(html).toContain("未知，不能假定原价可比");
  expect(html).toContain("原参考至当前的完整行情存在缺口");
  expect(html).toContain("个人加仓许可：未授予");
  expect(html).toContain("未给出个人可操作股数");
});

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "wraps owned entry references and unknowns at 320/390 without private API access",
  async () => {
    const output = resolve("../.tmp/owned-hotspot-entry-layout");
    mkdirSync(output, { recursive: true });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const context = await chromium.launchPersistentContext(
      resolve(output, "browser-profile"),
      {
        executablePath: process.env.READINESS_BROWSER_PATH,
        headless: true,
        downloadsPath: output,
      },
    );
    try {
      const page = await context.newPage(),
        rows = [];
      await page.route("**/*", (route: any) => route.abort());
      for (const width of [390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        await page.setContent(
          `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font-family:Arial,sans-serif;font-size:14px;line-height:1.6}main{padding:16px;box-sizing:border-box;width:100%}</style><main>${render()}</main></html>`,
        );
        await page
          .locator("details")
          .evaluateAll((elements: HTMLDetailsElement[]) =>
            elements.forEach((element) => {
              element.open = true;
            }),
          );
        expect(await page.locator("main").innerText()).toContain(
          "个人加仓许可：未授予",
        );
        const size = await page.evaluate(() => ({
          width: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(size.scrollWidth).toBeLessThanOrEqual(width);
        rows.push(size);
        await page.screenshot({
          path: resolve(output, `owned-reference-${width}.png`),
          fullPage: true,
        });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(rows, null, 2),
      );
    } finally {
      await context.close();
    }
  },
  90000,
);
