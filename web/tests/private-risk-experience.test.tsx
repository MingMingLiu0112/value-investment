import React from "react";
import { expect, it } from "vitest";
import { ReconciliationPanel } from "../src/components/ReconciliationPanel";
import { retryableWrite } from "../src/components/PrivateRiskContext";
import type { PortfolioResponse } from "../src/types/api";
import { reconciliationConfirmation } from "../src/components/reconciliationConfirmation";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};

it("shows explicit checks and initial holdings with zero fills, never preconfirms", () => {
  const html = renderToStaticMarkup(
    <ReconciliationPanel
      portfolio={
        {
          revision: 1,
          positions: [],
          trades: [],
          cash_cny: "8000",
          pending_draft: null,
        } as unknown as PortfolioResponse
      }
      onConfirm={async () => {
        throw new Error("must not write during render");
      }}
      onDone={() => {}}
    />,
  );
  expect(html).toContain("现金 8000 元与记录一致");
  expect(html).toContain("尚无成交，本次核对已确认的初始现金与持仓");
  expect(html).toContain("本人对账说明");
  expect(html.match(/<input[^>]*type="checkbox"[^>]*>/g)).toHaveLength(3);
  for (const checkbox of html.match(/<input[^>]*type="checkbox"[^>]*>/g) ?? [])
    expect(checkbox).not.toContain('checked=""');
  expect(html).toMatch(/<button[^>]*disabled/);
});

it("retains exact request identity and timestamp for uncertain network retries", () => {
  const retry = retryableWrite();
  const first = retry.body("revision1:note", () => ({
    idempotency_key: "key1",
    confirmed_at: "time1",
  }));
  expect(
    retry.body("revision1:note", () => ({ idempotency_key: "key2" })),
  ).toBe(first);
  expect(
    retry.body("revision2:note", () => ({ idempotency_key: "key3" })),
  ).not.toBe(first);
  retry.clear();
  expect(
    retry.body("revision1:note", () => ({ idempotency_key: "key4" })),
  ).not.toBe(first);
});

it("never upgrades internal review even when stale external fields are present", () => {
  const body = reconciliationConfirmation({
    mode: "INTERNAL",
    evidenceId: "old-ref",
    evidenceKind: "broker_statement",
    note: "本人核对",
    checks: {
      cash_checked: true,
      positions_checked: true,
      fills_checked: true,
    },
  });
  expect(body).not.toHaveProperty("account_evidence");
});

it("requires external reference, supported kind and every explicit acknowledgement", () => {
  const input = {
    mode: "EXTERNAL" as const,
    evidenceId: "STATEMENT-TEST-ONLY",
    evidenceKind: "broker_statement",
    note: "本人使用真实对账单核对",
    checks: {
      cash_checked: true,
      positions_checked: true,
      fills_checked: true,
    },
  };
  expect(reconciliationConfirmation(input).account_evidence).toEqual({
    id: "STATEMENT-TEST-ONLY",
    kind: "broker_statement",
  });
  for (const changes of [
    { evidenceId: " " },
    { evidenceKind: undefined },
    { evidenceKind: "unknown" },
    { checks: { ...input.checks, positions_checked: false } },
    { note: " " },
  ]) {
    expect(() =>
      reconciliationConfirmation({ ...input, ...changes }),
    ).toThrow();
  }
  const attempt = retryableWrite();
  const content = reconciliationConfirmation(input);
  const identity = JSON.stringify([1, content]);
  const body = attempt.body(identity, () => ({
    idempotency_key: "first",
    ...content,
  }));
  expect(
    attempt.body(identity, () => ({ idempotency_key: "second", ...content })),
  ).toBe(body);
  expect(
    attempt.body(
      JSON.stringify([
        1,
        reconciliationConfirmation({ ...input, evidenceId: "different" }),
      ]),
      () => ({ idempotency_key: "third" }),
    ),
  ).not.toBe(body);
});
