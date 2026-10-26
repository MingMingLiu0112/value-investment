import type {
  PolicyHandoff,
  JointCapitalReview as JointReview,
} from "../services/valuePolicy";
import type { ValueResearchAnalysis } from "../types/api";
import {
  jointCapitalReviewMatches,
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

function Value({ name, value }: { name: string; value: unknown }) {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    !Number.isFinite(Number(value))
  )
    return (
      <div>
        <dt>{names[name] ?? name}</dt>
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
      <dt>{names[name] ?? name}</dt>
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

function CashCapitalLedger({ review }: { review: Readonly<JointReview> }) {
  const v3 = review.schema_version === "joint-capital-cash-review-v3";
  const fields = (row: Record<string, unknown>, keys: readonly string[]) => (
    <dl
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,220px),1fr))",
        gap: 12,
      }}
    >
      {keys.map((key) => (
        <Value key={key} name={key} value={row[key]} />
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
                {v3
                  ? "尾期经济合同：资本用途／维护／WC／承诺与股东分配"
                  : "持续终端：维护／WC／承诺与分配约束"}
              </summary>
              <p>
                {v3
                  ? "账面留存不会自动转化为终端增长；只有明确投入生产资本并具有边际回报，才会形成新增盈利。维护、营运资金、承诺支出和受限资金按声明机制递推。"
                  : "终端必要支出单独持续设定，不从第10年自动延续，也不把缺失需求当作零。终端 ROE 不是已验证 ROIC。"}
              </p>
              {fields(policy, [...jointCashPolicyFields, "profit_scale"])}
              <p>终端持续依据：{String(policy.rationale)}</p>
              {v3 && economics ? (
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
