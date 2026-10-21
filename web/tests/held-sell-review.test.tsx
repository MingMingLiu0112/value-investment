import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { PrivateStateHandle } from "../src/hooks/usePrivateState";
import type { HeldSellReviewRequest } from "../src/services/api";
const { renderToStaticMarkup } = require("react-dom/server");

// The repository uses server rendering for component tests. Retain hook state
// between renders here so deferred requests can race actual control callbacks.
const harness = vi.hoisted(() => ({
  slots: [] as any[],
  index: 0,
  effects: [] as Array<() => void>,
  controls: {} as Record<string, any>,
  review: vi.fn(),
}));
vi.mock("react", async (load) => {
  const actual = await load<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const index = harness.index++;
      if (!(index in harness.slots)) harness.slots[index] = initial;
      return [
        harness.slots[index],
        (value: unknown) => {
          harness.slots[index] = value;
        },
      ];
    },
    useRef: (initial: unknown) => {
      const index = harness.index++;
      return (harness.slots[index] ??= { current: initial });
    },
    useEffect: (effect: () => () => void, deps: unknown[]) => {
      const index = harness.index++;
      const previous = harness.slots[index];
      if (!previous || deps.some((value, i) => value !== previous.deps[i])) {
        harness.effects.push(() => {
          previous?.cleanup?.();
          harness.slots[index] = { deps, cleanup: effect() };
        });
      }
    },
  };
});
vi.mock("@umijs/max", () => ({
  Link: ({ children }: any) => <a>{children}</a>,
}));
vi.mock("../src/services/api", () => ({
  api: { reviewHeldSell: harness.review },
}));
vi.mock("antd", () => ({
  Space: ({ children }: any) => <div>{children}</div>,
  Alert: ({ message }: any) => <p role="alert">{message}</p>,
  Select: (props: any) => {
    harness.controls.intent = props;
    return null;
  },
  InputNumber: (props: any) => {
    harness.controls.quantity = props;
    return null;
  },
  Checkbox: (props: any) => {
    harness.controls.ack = props;
    return null;
  },
  Button: (props: any) => {
    if (props.children === "核验卖出条件") harness.controls.submit = props;
    return <button>{props.children}</button>;
  },
}));
import { HoldingsAttention } from "../src/components/HoldingsAttention";

let state: PrivateStateHandle;
beforeEach(() => {
  harness.slots = [];
  harness.effects = [];
  harness.controls = {};
  harness.review.mockReset();
  state = {
    retry: vi.fn(),
    portfolio: {
      status: "CONNECTED",
      revision: 4,
      positions: [
        {
          symbol: "000333",
          exchange: "SZSE",
          sleeves: [{ sleeve: "CORE_VALUE", quantity: "200" }],
        },
      ],
    },
    risk: { facts: { account_scope: "TEST_ONLY" }, blockers: [] },
    heldContinuity: {
      items: [
        {
          symbol: "000333",
          quantity: "200",
          sellable_quantity: "200",
          review_reasons: [],
          data_gaps: [],
          actionable_decisions: [
            {
              action: "no_order",
              decision_action: "UNASSESSABLE",
              symbol: "000333",
              strategy: "CORE_VALUE",
              decision_reason: "TEST_ONLY",
              blockers: [],
              review_quantity: null,
              broker_execution_permission: false,
              ownership_verified: true,
              held_quantity: "200",
              sellable_quantity: "200",
              entry_thesis_record_sha256: "a".repeat(64),
            },
          ],
        },
      ],
    },
  } as unknown as PrivateStateHandle;
});

function render() {
  harness.index = 0;
  const html = renderToStaticMarkup(
    <HoldingsAttention state={state} decisions={[]} />,
  );
  harness.effects.splice(0).forEach((effect) => effect());
  return html as string;
}
function acknowledge(checked: boolean) {
  harness.controls.ack.onChange({ target: { checked } });
  return render();
}
function prepare() {
  render();
  harness.controls.quantity.onChange(50);
  render();
  acknowledge(true);
}
function response(request: HeldSellReviewRequest) {
  return {
    schema_version: "private-held-sell-review-v1",
    action: "no_order",
    revision: 4,
    ledger_written: false,
    broker_execution_permission: false,
    request: { ...request },
    actionable_decision: {
      ...state.heldContinuity!.items[0].actionable_decisions![0],
      decision_action: request.requested_action,
      review_quantity: request.requested_quantity,
    },
  };
}
function deferred() {
  let resolve!: (value: ReturnType<typeof response>) => void;
  harness.review.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const pending = harness.controls.submit.onClick() as Promise<void>;
  render();
  const request = harness.review.mock.calls[0][0] as HeldSellReviewRequest;
  return { resolve, pending, request };
}

it("renders a positive review only for the exact acknowledged request", async () => {
  prepare();
  const { resolve, pending, request } = deferred();
  expect(request).toEqual({
    schema_version: "private-held-sell-review-request-v1",
    action: "no_order",
    expected_revision: 4,
    account_scope: "TEST_ONLY",
    symbol: "000333",
    exchange: "SZSE",
    sleeve: "CORE_VALUE",
    requested_action: "REDUCE",
    requested_quantity: 50,
    entry_thesis_record_sha256: "a".repeat(64),
    read_and_confirmed: true,
  });
  resolve(response(request));
  await pending;
  expect(render()).toContain("当前条件下复核数量：50");
  expect(acknowledge(false)).not.toContain("当前条件下复核数量：50");
});

it.each([
  ["schema_version", "wrong"],
  ["action", "order"],
  ["expected_revision", 5],
  ["account_scope", "OTHER"],
  ["symbol", "600519"],
  ["exchange", "SSE"],
  ["sleeve", "HOTSPOT_SATELLITE"],
  ["requested_action", "EXIT"],
  ["requested_quantity", 100],
  ["entry_thesis_record_sha256", "b".repeat(64)],
  ["read_and_confirmed", false],
])("rejects an altered echoed %s", async (key, value) => {
  prepare();
  const { resolve, pending, request } = deferred();
  const result = response(request);
  Object.assign(result.request, { [key]: value });
  resolve(result);
  await pending;
  expect(render()).toContain("复核结果与当前持仓版本不一致");
  expect(render()).not.toContain("当前条件下复核数量：");
});

it.each(["missing", "extra", "quantity", "action"])(
  "rejects %s response binding",
  async (fault) => {
    prepare();
    const { resolve, pending, request } = deferred();
    const result = response(request);
    if (fault === "missing") Object.assign(result, { request: undefined });
    if (fault === "extra") Object.assign(result.request, { unbound: true });
    if (fault === "quantity") result.actionable_decision.review_quantity = 100;
    if (fault === "action") result.actionable_decision.decision_action = "EXIT";
    resolve(result);
    await pending;
    expect(render()).toContain("复核结果与当前持仓版本不一致");
    expect(render()).not.toContain("当前条件下复核数量：");
  },
);

it.each(["ack", "quantity", "intent", "revision"])(
  "discards a pending review after %s changes",
  async (change) => {
    prepare();
    const { resolve, pending, request } = deferred();
    if (change === "ack") {
      acknowledge(false);
      acknowledge(true);
    }
    if (change === "quantity") harness.controls.quantity.onChange(100);
    if (change === "intent") harness.controls.intent.onChange("EXIT");
    if (change === "revision") state.portfolio!.revision = 5;
    render();
    resolve(response(request));
    await pending;
    expect(render()).not.toContain("当前条件下复核数量：");
  },
);
