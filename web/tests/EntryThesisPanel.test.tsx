import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { EntryThesisView } from "../src/services/entryThesis";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactNode) => string;
};
const control = vi.hoisted(() => ({
  data: undefined as EntryThesisView | undefined,
  states: {} as Record<number, unknown>,
  index: 0,
  buttons: [] as Array<{
    children?: React.ReactNode;
    disabled?: boolean;
    onClick?: () => Promise<void>;
  }>,
  confirm: vi.fn(),
  revoke: vi.fn(),
  retry: vi.fn(),
  done: vi.fn(),
}));
vi.mock("react", async (load) => {
  const actual = await load<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const index = control.index++;
      const pair = actual.useState(initial);
      return index in control.states ? [control.states[index], pair[1]] : pair;
    },
  };
});
vi.mock("../src/hooks/useApi", () => ({
  useApi: () => ({ data: control.data, loading: false, retry: control.retry }),
}));
vi.mock("../src/services/api", () => ({
  api: {
    entryThesis: vi.fn(),
    confirmEntryThesis: control.confirm,
    revokeEntryThesis: control.revoke,
  },
}));
vi.mock("antd", async () => {
  const React = await import("react");
  const wrapper = ({ children }: { children?: React.ReactNode }) =>
    React.createElement("div", null, children);
  return {
    Alert: ({
      message,
      description,
    }: {
      message: string;
      description: string;
    }) => React.createElement("p", null, message, description),
    Button: (props: (typeof control.buttons)[number]) => {
      control.buttons.push(props);
      return React.createElement(
        "button",
        { disabled: props.disabled },
        props.children,
      );
    },
    Checkbox: wrapper,
    Space: wrapper,
    Input: { TextArea: () => React.createElement("textarea") },
    Select: () => React.createElement("select"),
  };
});
import { EntryThesisPanel } from "../src/components/EntryThesisPanel";

beforeEach(() => {
  control.index = 0;
  control.buttons = [];
  control.states = {};
  vi.clearAllMocks();
  control.confirm.mockResolvedValue({
    action: "no_order",
    status: "PERSONAL_ENTRY_THESIS_CONFIRMED",
  });
  control.data = {
    action: "no_order",
    status: "AVAILABLE",
    revision: 3,
    account_scope: "TEST_ONLY_UI",
    items: [
      {
        fill_record_sha256: "a".repeat(64),
        transaction_id: "TEST_ONLY-buy",
        symbol: "600019",
        exchange: "SSE",
        sleeve: "HOTSPOT_SATELLITE",
        quantity: "100",
        remaining_quantity: "100",
        trade_date: "2026-10-19",
        price_cny: "6.05",
        current_binding: null,
        history: [],
        candidate_plans: [],
      },
    ],
  };
});

function render(revision = 3) {
  control.index = 0;
  return renderToStaticMarkup(
    <EntryThesisPanel revision={revision} onDone={control.done} />,
  );
}

it("does not invent a confirmed buy for an initial or disconnected holding", () => {
  control.data!.items = [];
  expect(render()).toContain("初始持仓不会被伪造成历史成交");
  expect(control.confirm).not.toHaveBeenCalled();
});

it("shows saved retrospective rationale and its boundary", () => {
  control.states[0] = "a".repeat(64);
  control.data!.items[0].current_binding = {
    record_sha256: "b".repeat(64),
    recorded_at: "2026-10-21T00:00:00Z",
    kind: "PERSONAL_ENTRY_THESIS_CONFIRMED",
    binding_mode: "HISTORICAL_RECONSTRUCTION",
    confirmation_note: "TEST_ONLY",
    reconstruction: {
      thesis: "Original user explanation",
      hold_logic: "Hold explanation",
      invalidation_conditions: ["Thesis breaker"],
    },
  };
  const html = render();
  expect(html).toContain("Original user explanation");
  expect(html).toContain("Hold explanation");
  expect(html).toContain("Thesis breaker");
  expect(html).toContain("事后补录");
});

it("requires acknowledgement before saving and rejects a stale revision", async () => {
  control.states[0] = "a".repeat(64);
  render(4);
  const save = control.buttons.find(
    (button) => button.children === "保存本人确认",
  )!;
  expect(save.disabled).toBe(true);
  await save.onClick?.();
  expect(control.confirm).not.toHaveBeenCalled();
});

it("submits a single acknowledged retrospective write even on double click", async () => {
  Object.assign(control.states, {
    0: "a".repeat(64),
    3: "TEST_ONLY thesis",
    4: "TEST_ONLY hold",
    5: "TEST_ONLY breaker",
    6: "TEST_ONLY confirmation",
    7: true,
  });
  render();
  const save = control.buttons.find(
    (button) => button.children === "保存本人确认",
  )!;
  expect(save.disabled).toBe(false);
  await Promise.all([save.onClick?.(), save.onClick?.()]);
  expect(control.confirm).toHaveBeenCalledTimes(1);
  const payload = control.confirm.mock.calls[0][0];
  expect(payload.read_and_confirmed).toBe(true);
  expect(payload.binding_mode).toBe("HISTORICAL_RECONSTRUCTION");
  expect(payload).not.toHaveProperty("authenticated_subject");
  expect(payload).not.toHaveProperty("confirmed_at");
  expect(control.done).toHaveBeenCalledTimes(1);
});
