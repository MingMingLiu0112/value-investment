import { MainValuationRevalidationPanel } from "./MainValuationRevalidationPanel";
import { ParentFundingResearchPanel } from "./ParentFundingResearchPanel";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Space, Table } from "antd";
import {
  api,
  ApiError,
  type LiveOperatingResearchTask,
  type OperatingResearchModelStatus,
  type PublicOperatingResearchResult,
  type PublicOperatingResearchSuccess,
  type PublicOperatingResearchPartial,
  type OperatingResearchRoleKey,
  type OperatingDriverBridge,
  type OperatingDriverKey,
  type OperatingDriverScenario,
  type OperatingDriverRange,
  type CurrentCapitalObservation,
  type FiscalDistributionReview,
  type FiscalDistributionScenario,
} from "../services/api";

const LABELS: Record<string, string> = {
  PROJECTED_YOY_SAME_PERIOD: "与历史基线相邻年份的同期间投影同比",
  CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY:
    "相对历史基线的累计变化，不是逐年同比",
  REOPEN_RESEARCH_ONLY_NOT_AUTOMATIC_REVISION:
    "仅重开研究，不自动修订假设或批准",
  COMPARABLE: "同期间可比较",
  NONPOSITIVE_BASE_NOT_ASSESSABLE: "历史基数非正，变化率不可评估",
  H1: "半年口径",
  FY: "全年口径",
  consolidated: "合并口径",
  business_drivers: "经营驱动",
  scenarios: "条件情景",
  bear: "压力条件情景",
  base: "中间条件情景（未采用主区间）",
  bull: "修复条件情景",
  counterevidence: "反证",
  invalidation: "失效条件",
  seen_events: "已见事件",
  uncovered: "未覆盖事项",
  dimension: "经济维度",
  growth: "增长",
  profit: "盈利",
  investment: "再投资",
  funding_access: "资金可达性",
  terminal: "终端持续性",
  period_start: "期间起点",
  period_end: "期间终点",
  classification: "性质",
  lower: "下界",
  upper: "上界",
  unit: "单位",
  evidence_ids: "证据编号",
  FORECAST: "条件经营假设",
  UNKNOWN: "未知，未证明",
  ratio: "比率",
  not_quantified: "未量化",
  CNY: "人民币元",
  FUNDAMENTAL: "经营基本面",
  COUNTER_EVIDENCE: "反证与失效",
  EVENT: "事件研究",
  PARTIAL: "部分研究可读，任务未全部完成",
  QUEUED: "已排队",
  RUNNING: "研究中",
  SUCCEEDED: "任务完成",
  FAILED: "任务失败",
  CANCELLED: "已取消",
  WAITING_EVIDENCE: "等待证据",
  thesis: "研究判断",
  summary: "摘要",
  rationale: "理由",
  text: "说明",
  counter_evidence: "反证",
  thesis_breakers: "失效条件",
  next_events: "后续事件",
  findings: "研究发现",
  evidence_refs: "证据引用",
  unknowns: "未知与待补证",
};
export function Readable({ value }: { value: unknown }) {
  if (value == null) return <p>未提供，不补零</p>;
  if (Array.isArray(value))
    return (
      <ul>
        {value.map((item, i) => (
          <li key={i}>
            <Readable value={item} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <dl>
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt>{LABELS[key] || key}</dt>
            <dd>
              <Readable value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{LABELS[String(value)] || String(value)}</span>;
}
const DRIVER_LABELS: Record<OperatingDriverKey, string> = {
  volume_change: "活动量指数变化",
  realization_mix_change: "实现价与产品组合变化",
  unit_cost_change: "整体营业成本水平变化（假设）",
  fixed_cogs_share: "基期营业成本的非活动量敏感份额（假设）",
  opex_change: "期间费用变化",
  surcharge_ratio: "税金及附加占收入比率",
  other_pretax_cny: "其他税前残差（元）",
};
const FIELD_LABELS: Record<string, string> = {
  revenue: "营业收入",
  cost: "营业成本",
  surcharges: "税金及附加",
  selling: "销售费用",
  admin: "管理费用",
  research: "研发费用",
  pre_tax_profit: "税前利润",
  revenue_growth: "收入增长率",
  growth: "收入增长率",
  margin: "税前利润率",
  pretax_margin: "税前利润率",
};
function driverNumber(value: unknown, digits = 4) {
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string" &&
          /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim())
        ? Number(value)
        : NaN;
  return Number.isFinite(number)
    ? number.toLocaleString("en-US", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      })
    : "未提供，不补零";
}
function driverRange(value?: OperatingDriverRange, digits = 4) {
  return value
    ? driverNumber(value.lower, digits) +
        " ～ " +
        driverNumber(value.upper, digits)
    : "未提供，不补区间";
}
const DRIVER_SCENARIOS: OperatingDriverScenario[] = ["bear", "base", "bull"];
const EXTREMA = [
  ["growth_lower", "收入增长下界角点"],
  ["growth_upper", "收入增长上界角点"],
  ["margin_lower", "税前利润率下界角点"],
  ["margin_upper", "税前利润率上界角点"],
] as const;
export function OperatingDriverBridgeView({
  bridge,
}: {
  bridge: OperatingDriverBridge;
}) {
  if (
    !bridge.version ||
    !bridge.basis?.baselines ||
    !Array.isArray(bridge.basis.comparisons) ||
    !Array.isArray(bridge.thresholds) ||
    DRIVER_SCENARIOS.some((name) => {
      const input = bridge.inputs?.[name],
        path = bridge.paths?.[name];
      return (
        !input?.drivers ||
        !bridge.basis.baselines[input.baseline_period] ||
        !path?.growth_range ||
        !path.margin_range ||
        !path.extrema ||
        !Array.isArray(path.limitations)
      );
    })
  )
    return (
      <Alert
        type="warning"
        message="经营驱动桥字段不完整，停止展示计算摘要，不推定已有完整driver链"
      />
    );
  return (
    <section aria-label="经营驱动与成本传导桥">
      <h3>经营驱动与成本传导桥（条件研究）</h3>
      <p>
        本区只展示后端同口径计算，不在页面重算。活动量指数不是酒吨数；实现价包含产品组合mix，不是纯涨价；固定份额仅为敏感性假设，不是已证实的会计固定成本拆分；成本水平变化作用于固定与活动量敏感份额组成的全部营业成本。
      </p>
      <p>
        128角点压力包络不是概率分布；其他税前残差不等于经常性盈利。结果不是正式净利、股东现金或估值，也不代表经济批准。
      </p>
      <p>
        金额单位为人民币元，比率为小数而非百分数；摘要仅作展示四舍五入，完整原值见折叠明细。
      </p>
      <h4>同期间历史比较</h4>
      <div style={{ overflowX: "auto" }}>
        <table>
          <caption>
            仅按后端明确列出的期间与比较状态展示；不将全年与半年拼成同比
          </caption>
          <thead>
            <tr>
              <th>指标</th>
              <th>本期</th>
              <th>对比期</th>
              <th>期间口径</th>
              <th>本期值</th>
              <th>对比值</th>
              <th>变化比率</th>
              <th>比较状态</th>
            </tr>
          </thead>
          <tbody>
            {bridge.basis.comparisons.map((row, i) => (
              <tr key={i}>
                <td>{FIELD_LABELS[row.field] || row.field}</td>
                <td>{row.current_period}</td>
                <td>{row.prior_period}</td>
                <td>{row.period_basis}</td>
                <td>{driverNumber(row.current_value, 2)}</td>
                <td>{driverNumber(row.prior_value, 2)}</td>
                <td>{driverNumber(row.change_ratio)}</td>
                <td>{LABELS[row.status] || row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {bridge.basis.comparisons.length === 0 && (
        <p>尚无可显示的同期间比较，不自行生成同比。</p>
      )}
      <details>
        <summary>历史基线、证据编号与缺口</summary>
        <Readable value={bridge.basis} />
      </details>
      {DRIVER_SCENARIOS.map((name) => {
        const input = bridge.inputs[name],
          path = bridge.paths[name];
        const baseline = bridge.basis.baselines[input.baseline_period];
        return (
          <section key={name} aria-label={LABELS[name] + "经营驱动"}>
            <h4>{LABELS[name]}：输入假设与计算摘要</h4>
            <p>
              历史基线：{input.baseline_period}（{baseline.period_basis}，
              {baseline.scope}，{baseline.currency}）； 条件期间：
              {input.period_start} ～ {input.period_end}； 结果期间：
              {path.period_start} ～ {path.period_end}（{path.period_basis}，
              {path.scope}）。
            </p>
            <div>
              结果比较口径：
              <Readable value={path.comparison_basis} />
            </div>
            <p>
              后端收入增长区间：{driverRange(path.growth_range)}；
              税前利润率区间：{driverRange(path.margin_range)}（比率）。
            </p>
            <div style={{ overflowX: "auto" }}>
              <table>
                <caption>
                  输入bounds与理由：条件假设，不是已验证经营事实
                </caption>
                <thead>
                  <tr>
                    <th>驱动</th>
                    <th>下界 ～ 上界</th>
                    <th>理由</th>
                    <th>证据编号</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(DRIVER_LABELS) as OperatingDriverKey[]).map(
                    (key) => {
                      const value = input.drivers[key];
                      return (
                        <tr key={key}>
                          <th>{DRIVER_LABELS[key]}</th>
                          <td>
                            {driverRange(
                              value,
                              key === "other_pretax_cny" ? 2 : 4,
                            )}
                          </td>
                          <td>{value?.rationale || "尚未提供理由"}</td>
                          <td>
                            {value?.evidence_ids?.join("、") ||
                              "尚无证据编号，不推定有据"}
                          </td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
            </div>
            <p>
              成本传导：以下为后端包络角点的收入、营业成本、期间费用、税金及附加、其他税前残差与税前利润；各指标极值可能来自不同角点，不拼成一个实际情景。
            </p>
            <div style={{ overflowX: "auto" }}>
              <table>
                <caption>
                  计算结果（元；各自极值角点，不代表概率或净利预测）
                </caption>
                <thead>
                  <tr>
                    <th>极值角点</th>
                    <th>收入</th>
                    <th>营业成本</th>
                    <th>期间费用</th>
                    <th>税金及附加</th>
                    <th>其他税前残差</th>
                    <th>税前利润</th>
                  </tr>
                </thead>
                <tbody>
                  {EXTREMA.map(([key, title]) => {
                    const row = path.extrema[key];
                    return (
                      <tr key={key}>
                        <th>{title}</th>
                        {(
                          [
                            "revenue_cny",
                            "cogs_cny",
                            "opex_cny",
                            "surcharges_cny",
                            "other_pretax_cny",
                            "pretax_profit_cny",
                          ] as const
                        ).map((field) => (
                          <td key={field}>{driverNumber(row?.[field], 2)}</td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <ul>
              {path.limitations.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
            <details>
              <summary>
                {LABELS[name]}：角点驱动、资本假设与完整路径原值
              </summary>
              <Readable value={{ inputs: input, path }} />
            </details>
          </section>
        );
      })}
      <h4>同一bounds生成的重审阈值（不是自动批准或触发交易）</h4>
      <p>
        仅在同一期间、范围和比较基准下严格越界才满足重审条件；等于阈值不触发，跨历史基线不等于越界。阈值摘要四舍五入，仅原始精确值可用于判断。本页不读取当前经营值或报价，也不判断已触发。
      </p>
      {bridge.thresholds.map((row, i) => (
        <section key={i}>
          <p>
            {LABELS[row.scenario]} · {FIELD_LABELS[row.metric] || row.metric}：
            {row.direction === "below" ||
            row.direction === "lt" ||
            row.direction === "LOWER" ||
            row.direction === "BELOW"
              ? "严格低于"
              : row.direction === "above" ||
                  row.direction === "gt" ||
                  row.direction === "UPPER" ||
                  row.direction === "ABOVE"
                ? "严格高于"
                : row.direction}{" "}
            {driverNumber(row.threshold)}（比率）；期间 {row.period_start} ～{" "}
            {row.period_end}； 历史基线 {row.baseline_period} ·{" "}
            {row.period_basis} · {row.scope}。
          </p>
          <div>
            阈值比较口径：
            <Readable value={row.comparison_basis} />
          </div>
          <p>{LABELS[row.meaning] || row.meaning}</p>
        </section>
      ))}
      {bridge.thresholds.length === 0 && (
        <p>尚无后端重审阈值，不由页面补造。</p>
      )}
      <details>
        <summary>经营驱动桥完整原稿与版本</summary>
        <Readable value={bridge} />
      </details>
    </section>
  );
}
const CAPITAL_KIND_LABELS: Record<string, string> = {
  interim: "半年度报告",
  annual: "年度报告",
  q1: "第一季度报告",
  q3: "第三季度报告",
  dividend_implementation: "分红派息实施公告",
  share_unlock_notice: "解除限售股份上市流通公告",
};
const CAPITAL_STATE_LABELS: Record<string, string> = {
  SCHEME_ADJUSTMENT_RECALL_NOT_ADDITIONAL_CANCELLATION:
    "方案回溯说明，不是新增注销",
  HISTORICAL_RECALL_NOT_NEW_SHARE_REDUCTION:
    "历史注销回溯，不是本次新增股数减少",
  SCHEDULED_CLASS_TRANSFER_SUBJECT_TO_CSDC_STRUCTURE:
    "拟解除限售的股份类别转移，须以中国结算股本结构表为准",
};
function observationText(value: unknown) {
  return typeof value === "string" && value.trim() && value !== "UNKNOWN"
    ? value
    : "未知，不能推定";
}
function observationMoney(value: unknown) {
  const n =
    typeof value === "string" &&
    /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim())
      ? Number(value)
      : NaN;
  return Number.isFinite(n) ? driverNumber(n / 100000000, 4) : "未知，不补零";
}
function observationHash(value: unknown) {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
function observationLink(value: string) {
  return /^https:\/\/static\.cninfo\.com\.cn\/finalpage\/\d{4}-\d{2}-\d{2}\/\d+\.PDF$/.test(
    value,
  )
    ? value
    : undefined;
}
export function CurrentCapitalObservationView({
  value,
  symbol,
}: {
  value: CurrentCapitalObservation;
  symbol: string;
}) {
  if (
    value.action !== "no_order" ||
    value.formal_eligibility !== false ||
    (value.symbol !== undefined && value.symbol !== symbol) ||
    (value.current_capital_continuity !== undefined &&
      value.current_capital_continuity !== "NOT_PROVEN")
  )
    return (
      <Alert
        type="warning"
        message="公开资本观察身份或边界不符，本区停止展示；其他研究保留"
      />
    );
  const rows = Array.isArray(value.source_bound_observations)
    ? value.source_bound_observations
    : [];
  const results = Array.isArray(value.source_results)
    ? value.source_results
    : [];
  return (
    <section aria-label="来源绑定的公开资本观察">
      <h3>公开资本与分配观察（登记原件范围）</h3>
      <p>
        报告期股数与股利方案是原件观察，不证明当前股本连续性；股利计划、财政年度归属、宣告和实际付款必须分开。当前资本连续性：尚未证明。
      </p>
      {value.status === "NOT_STARTED" && (
        <p>尚无已登记资本原件观察，不推定没有分配或股本变化。</p>
      )}
      {value.status === "UNASSESSABLE" && (
        <Alert
          type="info"
          message="资本原件暂不可核验，不能据此显示观察值；其他D2/现金结果保留"
          description={value.reason || value.error_code}
        />
      )}
      {value.status === "PARTIAL" && (
        <Alert
          type="warning"
          message="资本观察仅部分原件通过，未通过来源不参与展示"
        />
      )}
      {value.status !== "UNASSESSABLE" &&
        value.status !== "NOT_STARTED" &&
        rows.map((row, i) => {
          const source = row.source,
            native = row.observation;
          if (
            row.status !== "VERIFIED" ||
            !source ||
            !observationHash(source.sha256) ||
            typeof source.source_url !== "string" ||
            !native ||
            native.status !== "VERIFIED" ||
            native.symbol !== symbol ||
            native.report_period !== source.report_period
          )
            return (
              <Alert
                key={i}
                type="warning"
                message="该条原件身份或Hash绑定不符，观察值不展示"
              />
            );
          const url = observationLink(source.source_url);
          return (
            <section key={i}>
              <h4>
                {source.report_period} · {native.issuer_name || symbol} ·{" "}
                {CAPITAL_KIND_LABELS[native.kind || native.report_kind || ""] ||
                  native.kind ||
                  native.report_kind ||
                  source.kind}
              </h4>
              <p>
                原件报告期：{source.report_period}；原件链接日期：
                {source.source_url.match(
                  /finalpage\/(\d{4}-\d{2}-\d{2})\//,
                )?.[1] || "未知"}
                ； 登记可用时间：{source.available_at}；董事会批准报出日：
                {observationText(native.report_approved_date)}。
                这些日期不是股本变化生效日或付款日。
              </p>
              {url && (
                <p>
                  <a href={url} target="_blank" rel="noreferrer">
                    查看官方原件
                  </a>
                </p>
              )}
              <table>
                <caption>
                  报告期末股数（股；不使用人民币股本金额换算股数）
                </caption>
                <thead>
                  <tr>
                    <th>变动前股数</th>
                    <th>期末普通股数</th>
                    <th>注销股数</th>
                    <th>注销日期与状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{driverNumber(native.shares_before, 0)}</td>
                    <td>{driverNumber(native.ordinary_shares, 0)}</td>
                    <td>{driverNumber(native.cancelled_shares, 0)}</td>
                    <td>
                      {observationText(native.cancellation_date)} ·{" "}
                      {native.cancellation_state ===
                      "REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED_BY_PERIOD_END"
                        ? "原件称报告期末前已完成限制性股票注销"
                        : CAPITAL_STATE_LABELS[
                            native.cancellation_state || ""
                          ] || observationText(native.cancellation_state)}
                    </td>
                  </tr>
                </tbody>
              </table>
              {native.observation_date && (
                <p>公告署期：{native.observation_date}；不等于实际付款日。</p>
              )}
              {(native.record_date ||
                native.ex_date ||
                native.agency_payment_date) && (
                <section>
                  <h5>分红实施安排（不是到账证明）</h5>
                  <p>
                    股权登记日：{observationText(native.record_date)}
                    ；除权除息日：{observationText(native.ex_date)}；
                    公告计划委托代派日：
                    {observationText(native.agency_payment_date)}。
                  </p>
                  <p>
                    派息基数：{driverNumber(native.distribution_base_shares, 0)}
                    股； 排除的回购股份：
                    {driverNumber(native.excluded_repurchase_shares, 0)}股；
                    每10股派息：
                    {driverNumber(native.dividend_per_10_shares_cny, 2)}元。
                    委托代派与公司自行派发安排不等于账户到账；该付款安排归属原财政年度，不能算入另一年度政策目标。
                  </p>
                </section>
              )}
              {native.share_effective_date && (
                <p>
                  限售股拟上市流通日：{native.share_effective_date}；
                  {CAPITAL_STATE_LABELS[native.share_observation_state || ""] ||
                    observationText(native.share_observation_state)}
                  。 历史注销回溯：
                  {driverNumber(native.historical_cancelled_shares, 0)}股（
                  {observationText(native.historical_cancellation_date)}
                  ），不是新增注销；不证明当前股本连续性。
                </p>
              )}
              {native.share_table_qualification && (
                <p>{native.share_table_qualification}</p>
              )}
              {native.equity_distribution_implementation && (
                <section>
                  <h5>原件实施观察（非付款完成结论）</h5>
                  <Readable value={native.equity_distribution_implementation} />
                </section>
              )}
              {native.financial_update?.status === "VERIFIED" && (
                <section>
                  <h5>后续财报实际观察（不回写冻结模型输入）</h5>
                  <p>
                    {native.financial_update.period_start} ～{" "}
                    {native.financial_update.period_end}；
                    {native.financial_update.period_basis ===
                    "YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER"
                      ? "年初累计九个月，不是第三季度单季，也不是全年"
                      : native.financial_update.period_basis}
                    。
                  </p>
                  <p>
                    营业收入：
                    {observationMoney(
                      native.financial_update.fields?.revenue_cny?.value,
                    )}
                    亿元； 归母利润：
                    {observationMoney(
                      native.financial_update.fields?.parent_profit_cny?.value,
                    )}
                    亿元。
                    后续财报需触发当前模型重验，不自动覆盖原研究或授予当前价格资格。
                  </p>
                </section>
              )}
              <p>
                股利方案归属财政年度：
                {observationText(native.dividend_fiscal_year)}；
                已披露方案总额（含税，亿元）：
                {observationMoney(native.declared_ordinary_dividend_cny)}。
                这是方案金额，不是已付款金额。
              </p>
              <p>
                中期分配计划：
                {native.interim_proposal_state ===
                "REPORTED_NO_INTERIM_DIVIDEND_OR_CAPITALIZATION_PLANNED"
                  ? "报告称拟不进行中期现金分红、送股或转增；不等于全年政策取消"
                  : observationText(native.interim_proposal_state)}
                。
              </p>
              <p>
                实际付款完成：{observationText(native.payment_completion_state)}
                ；不能把方案或历史付款当作当年已支付。
              </p>
              {native.dividend_policy?.status === "VERIFIED" &&
                Array.isArray(native.dividend_policy.policies) && (
                  <ul>
                    {native.dividend_policy.policies.map((policy, j) => (
                      <li key={j}>
                        {policy.fiscal_year}财政年度：最低派息比率{" "}
                        {driverNumber(policy.minimum_payout_ratio)}
                        （小数比率），最低政策总额{" "}
                        {observationMoney(policy.minimum_distribution_cny)}
                        亿元；条件性政策意向，不是已宣告负债或付款完成证明。
                      </li>
                    ))}
                  </ul>
                )}
              <details>
                <summary>该原件Hash与逐字段原文证据</summary>
                <p>
                  SHA-256：<code>{source.sha256}</code>
                </p>
                <ul>
                  {(Array.isArray(native.evidence_refs)
                    ? native.evidence_refs
                    : []
                  ).map((ref, j) => (
                    <li key={j}>
                      <code>{ref.field}</code> · 物理页 {ref.physical_page}
                      <blockquote>{ref.excerpt}</blockquote>
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          );
        })}
      {results.some((row) => row.status !== "VERIFIED") && (
        <ul>
          {results
            .filter((row) => row.status !== "VERIFIED")
            .map((row, i) => (
              <li key={i}>
                原件 {row.source_index} 未通过：{row.error_code || row.status}
                ；报告期 {row.source?.report_period || "未知"}。
              </li>
            ))}
        </ul>
      )}
      {value.current_financial_coverage && (
        <p>
          仅已登记财报覆盖：
          {(Array.isArray(value.current_financial_coverage.report_periods)
            ? value.current_financial_coverage.report_periods
            : []
          ).join("、") || "未知"}
          ； 最新登记报告期：
          {value.current_financial_coverage.latest_report_period || "未知"}
          。不代表当前财务/事件完整覆盖，不授予当前价格资格。
        </p>
      )}
    </section>
  );
}
const FISCAL_MONEY_FIELDS: [keyof FiscalDistributionScenario, string][] = [
  ["reported_h1_parent_profit_cny", "H1实际归母利润"],
  ["assumed_h2_parent_profit_cny", "H2条件归母利润（派生）"],
  ["conditional_fy_parent_profit_cny", "同一财政年度条件归母利润"],
  ["ratio_target_cny", "比例政策目标"],
  ["disclosed_floor_cny", "披露的年度绝对政策下限"],
  ["policy_target_cny", "当年政策目标"],
  [
    "target_above_current_year_positive_earnings_cny",
    "政策目标超过当年正利润金额（非资金缺口）",
  ],
];
export function FiscalDistributionReviewView({
  value,
  symbol,
}: {
  value: FiscalDistributionReview;
  symbol: string;
}) {
  if (
    value.action !== "no_order" ||
    value.formal_eligibility !== false ||
    (value.symbol !== undefined && value.symbol !== symbol) ||
    (value.main_range_adopted !== undefined &&
      value.main_range_adopted !== false) ||
    value.condition_price != null ||
    value.personal_quantity != null
  )
    return (
      <Alert
        type="warning"
        message="财政年度诊断身份或边界不符，本区停止展示；其他研究保留"
      />
    );
  const update = value.financial_update_review;
  const sources = Array.isArray(value.source_binding)
    ? value.source_binding
    : [];
  const names = DRIVER_SCENARIOS.filter((name) => value.scenarios?.[name]);
  const valid =
    value.status === "SOURCE_BOUND_FISCAL_POLICY_REVIEW" &&
    names.length > 0 &&
    sources.length > 0 &&
    sources.every((row) => observationHash(row.sha256)) &&
    names.every((name) => {
      const row = value.scenarios![name]!;
      return (
        Number.isInteger(row.fiscal_year) &&
        value.financial_basis === String(row.fiscal_year) + "-06-30" &&
        row.funding_status === "NOT_ASSESSED" &&
        row.payment_status === "NOT_ASSESSED" &&
        row.policy_compliance === "NOT_ASSESSED"
      );
    });
  const q3Names = DRIVER_SCENARIOS.filter(
    (name) => update?.comparisons?.[name],
  );
  const q3Source = update?.comparison_source;
  const q3Verified =
    !!q3Source &&
    observationHash(q3Source.sha256) &&
    q3Names.every((name) => {
      const row = update!.comparisons![name]!;
      return (
        row.status === "ACTUAL_UPDATE_COMPARED_WITH_FROZEN_CONDITIONAL_PATH" &&
        row.model_revalidated === false &&
        row.action === "no_order" &&
        row.formal_eligibility === false &&
        row.condition_price === null &&
        row.fiscal_year === value.scenarios?.[name]?.fiscal_year &&
        row.source_anchor?.unit === "CNY" &&
        row.source_anchor.scope === "consolidated_parent" &&
        row.implied_q4_start === row.fiscal_year + "-10-01" &&
        row.implied_q4_end === row.fiscal_year + "-12-31" &&
        q3Source.report_period === row.fiscal_year + "-09-30"
      );
    });
  const q3Rows = q3Names.map((name) => {
    const row = update!.comparisons![name]!;
    return [
      LABELS[name],
      observationMoney(row.reported_ytd_parent_profit_cny),
      observationMoney(row.unchanged_conditional_fy_parent_profit_cny),
      observationMoney(row.implied_q4_parent_profit_cny),
      row.implied_q4_start + " ～ " + row.implied_q4_end,
      row.implication === "IMPLIED_Q4_LOSS_REQUIRES_EXPLICIT_REVIEW"
        ? "隐含Q4亏损要求，须显式复核"
        : "隐含Q4非负利润要求，仍须复核",
    ];
  });
  return (
    <section aria-label="财政年度分配政策诊断">
      <h3>财政年度政策目标与利润诊断（非资金能力评估）</h3>
      {update && (
        <Alert
          type="warning"
          message={
            update.status === "NEWER_REPORT_REQUIRES_MODEL_REVALIDATION"
              ? "已登记更新财报，模型当前使用需重验"
              : "仅登记来源覆盖，当前模型资格未授予"
          }
          description={
            "模型财务基准：" +
            update.model_financial_basis +
            "；最新登记报告期：" +
            (update.latest_registered_report_period || "未知") +
            "。新财报不回写冻结研究输入；不能据旧模型直接输出当前买价。"
          }
        />
      )}
      {valid && q3Names.length > 0 && (
        <section aria-label="Q3实际与原全年条件情景比较">
          <h4>Q3累计实际对原条件全年值的隐含要求</h4>
          <p>
            原全年条件值保持不变；隐含Q4是维持该情景所需的剩余归母利润，不是已发生亏损或新预测，不自动拒绝或改值。模型尚未重验，无投资批准。
          </p>
          {!q3Verified ? (
            <Alert
              type="info"
              message="Q3比较来源或期间未核验，仅本表不展示，原财政诊断保留"
            />
          ) : (
            <>
              <p>
                金额单位亿元；Q3为年初累计九个月，负数仅是原情景的隐含要求。
              </p>
              <Table
                size="small"
                pagination={false}
                scroll={{ x: true }}
                rowKey={(row) => row[0]}
                columns={[
                  "情景",
                  "累计实际归母",
                  "原条件全年归母（未改）",
                  "隐含Q4归母要求",
                  "Q4期间",
                  "需复核事项",
                ].map((title, index) => ({
                  title,
                  dataIndex: index,
                  key: title,
                }))}
                dataSource={q3Rows}
              />
              <p>
                Q3原件报告期：{q3Source!.report_period}；登记可用：
                {q3Source!.available_at}；
                {observationLink(q3Source!.source_url) && (
                  <a
                    href={q3Source!.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    查看Q3官方原件
                  </a>
                )}
              </p>
            </>
          )}
        </section>
      )}
      {valid && update?.comparison_status && q3Names.length === 0 && (
        <p>暂无唯一可核验的同年Q3实际对比；不推定Q4结果或模型已重验。</p>
      )}
      {!valid ? (
        <Alert
          type="info"
          message="财政年度政策诊断暂不可核验，其他D2/现金结果保留"
          description={value.reason || value.error_code || value.status}
        />
      ) : (
        <>
          <p>
            同一财政年度H1实际归母利润 +
            H2条件归母利润。H2来自滚动首年减同一2027H1
            witness，不是另设一份利润预测；不把2026H2+2027H1滚动年度套用财政年度政策下限。
          </p>
          <p>
            金额单位亿元，仅单位换算与展示四舍五入；原始元值在折叠明细。政策目标高于当年正利润的金额不是资金缺口，不证明违约，也不证明已支付；历史留存和可达现金须另行验证。
          </p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <caption>
                财政年度归属：H1实际与H2条件派生；未评估资金、付款或政策履约
              </caption>
              <thead>
                <tr>
                  <th>情景</th>
                  <th>财政年度</th>
                  {FISCAL_MONEY_FIELDS.map(([key, title]) => (
                    <th key={key}>{title}</th>
                  ))}
                  <th>主导政策约束</th>
                </tr>
              </thead>
              <tbody>
                {names.map((name) => {
                  const row = value.scenarios![name]!;
                  return (
                    <tr key={name}>
                      <th>{LABELS[name]}</th>
                      <td>{row.fiscal_year}</td>
                      {FISCAL_MONEY_FIELDS.map(([key]) => (
                        <td key={key}>{observationMoney(row[key])}</td>
                      ))}
                      <td>
                        {row.dominant_constraint === "ABSOLUTE_FLOOR"
                          ? "绝对政策下限"
                          : "派息比例"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p>
            资金能力：未评估；实际付款：未评估；政策履约：未评估；财政年度付款归属对齐：
            {value.fiscal_payment_alignment === "NOT_ASSESSED"
              ? "未评估"
              : "尚未提供，不推定完成"}
            。无投资批准，主研究区间未采用，不生成条件价。
          </p>
          <ul>
            {sources.map((source, i) => (
              <li key={i}>
                政策来源报告期：{source.report_period}；登记可用：
                {source.available_at}；
                {observationLink(source.source_url) && (
                  <a href={source.source_url} target="_blank" rel="noreferrer">
                    官方政策原件
                  </a>
                )}
              </li>
            ))}
          </ul>
          <details>
            <summary>政策绑定与财政年度精确元值</summary>
            {q3Verified && q3Names.length > 0 && (
              <>
                <p>
                  Q3来源SHA-256：<code>{q3Source!.sha256}</code>
                </p>
                {q3Names.map((name) => (
                  <p key={name}>
                    {LABELS[name]} · 物理页{" "}
                    {update!.comparisons![name]!.source_anchor.physical_page}：
                    {update!.comparisons![name]!.source_anchor.excerpt}
                  </p>
                ))}
              </>
            )}
            <p>
              复核指纹：<code>{value.review_fingerprint || "未提供"}</code>
            </p>
            {sources.map((source, i) => (
              <p key={i}>
                来源SHA-256：<code>{source.sha256}</code>
              </p>
            ))}
            {names.map((name) => (
              <section key={name}>
                <h4>{LABELS[name]}（元；原始值）</h4>
                <dl>
                  {FISCAL_MONEY_FIELDS.map(([key, title]) => (
                    <div key={key}>
                      <dt>{title}</dt>
                      <dd>{value.scenarios![name]![key]}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
            <ul>
              {value.limitations?.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
export function validLiveTask(
  value: unknown,
  symbol: string,
): value is LiveOperatingResearchTask {
  if (!value || typeof value !== "object") return false;
  const row = value as LiveOperatingResearchTask;
  return (
    row.symbol === symbol &&
    typeof row.task_id === "string" &&
    !!row.task_id &&
    typeof row.status === "string" &&
    row.currency === "CNY" &&
    (row.scope === "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" ||
      row.scope === "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH") &&
    row.main_range_adopted === false &&
    row.approval_changed === false &&
    row.formal_fact_count === 0 &&
    row.condition_price === null &&
    row.personal_quantity === null &&
    Number.isInteger(row.new_llm_calls) &&
    row.new_llm_calls >= 0
  );
}
export function OperatingCashConsumptionView({
  value,
}: {
  value: Record<string, unknown>;
}) {
  if (value.status === "UNASSESSABLE")
    return (
      <Alert
        type="warning"
        message="股东现金消费来源尚未核验"
        description={String(
          value.reason || "来源或映射失败；原经营研究仍可阅读",
        )}
      />
    );
  const annual =
    value.annual_followup && typeof value.annual_followup === "object"
      ? (value.annual_followup as Record<string, unknown>)
      : null;
  const history = Array.isArray(value.historical_parent_cash)
    ? (value.historical_parent_cash as Record<string, unknown>[])
    : [];
  const paths =
    value.scenarios && typeof value.scenarios === "object"
      ? (value.scenarios as Record<string, Record<string, unknown>>)
      : {};
  const blockers = Array.isArray(value.current_blockers)
    ? (value.current_blockers as Record<string, unknown>[])
    : [];
  const supplement = value.annual_research_supplement as
    | {
        status: string;
        reason?: string;
        task_id?: string;
        research_as_of?: string;
        transport_status?: string;
        scope_decomposition_status?: string;
        years?: Record<
          string,
          {
            estimate_kind: string;
            counter_evidence: string;
            reopen_condition: string;
            unit_cost_mechanisms?: Record<string, string>;
            quantification_status?: string;
            earnings: Record<
              string,
              { witnesses: Record<string, { parent_profit_cny: string }> }
            >;
          }
        >;
      }
    | undefined;
  const compilation = value.earnings_input_compilation as
    | {
        status?: string;
        reason?: string;
        scenarios?: Record<
          string,
          {
            period_start: string;
            period_end: string;
            model_year: number;
            candidates: Record<string, unknown>;
            missing_calendar_years: number[];
          }
        >;
      }
    | undefined;
  return (
    <section aria-label="经营利润到股东现金的实际消费">
      <h3>经营利润 → 股东现金 → 估值 → 条件价格</h3>
      <Alert
        type="info"
        message={
          annual?.status === "CONDITIONAL_STRESS_CONSUMED"
            ? "条件压力经营 → 股东现金 → 共享估值已接通；尚非主估值或买价"
            : "税后归属已实际计算；未来现金、年度估值与条件价格尚未形成完整链路"
        }
        description="这里消费同一D2角点，保留实际年度或半年期间。归母利润不等于可分配现金，历史母公司现金代理不等于未来自由现金；不将旧年度估值冒充本次D2结果。"
      />
      <p>
        研究任务：{String(value.task_id || "未提供")}；消费版本：
        {String(value.consumption_fingerprint || "未核验")}；action=no_order。
      </p>
      {supplement && supplement.status !== "NOT_STARTED" && (
        <section aria-label="逐年经营研究补充">
          <h4>逐年经营研究补充</h4>
          <p>
            任务：{supplement.task_id || "未形成"}；状态：
            {(
              {
                QUEUED: "等待执行",
                RUNNING: "研究中",
                FAILED: "研究未通过校验",
                CANCELLED: "已取消",
                UNASSESSABLE: "当前不能核验",
                ANNUAL_SUPPLEMENT_COMPILED_NOT_CASH_POLICY:
                  "年度利润已编译，现金路径尚未完成",
                ANNUAL_SUPPLEMENT_TRANSPORT_NORMALIZED_ECONOMIC_REVIEW_REQUIRED:
                  "传输格式已严格归一化；经济复核尚未通过",
              } as Record<string, string>
            )[supplement.status] || supplement.status}
            ；研究时点：
            {supplement.research_as_of || "未形成"}。
          </p>
          <p>
            独立年度假设，尚未通过独立经济复核；不覆盖原研究、不自动连接成主预测。
          </p>
          {Object.entries(supplement.years || {}).map(([year, row]) => (
            <section key={year}>
              <h5>
                {year}：
                {row.estimate_kind === "CURRENT_FY_ESTIMATE"
                  ? "当年全年估计（包含已过月份，非实际财报）"
                  : "未来全年条件假设"}
              </h5>
              {row.quantification_status && (
                <p>参数区间属于条件敏感性假设，尚未证明是可信预测边界。</p>
              )}
              <p>反证：{row.counter_evidence}</p>
              <p>重开研究条件：{row.reopen_condition}</p>
              {Object.entries(row.earnings).map(([scenario, path]) => (
                <p key={scenario}>
                  {LABELS[scenario] || scenario}：
                  {row.unit_cost_mechanisms &&
                    `独立成本依据：${({ INPUT_PRICE: "投入品价格", INDEPENDENT_EFFICIENCY: "独立运营效率", UNRESOLVED_SENSITIVITY: "尚未论证的敏感性假设" } as Record<string, string>)[row.unit_cost_mechanisms[scenario]] || "未核验"}；`}
                  {Object.entries(path.witnesses)
                    .map(
                      ([point, value]) =>
                        `${EXTREMA.find(([key]) => key === point)?.[1] || point}归母利润 ${driverNumber(value.parent_profit_cny, 2)} 元`,
                    )
                    .join("；")}
                  。 完整角点分别保留，不等同可分配现金或主估值。
                </p>
              ))}
            </section>
          ))}
          {supplement.reason && (
            <Alert
              type="warning"
              message="年度补充尚不可消费"
              description={
                supplement.reason ===
                "HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED"
                  ? "模型响应格式、引用或来源未通过严格校验；本次结果未进入估值。原始响应已保留供定位，不代表公司不值得研究。"
                  : supplement.reason
              }
            />
          )}
          {supplement.transport_status && (
            <Alert
              type="warning"
              message="供应商传输格式已归一化"
              description="只接受完整JSON对象后恰好一个多余右花括号；原始响应、修复响应和哈希均保留。此处理不认可任何经营假设，也不改变未批准状态。"
            />
          )}
        </section>
      )}
      {compilation?.scenarios && (
        <section aria-label="年度模型输入编译">
          <h4>D2 到年度模型输入</h4>
          <p>
            每个完整情景保留自己的税前利润、税费和少数股东损益，经共享年度编译器核账；不拼接不同角点，不补齐未知年份。
          </p>
          {Object.entries(compilation.scenarios).map(([name, row]) => (
            <p key={name}>
              {LABELS[name] || name}：{row.period_start} ～ {row.period_end}，第
              {row.model_year}模型年；
              {Object.keys(row.candidates).length > 0
                ? "完整年度输入已编译，尚未选择主预测"
                : "不是完整年度，尚不能编译成年输入"}
              。 尚缺年份：{row.missing_calendar_years.join("、")}
              。现金政策和终值仍须独立验证。
            </p>
          ))}
        </section>
      )}
      {compilation?.status === "UNASSESSABLE" && (
        <Alert
          type="warning"
          message="年度输入编译未通过"
          description={
            compilation.reason || "年度编译未返回可核验结果；原经营研究仍可阅读"
          }
        />
      )}
      {compilation?.status === "DELEGATED_TO_EXISTING_PERIOD_ADAPTER" && (
        <p>{compilation.reason}</p>
      )}
      {history.length > 0 && (
        <table>
          <caption>母公司历史现金勾稽（元；不同期间分别列示，非FCFE）</caption>
          <thead>
            <tr>
              <th>期间</th>
              <th>经营现金流</th>
              <th>投资收益收现</th>
              <th>购建资产现金</th>
              <th>前三项合计：经营＋投资收现－购建</th>
            </tr>
          </thead>
          <tbody>
            {history.map((row) => (
              <tr key={String(row.period)}>
                <td>
                  {String(row.period)} · {String(row.period_basis)}
                </td>
                <td>{driverNumber(row.parent_cfo, 2)}</td>
                <td>{driverNumber(row.investment_cash, 2)}</td>
                <td>{driverNumber(row.gross_cash_capex, 2)}</td>
                <td>{driverNumber(row.cash_proxy_cny, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        历史经营现金流已包含营运资本变动，不再扣一次WC；投资收益收现不能直接视为经常性分红，集团现金不与母公司现金相加。
      </p>
      {Object.entries(paths).map(([name, path]) => {
        const points =
          path.witnesses && typeof path.witnesses === "object"
            ? (path.witnesses as Record<string, Record<string, unknown>>)
            : {};
        return (
          <section key={name}>
            <h4>{LABELS[name] || name}：税后及归母勾稽（非现金预测）</h4>
            <p>
              {String(path.period_start)} ～ {String(path.period_end)}；
              {String(path.period_basis)}
              。沿用历史有效税率和带符号少数损益关系只是显式条件假设，不是已知未来事实。
            </p>
            <table>
              <thead>
                <tr>
                  <th>原经营角点</th>
                  <th>税前利润（元）</th>
                  <th>所得税（元）</th>
                  <th>少数损益（元）</th>
                  <th>归母利润（元）</th>
                  <th>可分配现金</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(points).map(([key, point]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{driverNumber(point.group_pbt_cny, 2)}</td>
                    <td>{driverNumber(point.income_tax_cny, 2)}</td>
                    <td>{driverNumber(point.signed_nci_cny, 2)}</td>
                    <td>{driverNumber(point.parent_profit_cny, 2)}</td>
                    <td>未形成，不补零</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}
      {annual && <AnnualCashFollowup value={annual} />}
      <h4>当前必需缺口（阻断本条业务链）</h4>
      <ul>
        {blockers.map((row) => (
          <li key={String(row.code)}>
            {CASH_BLOCKERS[String(row.code)] ||
              String(row.explanation || row.code)}
          </li>
        ))}
      </ul>
      <p>
        {annual?.status === "CONDITIONAL_STRESS_CONSUMED"
          ? "已调用原ResearchApplicationService和v4共享模型；新结果绑定本次D2、年度传递假设和现金政策，非旧估值改名。主研究区间未采纳，条件价格与个人股数仍为空。"
          : "尚未完成年度估值消费，不生成条件买价或个人股数；旧年度研究有独立版本，不能冒充本次D2结果。"}
      </p>
      <details>
        <summary>税后归属来源与精确数值</summary>
        <Readable value={value} />
      </details>
    </section>
  );
}

function ParentCashFollowupView({ value }: { value: Record<string, unknown> }) {
  const status =
    typeof value.status === "string" ? value.status : "UNASSESSABLE";
  const blockers = Array.isArray(value.current_blockers)
    ? value.current_blockers
    : [];
  const observation = value.observations as Record<string, unknown> | undefined;
  const sourceCount = Array.isArray(observation?.source_bindings)
    ? observation.source_bindings.length
    : 0;
  return (
    <section aria-label="母公司现金观察准备">
      <h4>母公司现金观察（E2 准备）</h4>
      <p>
        状态：{status} · 已绑定报告：{sourceCount} 份
      </p>
      <Alert
        type={
          status === "SOURCE_BOUND_PARENT_CASH_OBSERVATIONS_READY_FOR_POLICY"
            ? "info"
            : "warning"
        }
        message={
          status === "SOURCE_BOUND_PARENT_CASH_OBSERVATIONS_READY_FOR_POLICY"
            ? "已重放官方母公司现金表；这只是估值输入准备，不是可分配现金或买卖结论"
            : "尚未形成可消费的母公司现金观察"
        }
        description={
          blockers.length > 0
            ? "仍需：" +
              blockers
                .map((row) =>
                  typeof row === "object" && row !== null && "code" in row
                    ? String(row.code)
                    : String(row),
                )
                .join("；")
            : typeof value.reason === "string"
              ? value.reason
              : "未提供可核验的来源绑定"
        }
      />
    </section>
  );
}
function AnnualCashFollowup({ value }: { value: Record<string, unknown> }) {
  if (value.status !== "CONDITIONAL_STRESS_CONSUMED")
    return (
      <Alert
        type="warning"
        message="年度现金/估值消费未通过"
        description={String(value.reason || value.status)}
      />
    );
  const valuation =
    value.valuation && typeof value.valuation === "object"
      ? (value.valuation as Record<string, unknown>)
      : {};
  const ledgers =
    value.annual_ledgers && typeof value.annual_ledgers === "object"
      ? (value.annual_ledgers as Record<string, Record<string, unknown>>)
      : {};
  return (
    <section aria-label="D2实际消费的条件现金与估值">
      <h4>新增滚动年度条件研究：现金约束与估值实际消费</h4>
      <p>
        财务及估值基准：{String(value.financial_basis)}
        ；低置信度，仅未采用的压力路径，不是当前合理价值或买价。首年由下半年条件估计和原D2上半年完整角点组成，不将半年乘二。
      </p>
      <p>{String(value.rationale)}</p>
      <table>
        <caption>
          共享v4模型计算的三条条件路径（元/股，不是已采纳Bear/Base/Bull）
        </caption>
        <thead>
          <tr>
            <th>条件路径</th>
            <th>条件值</th>
            <th>价格资格</th>
          </tr>
        </thead>
        <tbody>
          {["bear", "base", "bull"].map((name) => (
            <tr key={name}>
              <td>{LABELS[name]}</td>
              <td>{driverNumber(valuation[name + "_value"], 2)}</td>
              <td>未采用主区间；未形成买价</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.entries(ledgers).map(([name, ledger]) => {
        const rows = Array.isArray(ledger.rows)
          ? (ledger.rows as Record<string, unknown>[])
          : [];
        return (
          <details key={name}>
            <summary>{LABELS[name]}：逐年股东现金、分配和权益账</summary>
            <p>
              现金约束导致分配低于目标的模型年：
              {Array.isArray(ledger.distribution_constraint_years)
                ? ledger.distribution_constraint_years.length
                  ? ledger.distribution_constraint_years.join("、")
                  : "本条件路径未发生"
                : "未提供"}
              。目标派息不是保证兑现。
            </p>
            <table>
              <thead>
                <tr>
                  <th>模型期间</th>
                  <th>归母利润</th>
                  <th>可达利润</th>
                  <th>维护/WC/承诺合计</th>
                  <th>现金约束后的假设分配</th>
                  <th>期末现金</th>
                  <th>期末权益</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={String(row.year)}>
                    <td>
                      {String(row.period_start)} ～ {String(row.period_end)}
                    </td>
                    <td>{driverNumber(row.profit, 2)}</td>
                    <td>{driverNumber(row.accessible_profit, 2)}</td>
                    <td>{driverNumber(row.mandatory_cash, 2)}</td>
                    <td>{driverNumber(row.distribution, 2)}</td>
                    <td>{driverNumber(row.closing_cash, 2)}</td>
                    <td>{driverNumber(row.closing_book, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        );
      })}
      <p>最强反证与失效依据：{String(value.countercase)}</p>
      <details>
        <summary>既有条件价格政策的实际检查结果（无买价、未批准）</summary>
        <p>
          未采用压力值不具备操作价格基础；没有阈值理由，不创建默认安全边际。空规则预览不是待批准的买入计划。
        </p>
        <Readable value={value.price_policy} />
      </details>
      <p>
        完整利润→现金→权益输入指纹：{String(value.input_descriptor_sha256)}
        。现金政策是另行绑定的原条件研究，不是把Agent的UNKNOWN填零或取得G3。
      </p>
    </section>
  );
}
const CASH_BLOCKERS: Record<string, string> = {
  ANNUAL_TRANSPORT_AND_CASH_POLICY_NOT_ECONOMICALLY_ADOPTED:
    "年度压力传递、利润持续性及资金政策还未获得经济采纳；原D2资本未知项没有因此变成已知事实。",
  COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED:
    "完整年度经营路径缺失：已有期间尚未覆盖全年，不能乘二、默认其余期间或让旧年度模型改写费用。",
  COMPLETE_TEN_YEAR_OPERATING_PATH_REQUIRED:
    "已有完整年度输入，但十年路径仍不连续：缺失年份、主预测选择及现金政策必须显式补齐，不能把一年复制十次。",
  EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED:
    "同期间现金政策缺失：需绑定期初现金、维护/营运资本、上划和分配假设；既有UNKNOWN不能填零。",
  MAIN_ECONOMIC_RANGE_NOT_ADOPTED:
    "尚未选定有经济依据的主研究区间；利润和现金代理不能直接变成买价。",
  CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED:
    "当前股本、期间分配、重大事件和合格报价仍需同版本对齐；历史现金不是今日余额。",
};
export function LiveOperatingResearchDraft({
  task,
}: {
  task:
    | LiveOperatingResearchTask
    | PublicOperatingResearchSuccess
    | PublicOperatingResearchPartial;
}) {
  return (
    <section aria-label="新Agent经营研究结果">
      {task.scope === "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH" && (
        <Alert type="warning" message="仅测试合同结果，不是真实模型研究" />
      )}
      <p>
        任务：{task.task_id} · {LABELS[task.status] || task.status} · 模型：
        {task.model_id}
      </p>
      {"controller_finalization" in task && task.controller_finalization && (
        <Alert
          type="warning"
          message="工作进程已停止，原记录的状态写入尚未完成"
          description="这是落盘待恢复，不是模型仍在运行。点击完成状态写入，不重新研究或释放预留费用。"
        />
      )}
      {"live_controller" in task && task.live_controller && (
        <p>
          后台总时限：{task.live_controller.timeout_seconds}秒； 开始：
          {task.live_controller.started_at}； 截止：
          {task.live_controller.deadline_at}； 监督结果：
          {task.live_controller.result}。
          取消或到期会停止本次自建工作进程；未结算费用不会自动记零。
        </p>
      )}
      {"reserved_cost" in task ? (
        <p>
          新增模型调用：{task.new_llm_calls} · 预留费用（人民币元）：
          {task.reserved_cost} · 估算结算费用（人民币元）：{task.settled_cost}
          （用量与费用按配置费率估算，非服务商账单）
        </p>
      ) : (
        <p>
          已记录模型调用：{task.new_llm_calls}
          ；此处仅读取已生成研究，不发起新调用。
        </p>
      )}
      {task.main_valuation_revalidation && (
        <MainValuationRevalidationPanel
          value={task.main_valuation_revalidation}
          symbol={task.symbol}
        />
      )}
      <p>
        研究截止：{task.research_as_of || "未提供"} ·
        经济主区间未采用；审批未改变，正式事实新增 0。
      </p>
      {task.status === "PARTIAL" && "completed_roles" in task ? (
        <Alert
          type="warning"
          message="仅部分角色研究可读，三角色未全部完成，执行状态为失败"
          description={
            <>
              <p>
                已完成：
                {task.completed_roles.map((role) => LABELS[role]).join("、")}
                ；待完成：
                {task.pending_roles.map((role) => LABELS[role]).join("、")}。
              </p>
              <p>
                {task.reason === "DAILY_BUDGET_EXHAUSTED_BEFORE_CALL"
                  ? "事件研究待预算：调用前预算预留被拒，未完成事件模型研究；本轮已停止于每日预算预留，事件待继续。"
                  : "最新执行未完成，待完成角色不能视为已有研究结果。"}
              </p>
              <p>部分草案不代表经营或估值研究充分，经济主区间仍未采用。</p>
            </>
          }
        />
      ) : (
        <p>任务完成仅表示流程完成，不代表经营或估值研究充分。</p>
      )}
      <p>任务成功不等于研究可信；反证本身也可能存在误述，需逐条核验。</p>
      {task.independent_review_status === "REVIEW_BINDING_INVALID" ? (
        <Alert
          type="warning"
          message="独立经济复核绑定失效，旧复核内容不予展示"
          description="复核与当前来源或角色结果的绑定未通过核验，不能作为当前研究的独立复核依据。"
        />
      ) : task.independent_review ? (
        <Alert
          type="warning"
          message="独立复核待处理，不代表批准；反证也可能有误述"
          description={
            <ul>
              {task.independent_review.findings.map((finding, index) => (
                <li key={index}>
                  {finding.priority} · {LABELS[finding.role] || finding.role} ·
                  原始条目索引 {finding.claim_index}：{finding.reason}
                </li>
              ))}
            </ul>
          }
        />
      ) : task.status === "SUCCEEDED" ? (
        <Alert
          type="info"
          message="尚无独立经济复核"
          description="任务成功不代表已完成独立经济复核，不能推定研究可信或经济有效性通过。"
        />
      ) : null}
      {task.research_completeness ? (
        <section aria-label="研究完整度">
          <p>
            情景数：{task.research_completeness.scenario_count} ·{" "}
            {task.operating_driver_bridge &&
            task.research_completeness.numeric_basis ===
              "GROWTH_AND_PROFIT_ARE_CODE_DERIVED_NOT_MODEL_ENTERED" &&
            Number.isInteger(
              task.research_completeness.structured_driver_range_count,
            ) &&
            Number.isInteger(
              task.research_completeness.derived_scenario_metric_count,
            ) ? (
              <>
                {task.research_completeness.structured_driver_range_count}
                项经营驱动范围，
                {task.research_completeness.derived_scenario_metric_count}
                项增长/税前利润率由代码派生，不是模型直接填值
              </>
            ) : (
              <>
                数值假设数：
                {task.research_completeness.numeric_assumption_count}
              </>
            )}{" "}
            · 未知假设数：{task.research_completeness.unknown_assumption_count}
          </p>
          <Alert
            type="info"
            message={
              task.research_completeness.status ===
              "INSUFFICIENT_FOR_NUMERIC_SCENARIOS"
                ? "数值情景依据不足，不能视为完整数值研究"
                : "研究完整度仍需复核"
            }
            description="经济有效性尚未批准；情景与假设数量不代表经济质量或估值有效性通过。"
          />
        </section>
      ) : (
        <p>尚未提供研究完整度统计，不推定研究充分。</p>
      )}
      {task.operating_driver_bridge && (
        <OperatingDriverBridgeView bridge={task.operating_driver_bridge} />
      )}
      {task.cash_consumption && (
        <OperatingCashConsumptionView value={task.cash_consumption} />
      )}
      {task.parent_cash_followup && (
        <ParentCashFollowupView value={task.parent_cash_followup} />
      )}
      {(task.current_capital_observation ||
        task.fiscal_distribution_review?.current_observations) && (
        <CurrentCapitalObservationView
          value={
            (task.current_capital_observation ||
              task.fiscal_distribution_review!.current_observations)!
          }
          symbol={task.symbol}
        />
      )}

      {task.parent_funding_review && (
        <ParentFundingResearchPanel
          value={task.parent_funding_review}
          symbol={task.symbol}
        />
      )}
      {task.fiscal_distribution_review && (
        <FiscalDistributionReviewView
          value={task.fiscal_distribution_review}
          symbol={task.symbol}
        />
      )}
      {"error_code" in task && task.error_code && (
        <Alert type="info" message={"任务错误：" + task.error_code} />
      )}
      {task.research_draft ? (
        (
          [
            ["FUNDAMENTAL", "经营基本面草案"],
            ["COUNTER_EVIDENCE", "反证与失效草案"],
            ["EVENT", "事件与后续核验草案"],
          ] as const
        )
          .filter(
            ([key]) =>
              task.status !== "PARTIAL" ||
              ("completed_roles" in task && task.completed_roles.includes(key)),
          )
          .map(([key, title]) => (
            <section key={key}>
              <h4>{title}</h4>
              <Readable
                value={
                  task.research_draft?.[key] &&
                  typeof task.research_draft[key] === "object" &&
                  "draft" in task.research_draft[key]
                    ? (task.research_draft[key] as { draft: unknown }).draft
                    : task.research_draft?.[key]
                }
              />
            </section>
          ))
      ) : (
        <p>尚无可读研究草案，不据此补成研究结论。</p>
      )}
      <details>
        <summary>来源、上下文指纹与用量</summary>
        <Readable
          value={{
            source_binding: task.source_binding,
            context_fingerprint: task.context_fingerprint,
            usage: "usage" in task ? task.usage : undefined,
          }}
        />
      </details>
    </section>
  );
}
export function PublicOperatingResearchView({
  value,
  symbol,
}: {
  value: PublicOperatingResearchResult;
  symbol: string;
}) {
  if (
    value.symbol !== symbol ||
    value.action !== "no_order" ||
    value.formal_eligibility !== false
  )
    return (
      <Alert type="warning" message="公开经营研究身份或边界不符，停止展示" />
    );
  const independentRevalidation = value.main_valuation_revalidation ? (
    <MainValuationRevalidationPanel
      value={value.main_valuation_revalidation}
      symbol={symbol}
    />
  ) : null;
  if (value.status === "NOT_STARTED")
    return (
      <>
        <p>尚无已生成的公开经营研究。</p>
        {independentRevalidation}
      </>
    );
  if (value.status === "UNASSESSABLE")
    return (
      <>
        {" "}
        <Alert
          type="info"
          message="最新经营研究暂不可核验，不回退展示旧成功结果"
          description={value.reason}
        />
        {independentRevalidation}
      </>
    );
  if (value.status !== "SUCCEEDED" && value.status !== "PARTIAL")
    return <Alert type="warning" message="公开经营研究状态不符，停止展示" />;
  const allRoles: OperatingResearchRoleKey[] = [
    "FUNDAMENTAL",
    "COUNTER_EVIDENCE",
    "EVENT",
  ];
  const partial = value.status === "PARTIAL";
  const completed = partial ? value.completed_roles : allRoles;
  const rolePartitionValid =
    !partial ||
    (value.execution_status === "FAILED" &&
      Array.isArray(value.completed_roles) &&
      value.completed_roles.length > 0 &&
      value.completed_roles.length < allRoles.length &&
      Array.isArray(value.pending_roles) &&
      value.pending_roles.length > 0 &&
      [...value.completed_roles, ...value.pending_roles].length ===
        allRoles.length &&
      new Set([...value.completed_roles, ...value.pending_roles]).size ===
        allRoles.length &&
      [...value.completed_roles, ...value.pending_roles].every((role) =>
        allRoles.includes(role),
      ) &&
      typeof value.reason === "string" &&
      !!value.reason &&
      Object.keys(value.research_draft || {}).length ===
        value.completed_roles.length &&
      Object.keys(value.research_draft || {}).every((role) =>
        value.completed_roles.includes(role as OperatingResearchRoleKey),
      ));
  const source = value.source_binding as { sha256?: unknown } | null;
  const hash = (item: unknown) =>
    typeof item === "string" && /^[a-f0-9]{64}$/.test(item);
  if (
    (value.status !== "SUCCEEDED" && value.status !== "PARTIAL") ||
    !rolePartitionValid ||
    (value.research_completeness != null &&
      value.research_completeness.economic_validation !== "NOT_APPROVED") ||
    value.scope !== "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" ||
    value.main_range_adopted !== false ||
    value.approval_changed !== false ||
    value.formal_fact_count !== 0 ||
    value.condition_price !== null ||
    value.personal_quantity !== null ||
    !value.task_id ||
    !hash(value.context_fingerprint) ||
    !hash(source?.sha256) ||
    !Number.isInteger(value.new_llm_calls) ||
    value.new_llm_calls < 1 ||
    (Array.isArray(completed) ? completed : allRoles).some((role) => {
      const row = value.research_draft?.[role];
      return (
        !row ||
        !row.model_id ||
        !row.generated_at ||
        !Array.isArray(row.source_bindings) ||
        !row.source_bindings.length ||
        row.source_bindings.some(
          (ref) =>
            !ref ||
            typeof ref !== "object" ||
            !hash((ref as { pdf_sha256?: unknown }).pdf_sha256),
        ) ||
        !row.draft ||
        typeof row.draft !== "object" ||
        Array.isArray(row.draft)
      );
    })
  )
    return (
      <>
        {" "}
        <Alert
          type="warning"
          message="公开经营研究来源、角色草案或准入边界不完整，停止展示"
        />
        {independentRevalidation}
      </>
    );
  return <LiveOperatingResearchDraft task={value} />;
}
type Operation =
  "status" | "start" | "history" | "refresh" | "cancel" | "resume" | "finalize";
export function LiveOperatingResearchPanel({ symbol }: { symbol: string }) {
  const [opened, setOpened] = useState(false);
  const [publicResult, setPublicResult] =
    useState<PublicOperatingResearchResult>();
  const [publicError, setPublicError] = useState<string>();
  const [model, setModel] = useState<OperatingResearchModelStatus>();
  const [task, setTask] = useState<LiveOperatingResearchTask>();
  const [items, setItems] = useState<LiveOperatingResearchTask[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const lock = useRef(false);
  const generation = useRef(0);
  const publicReadEpoch = useRef(0);
  const [tracking, setTracking] = useState(true);
  useEffect(() => {
    generation.current += 1;
    setOpened(false);
    setTask(undefined);
    setItems([]);
    setPublicResult(undefined);
    setModel(undefined);
    setError(undefined);
    setTracking(true);
  }, [symbol]);
  // Poll only a task explicitly selected by the user. GET never starts research.
  useEffect(() => {
    if (
      !opened ||
      !tracking ||
      !task ||
      !["QUEUED", "RUNNING"].includes(task.status)
    )
      return;
    let disposed = false;
    const id = task.task_id;
    const timer = setTimeout(async () => {
      if (lock.current) return;
      try {
        const value = await api.operatingResearchTask(id);
        if (disposed) return;
        if (!validLiveTask(value, symbol) || value.task_id !== id)
          throw new Error("Invalid task identity");
        setTask(value);
      } catch (cause) {
        if (!disposed) {
          if (cause instanceof ApiError && cause.code === "LIVE_STATE_BUSY") {
            // Keep the last observed state; a publishing lock is not failure.
            setTask((current) =>
              current?.task_id === id ? { ...current } : current,
            );
            return;
          }
          setTracking(false);
          setError(
            "自动读取已暂停，后台任务状态未知；请刷新当前任务，不会重新调用模型。",
          );
        }
      }
    }, 3000);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [opened, tracking, task, symbol, busy]);
  async function perform(operation: Operation) {
    if (lock.current) return;
    if (
      (operation === "start" || operation === "resume") &&
      model?.status !== "READY"
    )
      return;
    if (
      ["refresh", "cancel", "resume", "finalize"].includes(operation) &&
      !task
    )
      return;
    lock.current = true;
    const requestGeneration = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      if (operation === "status") {
        const publicEpoch = ++publicReadEpoch.current;
        setOpened(true);
        setPublicResult(undefined);
        setPublicError(undefined);
        // Economic replay can be slow; it must not lock task controls. Both
        // reads remain source-validated, and neither can start a model call.
        void api.operatingResearchCompany(symbol).then(
          (value) => {
            if (
              generation.current === requestGeneration &&
              publicReadEpoch.current === publicEpoch
            )
              setPublicResult(value);
          },
          () => {
            if (
              generation.current === requestGeneration &&
              publicReadEpoch.current === publicEpoch
            )
              setPublicError(
                "公开经营研究暂不可读取，不回退展示旧结果；可手动刷新重试。",
              );
          },
        );
        const result = await api.operatingResearchModelStatus();
        if (generation.current !== requestGeneration) return;
        if (
          ![
            "READY",
            "MODEL_AUTHORIZATION_REQUIRED",
            "MODEL_CREDENTIAL_REQUIRED",
          ].includes(result.status)
        )
          throw new Error("Invalid model status");
        if (
          result.status !== "MODEL_AUTHORIZATION_REQUIRED" &&
          (result.currency !== "CNY" ||
            !result.model_id ||
            result.max_run_cost == null ||
            !Number.isFinite(Number(result.max_run_cost)) ||
            result.daily_cost_limit == null ||
            !Number.isFinite(Number(result.daily_cost_limit)))
        )
          throw new Error("Invalid model cost configuration");
        setModel(result);
      } else if (operation === "history") {
        const result = await api.operatingResearchTasks(symbol);
        if (generation.current !== requestGeneration) return;
        if (
          !Array.isArray(result.items) ||
          (result.symbol && result.symbol !== symbol)
        )
          throw new Error("Invalid task history");
        setItems(result.items);
        const latest = result.items.find((row) => validLiveTask(row, symbol));
        if (latest) {
          setTask(latest);
          setTracking(true);
        }
      } else {
        const result =
          operation === "start"
            ? await api.createOperatingResearchTask({
                symbol,
                request_key:
                  "live_" +
                  Array.from(crypto.getRandomValues(new Uint8Array(16)), (x) =>
                    x.toString(16).padStart(2, "0"),
                  ).join(""),
              })
            : operation === "refresh"
              ? await api.operatingResearchTask(task!.task_id)
              : operation === "cancel"
                ? await api.cancelOperatingResearchTask(task!.task_id)
                : operation === "finalize"
                  ? await api.finalizeOperatingResearchTask(task!.task_id)
                  : await api.resumeOperatingResearchTask(task!.task_id);
        if (generation.current !== requestGeneration) return;
        if (
          !validLiveTask(result, symbol) ||
          (operation !== "start" && result.task_id !== task!.task_id)
        )
          throw new Error("Invalid research task boundary");
        setTask(result);
        setTracking(true);
      }
    } catch (cause) {
      if (generation.current !== requestGeneration) return;
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "任务操作需要本机授权；公开研究仍可查看，请解锁后手动重试。"
          : cause instanceof ApiError && cause.code === "FINALIZATION_PENDING"
            ? "工作进程已停止，状态落盘尚待完成；点击完成状态写入，不会调用模型。"
            : cause instanceof ApiError &&
                cause.code === "LIVE_EXECUTION_STILL_ACTIVE"
              ? "任务仍在运行，未启动重复调用；请继续读取状态。"
              : "经营研究操作未完成或响应边界无法核验，请手动重试。",
      );
      if (operation === "status") setModel(undefined);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (!opened)
    return <Button onClick={() => perform("status")}>新Agent经营研究</Button>;
  const ready = model?.status === "READY";
  const active = task?.status === "QUEUED" || task?.status === "RUNNING";
  return (
    <section aria-label="新Agent经营研究" style={{ marginBlock: 20 }}>
      <h3>新Agent经营研究 · {symbol}</h3>
      <p>
        打开此区仅读取模型状态与已生成公开研究，不发起模型调用；点击启动才可能产生新调用费用。运行中每3秒读取一次真实任务状态，失败时暂停读取；刷新页面后点击读取已有任务即可恢复跟踪，不重复启动研究。研究结果仍需复核，不审批、不下单。
      </p>
      <section aria-label="已生成的公开经营研究">
        <h4>已生成的公开经营研究</h4>
        {publicError && <Alert type="info" message={publicError} />}
        {publicResult && (
          <PublicOperatingResearchView value={publicResult} symbol={symbol} />
        )}
      </section>
      {error && <Alert type="info" message={error} />}
      <p>
        {ready
          ? "模型已就绪"
          : model?.status === "MODEL_AUTHORIZATION_REQUIRED"
            ? "模型接口、模型或调用配置尚未齐备，不能启动"
            : model?.status === "MODEL_CREDENTIAL_REQUIRED"
              ? "缺少模型凭据，不能启动"
              : "模型状态尚未核验，不能启动"}{" "}
        · 模型：{model?.model_id || "未提供"} · 单次预留上限（人民币元）：
        {model?.max_run_cost ?? "未提供"} · 每日费用上限（人民币元）：
        {model?.daily_cost_limit ?? "未提供"}
        （已授权每日人民币10元；费用按配置费率估算，非账单）
      </p>
      <Space wrap>
        <Button disabled={busy} onClick={() => perform("status")}>
          刷新模型状态
        </Button>
        <Button
          disabled={busy || !ready || active}
          onClick={() => perform("start")}
        >
          启动新研究
        </Button>
        <Button disabled={busy} onClick={() => perform("history")}>
          读取已有经营研究任务
        </Button>
        <Button disabled={busy || !task} onClick={() => perform("refresh")}>
          刷新当前任务
        </Button>
        <Button
          disabled={busy || !task || !active}
          onClick={() => perform("cancel")}
        >
          取消当前任务
        </Button>
        <Button
          disabled={
            busy ||
            !ready ||
            !task ||
            ["SUCCEEDED", "CANCELLED"].includes(task.status)
          }
          onClick={() => perform("resume")}
        >
          恢复当前任务
        </Button>
        <Button disabled={busy || !task} onClick={() => perform("finalize")}>
          完成状态写入（不调用模型）
        </Button>
      </Space>
      <ul>
        {items.map((row, i) => (
          <li key={i}>
            {validLiveTask(row, symbol) ? (
              <Button
                disabled={busy}
                onClick={() => {
                  setTask(row);
                  setTracking(true);
                  setError(undefined);
                }}
              >
                选择任务 {row.task_id} · {LABELS[row.status] || row.status}
              </Button>
            ) : (
              "任务身份或研究边界不符，不能选择"
            )}
          </li>
        ))}
      </ul>
      {task && <LiveOperatingResearchDraft task={task} />}
    </section>
  );
}
