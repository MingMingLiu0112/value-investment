import type {
  PolicyHandoff,
  JointCapitalReview as JointReview,
} from "../services/valuePolicy";
import type { ValueResearchAnalysis } from "../types/api";
import { CandidatePriceDraft } from "./CandidatePriceDraft";
import {
  jointCapitalReviewMatches,
  distributionDiagnosticsMatch,
  distributionRawFields,
  distributionDerivedFields,
  publicJointCapitalReviewMatches,
  jointRowFields,
  jointTerminalFields,
  isJointCashReview,
  jointCashPolicyFields,
  jointCashRowFields,
  jointCashOperatingFields,
  jointCashTerminalFields,
} from "../services/valuePolicy";

const limitations: Record<string, string> = {
  "Maintenance equals scaled DA only by assumption.":
    "维持资本开支等于按收入缩放的折旧摊销，仅为假设。",
  "Parent cash conversion and terminal marginal return remain unapproved.":
    "归母盈利现金转换及终端边际回报仍未获批准。",
};

const names: Record<string, string> = {
  opening_cash: "期初现金",
  opening_unremitted: "期初未上划资本",
  opening_distribution_capacity: "期初分配容量",
  opening_operating_capital: "期初经营资本",
  opening_liquidity_capital: "期初流动资本",
  forecast_roe: "当年 ROE（非 ROIC）",
  target_distribution: "目标分配",
  accessible_profit: "可取得盈利现金假设",
  newly_unremitted: "新增未上划盈利",
  net_maintenance_cash_cny: "净维护现金（已扣费用化折旧）",
  operating_wc_cash_cny: "营运资金 WC 现金需求",
  commitment_cash_cny: "承诺现金支出",
  mandatory_cash: "必要现金支出合计",
  cash_distribution_limit: "现金约束分配上限",
  capacity_distribution_limit: "容量约束分配上限",
  reserve_transfer: "准备金转入",
  distribution: "受约束条件分配",
  discretionary_operating_addition: "可自主新增经营投入",
  closing_productive_operating_capital: "期末新增生产性经营资本",
  closing_operating_capital: "期末经营资本",
  closing_liquidity_capital: "期末流动资本",
  closing_cash: "期末现金",
  closing_unremitted: "期末未上划资本",
  closing_distribution_capacity: "期末分配容量",
  funding_shortfall: "资金缺口",
  clean_surplus_residual: "净盈余对账差额",
  capital_identity_residual: "资本对账差额",
  pre_tax_profit: "税前盈利",
  tax: "所得税",
  historical_da_anchor: "历史折旧摊销锚点（不重复加回现金）",
  other_pre_tax_balance: "其他税前项目余额",
  terminal_distribution: "终端受约束分配",
  target_payout_ratio: "目标分配比例",
  accessible_profit_ratio: "盈利现金可取得比例",
  reserve_ratio: "准备金比例",
  profit_scale: "终端盈利缩放倍数",
  surcharges: "税金及附加",
  selling: "销售费用",
  admin: "管理费用",
  research: "研发费用",
  bear: "谨慎情景",
  base: "中性条件情景",
  bull: "乐观情景",
  revenue: "营业收入",
  cost: "营业成本",
  legacy_pre_tax_profit: "存量业务税前盈利",
  legacy_parent_profit: "存量业务归母盈利",
  new_operating_profit: "新增经营资本盈利",
  new_liquidity_profit: "新增流动资本盈利",
  profit: "归母盈利合计",
  opening_book: "期初权益",
  roe: "当年 ROE（非 ROIC）",
  retained: "留存盈利",
  dividend: "条件分配金额",
  closing_book: "期末权益",
  net_operating_addition: "新增经营资本",
  net_liquidity_addition: "新增流动资本",
  maintenance_capex_assumption: "维持资本开支假设",
  cash_open: "期初现金代理",
  cash_close: "期末现金代理",
  retention: "盈利留存比例",
  operating_allocation: "留存转经营资本比例",
  new_operating_return: "新增经营资本回报假设",
  new_liquidity_return: "新增流动资本回报假设",
  parent_cash_conversion: "归母盈利现金转换假设",
  terminal_growth: "终端增长假设",
  terminal_profit_scale: "终端盈利缩放倍数",
  terminal_roe: "终端 ROE 假设（非已验证 ROIC）",
  terminal_profit: "终端盈利",
  terminal_book: "终端权益",
  terminal_retention: "终端留存比例",
  terminal_net_operating_investment: "终端新增经营投入",
  terminal_new_liquidity_investment: "终端新增流动投入",
  terminal_dividend: "终端条件分配",
  explicit_distribution_pv_cny: "显式十年股东分配现值",
  terminal_value_at_year_10_cny: "第10年末尾期经济价值",
  terminal_distribution_value_cny: "尾期股东分配价值",
  terminal_convergence_residual_cny: "尾期收敛残差",
  ri_ddm_difference_cny: "RI／股东分配交叉检查差额",
  revenue_growth: "收入增速假设",
  cost_ratio: "成本率假设",
};
const ratios = new Set([
  "forecast_roe",
  "target_payout_ratio",
  "accessible_profit_ratio",
  "reserve_ratio",
  "roe",
  "retention",
  "operating_allocation",
  "new_operating_return",
  "new_liquidity_return",
  "parent_cash_conversion",
  "terminal_growth",
  "terminal_roe",
  "terminal_retention",
  "revenue_growth",
  "cost_ratio",
]);

function Value({
  name,
  value,
  label,
}: {
  name: string;
  value: unknown;
  label?: string;
}) {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    !Number.isFinite(Number(value))
  )
    return (
      <div>
        <dt>{label ?? names[name] ?? name}</dt>
        <dd>缺失或无效，不能按零展示</dd>
      </div>
    );
  const number = Number(value);
  const display =
    name === "terminal_profit_scale" || name === "profit_scale"
      ? `${number.toFixed(2)} 倍`
      : ratios.has(name)
        ? `${(number * 100).toFixed(2)}%`
        : `${(number / 1e8).toFixed(2)} 亿元`;
  return (
    <div style={{ minWidth: 0 }}>
      <dt>{label ?? names[name] ?? name}</dt>
      <dd style={{ marginLeft: 0 }}>
        {display}
        <details>
          <summary>
            完整值
            {ratios.has(name)
              ? "（比例）"
              : name === "terminal_profit_scale" || name === "profit_scale"
                ? "（倍数）"
                : "（元）"}
          </summary>
          <code>{String(value)}</code>
        </details>
      </dd>
    </div>
  );
}

function Funding({ status }: { status: string }) {
  return status === "FAIL" ? (
    <p role="alert">
      FAIL：假设路径存在现金资金缺口；负值按原账本保留，不能认定可分红。
    </p>
  ) : (
    <p>
      PASS：仅表示本组假设下的现金资金演算通过，不代表可分红能力、经济假设或策略批准。
    </p>
  );
}

export function JointCapitalReview({
  handoff,
  symbol,
}: {
  handoff: PolicyHandoff;
  symbol: string;
}) {
  if (
    handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED" ||
    !handoff.economic_review_materials?.joint_capital_review
  )
    return null;
  if (!jointCapitalReviewMatches(handoff, symbol))
    return (
      <p role="alert">
        联合资本路径字段缺失、数值无效或身份绑定不一致，暂不可展示为核验账本；请重新读取。
      </p>
    );
  const review = handoff.economic_review_materials.joint_capital_review;
  return <JointCapitalLedger review={review} />;
}

export function PublicJointCapitalReview({
  analysis,
  symbol,
}: {
  analysis: ValueResearchAnalysis;
  symbol: string;
}) {
  if (analysis.joint_capital_review == null) return null;
  if (!publicJointCapitalReviewMatches(analysis, symbol))
    return (
      <p role="alert">
        公开联合资本路径与分析版本或来源绑定不一致，或账本字段无效，暂不可作为核验结果展示。
      </p>
    );
  return (
    <section aria-label="公开联合经营与资本年度账">
      <p>
        前瞻假设 ·
        LOW／低置信度，未批准。仅供公开条件研究，不是正常化事实、当前可交易价值或已证实现金。
      </p>
      <JointCapitalLedger review={analysis.joint_capital_review!} publicView />
    </section>
  );
}

function JointCapitalLedger({
  review,
  publicView = false,
}: {
  review: Readonly<JointReview>;
  publicView?: boolean;
}) {
  if (isJointCashReview(review)) return <CashCapitalLedger review={review} />;
  return (
    <section
      aria-label="联合资本路径待审"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h4>联合资本路径：三情景五年条件演算</h4>
      <p>
        以下全部未来年度均为未获批准的研究假设，不是正常化事实或分红承诺。现金与资金口径为
        proxy（代理），不证明母公司现金可上划或法定可分配。
      </p>
      {review.date_scope === "DATED_CONDITIONAL_MODEL" ? (
        <p>
          资料基准：{review.basis_at}；估值时点：{review.valuation_at}
          。不是最新行情日期。
        </p>
      ) : (
        <p role="alert">
          未建立定价时点：旧模型无已绑定的资料基准／估值日期；仅为未定日条件模型，不能当作当前价值。
        </p>
      )}
      <p>盈利 → 留存 → 经营资本／流动资本 → 条件分配 → 期末权益与现金代理</p>
      {review.scenarios.map((scenario) => (
        <details key={scenario.scenario} open>
          <summary>{names[scenario.scenario]} · 待审假设</summary>
          <p>
            条件估值：{Number(scenario.valuation_per_share).toFixed(2)}{" "}
            元／股；不是批准主估值或交易价格。
          </p>
          <details>
            <summary>每股估值完整值（元／股）</summary>
            <code>{scenario.valuation_per_share}</code>
          </details>
          <Funding status={String(scenario.ledger.cash_funding_status)} />
          <h5>共同驱动假设</h5>
          <dl
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(min(100%,220px),1fr))",
              gap: 12,
            }}
          >
            {Object.entries(scenario.drivers)
              .filter(([key]) => key !== "years")
              .map(([key, value]) => (
                <Value key={key} name={key} value={value} />
              ))}
          </dl>
          {scenario.ledger.rows.map((row, index) => (
            <details key={row.year}>
              <summary>
                第 {row.year} 年 · 未来假设 ·{" "}
                {row.cash_funding_status === "FAIL"
                  ? "资金演算 FAIL，有缺口"
                  : "资金演算 PASS，非批准"}
              </summary>
              <Funding status={String(row.cash_funding_status)} />
              <dl
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit,minmax(min(100%,220px),1fr))",
                  gap: 12,
                }}
              >
                <Value
                  name="revenue_growth"
                  value={scenario.drivers.years[index].revenue_growth}
                />
                <Value
                  name="cost_ratio"
                  value={scenario.drivers.years[index].cost_ratio}
                />
                {jointRowFields.map((key) => (
                  <Value key={key} name={key} value={row[key]} />
                ))}
              </dl>
            </details>
          ))}
          <details>
            <summary>终端条件（仍属假设）</summary>
            <p>
              终端 ROE 不等于已验证
              ROIC；终端增长、再投入与分配约束仍须经济判断。
            </p>
            <dl
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit,minmax(min(100%,220px),1fr))",
                gap: 12,
              }}
            >
              {jointTerminalFields.map((key) => (
                <Value key={key} name={key} value={scenario.ledger[key]} />
              ))}
            </dl>
          </details>
          <h5>反证与未解决条件</h5>
          <p>
            若归母现金转换不足、维持投入高于折旧摊销代理，或新增资本回报下降，本路径可能无法支持所列分配。以下限制来自原账本；
            {publicView
              ? "具体反证见本页条件研究分析。"
              : "具体反证见本次五组待审材料。"}
          </p>
          <ul>
            {scenario.ledger.limitations.map((text, index) => (
              <li key={index}>{limitations[text] ?? text}</li>
            ))}
          </ul>
        </details>
      ))}
      <details>
        <summary>原候选、提案与政策版本</summary>
        <p>
          选择：{review.selected_choice}；输入：
          <code>{review.input_descriptor_sha256}</code>
        </p>
        {[
          review.candidate_binding,
          review.proposal_binding,
          review.policy_binding,
        ].map((item, i) => (
          <p key={i}>
            <code>{item.path}</code>
            <br />
            <code>{item.sha256}</code>
          </p>
        ))}
      </details>
      <p>
        只读材料；正式批准、价格资格、仓位与操作状态均不改变。action=no_order。
      </p>
    </section>
  );
}

export const economicPathFields: Record<string, string[]> = {
  revenue: ["revenue", "cost"],
  earnings: [
    "pre_tax_profit",
    "tax",
    "legacy_parent_profit",
    "new_operating_profit",
    "new_liquidity_profit",
    "profit",
  ],
  capital: [
    "net_maintenance_cash_cny",
    "operating_wc_cash_cny",
    "commitment_cash_cny",
    "mandatory_cash",
  ],
  access: [
    "opening_cash",
    "accessible_profit",
    "newly_unremitted",
    "closing_unremitted",
  ],
  distribution: [
    "target_distribution",
    "cash_distribution_limit",
    "capacity_distribution_limit",
    "distribution",
  ],
  retention: [
    "opening_book",
    "retained",
    "closing_book",
    "closing_cash",
    "funding_shortfall",
  ],
};
const stageNames: Record<string, string> = {
  revenue: "营业收入与成本",
  earnings: "税后归母利润",
  capital: "必要投入与承诺",
  access: "可达现金与未上划资金",
  distribution: "受现金及容量约束的分配",
  retention: "留存与期末资本",
};
export function economicPathMatches(review: Readonly<JointReview>): boolean {
  const path = review.economic_path;
  if (!path) return true;
  try {
    return (
      path.action === "no_order" &&
      path.currency === "CNY" &&
      path.status === "CONDITIONAL_RESEARCH" &&
      path.period_basis === "MODEL_YEAR_NOT_DISCLOSED_FISCAL_YEAR" &&
      path.candidate_binding.path === review.candidate_binding.path &&
      path.candidate_binding.sha256 === review.candidate_binding.sha256 &&
      path.assumption_binding.path === review.policy_binding.path &&
      path.assumption_binding.sha256 === review.policy_binding.sha256 &&
      Array.isArray(path.scenarios) &&
      path.scenarios.length === review.scenarios.length &&
      path.scenarios.every((scenario, index) => {
        const consumed = review.scenarios[index];
        return (
          scenario.scenario === consumed.scenario &&
          Array.isArray(scenario.years) &&
          scenario.years.length === consumed.ledger.rows.length &&
          scenario.years.every((year, rowIndex) => {
            const row = consumed.ledger.rows[rowIndex];
            return (
              year.model_year === row.year &&
              Array.isArray(year.steps) &&
              year.steps.length === Object.keys(economicPathFields).length &&
              year.steps.every((step, stepIndex) => {
                const id = Object.keys(economicPathFields)[stepIndex];
                const fields = economicPathFields[id];
                const missing = fields.filter((field) => row[field] == null);
                return (
                  step.id === id &&
                  step.unit === "CNY" &&
                  step.classification === "CONDITIONAL_CALCULATION" &&
                  step.status === (missing.length ? "missing" : "available") &&
                  JSON.stringify(step.missing_fields) ===
                    JSON.stringify(missing) &&
                  Object.keys(step.values).length === fields.length &&
                  fields.every(
                    (field) =>
                      Object.prototype.hasOwnProperty.call(
                        step.values,
                        field,
                      ) && step.values[field] === (row[field] ?? null),
                  )
                );
              })
            );
          })
        );
      })
    );
  } catch {
    return false;
  }
}

const diagnosticNames: Record<string, string> = {
  first_year_distribution: "首年条件分配",
  cumulative_distribution: "十年累计条件分配",
  cumulative_profit: "十年累计归母盈利",
  cumulative_distribution_support_from_opening_resources:
    "各模型年分配期初资源支持下限的十年合计",
  net_period_resources: "当期净可达资源",
  target_reduction: "目标分配削减",
  distribution_support_from_opening_resources: "当年分配的期初资源支持下限",
  operating_resource_deficit: "经营资源缺口",
};
const constraintNames = {
  TARGET_POLICY: "目标政策",
  CASH_LIMIT: "现金上限",
  DISTRIBUTABLE_CAPACITY: "可分配容量",
};
const diagnosticStatuses = {
  FUNDING_SHORTFALL: "存在资金缺口",
  TARGET_CONSTRAINED: "目标分配受约束",
  TARGET_MET: "条件目标达到（非批准）",
};
function DiagnosticCoverage({ value }: { value: string | null }) {
  return value === null ? (
    <>不适用（条件分配为零，未按零覆盖率展示）</>
  ) : (
    <>
      {Number(value).toFixed(4)} 倍
      <details>
        <summary>覆盖倍数完整值</summary>
        <code>{value}</code>
      </details>
    </>
  );
}
function DistributionDiagnosticsPanel({
  review,
}: {
  review: Readonly<JointReview>;
}) {
  if (!review.distribution_diagnostics) return null;
  if (!distributionDiagnosticsMatch(review))
    return (
      <section aria-label="股东分配能力诊断">
        <h5>股东分配能力诊断</h5>
        <p role="alert">
          诊断不可评估、版本不支持或来源／年度账字段不匹配，已隐藏诊断数值；原研究继续保留。
        </p>
      </section>
    );
  const data = review.distribution_diagnostics;
  const amounts = (row: Record<string, unknown>, fields: readonly string[]) => (
    <dl>
      {fields.map((key) => (
        <Value
          key={key}
          name={key}
          label={diagnosticNames[key] ?? names[key]}
          value={row[key]}
        />
      ))}
    </dl>
  );
  return (
    <section aria-label="股东分配能力诊断">
      <h5>股东分配能力诊断：三情景条件摘要</h5>
      <p>
        未批准的研究假设，非实际现金流或分红承诺。金额以亿元展示（1亿元＝100000000元），完整元值可展开；模型年不是实际财报年度。action=no_order。
      </p>
      <p>
        覆盖率＝（可达盈利－强制投入）／条件分配，以倍数表示，不是实际自由现金流覆盖率，也不是市场股息率；零分配时不适用。期初资金依赖是诊断，不等于亏损或实际出金。十年路径不代表永久可持续。
      </p>
      <p>
        期初资源支持是各模型年用于分配的支持下限，经营资源缺口另列；累计值不是模型起始日所需初始现金，也不是总资金需求。例如当期净资源为-20、条件分配为20（同一金额单位）时，分配支持下限为20，经营缺口另为20，不能称总资金需求为20。
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,280px),1fr))",
          gap: 16,
          alignItems: "start",
        }}
      >
        {data.scenarios.map((scenario) => (
          <section
            key={scenario.scenario}
            aria-label={names[scenario.scenario] + "分配诊断"}
            style={{
              minWidth: 0,
              padding: 16,
              border: "1px solid #d9d9d9",
              borderRadius: 8,
              overflowWrap: "anywhere",
            }}
          >
            <h6>{names[scenario.scenario]} · 已核验条件账本，非实际现金流</h6>
            <p>
              {scenario.summary.opening_resources_used_years.length
                ? "本情景部分模型年的分配需要期初资源支持；该支持下限不包含另列的经营资源缺口，仍须核对现金底线、资金可达性及持续投入。"
                : "本情景未列出分配的期初资源支持，仅在当前假设下成立；现金可达性和持续投入仍需复核。"}
              {scenario.summary.minimum_distribution_coverage_ratio !== null &&
              Number(scenario.summary.minimum_distribution_coverage_ratio) < 1
                ? "最低覆盖倍数低于1，说明至少一个模型年的当期净可达资源不足以独立覆盖条件分配。"
                : "覆盖倍数不能替代对真实现金流和法定分配能力的核验。"}
              目标未削减或未列资金缺口均不等于安全，也不证明永久可持续。
            </p>
            {amounts(scenario.summary, [
              "first_year_distribution",
              "cumulative_distribution",
              "cumulative_profit",
              "cumulative_distribution_support_from_opening_resources",
              "closing_unremitted",
            ])}
            <dl>
              <dt>最低当期资源覆盖倍数</dt>
              <dd>
                <DiagnosticCoverage
                  value={scenario.summary.minimum_distribution_coverage_ratio}
                />
              </dd>
              <dt>目标分配削减的模型年</dt>
              <dd>
                {scenario.summary.target_reduced_years.join("、") ||
                  "无（仅本组假设）"}
              </dd>
              <dt>分配依赖期初资源的模型年</dt>
              <dd>
                {scenario.summary.opening_resources_used_years.join("、") ||
                  "无（仅本组假设）"}
              </dd>
              <dt>资金缺口的模型年</dt>
              <dd>
                {scenario.summary.funding_shortfall_years.join("、") ||
                  "无（仅本组假设）"}
              </dd>
            </dl>
            <details>
              <summary>{names[scenario.scenario]} · 展开十年分配诊断表</summary>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <caption>模型年度诊断；金额为亿元，覆盖率为倍数</caption>
                  <thead>
                    <tr>
                      <th scope="col">模型年</th>
                      <th scope="col">状态与约束</th>
                      <th scope="col">条件分配与资源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenario.years.map((year) => (
                      <tr key={year.model_year}>
                        <th scope="row">第 {year.model_year} 年</th>
                        <td>
                          {diagnosticStatuses[year.status]}
                          <p>
                            约束：
                            {year.binding_constraints
                              .map((key) => constraintNames[key])
                              .join("、") || "未列出"}
                          </p>
                        </td>
                        <td>
                          {amounts(year, [
                            ...distributionRawFields,
                            ...distributionDerivedFields,
                          ])}
                          <dl>
                            <dt>当期资源覆盖倍数</dt>
                            <dd>
                              <DiagnosticCoverage
                                value={year.distribution_coverage_ratio}
                              />
                            </dd>
                          </dl>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        ))}
      </div>
      <h6>诊断限制</h6>
      <ul>
        {data.limitations.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
      <p>诊断不改变正式资格、股数、买价或估值，仍为未批准条件研究。</p>
    </section>
  );
}

function CashCapitalLedger({ review }: { review: Readonly<JointReview> }) {
  const path = review.economic_path;
  const pathMatches = economicPathMatches(review);
  const v4 = review.schema_version === "joint-capital-cash-review-v4";
  const v3 = review.schema_version === "joint-capital-cash-review-v3";
  const economicTerminal = v3 || v4;
  const fields = (row: Record<string, unknown>, keys: readonly string[]) => (
    <dl
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,220px),1fr))",
        gap: 12,
      }}
    >
      {keys.map((key) => (
        <Value
          key={key}
          name={key}
          value={row[key]}
          label={
            v4 && key === "terminal_growth"
              ? "账面留存诊断比例（不参与 v4 尾值定价）"
              : undefined
          }
        />
      ))}
    </dl>
  );
  const funding = (status: unknown) =>
    status === "SHORTFALL" ? (
      <p role="alert">
        SHORTFALL：资金约束存在缺口，不能认定可分红；负值按原账本保留。
      </p>
    ) : (
      <p>FUNDED：仅为假设下资金演算通过，不代表法定分配能力或批准。</p>
    );
  return (
    <section
      aria-label="十年现金约束联合资本路径待审"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h4>联合资本路径：三情景 10年现金约束条件演算</h4>
      <p>
        候选选择依据：
        {typeof review.selection_reason === "string"
          ? review.selection_reason
          : "本候选未提供独立选择理由"}
      </p>
      <p>
        决定性反证：
        {typeof review.selection_countercase === "string"
          ? review.selection_countercase
          : "本候选未提供独立反证，请查看研究限制"}
      </p>
      {review.historical_input_mapping && (
        <details>
          <summary>历史输入与研究口径映射（不全部等同财报事实）</summary>
          <p>
            历史金额、期间桥接及资金映射可能具有不同性质，以每项口径说明为准。来源编号对应下列已绑定研究输入；原件出处见本页证据。
          </p>
          {Object.entries(review.historical_input_mapping)
            .filter(([, item]) => item != null && typeof item === "object")
            .map(([field, item]) => {
              const input = item as Record<string, unknown>;
              return (
                <div key={field}>
                  <strong>{names[field] || field}</strong>
                  <p>
                    {String(input.value ?? "缺失")}{" "}
                    {String(input.unit ?? "单位未提供")} ·{" "}
                    {String(input.scope ?? "口径未提供")}
                  </p>
                  <p>
                    {String(
                      input.rationale ?? "性质及推导依据未提供，不能认定为事实",
                    )}
                  </p>
                  <p>
                    来源 {String(input.source_id ?? "未提供")} · 字段{" "}
                    {Array.isArray(input.field_path)
                      ? input.field_path.join(".")
                      : "未提供"}
                  </p>
                </div>
              );
            })}
          {(Array.isArray(review.research_input_bindings)
            ? review.research_input_bindings
            : []
          )
            .filter(
              (binding) =>
                binding &&
                typeof binding.path === "string" &&
                typeof binding.sha256 === "string",
            )
            .map((binding) => (
              <p key={binding.path}>
                来源{" "}
                {typeof binding.id === "string" ? binding.id : "未提供编号"} ·
                可用时间{" "}
                {typeof binding.available_at === "string"
                  ? binding.available_at
                  : "未提供"}{" "}
                · {binding.path} · SHA256 {binding.sha256}
              </p>
            ))}
        </details>
      )}
      <CandidatePriceDraft review={review} />
      <DistributionDiagnosticsPanel review={review} />
      {path && !pathMatches && (
        <p role="alert">经济路径投影与已消费年度账不一致，暂不展示该投影。</p>
      )}
      {path && pathMatches && (
        <section aria-label="经营到股东现金的可审阅路径">
          <h5>经营到股东现金：逐步查看计算结果</h5>
          <p>
            以下为已消费账本的条件计算，金额单位人民币元；第几年是模型期间，不是实际财报年度。
          </p>
          {review.economic_path.scenarios.map((scenario) => (
            <details
              key={scenario.scenario}
              open={scenario.scenario === "base"}
            >
              <summary>
                {names[scenario.scenario] || scenario.scenario} · 经济路径
              </summary>
              {scenario.years.map((year) => (
                <details key={year.model_year} open={year.model_year === 1}>
                  <summary>模型第 {year.model_year} 年</summary>
                  <ol>
                    {year.steps.map((step) => (
                      <li key={step.id}>
                        <strong>{stageNames[step.id]}</strong>
                        <p>已消费账本的条件计算，非披露事实或分红承诺。</p>
                        {step.status === "missing" && (
                          <p role="status">
                            缺少：{step.missing_fields.join("、")}
                          </p>
                        )}
                        <dl>
                          {Object.entries(step.values).map(([field, value]) => (
                            <div key={field}>
                              <dt>{names[field] || field}</dt>
                              <dd>
                                {value == null
                                  ? "缺失，未补零"
                                  : Number(value).toLocaleString("zh-CN", {
                                      maximumFractionDigits: 2,
                                    })}{" "}
                                {value == null ? "" : "元"}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </li>
                    ))}
                  </ol>
                </details>
              ))}
            </details>
          ))}
        </section>
      )}
      <p>
        未批准 · 经营 → 现金 → 分配 →
        留存。全部前瞻数据均为研究假设，不是正常化事实或母公司法定可分配现金。
      </p>
      {review.date_scope === "DATED_CONDITIONAL_MODEL" ? (
        <p>
          资料基准：{review.basis_at}；估值时点：{review.valuation_at}
          。不是行情日期。
        </p>
      ) : (
        <p role="alert">
          未建立定价时点：仅为未定日条件模型，不能当作当前价值。
        </p>
      )}
      {review.scenarios.map((scenario) => {
        const ledger = scenario.ledger;
        const terminal = ledger.terminal as Record<string, unknown>;
        const policy = ledger.terminal_policy as Record<string, unknown>;
        const economics = scenario.terminal_economics;
        const v4Economics =
          economics?.terminal_contract_version ===
          "terminal-economic-contract-v2"
            ? economics
            : undefined;
        return (
          <details key={scenario.scenario} open>
            <summary>{names[scenario.scenario]} · 10年 · 未批准</summary>
            <p>
              条件估值：{Number(scenario.valuation_per_share).toFixed(2)}{" "}
              元／股；不是批准主估值或交易价格。
            </p>
            <details>
              <summary>每股估值完整值（元／股）</summary>
              <code>{scenario.valuation_per_share}</code>
            </details>
            {funding(ledger.funding_status)}
            <h5>经营与资本驱动假设</h5>
            {fields(scenario.drivers, [
              "operating_allocation",
              "new_operating_return",
              "new_liquidity_return",
            ])}
            {ledger.rows.map((row, index) => (
              <details key={row.year}>
                <summary>
                  第 {row.year} 年 · 经营／现金／分配／留存 ·{" "}
                  {String(row.funding_status)} · 未来假设
                </summary>
                {funding(row.funding_status)}
                <h5>经营假设与盈利</h5>
                {fields(scenario.drivers.years[index], [
                  "revenue_growth",
                  "cost_ratio",
                  ...jointCashPolicyFields,
                ])}
                {fields(row, jointCashOperatingFields)}
                {fields(row.expenses as Record<string, unknown>, [
                  "surcharges",
                  "selling",
                  "admin",
                  "research",
                ])}
                <h5>现金约束、实际分配与年度留存</h5>
                {fields(row, jointCashRowFields)}
              </details>
            ))}
            <details>
              <summary>
                {economicTerminal
                  ? "尾期经济合同：资本用途／维护／WC／承诺与股东分配"
                  : "持续终端：维护／WC／承诺与分配约束"}
              </summary>
              <p>
                {economicTerminal
                  ? "账面留存不会自动转化为终端增长；只有明确投入生产资本并具有边际回报，才会形成新增盈利。维护、营运资金、承诺支出和受限资金按声明机制递推。"
                  : "终端必要支出单独持续设定，不从第10年自动延续，也不把缺失需求当作零。终端 ROE 不是已验证 ROIC。"}
              </p>
              {fields(policy, [...jointCashPolicyFields, "profit_scale"])}
              <p>终端持续依据：{String(policy.rationale)}</p>
              {economicTerminal && economics ? (
                <>
                  <h5>终端机制与关键前提</h5>
                  <ul>
                    <li>机制：{economics.mechanism}</li>
                    <li>合同版本：{economics.terminal_contract_version}</li>
                    <li>存量盈利：{String(policy.legacy_profit_dynamics)}</li>
                    <li>
                      首笔分配时点：{String(policy.first_distribution_timing)}
                    </li>
                    <li>承诺持续期：{String(policy.commitment_occurrences)}</li>
                    <li>
                      受限资金释放年份：
                      {String(policy.restricted_cash_release_year)}
                    </li>
                    <li>尾期递推年数：{economics.terminal_years_evaluated}</li>
                    {v4 && v4Economics ? (
                      <>
                        <li>
                          尾期解析方法：{v4Economics.terminal_value_method}
                        </li>
                        <li>
                          第10年末总权益解析尾项截断误差上限：
                          {v4Economics.terminal_value_error_bound_cny} CNY
                        </li>
                        <li>
                          估值日每股解析尾项截断误差上限：
                          {
                            v4Economics.terminal_value_error_bound_valuation_date_per_share
                          }{" "}
                          元／股
                        </li>
                        <li>
                          净盈余桥有限精度校验容差：
                          {
                            v4Economics.terminal_bridge_arithmetic_tolerance_cny
                          }{" "}
                          CNY
                        </li>
                        <li>经济假设不确定性：未包含在上述数值误差上限中</li>
                        <li>
                          终端增长字段状态：账面留存诊断，不参与 v4 尾值定价
                        </li>
                        <li>
                          最后计划事件年：
                          {v4Economics.terminal_last_scheduled_event_year}
                        </li>
                      </>
                    ) : null}
                  </ul>
                  <h5>显式期与尾期价值贡献</h5>
                  {fields(economics as unknown as Record<string, unknown>, [
                    "explicit_distribution_pv_cny",
                    "terminal_value_at_year_10_cny",
                    "terminal_distribution_value_cny",
                    "terminal_convergence_residual_cny",
                    "ri_ddm_difference_cny",
                  ])}
                  <h5>终端合同主要限制</h5>
                  <ul>
                    {economics.limitations.map((text, index) => (
                      <li key={index}>{text}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {funding(terminal.funding_status)}
              {fields(terminal, jointCashRowFields)}
              {fields(ledger, jointCashTerminalFields)}
            </details>
            <h5>反证与未解决条件</h5>
            <p>
              若现金可取得比例下降、净维护／营运资金／承诺支出上升或新增资本回报不足，条件分配与估值可能不成立。资金演算通过不构成批准。
            </p>
            <ul>
              {ledger.limitations.map((text, index) => (
                <li key={index}>{text}</li>
              ))}
            </ul>
          </details>
        );
      })}
      <details>
        <summary>原候选、提案与政策版本</summary>
        <p>
          选择：{review.selected_choice}；输入：
          <code>{review.input_descriptor_sha256}</code>
        </p>
        {[
          review.candidate_binding,
          review.proposal_binding,
          review.policy_binding,
        ].map((ref, i) => (
          <p key={i}>
            <code>{ref.path}</code>
            <br />
            <code>{ref.sha256}</code>
          </p>
        ))}
      </details>
      <p>
        只读未批准材料；正式批准、价格资格、仓位与操作状态均不改变。action=no_order。
      </p>
    </section>
  );
}
