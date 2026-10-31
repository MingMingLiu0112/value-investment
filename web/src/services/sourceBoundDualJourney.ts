import type {
  DualAccountState,
  DualFormRow,
  SourceBoundDualPacket,
} from "../types/sourceBoundDualJourney";
import { day, intents, object } from "./simulatedJourney";

export const dualJourneyUrl = "/api/v1/simulated-trade-journey/dual-sleeve";
const hash = (v: unknown): v is string =>
  typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const text = (v: unknown): v is string => typeof v === "string" && !!v.trim();
const number = (v: unknown): v is string =>
  text(v) &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(v) &&
  Number.isFinite(Number(v));
const texts = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
const stamp = (v: unknown) =>
  text(v) &&
  day(v.slice(0, 10)) &&
  /T.*(?:Z|[+-]\d\d:\d\d)$/.test(v) &&
  Number.isFinite(Date.parse(v));
const bound = (v: unknown) =>
  object(v) &&
  text(v.path) &&
  !/^(?:[\\/]|[a-z]+:)/i.test(v.path) &&
  !v.path.split(/[\\/]/).includes("..") &&
  hash(v.sha256);
const canonical = (v: any): any =>
  Array.isArray(v)
    ? v.map(canonical)
    : object(v)
      ? Object.fromEntries(
          Object.keys(v)
            .sort()
            .map((key) => [key, canonical(v[key])]),
        )
      : v;
export const dualSourcesMatch = (a: unknown, b: unknown) =>
  JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

function noAuthority(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(noAuthority);
  if (!object(value)) return true;
  return Object.entries(value).every(([key, item]) => {
    if (
      [
        "formal_eligibility",
        "strategy_validated",
        "approval_changed",
        "broker_execution_permission",
        "actual_account_used",
        "original_pit_proven",
        "original_entry_advisory_eligible",
        "trade_eligible",
        "persistent_simulated_portfolio",
      ].includes(key) &&
      item !== false
    )
      return false;
    return noAuthority(item);
  });
}
function slots(value: unknown) {
  return (
    Array.isArray(value) &&
    value.map((row) => row?.intent).join(",") ===
      Object.keys(intents).join(",") &&
    value.every(
      (row) =>
        object(row) &&
        row.action === "no_order" &&
        row.formal_eligibility === false &&
        row.review_quantity === null &&
        row.outcome === (row.intent === "WAIT" ? "WAIT" : "NO_ACTION") &&
        texts(row.reasons) &&
        row.reasons.length > 0,
    )
  );
}
function state(value: unknown): value is DualAccountState {
  if (
    !object(value) ||
    !number(value.cash_cny) ||
    !number(value.confirmed_fees_cny) ||
    !Array.isArray(value.positions) ||
    !Array.isArray(value.aggregate_holdings) ||
    !(
      value.hypothetical_equity_cny === null ||
      number(value.hypothetical_equity_cny)
    ) ||
    value.mark_scope !==
      "CALLER_TEST_ONLY_MARKS_NOT_CURRENT_QUOTES_OR_INTRINSIC_VALUE" ||
    value.risk_scope !== "DISPOSABLE_ACCOUNT_MISSING_RISK_INPUTS_REMAIN_BLOCKED"
  )
    return false;
  const risk = value.risk_review,
    cash = value.sleeve_cash_review;
  return (
    object(risk) &&
    risk.namespace === "SIMULATED" &&
    risk.action === "no_order" &&
    text(risk.status) &&
    texts(risk.blockers) &&
    risk.position_guidance === null &&
    object(cash) &&
    cash.action === "no_order" &&
    cash.trade_eligible === false &&
    texts(cash.blockers) &&
    (cash.sleeves === null ||
      (object(cash.sleeves) &&
        ["CORE_VALUE", "HOTSPOT_SATELLITE"].every(
          (name) =>
            object(cash.sleeves[name]) &&
            number(cash.sleeves[name].cash_cny) &&
            number(cash.sleeves[name].shortfall_cny),
        ))) &&
    value.aggregate_holdings.every(
      (row) =>
        object(row) &&
        text(row.symbol) &&
        number(row.quantity) &&
        (row.market_value_cny === null || number(row.market_value_cny)),
    )
  );
}

/** Contract validation only; source bytes and accounting are verified by the server. */
export function verifiedDualJourney(
  value: unknown,
): value is SourceBoundDualPacket {
  try {
    if (
      !object(value) ||
      value.schema_version !== "source-bound-dual-sleeve-journey-v1" ||
      value.namespace !== "SIMULATED" ||
      value.action !== "no_order" ||
      value.scope !==
        "DISPOSABLE_SOURCE_BOUND_REHEARSAL_NOT_PERSISTENT_PORTFOLIO" ||
      !stamp(value.research_evaluated_at) ||
      ![
        "actual_account_used",
        "formal_eligibility",
        "strategy_validated",
        "approval_changed",
        "broker_execution_permission",
      ].every((key) => value[key] === false) ||
      value.position_guidance !== null ||
      !noAuthority(value)
    )
      return false;
    const identity = value.source_identity,
      wave = value.hotspot_case;
    if (
      !object(identity) ||
      !Array.isArray(identity.core) ||
      !identity.core.length ||
      !Array.isArray(value.core_cases) ||
      value.core_cases.length !== identity.core.length ||
      !object(identity.hotspot) ||
      !object(wave) ||
      wave.sleeve !== "HOTSPOT_SATELLITE" ||
      wave.action !== "no_order" ||
      wave.historical_only !== true ||
      wave.current_signal !== false ||
      wave.current_pit !== false ||
      wave.strategy_validated !== false ||
      wave.formal_eligibility !== false ||
      wave.review_quantity !== null ||
      !slots(wave.action_slots) ||
      !bound(wave.receipt_binding) ||
      !hash(wave.entry_freeze_sha256) ||
      wave.symbol !== identity.hotspot.symbol ||
      !dualSourcesMatch(
        wave.receipt_binding,
        identity.hotspot.receipt_binding,
      ) ||
      wave.entry_freeze_sha256 !== identity.hotspot.entry_freeze_sha256 ||
      "model_context" in wave
    )
      return false;
    if (!/^\d{6}$/.test(wave.symbol)) return false;
    const entry = wave.entry_reference;
    if (
      !object(entry) ||
      entry.namespace !== "SIMULATED" ||
      entry.symbol !== wave.symbol ||
      !stamp(entry.assumed_entry_at) ||
      !stamp(entry.generated_at) ||
      !bound(entry.entry_case_binding) ||
      entry.entry_origin !==
        "DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED" ||
      entry.fill_scope !==
        "HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL" ||
      !Array.isArray(wave.lifecycle_reviews) ||
      !wave.lifecycle_reviews.length ||
      !wave.lifecycle_reviews.every(
        (row) =>
          object(row) && row.action === "no_order" && stamp(row.evaluated_at),
      )
    )
      return false;
    if (
      new Set(identity.core.map((row) => row?.symbol)).size !==
        identity.core.length ||
      !value.core_cases.every((c: any, index: number) => {
        const source = identity.core[index],
          r = c?.research,
          e = c?.evaluation;
        return (
          object(source) &&
          object(c) &&
          c.action === "no_order" &&
          c.symbol === source.symbol &&
          /^\d{6}$/.test(c.symbol) &&
          object(r) &&
          bound(r.candidate_binding) &&
          dualSourcesMatch(r.candidate_binding, source.candidate_binding) &&
          text(r.research_version) &&
          r.research_version === source.research_version &&
          c.plan?.research_version === r.research_version &&
          r.scope === "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL" &&
          (r.confidence == null || text(r.confidence)) &&
          day(r.research_as_of) &&
          day(r.valuation_date) &&
          object(e) &&
          e.symbol === c.symbol &&
          e.action === "no_order" &&
          e.eligibility === false &&
          e.review_quantity === null &&
          e.position_range === null &&
          text(e.decision_action) &&
          slots(c.action_slots)
        );
      })
    )
      return false;
    const manual = value.manual_rehearsal;
    if (
      !object(manual) ||
      manual.actual_account_used !== false ||
      manual.persistent_simulated_portfolio !== false ||
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
      manual.restart_equal !== true ||
      !manual.fills.length ||
      !state(manual.account_state) ||
      !object(manual.assumptions) ||
      manual.assumptions.namespace !== "TEST_ONLY" ||
      manual.assumptions.confirmed !== true ||
      !object(manual.journal_receipt) ||
      !hash(manual.journal_receipt.sha256) ||
      manual.journal_receipt.retained !== false
    )
      return false;
    const seen = new Set<string>();
    const entries = new Map<
      string,
      { hash: string; sleeve: string; symbol: string; reference: unknown }
    >();
    return manual.fills.every((row) => {
      if (!object(row) || !object(row.fill)) return false;
      const fill = row.fill,
        core = value.core_cases.find((c: any) => c.symbol === fill.symbol);
      const version =
        fill.sleeve === "CORE_VALUE"
          ? core?.research?.research_version
          : fill.sleeve === "HOTSPOT_SATELLITE" && fill.symbol === wave.symbol
            ? wave.entry_freeze_sha256
            : null;
      if (!text(fill.transaction_id) || seen.has(fill.transaction_id))
        return false;
      seen.add(fill.transaction_id);
      const original = row.original_entry_reference;
      const selling = row.intent === "REDUCE" || row.intent === "EXIT";
      const consumed = row.consumed_original_entries;
      if (selling) {
        if (
          !Array.isArray(consumed) ||
          !consumed.length ||
          consumed.length > 12
        )
          return false;
        const ids = new Set<string>();
        if (
          !consumed.every((item: any) => {
            if (
              !object(item) ||
              !text(item.transaction_id) ||
              ids.has(item.transaction_id)
            )
              return false;
            ids.add(item.transaction_id);
            const linked = entries.get(item.transaction_id);
            return (
              !!linked &&
              linked.sleeve === fill.sleeve &&
              linked.symbol === fill.symbol &&
              number(item.quantity) &&
              /^\d+$/.test(item.quantity) &&
              Number(item.quantity) > 0 &&
              text(item.manual_rationale) &&
              item.consistency_scope ===
                "MANUAL_REASON_COMPARED_WITH_RECONSTRUCTED_THESIS_NOT_APPROVAL" &&
              dualSourcesMatch(item.original_entry_reference, linked.reference)
            );
          })
        )
          return false;
        if (
          !/^\d+$/.test(fill.quantity) ||
          consumed.reduce(
            (quantity: bigint, item: any) => quantity + BigInt(item.quantity),
            0n,
          ) !== BigInt(fill.quantity)
        )
          return false;
        if (consumed.length > 1) {
          if (original !== null || row.original_entry_transaction_id !== null)
            return false;
        } else if (
          row.original_entry_transaction_id !== consumed[0].transaction_id ||
          !dualSourcesMatch(original, consumed[0].original_entry_reference)
        )
          return false;
      } else if (
        consumed !== undefined &&
        (!Array.isArray(consumed) || consumed.length !== 0)
      )
        return false;
      if (
        !selling &&
        (!object(original) ||
          !hash(original.fill_record_sha256) ||
          !Array.isArray(original.key) ||
          original.key[0] !== fill.sleeve ||
          original.key[1] !== fill.symbol ||
          !object(original.narrative) ||
          !text(original.narrative.thesis) ||
          !text(original.narrative.hold_logic) ||
          !texts(original.narrative.invalidation_conditions))
      )
        return false;
      if (
        !dualSourcesMatch(
          row.source_reference,
          fill.sleeve === "CORE_VALUE" ? core?.research : wave,
        )
      )
        return false;
      if (row.intent === "BUY") {
        if (
          row.original_entry_transaction_id !== null ||
          original.fill_record_sha256 !== row.fill_record_sha256
        )
          return false;
      } else if (!selling) {
        const linked = entries.get(row.original_entry_transaction_id);
        if (
          !linked ||
          linked.hash !== original.fill_record_sha256 ||
          linked.sleeve !== fill.sleeve ||
          linked.symbol !== fill.symbol
        )
          return false;
      }
      if (row.intent === "BUY" || row.intent === "ADD")
        entries.set(fill.transaction_id, {
          hash: row.fill_record_sha256,
          sleeve: fill.sleeve,
          symbol: fill.symbol,
          reference:
            row.intent === "BUY"
              ? original
              : {
                  key: [fill.sleeve, fill.symbol],
                  narrative: original.narrative,
                  fill_record_sha256: row.fill_record_sha256,
                },
        });
      return (
        !!version &&
        row.source_version === version &&
        ["BUY", "ADD", "REDUCE", "EXIT"].includes(row.intent) &&
        fill.side === (["BUY", "ADD"].includes(row.intent) ? "BUY" : "SELL") &&
        [
          fill.quantity,
          fill.price_cny,
          fill.fees_cny,
          row.requested_quantity,
          row.unfilled_quantity,
        ].every(number) &&
        /^\d+$/.test(fill.quantity) &&
        Number(fill.quantity) > 0 &&
        Number(fill.price_cny) > 0 &&
        Number(fill.fees_cny) >= 0 &&
        Number(row.unfilled_quantity) >= 0 &&
        day(fill.trade_date) &&
        hash(row.fill_record_sha256) &&
        row.scope === "EXPLICIT_MANUAL_HYPOTHESIS_NOT_SYSTEM_ACTION" &&
        row.execution_price_scope === "CALLER_HYPOTHETICAL_NOT_MARKET_FILL" &&
        row.fee_scope ===
          "CALLER_TOTAL_COST_HYPOTHESIS_NOT_VERIFIED_FEE_SCHEDULE" &&
        row.unfilled_scope === "INFORMATION_ONLY_NOT_OPEN_ORDER" &&
        row.original_pit_proven === false &&
        row.original_entry_advisory_eligible === false &&
        row.confirmation_idempotent === true &&
        row.prepared_cash_unchanged === true &&
        texts(row.entry_blockers) &&
        text(row.rationale) &&
        state(row.before) &&
        state(row.after) &&
        ((original === null && !["BUY", "ADD"].includes(row.intent)) ||
          (object(original) &&
            hash(original.fill_record_sha256) &&
            Array.isArray(original.key) &&
            original.key[0] === fill.sleeve &&
            original.key[1] === fill.symbol &&
            object(original.narrative) &&
            text(original.narrative.thesis) &&
            text(original.narrative.hold_logic) &&
            texts(original.narrative.invalidation_conditions)))
      );
    });
  } catch {
    return false;
  }
}

/** Existing _policy(day) defaults, explicitly TEST_ONLY; not a personal IPS. */
export function dualTestPolicy(date: string) {
  return {
    investable_assets_cny: "10000",
    core_value_budget_cny: "5000",
    hotspot_budget_cny: "3000",
    cash_reserve_cny: "2000",
    minimum_cash_cny: "2000",
    emergency_cash_cny: "0",
    liquidity_needs_cny: "0",
    max_single_security_pct: "80",
    max_single_industry_pct: "90",
    max_cyclical_exposure_pct: "70",
    max_factor_pct: "100",
    hotspot_single_trade_risk_pct: "5",
    max_drawdown_pct: "20",
    financing_allowed: false,
    risk_tools_allowed: false,
    dividend_income_goal_cny: "0",
    effective_date: date,
    time_horizon_years: "5",
    risk_tolerance: "BALANCED",
    concentration_allowed: true,
    restrictions: ["no_order", "SIMULATED_ONLY"],
    tax_regime: "SIMULATED_FEE_FIXTURE",
    sleeves: {
      CORE_VALUE: { cash_cny: "5000", risk_budget_cny: "1000" },
      HOTSPOT_SATELLITE: {
        cash_cny: "3000",
        risk_budget_cny: "500",
        single_security_risk_cny: "300",
      },
    },
  };
}

export function dualManualRequest(
  packet: SourceBoundDualPacket,
  date: string,
  rows: DualFormRow[],
) {
  if (!verifiedDualJourney(packet) || !day(date) || rows.length !== 2)
    throw new Error("SOURCE_OR_PARAMETERS_UNVERIFIED");
  const selected = [
    { sleeve: "CORE_VALUE", symbol: packet.core_cases[0].symbol },
    { sleeve: "HOTSPOT_SATELLITE", symbol: packet.hotspot_case.symbol },
  ];
  const marks: Record<string, string> = {};
  const manual_fills = rows.map((row, index) => {
    if (
      ![row.price, row.fees].every((v) => number(v) && Number(v) >= 0) ||
      Number(row.price) <= 0 ||
      !/^\d+$/.test(row.quantity) ||
      Number(row.quantity) <= 0 ||
      ![row.rationale, row.thesis, row.hold, row.breakers].every(text)
    )
      throw new Error("EXPLICIT_HYPOTHESIS_REQUIRED");
    const { symbol, sleeve } = selected[index];
    if (marks[symbol] !== undefined && marks[symbol] !== row.price)
      throw new Error("AMBIGUOUS_SAME_SECURITY_MARK");
    marks[symbol] = row.price;
    const id =
      typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
            byte.toString(16).padStart(2, "0"),
          ).join("");
    return {
      intent: "BUY",
      rationale: row.rationale,
      entry_narrative: {
        thesis: row.thesis,
        hold_logic: row.hold,
        invalidation_conditions: row.breakers
          .split("\n")
          .map((v) => v.trim())
          .filter(Boolean),
      },
      fill: {
        transaction_id: `TEST_ONLY-${id}`,
        side: "BUY",
        sleeve,
        symbol,
        exchange: symbol.startsWith("6") ? "SSE" : "SZSE",
        quantity: row.quantity,
        price_cny: row.price,
        fees_cny: row.fees,
        trade_date: date,
        trading_unit: "100",
      },
    };
  });
  return {
    confirmed_hypothetical: true,
    expected_sources: structuredClone(packet.source_identity),
    test_only_account: {
      namespace: "TEST_ONLY",
      confirmed: true,
      opening_day: date,
      initial_cash_cny: "10000",
      policy: dualTestPolicy(date),
      hypothetical_marks: marks,
    },
    manual_fills,
  };
}
