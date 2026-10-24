import type { ValueResearchAnalysis } from "../types/api";
import { readinessNumber } from "../utils/strategyReadiness";

const labels: Record<string, string> = {
  operating_revenue: "营业收入",
  interest_income: "利息收入",
  revenue_unallocated: "未分配收入残差",
  cost_of_sales: "营业成本",
  interest_expense: "利息支出",
  commission_expense: "手续费及佣金支出",
  taxes_surcharges: "税金及附加",
  selling: "销售费用",
  administration: "管理费用",
  research: "研发费用",
  finance: "财务费用",
  cost_unallocated: "未分配成本残差",
  other_income: "其他收益",
  investment: "投资收益",
  fair_value: "公允价值变动",
  credit_impairment: "信用减值",
  asset_impairment: "资产减值",
  disposal: "资产处置",
  operating_unallocated: "未分配营业利润残差",
  nonoperating_income: "营业外收入",
  nonoperating_expense: "营业外支出",
  income_tax: "所得税费用",
  minority_profit: "少数股东损益",
  nonrecurring_parent_difference: "归母净非经常损益差额",
};

export function OperatingEarningsBridge({
  analysis,
}: {
  analysis: ValueResearchAnalysis;
}) {
  const independent = analysis.status === "SOURCE_OR_REPLAY_UNAVAILABLE";
  const review = independent
    ? analysis.historical_operating_review
    : analysis.economic_assessment?.earnings?.operating_quality_bridge;
  if (!review) return null;
  const current = analysis.review_binding?.candidate_binding;
  const sha = (value: unknown) =>
    typeof value === "string" &&
    value.length === 64 &&
    /^[a-f0-9]{64}$/.test(value);
  const sourceRows = review.source_bindings ?? [];
  const independentBound =
    independent &&
    analysis.schema_version === "value-research-analysis-v1" &&
    analysis.action === "no_order" &&
    analysis.arithmetic_complete === false &&
    analysis.action_admitted === false &&
    analysis.strategy_admitted === false &&
    analysis.price_comparison_eligible === false &&
    analysis.economic_assumptions_reviewed === false &&
    review.context_scope === "INDEPENDENT_RETAINED_FILINGS_V1" &&
    review.action_admitted === false &&
    review.approval_changed === false &&
    review.primary_valuation_usable === false &&
    review.scope ===
      "HISTORICAL_EARNINGS_DRIVERS_NOT_FORWARD_NORMALIZED_EARNINGS" &&
    review.availability_scope ===
      "RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF" &&
    review.candidate_binding === undefined &&
    review.input_descriptor_sha256 === undefined &&
    typeof review.read_at === "string" &&
    Number.isFinite(Date.parse(review.read_at)) &&
    Array.isArray(review.report_periods) &&
    review.report_periods.length === 2 &&
    review.report_periods.some(
      (periods) => JSON.stringify(periods) === '["FY2025","FY2024"]',
    ) &&
    review.report_periods.some(
      (periods) => JSON.stringify(periods) === '["H12026","H12025"]',
    ) &&
    Array.isArray(review.execution_bindings) &&
    review.execution_bindings.length === 4 &&
    new Set(review.execution_bindings.map((ref) => ref.path)).size === 4 &&
    review.execution_bindings.every(
      (ref) =>
        typeof ref.path === "string" && !!ref.path.trim() && sha(ref.sha256),
    ) &&
    typeof review.source_spec_binding?.path === "string" &&
    !!review.source_spec_binding.path.trim() &&
    sha(review.source_spec_binding.sha256) &&
    Array.isArray(sourceRows) &&
    sourceRows.length === 2 &&
    new Set(sourceRows.map((row) => row.source_id)).size === 2 &&
    new Set(sourceRows.map((row) => row.path)).size === 2 &&
    sourceRows.every(
      (row) =>
        typeof row.source_id === "string" &&
        !!row.source_id.trim() &&
        typeof row.path === "string" &&
        !!row.path.trim() &&
        sha(row.sha256),
    ) &&
    !!review.h1_change?.rows?.length &&
    review.h1_change.rows.every(
      (row) =>
        Array.isArray(row.fact_refs) &&
        row.fact_refs.length > 0 &&
        row.fact_refs.every((ref) =>
          sourceRows.some(
            (source) =>
              source.source_id === ref.source_id &&
              source.path === ref.path &&
              source.sha256 === ref.sha256 &&
              source.source_url === ref.source_url,
          ),
        ),
    );
  if (
    review.status !== "SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED" ||
    review.schema_version !== "operating-earnings-quality-bridge-v1" ||
    review.symbol !== analysis.symbol ||
    review.action !== "no_order" ||
    (independent
      ? !independentBound
      : review.context_scope !== undefined ||
        review.input_descriptor_sha256 !== analysis.input_descriptor_sha256 ||
        !current ||
        review.candidate_binding?.path !== current.path ||
        review.candidate_binding?.sha256 !== current.sha256) ||
    review.g3_changed !== false ||
    review.price_admitted !== false ||
    review.strategy_admitted !== false ||
    review.normalized_earnings_admitted !== false ||
    review.normalized_parent_profit_cny !== null ||
    review.normalized_range !== null ||
    !review.h1_change?.rows?.length ||
    !review.commercial_subtotal
  )
    return (
      <p>
        盈利驱动资料未通过当前研究来源或口径核验，暂不展示金额；不改变原投资状态。
      </p>
    );
  return (
    <section
      aria-label="历史盈利驱动"
      style={{ minWidth: 0, overflowWrap: "anywhere" }}
    >
      <h4>利润为什么变化</h4>
      {independent && (
        <p>
          独立财报解释：仅重验留存官方原件，不证明旧估值仍可重放，不继承其审批、价格或操作资格；原始取得时间未知时不补造历史
          PIT。
        </p>
      )}
      {independent && (
        <>
          <p>
            本次读取核验：{review.read_at}；报告期间：
            {review.report_periods
              ?.map((periods) => periods.join(" / "))
              .join("；")}
            。
          </p>
          <details>
            <summary>本次来源与解析依赖</summary>
            <p>
              来源规范：{review.source_spec_binding?.path} ·{" "}
              {review.source_spec_binding?.sha256}
            </p>
            <ul>
              {sourceRows.map((source) => (
                <li key={source.source_id}>
                  {source.source_id}；发布：{source.published_date}；原始取得：
                  {source.original_acquired_at ?? "未知（不补造）"}
                  <br />
                  {source.path} · {source.sha256}
                </li>
              ))}
            </ul>
            <ul>
              {review.execution_bindings?.map((ref) => (
                <li key={ref.path}>
                  {ref.path} · {ref.sha256}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <p>
        上半年扣非归母利润同比变化{" "}
        {readinessNumber(review.h1_change.computed_change_cny)} 元；
        营业收入减营业成本、税金及销售/管理/研发费用的小计同比变化{" "}
        {readinessNumber(review.commercial_subtotal.change_cny)} 元。
      </p>
      <p>
        上述商业小计不是正常化利润。减值、资金收益、税负和少数股东归属需要分别研究，不能直接把税前损失加回归母利润。
      </p>
      <p>
        全年扣非归母同比变化{" "}
        {readinessNumber(review.annual_change?.computed_change_cny)} 元；
        历史滚动扣非归母利润 {readinessNumber(review.historical_ttm_cny)} 元。
        正常化盈利仍未知，本桥不授予主估值、买入或加仓资格。
      </p>
      <details>
        <summary>逐项查看上半年盈利变化与原件</summary>
        <div className="earnings-driver-scroll">
          <table className="earnings-driver-table">
            <thead>
              <tr>
                <th>项目</th>
                <th>本期金额（元）</th>
                <th>同期金额（元）</th>
                <th>对扣非利润变化的贡献（元）</th>
                <th>证据</th>
              </tr>
            </thead>
            <tbody>
              {review.h1_change.rows.map((row) => (
                <tr key={row.field}>
                  <td>{labels[row.field] ?? row.field}</td>
                  <td>{readinessNumber(row.current_cny)}</td>
                  <td>{readinessNumber(row.comparative_cny)}</td>
                  <td>{readinessNumber(row.contribution_cny)}</td>
                  <td>
                    <details>
                      <summary>原始披露</summary>
                      {row.fact_refs.map((ref, index) => (
                        <div key={`${ref.source_id}:${ref.field}:${index}`}>
                          <a
                            href={
                              /^https:\/\//.test(ref.source_url)
                                ? ref.source_url
                                : undefined
                            }
                            target="_blank"
                            rel="noreferrer"
                          >
                            {ref.label} · PDF 第 {ref.physical_page} 页
                          </a>
                          <p>{ref.excerpt}</p>
                          <code>{ref.sha256}</code>
                        </div>
                      ))}
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          勾稽残差 {readinessNumber(review.h1_change.arithmetic_residual_cny)}{" "}
          元。
          残差为零仅证明所选表内金额对平，不证明披露完整或未来盈利可持续；未识别项不按零处理。
        </p>
      </details>
    </section>
  );
}
