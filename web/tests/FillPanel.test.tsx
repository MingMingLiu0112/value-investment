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
  alerts: [] as Record<string, any>[],
  change: undefined as undefined | ((changed: Record<string, unknown>) => void),
  checkbox: undefined as Record<string, any> | undefined,
  buttons: [] as Record<string, any>[],
  confirm: vi.fn().mockResolvedValue({}),
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
vi.mock("@ant-design/pro-components", async () => {
  const React = await import("react");
  const field = (props: Record<string, any>) => {
    captured.fields.push(props);
    return null;
  };
  return {
    ProForm: (props: Record<string, any>) => {
      captured.submit = props.onFinish;
      captured.change = props.onValuesChange;
      return React.createElement("div", null, props.children);
    },
    ProFormText: field,
    ProFormSelect: field,
    ProFormTextArea: field,
    ProFormDatePicker: field,
    ProFormDateTimePicker: field,
  };
});
vi.mock("antd", async () => {
  const React = await import("react");
  const wrapper = (props: Record<string, any>) =>
    React.createElement("div", null, props.children);
  return {
    Checkbox: (props: Record<string, any>) => {
      captured.checkbox = props;
      return wrapper(props);
    },
    Alert: (props: Record<string, any>) => {
      captured.alerts.push(props);
      return React.createElement(
        "div",
        null,
        props.message,
        props.description,
        props.action,
      );
    },
    Button: (props: Record<string, any>) => {
      captured.buttons.push(props);
      return React.createElement(
        "button",
        { disabled: props.disabled },
        props.children,
      );
    },
    Descriptions: (props: Record<string, any>) =>
      React.createElement(
        "div",
        null,
        (props.items ?? []).map((item: Record<string, any>) =>
          React.createElement("div", { key: item.key }, item.children),
        ),
      ),
    Input: Object.assign(wrapper, { TextArea: wrapper }),
    Table: () => null,
    Popconfirm: wrapper,
    Space: wrapper,
    Typography: { Title: wrapper, Text: wrapper },
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
  const exchange = captured.fields.find((item) => item.name === "exchange")!;
  expect(exchange.options.map((item: { value: string }) => item.value)).toEqual(
    ["SSE", "SZSE"],
  );
  expect(await captured.submit!({ side: "BUY" })).toBe(false);
  expect(captured.prepare).not.toHaveBeenCalled();
});
vi.mock("../src/services/api", () => ({
  ApiError: class extends Error {},
  api: { prepareFill: captured.prepare, confirmFill: captured.confirm },
}));
import {
  FillPanel,
  fillBudgetWarning,
  fillContextFromSearch,
  fillFailure,
  failureMessage,
  clearRejectedAttempt,
} from "../src/components/FillPanel";

it("explains a recorded broker fill exceeding a sleeve budget without pretending rollback", () => {
  expect(
    fillBudgetWarning({
      sleeve_cash_review: { blockers: ["SLEEVE_CASH_OVERDRAWN"] },
    }),
  ).toContain("真实成交已记录");
  expect(
    fillBudgetWarning({ sleeve_cash_review: { blockers: [] } }),
  ).toBeUndefined();
  expect(fillBudgetWarning(undefined)).toBeUndefined();
});
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
  captured.alerts.length = 0;
  captured.prepare.mockClear();
  captured.checkbox = undefined;
  captured.buttons = [];
  captured.confirm.mockClear();
});

it("classifies VERSION_CONFLICT as a dedicated ledger refresh requirement", () => {
  const conflict = Object.assign(
    new ApiError(409, "VERSION_CONFLICT", "当前 revision 为 7，请求为 4"),
    {
      status: 409,
      code: "VERSION_CONFLICT",
      detail: "当前 revision 为 7，请求为 4",
    },
  );
  expect(fillFailure(conflict, "生成草稿失败")).toEqual({
    message: "VERSION_CONFLICT：当前 revision 为 7，请求为 4",
    refreshRequired: true,
  });
  expect(fillFailure(new Error("response lost"), "生成草稿失败")).toEqual({
    message: "response lost",
    refreshRequired: false,
  });
});

it("renders a dedicated ledger refresh action for VERSION_CONFLICT", () => {
  const refresh = vi.fn();
  reactState.use = (initial) =>
    initial === undefined
      ? [
          {
            message: "VERSION_CONFLICT：当前 revision 已变化",
            refreshRequired: true,
          },
          vi.fn(),
        ]
      : undefined;
  try {
    renderToStaticMarkup(
      React.createElement(FillPanel, {
        revision: 4,
        draft: null,
        onDone: refresh,
      }),
    );
  } finally {
    reactState.use = null;
  }
  const alert = captured.alerts.find((item) => item.message === "未能生成草稿");
  expect(alert?.description).toContain("VERSION_CONFLICT");
  const action = alert?.action as React.ReactElement<{
    onClick: () => void;
    children?: React.ReactNode;
  }>;
  expect(action.props.children).toBe("刷新台账");
  action.props.onClick();
  expect(refresh).toHaveBeenCalledOnce();
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

const riskSelection = {
  symbol: "600887",
  sleeve: "HOTSPOT_SATELLITE" as const,
  revision: 4,
  assumptions: { buy_fee_fraction: "0.0003", gap_stress_cny: "0.5" },
};
const buyForm = {
  transaction_id: "TEST_ONLY_RECORDING_RISK",
  side: "BUY",
  sleeve: "HOTSPOT_SATELLITE",
  symbol: "600887",
  exchange: "SSE",
  quantity: "100",
  price_cny: "20",
  fees_cny: "5",
  trade_date: "2026-10-21",
  next_sell_session: "2026-10-22",
  trading_unit: "100",
};

function renderRiskForm() {
  const slots: unknown[] = [];
  let index = 0;
  reactState.use = (initial) => {
    const slot = index++;
    if (!(slot in slots)) slots[slot] = initial;
    return [
      slots[slot],
      (next) => {
        slots[slot] = typeof next === "function" ? next(slots[slot]) : next;
      },
    ];
  };
  const render = (selection = riskSelection, revision = 4) => {
    index = 0;
    renderToStaticMarkup(
      <FillPanel
        revision={revision}
        draft={null}
        onDone={vi.fn()}
        initialSymbol="600887"
        initialSleeve="HOTSPOT_SATELLITE"
        riskAssumptions={selection}
      />,
    );
  };
  render();
  captured.change!({ side: "BUY" });
  render();
  return render;
}

it("requires explicit opt-in and sends only reused assumptions for the matching BUY", async () => {
  try {
    const render = renderRiskForm();
    expect(captured.checkbox?.checked).toBe(false);
    expect(captured.checkbox?.disabled).toBe(false);
    await captured.submit!(buyForm);
    expect(captured.prepare.mock.lastCall![0]).not.toHaveProperty(
      "risk_preview",
    );
    captured.checkbox!.onChange({ target: { checked: true } });
    render();
    await captured.submit!(buyForm);
    expect(captured.prepare.mock.lastCall![0].risk_preview).toEqual({
      assumptions: riskSelection.assumptions,
    });
  } finally {
    reactState.use = null;
  }
});

it.each([
  ["SELL", { side: "SELL" }],
  ["other security", { symbol: "000333" }],
  ["other sleeve", { sleeve: "CORE_VALUE" }],
])("does not attach buy-risk assumptions to %s", async (_, changed) => {
  try {
    const render = renderRiskForm();
    captured.checkbox!.onChange({ target: { checked: true } });
    render();
    await captured.submit!({ ...buyForm, ...changed });
    expect(captured.prepare.mock.lastCall![0]).not.toHaveProperty(
      "risk_preview",
    );
  } finally {
    reactState.use = null;
  }
});

it("clears consent on identity edits and does not reuse a replaced selection or old revision", async () => {
  try {
    const render = renderRiskForm();
    captured.checkbox!.onChange({ target: { checked: true } });
    render();
    captured.change!({ symbol: "000333" });
    captured.change!({ symbol: "600887" });
    render();
    expect(captured.checkbox?.checked).toBe(false);
    captured.checkbox!.onChange({ target: { checked: true } });
    render({
      ...riskSelection,
      assumptions: { ...riskSelection.assumptions, buy_fee_fraction: "0.001" },
    });
    await captured.submit!(buyForm);
    expect(captured.prepare.mock.lastCall![0]).not.toHaveProperty(
      "risk_preview",
    );
    render(riskSelection, 5);
    expect(captured.checkbox?.disabled).toBe(true);
    await captured.submit!(buyForm);
    expect(captured.prepare.mock.lastCall![0]).not.toHaveProperty(
      "risk_preview",
    );
  } finally {
    reactState.use = null;
  }
});

it("keeps a failed optional capture visible without blocking the actual fill draft", async () => {
  const done = vi.fn();
  const onPreparedRisk = vi.fn();
  const outcome = {
    status: "UNAVAILABLE",
    reason: "MATCHING_PUBLIC_JUDGMENT_UNAVAILABLE",
  };
  captured.prepare.mockResolvedValueOnce({
    record_sha256: "prepared",
    personal_risk_capture: outcome,
  });
  renderToStaticMarkup(
    <FillPanel
      revision={4}
      draft={null}
      onDone={done}
      onPreparedRisk={onPreparedRisk}
    />,
  );
  await captured.submit!(buyForm);
  expect(done).toHaveBeenCalledOnce();
  expect(onPreparedRisk).toHaveBeenCalledWith({
    prepared: "prepared",
    outcome,
  });
  const html = renderToStaticMarkup(
    <FillPanel
      revision={5}
      onDone={vi.fn()}
      preparedRisk={{ prepared: "prepared", outcome }}
      draft={{
        status: "DRAFT_UNRECONFIRMED",
        prepared_record_sha256: "prepared",
        fill: buyForm,
        cash_cny: "100",
        realized_pnl_cny: "0",
        positions: [],
      }}
    />,
  );
  expect(html).toContain("录入时风险核验未能保存");
  expect(html).toContain("不证明成交前已核验");
  expect(html).toContain("确认");
});

it.each([{ blockers: [] }, { blockers: ["TEST_ONLY_PLAN_NOT_FORMAL"] }])(
  "reads the retained server capture on draft reload (%j)",
  ({ blockers }) => {
    const html = renderToStaticMarkup(
      <FillPanel
        revision={5}
        onDone={vi.fn()}
        draft={{
          status: "DRAFT_UNRECONFIRMED",
          prepared_record_sha256: "prepared",
          fill: {
            ...buyForm,
            judgment_snapshot: {
              personal_risk_capture: {
                status: "SERVER_VERIFIED_RECORDING_TIME_RISK",
                blockers,
              },
            },
          },
          cash_cny: "100",
          realized_pnl_cny: "0",
          positions: [],
        }}
      />,
    );
    expect(html).toContain(
      blockers.length ? "存在阻断项" : "录入时风险核验可用",
    );
    expect(html).toContain("不证明成交前已核验");
  },
);

it("translates capture failures and hides unknown codes and path details", () => {
  const html = renderToStaticMarkup(
    <FillPanel
      revision={5}
      onDone={vi.fn()}
      preparedRisk={{
        prepared: "prepared",
        outcome: {
          status: "UNAVAILABLE",
          reason: "RISK_CAPTURE_CURRENT_SOURCE_CHANGED:D:/private/ledger.json",
          blockers: ["UNKNOWN_CAPTURE:D:/private/account.json"],
        },
      }}
      draft={{
        status: "DRAFT_UNRECONFIRMED",
        prepared_record_sha256: "prepared",
        fill: buyForm,
        cash_cny: "100",
        realized_pnl_cny: "0",
        positions: [],
      }}
    />,
  );
  expect(html).toContain("风险来源已变化，需重新核验");
  expect(html).toContain("录入时风险资料未能核验");
  expect(html).not.toContain("RISK_CAPTURE_");
  expect(html).not.toContain("UNKNOWN_CAPTURE");
  expect(html).not.toContain("D:/private");
});

it("still confirms the actual fill and refreshes after optional capture failure", async () => {
  const refreshed = vi.fn();
  reactState.use = (initial) =>
    initial === "" ? ["已核对隔离成交单", vi.fn()] : undefined;
  try {
    renderToStaticMarkup(
      <FillPanel
        revision={5}
        onDone={refreshed}
        preparedRisk={{
          prepared: "prepared",
          outcome: {
            status: "UNAVAILABLE",
            reason: "RISK_CAPTURE_PROVIDER_UNAVAILABLE",
          },
        }}
        draft={{
          status: "DRAFT_UNRECONFIRMED",
          prepared_record_sha256: "prepared",
          fill: buyForm,
          cash_cny: "100",
          realized_pnl_cny: "0",
          positions: [],
        }}
      />,
    );
    const confirm = captured.buttons.find(
      (button) => button.children === "确认成交",
    )!;
    expect(confirm.disabled).toBe(false);
    await confirm.onClick();
    expect(captured.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_revision: 5,
        prepared_record_sha256: "prepared",
      }),
    );
    expect(refreshed).toHaveBeenCalledOnce();
  } finally {
    reactState.use = null;
  }
});
