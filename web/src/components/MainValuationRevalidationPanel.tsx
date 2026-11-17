import { Alert } from "antd";
import type { MainValuationRevalidationRecord } from "../services/api";

const NAMES: Record<string, string> = {
  DERIVED_FACT: "由已报告期间差额派生（非预测）",
  balances: "母公司历史账面余额（元）",
  cash_equivalents: "母公司现金及现金等价物",
  dividend_payable: "已宣派股利（仅预留一次）",
  short_term_borrowings: "短期借款",
  current_noncurrent_liabilities: "一年内到期的非流动负债",
  other_payables_including_dividend: "其他应付款（含股利）",
  trade_payables: "应付账款",
  advance_receipts: "预收款项",
  contract_liabilities: "合同负债",
  employee_payables: "应付职工薪酬",
  tax_payables: "应交税费",
  other_current_liabilities: "其他流动负债",
  current_liabilities_total: "流动负债合计",
  noncurrent_borrowings: "非流动借款余额",
  retained_profit: "未分配利润（非现金）",
  NONPRODUCTIVE_LIABILITY_SETTLEMENT: "非生产性负债清偿（不是CapEx或新分红）",
  pressure: "母公司条件义务压力",
  effective_cash_floor_cny: "实际进入模型的现金约束（元）",
  reservation_horizon: "义务占用期限假设",
  CONTINUOUS_LOCK_NO_AUTOMATIC_RELEASE_TEN_YEARS:
    "十年持续占用，不自动释放（假设）",
  declared_dividend_reserved_once: "已宣派股利只预留一次",
  wc_excludes_opening_payable_settlement: "营运资本不重扣期初已预留应付",
  net_maintenance_ex_rou_proxy_cny:
    "不扣使用权折旧的净维护代理（元，非维护事实）",
  wc_ex_payables_proxy_cny: "排除应付结算的营运资本代理（元）",
  rou_da_not_subtracted: "未减使用权折旧",
  wc_basis: "首年营运资本代理依据",
  later_wc_basis: "后续营运资本假设",
  EXPLICIT_HYPOTHESIS_NOT_MAINTENANCE_FACT: "显式假设，不是维护资本开支事实",
  FIRST_MODEL_YEAR_ONLY_INVENTORY_RECEIVABLE_PROXY_EXCLUDES_RESERVED_PAYABLES:
    "仅首年存货/应收代理，排除已预留应付",
  ZERO_INCREMENT_NO_RELEASE_UNDER_FROZEN_NOMINAL_EARNINGS_HYPOTHESIS:
    "冻结名义盈利假设下零增量，不自动释放",
  UNAPPROVED_DATED_RESEARCH_DRAFT: "带日期未批准研究草案（未注册）",
  settlement_schedule: "逐年负债清偿计划",
  liability_settlement_schedule: "逐年负债清偿计划",
  permanent_lock_pressure_comparison: "旧永锁压力比较（非本次支付政策）",
  initial_outstanding_cny: "计划期初账面义务（元）",
  terminal_outstanding_cny: "计划终端未偿余额（元）",
  opening_outstanding_cny: "期初未偿余额（元）",
  payment_cny: "假定清偿金额（元）",
  closing_outstanding_cny: "期末未偿余额（元）",
  opening_balance_cny: "逐项期初余额（元）",
  closing_balance_cny: "逐项期末余额（元）",
  obligation_id: "义务类别",
  year: "模型年",
  items: "逐项清偿",
  liability_settlement_cny: "非生产性负债清偿（元）",
  economic_capital_cash_cny: "经济性资本支出（元）",
  new_shareholder_distribution: "属于新股东分配",
  productive_capital_addition: "新增生产性资本",
  maturity_dates_proven: "真实到期日期已证",
  UNSCHEDULED_OTHER_CURRENT_AND_CASH_FLOOR_REMAIN_RESERVED:
    "未排程其他流动义务与现金准备金继续占用",
  DRAFT: "未批准草案",
  draft: "未批准规则草案",
  diagnostic_preview_prices: "草案算术预览（非当前行动价）",
  effective_from: "草案起始日期",
  effective_through: "草案截止日期",
  dividend_coverage_risk: "分红政策覆盖风险",
  thesis_reviews: "重开条件",
  registered: "已注册",
  value_fraction: "显式情景值比例（非默认折价）",
  comparison: "草案比较方向",
  rule_version: "规则版本",
  policy_id: "政策标识",
  BUY: "BUY规则研究预览（非买入建议）",
  ADD: "ADD规则研究预览（非加仓建议）",
  HOLD: "HOLD规则研究预览（非持有建议）",
  REDUCE: "REDUCE规则研究预览（非减仓建议）",
  EXIT: "EXIT规则研究预览（非卖出建议）",
  DATED_RESEARCH_REVIEW_THRESHOLDS: "带日期研究复核阈值",
  bear_value: "下行情景计算值（元/股）",
  base_value: "工作情景计算值（元/股，未采用Base）",
  bull_value: "上行情景计算值（元/股）",
  valuation_basis_date: "估值基准日",
  values: "计算区间",
  economic_approval: "经济批准",
  current_action_price: "当前行动价格",

  CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW:
    "条件研究工作候选，待人工经济复核（未采用主区间）",
  NOT_STARTED: "未开始",
  UNASSESSABLE: "不可核验",
  NOT_PREPARED: "尚未准备",
  REPORTED_FACT: "已报告实际",
  FORECAST_ASSUMPTION: "条件预测假设",
  bear: "下行情景",
  base: "工作情景（未采用Base）",
  bull: "上行情景",
  period_start: "期间起点",
  period_end: "期间终点",
  period_basis: "期间口径",
  kind: "性质",
  scope: "范围",
  currency: "币种",
  group_pbt_cny: "合并税前利润（元）",
  income_tax_cny: "所得税（元）",
  signed_nci_cny: "带符号少数损益（元）",
  parent_profit_cny: "归母利润（元）",
  source_refs: "来源引用",
  assumption_refs: "假设引用",
  source_binding: "来源绑定",
  source_spec: "独立输入版本",
  source_catalog: "来源目录",
  evidence_refs: "证据引用",
  rationale: "理由",
  reason: "原因",
  text: "说明",
  status: "状态",
  financial_basis: "财务基准",
  as_of: "研究日期",
  latest_actual_period: "最新实际期间",
  low: "低",
  LOW: "低",
  confidence: "置信度",
  limitations: "限制",
  unknowns: "未知与待补证",
  snapshot: "母公司历史快照",
  scenarios: "条件路径",
  per_scenario: "分情景义务压力",
  effective_cash_floor: "实际进入模型的现金约束",
  cash_floor_cny: "现金准备金假设（元）",
  conditional_cash_residual_cny: "条件现金余量（非当前能力，元）",
  current_capacity_proven: "当前容量已证",
  capacity_proven: "分配能力已证",
  debt_book_reserve_cny: "负债账面预留（元）",
  other_current_book_reserve_cny: "其他流动义务预留（元）",
  incremental_floor_cny: "增量现金准备金（元）",
  future_investment_reserve_cny: "未来投入预留（元）",
  floor_semantics: "准备金语义",
  unresolved: "未解决事项",
  key_findings: "核对要点",
  current_parent_cash_cny: "当前母公司现金（元）",
  current_distribution_capacity_cny: "当前分配能力（元）",
  actual_funding_shortfall_cny: "实际资金缺口（元）",
  formal_eligibility: "正式资格",
  current_comparable: "可与现价比较",
  quantity: "个人数量",
  CNY: "人民币",
  consolidated: "合并",
  consolidated_parent: "合并归母",
  parent: "母公司",
  action: "操作",
  no_order: "不下单",
  minimum: "下界",
  maximum: "上界",
  lower: "下界",
  upper: "上界",
  rules: "阈值规则与理由",
  draft_prices: "带日期未批准阈值",
  valuation_date: "估值基准日",
  date: "日期",
  threshold: "阈值",
  price: "条件阈值（非当前买价）",
  basis: "依据",
  classification: "性质",
  value: "值",
  amount: "金额",
  target: "目标",
  cash: "现金",
  evidence_ids: "证据编号",
};
const SCENARIOS = ["bear", "base", "bull"] as const;
function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
const BALANCE_MONEY_KEYS = new Set([
  "cash_equivalents",
  "dividend_payable",
  "short_term_borrowings",
  "current_noncurrent_liabilities",
  "other_payables_including_dividend",
  "trade_payables",
  "advance_receipts",
  "contract_liabilities",
  "employee_payables",
  "tax_payables",
  "other_current_liabilities",
  "current_liabilities_total",
  "noncurrent_borrowings",
  "retained_profit",
]);
function scalar(value: unknown, key = "") {
  if (value === null || value === undefined || value === "UNKNOWN")
    return "未知/空，不补零";
  if (typeof value === "boolean") return value ? "是" : "否";
  const str = String(value);
  if (
    (/_cny$/.test(key) ||
      /^(bear|base|bull)_value$/.test(key) ||
      BALANCE_MONEY_KEYS.has(key)) &&
    /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(str)
  ) {
    const number = Number(str);
    if (Number.isFinite(number))
      return number.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
  }
  return NAMES[str] || str;
}
function RecordView({ value, field = "" }: { value: unknown; field?: string }) {
  if (Array.isArray(value))
    return value.length ? (
      <ul>
        {value.map((row, i) => (
          <li key={i}>
            <RecordView value={row} field={field} />
          </li>
        ))}
      </ul>
    ) : (
      <p>未提供条目，不推定已满足。</p>
    );
  if (value !== null && typeof value === "object")
    return (
      <dl>
        {Object.entries(record(value)).map(([key, item]) => (
          <div key={key}>
            <dt>{NAMES[key] || <code>{key}</code>}</dt>
            <dd>
              {/source|evidence|binding|fingerprint|sha256|assumption_refs|baseline_component_rows|drivers|components|derivation|projection/.test(
                key,
              ) ? (
                <details>
                  <summary>
                    {/settlement_schedule/.test(key)
                      ? "查看逐年清偿及未偿余额"
                      : "查看来源/版本/假设明细"}
                  </summary>
                  <RecordView value={item} field={key} />
                </details>
              ) : (
                <RecordView value={item} field={key} />
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{scalar(value, field)}</span>;
}
export function MainValuationRevalidationPanel({
  value,
  symbol,
}: {
  value: MainValuationRevalidationRecord;
  symbol: string;
}) {
  if (
    value.action !== "no_order" ||
    value.formal_eligibility !== false ||
    (value.symbol !== undefined && value.symbol !== symbol)
  )
    return (
      <Alert
        type="warning"
        message="经营现金估值重验身份或只读边界不符，本区停止展示；其他研究保留"
      />
    );
  if (value.status === "NOT_STARTED" || value.status === "UNASSESSABLE")
    return (
      <section aria-label="经营现金估值重验">
        <h3>经营—现金—估值重验</h3>
        <Alert
          type="info"
          message={
            value.status === "NOT_STARTED"
              ? "尚无新的估值重验结果"
              : "新的估值重验暂不可核验"
          }
          description={scalar(value.reason || value.error_code || value.status)}
        />
      </section>
    );
  if (
    ![
      "CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW",
      "PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW",
    ].includes(String(value.status)) ||
    value.symbol !== symbol ||
    value.schema_version !== "main-valuation-revalidation-v1" ||
    value.approval_changed !== false ||
    value.formal_fact_count !== 0 ||
    value.main_range_adopted !== false ||
    value.current_comparable !== false ||
    value.quantity !== null ||
    value.personal_quantity !== null ||
    value.condition_price !== null
  )
    return (
      <Alert
        type="warning"
        message="新研究候选的采用、价格或数量边界不符，本区停止展示；其他研究保留"
      />
    );
  const partial =
    value.status === "PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW";
  const periods = record(value.period_assembly),
    scenarios = record(periods.scenarios);
  const ledgers = record(value.annual_ledgers),
    valuation = record(value.valuation),
    prices = record(value.price_policy);
  const draft = record(prices.draft);
  const draftMetadataValid =
    prices.formal_eligibility === false &&
    prices.economic_approval === false &&
    prices.current_action_prices === null &&
    prices.registered === false &&
    draft.status === "DRAFT" &&
    draft.action === "no_order" &&
    draft.registered === false &&
    typeof draft.effective_from === "string" &&
    typeof draft.effective_through === "string" &&
    typeof draft.rationale === "string" &&
    !!draft.rationale.trim();
  const datedDraft =
    !partial &&
    prices.status === "UNAPPROVED_DATED_RESEARCH_DRAFT" &&
    draftMetadataValid;
  return (
    <section
      aria-label="经营现金估值重验"
      style={{ marginBlock: 20, overflowWrap: "anywhere" }}
    >
      <h3>
        {partial
          ? "部分情景重验：整包未形成完整研究候选"
          : "新的经营—现金—估值研究候选"}
      </h3>
      <Alert
        type="warning"
        message={
          partial
            ? "部分情景未通过，保留准确失败原因，不补造整包估值"
            : "条件研究工作候选，待人工经济复核；主区间尚未采用，不是投资批准"
        }
        description="正式资格：否（formal=false）；不下单（no_order）；不比较现价（current_comparable=false）；个人数量：空（quantity=null）。"
      />
      <p>独立重验结果与旧压力研究分别保留，不以旧结果冒充本次实际消费。</p>
      <p>
        研究日期：{scalar(value.as_of)}；财务基准：
        {scalar(value.financial_basis)}； 最新实际期间：
        {scalar(value.latest_actual_period)}；置信度：{scalar(value.confidence)}
        。
      </p>
      {partial ? (
        <section>
          <h4>分情景未通过原因</h4>
          <RecordView value={value.scenario_failures} />
        </section>
      ) : (
        <>
          <h4>模型估值区间（元/股；未采用、低置信度条件候选）</h4>
          <table>
            <thead>
              <tr>
                <th>情景</th>
                <th>条件模型值</th>
              </tr>
            </thead>
            <tbody>
              {SCENARIOS.map((name) => (
                <tr key={name}>
                  <th>{NAMES[name]}</th>
                  <td>{scalar(valuation[name + "_value"], name + "_value")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            估值日期：{scalar(valuation.valuation_date)}；估值置信度：
            {scalar(value.confidence || valuation.confidence)}
            。未进行当前报价比较。
          </p>
        </>
      )}
      <Alert
        type="warning"
        message={
          value.policy_not_fully_modelled === true
            ? "分红政策尚未完整建模，不能据此判断政策履约或违约"
            : "分红政策模型覆盖尚未核验，不推定已覆盖"
        }
      />
      {!partial && value.dated_research_review_thresholds != null && (
        <section>
          <h4>带日期研究复核阈值（非当前行动价格）</h4>
          {record(value.dated_research_review_thresholds).status ===
          "NOT_PREPARED" ? (
            <p>
              研究复核阈值尚未准备：未选择实际规则，不把估值区间复制为价格阈值。
            </p>
          ) : (
            <>
              <p>
                仅按本次回传的日期、规则和理由供研究复核，不是当前买价；不与现价比较，不产生个人数量或订单。
              </p>
              <RecordView value={value.dated_research_review_thresholds} />
            </>
          )}
        </section>
      )}
      <h4>带日期、未批准的条件阈值</h4>
      {prices.status === "NOT_PREPARED" ||
      !Array.isArray(prices.rules) ||
      prices.rules.length === 0 ? (
        <>
          <p>
            价格政策尚未准备（{scalar(prices.status)}
            ）；没有阈值规则与理由，不补造条件价。
          </p>
          {draftMetadataValid && (
            <p>
              现有引擎已生成未批准、未注册草案：{scalar(draft.effective_from)}{" "}
              ～ {scalar(draft.effective_through)}； 理由：
              {scalar(draft.rationale)}。尚未选择数值规则，无当前买价。
            </p>
          )}
        </>
      ) : datedDraft ? (
        <>
          <p>以下仅为带日期未批准条件阈值，不是当前买价，不与现价比较。</p>
          <RecordView value={prices} />
        </>
      ) : (
        <Alert
          type="warning"
          message="价格草案的未批准、日期或理由边界未核验，数值不展示"
        />
      )}
      <h4>新Q3实际与季节性条件预测</h4>
      <p>
        新实际和预测分列，不将Q3、Q4与次年H1重复计入；预测假设不是已报告事实。
      </p>
      <section>
        <h5>Q3实际（9M－H1）</h5>
        <RecordView value={periods.q3_actual} />
      </section>
      {SCENARIOS.map((name) => {
        const path = record(scenarios[name]);
        return (
          <section key={name}>
            <h5>{NAMES[name]}：Q4与次年H1预测</h5>
            <RecordView value={path.q4_forecast} />
            <RecordView value={path.h1_next_forecast} />
            <details>
              <summary>完整模型年度组装与来源</summary>
              <RecordView value={path.model_years} />
            </details>
          </section>
        );
      })}
      <p>
        模型值仅作展示四舍五入，不在页面重算。负债清偿不是新分红或CapEx，不与年度新distribution相加作为股东回报。
      </p>
      <h4>十年现金与权益账</h4>
      {SCENARIOS.map((name) => {
        const ledger = record(ledgers[name]),
          rows = Array.isArray(ledger.rows) ? ledger.rows : [];
        return (
          <section key={name}>
            <p>
              {NAMES[name]}：实际回传 {rows.length} 行年度现金账；不补造缺行。
            </p>
            <details>
              <summary>{NAMES[name]}：逐年现金表及约束</summary>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      {[
                        "期间",
                        "归母利润（元）",
                        "可达利润（元）",
                        "义务现金（元）",
                        "年度新假设分配（元）",
                        "非生产性负债清偿（元，已含义务现金）",
                        "期末现金（元）",
                        "期末权益（元）",
                      ].map((title) => (
                        <th key={title}>{title}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((raw, i) => {
                      const row = record(raw);
                      return (
                        <tr key={i}>
                          <td>
                            {scalar(row.period_start)} ～{" "}
                            {scalar(row.period_end)}
                          </td>
                          {[
                            "profit",
                            "accessible_profit",
                            "mandatory_cash",
                            "distribution",
                            "closing_cash",
                            "closing_book",
                          ].map((key) => (
                            <td key={key}>{scalar(row[key], key + "_cny")}</td>
                          ))}
                          <td>
                            {scalar(
                              record(row.cash_use_breakdown)
                                .liability_settlement_cny,
                              "liability_settlement_cny",
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <RecordView value={ledger.limitations} />
            </details>
          </section>
        );
      })}
      <h4>现金投入、营运资本与清偿政策（模型假设）</h4>
      <RecordView value={value.cash_input_basis} />
      <h4>母公司义务与实际现金限制（条件，非当前容量证明）</h4>
      <p>
        母公司义务的预留或假定支付仅为模型处理，不等于当日全额到期或已偿付；不重复扣已宣派股利、历史资本开支或营运资本。准备金与投入仍为假设，不证明当前可分配能力。
      </p>
      <p>
        清偿计划按返回的账面义务合计展示，付款年是研究假设，不证明真实到期或已付款；不重复扣旧股利，也不是新股东回报。
      </p>
      {SCENARIOS.map((name) => {
        const parent = record(record(value.parent_obligations).per_scenario),
          own = record(parent[name]);
        const schedule = record(
          own.settlement_schedule || own.liability_settlement_schedule,
        );
        const rows = Array.isArray(schedule.rows) ? schedule.rows : [],
          first = record(rows[0]);
        return (
          <section key={name}>
            <p>
              {NAMES[name]}：三项账面义务计划期初合计{" "}
              {scalar(
                schedule.initial_outstanding_cny,
                "initial_outstanding_cny",
              )}{" "}
              元； 模型年1假定支付 {scalar(first.payment_cny, "payment_cny")}{" "}
              元；终端未偿{" "}
              {scalar(
                schedule.terminal_outstanding_cny,
                "terminal_outstanding_cny",
              )}{" "}
              元。
            </p>
            <details>
              <summary>
                {NAMES[name]}：逐项与逐年清偿（opening/payment/closing）
              </summary>
              <RecordView value={schedule} />
            </details>
          </section>
        );
      })}
      <details>
        <summary>母公司快照、现金限制及旧永锁压力比较</summary>
        <RecordView value={value.parent_obligations} />
      </details>
      <h4>反证与未知</h4>
      <RecordView value={value.counter_evidence} />
      <RecordView value={value.unknowns} />
      <details>
        <summary>版本绑定与其他限制</summary>
        <RecordView
          value={{
            source_spec: value.source_spec,
            input_descriptor_sha256: value.input_descriptor_sha256,
            limitations: value.limitations,
          }}
        />
      </details>
    </section>
  );
}
