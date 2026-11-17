export type EntryPlan = {
  entry_artifact_id: string;
  consistency_artifact_id: string;
  thesis: string;
  hold_logic: string;
  invalidation_conditions: string[];
  binding_modes: string[];
};

export type EntryConfirmation = {
  record_sha256: string;
  recorded_at: string;
  kind: string;
  binding_mode: string;
  confirmation_note: string;
  provenance?: string;
  thesis?: string;
  hold_logic?: string;
  invalidation_conditions?: string[];
  reconstruction?: {
    thesis: string;
    hold_logic: string;
    invalidation_conditions: string[];
  };
};

export type EntryThesisItem = {
  fill_record_sha256: string;
  transaction_id: string;
  symbol: string;
  exchange: string;
  sleeve: string;
  quantity: string;
  remaining_quantity: string;
  trade_date: string;
  price_cny: string;
  current_binding: EntryConfirmation | null;
  history: EntryConfirmation[];
  candidate_plans: EntryPlan[];
};

export type EntryThesisView = {
  action: "no_order";
  status: string;
  revision: number;
  account_scope: string | null;
  items: EntryThesisItem[];
  blockers?: string[];
};

export function thesisConfirmationBody(
  view: EntryThesisView,
  item: EntryThesisItem,
  input: {
    note: string;
    acknowledged: boolean;
    plan?: EntryPlan;
    mode: string;
    thesis: string;
    hold: string;
    breakers: string;
  },
) {
  if (view.action !== "no_order" || !input.acknowledged || !input.note.trim())
    throw new Error("请阅读原投资逻辑并填写确认说明。");
  if (!view.items.includes(item) || Number(item.remaining_quantity) <= 0)
    throw new Error("该笔买入已不属于当前剩余持仓，请刷新。");
  const result: Record<string, unknown> = {
    expected_revision: view.revision,
    fill_record_sha256: item.fill_record_sha256,
    confirmation_note: input.note.trim(),
    read_and_confirmed: true,
    binding_mode: input.mode,
  };
  if (item.current_binding)
    result.supersedes_record_sha256 = item.current_binding.record_sha256;
  if (input.plan) {
    if (
      !item.candidate_plans.includes(input.plan) ||
      !input.plan.binding_modes.includes(input.mode)
    )
      throw new Error("所选研究计划不支持该确认口径。");
    result.entry_artifact_id = input.plan.entry_artifact_id;
    result.consistency_artifact_id = input.plan.consistency_artifact_id;
  } else {
    const conditions = input.breakers
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (
      input.mode !== "HISTORICAL_RECONSTRUCTION" ||
      !input.thesis.trim() ||
      !input.hold.trim() ||
      !conditions.length
    )
      throw new Error("事后补录需要买入理由、持有逻辑和失效条件。");
    result.reconstruction = {
      thesis: input.thesis.trim(),
      hold_logic: input.hold.trim(),
      invalidation_conditions: conditions,
    };
  }
  return result;
}
