import { expect, it } from "vitest";
import {
  thesisConfirmationBody,
  type EntryThesisItem,
  type EntryThesisView,
} from "../src/services/entryThesis";

const item: EntryThesisItem = {
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
};
const view: EntryThesisView = {
  action: "no_order",
  status: "AVAILABLE",
  revision: 3,
  account_scope: "TEST_ONLY",
  items: [item],
};
const input = {
  note: "TEST_ONLY reconstructed now",
  acknowledged: true,
  mode: "HISTORICAL_RECONSTRUCTION",
  thesis: "Business belief",
  hold: "Evidence intact",
  breakers: "Cash flow fails\nThesis broken",
};

it("builds an explicitly retrospective confirmation, never client authentication", () => {
  const result = thesisConfirmationBody(view, item, input);
  expect(result.binding_mode).toBe("HISTORICAL_RECONSTRUCTION");
  expect(result.expected_revision).toBe(3);
  expect(result.reconstruction).toEqual({
    thesis: "Business belief",
    hold_logic: "Evidence intact",
    invalidation_conditions: ["Cash flow fails", "Thesis broken"],
  });
  expect(result).not.toHaveProperty("authenticated_subject");
  expect(result).not.toHaveProperty("confirmed_at");
  expect(result).not.toHaveProperty("entry_artifact_id");
});
it("rejects omitted acknowledgement and historical evidence forgery", () => {
  expect(() =>
    thesisConfirmationBody(view, item, { ...input, acknowledged: false }),
  ).toThrow();
  expect(() =>
    thesisConfirmationBody(view, item, { ...input, mode: "CONTEMPORANEOUS" }),
  ).toThrow();
  expect(() => thesisConfirmationBody(view, { ...item }, input)).toThrow();
  expect(() =>
    thesisConfirmationBody(view, item, { ...input, breakers: "" }),
  ).toThrow();
});
it("binds exact registered plan and superseded confirmation", () => {
  const plan = {
    entry_artifact_id: "TEST_ONLY-entry",
    consistency_artifact_id: "TEST_ONLY-review",
    thesis: "Actual registered thesis",
    hold_logic: "Hold",
    invalidation_conditions: ["Broken"],
    binding_modes: ["CONTEMPORANEOUS"],
  };
  const row = {
    ...item,
    candidate_plans: [plan],
    current_binding: {
      record_sha256: "b".repeat(64),
      recorded_at: "2026-10-21T01:00:00Z",
      kind: "PERSONAL_ENTRY_THESIS_CONFIRMED",
      binding_mode: "CONTEMPORANEOUS",
      confirmation_note: "TEST_ONLY",
    },
  };
  const result = thesisConfirmationBody({ ...view, items: [row] }, row, {
    ...input,
    plan,
    mode: "CONTEMPORANEOUS",
  });
  expect(result.entry_artifact_id).toBe(plan.entry_artifact_id);
  expect(result.supersedes_record_sha256).toBe("b".repeat(64));
  expect(result).not.toHaveProperty("reconstruction");
});
