import React from "react";
import { beforeEach, expect, it, vi } from "vitest";

const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};

const captured = vi.hoisted(() => ({
  fields: [] as Record<string, any>[],
  submit: undefined as
    undefined | ((form: Record<string, unknown>) => Promise<void>),
  prepare: vi.fn().mockResolvedValue({}),
}));
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  const field = (props: Record<string, any>) => {
    captured.fields.push(props);
    return null;
  };
  return {
    ProForm: (props: Record<string, any>) => {
      captured.submit = props.onFinish;
      return React.createElement("div", null, props.children);
    },
    ProFormText: field,
    ProFormSelect: field,
    ProFormTextArea: field,
    ProFormDatePicker: field,
    ProFormDateTimePicker: field,
  };
});

it("detaches candidate judgment when the actual security or sleeve changes", async () => {
  for (const changed of [{ symbol: "000001" }, { sleeve: "CORE_VALUE" }]) {
    renderToStaticMarkup(
      React.createElement(FillPanel, {
        revision: 4,
        draft: null,
        onDone: vi.fn(),
        initialSymbol: "600887",
        initialSleeve: "HOTSPOT_SATELLITE",
        initialDecisionId: "hotspot-600887",
        initialResearchVersion: "company-version",
      }),
    );
    await captured.submit!({
      transaction_id: "TEST",
      side: "SELL",
      symbol: "600887",
      sleeve: "HOTSPOT_SATELLITE",
      exchange: "SSE",
      quantity: "100",
      price_cny: "20",
      fees_cny: "5",
      trade_date: "2026-10-14",
      ...changed,
    });
    expect(captured.prepare.mock.lastCall![0].fill).toMatchObject({
      decision_id: null,
      research_version: null,
    });
  }
});

it("does not submit a buy without explicit settlement inputs", async () => {
  renderToStaticMarkup(
    React.createElement(FillPanel, {
      revision: 4,
      draft: null,
      onDone: vi.fn(),
    }),
  );
  expect(await captured.submit!({ side: "BUY" })).toBe(false);
  expect(captured.prepare).not.toHaveBeenCalled();
});
vi.mock("../src/services/api", () => ({
  ApiError: class extends Error {},
  api: { prepareFill: captured.prepare },
}));
import {
  FillPanel,
  fillContextFromSearch,
  failureMessage,
  clearRejectedAttempt,
} from "../src/components/FillPanel";
import { retryableWrite } from "../src/components/PrivateRiskContext";
import { ApiError } from "../src/services/api";

it.each([
  [
    "confirmation requires a timezone-aware time after trade",
    "确认时间不能早于实际成交日期",
  ],
  ["trade date precedes confirmed state", "成交日期早于账户核对日期"],
  ["insufficient sellable shares", "T+1"],
  ["BUY requires an explicit later sell session", "最早可卖交易日"],
  ["BUY requires an explicit trading unit dividing quantity", "交易单位"],
  ["SELL cannot specify next sell session", "卖出无需填写"],
])(
  "translates settlement refusal %s without changing submission eligibility",
  (detail, expected) => {
    const error = Object.assign(
      new ApiError(422, "VALIDATION_FAILED", detail),
      {
        code: "VALIDATION_FAILED",
        detail,
      },
    );
    expect(failureMessage(error, "失败")).toContain(expected);
  },
);

it("keeps unknown API failures visible", () => {
  const error = Object.assign(new ApiError(409, "UNKNOWN", "new failure"), {
    code: "UNKNOWN",
    detail: "new failure",
  });
  expect(failureMessage(error, "失败")).toBe("UNKNOWN：new failure");
});

beforeEach(() => {
  captured.fields.length = 0;
  captured.prepare.mockClear();
});

it("renews rejected requests but preserves uncertain outcomes", () => {
  const attempt = retryableWrite();
  const old = attempt.body("confirm", () => ({ confirmed_at: "yesterday" }));
  for (const cause of [
    new Error("response lost"),
    Object.assign(new ApiError(503, "FAIL", ""), { status: 503 }),
  ]) {
    clearRejectedAttempt(attempt, cause);
    expect(attempt.body("confirm", () => ({ confirmed_at: "today" }))).toBe(
      old,
    );
  }
  const rejection = Object.assign(new ApiError(422, "INVALID", "future"), {
    status: 422,
  });
  clearRejectedAttempt(attempt, rejection);
  expect(attempt.body("confirm", () => ({ confirmed_at: "today" }))).toEqual({
    confirmed_at: "today",
  });
});

it("reuses a lost-response request and suppresses concurrent preparation", async () => {
  renderToStaticMarkup(
    React.createElement(FillPanel, {
      revision: 4,
      draft: null,
      onDone: vi.fn(),
    }),
  );
  const form = {
    transaction_id: "TEST_ONLY_RETRY",
    side: "SELL",
    sleeve: "CORE_VALUE",
    symbol: "000333",
    exchange: "SZSE",
    quantity: "100",
    price_cny: "10",
    fees_cny: "1",
    trade_date: "2026-10-15",
  };
  let reject!: (reason: Error) => void;
  captured.prepare.mockImplementationOnce(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      }),
  );
  const first = captured.submit!(form);
  expect(await captured.submit!(form)).toBe(false);
  expect(captured.prepare).toHaveBeenCalledTimes(1);
  reject(new Error("response lost"));
  expect(await first).toBe(false);
  const original = captured.prepare.mock.calls[0][0];
  await captured.submit!(form);
  expect(captured.prepare.mock.calls[1][0]).toEqual(original);
  await captured.submit!({ ...form, quantity: "200" });
  expect(captured.prepare.mock.calls[2][0].idempotency_key).not.toBe(
    original.idempotency_key,
  );
});

it("reads candidate identity and strategy without accepting execution hints", () => {
  expect(
    fillContextFromSearch(
      "?symbol=600887&strategy=hotspot&decision_id=d1&research_version=v5&price_cny=25&quantity=100",
    ),
  ).toEqual({
    symbol: "600887",
    strategy: "HOTSPOT_SATELLITE",
    decision_id: "d1",
    research_version: "v5",
  });
  expect(
    fillContextFromSearch("?symbol=bad&strategy=bad").symbol,
  ).toBeUndefined();
  expect(fillContextFromSearch("?strategy=CORE_VALUE").strategy).toBe(
    "CORE_VALUE",
  );
});

it("requires actual execution inputs and submits the unchanged research reference", async () => {
  const done = vi.fn();
  renderToStaticMarkup(
    React.createElement(FillPanel, {
      revision: 4,
      draft: null,
      onDone: done,
      initialSymbol: "600887",
      initialSleeve: "HOTSPOT_SATELLITE",
      initialDecisionId: "d1",
      initialResearchVersion: "published-v5",
    }),
  );
  for (const name of ["price_cny", "quantity", "fees_cny", "trade_date"]) {
    const field = captured.fields.find((item) => item.name === name)!;
    expect(field.initialValue).toBeUndefined();
    expect(
      field.rules.some((rule: Record<string, unknown>) => rule.required),
    ).toBe(true);
  }
  expect(
    captured.fields.find((item) => item.name === "side")?.initialValue,
  ).toBeUndefined();
  expect(
    captured.fields.find((item) => item.name === "trading_unit")?.initialValue,
  ).toBeUndefined();
  await captured.submit!({
    transaction_id: "TEST",
    side: "BUY",
    sleeve: "HOTSPOT_SATELLITE",
    symbol: "600887",
    exchange: "SSE",
    quantity: "100",
    price_cny: "20",
    fees_cny: "0",
    trade_date: "2026-10-12",
    next_sell_session: "2026-10-13",
    trading_unit: "100",
  });
  expect(captured.prepare.mock.calls[0][0]).toMatchObject({
    expected_revision: 4,
    fill: {
      symbol: "600887",
      sleeve: "HOTSPOT_SATELLITE",
      decision_id: "d1",
      research_version: "published-v5",
      price_cny: "20",
      quantity: "100",
      fees_cny: "0",
      trade_date: "2026-10-12",
    },
  });
  expect(done).toHaveBeenCalledOnce();
});
