import { describe, expect, it } from "vitest";
import { ApiError } from "../src/services/api";
import { privateStateFrom } from "../src/utils/privateState";
import type { PortfolioResponse, RiskResponse } from "../src/types/api";

function notConnectedPortfolio(): PortfolioResponse {
  return {
    action: "no_order",
    status: "NOT_CONNECTED",
    revision: 0,
    as_of: null,
    cash_cny: null,
    realized_pnl_cny: null,
    positions: [],
    trades: [],
    policy: null,
    pending_draft: null,
    latest_snapshot: null,
    reconciliation: null,
    valuation: { status: "NOT_CONNECTED", reason: "尚未确认真实私人持仓" },
    blockers: ["PRIVATE_PORTFOLIO_NOT_CONNECTED", "PRICE_NOT_ADMITTED"],
  };
}

function connectedPortfolio(): PortfolioResponse {
  return {
    ...notConnectedPortfolio(),
    status: "CONNECTED",
    revision: 4,
    as_of: "2026-10-01",
    cash_cny: "50000",
    valuation: { status: "PRICE_NOT_ADMITTED", reason: "尚未接入经核验收盘价" },
    blockers: ["PRICE_NOT_ADMITTED"],
  };
}

function riskResponse(
  status: string,
  blockers: string[],
  engineBlockers: string[] = [],
): RiskResponse {
  return {
    action: "no_order",
    status,
    blockers,
    engine: engineBlockers.length
      ? {
          schema_version: "dual-sleeve-risk-report.v1",
          action: "no_order",
          status: "BLOCKED_PRIVATE_INPUT",
          blockers: engineBlockers,
          sleeves: null,
          trade_eligible: false,
          acceptance_authority: "human",
        }
      : null,
    facts: null,
  };
}

describe("privateStateFrom", () => {
  it("maps an unauthorized session to LOCKED, not NOT_CONNECTED", () => {
    const view = privateStateFrom({
      error: new ApiError(401, "LOCAL_AUTHORIZATION_REQUIRED", "unlock first"),
    });
    expect(view.kind).toBe("LOCKED");
    expect(view.detail).toContain("没有读取任何私人数据");
  });

  it("maps a readable-but-empty journal to NOT_CONNECTED and drops price-only blockers", () => {
    const view = privateStateFrom({ portfolio: notConnectedPortfolio() });
    expect(view.kind).toBe("NOT_CONNECTED");
    expect(view.blockers).toEqual(["PRIVATE_PORTFOLIO_NOT_CONNECTED"]);
    expect(view.detail).toContain("不代表你的组合为空");
  });

  it("maps CONNECTED + incomplete risk input to BLOCKED_PRIVATE_INPUT with merged blockers", () => {
    const view = privateStateFrom({
      portfolio: connectedPortfolio(),
      risk: riskResponse(
        "BLOCKED_PRIVATE_INPUT",
        ["investable_assets_cny", "PRICE_NOT_ADMITTED"],
        ["investable_assets_cny", "risk_tolerance"],
      ),
    });
    expect(view.kind).toBe("BLOCKED_PRIVATE_INPUT");
    expect(view.blockers).toEqual(["investable_assets_cny", "risk_tolerance"]);
  });

  it("keeps CONNECTED when the journal is readable and risk did not block input", () => {
    const view = privateStateFrom({
      portfolio: connectedPortfolio(),
      risk: riskResponse("BLOCKED", ["CORE_VALUE:risk_unknown"]),
    });
    expect(view.kind).toBe("CONNECTED");
    expect(view.blockers).toEqual(["CORE_VALUE:risk_unknown"]);
  });

  it("fails closed to UNAVAILABLE on a non-auth read error", () => {
    const view = privateStateFrom({
      error: new Error("journal checksum mismatch"),
    });
    expect(view.kind).toBe("UNAVAILABLE");
    expect(view.detail).toContain("journal checksum mismatch");
  });

  it("stays LOADING until the first portfolio read settles", () => {
    expect(privateStateFrom({ loading: true }).kind).toBe("LOADING");
    expect(privateStateFrom({}).kind).toBe("LOADING");
  });
});
