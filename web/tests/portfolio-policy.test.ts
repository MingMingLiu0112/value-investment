import { describe, expect, it } from "vitest";
import {
  missingPolicyInputs,
  policyConfirmationBody,
  policyFormValues,
  policyFromForm,
  policyReviewRows,
  policyRequiredFields,
} from "../src/utils/portfolioPolicy";

describe("IPS explicit input and human confirmation", () => {
  it("saves incomplete drafts without inventing allocation or risk choices", () => {
    expect(policyFromForm({})).toEqual({ action: "no_order" });
    expect(
      policyFromForm({
        financing_allowed: "DENY",
        risk_tools_allowed: "ALLOW",
      }),
    ).toEqual({
      action: "no_order",
      financing_allowed: false,
      risk_tools_allowed: true,
    });
    expect(
      policyFormValues({ financing_allowed: false }).financing_allowed,
    ).toBe("DENY");
    const policy = policyFromForm({
      investable_assets_cny: " 20000 ",
      financing_allowed: false,
      risk_tools_allowed: undefined,
      max_drawdown_pct: "",
      sleeves: { CORE_VALUE: { cash_cny: "0" } },
    });
    expect(policy).toEqual({
      action: "no_order",
      investable_assets_cny: "20000",
      financing_allowed: false,
      sleeves: { CORE_VALUE: { cash_cny: "0" } },
    });
    expect(missingPolicyInputs(policy)).not.toContain("financing_allowed");
    expect(missingPolicyInputs(policy)).not.toContain(
      "sleeves.CORE_VALUE.cash_cny",
    );
    expect(missingPolicyInputs(policy)).toContain(
      "sleeves.CORE_VALUE.risk_budget_cny",
    );
    expect(missingPolicyInputs(policy)).toContain("max_drawdown_pct");
    expect(missingPolicyInputs({ risk_tolerance: "UNKNOWN" })).toContain(
      "risk_tolerance",
    );
  });

  it("binds confirmation to the server draft revision/hash and explicit human note", () => {
    const digest = "a".repeat(64);
    expect(() =>
      policyConfirmationBody(7, digest, "", true, "2026-10-14T10:00:00+08:00"),
    ).toThrow();
    expect(() =>
      policyConfirmationBody(
        7,
        digest,
        "已核对",
        false,
        "2026-10-14T10:00:00+08:00",
      ),
    ).toThrow();
    expect(() =>
      policyConfirmationBody(
        7,
        "bad",
        "已核对",
        true,
        "2026-10-14T10:00:00+08:00",
      ),
    ).toThrow();
    expect(
      policyConfirmationBody(
        7,
        digest,
        " 本人逐项核对 ",
        true,
        "2026-10-14T10:00:00+08:00",
      ),
    ).toEqual({
      expected_revision: 7,
      prepared_record_sha256: digest,
      confirmation_note: "本人逐项核对",
      confirmed_at: "2026-10-14T10:00:00+08:00",
    });
  });

  it("requires every risk input while preserving explicit false and zero", () => {
    const policy: Record<string, any> = {
      sleeves: { CORE_VALUE: {}, HOTSPOT_SATELLITE: {} },
    };
    for (const key of policyRequiredFields) {
      if (key.startsWith("sleeves.")) {
        const [, sleeve, field] = key.split(".");
        policy.sleeves[sleeve][field] = "0";
      } else policy[key] = key.endsWith("allowed") ? false : "1";
    }
    expect(missingPolicyInputs(policy)).toEqual([]);
    delete policy.sleeves.HOTSPOT_SATELLITE.single_security_risk_cny;
    expect(missingPolicyInputs(policy)).toEqual([
      "sleeves.HOTSPOT_SATELLITE.single_security_risk_cny",
    ]);
  });

  it("keeps original source hashes and refuses partial or duplicate provenance", () => {
    const source = {
      symbol: "600887",
      path: "registered/risk.json",
      sha256: "b".repeat(64),
    };
    const policy = policyFromForm({
      security_bindings: [source],
      restrictions: "不得借款\n不得自动下单",
    });
    expect(policy.security_attribute_bindings).toEqual({
      "600887": { path: source.path, sha256: source.sha256 },
    });
    expect(policyFormValues(policy).security_bindings).toEqual([source]);
    expect(() =>
      policyFromForm({ security_bindings: [{ symbol: "600887" }] }),
    ).toThrow();
    expect(() =>
      policyFromForm({ security_bindings: [source, source] }),
    ).toThrow();
    expect(policyReviewRows({ financing_allowed: false })[0].value).toBe(
      "不允许",
    );
  });
});
