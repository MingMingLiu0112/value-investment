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
export function amount(value: unknown): string {
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

// Preserve backend decimal strings and unknown price structures without arithmetic.
function supplied(value: unknown): string {
  if (value === undefined || value === null || value === "") return "未提供";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function DirectOwnerCashView({ data }: { data: FirstResearchInputResponse }) {
  const cash = data.direct_owner_cash!;
  const price = cash.conditional_price;
  if (
    price &&
    (price.action !== "no_order" || price.currentpricecomparison !== false)
  )
    return (
      <Alert type="warning" message="直接经营现金条件价边界不符，停止展示" />
    );

  return (
    <section
      aria-label="直接母公司经营现金研究"
      style={{ overflowWrap: "anywhere" }}
    >
      <h3>直接母公司经营现金→资本/债务支付→约束分配→RI/DDM</h3>
      <p>
        历史估值时点：{supplied(data.valuation?.valuation_date)} · 研究截止：
        {supplied(data.research_as_of)}
      </p>
      <p>条件研究 / 未批准 / 不是当前买价；不比较当前报价；action=no_order。</p>
      <p>
        方法：{supplied(cash.method)} · 估值依据：
        {supplied(cash.valuation_basis)} · 范围：{supplied(cash.scope)}
      </p>
      <p>
        主区间采用状态：
        {data.main_range_adopted === true
          ? "已采用（研究字段，不代表批准）"
          : data.main_range_adopted === false
            ? "未采用"
            : "未提供"}
      </p>
      {data.main_range_adopted === true && (
        <p>主估值区间（原稿）：{supplied(data.main_valuation_range)}</p>
      )}
      {cash.financing_review && (
        <Alert
          type="warning"
          message="融资条件仍待核实"
          description={
            <span>
              {cash.financing_review.basis_date}之后披露的融资发行额：
              {amount(cash.financing_review.post_basis_issuance_cny)}元。
              这不能证明基准日母公司期初债务、当前未偿余额或未来续借能力；
              未核实前，三情景仅为条件研究。
              {cash.financing_review.opening_debt_evidence_comparison && (
                <span>
                  {" "}
                  基准日母公司报表已识别借款及租赁相关列示额
                  {amount(
                    cash.financing_review.opening_debt_evidence_comparison
                      .identified_parent_balance_lines_cny,
                  )}
                  元；模型期初债务假设
                  {amount(
                    cash.financing_review.opening_debt_evidence_comparison
                      .forecast_opening_debt_cny,
                  )}
                  元，两者差额
                  {amount(
                    cash.financing_review.opening_debt_evidence_comparison
                      .unexplained_difference_cny,
                  )}
                  元。列示额并非完整有息负债，差额不能直接认作不存在的债务；
                  仍需附注明细及到期安排核对。
                </span>
              )}
              {cash.financing_review.parent_financing_followup && (
                <span>
                  {" "}
                  后续母公司半年报（
                  {cash.financing_review.parent_financing_followup.period_end}
                  ）列示的同四项余额为
                  {amount(
                    cash.financing_review.parent_financing_followup
                      .closing_identified_balance_cny,
                  )}
                  元。其相对年末变动与半年内借还现金净额相差
                  {amount(
                    cash.financing_review.parent_financing_followup
                      .unallocated_reconciliation_difference_cny,
                  )}
                  元；此为尚未分解的对账差异，不认作已核债务或可续借额度。
                </span>
              )}
              {cash.financing_review.followup_unavailable_reason && (
                <span>
                  {" "}
                  后续母公司融资对账来源未通过核验，保持历史条件研究。
                </span>
              )}
              {cash.financing_review.first_year_no_new_borrowing_stress
                ?.base && (
                <span>
                  {" "}
                  若
                  {
                    cash.financing_review.first_year_no_new_borrowing_stress
                      .base.year
                  }
                  年 完全没有假设中的新增借款，且不分红，Base 路径维持现金底线
                  至少仍需
                  {amount(
                    cash.financing_review.first_year_no_new_borrowing_stress
                      .base.minimum_funding_gap_to_cash_floor_cny,
                  )}
                  元。
                  这是同一年度现金账的条件压力测试，不证明全部债务当年到期。
                </span>
              )}
            </span>
          }
        />
      )}
      <h4>三情景历史条件估值（元/股）</h4>
      <ul>
        {(["bear", "base", "bull"] as const).map((name) => (
          <li key={name}>
            {name}：{amount(data.valuation?.[`${name}_value`])}
          </li>
        ))}
      </ul>
      <h4>条件价草稿（不是当前买价）</h4>
      <p>状态：{supplied(price?.status)}</p>
      <ul>
        {(
          [
            ["entry", "建仓条件价"],
            ["add", "加仓条件价"],
            ["reduce", "减仓条件价"],
            ["exit", "退出条件价"],
          ] as const
        ).map(([key, label]) => {
          const value = record(price?.draft_prices)[key];
          return (
            <li key={key}>
              {label}：{value == null ? "未形成" : amount(value)}
            </li>
          );
        })}
      </ul>
      <p>
        原因代码：
        {price?.reason_codes?.length ? price.reason_codes.join("、") : "未提供"}
      </p>
      <p>有效期至：{supplied(price?.expires_at)}</p>
      <h4>经营与留存假设、反证</h4>
      {cash.assumptions?.length ? (
        <ul>
          {cash.assumptions.map((item, index) => (
            <li key={index}>
              假设{index + 1}
              {item.name && !/^假设\s*\d+$/.test(item.name)
                ? `（${item.name}）`
                : ""}
              ：{supplied(item.rationale)}；反证：
              {supplied(item.counter_evidence)}
            </li>
          ))}
        </ul>
      ) : (
        <p>未提供</p>
      )}
      <details>
        <summary>估值、条件价与假设原稿（保留精确值）</summary>
        <pre>
          {supplied({
            valuation: data.valuation,
            conditional_price: price,
            assumptions: cash.assumptions,
          })}
        </pre>
      </details>
      <details>
        <summary>三情景年度现金账（元，原值；条件分配不是分红承诺）</summary>
        <p>资本/债务支付仅按后端原稿解释；本组件不由余额倒算支付或分配。</p>
        {(["bear", "base", "bull"] as const).map((name) => (
          <div key={name} style={{ overflowX: "auto" }}>
            <table>
              <caption>{name} 年度现金账</caption>
              <thead>
                <tr>
                  {[
                    "年度",
                    "直接经营现金",
                    "约束条件分配",
                    "期末现金",
                    "期末账面权益",
                    "期末债务",
                    "留存假设",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cash.annual_rows?.[name]?.map((row, index) => (
                  <tr key={index}>
                    {[
                      row.year,
                      row.direct_operating_cash_cny,
                      row.conditional_distribution_cny,
                      row.closing_cash_cny,
                      row.closing_book_equity_cny,
                      row.closing_debt_cny,
                      row.retention_assumption,
                    ].map((value, column) => (
                      <td key={column}>{supplied(value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!cash.annual_rows?.[name]?.length && <p>年度现金账未提供</p>}
          </div>
        ))}
      </details>
      <details>
        <summary>来源引用与输入绑定原稿</summary>
        <p>输入指纹：{supplied(data.input_fingerprint)}</p>
        <pre>{supplied(cash.source_refs)}</pre>
        <DetailSection title="输入来源绑定" value={data.source_bindings} />
      </details>
    </section>
  );
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
    (!data.direct_owner_cash &&
      (data.scope !== "CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE" ||
        data.main_range_adopted !== false ||
        data.main_valuation_range !== null)) ||
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

  if (data.direct_owner_cash) return <DirectOwnerCashView data={data} />;

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
      {data.parent_cash_observation && (
        <section aria-label="母公司历史现金观察">
          <h4>母公司历史现金观察</h4>
          {data.parent_cash_observation.status === "OBSERVED" &&
          data.parent_cash_observation.whole_statement_reconciled === true &&
          data.parent_cash_observation.action === "no_order" &&
          data.parent_cash_observation.future_cash_proven === false &&
          data.parent_cash_observation.periods?.length ? (
            <>
              <p>
                母公司现金表各期间余额与现金变动已完整勾稽。以下仅是历史观察，
                只核对历史母公司现金流量表。经营现金和投资收付会受结算、借还款影响，
                不能据此推定未来可分配现金；“股利、利润或利息支付”是混合科目，不等于股息。
              </p>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <caption>
                    历史原件金额（亿元；四舍五入显示，原值保留在来源记录）
                  </caption>
                  <thead>
                    <tr>
                      <th>期间</th>
                      <th>经营现金净额</th>
                      <th>购建长期资产付现</th>
                      <th>借款取得</th>
                      <th>偿还债务</th>
                      <th>股利、利润或利息支付</th>
                      <th>期末现金等价物</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.parent_cash_observation.periods.map((row) => (
                      <tr key={row.period}>
                        <td>{row.period}</td>
                        {[
                          "cfo_cny",
                          "gross_capex_cny",
                          "borrowings_received_cny",
                          "debt_repaid_cny",
                          "mixed_distribution_interest_paid_cny",
                        ].map((field) => (
                          <td key={field}>
                            {amount(Number(row.flows[field]) / 1e8)}
                          </td>
                        ))}
                        <td>
                          {amount(
                            Number(row.closing_cash_and_equivalents_cny) / 1e8,
                          )}
                        </td>
                      </tr>
                    ))}
                    {data.parent_cash_observation.ttm_flows && (
                      <tr>
                        <th>TTM流量（FY＋当期H1－同期H1）</th>
                        {[
                          "cfo_cny",
                          "gross_capex_cny",
                          "borrowings_received_cny",
                          "debt_repaid_cny",
                          "mixed_distribution_interest_paid_cny",
                        ].map((field) => (
                          <td key={field}>
                            {amount(
                              Number(
                                data.parent_cash_observation!.ttm_flows![field],
                              ) / 1e8,
                            )}
                          </td>
                        ))}
                        <td>不适用（期末存量）</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <details>
                <summary>原件页码、来源Hash与现金观察限制</summary>
                <DetailSection
                  title="现金观察原稿"
                  value={data.parent_cash_observation}
                />
              </details>
            </>
          ) : (
            <Alert
              type="info"
              message="母公司现金原件尚未完成独立核验"
              description={
                data.parent_cash_observation.reason ||
                "现金观察来源或期间不完整"
              }
            />
          )}
        </section>
      )}
      {data.opening_capital && (
        <p aria-label="已消费的估值基准股本">
          估值基准股本：{data.opening_capital.shares} 股（
          {data.opening_capital.period_end}）。此股数用于复算历史条件估值。
          当前股本连续性仍需核验。
          {officialUrl(data.opening_capital.source_url) && (
            <>
              {" "}
              <a
                href={officialUrl(data.opening_capital.source_url)}
                target="_blank"
                rel="noreferrer"
              >
                原件第 {data.opening_capital.physical_page} 页
              </a>
            </>
          )}
        </p>
      )}
      {data.quote_observation && (
        <p aria-label="独立行情观察">
          行情观察：{data.quote_observation.quote_date || "未登记日期"}
          {data.quote_observation.display_price !== null
            ? ` · 收盘价 ${data.quote_observation.display_price} 元`
            : " · 无可核验报价"}
          {` · ${data.quote_observation.status}`}
          {data.quote_observation.comparison_eligible
            ? " · 行情比较资格须以正式研究和F2复核为准"
            : " · 尚无价格比较资格，不得据此认定低估或生成买价"}
        </p>
      )}
      <p>
        本页只读重放已登记输入，不发起新LLM或自动任务；不新增C第六家验收，也不授予正式画像准入或交易资格。
      </p>
      {data.successor_update?.status === "SOURCE_BOUND_CONDITIONAL_SUCCESSOR" &&
        data.successor_update.symbol === symbol &&
        data.successor_update.action === "no_order" &&
        data.successor_update.formal_eligibility === false &&
        data.successor_update.main_range_adopted === false &&
        data.successor_update.price_admitted === false && (
          <section aria-label="研究版本更新">
            <h4>E1 研究版本更新</h4>
            <p>
              新增来源或假设后，旧版与新版均已按各自绑定输入冷重算。新版仍是未批准的条件压力研究，不是当前可比较的主估值或买价。
            </p>
            <p>
              新版研究截止：{data.successor_update.research_as_of || "未提供"} ·
              财务依据：{data.successor_update.financial_basis || "未提供"}
            </p>
            <p>
              变化输入：
              {data.successor_update.changed_input_fields?.join("、") ||
                "未提供"}
            </p>
            {data.successor_update.change_rationale && (
              <p>
                <strong>变更依据与性质：</strong>
                {data.successor_update.change_rationale}
              </p>
            )}
            {data.successor_update.countercase && (
              <p>
                <strong>需要重开的反证：</strong>
                {data.successor_update.countercase}
              </p>
            )}
            <ul>
              {SCENARIOS.map(([name, label]) => {
                const key =
                  name === "bear"
                    ? "bear_value"
                    : name === "base"
                      ? "base_value"
                      : "bull_value";
                return (
                  <li key={name}>
                    {label}：旧版{" "}
                    {amount(
                      data.successor_update?.predecessor_valuation?.[key],
                    )}{" "}
                    元 → 新版{" "}
                    {amount(data.successor_update?.successor_valuation?.[key])}{" "}
                    元
                  </li>
                );
              })}
            </ul>
            <details>
              <summary>新旧输入指纹</summary>
              <p>旧版：{data.successor_update.predecessor_input_fingerprint}</p>
              <p>新版：{data.successor_update.successor_input_fingerprint}</p>
            </details>
          </section>
        )}
      {data.successor_update?.status === "UNASSESSABLE" && (
        <Alert
          type="warning"
          message="后继研究版本无法核验"
          description={data.successor_update.reason || "来源或版本校验失败"}
        />
      )}
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
