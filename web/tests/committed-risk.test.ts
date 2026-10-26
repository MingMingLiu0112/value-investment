import { expect, it } from "vitest";
import {
  committedRiskConfirmation,
  verifyCommittedRiskResponse,
  type CommittedRiskView,
} from "../src/services/committedRisk";

const view: CommittedRiskView = {
  action: "no_order",
  status: "CONFIRMATION_REQUIRED",
  account_scope: "TEST_ONLY",
  revision: 9,
  journal_tip_sha256: "a".repeat(64),
  formal_eligibility: false,
  allocations: [
    {
      symbol: "600519",
      sleeve: "CORE_VALUE",
      exchange: "SSE",
      quantity: "100",
      cost_basis_cny: "120000",
      committed_risk_cny: null,
      evidence_ref: null,
    },
  ],
};
const amounts = [
  {
    symbol: "600519",
    sleeve: "CORE_VALUE",
    committed_risk_cny: "2500.00",
    evidence_ref: "TEST_ONLY explicit assessment",
  },
];
const build = () =>
  committedRiskConfirmation(view, 9, amounts, "TEST_ONLY confirmed now", true);
it("binds explicitly entered amounts to the current private ledger without inferred risk or signing identity", () => {
  const body = build();
  expect(body.amounts[0].committed_risk_cny).toBe("2500.00");
  expect(body.journal_tip_sha256).toBe(view.journal_tip_sha256);
  expect(body).not.toHaveProperty("authenticated_subject");
  expect(body).not.toHaveProperty("confirmed_at");
  expect(() =>
    committedRiskConfirmation(view, 8, amounts, "note", true),
  ).toThrow();
  expect(() =>
    committedRiskConfirmation(view, 9, amounts, "note", false),
  ).toThrow();
});
it.each(["", "NaN", "Infinity", "-1", "1e4", "0.001"])(
  "rejects missing or ambiguous risk amount %s",
  (value) => {
    expect(() =>
      committedRiskConfirmation(
        view,
        9,
        [{ ...amounts[0], committed_risk_cny: value }],
        "note",
        true,
      ),
    ).toThrow();
  },
);
it("rejects omitted, duplicate, different-sleeve and ungrounded declarations", () => {
  for (const rows of [
    [],
    [...amounts, ...amounts],
    [{ ...amounts[0], sleeve: "HOTSPOT_SATELLITE" }],
    [{ ...amounts[0], evidence_ref: " " }],
  ]) {
    expect(() =>
      committedRiskConfirmation(view, 9, rows, "note", true),
    ).toThrow();
  }
});
it("verifies exact echoed amount, account, revision, basis and immutable receipt before showing success", () => {
  const response = {
    ...view,
    revision: 10,
    journal_tip_sha256: "d".repeat(64),
    changes_holdings: false,
    request_binding: {
      expected_revision: 9,
      account_scope: "TEST_ONLY",
      journal_tip_sha256: view.journal_tip_sha256!,
    },
    status: "COMMITTED_RISK_CONFIRMED",
    confirmation_sha256: "b".repeat(64),
    allocations: [
      { ...view.allocations[0], ...amounts[0], committed_risk_cny: "2500" },
    ],
  };
  expect(() => verifyCommittedRiskResponse(response, build())).not.toThrow();
  for (const changed of [
    { ...response, account_scope: "other" },
    { ...response, revision: 9 },
    {
      ...response,
      request_binding: {
        ...response.request_binding,
        journal_tip_sha256: "c".repeat(64),
      },
    },
    { ...response, confirmation_sha256: null },
    {
      ...response,
      allocations: [{ ...response.allocations[0], committed_risk_cny: "0" }],
    },
    {
      ...response,
      allocations: [{ ...response.allocations[0], evidence_ref: "other" }],
    },
  ]) {
    expect(() => verifyCommittedRiskResponse(changed, build())).toThrow();
  }
});
