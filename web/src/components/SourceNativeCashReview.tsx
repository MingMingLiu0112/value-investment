import type { ValueResearchAnalysis } from "../types/api";
import { SourceNativeEconomicReview } from "./SourceNativeEconomicReview";
import {
  nativeCashFields,
  sourceNativeCashReviewMatches,
} from "../services/valuePolicy";
import { readinessNumber } from "../utils/strategyReadiness";

const rowLabels: Record<(typeof nativeCashFields)[number], string> = {
  opening_book: "期初普通股权益（模型口径）",
  profit: "普通股权益模型利润",
  roe: "模型 ROE（不是已验证 ROIC）",
  book_close: "期末普通股权益（模型口径）",
  actual_retention: "模型实际留存比例",
  legacy_profit_before_new_cash_cost: "新增现金成本前的原经营利润",
  permanent_after_tax_cash_expense: "永久性税后现金费用（本分支模型值）",
  assumed_parent_standalone_profit: "假设母公司单体利润",
  parent_net_funds: "模型母公司净资金流入",
  incremental_parent_cash_income: "增量母公司现金收益（模型值）",
  opening_parent_cash: "期初母公司现金",
  opening_delayed_asset: "期初延迟回收资产",
  newly_withheld: "本期新增延迟上划",
  released: "本期假设回收额",
  delayed_close: "期末仍延迟资产",
  cash_capacity: "模型现金容量（非已证可分红现金）",
  cash_close: "期末母公司现金",
  cash_bridge_residual: "模型现金演算残差（零不证明历史桥完整）",
  project_cash: "项目现金支出假设",
  fund_capital_call: "基金出资付款假设",
  fund_asset_at_cost: "基金资产成本（模型账）",
  dividend_planned: "计划股息（假设）",
  dividend_paid: "模型允许支付股息（不是已派息）",
  retained_profit_capacity: "模型留存利润容量（不是法律意见）",
  parent_retained_profit_close: "期末母公司留存利润",
  parent_equity_close: "期末母公司单体权益",
  statutory_appropriation: "法定提取假设",
};
const scenarioLabels = {
  bear: "保守 Bear",
  base: "基准 Base",
  bull: "乐观 Bull",
};

/** Read-only source projection. No valuation, ledger reconstruction or approval. */
export function SourceNativeCashReview({
  analysis,
  symbol,
}: {
  analysis: ValueResearchAnalysis;
  symbol: string;
}) {
  if (analysis.source_native_cash_review == null) return null;
  if (!sourceNativeCashReviewMatches(analysis, symbol))
    return (
      <section aria-label="原生现金路径条件研究">
        <p className="value-analysis-boundary">
          当前页面仍展示待审候选；研究级签名CLI已实现，本页尚未接入其准入结果。
        </p>
        <p role="status">
          原生现金路径的分支、日期、来源或估值绑定待核验，暂不展示本附录现金数值。不得据此认定经济或交易准入。
        </p>
      </section>
    );
  const native = analysis.source_native_cash_review!;
  return (
    <section
      aria-label="原生现金路径条件研究"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h3>原生现金路径条件研究</h3>
      <p className="value-analysis-boundary">
        当前页面仍展示待审候选；研究级签名CLI已实现，本页尚未接入其准入结果，不能视为主估值或价格批准。
      </p>
      <p className="value-analysis-boundary">
        低置信度（LOW） · 前瞻假设，非正常化事实 · 未获主估值 / G3 或策略批准。
      </p>
      <p>
        估值基准日 {native.point_in_time.valuation_date}；研究截至{" "}
        {native.point_in_time.research_as_of}
        。这是指定基准日的条件模型，不是今日公允价值。
      </p>
      <SourceNativeEconomicReview
        key={`${symbol}:${native.candidate_binding.path}:${native.candidate_binding.sha256}`}
        symbol={symbol}
        candidate={native.candidate_binding}
      />
      <h4>只选择了“暂时延迟回收”分支</h4>
      <p>
        本次后端明确选择
        TIMING_DELAY：假设第一年发生延迟，第二年收回全部期初延迟资产，此后不再新增留置。这不是已经收到现金或已证明可以上划。
      </p>
      <p>
        暂时延迟影响资金可得时点；永久性现金费用会损伤未来利润；长期无法上划则可能留下不可支配资产。三者不是同一件事，选定本分支不证明其他分支成立、已排除或已获验证。
      </p>
      <p>
        模型把现金回收、母公司利润确认、项目及基金付款、股息与期末权益联动。母公司利润、普通股权益模型利润和现金容量不能直接等同。
      </p>
      <p>
        延迟比例假设：{native.joint_assumptions.TIMING_DELAY.withheld_fraction}
        ；发生期：第{" "}
        {native.joint_assumptions.TIMING_DELAY.withheld_years.join("、")}{" "}
        年；留存比例假设：{native.joint_assumptions.explicit_retention}
        。回收节奏以以下后端年度账为准。
      </p>
      <p className="value-analysis-boundary">
        本附录不证明历史现金桥完整；经济性、事件影响、主估值与正式审批仍须独立核验。算术重放成功不等于股息可持续或现金已可分配。
      </p>
      {(["bear", "base", "bull"] as const).map((name) => {
        const scenario = native.scenarios[name];
        return (
          <details key={name}>
            <summary>
              {scenarioLabels[name]} · 条件模型值{" "}
              {readinessNumber(scenario.per_share_value)} 元/股（未批准）
            </summary>
            <p>未来年度均为假设。金额单位为元；比例原样显示，负值不抹零。</p>
            <dl className="value-analysis-grid">
              <div>
                <dt>权益资本成本（假设）</dt>
                <dd>{readinessNumber(scenario.inputs.cost_of_equity)}</dd>
              </div>
              <div>
                <dt>终端 ROE（不是已验证 ROIC）</dt>
                <dd>{readinessNumber(scenario.inputs.terminal_roe)}</dd>
              </div>
              <div>
                <dt>终端增长（假设）</dt>
                <dd>{readinessNumber(scenario.inputs.terminal_growth)}</dd>
              </div>
            </dl>
            {scenario.cash_ledger.map((row) => (
              <details key={row.year}>
                <summary>
                  第 {row.year} 年 · 利润、回收、股息与权益（全部为模型假设）
                </summary>
                <dl className="value-analysis-grid">
                  {nativeCashFields.map((field) => (
                    <div key={field}>
                      <dt>{rowLabels[field]}</dt>
                      <dd>{readinessNumber(row[field])}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            ))}
          </details>
        );
      })}
      <h4>仍需判断的关键问题</h4>
      <ul>
        <li>
          延迟资产是否确为可回收的结算或营运资金，而非永久损失？回收证据及时间表是什么？
        </li>
        <li>
          子公司是否能够依法向母公司上划资金？长期受限时，终端能否继续沿用？
        </li>
        <li>
          项目及基金付款、维持性支出和现金底线是否完整？母公司可分配利润与分红限制是否已经单独确认？
        </li>
        <li>
          利润确认、股息和终端假设有无最强反证？模型账闭合不能替代上述经济判断。
        </li>
      </ul>
      <details>
        <summary>原始时点、假设与来源绑定（只读）</summary>
        <p>
          资料可得：{native.point_in_time.available_at}；计算：
          {native.point_in_time.computed_at}；模型起点：
          {native.valuation_timing.basis_at}；估值时点：
          {native.valuation_timing.valuation_at}。不是原始历史 PIT 证明。
        </p>
        <p>候选：{native.candidate_binding.path}</p>
        <code>{native.candidate_binding.sha256}</code>
        <ul>
          {native.source_bindings.map((ref) => (
            <li key={ref.path}>
              <span>{ref.path}</span>
              <code>{ref.sha256}</code>
            </li>
          ))}
        </ul>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            maxWidth: "100%",
          }}
        >
          {JSON.stringify(native.joint_assumptions, null, 2)}
        </pre>
      </details>
    </section>
  );
}
