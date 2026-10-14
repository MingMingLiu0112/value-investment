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
