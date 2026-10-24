import { useRef, useState } from "react";
import { SourceBoundDualJourney } from "./SourceBoundDualJourney";
import { Alert, Button, Table } from "antd";
import { codeText } from "../utils/codes";
import { blockerText } from "../utils/researchDetail";
import type {
  Journey,
  ExpectedCandidate,
  SourceBoundJourney,
} from "../types/simulatedJourney";
import {
  intents,
  object,
  decimal,
  day,
  verifiedSourceBoundJourney,
  sourceBoundCandidatesMatch,
} from "../services/simulatedJourney";
export {
  verifiedSourceBoundJourney,
  sourceBoundCandidatesMatch,
} from "../services/simulatedJourney";
export type { SourceBoundJourney } from "../types/simulatedJourney";
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
const reasonLabels: Record<string, string> = {
  ORIGINAL_ENTRY_AND_PERSONAL_RISK_NOT_ESTABLISHED:
    "原入场依据及个人风险条件尚未建立",
};

function ReadableReasons({ values }: { values: string[] }) {
  const rows = [...new Set(values)].map((raw) => {
    const existing = blockerText(raw);
    return {
      raw,
      label:
        reasonLabels[raw] ??
        codeText(raw) ??
        (/\p{Script=Han}/u.test(raw)
          ? raw
          : /\p{Script=Han}/u.test(existing)
            ? existing
            : null),
    };
  });
  const unknown = rows.filter((row) => row.label === null);
  return (
    <>
      {rows.some((row) => row.label !== null) && (
        <ul style={{ paddingInlineStart: 20, marginBlock: 8 }}>
          {rows
            .filter((row) => row.label !== null)
            .map((row) => (
              <li key={row.raw}>{row.label}</li>
            ))}
        </ul>
      )}
      {unknown.length > 0 && (
        <details>
          <summary>
            另有 {unknown.length}{" "}
            项未识别原因：含义待核验，仍为否定前提（展开原文）
          </summary>
          <ul style={{ paddingInlineStart: 20 }}>
            {unknown.map((row) => (
              <li key={row.raw}>
                <code>{row.raw}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

/** Presentation only: exact shared strings, never inference or decision changes. */
export function SourceActionReasons({
  slots,
}: {
  slots: SourceBoundJourney["cases"][number]["action_slots"];
}) {
  const occurrences = new Map<string, number[]>();
  slots.forEach((slot, index) => {
    for (const reason of new Set(slot.reasons))
      occurrences.set(reason, [...(occurrences.get(reason) ?? []), index]);
  });
  const groups = new Map<string, { actions: number[]; reasons: string[] }>();
  for (const [reason, actions] of occurrences) {
    if (actions.length < 2) continue;
    const key = actions.join(",");
    const group: { actions: number[]; reasons: string[] } = groups.get(key) ?? {
      actions,
      reasons: [],
    };
    group.reasons.push(reason);
    groups.set(key, group);
  }
  const shared = [...groups.values()];
  const sharedSet = new Set(shared.flatMap((group) => group.reasons));
  return (
    <section
      aria-label="六动作核验（非建议）"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h5>六动作核验（非建议）</h5>
      <p>
        <strong>共同未满足条件（按适用动作核对）</strong>
      </p>
      {shared.length > 0 ? (
        shared.map((group, index) => (
          <div key={group.actions.join(",")}>
            <p>
              共同条件第 {index + 1} 组 · 适用动作：
              {group.actions
                .map(
                  (action) =>
                    intents[slots[action].intent as keyof typeof intents],
                )
                .join("、")}
            </p>
            <ReadableReasons values={group.reasons} />
          </div>
        ))
      ) : (
        <p>没有可合并的共同原因，请分别核对各动作；不代表条件通过。</p>
      )}
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {slots.map((slot, slotIndex) => {
          const specific = [...new Set(slot.reasons)].filter(
            (reason) => !sharedSet.has(reason),
          );
          const intent = intents[slot.intent as keyof typeof intents];
          const applicable = shared.flatMap((group, index) =>
            group.actions.includes(slotIndex) ? [index + 1] : [],
          );
          return (
            <li
              key={slot.intent}
              aria-label={`${intent}动作核验`}
              style={{
                minWidth: 0,
                paddingBlock: 12,
                borderTop: "1px solid #e5e7eb",
              }}
            >
              <h5 style={{ marginBlock: "0 8px" }}>
                {intent} ·{" "}
                <span>
                  {slot.outcome === "WAIT"
                    ? "WAIT · 等待条件"
                    : "NO_ACTION · 不形成动作"}
                </span>
              </h5>
              {specific.length > 0 ? (
                <ReadableReasons values={specific} />
              ) : (
                <p>本动作没有新增特有原因，不代表获准。</p>
              )}
              {applicable.length > 0 && (
                <p>
                  本动作受上列共同条件第 {applicable.join("、")}{" "}
                  组全部原因约束。
                </p>
              )}
              <details>
                <summary>
                  本动作完整原始原因（{slot.reasons.length}{" "}
                  项，保留原顺序及重复）
                </summary>
                <ol style={{ paddingInlineStart: 20 }}>
                  {slot.reasons.map((reason, index) => (
                    <li key={index}>
                      <code>{reason}</code>
                    </li>
                  ))}
                </ol>
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
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
              <SourceActionReasons slots={item.action_slots} />
              <details>
                <summary>来源绑定、研究版本与各类日期</summary>
                <p>
                  研究版本：{item.research.research_version}；模型：
                  {String(item.research.model_context.model_id)}／
                  {String(item.research.model_context.model_version)}
                </p>
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
                    {row.fill.trade_date}。<p>记录时点：{row.recorded_at}</p>
                    <details>
                      <summary>模拟记录来源绑定（非成交前已知证明）</summary>
                      <p>候选：{row.source_candidate_binding.path}</p>
                      <p>SHA-256：{row.source_candidate_binding.sha256}</p>
                    </details>
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
      <SourceBoundDualJourney />
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
