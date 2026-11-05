import { useEffect, useRef, useState } from "react";
import { codeText } from "../utils/codes";
import { blockerText, normalizeEvidenceLines } from "../utils/researchDetail";
import { intents } from "../services/simulatedJourney";
import {
  dualJourneyUrl,
  dualManualRequest,
  dualSourcesMatch,
  dualTestPolicy,
  verifiedDualJourney,
} from "../services/sourceBoundDualJourney";
import type {
  DualAccountState,
  DualFormRow,
  SourceBoundDualPacket,
} from "../types/sourceBoundDualJourney";

function Reasons({ values }: { values: string[] }) {
  const rows = [...new Set(values)].map((raw) => {
    const label = codeText(raw) ?? blockerText(raw);
    return {
      raw,
      label: /\p{Script=Han}/u.test(raw)
        ? raw
        : /\p{Script=Han}/u.test(label)
          ? label
          : null,
    };
  });
  const unknown = rows.filter((row) => !row.label);
  return (
    <>
      <ul>
        {rows
          .filter((row) => row.label)
          .map((row) => (
            <li key={row.raw}>{row.label}</li>
          ))}
      </ul>
      {!!unknown.length && (
        <details>
          <summary>
            {unknown.length} 项原因暂未识别，不能视为通过（原文）
          </summary>
          <ul>
            {unknown.map((row) => (
              <li key={row.raw}>{row.raw}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
function ActionSlots({
  slots,
}: {
  slots: SourceBoundDualPacket["hotspot_case"]["action_slots"];
}) {
  const shared = [...new Set(slots[0]?.reasons ?? [])].filter((reason) =>
    slots.every((slot) => slot.reasons.includes(reason)),
  );
  return (
    <section aria-label="双来源六动作（非建议）">
      <p>共同缺口适用于每个动作，不表示没有机会：</p>
      <Reasons values={shared} />
      <ol style={{ paddingInlineStart: 20 }}>
        {slots.map((slot) => (
          <li key={slot.intent}>
            <strong>
              {intents[slot.intent as keyof typeof intents]}：
              {slot.outcome === "WAIT" ? "等待条件" : "不形成动作"}
            </strong>
            <Reasons
              values={slot.reasons.filter((reason) => !shared.includes(reason))}
            />
            <details>
              <summary>此动作全部原始原因</summary>
              <ul>
                {slot.reasons.map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
const riskLabels: Record<string, string> = {
  BLOCKED_PRIVATE_INPUT: "风险输入不全，尚未通过",
  RISK_REVIEW_CALCULATED: "演练风险已计算，不是正式准入",
  REVIEW_REQUIRED: "演练风险需复核",
};
function AccountResult({ value }: { value: DualAccountState }) {
  return (
    <section aria-label="同一临时账本结果">
      <p>
        同一账本模拟现金：{value.cash_cny} 元；累计假设费用：
        {value.confirmed_fees_cny} 元；按假设标价的总权益：
        {value.hypothetical_equity_cny ?? "未评估，不是零"} 元。
      </p>
      <p>
        CORE 剩余模拟现金：
        {value.sleeve_cash_review.sleeves?.CORE_VALUE?.cash_cny ??
          "未评估"}{" "}
        元；WAVE 剩余模拟现金：
        {value.sleeve_cash_review.sleeves?.HOTSPOT_SATELLITE?.cash_cny ??
          "未评估"}{" "}
        元。
      </p>
      <h5>同股合并持仓与风险</h5>
      <p>
        后台合并持仓不重复计入总资产；以下是假设标价，不是当前行情。缺少同股风险输入不等于风险为零。
      </p>
      <ul>
        {value.aggregate_holdings.map((row) => (
          <li key={row.symbol}>
            {row.symbol}：合计 {row.quantity} 股，假设市值{" "}
            {row.market_value_cny ?? "未评估"} 元。
          </li>
        ))}
      </ul>
      <p>
        {riskLabels[value.risk_review.status] ?? "风险状态未识别，不能视为通过"}
        ；不提供正式仓位建议。
      </p>
      <Reasons values={value.risk_review.blockers} />
      <details>
        <summary>完整风险与预算原始回执</summary>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {JSON.stringify(
            { risk: value.risk_review, sleeve_cash: value.sleeve_cash_review },
            null,
            2,
          )}
        </pre>
      </details>
    </section>
  );
}
const blankRow = (): DualFormRow => ({
  price: "10",
  fees: "5",
  quantity: "100",
  rationale: "",
  thesis: "",
  hold: "",
  breakers: "",
});

export function SourceBoundDualJourney() {
  const [data, setData] = useState<SourceBoundDualPacket>();
  const [read, setRead] = useState<SourceBoundDualPacket>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [date, setDate] = useState("");
  const [rows, setRows] = useState([blankRow(), blankRow()]);
  const busy = useRef(false),
    sequence = useRef(0),
    controller = useRef<AbortController>();
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort();
    },
    [],
  );
  async function run(body?: ReturnType<typeof dualManualRequest>) {
    if (busy.current) return;
    busy.current = true;
    const id = ++sequence.current;
    controller.current = new AbortController();
    setLoading(true);
    setData(undefined);
    setRead(undefined);
    setError(undefined);
    setConfirmed(false);
    try {
      const response = await fetch(dualJourneyUrl, {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.current.signal,
        ...(body
          ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }
          : {}),
      });
      if (response.status === 409) throw new Error("RESEARCH_VERSION_CHANGED");
      const packet: unknown = await response.json();
      if (
        !response.ok ||
        !verifiedDualJourney(packet) ||
        packet.manual_rehearsal.status !==
          (body ? "EXPLICIT_SIMULATED_RECORDS_ONLY" : "NOT_REQUESTED") ||
        (body &&
          !dualSourcesMatch(packet.source_identity, body.expected_sources))
      )
        throw new Error("UNVERIFIED_RESPONSE");
      if (id !== sequence.current) return;
      setData(packet);
      if (!body) setRead(packet);
    } catch (fault) {
      if (id !== sequence.current) return;
      setError(
        fault instanceof Error && fault.message === "RESEARCH_VERSION_CHANGED"
          ? "研究来源版本已变化或不可核验（409）。旧结果与确认已清空，请重新读取来源；不表示没有机会。"
          : "双来源或演练回执暂不可核验，旧结果已清空；不表示没有机会。未接入私人账户，不能视为策略通过。",
      );
    } finally {
      if (id === sequence.current) {
        setLoading(false);
        busy.current = false;
      }
    }
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current || !confirmed || !read) return;
    try {
      const body = dualManualRequest(read, date, rows);
      void run(body);
    } catch {
      setData(undefined);
      setRead(undefined);
      setConfirmed(false);
      setError(
        "日期、人工理由、价格或费用不完整；同股标价须一致。请重新读取来源并明确填写TEST_ONLY假设，不推断为没有机会。",
      );
    }
  }
  return (
    <section
      aria-label="双来源同账本模拟演练"
      style={{
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        marginBlock: 20,
      }}
    >
      <h3>C · 双来源同账本模拟演练（TEST_ONLY）</h3>
      <p>
        价值研究与封存波段资料共用一个临时模拟账本，不是双策略已通过。GET只读不建账；只有明确确认才请求演练，不读取私人账户、不下单、不保留模拟组合。
      </p>
      <button type="button" disabled={loading} onClick={() => void run()}>
        读取双来源（只读）
      </button>
      {loading && <p role="status">正在核验来源或临时演练，尚无本次结果。</p>}
      {error && <p role="alert">{error}</p>}
      {!data && !error && !loading && (
        <p>尚未读取双来源，不能判断；不会自动POST或成交。</p>
      )}
      {data && (
        <>
          <p>
            本次读取时点：{data.research_evaluated_at}
            ，不是研究更新日期或历史PIT证明。资格仍为false。
          </p>
          {data.core_cases.map((item) => (
            <section key={item.symbol} aria-label="CORE来源研究">
              <h4>CORE · {item.symbol} · 条件研究未批准</h4>
              <p>
                研究截至 {item.research.research_as_of}；估值基准{" "}
                {item.research.valuation_date}；置信度{" "}
                {item.research.confidence ?? "UNKNOWN（未提供）"}
                。不是今日公允价值或买入许可。
              </p>
              <ul>
                {normalizeEvidenceLines(item.research.thesis).map(
                  (row, index) => (
                    <li key={index}>{row.text}</li>
                  ),
                )}
              </ul>
              <ActionSlots slots={item.action_slots} />
            </section>
          ))}
          <section aria-label="WAVE封存来源">
            <h4>WAVE · {data.hotspot_case.symbol} · 历史封存参考</h4>
            <p>
              原假设入场时点：
              {data.hotspot_case.entry_reference.assumed_entry_at}；封存生成：
              {data.hotspot_case.entry_reference.generated_at}
              。当前信号/PIT均未通过；当前置信度UNKNOWN，不借用价值线LOW或历史保护价。
            </p>
            <p>
              原始Entry来自历史自主模拟，不是策略合格入场，也不是本次用户实际成交。
            </p>
            <ActionSlots slots={data.hotspot_case.action_slots} />
            <h5>历史后续对照（非当前操作）</h5>
            <ul>
              {data.hotspot_case.lifecycle_reviews.map((row, index) => (
                <li key={index}>
                  历史复核时点：{row.evaluated_at}，只供原始结构连续性核查。
                </li>
              ))}
            </ul>
          </section>
          <details>
            <summary>双来源版本、绑定及历史复核原文</summary>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {JSON.stringify(
                {
                  source_identity: data.source_identity,
                  entry: data.hotspot_case.entry_reference,
                  historical_reviews: data.hotspot_case.lifecycle_reviews,
                },
                null,
                2,
              )}
            </pre>
          </details>
          {data.manual_rehearsal.status === "NOT_REQUESTED" ? (
            <p>只读完成，尚未请求建账或模拟成交。</p>
          ) : (
            <>
              <h4>人工假设记账结果，不是系统建议</h4>
              <AccountResult value={data.manual_rehearsal.account_state!} />
              {data.manual_rehearsal.fills.map((row) => (
                <section
                  key={row.fill.transaction_id}
                  aria-label="模拟Entry与后续对照"
                >
                  <h5>
                    人工 {row.intent} · {row.fill.sleeve} · {row.fill.symbol}
                  </h5>
                  <p>
                    假设 {row.fill.quantity} 股、价格 {row.fill.price_cny}{" "}
                    元、费用 {row.fill.fees_cny} 元；日期 {row.fill.trade_date}
                    。请求数量 {row.requested_quantity}，未成交信息{" "}
                    {row.unfilled_quantity}，不是未结订单。
                  </p>
                  <p>
                    本次人工理由：{row.rationale}；引用原Entry交易：
                    {row.original_entry_transaction_id ??
                      (row.fill.side === "SELL"
                        ? "跨批实际消耗，逐笔见下方"
                        : "本笔开仓的事后重建")}
                    。
                  </p>
                  {row.original_entry_reference && (
                    <>
                      <p>
                        原始假设：
                        {row.original_entry_reference.narrative.thesis}
                      </p>
                      <p>
                        持有逻辑：
                        {row.original_entry_reference.narrative.hold_logic}
                      </p>
                      <p>
                        失效条件：
                        {row.original_entry_reference.narrative.invalidation_conditions.join(
                          "；",
                        )}
                      </p>
                    </>
                  )}
                  {row.consumed_original_entries?.map((entry) => (
                    <section
                      key={entry.transaction_id}
                      aria-label="卖出实际消耗原Entry"
                    >
                      <p>
                        原Entry交易：{entry.transaction_id}；本笔消耗{" "}
                        {entry.quantity} 股。
                      </p>
                      <p>
                        原始假设：
                        {entry.original_entry_reference.narrative.thesis}
                      </p>
                      <p>
                        持有逻辑：
                        {entry.original_entry_reference.narrative.hold_logic}
                      </p>
                      <p>
                        失效条件：
                        {entry.original_entry_reference.narrative.invalidation_conditions.join(
                          "；",
                        )}
                      </p>
                      <p>
                        对应人工卖出理由：{entry.manual_rationale}
                        。仅人工理由与重建假设对照，不是策略批准。
                      </p>
                    </section>
                  ))}
                  <p>
                    记账前现金 {row.before.cash_cny} → 记账后{" "}
                    {row.after.cash_cny}{" "}
                    元（服务器回执）；原始PIT和原Entry建议资格仍为false。
                  </p>
                  <Reasons values={row.entry_blockers} />
                </section>
              ))}
              <p>
                回执确认：重启一致、临时账本已清理。仅验证本次假设记账，不证明策略有效、正式仓位或真实Entry成立。
              </p>
            </>
          )}
        </>
      )}
      <details>
        <summary>显式TEST_ONLY双仓假设（不是账户IPS）</summary>
        <p>
          沿用既有默认：初始10000元；CORE5000、HOTSPOT3000、预留2000。每仓100股、费用5元、价格10元仅为可编辑假设，不是行情或仓位建议。完整政策固定如下，资产/预算/风控由后台计算。
        </p>
        <details>
          <summary>完整既有TEST_ONLY政策</summary>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(dualTestPolicy(date || "待填写日期"), null, 2)}
          </pre>
        </details>
        <form onSubmit={submit}>
          <fieldset
            disabled={loading}
            style={{ minWidth: 0, border: 0, padding: 0 }}
          >
            <label>
              演练开户及成交日期
              <input
                type="date"
                required
                value={date}
                onChange={(event) => setDate(event.target.value)}
                style={{ width: "100%", boxSizing: "border-box" }}
              />
            </label>
            {rows.map((row, index) => (
              <fieldset key={index} style={{ minWidth: 0, marginBlock: 12 }}>
                <legend>
                  {index === 0 ? "CORE_VALUE" : "HOTSPOT_SATELLITE"} ·{" "}
                  {index === 0
                    ? (read?.core_cases[0].symbol ?? "待读取来源")
                    : (read?.hotspot_case.symbol ?? "待读取来源")}{" "}
                  人工BUY假设
                </legend>
                {(
                  [
                    ["price", "假设价格（不是市场价）"],
                    ["fees", "假设总费用"],
                    ["quantity", "假设股数"],
                    ["rationale", "本次人工演练理由"],
                    ["thesis", "原Entry投资逻辑假设"],
                    ["hold", "持有逻辑假设"],
                    ["breakers", "失效条件假设"],
                  ] as const
                ).map(([field, label]) => (
                  <label
                    key={field}
                    style={{ display: "block", marginBlock: 8 }}
                  >
                    {label}
                    <input
                      required
                      value={row[field]}
                      onChange={(event) =>
                        setRows((current) =>
                          current.map((value, i) =>
                            i === index
                              ? { ...value, [field]: event.target.value }
                              : value,
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
              </fieldset>
            ))}
            <label>
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              我明确确认：仅TEST_ONLY人工假设，不是实际成交、原始PIT
              Entry或策略批准
            </label>
            <p>
              来源证券由当前只读GET确定；再次提交前须重新读取，不可指定服务器路径或授权。
            </p>
            <button type="submit" disabled={!confirmed || !read || loading}>
              确认运行临时双仓演练
            </button>
          </fieldset>
        </form>
      </details>
    </section>
  );
}
