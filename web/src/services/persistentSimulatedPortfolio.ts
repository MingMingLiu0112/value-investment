import type {
  PersistentSimulatedWorkbench,
  SimulatedOperation,
  SimulatedWrite,
} from "../types/persistentSimulatedPortfolio";

export const simulatedPortfolioUrl = "/api/v1/simulated-portfolio";
const object = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string" && !!v.trim();
const hash = (v: unknown) => text(v) && /^[a-f0-9]{64}$/.test(v);
const decimal = (v: unknown) =>
  text(v) &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(v) &&
  Number.isFinite(Number(v));
const date = (v: unknown) =>
  text(v) &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v;
const stamp = (v: unknown) =>
  text(v) &&
  /T.*(?:Z|[+-]\d\d:\d\d)$/.test(v) &&
  date(v.slice(0, 10)) &&
  Number.isFinite(Date.parse(v));
const sleeve = (v: unknown) => v === "CORE_VALUE" || v === "HOTSPOT_SATELLITE";
const strings = (v: unknown) => Array.isArray(v) && v.every(text);
const fill = (v: unknown) =>
  object(v) &&
  text(v.transaction_id) &&
  ["BUY", "SELL"].includes(v.side) &&
  sleeve(v.sleeve) &&
  /^\d{6}$/.test(v.symbol) &&
  ["SSE", "SZSE"].includes(v.exchange) &&
  decimal(v.quantity) &&
  /^\d+$/.test(v.quantity) &&
  Number(v.quantity) > 0 &&
  decimal(v.price_cny) &&
  Number(v.price_cny) > 0 &&
  decimal(v.fees_cny) &&
  Number(v.fees_cny) >= 0 &&
  date(v.trade_date);
export function verifiedPersistentSimulatedWorkbench(
  v: unknown,
): v is PersistentSimulatedWorkbench {
  if (
    !object(v) ||
    v.schema_version !== "persistent-simulated-workbench-v1" ||
    v.action !== "no_order" ||
    v.namespace !== "SIMULATED" ||
    v.formal_eligibility !== false ||
    v.actual_account_used !== false ||
    v.position_guidance !== null ||
    !stamp(v.server_now) ||
    !object(v.account) ||
    !object(v.sources)
  )
    return false;
  const a = v.account;
  if (
    a.schema_version !== "persistent-simulated-portfolio-v1" ||
    a.namespace !== "SIMULATED" ||
    a.action !== "no_order" ||
    a.formal_eligibility !== false ||
    a.actual_account_used !== false ||
    a.ownership_verified !== false ||
    a.position_guidance !== null ||
    a.confirmed_fill_correction !== "UNSUPPORTED" ||
    a.source_scope !==
      "HASH_BOUND_REFERENCE_NOT_STRATEGY_OR_MARKET_PRICE_ADMISSION" ||
    !text(a.account_id) ||
    !object(a.account_context) ||
    a.account_context.namespace !== "SIMULATED" ||
    a.account_context.account_id !== a.account_id ||
    a.account_context.version !== a.schema_version ||
    !Number.isSafeInteger(a.revision) ||
    a.revision < 0 ||
    !Array.isArray(a.entries)
  )
    return false;
  if (
    !a.entries.every(
      (e: any) =>
        object(e) &&
        text(e.transaction_id) &&
        /^\d{6}$/.test(e.symbol) &&
        sleeve(e.sleeve) &&
        decimal(e.remaining_quantity) &&
        Number(e.remaining_quantity) >= 0 &&
        hash(e.fill_record_sha256) &&
        e.original_pit_proven === false &&
        e.advisory_eligible === false &&
        ((e.hypothesis === null && e.entry_confirmation_sha256 === null) ||
          (object(e.hypothesis) &&
            hash(e.entry_confirmation_sha256) &&
            text(e.hypothesis.thesis) &&
            text(e.hypothesis.hold_logic) &&
            strings(e.hypothesis.invalidation_conditions) &&
            text(e.hypothesis.research_version) &&
            text(e.hypothesis.strategy_version))),
    )
  )
    return false;
  if (a.status === "NOT_INITIALIZED") {
    if (a.portfolio !== null || a.revision !== 0 || a.entries.length)
      return false;
  } else if (a.status === "CONNECTED") {
    const p = a.portfolio;
    if (
      !object(p) ||
      p.action !== "no_order" ||
      p.revision !== a.revision ||
      !date(p.as_of) ||
      !decimal(p.cash_cny) ||
      !decimal(p.realized_pnl_cny) ||
      !Array.isArray(p.positions) ||
      !Array.isArray(p.trades)
    )
      return false;
    if (
      !p.positions.every(
        (row: any) =>
          object(row) &&
          /^\d{6}$/.test(row.symbol) &&
          text(row.exchange) &&
          decimal(row.quantity) &&
          decimal(row.cost_cny) &&
          Array.isArray(row.sleeves) &&
          row.sleeves.every(
            (s: any) =>
              object(s) &&
              sleeve(s.sleeve) &&
              decimal(s.quantity) &&
              decimal(s.cost_cny) &&
              decimal(s.sellable_quantity) &&
              (s.next_sell_session === null || date(s.next_sell_session)),
          ),
      )
    )
      return false;
    if (
      !p.trades.every(
        (t: any) => fill(t) && hash(t.record_sha256) && stamp(t.confirmed_at),
      )
    )
      return false;
    if (
      new Set(p.trades.map((t: any) => t.record_sha256)).size !==
        p.trades.length ||
      new Set(a.entries.map((e: any) => e.fill_record_sha256)).size !==
        a.entries.length ||
      !a.entries.every((e: any) =>
        p.trades.some(
          (t: any) =>
            t.side === "BUY" &&
            t.record_sha256 === e.fill_record_sha256 &&
            t.transaction_id === e.transaction_id &&
            t.symbol === e.symbol &&
            t.sleeve === e.sleeve,
        ),
      )
    )
      return false;
    const pending = p.pending_draft;
    if (
      pending !== null &&
      (!object(pending) ||
        pending.status !== "DRAFT_UNRECONFIRMED" ||
        !hash(pending.prepared_record_sha256) ||
        !fill(pending.fill) ||
        !decimal(pending.cash_cny) ||
        !decimal(pending.realized_pnl_cny))
    )
      return false;
  } else return false;
  const s = v.sources;
  if (
    !["AVAILABLE", "UNAVAILABLE"].includes(s.status) ||
    !Array.isArray(s.items) ||
    (s.status === "UNAVAILABLE" && s.items.length)
  )
    return false;
  const ids = new Set<string>();
  if (
    !s.items.every((item: any) => {
      if (!object(item) || ids.has(item.id)) return false;
      ids.add(item.id);
      const binding = item.candidate_binding;
      return (
        ((item.id === "core:600519" &&
          item.symbol === "600519" &&
          item.sleeve === "CORE_VALUE") ||
          (item.id === "swing:300750" &&
            item.symbol === "300750" &&
            item.sleeve === "HOTSPOT_SATELLITE")) &&
        item.scope === "REFERENCE_ONLY_NOT_APPROVAL" &&
        object(binding) &&
        text(binding.path) &&
        !/^(?:[\\/]|[a-z]+:)/i.test(binding.path) &&
        !binding.path.split(/[\\/]/).includes("..") &&
        hash(binding.sha256)
      );
    })
  )
    return false;
  return (
    v.mutation === undefined ||
    (object(v.mutation) &&
      [
        "initialize",
        "prepare-fill",
        "confirm-fill",
        "cancel-fill",
        "confirm-entry",
      ].includes(v.mutation.operation) &&
      hash(v.mutation.record_sha256))
  );
}
export class SimulatedRequestError extends Error {
  constructor(
    public status: number,
    public uncertain = false,
  ) {
    super(
      status === 409
        ? "记录版本或研究来源已变化（409），请刷新核对；不会自动重试。"
        : status === 422
          ? "输入或记账条件未通过（422），请检查日期、费用、可卖数量及原Entry来源。"
          : "未能核验服务器结果；写入可能已完成，请先刷新核对，或显式以同一请求重试。",
    );
  }
}
export function simulatedCommon(
  view: PersistentSimulatedWorkbench,
  key: string = crypto.randomUUID(),
): SimulatedWrite {
  return {
    confirmed_hypothetical: true,
    idempotency_key: key,
    expected_revision: view.account.revision,
  };
}
export async function readSimulatedPortfolio(): Promise<PersistentSimulatedWorkbench> {
  const response = await fetch(simulatedPortfolioUrl, {
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) throw new SimulatedRequestError(response.status);
  const result: unknown = await response.json();
  if (!verifiedPersistentSimulatedWorkbench(result))
    throw new SimulatedRequestError(0);
  return result;
}
export async function writeSimulatedPortfolio(
  operation: SimulatedOperation,
  body: SimulatedWrite,
): Promise<PersistentSimulatedWorkbench> {
  try {
    const response = await fetch(`${simulatedPortfolioUrl}/${operation}`, {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok)
      throw new SimulatedRequestError(response.status, response.status >= 500);
    const result: unknown = await response.json();
    if (
      !verifiedPersistentSimulatedWorkbench(result) ||
      result.mutation?.operation !== operation
    )
      throw new SimulatedRequestError(0, true);
    return result;
  } catch (error) {
    if (error instanceof SimulatedRequestError) throw error;
    throw new SimulatedRequestError(0, true);
  }
}
