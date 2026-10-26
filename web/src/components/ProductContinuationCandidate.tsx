import React from "react";
import type { ProductContinuationCandidateReview } from "../types/api";

const object = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string =>
  typeof v === "string" && v.trim().length > 0;
const texts = (v: unknown): v is string[] =>
  Array.isArray(v) && v.length > 0 && v.every(text);
const decimal = (v: unknown): v is string =>
  typeof v === "string" &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v) &&
  Number.isFinite(Number(v));
const date = (v: unknown) =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v;
const binding = (v: unknown) =>
  object(v) &&
  text(v.path) &&
  !/^(?:[a-z]+:|[\\/])/i.test(v.path) &&
  !v.path.split(/[\\/]/).some((part: string) => part === ".." || !part) &&
  typeof v.sha256 === "string" &&
  /^[a-f0-9]{64}$/.test(v.sha256);
const cashFields = [
  "profit_cny",
  "distribution_cny",
  "opening_book_cny",
  "closing_book_cny",
  "opening_cash_cny",
  "closing_cash_cny",
] as const;
const operatingFields = [
  "revenue",
  "cost",
  "other_pre_tax_balance",
  "legacy_pre_tax_profit",
  "effective_tax_rate",
  "parent_share",
  "net_parent_nonrecurring_difference",
  "legacy_ex_parent",
];
const terminalFields = [
  "legacy_profit_cny",
  "incremental_cash_income_cny",
  "next_profit_cny",
  "next_distribution_cny",
  "next_cash_cny",
  "next_book_cny",
  "terminal_ri_cny",
  "terminal_equity_cash_value_cny",
  "first_year_ri_cny",
];
const terminalChecks = [
  "explicit_method",
  "explicit_product_continuation",
  "positive_product_and_total_profit",
  "no_unremitted_assets",
  "no_unpaid_selected_commitments",
  "no_new_funding",
  "net_maintenance_gap_zero",
  "no_recurring_wc_release_or_investment",
  "net_maintenance_wc_balanced",
  "full_funds_conversion",
  "supported_full_distribution",
  "cash_floor",
  "capacity_non_depleting",
];
const numericMap = (v: unknown, keys: string[]) =>
  object(v) && keys.every((key) => decimal(v[key]));
const terminalCapital = (v: unknown) =>
  object(v) &&
  v.year === 11 &&
  v.scope === "ordinary_owner_equivalent_cash_mapping" &&
  text(v.rationale) &&
  v.funding_treatment === "NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING" &&
  numericMap(v, [
    "project_cash_cny",
    "maintenance_project_overlap_cny",
    "operating_wc_increase_cny",
    "fund_call_cny",
    "other_noncash_adjustment_cny",
    "net_financing_cny",
  ]) &&
  (v.maintenance_basis === "EXPLICIT_NET_GAP_ASSUMPTION"
    ? decimal(v.net_maintenance_gap_cny)
    : v.maintenance_basis === "MATCHED_CAPEX_MINUS_DA_ALREADY_EXPENSED_IN_P" &&
      numericMap(v, ["maintenance_capex_cny", "matched_da_cny"]));
const terminalDistribution = (v: unknown) =>
  object(v) &&
  v.year === 11 &&
  numericMap(v, [
    "payout_ratio",
    "newly_withheld_fraction",
    "release_fraction",
    "reserve_transfer_fraction",
  ]) &&
  text(v.reserve_policy_rationale) &&
  text(v.capacity_mapping_rationale);
// Validate presentation structure and numeric syntax only. Kernel replay and
// source hash authentication remain the existing backend's responsibility.
export function verifiedProductContinuationCandidate(
  value: unknown,
  symbol: string,
): value is ProductContinuationCandidateReview {
  if (
    !object(value) ||
    !/^\d{6}$/.test(symbol) ||
    value.symbol !== symbol ||
    value.schema_version !== "product-continuation-candidate-review-v1" ||
    value.action !== "no_order" ||
    value.status !== "PENDING_ECONOMIC_REVIEW" ||
    value.confidence !== "LOW" ||
    value.formal_eligibility !== false ||
    value.approval_changed !== false ||
    value.primary_approved !== false ||
    value.position_guidance !== null ||
    value.price_comparison_eligible !== false ||
    value.price_draft !== null ||
    value.price_draft_status !==
      "NOT_PREPARED_ECONOMIC_OR_PRICE_BASIS_INSUFFICIENT" ||
    !binding(value.candidate_binding) ||
    !Array.isArray(value.source_bindings) ||
    !value.source_bindings.length ||
    !value.source_bindings.every(binding) ||
    ![value.financial_basis, value.valuation_date, value.research_as_of].every(
      date,
    ) ||
    !texts(value.financial_periods) ||
    !texts(value.blockers)
  )
    return false;
  const e = value.economic_explanation,
    c = value.cash_conditions,
    r = value.research_case;
  if (
    !object(e) ||
    ![e.rationale, e.cash_return_rationale, e.terminal_rationale].every(text) ||
    !texts(e.counter_evidence) ||
    (e.strongest_counter_evidence !== undefined &&
      !text(e.strongest_counter_evidence)) ||
    !object(c) ||
    ![
      c.maintenance_rationale,
      c.capacity_rationale,
      c.cash_mapping_rationale,
      c.terminal_distribution_rationale,
    ].every(text) ||
    !object(r) ||
    ![r.thesis, r.return_driver, r.mispricing_hypothesis].every(text) ||
    ![r.counter_evidence, r.thesis_breakers, r.next_events].every(
      (items) =>
        Array.isArray(items) &&
        items.length > 0 &&
        items.every((item) => object(item) && text(item.text)),
    )
  )
    return false;
  if (
    !Array.isArray(value.scenarios) ||
    value.scenarios.length !== 3 ||
    new Set(value.scenarios.map((s: any) => s?.scenario)).size !== 3
  )
    return false;
  return value.scenarios.every((s: any) => {
    if (
      !object(s) ||
      !["bear", "base", "bull"].includes(s.scenario) ||
      !decimal(s.per_share_value) ||
      Number(s.per_share_value) <= 0 ||
      !decimal(s.cost_of_equity) ||
      Number(s.cost_of_equity) <= 0 ||
      Number(s.cost_of_equity) >= 1
    )
      return false;
    if (
      ![s.cash_rows, s.operating_rows].every(
        (rows) =>
          Array.isArray(rows) &&
          rows.length === 10 &&
          rows.every((row, i) => object(row) && row.year === i + 1),
      )
    )
      return false;
    if (
      !s.cash_rows.every((row: any) => numericMap(row, [...cashFields])) ||
      !s.operating_rows.every(
        (row: any) =>
          numericMap(row, operatingFields) &&
          numericMap(row.product_revenue_cny, ["moutai", "series", "other"]) &&
          numericMap(row.opening_product_reference_revenue_cny, [
            "moutai",
            "series",
            "other",
          ]) &&
          numericMap(row.expenses, [
            "taxes_surcharges",
            "selling",
            "administration",
            "research",
          ]) &&
          numericMap(row.drivers, [
            "moutai_volume_growth",
            "moutai_realization_growth",
            "series_volume_growth",
            "series_realization_growth",
            "other_revenue_growth",
            "cost_ratio",
          ]),
      )
    )
      return false;
    const t = s.terminal;
    return (
      numericMap(t, terminalFields) &&
      t.status === "CONDITIONAL_TERMINAL_SUPPORTED" &&
      object(t.checks) &&
      terminalChecks.every((key) => t.checks[key] === true) &&
      Array.isArray(t.reasons) &&
      t.reasons.length === 0 &&
      object(t.policy) &&
      t.policy.method === "STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT" &&
      t.policy.operating_continuation ===
        "FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT" &&
      text(t.policy.rationale) &&
      text(t.policy.distribution_constraint_rationale) &&
      terminalCapital(t.policy.capital_cash_row) &&
      terminalDistribution(t.policy.distribution_row)
    );
  });
}

const labels = { bear: "悲观", base: "基准", bull: "乐观" };
// Display rounding only; preserve the consumed decimal strings in raw details.
const displayNumber = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 3,
});
const formatted = (value: unknown) => displayNumber.format(Number(value));
const rawStyle = {
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  maxWidth: "100%",
} as const;
function TextList({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export function ProductContinuationCandidate({
  value,
  symbol,
}: {
  value: unknown;
  symbol: string;
}) {
  if (value == null) return null;
  if (!verifiedProductContinuationCandidate(value, symbol))
    return (
      <section role="status">
        十年产品候选材料不可核验，已隐藏条件估值。
      </section>
    );
  const e = value.economic_explanation,
    c = value.cash_conditions,
    r = value.research_case;
  const cash = value.shareholder_cash_research;
  const cashVerified =
    cash?.status === "SOURCE_REPLAYED_PARTIAL_PARENT_CASH" &&
    cash.action === "no_order" &&
    cash.economic_approval === false &&
    cash.primary_valuation_usable === false &&
    cash.historical_cash_reconciliation_status === "INCOMPLETE" &&
    Array.isArray(cash.cash_routes) &&
    cash.cash_routes.length > 0 &&
    cash.cash_routes.every(
      (row) =>
        object(row) &&
        text(row.period) &&
        row.scope === "listed_parent_only" &&
        row.currency === "CNY" &&
        [
          row.printed_cfo_cny,
          row.printed_gross_capex_cny,
          row.printed_mixed_distribution_interest_paid_cny,
          row.printed_cash_change_cny,
        ].every(decimal) &&
        [
          row.printed_investment_income_cash_cny,
          row.partial_cash_before_mixed_payments_cny,
        ].every((v) => v === null || decimal(v)) &&
        Array.isArray(row.unknown_fields) &&
        row.unknown_fields.every(text) &&
        row.future_distributable_cash_cny === null &&
        row.ordinary_dividends_identified === false,
    );
  return (
    <section
      aria-label="十年产品延续候选研究"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h3>{symbol} 十年产品延续候选研究</h3>
      <p>
        条件估值，待经济审核；不是批准主估值，也不代表当前便宜。置信度
        LOW（低）。
        无操作资格、无价格比较资格；no_order。公共研究展示不依赖账户。
      </p>
      <dl>
        <dt>金融期间</dt>
        <dd>{value.financial_periods.join(" / ")}</dd>
        <dt>财务基准日</dt>
        <dd>{value.financial_basis}</dd>
        <dt>估值基准日</dt>
        <dd>{value.valuation_date}</dd>
        <dt>研究截至</dt>
        <dd>{value.research_as_of}</dd>
        <dt>研究论点</dt>
        <dd>{r.thesis}</dd>
        <dt>回报驱动</dt>
        <dd>{r.return_driver}</dd>
        <dt>错价假说（未获价格准入）</dt>
        <dd>{r.mispricing_hypothesis}</dd>
        <dt>十年延续理由</dt>
        <dd>{e.rationale}</dd>
        <dt>现金回报条件</dt>
        <dd>{e.cash_return_rationale}</dd>
        <dt>终值条件</dt>
        <dd>{e.terminal_rationale}</dd>
        <dt>维护投入</dt>
        <dd>{c.maintenance_rationale}</dd>
        <dt>分配能力</dt>
        <dd>{c.capacity_rationale}</dd>
        <dt>现金映射</dt>
        <dd>{c.cash_mapping_rationale}</dd>
        <dt>终值分配条件</dt>
        <dd>{c.terminal_distribution_rationale}</dd>
      </dl>
      {cash &&
        (cashVerified ? (
          <>
            <h4>母公司现金事实与当前判断</h4>
            <p>
              以下仅为已披露部分现金流，不是正常化股东现金，也未完成整表勾稽。投资收益收现不自动等于子公司分红；购建支出未拆为维护和增长。当前90%分配及终端全额分配仍不能作为已建立的主估值依据。资料不足不等于公司没有投资价值，也不能据此输出买入、加仓或持有。
            </p>
            <div style={{ overflowX: "auto", maxWidth: "100%" }}>
              <table>
                <caption>历史母公司现金路径，CNY元；空白不补零</caption>
                <thead>
                  <tr>
                    {[
                      "期间",
                      "经营现金净流入",
                      "购建长期资产现金",
                      "投资收益收现",
                      "混合分配/利润/利息支付",
                      "现金净变化",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cash.cash_routes.map((row) => (
                    <tr key={row.period}>
                      <th scope="row">{row.period}</th>
                      <td>{formatted(row.printed_cfo_cny)}</td>
                      <td>{formatted(row.printed_gross_capex_cny)}</td>
                      <td>
                        {row.printed_investment_income_cash_cny === null
                          ? "未取得完整两列证据"
                          : formatted(row.printed_investment_income_cash_cny)}
                      </td>
                      <td>
                        {formatted(
                          row.printed_mixed_distribution_interest_paid_cny,
                        )}
                      </td>
                      <td>{formatted(row.printed_cash_change_cny)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              下一决定性证据：同范围维护/增长投入、必要营运资本、实际子公司分红上划和法定提留之间的桥接。缺失字段：
              {[
                ...new Set(
                  cash.cash_routes.flatMap((row) => row.unknown_fields),
                ),
              ].join("、")}
            </p>
          </>
        ) : (
          <p role="status">母公司现金证据不可核验，已隐藏现金数值。</p>
        ))}
      {e.strongest_counter_evidence && (
        <>
          <h4>最强反证（后端研究输入）</h4>
          <p>{e.strongest_counter_evidence}</p>
        </>
      )}
      <h4>未排序反证</h4>
      <TextList
        items={[
          ...e.counter_evidence,
          ...r.counter_evidence.map((item) => item.text),
        ]}
      />
      <h4>论点失效条件</h4>
      <TextList items={r.thesis_breakers.map((item) => item.text)} />
      <h4>下一事件</h4>
      <TextList items={r.next_events.map((item) => item.text)} />
      <p>
        以下为后端已消费值，展示最多三位小数并使用千分位，完整精度保留在原文；金额单位
        CNY（元），每股值单位元/股；前端不重算估值。
        第1–10年为研究步骤，不推定为日历年。Ke 为原始小数形式。
      </p>
      {(["bear", "base", "bull"] as const).map((name) => {
        const s = value.scenarios.find((item) => item.scenario === name)!;
        return (
          <div key={name}>
            <h4>
              {labels[name]}条件每股值：{formatted(s.per_share_value)}；Ke：
              {formatted(s.cost_of_equity)}
            </h4>
            <details>
              <summary>{labels[name]}：展开十年逐年经营与现金表</summary>
              <div style={{ overflowX: "auto", maxWidth: "100%" }}>
                <table>
                  <caption>{labels[name]}十年原始现金路径（CNY）</caption>
                  <thead>
                    <tr>
                      {[
                        "研究年",
                        "经营收入",
                        "产品归母利润假设",
                        "利润",
                        "分配",
                        "期初账面权益",
                        "期末账面权益",
                        "期初现金",
                        "期末现金",
                      ].map((title) => (
                        <th key={title} scope="col">
                          {title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {s.cash_rows.map((row, i) => (
                      <tr key={row.year}>
                        <th scope="row">{row.year}</th>
                        <td>{formatted(s.operating_rows[i].revenue)}</td>
                        <td>
                          {formatted(s.operating_rows[i].legacy_ex_parent)}
                        </td>
                        {cashFields.map((key) => (
                          <td key={key}>{formatted(row[key])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <details>
                <summary>
                  完整精度、经营行、现金行与终值字段（后端原文）
                </summary>
                <pre style={rawStyle}>{JSON.stringify(s, null, 2)}</pre>
              </details>
            </details>
          </div>
        );
      })}
      <h4>为何没有价格草案</h4>
      <p>
        当前仅为条件研究，主估值尚未建立；经济现金依据不足，股本、财务期间、分配事件与当前报价尚未对齐，
        且未选定具体价格阈值、理由与有效期，因此 price_draft=null。
      </p>
      <p>{value.price_draft_status}</p>
      <TextList items={value.blockers} />
      <details>
        <summary>候选与来源绑定（路径 / SHA-256）</summary>
        <p>来源哈希由后端核验；浏览器只展示绑定，不读取本地证据文件。</p>
        <pre style={rawStyle}>
          {JSON.stringify(
            {
              candidate_binding: value.candidate_binding,
              source_bindings: value.source_bindings,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </section>
  );
}
