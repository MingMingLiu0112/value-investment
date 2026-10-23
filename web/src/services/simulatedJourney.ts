import type { Binding, SourceBoundJourney } from "../types/simulatedJourney";

export const intents = {
  BUY: "买入",
  ADD: "加仓",
  HOLD: "持有",
  REDUCE: "减仓",
  EXIT: "退出",
  WAIT: "等待",
};

export const object = (value: unknown): value is Record<string, any> =>
  !!value && typeof value === "object" && !Array.isArray(value);

const text = (value: unknown): value is string =>
  typeof value === "string" && !!value.trim();

export const decimal = (value: unknown): value is string =>
  typeof value === "string" &&
  /^\d+(?:\.\d+)?$/.test(value) &&
  Number.isFinite(Number(value));

const digest = (value: unknown) =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);

const binding = (value: unknown): value is Binding =>
  object(value) &&
  text(value.path) &&
  !/^(?:[\\/]|[a-z]+:)/i.test(value.path) &&
  !value.path.split(/[\\/]/).includes("..") &&
  digest(value.sha256);

const sameBinding = (left: Binding, right: Binding) =>
  left.path === right.path && left.sha256 === right.sha256;

export function day(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  );
}

const timestamp = (value: unknown) =>
  text(value) &&
  /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
  Number.isFinite(Date.parse(value));

/** Validate only this source-bound non-action contract, not investment merit. */
export function verifiedSourceBoundJourney(
  value: unknown,
): value is SourceBoundJourney {
  try {
    if (
      !object(value) ||
      value.schema_version !== "source-bound-simulated-trade-journey-v1" ||
      value.namespace !== "SIMULATED" ||
      value.research_namespace !== "PUBLIC_SOURCE_BOUND" ||
      value.action !== "no_order" ||
      value.scope !==
        "PUBLIC_RESEARCH_WITH_OPTIONAL_ISOLATED_MANUAL_ACCOUNTING" ||
      value.strategy_validated !== false ||
      value.approval_changed !== false ||
      value.broker_execution_permission !== false ||
      value.personal_risk_evaluated !== false ||
      value.position_guidance !== null ||
      !timestamp(value.research_evaluated_at) ||
      !Number.isInteger(value.source_files_verified) ||
      value.source_files_verified < 0 ||
      !Array.isArray(value.cases) ||
      (value.cases.length !== 0 &&
        (value.cases.length !== 2 ||
          new Set(value.cases.map((row: any) => row.symbol)).size !== 2))
    )
      return false;
    for (const item of value.cases) {
      if (
        !object(item) ||
        !["600519", "600887"].includes(item.symbol) ||
        item.action !== "no_order" ||
        !text(item.company_name)
      )
        return false;
      const r = item.research,
        p = item.plan,
        e = item.evaluation;
      if (
        !object(r) ||
        !binding(r.candidate_binding) ||
        !text(r.research_version) ||
        !object(r.model_context) ||
        (r.confidence !== undefined &&
          !["高", "中", "低"].includes(r.confidence)) ||
        !digest(r.model_context.input_descriptor_sha256) ||
        !text(r.model_context.model_id) ||
        !text(r.model_context.model_version) ||
        !day(r.research_as_of) ||
        !day(r.valuation_date) ||
        !timestamp(r.generated_at) ||
        !timestamp(r.available_at) ||
        !timestamp(r.computed_at) ||
        (r.replayed_at != null && !timestamp(r.replayed_at)) ||
        r.scope !== "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL" ||
        !object(p) ||
        p.research_version !== r.research_version ||
        !text(p.signal_state) ||
        !text(p.candidate_action) ||
        !text(p.verification_scope) ||
        !object(e) ||
        e.symbol !== item.symbol ||
        e.action !== "no_order" ||
        e.strategy !== "CORE_VALUE" ||
        !text(e.decision_action) ||
        e.eligibility !== false ||
        e.review_quantity !== null ||
        e.position_range !== null ||
        !Array.isArray(item.action_slots) ||
        item.action_slots.length !== 6 ||
        item.action_slots.map((slot: any) => slot?.intent).join(",") !==
          Object.keys(intents).join(",") ||
        !item.action_slots.every(
          (slot: any) =>
            object(slot) &&
            slot.action === "no_order" &&
            slot.formal_eligibility === false &&
            slot.review_quantity === null &&
            slot.outcome === (slot.intent === "WAIT" ? "WAIT" : "NO_ACTION") &&
            slot.strategy_verdict === e.decision_action &&
            Array.isArray(slot.reasons) &&
            slot.reasons.length > 0 &&
            slot.reasons.every(text),
        )
      )
        return false;
    }
    const manual = value.manual_rehearsal;
    if (
      !object(manual) ||
      manual.actual_account_used !== false ||
      manual.temporary_journal_removed !== true ||
      !Array.isArray(manual.fills)
    )
      return false;
    if (manual.status === "NOT_REQUESTED")
      return (
        manual.fills.length === 0 &&
        manual.account_state === null &&
        manual.journal_receipt === null
      );
    if (
      manual.status !== "EXPLICIT_SIMULATED_RECORDS_ONLY" ||
      !manual.fills.length ||
      value.cases.length !== 2 ||
      manual.restart_equal !== true ||
      !object(manual.account_state) ||
      !decimal(manual.account_state.cash_cny) ||
      !decimal(manual.account_state.confirmed_fees_cny) ||
      (manual.account_state.positions !== undefined &&
        (!Array.isArray(manual.account_state.positions) ||
          !manual.account_state.positions.every(
            (position: any) =>
              object(position) &&
              ["600519", "600887"].includes(position.symbol) &&
              decimal(position.quantity) &&
              decimal(position.cost_cny) &&
              Array.isArray(position.sleeves) &&
              position.sleeves.every(
                (sleeve: any) =>
                  object(sleeve) &&
                  sleeve.sleeve === "CORE_VALUE" &&
                  decimal(sleeve.sellable_quantity) &&
                  (sleeve.next_sell_session == null ||
                    day(sleeve.next_sell_session)),
              ),
          ))) ||
      !object(manual.journal_receipt) ||
      !digest(manual.journal_receipt.sha256) ||
      manual.journal_receipt.retained !== false ||
      !Number.isInteger(manual.t1_negative_checks) ||
      manual.t1_negative_checks < 0 ||
      (manual.t1_negative_checks > 0
        ? manual.same_session_sell_rejected !== true
        : manual.same_session_sell_rejected !== null)
    )
      return false;
    return manual.fills.every((row: any) => {
      const source = value.cases.find(
        (item: any) => item.symbol === row?.symbol,
      );
      return (
        object(row) &&
        source &&
        ["BUY", "SELL"].includes(row.side) &&
        row.scope === "EXPLICIT_SIMULATED_MANUAL_FILL_NOT_STRATEGY_ACTION" &&
        binding(row.source_candidate_binding) &&
        sameBinding(
          row.source_candidate_binding,
          source.research.candidate_binding,
        ) &&
        row.original_entry_advisory_eligible === false &&
        row.execution_price_scope ===
          "CALLER_SUPPLIED_HYPOTHETICAL_FILL_NOT_QUOTE_OR_FAIR_VALUE" &&
        row.confirmation_idempotent === true &&
        row.prepared_cash_unchanged === true &&
        digest(row.fill_record_sha256) &&
        timestamp(row.recorded_at) &&
        text(row.snapshot_status) &&
        text(row.historical_reference_status) &&
        (row.historical_reference_scope === null ||
          row.historical_reference_scope === "NOT_ORIGINAL_PIT_ENTRY") &&
        object(row.fill) &&
        row.fill.symbol === row.symbol &&
        row.fill.side === row.side &&
        [row.fill.quantity, row.fill.price_cny, row.fill.fees_cny].every(
          decimal,
        ) &&
        day(row.fill.trade_date)
      );
    });
  } catch {
    return false;
  }
}

export function sourceBoundCandidatesMatch(
  packet: SourceBoundJourney,
  expected: unknown,
): boolean {
  return (
    Array.isArray(expected) &&
    expected.length === 2 &&
    packet.cases.length === 2 &&
    new Set(expected.map((item) => item?.symbol)).size === 2 &&
    expected.every((item) => {
      const source = packet.cases.find((row) => row.symbol === item?.symbol);
      return (
        object(item) &&
        !!source &&
        binding(item.candidate_binding) &&
        sameBinding(
          item.candidate_binding,
          source.research.candidate_binding,
        ) &&
        item.research_version === source.research.research_version
      );
    })
  );
}
