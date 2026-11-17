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
  SourceActionReasons,
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

it("TEST_ONLY deduplicates exact shared reasons without losing Chinese, unknown or action-specific premises", () => {
  const slots = sourcePacket().cases[0].action_slots;
  for (const slot of slots)
    slot.reasons = [
      "CURRENT_PLAN_EXPIRED",
      "CURRENT_PLAN_EXPIRED",
      "model_validity_unavailable",
      "TEST_ONLY 中文否定前提必须保留",
      "TEST_ONLY_UNKNOWN_A",
      "TEST_ONLY_UNKNOWN_A",
      "TEST_ONLY_UNKNOWN_B",
    ];
  slots[0].reasons.push("TEST_ONLY 买入特有：价格依据不足");
  slots[4].reasons.push(
    "TEST_ONLY 退出特有：原始论点待核验",
    "TEST_ONLY_EXIT_UNKNOWN",
  );
  slots[5].reasons.push("research_case:TEST_ONLY_FUTURE_CODE");
  const before = JSON.stringify(slots);
  const fetcher = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(
    <SourceActionReasons slots={slots} />,
  ).replace(/<!--[\s\S]*?-->/g, "");
  const visible = html.replace(/<details>[\s\S]*?<\/details>/g, "");
  expect(visible.match(/当前计划已到期，不能继续使用原价位/g)).toHaveLength(1);
  expect(visible.match(/模型有效性尚未提供/g)).toHaveLength(1);
  expect(visible.match(/TEST_ONLY 中文否定前提必须保留/g)).toHaveLength(1);
  expect(visible).toContain("TEST_ONLY 买入特有：价格依据不足");
  expect(visible).toContain("TEST_ONLY 退出特有：原始论点待核验");
  expect(visible).not.toContain("TEST_ONLY_UNKNOWN_A");
  expect(visible).not.toContain("TEST_ONLY_FUTURE_CODE");
  expect(html).toContain("research_case:TEST_ONLY_FUTURE_CODE");
  expect(html).toContain("另有 2 项未识别原因");
  expect(html).toContain("另有 1 项未识别原因");
  expect(html).toContain("仍为否定前提");
  expect(html).toContain("TEST_ONLY_EXIT_UNKNOWN");
  const originals = html.match(
    /<summary>本动作完整原始原因[\s\S]*?<\/details>/g,
  )!;
  expect(originals).toHaveLength(6);
  for (let i = 0; i < slots.length; i++) {
    expect(originals[i]).toContain(`${slots[i].reasons.length} 项`);
    expect(originals[i].match(/<li>/g)).toHaveLength(slots[i].reasons.length);
    for (const reason of slots[i].reasons)
      expect(originals[i]).toContain(reason);
  }
  expect(html.match(/NO_ACTION · 不形成动作/g)).toHaveLength(5);
  expect(html.match(/WAIT · 等待条件/g)).toHaveLength(1);
  expect(html).not.toContain("<table");
  expect(html).toContain("overflow-wrap:anywhere");
  expect(html).toContain("max-width:100%");
  expect(JSON.stringify(slots)).toBe(before);
  expect(fetcher).not.toHaveBeenCalled();
  fetcher.mockRestore();
});

it("TEST_ONLY shows a partly shared reason once with exact applicable actions, never as a six-action premise", () => {
  const slots = sourcePacket().cases[0].action_slots;
  slots[0].reasons.push("TEST_ONLY 部分适用的否定前提");
  slots[1].reasons.push("TEST_ONLY 部分适用的否定前提");
  const html = renderToStaticMarkup(
    <SourceActionReasons slots={slots} />,
  ).replace(/<!--[\s\S]*?-->/g, "");
  const visible = html.replace(/<details>[\s\S]*?<\/details>/g, "");
  expect(visible.match(/TEST_ONLY 部分适用的否定前提/g)).toHaveLength(1);
  expect(visible).toContain("适用动作：买入、加仓</p>");
  expect(visible.match(/本动作受上列共同条件第 1、2 组/g)).toHaveLength(2);
  expect(visible.match(/本动作受上列共同条件第 1 组/g)).toHaveLength(4);
  const distinct = slots.map((slot: any, index: number) => ({
    ...slot,
    reasons: [`TEST_ONLY 独立原因${index}`],
  }));
  const other = renderToStaticMarkup(<SourceActionReasons slots={distinct} />);
  expect(other).toContain("没有可合并的共同原因");
  for (let i = 0; i < 6; i++) expect(other).toContain(`TEST_ONLY 独立原因${i}`);
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

const legacyReceiptHashes = {
  read: "4b0c4015ffc84d5b33657d1ab1b57f2cca73445ea2d26e76f60e1a7cc794989f",
  manual: "17b5fe0ed2cd05730ff0a72f1014ba0a064b9b068a8289bc87f98fb6ae3a9ced",
};
const receiptInputNames = [
  "SOURCE_BOUND_JOURNEY_JSON",
  "SOURCE_BOUND_MANUAL_JSON",
  "SOURCE_BOUND_JOURNEY_SHA256",
  "SOURCE_BOUND_MANUAL_SHA256",
] as const;

function pinnedReceiptInputs(env: Record<string, string | undefined>) {
  const explicitHashes =
    env.SOURCE_BOUND_JOURNEY_SHA256 !== undefined ||
    env.SOURCE_BOUND_MANUAL_SHA256 !== undefined;
  const inputs = {
    read: {
      file: env.SOURCE_BOUND_JOURNEY_JSON,
      expected: explicitHashes
        ? env.SOURCE_BOUND_JOURNEY_SHA256
        : legacyReceiptHashes.read,
    },
    manual: {
      file: env.SOURCE_BOUND_MANUAL_JSON,
      expected: explicitHashes
        ? env.SOURCE_BOUND_MANUAL_SHA256
        : legacyReceiptHashes.manual,
    },
  };
  for (const input of Object.values(inputs)) {
    expect(
      typeof input.file,
      "Each opt-in receipt requires an explicit file",
    ).toBe("string");
    expect(input.file?.trim()).toBeTruthy();
    expect(
      input.expected,
      "Both expected SHA-256 values must be explicitly pinned when overriding",
    ).toMatch(/^[a-fA-F0-9]{64}$/);
  }
  return inputs;
}

function assertPinnedBytes(bytes: Buffer, expected: unknown) {
  expect(expected).toMatch(/^[a-fA-F0-9]{64}$/);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(
    (expected as string).toLowerCase(),
  );
}

it("rejects wrong or malformed expected receipt hashes rather than learning them from the input", () => {
  const bytes = Buffer.from("TEST_ONLY receipt bytes");
  for (const expected of ["0".repeat(64), "not-a-sha", "", undefined])
    expect(() => assertPinnedBytes(bytes, expected)).toThrow();
});

it("retains legacy pins and rejects incomplete explicit receipt pairs", () => {
  const files = {
    SOURCE_BOUND_JOURNEY_JSON: "TEST_ONLY/read.json",
    SOURCE_BOUND_MANUAL_JSON: "TEST_ONLY/manual.json",
  };
  expect(pinnedReceiptInputs(files).read.expected).toBe(
    legacyReceiptHashes.read,
  );
  expect(pinnedReceiptInputs(files).manual.expected).toBe(
    legacyReceiptHashes.manual,
  );
  expect(() =>
    pinnedReceiptInputs({
      ...files,
      SOURCE_BOUND_JOURNEY_SHA256: "a".repeat(64),
    }),
  ).toThrow();
  expect(() =>
    pinnedReceiptInputs({
      SOURCE_BOUND_JOURNEY_JSON: files.SOURCE_BOUND_JOURNEY_JSON,
    }),
  ).toThrow();
});

it.skipIf(!receiptInputNames.some((name) => process.env[name] !== undefined))(
  "validates the user-pinned actual in-process API receipts without any Live request",
  () => {
    const inputs = pinnedReceiptInputs(process.env);
    const read = readFileSync(inputs.read.file!);
    const manual = readFileSync(inputs.manual.file!);
    assertPinnedBytes(read, inputs.read.expected);
    assertPinnedBytes(manual, inputs.manual.expected);
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
      const narrowSource = sourcePacket(true);
      for (const item of narrowSource.cases)
        for (const slot of item.action_slots)
          slot.reasons.push(
            "CURRENT_PLAN_EXPIRED",
            "TEST_ONLY 手机中文原因始终可读",
            `TEST_ONLY_UNKNOWN_MOBILE_${"X".repeat(240)}`,
          );
      await page.evaluate(
        (p: unknown) => (window as any).reply(p),
        narrowSource,
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
        const sourceLayout = await page
          .locator('[aria-label="六动作核验（非建议）"]')
          .evaluateAll((elements: HTMLElement[]) =>
            elements.map((element) => ({
              left: element.getBoundingClientRect().left,
              right: element.getBoundingClientRect().right,
              width: element.clientWidth,
              scrollWidth: element.scrollWidth,
              actions: element.querySelectorAll(":scope > ol > li").length,
              tables: element.querySelectorAll("table").length,
            })),
          );
        expect(sourceLayout).toHaveLength(2);
        for (const layout of sourceLayout) {
          expect(layout.left).toBeGreaterThanOrEqual(0);
          expect(layout.right).toBeLessThanOrEqual(width);
          expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width);
          expect(layout.actions).toBe(6);
          expect(layout.tables).toBe(0);
        }
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
