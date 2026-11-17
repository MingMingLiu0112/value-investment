import { useState } from "react";
import type { HotspotSampleReview as Sample } from "../types/api";

const shown = (value: unknown) => (value == null ? "不可评" : String(value));
const flag = (value: boolean | null) =>
  value == null ? "不可评" : value ? "是" : "否";
const reasons: Record<string, string> = {
  DATED_TRADABILITY_AND_SUSPENSION: "缺少历史可交易及停牌证据",
  DATED_PRICE_LIMITS: "缺少当日涨跌停约束",
  KNOWN_AT_LIQUIDITY_BUDGET: "缺少当时可得的流动性预算",
  EXPLICIT_QUANTITY_CASH_AND_LIMIT: "未绑定交易数量、现金和限价",
  DATED_COST_AND_SLIPPAGE_BASIS: "缺少历史费用与滑点依据",
  CORPORATE_ACTION_REVIEW: "公司行动与价格可比性未核验",
};

const failures: Record<string, string> = {
  MISSING_SOURCE: "绑定的留存来源缺失",
  SOURCE_READ_FAILED: "绑定的留存来源无法读取",
  HASH_MISMATCH: "留存来源哈希与绑定不一致",
  RULE_MISMATCH: "当前规则与冻结协议不一致",
  BINDING_CHANGED: "读取期间样本绑定发生变化",
  CLOCK_INVALID: "证据时间未通过核验",
  NON_ACTUAL_EVIDENCE: "测试或模拟证据不能作为真实样本",
  PROTOCOL_INVALID: "留存协议或输入结构未通过核验",
};

export function HotspotSampleReview({
  sample,
  symbol,
}: {
  sample?: Sample;
  symbol: string;
}) {
  if (!sample) return null;
  const valid =
    sample.symbol === symbol &&
    sample.action === "no_order" &&
    sample.formal_eligibility === false &&
    sample.strategy_validation === "NOT_PROVEN" &&
    sample.trade_count === null;
  const covered =
    valid &&
    sample.status === "COVERED" &&
    sample.namespace === "ACTUAL" &&
    sample.source_integrity === "VERIFIED";
  return (
    <section aria-label="真实历史样本复核">
      <h3>真实历史样本复核</h3>
      {!covered ? (
        <p>
          {valid && sample.status === "NOT_COVERED"
            ? "未覆盖（NOT_COVERED）：此证券不在已绑定的真实留存样本中，不借用其他证券结果。"
            : valid && sample.reason_code && failures[sample.reason_code]
              ? failures[sample.reason_code] +
                "（" +
                sample.reason_code +
                "）；原候选观察仍可查看。"
              : "样本证据不可用；原候选观察仍可查看。"}
        </p>
      ) : (
        <>
          <p>
            {sample.symbol} · 真实行情留存（ACTUAL），仅描述历史价格路径。
            不是当前结构验证、实际成交或策略优势证明。不采取交易动作。
          </p>
          <p>
            历史窗口：{sample.partitions?.start_date} 至{" "}
            {sample.partitions?.end_date}； 开发截止：
            {sample.partitions?.development_end}； 验证开始：
            {sample.partitions?.validation_start}（不是严格样本外）。
          </p>
          <p>
            行情日期：{sample.market_trade_date}；资料可得时间：
            {sample.data_available_at}； 留存：{sample.retained_at}；本次核验：
            {sample.evaluated_at}。
          </p>
          <p>
            冻结规则：{sample.rule_version}；主周期：
            {sample.rule_inputs?.primary_period}； 随访：
            {sample.rule_inputs?.forward_sessions} 个后续交易日。
          </p>
          {sample.rule_definition && (
            <section aria-label="冻结规则定义">
              <h4>触发、失效与退出边界</h4>
              <p>{sample.rule_definition.entry}</p>
              <p>{sample.rule_definition.invalidation}</p>
              <p>{sample.rule_definition.context}</p>
              <p>{sample.rule_definition.followup}</p>
              <p>{sample.rule_definition.censoring}</p>
              <p>{sample.rule_definition.exit}</p>
            </section>
          )}
          <ul>
            {sample.limitations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
          <p>真实退出与净收益不可评：失效线被观察到不代表能够成交退出。</p>
          <ul>
            {sample.execution_unassessable_reasons?.map((code) => (
              <li key={code}>{reasons[code] ?? code}</li>
            ))}
          </ul>
          <details>
            <summary>查看冻结规则、输入与来源</summary>
            <p>假突破口径：{sample.rule_inputs?.false_breakout_proxy}</p>
            <p>失效口径：{sample.rule_inputs?.failure_proxy}</p>
            <p>随访分段边界：{sample.rule_inputs?.outcome_boundary}</p>
            {Object.entries(sample.source_bindings ?? {}).map(
              ([period, source]) => (
                <div key={period}>
                  <h4>{period} 原始行情</h4>
                  <p>
                    抓取：{source.fetched_at}；复权：{source.adjustment}；范围：
                    {source.scope}
                  </p>
                  <p style={{ overflowWrap: "anywhere" }}>
                    来源：{source.source_url}
                  </p>
                  <p style={{ overflowWrap: "anywhere" }}>
                    {source.path} · SHA256 {source.sha256}
                  </p>
                </div>
              ),
            )}
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {JSON.stringify(
                {
                  manifest: sample.manifest_binding,
                  protocol: sample.protocol_binding,
                  case: sample.case_binding,
                  quote: sample.quote_binding,
                  rules: sample.rule_bindings,
                  retained: sample.retained_bindings,
                },
                null,
                2,
              )}
            </pre>
          </details>
          <details>
            <summary>查看全部 {sample.events.length} 次触发及随访</summary>
            {sample.events.length === 0 && (
              <p>该证券在冻结窗口没有触发事件，不代表策略通过。</p>
            )}
            {sample.events.map((event) => (
              <details key={event.segment + event.cutoff}>
                <summary>
                  {event.cutoff} ·{" "}
                  {event.segment === "development" ? "开发段" : "验证段"} ·
                  {event.outcome.right_censored
                    ? "随访未完整（右删失）"
                    : "五日随访完整"}
                </summary>
                <p>
                  信号：{event.signal_state}；参考收盘：
                  {shown(event.levels.reference_close)}； 触发价：
                  {shown(event.levels.entry_trigger_price)}； 失效价：
                  {shown(event.levels.invalidation_price)}。
                </p>
                <p>
                  已观察 {event.outcome.observed_followup_sessions}{" "}
                  个后续交易日； 最后随访 bar：
                  {shown(event.outcome.last_observed_bar)}；
                  首次观察跌破失效线：
                  {event.outcome.first_invalidation_observed_at ??
                    (event.outcome.right_censored
                      ? "已观察窗口内尚未记录跌破；随访未完整，后续失效未知，不计作成功"
                      : "完整五日观察窗口内未记录跌破；不代表窗口外不会失效")}
                  。
                </p>
                <p>
                  五日失效代理：
                  {flag(event.outcome.failed_within_five_sessions)}；
                  次日假突破代理：
                  {flag(event.outcome.false_breakout_next_session_proxy)}。
                </p>
                <p>
                  次日收盘变化（%）：
                  {shown(event.outcome.next_session_close_change_pct)}；
                  第五日收盘变化（%）：
                  {shown(event.outcome.fifth_session_close_change_pct)}；
                  不利价格偏移（%）：
                  {shown(event.outcome.adverse_excursion_from_signal_close_pct)}
                  。 均为价格路径，不是交易收益；未完整随访不计作成功或失败。
                </p>
                <details>
                  <summary>查看本次已完成周期输入与执行未知项</summary>
                  <pre
                    style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                  >
                    {JSON.stringify(
                      {
                        primary: event.levels,
                        completed_context: event.completed_context,
                        execution: event.outcome.execution,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </details>
            ))}
          </details>
        </>
      )}
    </section>
  );
}

export async function loadHotspotSample(symbol: string): Promise<Sample> {
  const response = await fetch(
    "/api/v1/hotspot-replay-review?symbol=" + encodeURIComponent(symbol),
  );
  const body = await response.json();
  if (
    !response.ok ||
    body.action !== "no_order" ||
    body.symbol !== symbol ||
    body.schema_version !== "hotspot-symbol-retained-replay-v1"
  ) {
    throw new Error("样本响应不可核验");
  }
  return body;
}

export function HotspotSampleLookup() {
  const [symbol, setSymbol] = useState("300059");
  const [sample, setSample] = useState<Sample>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const valid = /^[0-9]{6}$/.test(symbol);
  async function load() {
    setLoading(true);
    setError(false);
    setSample(undefined);
    try {
      setSample(await loadHotspotSample(symbol));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section aria-label="按证券查看真实留存样本">
      <h3>按证券查看真实留存样本</h3>
      <p>
        历史样本不要求属于当前候选池，也不会加入候选池。点击后只核验这一只证券。
      </p>
      <label>
        证券代码{" "}
        <input
          value={symbol}
          disabled={loading}
          maxLength={6}
          onChange={(event) => {
            setSymbol(event.target.value);
            setSample(undefined);
            setError(false);
          }}
        />
      </label>
      <button type="button" disabled={!valid || loading} onClick={load}>
        {loading ? "正在核验…" : "查看该证券真实样本"}
      </button>
      {valid && (
        <a
          href={
            "/api/v1/hotspot-replay-review?symbol=" + encodeURIComponent(symbol)
          }
          target="_blank"
          rel="noreferrer"
        >
          打开该证券样本API
        </a>
      )}
      {error && <p>样本响应不可核验；可重试，未借用其他证券结果。</p>}
      <HotspotSampleReview sample={sample} symbol={symbol} />
    </section>
  );
}
