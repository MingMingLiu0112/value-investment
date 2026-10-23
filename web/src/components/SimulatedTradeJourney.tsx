import { useRef, useState } from "react";
import { Alert, Button, Table } from "antd";

type State = { cash_cny: string; confirmed_fees_cny: string };
type SimulatedPosition = {
  symbol: string;
  quantity: string;
  cost_cny: string;
  sleeves: {
    sleeve: "CORE_VALUE";
    sellable_quantity: string;
    next_sell_session?: string | null;
  }[];
};
type Journey = {
  schema_version: "simulated-trade-journey-v1";
  status: "SIMULATED_JOURNEY_COMPLETE";
  approval_changed: false;
  namespace: "SIMULATED";
  action: "no_order";
  actual_account_used: false;
  strategy_validated: false;
  broker_execution_permission: false;
  steps: {
    label: string;
    sleeve?: string;
    rationale?: string;
    reason?: string;
    quantity?: string;
    price_cny?: string;
    before: State;
    after: State;
  }[];
  checks: Record<string, boolean>;
  assumptions: { entry_thesis: string; initial_cash_cny: string };
};

const labels: Record<string, string> = {
  CORE_BUY: "价值仓建仓",
  HOTSPOT_BUY: "热点仓建仓",
  CORE_ADD: "价值仓加仓",
  HOLD: "继续持有",
  T_PLUS_ONE_REJECTED: "拒绝当日卖出",
  CORE_REDUCE: "价值仓减仓",
  CORE_EXIT: "价值仓退出",
  HOTSPOT_EXIT: "热点仓退出",
};
const reasons: Record<string, string> = {
  CORE_BUY:
    "模拟假设：现金创造能力稳定，假设价值高于价格，且价值仓预算允许建立初始仓位。不是对该股票的实际判断。",
  HOTSPOT_BUY:
    "模拟假设：突破结构满足预设条件，止损压力和热点仓预算允许建仓；不表示真实突破策略已验证。",
  CORE_ADD:
    "模拟假设：价格下降，但企业价值、原始逻辑和置信度未变，且合并持仓风险仍允许；不是因为下跌就加仓。",
  HOLD: "模拟假设：原始现金创造逻辑仍成立，没有出现失效事实，因此不新增交易。",
  T_PLUS_ONE_REJECTED:
    "当日买入股份尚不可卖出，现有成交服务拒绝该请求，现金与持仓保持不变。",
  CORE_REDUCE:
    "模拟假设：部分价值预期兑现，需要降低暴露；剩余投资逻辑尚未破坏。",
  CORE_EXIT:
    "模拟假设：新证据破坏了当初买入的现金创造逻辑，因此退出，不以涨跌幅作为唯一理由。",
  HOTSPOT_EXIT:
    "模拟假设：突破失败，满足原定保护条件，并已到可卖交易日；假设成交价不代表保证能够止损。",
};

type Binding = { path: string; sha256: string };
type SourceCase = {
  symbol: string;
  company_name: string;
  action: "no_order";
  research: {
    candidate_binding: Binding;
    research_version: string;
    model_context: Record<string, unknown>;
    generated_at: string;
    replayed_at?: string | null;
    research_as_of: string;
    valuation_date: string;
    available_at: string;
    computed_at: string;
    thesis: unknown;
    confidence?: string;
    counter_evidence?: unknown;
    thesis_breakers: unknown;
    scope: "SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL";
  };
  plan: {
    research_version: string;
    signal_state: string;
    candidate_action: string;
    verification_scope: string;
  };
  evaluation: {
    symbol: string;
    action: "no_order";
    strategy: "CORE_VALUE";
    decision_action: string;
    eligibility: false;
    review_quantity: null;
    position_range: null;
  };
  action_slots: {
    intent: string;
    outcome: string;
    strategy_verdict: string;
    reasons: string[];
    formal_eligibility: false;
    review_quantity: null;
    action: "no_order";
  }[];
};
type ManualRow = {
  symbol: string;
  side: "BUY" | "SELL";
  scope: string;
  fill: {
    symbol: string;
    side: string;
    quantity: string;
    price_cny: string;
    fees_cny: string;
    trade_date: string;
    next_sell_session?: string;
  };
  source_candidate_binding: Binding;
  fill_record_sha256: string;
  recorded_at: string;
  original_entry_advisory_eligible: false;
  execution_price_scope: string;
  snapshot_status: string;
  historical_reference_status: string;
  historical_reference_scope: string | null;
  t1_negative_status?: string;
  confirmation_idempotent: true;
  prepared_cash_unchanged: true;
};
export type SourceBoundJourney = {
  schema_version: "source-bound-simulated-trade-journey-v1";
  namespace: "SIMULATED";
  research_namespace: "PUBLIC_SOURCE_BOUND";
  action: "no_order";
  scope: "PUBLIC_RESEARCH_WITH_OPTIONAL_ISOLATED_MANUAL_ACCOUNTING";
  research_evaluated_at: string;
  strategy_validated: false;
  approval_changed: false;
  broker_execution_permission: false;
  personal_risk_evaluated: false;
  position_guidance: null;
  source_files_verified: number;
  cases: SourceCase[];
  manual_rehearsal: {
    status: "NOT_REQUESTED" | "EXPLICIT_SIMULATED_RECORDS_ONLY";
    fills: ManualRow[];
    account_state: (State & { positions?: SimulatedPosition[] }) | null;
    journal_receipt: { sha256: string; retained: false } | null;
    actual_account_used: false;
    temporary_journal_removed: true;
    restart_equal?: true;
    same_session_sell_rejected?: boolean | null;
    t1_negative_checks?: number;
  };
};
const intents = {
  BUY: "买入",
  ADD: "加仓",
  HOLD: "持有",
  REDUCE: "减仓",
  EXIT: "退出",
  WAIT: "等待",
};
const object = (value: unknown): value is Record<string, any> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string =>
  typeof value === "string" && !!value.trim();
const decimal = (value: unknown): value is string =>
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
function day(value: unknown): value is string {
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

function Lines({ value }: { value: unknown }) {
  const rows = (Array.isArray(value) ? value : [value]).flatMap((item) =>
    typeof item === "string"
      ? [item]
      : object(item) && typeof item.text === "string"
        ? [item.text]
        : [],
  );
  return rows.length ? (
    <ul>
      {rows.map((line, index) => (
        <li key={index}>{line}</li>
      ))}
    </ul>
  ) : (
    <p>未提供可读依据，不能据此评价。</p>
  );
}

type ExpectedCandidate = {
  symbol: string;
  candidate_binding: Binding;
  research_version: string;
};

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
const reasonLabels: Record<string, string> = {
  ORIGINAL_ENTRY_AND_PERSONAL_RISK_NOT_ESTABLISHED:
    "原入场依据及个人风险条件尚未建立",
};
const emptyFill = () => ({
  transaction_id: "",
  side: "BUY",
  symbol: "600519",
  quantity: "100",
  price_cny: "",
  fees_cny: "",
  trade_date: "",
  historical: false,
});

function SourceBoundJourneyPanel() {
  const [expectedCandidates, setExpectedCandidates] =
    useState<ExpectedCandidate[]>();
  const [data, setData] = useState<SourceBoundJourney>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false),
    busy = useRef(false);
  const [initialCash, setInitialCash] = useState("100000");
  const [fills, setFills] = useState([emptyFill()]);
  const [confirmed, setConfirmed] = useState(false);
  async function run(body?: unknown) {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError(undefined);
    setData(undefined);
    setExpectedCandidates(undefined);
    try {
      const response = await fetch(
        `/api/v1/simulated-trade-journey${body ? "" : "?mode=source_bound"}`,
        {
          cache: "no-store",
          credentials: "same-origin",
          ...(body
            ? {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
              }
            : {}),
        },
      );
      const packet: unknown = await response.json();
      if (
        !response.ok ||
        !verifiedSourceBoundJourney(packet) ||
        (body
          ? packet.manual_rehearsal.status !== "EXPLICIT_SIMULATED_RECORDS_ONLY"
          : packet.manual_rehearsal.status !== "NOT_REQUESTED")
      )
        throw new Error("Invalid source journey");
      if (
        body &&
        (!object(body) ||
          !sourceBoundCandidatesMatch(packet, body.expected_candidates))
      )
        throw new Error("Candidate changed");
      setData(packet);
      if (!body)
        setExpectedCandidates(
          packet.cases.map((item) => ({
            symbol: item.symbol,
            candidate_binding: { ...item.research.candidate_binding },
            research_version: item.research.research_version,
          })),
        );
    } catch {
      setError(
        "真实来源资料或模拟记录暂不可核验，旧结果已清空；这不代表没有机会，私人账户未被修改。请重新读取当前候选后再确认。",
      );
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!confirmed || loading) return;
    if (!expectedCandidates?.length) {
      setError("请先重新只读读取当前两家候选，再确认模拟记账。");
      return;
    }
    setData(undefined);
    setError(undefined);
    if (
      !decimal(initialCash) ||
      Number(initialCash) <= 0 ||
      fills.some(
        (row) =>
          !decimal(row.price_cny) ||
          Number(row.price_cny) <= 0 ||
          !decimal(row.fees_cny) ||
          !/^\d+$/.test(row.quantity) ||
          Number(row.quantity) <= 0 ||
          !day(row.trade_date) ||
          (row.side === "SELL" && row.historical),
      )
    ) {
      setError(
        "请填写有效的模拟现金、股数、手工价格、费用及日期；卖出不能确认历史入场引用。",
      );
      return;
    }
    const manual_fills = fills.map((row) => ({
      fill: {
        transaction_id:
          row.transaction_id.trim() ||
          `SIMULATED-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("")}`,
        side: row.side,
        sleeve: "CORE_VALUE",
        symbol: row.symbol,
        exchange: "SSE",
        quantity: row.quantity,
        price_cny: row.price_cny,
        fees_cny: row.fees_cny,
        trade_date: row.trade_date,
        ...(row.side === "BUY" ? { trading_unit: "100" } : {}),
      },
      ...(row.historical
        ? { research_reference: "HISTORICAL_RECONSTRUCTION" }
        : {}),
    }));
    setConfirmed(false);
    void run({
      confirmed_hypothetical: true,
      initial_cash_cny: initialCash,
      expected_candidates: expectedCandidates,
      manual_fills,
    });
  }
  return (
    <section
      aria-label="真实来源研究与模拟记录"
      style={{ minWidth: 0, marginBlock: 20, overflowWrap: "anywhere" }}
    >
      <h3>A · 真实来源研究与模拟记录</h3>
      <p>
        只读读取两家公司价值样本；未建立真实来源热点成交或双策略仓位验证。输入不足是待研究，不等于没有机会。
      </p>
      <Button
        aria-label="读取真实来源研究（只读）"
        aria-busy={loading}
        onClick={() => void run()}
        disabled={loading}
        loading={loading}
      >
        读取真实来源研究（只读）
      </Button>
      {loading && (
        <p role="status">正在核验来源／显式模拟请求，尚无本次可用结果。</p>
      )}
      {error && <p role="alert">{error}</p>}
      {!data && !loading && !error && (
        <p>尚未读取研究；不会自动记账或成交，不代表没有机会。</p>
      )}
      {data && (
        <>
          <p>
            本次来源核验：{data.research_evaluated_at}
            。这是读取时点，不是研究更新日期或原始 PIT 证明。
          </p>
          {!data.cases.length && (
            <p role="status">
              当前响应未提供公司研究，尚不能评价；不代表没有机会。
            </p>
          )}
          {data.cases.map((item) => (
            <section
              key={item.symbol}
              aria-label={`${item.company_name}来源研究`}
            >
              <h4>
                {item.company_name} {item.symbol} · 条件研究，非交易批准
              </h4>
              <p>
                研究截至：{item.research.research_as_of}；估值日：
                {item.research.valuation_date}
              </p>
              <p>
                研究版本：{item.research.research_version}；模型：
                {String(item.research.model_context.model_id)}／
                {String(item.research.model_context.model_version)}
              </p>
              <h5>投资逻辑引用（未批准）</h5>
              <Lines value={item.research.thesis} />
              <p>
                模型置信度：{item.research.confidence ?? "未提供，不能推定"}
                ；来源研究仍非批准。
              </p>
              <h5>反证与冲突</h5>
              <Lines value={item.research.counter_evidence} />
              <h5>逻辑失效条件</h5>
              <Lines value={item.research.thesis_breakers} />
              <Table
                size="small"
                rowKey="intent"
                pagination={false}
                scroll={{ x: 560 }}
                dataSource={item.action_slots}
                columns={[
                  {
                    title: "动作槽（非建议）",
                    render: (_, row) =>
                      intents[row.intent as keyof typeof intents],
                  },
                  {
                    title: "实际结果",
                    render: (_, row) =>
                      row.outcome === "WAIT"
                        ? "WAIT · 等待条件"
                        : "NO_ACTION · 不形成动作",
                  },
                  {
                    title: "当前原因",
                    render: (_, row) => (
                      <ul>
                        {row.reasons.map((reason, index) => (
                          <li key={index}>{reasonLabels[reason] ?? reason}</li>
                        ))}
                      </ul>
                    ),
                  },
                ]}
              />
              <details>
                <summary>来源绑定与各类日期</summary>
                <p>候选：{item.research.candidate_binding.path}</p>
                <p>SHA-256：{item.research.candidate_binding.sha256}</p>
                <p>
                  候选生成：{item.research.generated_at}；重放：
                  {item.research.replayed_at ?? "未提供"}；资料可用：
                  {item.research.available_at}；计算：
                  {item.research.computed_at}
                </p>
              </details>
            </section>
          ))}
          {data.manual_rehearsal.status === "NOT_REQUESTED" ? (
            <p>未请求模拟记录；本次只读，不初始化账本、不成交。</p>
          ) : (
            <section aria-label="显式模拟记账结果">
              <h4>显式模拟记账结果 · 不是系统建议</h4>
              <p>
                模拟现金 {data.manual_rehearsal.account_state!.cash_cny}{" "}
                元；累计费用{" "}
                {data.manual_rehearsal.account_state!.confirmed_fees_cny}{" "}
                元。非真实账户余额。
              </p>
              {data.manual_rehearsal.account_state!.positions ? (
                <ul>
                  {data.manual_rehearsal.account_state!.positions!.map(
                    (position, index) => (
                      <li key={index}>
                        模拟持仓 {position.symbol}：{position.quantity}{" "}
                        股，账面成本 {position.cost_cny} 元。
                        {position.sleeves.map((sleeve, i) => (
                          <span key={i}>
                            价值模拟仓可卖 {sleeve.sellable_quantity}{" "}
                            股；服务器返回下一可卖日{" "}
                            {sleeve.next_sell_session ?? "未提供"}。
                          </span>
                        ))}
                      </li>
                    ),
                  )}
                </ul>
              ) : (
                <p>模拟持仓细项未返回，不能推断空仓。</p>
              )}
              <ul>
                {data.manual_rehearsal.fills.map((row, index) => (
                  <li key={index}>
                    手工模拟{row.side === "BUY" ? "买入" : "卖出"} {row.symbol}
                    ：{row.fill.quantity} 股，用户假设价 {row.fill.price_cny}{" "}
                    元，费用 {row.fill.fees_cny} 元，假设成交日{" "}
                    {row.fill.trade_date}。
                    <p>
                      记录时点：{row.recorded_at}；来源候选：
                      {row.source_candidate_binding.sha256}
                    </p>
                    <p>
                      记录时研究快照状态：
                      {row.snapshot_status ===
                      "EXACT_PUBLICATION_RECORDING_TIME_REFERENCE_NOT_PRETRADE"
                        ? "已记录当时发布版本的引用，不是成交前已知证明"
                        : row.snapshot_status ===
                            "SNAPSHOT_UNAVAILABLE_NO_EXACT_PUBLISHED_RESEARCH"
                          ? "精确发布研究快照不可用，未补造"
                          : "状态未识别，不视为已核验"}
                      （不等于成交前已知）；历史引用：
                      {row.historical_reference_scope ===
                      "NOT_ORIGINAL_PIT_ENTRY"
                        ? "历史研究重建，不是原始 PIT Entry"
                        : "未请求"}
                      。
                    </p>
                    <p>
                      T+1 反例：
                      {row.t1_negative_status ===
                      "REJECTED_WITHOUT_JOURNAL_WRITE"
                        ? "当日卖出被拒绝且未写账本"
                        : row.t1_negative_status ===
                            "NOT_APPLICABLE_OLDER_SELLABLE_LOTS"
                          ? "已有较早可卖股份，本条不适用"
                          : "本条未评估，不等于通过"}
                    </p>
                  </li>
                ))}
              </ul>
              <p>
                记账重启一致；临时账本已清理。以上仅验证本次模拟记账，不授予策略、仓位或原入场资格。
              </p>
            </section>
          )}
        </>
      )}
      <details>
        <summary>显式模拟成交记账（仅价值样本）</summary>
        <p>
          价格和费用必须由你填写，不能用真实行情自动假设成交。每次提交都是新的临时账户，不延续上次模拟余额；买入后的可卖日由服务器交易日历派生。
        </p>
        <form onSubmit={submit} style={{ minWidth: 0 }}>
          <fieldset
            disabled={loading}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <label>
              初始模拟现金（元）
              <input
                aria-label="初始模拟现金（元）"
                value={initialCash}
                onChange={(e) => setInitialCash(e.target.value)}
                required
                style={{ width: "100%", boxSizing: "border-box" }}
              />
            </label>
            {fills.map((row, index) => (
              <fieldset
                key={index}
                style={{
                  minWidth: 0,
                  margin: "12px 0",
                  padding: 8,
                  border: "1px solid #ddd",
                }}
              >
                <legend>模拟记录 {index + 1}</legend>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fit,minmax(min(100%,200px),1fr))",
                    gap: 8,
                  }}
                >
                  <label>
                    方向
                    <select
                      aria-label={`记录${index + 1}方向`}
                      value={row.side}
                      onChange={(e) =>
                        setFills((items) =>
                          items.map((item, i) =>
                            i === index
                              ? {
                                  ...item,
                                  side: e.target.value,
                                  historical: false,
                                }
                              : item,
                          ),
                        )
                      }
                    >
                      <option value="BUY">手工模拟买入</option>
                      <option value="SELL">手工模拟卖出</option>
                    </select>
                  </label>
                  <label>
                    公司
                    <select
                      aria-label={`记录${index + 1}公司`}
                      value={row.symbol}
                      onChange={(e) =>
                        setFills((items) =>
                          items.map((item, i) =>
                            i === index
                              ? { ...item, symbol: e.target.value }
                              : item,
                          ),
                        )
                      }
                    >
                      <option value="600519">贵州茅台 600519</option>
                      <option value="600887">伊利股份 600887</option>
                    </select>
                  </label>
                  {(
                    [
                      ["transaction_id", "模拟ID（留空在提交时生成）"],
                      ["quantity", "股数"],
                      ["price_cny", "手工假设价（元）"],
                      ["fees_cny", "手工费用（元）"],
                      ["trade_date", "假设成交日"],
                    ] as const
                  ).map(([key, title]) => (
                    <label key={key}>
                      {title}
                      <input
                        aria-label={`记录${index + 1}${title}`}
                        type={key === "trade_date" ? "date" : "text"}
                        value={row[key]}
                        required={key !== "transaction_id"}
                        onChange={(e) =>
                          setFills((items) =>
                            items.map((item, i) =>
                              i === index
                                ? { ...item, [key]: e.target.value }
                                : item,
                            ),
                          )
                        }
                        style={{
                          width: "100%",
                          minWidth: 0,
                          boxSizing: "border-box",
                        }}
                      />
                    </label>
                  ))}
                </div>
                <label style={{ display: "block" }}>
                  <input
                    type="checkbox"
                    disabled={row.side !== "BUY"}
                    checked={row.historical}
                    onChange={(e) =>
                      setFills((items) =>
                        items.map((item, i) =>
                          i === index
                            ? { ...item, historical: e.target.checked }
                            : item,
                        ),
                      )
                    }
                  />
                  另行引用历史研究（重建，非原始 PIT Entry）
                </label>
                {fills.length > 1 && (
                  <Button
                    onClick={() =>
                      setFills((items) => items.filter((_, i) => i !== index))
                    }
                  >
                    移除此条模拟记录
                  </Button>
                )}
              </fieldset>
            ))}
            <Button
              onClick={() => setFills((items) => [...items, emptyFill()])}
            >
              添加模拟记录
            </Button>
            <label style={{ display: "block", marginBlock: 12 }}>
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              仅模拟记账，不是实际成交或策略批准
            </label>
            <Button
              htmlType="submit"
              disabled={!confirmed || !expectedCandidates?.length}
            >
              提交显式模拟记录
            </Button>
          </fieldset>
        </form>
      </details>
    </section>
  );
}

export function verifiedSimulatedJourney(body: Journey): boolean {
  return (
    body?.namespace === "SIMULATED" &&
    body.schema_version === "simulated-trade-journey-v1" &&
    body.status === "SIMULATED_JOURNEY_COMPLETE" &&
    body.approval_changed === false &&
    body.action === "no_order" &&
    body.actual_account_used === false &&
    body.strategy_validated === false &&
    body.broker_execution_permission === false &&
    decimal(body.assumptions?.initial_cash_cny) &&
    Array.isArray(body.steps) &&
    body.steps.every(
      (row) =>
        object(row) &&
        object(row.before) &&
        object(row.after) &&
        decimal(row.before.cash_cny) &&
        decimal(row.before.confirmed_fees_cny) &&
        decimal(row.after.cash_cny) &&
        decimal(row.after.confirmed_fees_cny),
    ) &&
    body.steps.map((row) => row.label).join(",") ===
      Object.keys(labels).join(",") &&
    [
      "confirmation_idempotency",
      "restart_equality",
      "same_day_sell_rejected",
      "temporary_journal_removed",
    ].every((key) => body.checks?.[key] === true)
  );
}

export function SimulatedTradeJourney() {
  const [data, setData] = useState<Journey>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  async function run() {
    setLoading(true);
    setError(undefined);
    setData(undefined);
    try {
      const response = await fetch("/api/v1/simulated-trade-journey", {
        cache: "no-store",
      });
      const body: Journey = await response.json();
      if (!response.ok || !verifiedSimulatedJourney(body)) {
        throw new Error("模拟闭环核验未通过，不展示为已完成。");
      }
      setData(body);
    } catch {
      setError("模拟流程暂不可核验，请检查系统状态；私人账户未被修改。");
    } finally {
      setLoading(false);
    }
  }
  return (
    <div style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}>
      <SourceBoundJourneyPanel />
      <section
        aria-label="纯假设计账演练"
        style={{ marginBlock: 20, minWidth: 0 }}
      >
        <h3>B · 纯假设计账演练</h3>
        <Alert
          type="info"
          showIcon
          message="SIMULATED · 仅验收产品流程，不是实盘建议"
          description="固定假设价格、研究逻辑与费率；临时账本结束后删除，不读取或修改私人账户，不证明选股有效。"
        />
        <Button
          aria-label="运行纯假设计账演练"
          aria-busy={loading}
          onClick={run}
          loading={loading}
          style={{ marginBlock: 12 }}
        >
          运行纯假设计账演练
        </Button>
        {error && <p role="alert">{error}</p>}
        {data && (
          <>
            <p>
              初始模拟现金 {data.assumptions.initial_cash_cny}{" "}
              元；以下两策略共用同一现金账户。
            </p>
            <Table
              size="small"
              rowKey="label"
              pagination={false}
              scroll={{ x: 640 }}
              dataSource={data.steps}
              columns={[
                {
                  title: "步骤",
                  render: (_, row) => labels[row.label] ?? row.label,
                },
                { title: "模拟股数", dataIndex: "quantity" },
                { title: "假设价格", dataIndex: "price_cny" },
                { title: "之前现金", render: (_, row) => row.before.cash_cny },
                { title: "之后现金", render: (_, row) => row.after.cash_cny },
                {
                  title: "累计费用",
                  render: (_, row) => row.after.confirmed_fees_cny,
                },
              ]}
              expandable={{
                expandedRowRender: (row) => (
                  <p style={{ overflowWrap: "anywhere" }}>
                    {reasons[row.label] ?? row.rationale ?? row.reason}
                  </p>
                ),
              }}
            />
            <p>
              已验证：共用现金、成交确认幂等、T+1
              拒绝、重启一致性、临时账本清理。模拟动作不改变当前正式研究准入。
            </p>
          </>
        )}
      </section>
    </div>
  );
}
