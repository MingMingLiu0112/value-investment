import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
const response = vi.hoisted(() => ({
  loading: false,
  error: undefined,
  retry: () => {},
  data: {
    status: "MOCK_DRAFT_PENDING_HUMAN_REVIEW",
    mode: "MOCK",
    ledger_source: "TEST_ONLY",
    items: [
      {
        manual_fill: {
          transaction_id: "TEST_ONLY",
          symbol: "000333",
          side: "BUY",
          quantity: "100",
          price_cny: "10",
        },
        differences: [
          {
            field: "invalidation_price",
            saved_reference_cny: "9.9",
            fill_minus_reference_cny: "0.1",
          },
        ],
        evidence_gaps: [
          "UNLINKED_FILL_NO_RESEARCH_APPROVAL_INFERRED",
          "TRADE_TIME_PLAN_AND_DATA_AVAILABILITY_NOT_PROVEN",
        ],
      },
    ],
  } as any,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: () => response }));
import { PrivateRetrospectivePanel } from "../src/components/PrivateRetrospectivePanel";

const originalData = structuredClone(response.data);
beforeEach(() => {
  response.data = structuredClone(originalData);
});

it("never requests or invents review dates without confirmed trades", () => {
  expect(renderToStaticMarkup(<PrivateRetrospectivePanel trades={[]} />)).toBe(
    "",
  );
});

it("shows private synthetic facts and uncertainty without alleging a violation", () => {
  const html = renderToStaticMarkup(
    <PrivateRetrospectivePanel
      trades={[{ trade_date: "2026-10-14" } as any]}
    />,
  );
  expect(html).toContain("复盘成交日");
  expect(html).toContain("TEST_ONLY 隔离台账");
  expect(html).toContain("失效参考");
  expect(html).toContain("不推断其已获批准");
  expect(html).toContain("尚不能证明实际成交前已知该计划与数据");
  expect(html).not.toContain("交易已获批准");
});

it("does not turn a missing journal into a real-account or no-trades claim", () => {
  response.data = {
    status: "BLOCKED_PRIVATE_INPUT",
    ledger_source: "MISSING_PRIVATE_INPUT",
    items: [],
  };
  const html = renderToStaticMarkup(
    <PrivateRetrospectivePanel
      trades={[{ trade_date: "2026-10-14" } as any]}
    />,
  );
  expect(html).toContain("私人台账尚不可用，无法复盘");
  expect(html).not.toContain("依据本人确认的台账");
  expect(html).not.toContain("该日没有已确认成交");
});

it.each([0, 100, null])(
  "shows retained recording evidence and original review quantity %s without claiming pretrade",
  (quantity) => {
    Object.assign(response.data.items[0], {
      recording_time_risk_status: "AVAILABLE_RECORDING_TIME_ONLY",
      recording_time_personal_risk: {
        status: "SERVER_VERIFIED_RECORDING_TIME_RISK",
        risk_status: "BLOCKED_PRIVATE_INPUT",
        review_quantity: quantity,
      },
    });
    const html = renderToStaticMarkup(
      <PrivateRetrospectivePanel
        trades={[{ trade_date: "2026-10-22" } as any]}
      />,
    );
    expect(html).toContain("已保留；原风险状态：私人风险输入不完整");
    expect(html).not.toContain("BLOCKED_PRIVATE_INPUT");
    expect(html).toContain(`当时复核股数：${quantity ?? "未提供"}`);
    expect(html).toContain("不能证明成交前已核验");
    expect(html).toContain("不推断其已获批准");
  },
);

it.each([
  ["RECORDING_TIME_PERSONAL_RISK_MISSING", "未保留可核验的录入时个人风险"],
  ["RECORDING_TIME_PERSONAL_RISK_INVALID", "录入时个人风险留存校验未通过"],
])("shows unavailable evidence honestly (%s)", (gap, label) => {
  Object.assign(response.data.items[0], {
    recording_time_risk_status: "UNAVAILABLE",
    recording_time_personal_risk: null,
    evidence_gaps: [gap],
  });
  const html = renderToStaticMarkup(
    <PrivateRetrospectivePanel
      trades={[{ trade_date: "2026-10-22" } as any]}
    />,
  );
  expect(html).toContain("未保留可核验结果");
  expect(html).toContain(label);
  expect(html).toContain("不能证明成交前已核验");
  expect(html).not.toContain("当时复核股数");
});

it("shows the newly confirmed fill evidence on the refreshed retrospective", () => {
  expect(renderToStaticMarkup(<PrivateRetrospectivePanel trades={[]} />)).toBe(
    "",
  );
  Object.assign(response.data.items[0], {
    recording_time_risk_status: "AVAILABLE_RECORDING_TIME_ONLY",
    recording_time_personal_risk: {
      status: "SERVER_VERIFIED_RECORDING_TIME_RISK",
      risk_status: "BLOCKED_PRIVATE_INPUT",
      review_quantity: 0,
    },
  });
  const html = renderToStaticMarkup(
    <PrivateRetrospectivePanel
      trades={[{ trade_date: "2026-10-22" } as any]}
    />,
  );
  expect(html).toContain("成交复盘草稿");
  expect(html).toContain("已保留；原风险状态：私人风险输入不完整");
  expect(html).toContain("当时复核股数：0");
});
