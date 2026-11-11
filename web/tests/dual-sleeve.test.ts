import { describe, expect, it } from "vitest";
import {
  dualSleeveLiveUnreadable,
  dualSleeveMismatch,
  dualSleeveView,
} from "../src/utils/dualSleeve";
import type { DailyDualSleeveSurface } from "../src/types/api";

const NOT_CONNECTED: DailyDualSleeveSurface = {
  schema_version: "daily-dual-sleeve-surface-v1",
  action: "no_order",
  status: "NOT_CONNECTED",
  namespace: "ACTUAL",
  portfolio_connected: false,
  position_guidance: null,
  position_guidance_available: false,
  trade_eligible: false,
  acceptance_authority: "NONE",
  review_generated_at: null,
  blockers: ["portfolio.private_input_missing"],
  next_user_input: "PRIVATE_PORTFOLIO_INPUT_REQUIRED",
  source:
    "runtime/daily-trade-assistant/fm3-v3-publish-20261012-v2/dual-sleeve-risk.json",
};

describe("dual-sleeve daily surface view", () => {
  it("marks the published table as a snapshot when the live ledger is unreadable", () => {
    expect(dualSleeveLiveUnreadable("LOCKED")).toBe(true);
    expect(dualSleeveLiveUnreadable("UNAVAILABLE")).toBe(true);
    expect(dualSleeveLiveUnreadable("LOADING")).toBe(true);
    expect(dualSleeveLiveUnreadable("NOT_CONNECTED")).toBe(false);
    expect(dualSleeveLiveUnreadable("CONNECTED")).toBe(false);
    expect(dualSleeveLiveUnreadable("BLOCKED_PRIVATE_INPUT")).toBe(false);
  });

  it("reports the not-connected state without inventing a position", () => {
    const view = dualSleeveView(NOT_CONNECTED)!;
    expect(view.statusText).toContain("私人组合未接入");
    expect(view.connectedText).toBe("未接入");
    expect(view.guidanceText).toBe("尚未生成");
    expect(view.guidanceMissingReason).toContain("不会给出");
    expect(view.eligibilityText).toBe("未开启交易资格");
    expect(view.authorityText).toContain("人工");
  });

  it("names the next user input instead of ending in a silent dead end", () => {
    const view = dualSleeveView(NOT_CONNECTED)!;
    expect(view.nextInputText).toContain("私人组合输入");
    expect(view.guidanceMissingReason).toContain("尚未接入真实私人组合");
  });

  it("translates known blocker codes and keeps unknown codes visible", () => {
    const translated = dualSleeveView({
      ...NOT_CONNECTED,
      status: "BLOCKED_PRIVATE_INPUT",
      next_user_input: "PRIVATE_INPUT_INCOMPLETE",
    })!;
    expect(translated.guidanceMissingReason).toContain("私人组合输入");
    const unknown = dualSleeveView({
      ...NOT_CONNECTED,
      status: "BLOCKED_PRIVATE_INPUT",
      blockers: ["BRAND_NEW_CODE"],
      next_user_input: "PRIVATE_INPUT_INCOMPLETE",
    })!;
    expect(unknown.guidanceMissingReason).toContain("BRAND_NEW_CODE");
  });

  it("states that a computed review still produces no position guidance", () => {
    const view = dualSleeveView({
      ...NOT_CONNECTED,
      status: "REVIEW_REQUIRED",
      portfolio_connected: true,
      blockers: [],
      next_user_input: null,
    })!;
    expect(view.guidanceMissingReason).toContain("仍需人工决策");
    expect(view.nextInputText).toBeNull();
    expect(view.connectedText).toBe("已接入");
  });

  it("stops claiming a missing reason once guidance exists", () => {
    const view = dualSleeveView({
      ...NOT_CONNECTED,
      portfolio_connected: true,
      position_guidance: { note: "engine output" },
      position_guidance_available: true,
      next_user_input: null,
    })!;
    expect(view.guidanceText).toContain("已生成");
    expect(view.guidanceMissingReason).toBeNull();
  });

  it("returns null when the publication carries no dual-sleeve section", () => {
    expect(dualSleeveView(undefined)).toBeNull();
    expect(dualSleeveView(null)).toBeNull();
  });
});

describe("dual-sleeve publication vs live private ledger", () => {
  it("flags a published-connected surface when the live ledger is missing", () => {
    const mismatch = dualSleeveMismatch(
      { ...NOT_CONNECTED, portfolio_connected: true },
      "NOT_CONNECTED",
    );
    expect(mismatch).toContain("当前读不到真实台账");
  });

  it("flags a published-disconnected surface when the live ledger is readable", () => {
    const mismatch = dualSleeveMismatch(NOT_CONNECTED, "CONNECTED");
    expect(mismatch).toContain("尚未包含最新私人组合");
    expect(
      dualSleeveMismatch(NOT_CONNECTED, "BLOCKED_PRIVATE_INPUT"),
    ).not.toBeNull();
  });

  it("stays silent while the ledger is locked, loading or unreadable", () => {
    expect(dualSleeveMismatch(NOT_CONNECTED, "LOCKED")).toBeNull();
    expect(dualSleeveMismatch(NOT_CONNECTED, "LOADING")).toBeNull();
    expect(dualSleeveMismatch(NOT_CONNECTED, "UNAVAILABLE")).toBeNull();
  });

  it("stays silent when published and live states agree", () => {
    expect(dualSleeveMismatch(NOT_CONNECTED, "NOT_CONNECTED")).toBeNull();
    expect(
      dualSleeveMismatch(
        { ...NOT_CONNECTED, portfolio_connected: true },
        "CONNECTED",
      ),
    ).toBeNull();
  });
});
