import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};

const captured = vi.hoisted(() => ({
  list: {} as Record<string, any>,
  submit: undefined as
    undefined | ((form: Record<string, unknown>) => Promise<void>),
  initialize: vi.fn(),
}));
vi.mock("../src/services/api", () => ({
  ApiError: class extends Error {},
  api: { initializePortfolio: captured.initialize },
}));
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  const field = () => null;
  return {
    ProForm: (props: Record<string, any>) => {
      captured.submit = props.onFinish;
      return React.createElement("div", null, props.children);
    },
    ProFormList: (props: Record<string, any>) => {
      captured.list = props;
      return null;
    },
    ProFormText: field,
    ProFormSelect: field,
    ProFormTextArea: field,
    ProFormDatePicker: field,
    ProFormDateTimePicker: field,
  };
});
vi.mock("antd", () => ({ Alert: () => null }));
import { PortfolioSetupForm } from "../src/components/PortfolioSetupForm";

beforeEach(() => vi.clearAllMocks());

it.each([undefined, []])(
  "submits a cash-only account with explicit empty holdings (%s)",
  async (holdings) => {
    const onDone = vi.fn();
    renderToStaticMarkup(<PortfolioSetupForm onDone={onDone} />);
    expect(captured.list.min).toBe(0);
    expect(captured.list.initialValue).toEqual([]);
    await captured.submit!({
      account_scope: "synthetic-cash-account",
      cash_cny: "10000",
      as_of: "2026-10-14",
      confirmed_at: "2026-10-14T10:00:00+08:00",
      confirmation_note: "Synthetic test confirmation",
      holdings,
    });
    expect(captured.initialize).toHaveBeenCalledOnce();
    expect(captured.initialize.mock.calls[0][0]).toMatchObject({
      cash_cny: "10000",
      holdings: [],
      sleeve_allocations: {},
      policy: {},
      confirmation_note: "Synthetic test confirmation",
    });
    expect(onDone).toHaveBeenCalledOnce();
  },
);
