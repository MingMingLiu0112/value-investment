import React from "react";
import { expect, it, vi } from "vitest";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { createHash } from "node:crypto";
import { PersistentSimulatedPortfolio } from "../src/components/PersistentSimulatedPortfolio";
import {
  readSimulatedPortfolio,
  simulatedCommon,
  simulatedPortfolioUrl,
  SimulatedRequestError,
  verifiedPersistentSimulatedWorkbench,
  writeSimulatedPortfolio,
} from "../src/services/persistentSimulatedPortfolio";
const { renderToStaticMarkup } = require("react-dom/server");

it.skipIf(!process.env.PERSISTENT_SIMULATED_VIEWS_PATH)(
  "validates actual public-reference API states including cancellation, FIFO and restored Entries",
  () => {
    const file = resolve(process.env.PERSISTENT_SIMULATED_VIEWS_PATH!);
    const within = relative(resolve(process.cwd(), "..", ".tmp"), file);
    expect(within).not.toMatch(/^(?:\.\.|[A-Za-z]:|[\\/])/);
    const bytes = readFileSync(file);
    const receipt = JSON.parse(
      readFileSync(resolve(dirname(file), "receipt.json"), "utf8"),
    );
    expect(receipt.scope).toBe(
      "REAL_PUBLIC_REFERENCES_WITH_TEST_ONLY_ACCOUNT_NOT_INVESTMENT_APPROVAL",
    );
    expect(receipt.status).toBe("PASS");
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      receipt.views_sha256,
    );
    const states = JSON.parse(bytes.toString("utf8"));
    expect(states.length).toBe(receipt.view_count);
    for (const state of states)
      expect(verifiedPersistentSimulatedWorkbench(state)).toBe(true);
    expect(states[0].account.status).toBe("NOT_INITIALIZED");
    expect(
      states.some((s: any) => s.mutation?.operation === "cancel-fill"),
    ).toBe(true);
    expect(states.at(-1).account.portfolio.cash_cny).toBe(
      receipt.final_cash_cny,
    );
    expect(states.at(-1).account.entries[0].remaining_quantity).toBe("0");
    expect(states.at(-1).account.entries[0].hypothesis).not.toBeNull();
    expect(receipt.separate_process_restoration).toBe(true);
    expect(receipt.sources_unchanged).toBe(true);
  },
);

/** TEST_ONLY native-service-shaped fixtures; no journal, actual account or API. */
function fixture(
  phase: "empty" | "initialized" | "pending" | "filled" | "entry" = "empty",
  available = true,
): any {
  const initialized = phase !== "empty",
    pending = phase === "pending",
    filled = phase === "filled" || phase === "entry";
  const revision =
    phase === "entry" ? 4 : filled ? 3 : pending ? 2 : initialized ? 1 : 0;
  const fill = {
    transaction_id: "TEST_ONLY-buy",
    side: "BUY",
    sleeve: "CORE_VALUE",
    symbol: "600519",
    exchange: "SSE",
    quantity: "100",
    price_cny: "10",
    fees_cny: "5",
    trade_date: "2026-10-23",
    trading_unit: "100",
    next_sell_session: "2026-10-26",
  };
  const position = {
    symbol: "600519",
    exchange: "SSE",
    quantity: "100",
    cost_cny: "1005",
    sleeves: [
      {
        sleeve: "CORE_VALUE",
        quantity: "100",
        cost_cny: "1005",
        sellable_quantity: "0",
        next_sell_session: "2026-10-26",
      },
    ],
    market_value_cny: null,
  };
  return {
    schema_version: "persistent-simulated-workbench-v1",
    action: "no_order",
    namespace: "SIMULATED",
    formal_eligibility: false,
    actual_account_used: false,
    position_guidance: null,
    server_now: "2026-10-24T10:00:00+08:00",
    account: {
      schema_version: "persistent-simulated-portfolio-v1",
      account_context: {
        namespace: "SIMULATED",
        account_id: "TEST_ONLY-paper",
        version: "persistent-simulated-portfolio-v1",
      },
      account_id: "TEST_ONLY-paper",
      namespace: "SIMULATED",
      action: "no_order",
      status: initialized ? "CONNECTED" : "NOT_INITIALIZED",
      revision,
      portfolio: !initialized
        ? null
        : {
            action: "no_order",
            revision,
            as_of: "2026-10-23",
            cash_cny: filled ? "8995" : "10000",
            realized_pnl_cny: "0",
            positions: filled ? [position] : [],
            trades: filled
              ? [
                  {
                    ...fill,
                    record_sha256: "c".repeat(64),
                    confirmed_at: "2026-10-24T10:00:00+08:00",
                  },
                ]
              : [],
            pending_draft: !pending
              ? null
              : {
                  status: "DRAFT_UNRECONFIRMED",
                  prepared_record_sha256: "b".repeat(64),
                  fill,
                  cash_cny: "8995",
                  realized_pnl_cny: "0",
                  positions: [position],
                },
          },
      entries: !filled
        ? []
        : [
            {
              transaction_id: fill.transaction_id,
              symbol: "600519",
              sleeve: "CORE_VALUE",
              remaining_quantity: "100",
              fill_record_sha256: "c".repeat(64),
              hypothesis:
                phase !== "entry"
                  ? null
                  : {
                      thesis: "TEST_ONLY thesis",
                      hold_logic: "TEST_ONLY hold",
                      invalidation_conditions: ["TEST_ONLY breaker"],
                      research_version: JSON.stringify({
                        path: "runtime/public-research/TEST_ONLY.json",
                        sha256: "a".repeat(64),
                      }),
                      strategy_version:
                        "SIMULATED_MANUAL_HYPOTHESIS_NOT_STRATEGY_APPROVAL",
                    },
              entry_confirmation_sha256:
                phase === "entry" ? "d".repeat(64) : null,
              original_pit_proven: false,
              advisory_eligible: false,
            },
          ],
      formal_eligibility: false,
      actual_account_used: false,
      ownership_verified: false,
      position_guidance: null,
      confirmed_fill_correction: "UNSUPPORTED",
      source_scope:
        "HASH_BOUND_REFERENCE_NOT_STRATEGY_OR_MARKET_PRICE_ADMISSION",
    },
    sources: {
      status: available ? "AVAILABLE" : "UNAVAILABLE",
      items: available
        ? [
            {
              id: "core:600519",
              symbol: "600519",
              sleeve: "CORE_VALUE",
              candidate_binding: {
                path: "runtime/public-research/TEST_ONLY.json",
                sha256: "a".repeat(64),
              },
              scope: "REFERENCE_ONLY_NOT_APPROVAL",
            },
          ]
        : [],
    },
  };
}
function mutation(
  phase: Parameters<typeof fixture>[0],
  operation: string,
  available = true,
): any {
  return {
    ...fixture(phase, available),
    mutation: {
      operation,
      record_sha256: "e".repeat(64),
      result: { action: "no_order", scope: "TEST_ONLY" },
    },
  };
}
it("renders conservatively without reading or initializing on SSR", () => {
  const fetcher = vi.spyOn(globalThis, "fetch");
  try {
    const html = renderToStaticMarkup(<PersistentSimulatedPortfolio />);
    expect(fetcher).not.toHaveBeenCalled();
    expect(html).toContain("持久模拟账户");
    expect(html).toContain("确认后更正暂不支持");
    expect(html).toContain("风险及仓位未评估");
  } finally {
    fetcher.mockRestore();
  }
});
it("accepts native account states and unavailable sources independently", () => {
  for (const phase of [
    "empty",
    "initialized",
    "pending",
    "filled",
    "entry",
  ] as const)
    for (const available of [true, false])
      expect(
        verifiedPersistentSimulatedWorkbench(fixture(phase, available)),
      ).toBe(true);
  expect(simulatedCommon(fixture(), "TEST_ONLY-stable")).toEqual({
    confirmed_hypothetical: true,
    expected_revision: 0,
    idempotency_key: "TEST_ONLY-stable",
  });
});
it.each([
  (p: any) => {
    p.account.entries[0].transaction_id = "OTHER-ENTRY";
  },
  (p: any) => {
    p.account.entries[0].symbol = "300750";
  },
  (p: any) => {
    p.namespace = "ACTUAL";
  },
  (p: any) => {
    p.formal_eligibility = true;
  },
  (p: any) => {
    p.position_guidance = { quantity: 100 };
  },
  (p: any) => {
    p.server_now = "2026-02-30T12:00:00Z";
  },
  (p: any) => {
    p.account.account_context.account_id = "OTHER";
  },
  (p: any) => {
    p.account.ownership_verified = true;
  },
  (p: any) => {
    p.account.revision = -1;
  },
  (p: any) => {
    p.account.entries[0].advisory_eligible = true;
  },
  (p: any) => {
    p.account.entries[0].hypothesis.thesis = {};
  },
  (p: any) => {
    p.account.portfolio.cash_cny = "NaN";
  },
  (p: any) => {
    p.account.portfolio.revision++;
  },
  (p: any) => {
    p.account.portfolio.trades[0].fees_cny = "-5";
  },
  (p: any) => {
    p.account.portfolio.pending_draft = {};
  },
  (p: any) => {
    p.sources.items[0].candidate_binding.path = "../private.json";
  },
  (p: any) => {
    p.sources.items[0].sleeve = "HOTSPOT_SATELLITE";
  },
  (p: any) => {
    p.sources.items[0].candidate_binding.sha256 = "broken";
  },
  (p: any) => {
    p.sources.items[0].scope = "APPROVED";
  },
  (p: any) => {
    p.mutation = { operation: "unlock", record_sha256: "e".repeat(64) };
  },
])("rejects malformed or authority-changing packet %#", (change) => {
  const p = fixture("entry");
  change(p);
  expect(verifiedPersistentSimulatedWorkbench(p)).toBe(false);
});
it("uses only same-origin no-store requests, rejects wrong mutation and reports 409/422", async () => {
  const fetcher = vi.spyOn(globalThis, "fetch");
  try {
    fetcher.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture(),
    } as Response);
    await readSimulatedPortfolio();
    expect(fetcher).toHaveBeenLastCalledWith(simulatedPortfolioUrl, {
      cache: "no-store",
      credentials: "same-origin",
    });
    for (const status of [409, 422]) {
      fetcher.mockResolvedValueOnce({ ok: false, status } as Response);
      await expect(
        writeSimulatedPortfolio("initialize", simulatedCommon(fixture())),
      ).rejects.toMatchObject({ status, uncertain: false });
    }
    fetcher.mockResolvedValueOnce({
      ok: true,
      json: async () => mutation("initialized", "cancel-fill"),
    } as Response);
    await expect(
      writeSimulatedPortfolio("initialize", simulatedCommon(fixture())),
    ).rejects.toMatchObject({ uncertain: true });
    fetcher.mockRejectedValueOnce(new Error("TEST_ONLY disconnected"));
    await expect(
      writeSimulatedPortfolio("initialize", simulatedCommon(fixture())),
    ).rejects.toBeInstanceOf(SimulatedRequestError);
  } finally {
    fetcher.mockRestore();
  }
});

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "TEST_ONLY records explicit writes, reopens draft, rejects stale source and preserves uncertain retry at 320/390",
  async () => {
    const output = resolve("../.tmp/persistent-simulated-ui");
    mkdirSync(output, { recursive: true });
    const { build } = require("esbuild");
    const bundle = await build({
      stdin: {
        contents:
          'import React from "react";import{createRoot}from"react-dom/client";import{PersistentSimulatedPortfolio}from"./src/components/PersistentSimulatedPortfolio";let root;window.restart=()=>{root?.unmount();root=createRoot(document.getElementById("root"));root.render(<PersistentSimulatedPortfolio/>)};window.restart();',
        loader: "tsx",
        resolveDir: process.cwd(),
      },
      bundle: true,
      write: false,
      format: "iife",
      platform: "browser",
      define: { "process.env.NODE_ENV": '"production"' },
    });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const browser = await chromium.launch({
      executablePath: process.env.READINESS_BROWSER_PATH,
      headless: true,
    });
    const context = await browser.newContext();
    try {
      await context.route("**/*", (route: any) => route.abort());
      const page = await context.newPage();
      // Fulfilled entirely in-process: secure localhost UUID support, no server/network.
      await page.route(
        "http://localhost/TEST_ONLY-persistent-ui",
        (route: any) =>
          route.fulfill({
            contentType: "text/html",
            body: '<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;font:14px Arial}main{padding:12px;box-sizing:border-box;width:100%}ul{padding-left:20px}button{max-width:100%;white-space:normal!important;height:auto!important}select{max-width:100%}</style><main id="root"></main></html>',
          }),
      );
      await page.goto("http://localhost/TEST_ONLY-persistent-ui");
      await page.evaluate(() => {
        const w = window as any;
        w.calls = [];
        window.fetch = ((url: string, options: any) => {
          w.calls.push({ url, options });
          return new Promise((resolve, reject) => {
            w.fail = () => reject(new Error("TEST_ONLY timeout"));
            w.reply = (value: unknown, status = 200) =>
              resolve({ ok: status === 200, status, json: async () => value });
          });
        }) as any;
      });
      await page.addScriptTag({ content: bundle.outputFiles[0].text });
      const panel = page.locator('[aria-label="持久模拟账户"]');
      const read = () =>
        panel.getByRole("button", { name: "读取 / 刷新模拟账户", exact: true });
      const consent = () => panel.getByRole("checkbox");
      const last = () => page.evaluate(() => (window as any).calls.at(-1));
      const reply = (p: any, status = 200) =>
        page.evaluate(
          ({ p, status }: { p: unknown; status: number }) =>
            (window as any).reply(p, status),
          { p, status },
        );
      await panel.waitFor();
      expect(await page.evaluate(() => (window as any).calls.length)).toBe(0);
      await read().click();
      await reply(fixture());
      await panel.getByText("初始化模拟账户", { exact: true }).waitFor();
      await panel.getByLabel("初始模拟现金（元）").fill("10000");
      await panel.getByLabel("模拟开户日期").fill("2026-10-23");
      const initialize = panel.getByRole("button", {
        name: "确认初始化模拟账户",
        exact: true,
      });
      expect(await initialize.isDisabled()).toBe(true);
      await consent().check();
      await initialize.evaluate((button: HTMLButtonElement) => {
        button.click();
        button.click();
      });
      expect(
        await page.evaluate(
          () =>
            (window as any).calls.filter(
              (call: any) => call.options.method === "POST",
            ).length,
        ),
      ).toBe(1);
      const init = JSON.parse((await last()).options.body);
      expect(init.confirmed_at).toBe(fixture().server_now);
      expect(init.expected_revision).toBe(0);
      expect(init.cash_cny).toBe("10000");
      expect(init).not.toHaveProperty("policy");
      await reply(mutation("initialized", "initialize"));
      await panel.getByText("共享现金与持仓", { exact: true }).waitFor();
      for (const [label, value] of [
        ["证券代码", "600519"],
        ["假设成交股数", "100"],
        ["假设成交价格（非行情）", "10"],
        ["假设成交费用（元）", "5"],
        ["模拟成交日期", "2026-10-23"],
      ])
        await panel.getByLabel(label, { exact: true }).fill(value);
      expect(await consent().isChecked()).toBe(false);
      await consent().check();
      await panel
        .getByRole("button", { name: "准备模拟草稿", exact: true })
        .click();
      const prepared = JSON.parse((await last()).options.body);
      expect(prepared.expected_revision).toBe(1);
      expect(prepared.fill.side).toBe("BUY");
      expect(Object.keys(prepared.fill).sort()).toEqual(
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
        ].sort(),
      );
      await reply(mutation("pending", "prepare-fill"));
      await panel.locator('[aria-label="已保存模拟草稿"]').waitFor();
      // Simulated remount proves no dependency on the prepare response held in React state.
      await page.evaluate(() => (window as any).restart());
      await read().click();
      await reply(fixture("pending", false));
      await panel.locator('[aria-label="已保存模拟草稿"]').waitFor();
      await consent().check();
      await panel
        .getByRole("button", { name: "取消未确认草稿", exact: true })
        .click();
      const cancelled = JSON.parse((await last()).options.body);
      expect(cancelled.expected_revision).toBe(2);
      expect(cancelled.prepared_record_sha256).toBe("b".repeat(64));
      expect(cancelled.confirmed_at).toBe(fixture().server_now);
      await reply(mutation("initialized", "cancel-fill", false));
      await read().click();
      await reply(fixture("pending", false));
      await panel.locator('[aria-label="已保存模拟草稿"]').waitFor();
      await consent().check();
      await panel
        .getByRole("button", { name: "确认这笔模拟成交", exact: true })
        .click();
      const confirmed = JSON.parse((await last()).options.body);
      expect(confirmed.prepared_record_sha256).toBe("b".repeat(64));
      expect(confirmed.expected_revision).toBe(2);
      await reply(mutation("filled", "confirm-fill", false));
      await panel.locator('[aria-label="模拟原Entry"]').waitFor();
      expect(
        await panel
          .getByRole("button", { name: "确认模拟Entry假说", exact: true })
          .isDisabled(),
      ).toBe(true);
      await read().click();
      await reply(fixture("filled"));
      await panel
        .getByLabel("选择未绑定假说的模拟Entry")
        .selectOption("c".repeat(64));
      await panel
        .getByLabel("选择同证券同策略来源")
        .selectOption("core:600519");
      await panel
        .getByLabel("原始投资假说", { exact: true })
        .fill("TEST_ONLY thesis");
      await panel
        .getByLabel("继续持有理由", { exact: true })
        .fill("TEST_ONLY hold");
      await panel.getByLabel("失效条件（每行一项）").fill("TEST_ONLY breaker");
      await consent().check();
      await panel
        .getByRole("button", { name: "确认模拟Entry假说", exact: true })
        .click();
      const entry = JSON.parse((await last()).options.body);
      expect(entry.expected_source_binding).toEqual(
        fixture("filled").sources.items[0].candidate_binding,
      );
      expect(entry.fill_record_sha256).toBe("c".repeat(64));
      expect(entry).not.toHaveProperty("confirmed_at");
      await reply({ detail: "RESEARCH_VERSION_CHANGED" }, 409);
      await panel.getByText(/研究来源已变化（409）/).waitFor();
      expect(await panel.locator('[aria-label="模拟原Entry"]').count()).toBe(0);
      await read().click();
      await reply(fixture("filled"));
      await panel
        .getByLabel("选择未绑定假说的模拟Entry")
        .selectOption("c".repeat(64));
      await panel
        .getByLabel("选择同证券同策略来源")
        .selectOption("core:600519");
      await consent().check();
      await panel
        .getByRole("button", { name: "确认模拟Entry假说", exact: true })
        .click();
      const originalRequest = await last();
      await page.evaluate(() => (window as any).fail());
      await panel
        .getByRole("button", { name: "以相同请求重试模拟写入", exact: true })
        .waitFor();
      await consent().check();
      await panel
        .getByRole("button", { name: "以相同请求重试模拟写入", exact: true })
        .click();
      expect((await last()).options.body).toBe(originalRequest.options.body);
      await reply(mutation("entry", "confirm-entry"));
      await panel
        .getByText("原假说：TEST_ONLY thesis", { exact: true })
        .waitFor();
      const layouts = [];
      for (const width of [320, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await panel
          .locator("details")
          .evaluateAll((nodes: HTMLDetailsElement[]) =>
            nodes.forEach((node) => {
              node.open = true;
            }),
          );
        const layout = await page.evaluate(() => ({
          width: innerWidth,
          scroll: document.documentElement.scrollWidth,
          overflow: [...document.querySelectorAll("main *")]
            .filter((el) => {
              const r = el.getBoundingClientRect();
              return r.width > 0 && (r.left < -1 || r.right > innerWidth + 1);
            })
            .map((el) => el.tagName),
        }));
        expect(layout.scroll).toBeLessThanOrEqual(width);
        expect(layout.overflow).toEqual([]);
        layouts.push(layout);
        await page.screenshot({
          path: resolve(output, `${width}.png`),
          fullPage: true,
        });
      }
      writeFileSync(
        resolve(output, "layout.json"),
        JSON.stringify(layouts, null, 2),
      );
      await read().click();
      await reply({ detail: "TEST_ONLY invalid fill" }, 422);
      await panel.getByText(/输入或记账条件未通过（422）/).waitFor();
      expect(await panel.locator('[aria-label="模拟原Entry"]').count()).toBe(0);
      const calls = await page.evaluate(() => (window as any).calls);
      for (const call of calls) {
        expect(call.options.cache).toBe("no-store");
        expect(call.options.credentials).toBe("same-origin");
      }
    } finally {
      await context.close();
      await browser.close();
    }
  },
  90000,
);
