import { useCallback } from "react";
import { Alert, Button } from "antd";
import {
  api,
  type FirstResearchInputResponse,
  type FirstResearchScenarioKey,
  type FirstResearchAnnualLedger,
} from "../services/api";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";

const SCENARIOS = [
  ["bear", "渠道压力持续"],
  ["base", "逐步稳定"],
  ["bull", "有条件修复"],
] as const;

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function text(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value;
  const row = record(value);
  for (const key of ["text", "statement", "reason", "claim"]) {
    const candidate = row[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate;
  }
  return undefined;
}
function amount(value: unknown): string {
  const numeric =
    typeof value === "number"
      ? value
      : typeof value === "string" &&
          /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim())
        ? Number(value)
        : NaN;
  return Number.isFinite(numeric)
    ? numeric.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    : "未提供";
}
function annualRows(ledger?: FirstResearchAnnualLedger) {
  return ledger?.rows10 ?? ledger?.rows;
}
function scenarioReason(
  data: FirstResearchInputResponse,
  name: FirstResearchScenarioKey,
) {
  const assumptions = record(data.operating_assumptions);
  const own = record(record(assumptions.scenarios)[name]);
  const direct = text(own.economic_rationale) || text(own.rationale);
  return {
    direct,
    terminal: text(record(own.terminal_policy).rationale),
    shared:
      text(record(assumptions.choice).rationale) ||
      text(assumptions.rationale) ||
      data.research_case?.thesis,
  };
}
function Claims({ title, items }: { title: string; items?: unknown[] }) {
  return (
    <section>
      <h4>{title}</h4>
      {items?.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={index}>{text(item) || "原稿未提供可读说明"}</li>
          ))}
        </ul>
      ) : (
        <p>原稿尚未提供，不能推定已满足。</p>
      )}
    </section>
  );
}
function officialUrl(value: unknown) {
  if (typeof value !== "string") return undefined;
  try {
    return new URL(value).protocol === "https:" ? value : undefined;
  } catch {
    return undefined;
  }
}

export function FirstResearchInputView({
  data,
  symbol,
}: {
  data: FirstResearchInputResponse;
  symbol: string;
}) {
  if (data.status === "NOT_STARTED") return null;
  if (
    data.symbol !== symbol ||
    data.action !== "no_order" ||
    data.formal_eligibility !== false ||
    data.scope !== "CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE" ||
    data.main_range_adopted !== false ||
    data.main_valuation_range !== null ||
    data.current_price !== null ||
    data.condition_price !== null ||
    data.personal_quantity !== null
  )
    return (
      <Alert
        type="warning"
        message="首次研究输入身份或压力研究边界不符，停止展示"
      />
    );

  if (data.status !== "SOURCE_BOUND_FIRST_INPUT_COMPILED")
    return (
      <section aria-label="首次条件压力研究">
        <h3>首次条件压力研究</h3>
        <Alert
          type="info"
          message="已登记首次研究输入暂不可核验"
          description="现有来源或输入未能完成冷重放，不能据此显示场景结果。此状态不代表未开始，也不代表零结果。"
        />
        <details>
          <summary>核验失败原因</summary>
          <p>{data.reason || "尚未提供具体失败原因"}</p>
        </details>
      </section>
    );

  if (
    !data.research_case ||
    (data.research_case.symbol && data.research_case.symbol !== symbol) ||
    !data.input_fingerprint ||
    !data.source_bindings?.length ||
    SCENARIOS.some(([name]) => {
      const rows = annualRows(data.annual_ledgers?.[name]);
      return !Array.isArray(rows) || rows.length !== 10;
    })
  )
    return (
      <Alert
        type="warning"
        message="首次研究输入或年度来源绑定不完整，停止展示压力结果"
      />
    );

  return (
    <section
      aria-label="首次条件压力研究"
      style={{ marginBlock: 20, overflowWrap: "anywhere" }}
    >
      <h3>
        首次条件压力研究 ·{" "}
        {data.company_name || data.research_case.name || symbol}（{symbol}）
      </h3>
      <Alert
        type="warning"
        message="经济主区间：拒绝采用（REJECTED）"
        description="仅为条件压力研究首编，不是已采用的主估值区间或买价，不比较当前报价，不提供个人数量，不审批。"
      />
      <p>
        财务依据期间：{data.financial_basis || "未提供"} · 研究截止：
        {data.research_as_of || "未提供"}
        {data.available_at ? " · 输入可用时间：" + data.available_at : ""}
      </p>
      <p>
        本页只读重放已登记输入，不发起新LLM或自动任务；不新增C第六家验收，也不授予正式画像准入或交易资格。
      </p>
      <h4>条件研究论点</h4>
      <p>{data.research_case.thesis}</p>
      {SCENARIOS.map(([name, label]) => {
        const ledger = data.annual_ledgers![name];
        const rows = annualRows(ledger)!;
        const reason = scenarioReason(data, name);
        return (
          <article key={name} aria-label={label}>
            <h4>{label}（条件假设）</h4>
            <p>
              <strong>
                {reason.direct ? "本情景理由：" : "共用研究理由："}
              </strong>
              {reason.direct ||
                reason.shared ||
                "响应尚未提供该情景理由，不能自行补成结论。"}
            </p>
            {reason.terminal && (
              <p>
                <strong>终端条件理由（假设）：</strong>
                {reason.terminal}
              </p>
            )}
            <p>
              资金约束：
              {ledger.funding_status === "SHORTFALL"
                ? "假设路径内存在资金缺口"
                : ledger.funding_status === "FUNDED"
                  ? "假设路径内资金节点平衡，合法可分配能力仍待核验"
                  : "状态未提供"}
            </p>
            <div style={{ overflowX: "auto" }}>
              <table>
                <caption>
                  年度利润、分配与留存摘要（元；展示四舍五入至两位小数，原值见完整年度账本；均为条件假设，非分红承诺）
                </caption>
                <thead>
                  <tr>
                    <th>研究年度</th>
                    <th>利润</th>
                    <th>分配</th>
                    <th>留存</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      <td>{String(row.year)}</td>
                      <td>{amount(row.profit)}</td>
                      <td>{amount(row.distribution)}</td>
                      <td>{amount(row.retained)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details>
              <summary>{label}：完整年度账本与假设原稿</summary>
              <DetailSection
                title="后端年度重算原稿（不新增计算）"
                value={ledger}
              />
              <DetailSection
                title="来源绑定经营假设"
                value={
                  record(record(data.operating_assumptions).scenarios)[name]
                }
              />
            </details>
          </article>
        );
      })}
      <Claims title="关键反证" items={data.research_case.counter_evidence} />
      <Claims
        title="失效与重审条件"
        items={data.research_case.thesis_breakers}
      />
      <Claims title="后续核验事件" items={data.research_case.next_events} />
      <details>
        <summary>数学压力结果（非主估值区间、非买价）</summary>
        <p>
          仅保留数学压力结果；中间条件场景未被采用为经济主区间，不与当前报价比较。
        </p>
        {data.valuation ? (
          <>
            <p>
              计算时点：{data.valuation.valuation_date} · 原稿置信度：
              {data.valuation.confidence}
            </p>
            <ul>
              {SCENARIOS.map(([name, label]) => (
                <li key={name}>
                  {label}：
                  {amount(
                    data.valuation![
                      name === "bear"
                        ? "bear_value"
                        : name === "base"
                          ? "base_value"
                          : "bull_value"
                    ],
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p>本响应未提供可核验数学压力结果。</p>
        )}
      </details>
      <details>
        <summary>官方来源、输入指纹与技术明细</summary>
        <p>
          原生来源行数：{data.native_fact_count ?? "未提供"}
          ；不等于正式事实准入。
        </p>
        <p>
          输入指纹：<code>{data.input_fingerprint}</code>
        </p>
        <p>bear / base / bull仅为接口兼容键，不代表主区间选择。</p>
        <ul>
          {data.sources?.map((source, index) => {
            const url = officialUrl(
              source.official_url ||
                source.officialURL ||
                source.source_url ||
                source.location ||
                source.url,
            );
            return (
              <li key={index}>
                {url ? (
                  <a href={url} target="_blank" rel="noreferrer">
                    {source.title || source.id || "官方来源"}
                  </a>
                ) : (
                  source.title || source.id || "来源链接尚未提供"
                )}
                {source.sha256 ? " · SHA-256 " + source.sha256 : ""}
              </li>
            );
          })}
        </ul>
        <DetailSection title="输入来源绑定" value={data.source_bindings} />
        <DetailSection
          title="经营假设原稿（不作新推导）"
          value={data.operating_assumptions}
        />
        <DetailSection title="尚未通过的研究条件" value={data.blockers} />
      </details>
    </section>
  );
}

export function FirstResearchInputPanel({ symbol }: { symbol: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.firstResearchInput(symbol, signal),
    [symbol],
  );
  const result = useApi(load);
  if (result.loading) return null;
  if (result.error || !result.data)
    return (
      <Alert
        type="info"
        message="首次研究输入读取失败，尚不能核验"
        description={
          <Button onClick={result.retry}>重新读取首次研究输入</Button>
        }
      />
    );
  return <FirstResearchInputView data={result.data} symbol={symbol} />;
}
