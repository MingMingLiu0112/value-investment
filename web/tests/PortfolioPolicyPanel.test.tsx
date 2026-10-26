import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { PolicyResponse } from "../src/types/api";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const captured = vi.hoisted(() => ({
  fields: [] as Record<string, any>[],
  buttons: [] as Record<string, any>[],
  submit: undefined as
    undefined | ((form: Record<string, unknown>) => Promise<boolean>),
  response: undefined as PolicyResponse | undefined,
  prepare: vi.fn(),
  confirm: vi.fn(),
  retry: vi.fn(),
}));
const reactState = vi.hoisted(() => ({
  use: null as
    | null
    | ((initial: unknown) => [unknown, (next: unknown) => void] | undefined),
}));
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) =>
      reactState.use?.(initial) ?? actual.useState(initial),
  };
});
vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({
    data: captured.response,
    loading: false,
    retry: captured.retry,
  }),
}));
vi.mock("../src/services/api", () => ({
  ApiError: class extends Error {},
  api: {
    policy: vi.fn(),
    preparePolicy: captured.prepare,
    confirmPolicy: captured.confirm,
  },
}));
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  const field = (props: Record<string, any>) => {
    captured.fields.push(props);
    return null;
  };
  const form = Object.assign(
    (props: Record<string, any>) => {
      captured.submit = props.onFinish;
      return React.createElement("div", null, props.children);
    },
    {
      Group: (props: Record<string, any>) =>
        React.createElement("div", null, props.children),
    },
  );
  return {
    ProForm: form,
    ProFormText: field,
    ProFormSelect: field,
    ProFormTextArea: field,
    ProFormDatePicker: field,
    ProFormList: (props: Record<string, any>) =>
      React.createElement("div", null, props.children),
  };
});
vi.mock("antd", async () => {
  const React = await import("react");
  const wrapper = (props: Record<string, any>) =>
    React.createElement("div", null, props.children);
  return {
    Alert: (props: Record<string, any>) =>
      React.createElement("div", null, props.message, props.description),
    Button: (props: Record<string, any>) => {
      captured.buttons.push(props);
      return React.createElement(
        "button",
        { disabled: props.disabled },
        props.children,
      );
    },
    Checkbox: wrapper,
    Space: wrapper,
    Input: { TextArea: wrapper },
    Descriptions: (props: Record<string, any>) =>
      React.createElement(
        "div",
        null,
        props.items.map((row: any) =>
          React.createElement("div", { key: row.key }, row.label, row.children),
        ),
      ),
    Typography: { Title: wrapper, Text: wrapper },
  };
});
vi.mock("../src/components/PositionTable", () => ({
  sleeveLabel: (value: string) => value,
}));
vi.mock("../src/components/RemoteState", async () => {
  const React = await import("react");
  return {
    RemoteState: (props: Record<string, any>) =>
      React.createElement("div", null, props.children),
  };
});
import { PortfolioPolicyPanel } from "../src/components/PortfolioPolicyPanel";

beforeEach(() => {
  captured.fields.length = 0;
  captured.buttons.length = 0;
  captured.prepare
    .mockReset()
    .mockResolvedValue({ action: "no_order", status: "POLICY_PREPARED" });
  captured.confirm.mockReset();
  captured.retry.mockClear();
  captured.response = {
    action: "no_order",
    status: "NOT_CONFIRMED",
    revision: 4,
    policy: null,
    pending_policy: null,
    missing_fields: [],
  };
});

it("renders blank budget/risk controls and saves incomplete input without confirming", async () => {
  const done = vi.fn();
  renderToStaticMarkup(
    React.createElement(PortfolioPolicyPanel, {
      revision: 4,
      fillPending: false,
      onDone: done,
    }),
  );
  expect(
    captured.fields.every((field) => field.initialValue === undefined),
  ).toBe(true);
  expect(
    captured.fields.some((field) =>
      ["path", "sha256", "security_bindings"].includes(field.name),
    ),
  ).toBe(false);
  await captured.submit!({
    investable_assets_cny: "10000",
    financing_allowed: false,
  });
  expect(captured.prepare).toHaveBeenCalledWith(
    expect.objectContaining({
      expected_revision: 4,
      policy: {
        action: "no_order",
        investable_assets_cny: "10000",
        financing_allowed: false,
      },
    }),
  );
  expect(captured.confirm).not.toHaveBeenCalled();
  expect(done).toHaveBeenCalledOnce();
});

it("saves a complete two-sleeve IPS draft without mixing or dropping sleeve budgets", async () => {
  renderToStaticMarkup(
    React.createElement(PortfolioPolicyPanel, {
      revision: 4,
      fillPending: false,
      onDone: vi.fn(),
    }),
  );
  expect(captured.fields.map((field) => field.name)).toEqual(
    expect.arrayContaining([
      ["sleeves", "CORE_VALUE", "cash_cny"],
      ["sleeves", "CORE_VALUE", "risk_budget_cny"],
      ["sleeves", "HOTSPOT_SATELLITE", "cash_cny"],
      ["sleeves", "HOTSPOT_SATELLITE", "risk_budget_cny"],
      ["sleeves", "HOTSPOT_SATELLITE", "single_security_risk_cny"],
    ]),
  );
  expect(
    await captured.submit!({
      investable_assets_cny: "10000",
      core_value_budget_cny: "6000",
      hotspot_budget_cny: "3500",
      cash_reserve_cny: "500",
      minimum_cash_cny: "1000",
      dividend_income_goal_cny: "0",
      time_horizon_years: "5",
      max_single_security_pct: "10",
      max_single_industry_pct: "25",
      hotspot_single_trade_risk_pct: "1",
      max_drawdown_pct: "20",
      max_factor_pct: "30",
      financing_allowed: "DENY",
      risk_tools_allowed: "DENY",
      concentration_allowed: "DENY",
      risk_tolerance: "BALANCED",
      effective_date: "2026-10-19",
      restrictions: "仅限 A 股\n不使用融资",
      sleeves: {
        CORE_VALUE: { cash_cny: "6000", risk_budget_cny: "6000" },
        HOTSPOT_SATELLITE: {
          cash_cny: "3500",
          risk_budget_cny: "3500",
          single_security_risk_cny: "350",
        },
      },
    }),
  ).toBe(true);
  expect(captured.prepare).toHaveBeenCalledWith({
    idempotency_key: expect.any(String),
    expected_revision: 4,
    policy: {
      action: "no_order",
      investable_assets_cny: "10000",
      core_value_budget_cny: "6000",
      hotspot_budget_cny: "3500",
      cash_reserve_cny: "500",
      minimum_cash_cny: "1000",
      dividend_income_goal_cny: "0",
      time_horizon_years: "5",
      max_single_security_pct: "10",
      max_single_industry_pct: "25",
      hotspot_single_trade_risk_pct: "1",
      max_drawdown_pct: "20",
      max_factor_pct: "30",
      financing_allowed: false,
      risk_tools_allowed: false,
      concentration_allowed: false,
      effective_date: "2026-10-19",
      risk_tolerance: "BALANCED",
      restrictions: ["仅限 A 股", "不使用融资"],
      sleeves: {
        CORE_VALUE: { cash_cny: "6000", risk_budget_cny: "6000" },
        HOTSPOT_SATELLITE: {
          cash_cny: "3500",
          risk_budget_cny: "3500",
          single_security_risk_cny: "350",
        },
      },
    },
  });
  expect(captured.confirm).not.toHaveBeenCalled();
});

it("blocks writes when the policy read and current ledger revisions differ or a fill is pending", async () => {
  for (const props of [
    { revision: 5, fillPending: false },
    { revision: 4, fillPending: true },
  ]) {
    renderToStaticMarkup(
      React.createElement(PortfolioPolicyPanel, { ...props, onDone: vi.fn() }),
    );
    expect(await captured.submit!({})).toBe(false);
  }
  expect(captured.prepare).not.toHaveBeenCalled();
});

it("retries the exact IPS save request after a lost response", async () => {
  captured.prepare.mockRejectedValueOnce(new Error("response lost"));
  renderToStaticMarkup(
    React.createElement(PortfolioPolicyPanel, {
      revision: 4,
      fillPending: false,
      onDone: vi.fn(),
    }),
  );
  const form = { investable_assets_cny: "10000" };
  expect(await captured.submit!(form)).toBe(false);
  expect(await captured.submit!(form)).toBe(true);
  expect(captured.prepare.mock.calls[1][0]).toEqual(
    captured.prepare.mock.calls[0][0],
  );
});

it("never confirms an incomplete draft or a complete draft without human acknowledgement", () => {
  captured.response!.pending_policy = {
    policy: { action: "no_order" },
    state_version: 1,
    prepared_record_sha256: "a".repeat(64),
  };
  const html = renderToStaticMarkup(
    React.createElement(PortfolioPolicyPanel, {
      revision: 4,
      fillPending: false,
      onDone: vi.fn(),
    }),
  );
  expect(html).toContain("草稿尚不完整");
  expect(
    captured.buttons.find((button) => button.children === "本人确认 IPS 草稿")
      ?.disabled,
  ).toBe(true);
  captured.response!.pending_policy!.missing_fields = [];
  captured.buttons.length = 0;
  renderToStaticMarkup(
    React.createElement(PortfolioPolicyPanel, {
      revision: 4,
      fillPending: false,
      onDone: vi.fn(),
    }),
  );
  expect(
    captured.buttons.find((button) => button.children === "本人确认 IPS 草稿")
      ?.disabled,
  ).toBe(true);
  expect(captured.confirm).not.toHaveBeenCalled();
});

it("confirms a complete two-sleeve IPS draft only with explicit human acknowledgement", async () => {
  const digest = "b".repeat(64);
  captured.response!.pending_policy = {
    policy: {
      action: "no_order",
      investable_assets_cny: "10000",
      core_value_budget_cny: "6000",
      hotspot_budget_cny: "3500",
      cash_reserve_cny: "500",
      minimum_cash_cny: "1000",
      sleeves: {
        CORE_VALUE: { cash_cny: "6000", risk_budget_cny: "6000" },
        HOTSPOT_SATELLITE: {
          cash_cny: "3500",
          risk_budget_cny: "3500",
          single_security_risk_cny: "350",
        },
      },
    },
    state_version: 1,
    prepared_record_sha256: digest,
    missing_fields: [],
  };
  captured.confirm.mockResolvedValue({
    action: "no_order",
    status: "POLICY_CONFIRMED",
  });
  let hook = 0;
  reactState.use = () => {
    const index = hook++;
    if (index === 2) return ["本人已逐项核对，TEST_ONLY", vi.fn()];
    if (index === 3) return [true, vi.fn()];
    return undefined;
  };
  const done = vi.fn();
  try {
    renderToStaticMarkup(
      React.createElement(PortfolioPolicyPanel, {
        revision: 4,
        fillPending: false,
        onDone: done,
      }),
    );
    const confirmButton = captured.buttons.find(
      (button) => button.children === "本人确认 IPS 草稿",
    );
    expect(confirmButton?.disabled).toBe(false);
    await confirmButton!.onClick();
  } finally {
    reactState.use = null;
  }
  expect(captured.confirm).toHaveBeenCalledWith({
    idempotency_key: expect.any(String),
    expected_revision: 4,
    prepared_record_sha256: digest,
    confirmation_note: "本人已逐项核对，TEST_ONLY",
    confirmed_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
  });
  expect(done).toHaveBeenCalledOnce();
});
