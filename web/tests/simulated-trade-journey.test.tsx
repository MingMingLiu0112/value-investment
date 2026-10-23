import React from "react";
import { expect, it, vi } from "vitest";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import {
  SimulatedTradeJourney,
  verifiedSimulatedJourney,
  verifiedSourceBoundJourney,
  sourceBoundCandidatesMatch,
} from "../src/components/SimulatedTradeJourney";
const { renderToStaticMarkup } = require("react-dom/server");

const packet = () => ({
  schema_version: "simulated-trade-journey-v1",
  status: "SIMULATED_JOURNEY_COMPLETE",
  approval_changed: false,
  namespace: "SIMULATED",
  action: "no_order",
  actual_account_used: false,
  strategy_validated: false,
  broker_execution_permission: false,
  steps: [
    "CORE_BUY",
    "HOTSPOT_BUY",
    "CORE_ADD",
    "HOLD",
    "T_PLUS_ONE_REJECTED",
    "CORE_REDUCE",
    "CORE_EXIT",
    "HOTSPOT_EXIT",
  ].map((label) => ({
    label,
    before: { cash_cny: "10000", confirmed_fees_cny: "0" },
    after: { cash_cny: "9995", confirmed_fees_cny: "5" },
  })),
  assumptions: {
    initial_cash_cny: "10000",
    entry_thesis: "TEST_ONLY_SYNTHETIC",
  },
  checks: {
    confirmation_idempotency: true,
    restart_equality: true,
    same_day_sell_rejected: true,
    temporary_journal_removed: true,
  },
});
it("does not run on render or present a scripted account as live", () => {
  const fetcher = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(<SimulatedTradeJourney />);
  expect(html).toContain("SIMULATED");
  expect(html).toContain("不是实盘建议");
  expect(html).toContain("不读取或修改私人账户");
  expect(html).not.toContain("10170");
  expect(html).toContain("真实来源研究与模拟记录");
  expect(html).toContain("运行纯假设计账演练");
  expect(html).not.toContain("运行双策略模拟闭环");
  expect(html).toContain("不会自动记账或成交");
  expect(fetcher).not.toHaveBeenCalled();
  fetcher.mockRestore();
});

function sourcePacket(manual = false): any {
  const cases = ["600519", "600887"].map((symbol, index) => ({
    symbol,
    company_name: `TEST_ONLY 公司${index + 1}`,
    action: "no_order",
    research: {
      candidate_binding: {
        path: `TEST_ONLY/${symbol}/candidate.json`,
        sha256: String(index + 1).repeat(64),
      },
      research_version: `TEST_ONLY_VERSION_${symbol}`,
      model_context: {
        input_descriptor_sha256: "a".repeat(64),
        model_id: "TEST_ONLY_RI",
        model_version: "TEST_ONLY_V1",
      },
      generated_at: "2026-10-23T14:00:00Z",
      replayed_at: null,
      research_as_of: "2026-10-22",
      valuation_date: "2026-10-23",
      available_at: "2026-10-23T14:00:00Z",
      computed_at: "2026-10-24T01:00:00Z",
      thesis: "TEST_ONLY 现金创造逻辑",
      confidence: "低",
      counter_evidence: [{ text: "TEST_ONLY 经营反证" }],
      thesis_breakers: [{ text: "TEST_ONLY 现金逻辑永久受损" }],
      scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL",
    },
    plan: {
      research_version: `TEST_ONLY_VERSION_${symbol}`,
      signal_state: "WAIT",
      candidate_action: "WAIT",
      verification_scope: "TEST_ONLY",
    },
    evaluation: {
      symbol,
      action: "no_order",
      strategy: "CORE_VALUE",
      decision_action: "UNASSESSABLE",
      eligibility: false,
      review_quantity: null,
      position_range: null,
    },
    action_slots: ["BUY", "ADD", "HOLD", "REDUCE", "EXIT", "WAIT"].map(
      (intent) => ({
        intent,
        outcome: intent === "WAIT" ? "WAIT" : "NO_ACTION",
        strategy_verdict: "UNASSESSABLE",
        reasons: [
          "TEST_ONLY 研究及价格条件不足",
          "ORIGINAL_ENTRY_AND_PERSONAL_RISK_NOT_ESTABLISHED",
        ],
        formal_eligibility: false,
        review_quantity: null,
        action: "no_order",
      }),
    ),
  }));
  return {
    schema_version: "source-bound-simulated-trade-journey-v1",
    namespace: "SIMULATED",
    action: "no_order",
    research_namespace: "PUBLIC_SOURCE_BOUND",
    research_evaluated_at: "2026-10-24T02:00:00Z",
    scope: "PUBLIC_RESEARCH_WITH_OPTIONAL_ISOLATED_MANUAL_ACCOUNTING",
    strategy_validated: false,
    approval_changed: false,
    broker_execution_permission: false,
    personal_risk_evaluated: false,
    position_guidance: null,
    source_files_verified: 5,
    cases,
    manual_rehearsal: manual
      ? {
          status: "EXPLICIT_SIMULATED_RECORDS_ONLY",
          actual_account_used: false,
          temporary_journal_removed: true,
          restart_equal: true,
          same_session_sell_rejected: true,
          t1_negative_checks: 1,
          journal_receipt: { sha256: "f".repeat(64), retained: false },
          account_state: { cash_cny: "98995", confirmed_fees_cny: "5" },
          fills: [
            {
              symbol: "600519",
              side: "BUY",
              scope: "EXPLICIT_SIMULATED_MANUAL_FILL_NOT_STRATEGY_ACTION",
              fill: {
                symbol: "600519",
                research_version: cases[0].research.research_version,
                decision_id: "600519",
                sleeve: "CORE_VALUE",
                exchange: "SSE",
                side: "BUY",
                quantity: "100",
                price_cny: "10",
                fees_cny: "5",
                trade_date: "2026-10-23",
              },
              source_candidate_binding: structuredClone(
                cases[0].research.candidate_binding,
              ),
              fill_record_sha256: "b".repeat(64),
              recorded_at: "2026-10-24T02:00:00Z",
              original_entry_advisory_eligible: false,
              execution_price_scope:
                "CALLER_SUPPLIED_HYPOTHETICAL_FILL_NOT_QUOTE_OR_FAIR_VALUE",
              snapshot_status:
                "SNAPSHOT_UNAVAILABLE_NO_EXACT_PUBLISHED_RESEARCH",
              historical_reference_status: "TEST_ONLY_RECORDED",
              historical_reference_scope: "NOT_ORIGINAL_PIT_ENTRY",
              t1_negative_status: "REJECTED_WITHOUT_JOURNAL_WRITE",
              confirmation_idempotent: true,
              prepared_cash_unchanged: true,
            },
          ],
        }
      : {
          status: "NOT_REQUESTED",
          actual_account_used: false,
          temporary_journal_removed: true,
          fills: [],
          account_state: null,
          journal_receipt: null,
        },
  };
}

it("accepts two source-bound WAIT cases and separately explicit manual bookkeeping", () => {
  expect(verifiedSourceBoundJourney(sourcePacket())).toBe(true);
  expect(verifiedSourceBoundJourney(sourcePacket(true))).toBe(true);
  expect(verifiedSourceBoundJourney(packet())).toBe(false);
  const empty = sourcePacket();
  empty.cases = [];
  empty.source_files_verified = 0;
  expect(verifiedSourceBoundJourney(empty)).toBe(true);
});

it("requires the complete previously read candidate set before accepting a manual response", () => {
  const packet = sourcePacket(true);
  const expected = sourcePacket().cases.map((item: any) => ({
    symbol: item.symbol,
    candidate_binding: item.research.candidate_binding,
    research_version: item.research.research_version,
  }));
  expect(sourceBoundCandidatesMatch(packet, expected)).toBe(true);
  expect(sourceBoundCandidatesMatch(packet, undefined)).toBe(false);
  expect(sourceBoundCandidatesMatch(packet, expected.slice(0, 1))).toBe(false);
  const mixed = structuredClone(expected);
  mixed[0].research_version = "ANOTHER_VERSION";
  expect(sourceBoundCandidatesMatch(packet, mixed)).toBe(false);
  mixed[0].research_version = expected[0].research_version;
  mixed[0].candidate_binding.sha256 = "c".repeat(64);
  expect(sourceBoundCandidatesMatch(packet, mixed)).toBe(false);
});

it.skipIf(
  !process.env.SOURCE_BOUND_JOURNEY_JSON ||
    !process.env.SOURCE_BOUND_MANUAL_JSON,
)(
  "validates the user-pinned actual in-process API receipts without any Live request",
  () => {
    const read = readFileSync(process.env.SOURCE_BOUND_JOURNEY_JSON!);
    const manual = readFileSync(process.env.SOURCE_BOUND_MANUAL_JSON!);
    expect(createHash("sha256").update(read).digest("hex")).toBe(
      "4b0c4015ffc84d5b33657d1ab1b57f2cca73445ea2d26e76f60e1a7cc794989f",
    );
    expect(createHash("sha256").update(manual).digest("hex")).toBe(
      "17b5fe0ed2cd05730ff0a72f1014ba0a064b9b068a8289bc87f98fb6ae3a9ced",
    );
    const first = JSON.parse(read.toString("utf8")),
      second = JSON.parse(manual.toString("utf8"));
    expect(verifiedSourceBoundJourney(first)).toBe(true);
    expect(verifiedSourceBoundJourney(second)).toBe(true);
    const expected = first.cases.map((item: any) => ({
      symbol: item.symbol,
      candidate_binding: item.research.candidate_binding,
      research_version: item.research.research_version,
    }));
    expect(sourceBoundCandidatesMatch(second, expected)).toBe(true);
    expect(first.manual_rehearsal.status).toBe("NOT_REQUESTED");
    expect(second.manual_rehearsal.fills).toHaveLength(2);
    expect(
      first.cases.every(
        (item: any) => item.evaluation.decision_action === "UNASSESSABLE",
      ),
    ).toBe(true);
  },
);

it.each([
  (p: any) => {
    p.schema_version = "other";
  },
  (p: any) => {
    p.namespace = "ACTUAL";
  },
  (p: any) => {
    p.action = "order";
  },
  (p: any) => {
    p.strategy_validated = true;
  },
  (p: any) => {
    p.approval_changed = true;
  },
  (p: any) => {
    p.broker_execution_permission = true;
  },
  (p: any) => {
    p.personal_risk_evaluated = true;
  },
  (p: any) => {
    p.position_guidance = "20%";
  },
  (p: any) => {
    p.cases[0].plan.research_version = "MIXED_VERSION";
  },
  (p: any) => {
    p.cases[0].research.candidate_binding.sha256 = "wrong";
  },
  (p: any) => {
    p.cases[0].research.valuation_date = "2026-02-30";
  },
  (p: any) => {
    p.cases[0].symbol = "300033";
  },
  (p: any) => {
    p.cases[1].symbol = p.cases[0].symbol;
  },
  (p: any) => {
    p.cases[0].evaluation.eligibility = true;
  },
  (p: any) => {
    p.cases[0].action_slots[0].outcome = "BUY";
  },
  (p: any) => {
    p.cases[0].action_slots[0].review_quantity = 100;
  },
  (p: any) => {
    p.cases[0].action_slots[0].reasons = [];
  },
  (p: any) => {
    p.manual_rehearsal.actual_account_used = true;
  },
  (p: any) => {
    p.manual_rehearsal.temporary_journal_removed = false;
  },
])("rejects mixed or authority-changing source responses %#", (change) => {
  const p = sourcePacket();
  change(p);
  expect(verifiedSourceBoundJourney(p)).toBe(false);
});

it.each([
  (p: any) => {
    p.manual_rehearsal.restart_equal = false;
  },
  (p: any) => {
    p.manual_rehearsal.same_session_sell_rejected = false;
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].source_candidate_binding.sha256 = "c".repeat(
      64,
    );
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].original_entry_advisory_eligible = true;
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].fill.price_cny = "NaN";
  },
  (p: any) => {
    p.manual_rehearsal.journal_receipt.retained = true;
  },
])(
  "rejects manual accounting authority or attribution conflicts %#",
  (change) => {
    const p = sourcePacket(true);
    change(p);
    expect(verifiedSourceBoundJourney(p)).toBe(false);
  },
);

it.each([
  [
    "same-symbol stale research",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.research_version =
        "TEST_ONLY_OLD_VERSION_600519";
    },
  ],
  [
    "missing research version",
    (p: any) => {
      delete p.manual_rehearsal.fills[0].fill.research_version;
    },
  ],
  [
    "another case research version",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.research_version =
        p.cases[1].research.research_version;
    },
  ],
  [
    "wrong server decision identity",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.decision_id = "600887";
    },
  ],
  [
    "missing server decision identity",
    (p: any) => {
      delete p.manual_rehearsal.fills[0].fill.decision_id;
    },
  ],
  [
    "non-value sleeve",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.sleeve = "HOTSPOT_SATELLITE";
    },
  ],
  [
    "wrong exchange",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.exchange = "SZSE";
    },
  ],
  [
    "inner symbol conflict",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.symbol = "600887";
    },
  ],
  [
    "inner side conflict",
    (p: any) => {
      p.manual_rehearsal.fills[0].fill.side = "SELL";
    },
  ],
  [
    "candidate path conflict",
    (p: any) => {
      p.manual_rehearsal.fills[0].source_candidate_binding.path =
        "TEST_ONLY/other/candidate.json";
    },
  ],
] as const)("refuses mismatched fill/case identity: %s", (_, change) => {
  const response = sourcePacket(true);
  expect(verifiedSourceBoundJourney(response)).toBe(true);
  change(response);
  expect(verifiedSourceBoundJourney(response)).toBe(false);
});

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "exercises only TEST_ONLY mocked GET/POST, consent, loading/error/empty and 320/390 layout",
  async () => {
    const output = resolve("../.tmp/simulated-journey-ui");
    mkdirSync(output, { recursive: true });
    const { build } = require("esbuild") as typeof import("esbuild");
    const bundle = await build({
      stdin: {
        contents: `import React from "react";import{createRoot}from"react-dom/client";import{SimulatedTradeJourney}from"./src/components/SimulatedTradeJourney";createRoot(document.getElementById("root")).render(<SimulatedTradeJourney/>);`,
        loader: "tsx",
        resolveDir: process.cwd(),
      },
      bundle: true,
      write: false,
      platform: "browser",
      format: "iife",
      jsx: "automatic",
      loader: { ".css": "empty" },
      define: { "process.env.NODE_ENV": '"production"' },
    });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const context = await chromium.launchPersistentContext(
      resolve(output, "profile"),
      {
        executablePath: process.env.READINESS_BROWSER_PATH,
        headless: true,
        downloadsPath: output,
      },
    );
    try {
      const page = await context.newPage();
      const errors: string[] = [];
      page.on("pageerror", (error: Error) => errors.push(error.message));
      await page.route("**/*", (route: any) => route.abort());
      await page.setContent(
        '<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{padding:12px;box-sizing:border-box;width:100%}button{max-width:100%;height:auto!important;white-space:normal!important}select{max-width:100%}</style><main id="root"></main></html>',
      );
      await page.evaluate(() => {
        const w = window as any;
        w.calls = [];
        window.fetch = ((url: string, options = {}) => {
          w.calls.push({ url, options });
          return new Promise((resolve) => {
            w.reply = (body: unknown, ok = true) =>
              resolve({ ok, json: async () => body });
          });
        }) as any;
      });
      await page.addScriptTag({ content: bundle.outputFiles[0].text });
      const read = page.getByRole("button", {
        name: "读取真实来源研究（只读）",
        exact: true,
      });
      await read.waitFor();
      expect(await page.evaluate(() => (window as any).calls.length)).toBe(0);
      await read.click();
      await page.getByRole("status").filter({ hasText: "正在核验" }).waitFor();
      expect((await page.evaluate(() => (window as any).calls[0])).url).toBe(
        "/api/v1/simulated-trade-journey?mode=source_bound",
      );
      await page.evaluate(
        (p: unknown) => (window as any).reply(p),
        sourcePacket(),
      );
      await page
        .getByText("未请求模拟记录；本次只读", { exact: false })
        .waitFor();
      await read.click();
      expect(
        await page
          .getByText("TEST_ONLY_VERSION_600519", { exact: false })
          .count(),
      ).toBe(0);
      await page.evaluate(() => (window as any).reply({}, false));
      await page
        .getByRole("alert")
        .filter({ hasText: "旧结果已清空" })
        .waitFor();
      await read.click();
      const empty = sourcePacket();
      empty.cases = [];
      empty.source_files_verified = 0;
      await page.evaluate((p: unknown) => (window as any).reply(p), empty);
      await page
        .getByRole("status")
        .filter({ hasText: "不代表没有机会" })
        .waitFor();
      expect(errors).toEqual([]);
      expect(await read.count(), await page.locator("body").innerText()).toBe(
        1,
      );
      await read.click();
      await page.evaluate(
        (p: unknown) => (window as any).reply(p),
        sourcePacket(),
      );
      await page
        .getByText("未请求模拟记录；本次只读", { exact: false })
        .waitFor();
      await page
        .getByText("显式模拟成交记账（仅价值样本）", { exact: true })
        .click();
      expect(await page.getByLabel("记录1手工假设价（元）").inputValue()).toBe(
        "",
      );
      expect(await page.getByLabel("记录1手工费用（元）").inputValue()).toBe(
        "",
      );
      const submit = page.getByRole("button", {
        name: "提交显式模拟记录",
        exact: true,
      });
      expect(await submit.isDisabled()).toBe(true);
      await page.getByLabel("记录1手工假设价（元）").fill("10");
      await page.getByLabel("记录1手工费用（元）").fill("5");
      await page.getByLabel("记录1假设成交日").fill("2026-10-23");
      await page
        .getByLabel("另行引用历史研究（重建，非原始 PIT Entry）")
        .check();
      await page.getByLabel("仅模拟记账，不是实际成交或策略批准").check();
      await submit.click();
      const call = await page.evaluate(() => (window as any).calls.at(-1));
      const body = JSON.parse(call.options.body);
      expect(call.url).toBe("/api/v1/simulated-trade-journey");
      expect(call.options.method).toBe("POST");
      expect(Object.keys(body).sort()).toEqual([
        "confirmed_hypothetical",
        "expected_candidates",
        "initial_cash_cny",
        "manual_fills",
      ]);
      expect(body.confirmed_hypothetical).toBe(true);
      expect(body.expected_candidates).toEqual(
        sourcePacket().cases.map((item: any) => ({
          symbol: item.symbol,
          candidate_binding: item.research.candidate_binding,
          research_version: item.research.research_version,
        })),
      );
      expect(body.manual_fills[0].research_reference).toBe(
        "HISTORICAL_RECONSTRUCTION",
      );
      expect(Object.keys(body.manual_fills[0].fill).sort()).toEqual(
        [
          "transaction_id",
          "side",
          "sleeve",
          "symbol",
          "exchange",
          "quantity",
          "price_cny",
          "fees_cny",
          "trade_date",
          "trading_unit",
        ].sort(),
      );
      expect(body.manual_fills[0].fill.transaction_id).toMatch(/^SIMULATED-/);
      expect(body.manual_fills[0].fill.sleeve).toBe("CORE_VALUE");
      expect(body.manual_fills[0].fill.price_cny).toBe("10");
      await page.evaluate(
        (p: unknown) => (window as any).reply(p),
        sourcePacket(true),
      );
      await page
        .getByRole("heading", {
          name: "显式模拟记账结果 · 不是系统建议",
          exact: true,
        })
        .waitFor();
      expect(await submit.isDisabled()).toBe(true);
      expect(
        await page.getByText("NO_ACTION · 不形成动作", { exact: true }).count(),
      ).toBe(10);
      expect(
        await page
          .getByText("历史研究重建，不是原始 PIT Entry", { exact: false })
          .count(),
      ).toBeGreaterThan(0);
      await page
        .getByRole("button", { name: "运行纯假设计账演练", exact: true })
        .click();
      const legacy = await page.evaluate(() => (window as any).calls.at(-1));
      expect(legacy.url).toBe("/api/v1/simulated-trade-journey");
      expect(legacy.options.method).toBeUndefined();
      await page.evaluate((p: unknown) => (window as any).reply(p), packet());
      await page.getByText("初始模拟现金", { exact: false }).last().waitFor();
      const measurements: unknown[] = [];
      for (const width of [320, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page
          .locator("details")
          .evaluateAll((items: HTMLDetailsElement[]) =>
            items.forEach((item) => {
              item.open = true;
            }),
          );
        const size = await page.evaluate(() => ({
          width: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(size.scrollWidth).toBeLessThanOrEqual(width);
        measurements.push(size);
        await page.screenshot({
          path: resolve(output, `${width}.png`),
          fullPage: true,
        });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(measurements, null, 2),
      );
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  },
  90000,
);
it("requires all checks and all business steps", () => {
  expect(verifiedSimulatedJourney(packet() as any)).toBe(true);
  expect(verifiedSimulatedJourney({ ...packet(), checks: {} } as any)).toBe(
    false,
  );
  expect(verifiedSimulatedJourney({ ...packet(), steps: [] } as any)).toBe(
    false,
  );
  expect(
    verifiedSimulatedJourney({ ...packet(), actual_account_used: true } as any),
  ).toBe(false);
  expect(
    verifiedSimulatedJourney({ ...packet(), strategy_validated: true } as any),
  ).toBe(false);
});
