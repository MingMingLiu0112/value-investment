import React from "react";
import { expect, it, vi } from "vitest";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { SourceBoundDualJourney } from "../src/components/SourceBoundDualJourney";
import {
  dualJourneyUrl,
  dualManualRequest,
  dualSourcesMatch,
  dualTestPolicy,
  verifiedDualJourney,
} from "../src/services/sourceBoundDualJourney";
const { renderToStaticMarkup } = require("react-dom/server");

it.skipIf(!process.env.PUBLIC_DUAL_ACCOUNT_RESULT)(
  "accepts the exact independently bound real-source API result without granting eligibility",
  () => {
    const raw = readFileSync(process.env.PUBLIC_DUAL_ACCOUNT_RESULT!);
    expect(createHash("sha256").update(raw).digest("hex")).toBe(
      process.env.PUBLIC_DUAL_ACCOUNT_RESULT_SHA256,
    );
    const result = JSON.parse(raw.toString("utf8"));
    expect(verifiedDualJourney(result)).toBe(true);
    expect(result.formal_eligibility).toBe(false);
    expect(result.manual_rehearsal.account_state.cash_cny).toBe("7990");
    expect(result.manual_rehearsal.temporary_journal_removed).toBe(true);
    expect(result.source_identity.core[0].symbol).toBe("600519");
    expect(result.source_identity.hotspot.symbol).toBe("300750");
  },
);

/** TEST_ONLY protocol fixtures. No real account, live API, price or strategy claim. */
function packet(manual = false): any {
  const candidate = { path: "TEST_ONLY/core.json", sha256: "a".repeat(64) };
  const receipt = { path: "TEST_ONLY/wave.json", sha256: "b".repeat(64) };
  const slots = () =>
    ["BUY", "ADD", "HOLD", "REDUCE", "EXIT", "WAIT"].map((intent) => ({
      intent,
      outcome: intent === "WAIT" ? "WAIT" : "NO_ACTION",
      reasons: [
        "MODEL_VALIDITY_UNKNOWN",
        `TEST_ONLY_UNKNOWN_${"X".repeat(160)}`,
      ],
      formal_eligibility: false,
      review_quantity: null,
      action: "no_order",
    }));
  const core = {
    symbol: "600519",
    action: "no_order",
    research: {
      candidate_binding: candidate,
      research_version: "TEST_ONLY_CORE",
      research_as_of: "2026-10-24",
      valuation_date: "2026-06-30",
      confidence: "低",
      scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL",
      thesis: "TEST_ONLY value hypothesis",
    },
    plan: { research_version: "TEST_ONLY_CORE" },
    evaluation: {
      symbol: "600519",
      action: "no_order",
      eligibility: false,
      review_quantity: null,
      position_range: null,
      decision_action: "UNASSESSABLE",
    },
    action_slots: slots(),
  };
  const wave = {
    symbol: "300750",
    sleeve: "HOTSPOT_SATELLITE",
    action: "no_order",
    receipt_binding: receipt,
    entry_freeze_sha256: "c".repeat(64),
    historical_only: true,
    current_signal: false,
    current_pit: false,
    strategy_validated: false,
    formal_eligibility: false,
    review_quantity: null,
    source_scope: "TEST_ONLY_HISTORICAL",
    entry_reference: {
      namespace: "SIMULATED",
      symbol: "300750",
      assumed_entry_at: "2026-10-21T07:00:00Z",
      generated_at: "2026-10-22T07:00:00Z",
      entry_case_binding: {
        path: "TEST_ONLY/entry.json",
        sha256: "d".repeat(64),
      },
      entry_origin: "DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED",
      fill_scope:
        "HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL",
    },
    lifecycle_reviews: [
      {
        action: "no_order",
        evaluated_at: "2026-10-22T07:00:00Z",
        formal_eligibility: false,
      },
    ],
    action_slots: slots(),
  };
  const state = (
    cash: string,
    fees: string,
    coreCash: string,
    waveCash: string,
  ): any => ({
    cash_cny: cash,
    confirmed_fees_cny: fees,
    positions: [],
    aggregate_holdings: [],
    hypothetical_equity_cny: null,
    mark_scope: "CALLER_TEST_ONLY_MARKS_NOT_CURRENT_QUOTES_OR_INTRINSIC_VALUE",
    risk_scope: "DISPOSABLE_ACCOUNT_MISSING_RISK_INPUTS_REMAIN_BLOCKED",
    risk_review: {
      namespace: "SIMULATED",
      action: "no_order",
      status: "BLOCKED_PRIVATE_INPUT",
      blockers: ["TEST_ONLY_missing_attributes"],
      position_guidance: null,
      trade_eligible: false,
    },
    sleeve_cash_review: {
      action: "no_order",
      trade_eligible: false,
      status: "RISK_REVIEW_CALCULATED",
      blockers: [],
      sleeves: {
        CORE_VALUE: { cash_cny: coreCash, shortfall_cny: "0" },
        HOTSPOT_SATELLITE: { cash_cny: waveCash, shortfall_cny: "0" },
      },
    },
  });
  const before = state("10000", "0", "5000", "3000"),
    middle = state("8995", "5", "3995", "3000"),
    after = state("7990", "10", "3995", "1995");
  after.positions = [
    { symbol: "600519", quantity: "100" },
    { symbol: "300750", quantity: "100" },
  ];
  after.aggregate_holdings = after.positions.map((row: any) => ({
    ...row,
    market_value_cny: "1000",
  }));
  after.hypothetical_equity_cny = "9990";
  const fills = [core.symbol, wave.symbol].map((symbol, index) => ({
    intent: "BUY",
    fill: {
      transaction_id: `TEST_ONLY_${index}`,
      side: "BUY",
      sleeve: index ? "HOTSPOT_SATELLITE" : "CORE_VALUE",
      symbol,
      quantity: "100",
      price_cny: "10",
      fees_cny: "5",
      trade_date: "2026-10-21",
    },
    rationale: "TEST_ONLY manual hypothesis",
    source_version: index
      ? wave.entry_freeze_sha256
      : core.research.research_version,
    source_reference: index
      ? structuredClone(wave)
      : structuredClone(core.research),
    fill_record_sha256: String(index + 1).repeat(64),
    original_entry_transaction_id: null,
    original_entry_reference: {
      key: [index ? "HOTSPOT_SATELLITE" : "CORE_VALUE", symbol],
      fill_record_sha256: String(index + 1).repeat(64),
      narrative: {
        thesis: "TEST_ONLY Entry",
        hold_logic: "TEST_ONLY hold",
        invalidation_conditions: ["TEST_ONLY breaker"],
      },
    },
    original_pit_proven: false,
    original_entry_advisory_eligible: false,
    confirmation_idempotent: true,
    prepared_cash_unchanged: true,
    entry_blockers: ["HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY"],
    scope: "EXPLICIT_MANUAL_HYPOTHESIS_NOT_SYSTEM_ACTION",
    execution_price_scope: "CALLER_HYPOTHETICAL_NOT_MARKET_FILL",
    fee_scope: "CALLER_TOTAL_COST_HYPOTHESIS_NOT_VERIFIED_FEE_SCHEDULE",
    requested_quantity: "100",
    unfilled_quantity: "0",
    unfilled_scope: "INFORMATION_ONLY_NOT_OPEN_ORDER",
    before: index ? middle : before,
    after: index ? after : middle,
  }));
  return {
    schema_version: "source-bound-dual-sleeve-journey-v1",
    namespace: "SIMULATED",
    action: "no_order",
    scope: "DISPOSABLE_SOURCE_BOUND_REHEARSAL_NOT_PERSISTENT_PORTFOLIO",
    research_evaluated_at: "2026-10-24T01:00:00Z",
    source_identity: {
      core: [
        {
          symbol: core.symbol,
          candidate_binding: candidate,
          research_version: core.research.research_version,
        },
      ],
      hotspot: {
        symbol: wave.symbol,
        receipt_binding: receipt,
        entry_freeze_sha256: wave.entry_freeze_sha256,
      },
    },
    core_cases: [core],
    hotspot_case: wave,
    manual_rehearsal: manual
      ? {
          status: "EXPLICIT_SIMULATED_RECORDS_ONLY",
          fills,
          account_state: after,
          journal_receipt: {
            sha256: "e".repeat(64),
            retained: false,
            record_count: 10,
          },
          restart_equal: true,
          assumptions: { namespace: "TEST_ONLY", confirmed: true },
          temporary_journal_removed: true,
          actual_account_used: false,
          persistent_simulated_portfolio: false,
        }
      : {
          status: "NOT_REQUESTED",
          fills: [],
          account_state: null,
          journal_receipt: null,
          temporary_journal_removed: true,
          actual_account_used: false,
          persistent_simulated_portfolio: false,
        },
    actual_account_used: false,
    formal_eligibility: false,
    strategy_validated: false,
    approval_changed: false,
    broker_execution_permission: false,
    position_guidance: null,
  };
}
it("does not fetch or create any account on SSR", () => {
  const fetcher = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(<SourceBoundDualJourney />);
  expect(fetcher).not.toHaveBeenCalled();
  fetcher.mockRestore();
  expect(html).toContain("TEST_ONLY");
  expect(html).toContain("CORE5000、HOTSPOT3000、预留2000");
  expect(html).toContain("不会自动POST或成交");
  expect(html).toContain("共用一个临时模拟账本");
});
it("validates both sources, one shared account, and exact policy defaults without inventing risk", () => {
  expect(verifiedDualJourney(packet())).toBe(true);
  expect(verifiedDualJourney(packet(true))).toBe(true);
  const p = packet(),
    rows = Array.from({ length: 2 }, () => ({
      price: "10",
      fees: "5",
      quantity: "100",
      rationale: "TEST_ONLY discretionary",
      thesis: "TEST_ONLY thesis",
      hold: "TEST_ONLY hold",
      breakers: "TEST_ONLY breaker",
    }));
  const body = dualManualRequest(p, "2026-10-21", rows);
  expect(Object.keys(body).sort()).toEqual(
    [
      "confirmed_hypothetical",
      "expected_sources",
      "test_only_account",
      "manual_fills",
    ].sort(),
  );
  expect(body.expected_sources).toEqual(p.source_identity);
  expect(body.test_only_account.policy).toEqual(dualTestPolicy("2026-10-21"));
  expect(body.test_only_account.policy.sleeves.CORE_VALUE.cash_cny).toBe(
    "5000",
  );
  expect(body.test_only_account.policy.cash_reserve_cny).toBe("2000");
  expect(body.manual_fills.map((row) => row.fill.sleeve)).toEqual([
    "CORE_VALUE",
    "HOTSPOT_SATELLITE",
  ]);
  for (const row of body.manual_fills)
    expect(Object.keys(row.fill)).not.toContain("next_sell_session");
  expect(JSON.stringify(body)).not.toMatch(
    /workspace_root|hotspot_root|approval|receipt_binding_override/,
  );
  const changed = structuredClone(p.source_identity);
  changed.hotspot.entry_freeze_sha256 = "0".repeat(64);
  expect(dualSourcesMatch(changed, p.source_identity)).toBe(false);
  expect(() => dualManualRequest(p, "", rows)).toThrow();
});
function fifoPacket(): any {
  const p = packet(true);
  const first = p.manual_rehearsal.fills[0];
  const second = structuredClone(first);
  second.fill.transaction_id = "TEST_ONLY-CORE-SECOND";
  second.fill_record_sha256 = "d".repeat(64);
  second.original_entry_reference.fill_record_sha256 =
    second.fill_record_sha256;
  second.original_entry_reference.narrative.thesis =
    "TEST_ONLY second batch thesis";
  const sell = structuredClone(first);
  sell.intent = "REDUCE";
  sell.fill.side = "SELL";
  sell.fill.transaction_id = "TEST_ONLY-SELL-FIFO";
  sell.fill.quantity = "200";
  sell.requested_quantity = "200";
  sell.fill_record_sha256 = "e".repeat(64);
  sell.original_entry_transaction_id = null;
  sell.original_entry_reference = null;
  sell.consumed_original_entries = [first, second].map((entry, index) => ({
    transaction_id: entry.fill.transaction_id,
    quantity: "100",
    original_entry_reference: structuredClone(entry.original_entry_reference),
    manual_rationale: `TEST_ONLY batch ${index + 1} exit reason`,
    consistency_scope:
      "MANUAL_REASON_COMPARED_WITH_RECONSTRUCTED_THESIS_NOT_APPROVAL",
  }));
  p.manual_rehearsal.fills = [first, second, p.manual_rehearsal.fills[1], sell];
  return p;
}
it("binds every consumed FIFO Entry without claiming a single original reference", () => {
  expect(verifiedDualJourney(fifoPacket())).toBe(true);
  for (const mutate of [
    (p: any) => {
      p.manual_rehearsal.fills[3].original_entry_transaction_id =
        p.manual_rehearsal.fills[0].fill.transaction_id;
    },
    (p: any) => {
      p.manual_rehearsal.fills[3].consumed_original_entries[1].manual_rationale =
        "";
    },
    (p: any) => {
      p.manual_rehearsal.fills[3].consumed_original_entries[1].original_entry_reference =
        p.manual_rehearsal.fills[2].original_entry_reference;
    },
    (p: any) => {
      p.manual_rehearsal.fills[3].consumed_original_entries = [];
    },
  ]) {
    const p = fifoPacket();
    mutate(p);
    expect(verifiedDualJourney(p)).toBe(false);
  }
});
it.each(["1", "1000", "9007199254740993"])(
  "rejects an inconsistent consumed FIFO total %s without floating-point rounding",
  (quantity) => {
    const p = fifoPacket();
    p.manual_rehearsal.fills[3].consumed_original_entries[0].quantity =
      quantity;
    expect(verifiedDualJourney(p)).toBe(false);
  },
);
it.each([
  (p: any) => {
    p.core_cases = [];
  },
  (p: any) => {
    p.hotspot_case = null;
  },
  (p: any) => {
    p.namespace = "ACTUAL";
  },
  (p: any) => {
    p.formal_eligibility = true;
  },
  (p: any) => {
    p.broker_execution_permission = true;
  },
  (p: any) => {
    p.position_guidance = "20%";
  },
  (p: any) => {
    p.hotspot_case.current_pit = true;
  },
  (p: any) => {
    p.hotspot_case.current_signal = true;
  },
  (p: any) => {
    p.core_cases[0].research.confidence = { bad: true };
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].fill.quantity = "-100";
  },
  (p: any) => {
    p.hotspot_case.sleeve = "TACTICAL_HOTSPOT";
  },
  (p: any) => {
    p.source_identity.core[0].research_version = "MIXED";
  },
  (p: any) => {
    p.source_identity.hotspot.receipt_binding.sha256 = "0".repeat(64);
  },
  (p: any) => {
    p.core_cases[0].action_slots[0].outcome = "BUY";
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].source_version = "OTHER";
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].source_reference = {};
  },
  (p: any) => {
    p.manual_rehearsal.fills[0].original_entry_advisory_eligible = true;
  },
  (p: any) => {
    p.manual_rehearsal.temporary_journal_removed = false;
  },
  (p: any) => {
    p.manual_rehearsal.account_state.risk_review.namespace = "ACTUAL";
  },
])("rejects missing, mixed or authority-changing replies %#", (change) => {
  const p = packet(true);
  change(p);
  expect(verifiedDualJourney(p)).toBe(false);
});

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "TEST_ONLY exercises explicit GET/POST, busy/stale/error handling and 320/390 without a server",
  async () => {
    const output = resolve("../.tmp/source-dual-journey-ui");
    mkdirSync(output, { recursive: true });
    const { build } = require("esbuild");
    const bundle = await build({
      stdin: {
        contents:
          'import React from "react";import{createRoot}from"react-dom/client";import{SourceBoundDualJourney}from"./src/components/SourceBoundDualJourney";createRoot(document.getElementById("root")).render(<SourceBoundDualJourney/>);',
        loader: "tsx",
        resolveDir: process.cwd(),
      },
      bundle: true,
      write: false,
      platform: "browser",
      format: "iife",
      jsx: "automatic",
      define: { "process.env.NODE_ENV": '"production"' },
    });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const context = await chromium.launchPersistentContext(
      resolve(output, "profile"),
      { headless: true, executablePath: process.env.READINESS_BROWSER_PATH },
    );
    try {
      const page = await context.newPage();
      await page.route("**/*", (route: any) => route.abort());
      await page.setContent(
        '<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{padding:12px;box-sizing:border-box;width:100%}button{max-width:100%;white-space:normal}ul{padding-left:20px}</style><main id="root"></main></html>',
      );
      await page.evaluate(() => {
        const w = window as any;
        w.calls = [];
        window.fetch = ((url: string, options: any) => {
          w.calls.push({ url, options });
          return new Promise((resolve) => {
            w.reply = (body: unknown, status = 200) =>
              resolve({ ok: status === 200, status, json: async () => body });
            w.invalidJSON = () =>
              resolve({
                ok: true,
                status: 200,
                json: async () => {
                  throw new Error("TEST_ONLY JSON");
                },
              });
          });
        }) as any;
      });
      await page.addScriptTag({ content: bundle.outputFiles[0].text });
      const read = page.getByRole("button", {
        name: "读取双来源（只读）",
        exact: true,
      });
      await read.waitFor();
      expect(await page.evaluate(() => (window as any).calls.length)).toBe(0);
      await read.evaluate((button: HTMLButtonElement) => {
        button.click();
        button.click();
      });
      expect(await page.evaluate(() => (window as any).calls.length)).toBe(1);
      expect(await read.isDisabled()).toBe(true);
      await page.evaluate((p: unknown) => (window as any).reply(p), packet());
      await page
        .getByText("只读完成，尚未请求建账或模拟成交。", { exact: true })
        .waitFor();
      expect(
        await page
          .locator('[aria-label="双来源六动作（非建议）"] > ol > li')
          .count(),
      ).toBe(12);
      await page
        .getByText("显式TEST_ONLY双仓假设（不是账户IPS）", { exact: true })
        .click();
      const submit = page.getByRole("button", {
        name: "确认运行临时双仓演练",
        exact: true,
      });
      expect(await submit.isDisabled()).toBe(true);
      await page.getByLabel("演练开户及成交日期").fill("2026-10-21");
      for (const label of [
        "本次人工演练理由",
        "原Entry投资逻辑假设",
        "持有逻辑假设",
        "失效条件假设",
      ])
        for (let i = 0; i < 2; i++)
          await page
            .getByLabel(label, { exact: true })
            .nth(i)
            .fill(`TEST_ONLY ${label}`);
      const confirm = page.getByRole("checkbox");
      await confirm.check();
      await submit.click();
      expect(await read.isDisabled()).toBe(true);
      const post = await page.evaluate(() => (window as any).calls.at(-1));
      expect(post.url).toBe(dualJourneyUrl);
      expect(post.options.method).toBe("POST");
      expect(post.options.cache).toBe("no-store");
      const body = JSON.parse(post.options.body);
      expect(Object.keys(body).sort()).toEqual(
        [
          "confirmed_hypothetical",
          "expected_sources",
          "test_only_account",
          "manual_fills",
        ].sort(),
      );
      expect(body.expected_sources).toEqual(packet().source_identity);
      expect(body.test_only_account.policy).toEqual(
        dualTestPolicy("2026-10-21"),
      );
      const wrong = packet(true);
      wrong.source_identity.hotspot.entry_freeze_sha256 = "f".repeat(64);
      wrong.hotspot_case.entry_freeze_sha256 = "f".repeat(64);
      wrong.manual_rehearsal.fills[1].source_version = "f".repeat(64);
      wrong.manual_rehearsal.fills[1].source_reference.entry_freeze_sha256 =
        "f".repeat(64);
      expect(verifiedDualJourney(wrong)).toBe(true);
      await page.evaluate((p: unknown) => (window as any).reply(p), wrong);
      await page.getByRole("alert").waitFor();
      expect(await submit.isDisabled()).toBe(true);
      expect(await page.locator('[aria-label="WAVE封存来源"]').count()).toBe(0);
      await read.click();
      await page.evaluate((p: unknown) => (window as any).reply(p), packet());
      await page
        .getByText("只读完成，尚未请求建账或模拟成交。", { exact: true })
        .waitFor();
      await confirm.check();
      await submit.click();
      await page.evaluate(
        (p: unknown) => (window as any).reply(p),
        fifoPacket(),
      );
      await page.locator('[aria-label="同一临时账本结果"]').waitFor();
      expect(
        await page.locator('[aria-label="卖出实际消耗原Entry"]').count(),
      ).toBe(2);
      expect(
        await page
          .getByText("TEST_ONLY batch 2 exit reason", { exact: false })
          .count(),
      ).toBe(1);
      expect(await submit.isDisabled()).toBe(true);
      expect(
        await page
          .getByText("风险输入不全，尚未通过", { exact: false })
          .count(),
      ).toBe(1);
      const dimensions = [];
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
          overflowing: [...document.querySelectorAll("main *")]
            .filter((item) => {
              const r = item.getBoundingClientRect();
              return r.width > 0 && (r.left < -1 || r.right > innerWidth + 1);
            })
            .map((item) => item.tagName),
        }));
        expect(size.scrollWidth).toBeLessThanOrEqual(width);
        expect(size.overflowing).toEqual([]);
        dimensions.push(size);
        await page.screenshot({
          path: resolve(output, `${width}.png`),
          fullPage: true,
        });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(dimensions, null, 2),
      );
      for (const failure of ["409", "json", "authority", "missing"]) {
        await read.click();
        if (failure === "json")
          await page.evaluate(() => (window as any).invalidJSON());
        else {
          const bad = packet();
          if (failure === "authority") bad.formal_eligibility = true;
          if (failure === "missing") bad.core_cases = [];
          await page.evaluate(
            ({ p, status }: { p: unknown; status: number }) =>
              (window as any).reply(p, status),
            { p: bad, status: failure === "409" ? 409 : 200 },
          );
        }
        await page.getByRole("alert").waitFor();
        expect(await submit.isDisabled()).toBe(true);
        expect(
          await page.locator('[aria-label="同一临时账本结果"]').count(),
        ).toBe(0);
      }
    } finally {
      await context.close();
    }
  },
  90000,
);
