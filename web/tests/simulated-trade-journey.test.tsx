import React from "react";
import { expect, it } from "vitest";
import {
  SimulatedTradeJourney,
  verifiedSimulatedJourney,
} from "../src/components/SimulatedTradeJourney";
const { renderToStaticMarkup } = require("react-dom/server");

const packet = () => ({
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
  ].map((label) => ({ label })),
  checks: {
    confirmation_idempotency: true,
    restart_equality: true,
    same_day_sell_rejected: true,
    temporary_journal_removed: true,
  },
});
it("does not run on render or present a scripted account as live", () => {
  const html = renderToStaticMarkup(<SimulatedTradeJourney />);
  expect(html).toContain("SIMULATED");
  expect(html).toContain("不是实盘建议");
  expect(html).toContain("不读取或修改私人账户");
  expect(html).not.toContain("10170");
});
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
