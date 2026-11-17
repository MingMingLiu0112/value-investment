import type { FiniteAdvantageResearch as Research } from "../types/api";
import type { ProductContinuationResearch } from "../types/api";
import { isObservedResearchTimestamp } from "../utils/researchDraftText";
import { readinessNumber } from "../utils/strategyReadiness";

const number = (v: unknown) =>
  typeof v === "string" &&
  /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(v) &&
  Number.isFinite(Number(v));
const reconciled = (v: unknown) => number(v) && Math.abs(Number(v)) <= 1e-8;
const names: Record<string, string> = {
  bear: "保守",
  base: "基准",
  bull: "乐观",
};

function ProductContinuation({
  research,
}: {
  research?: ProductContinuationResearch;
}) {
  if (!research) return null;
  let valid = false;
  try {
    valid =
      research.status === "SOURCE_BOUND_PRODUCT_CONTINUATION_NOT_APPROVED" &&
      research.action === "no_order" &&
      research.confidence === "LOW" &&
      research.formal_eligibility === false &&
      research.economic_approval === false &&
      research.price_admission === false &&
      research.primary_valuation_changed === false &&
      isObservedResearchTimestamp(research.input_available_at) &&
      Array.isArray(research.source_bindings) &&
      research.source_bindings.length > 0 &&
      research.source_bindings.every(
        (ref) =>
          typeof ref.path === "string" &&
          ref.path.trim() &&
          /^[a-f0-9]{64}$/.test(ref.sha256),
      ) &&
      Array.isArray(research.scenarios) &&
      research.scenarios.length === 6 &&
      new Set(research.scenarios.map((row) => row.scenario + ":" + row.branch))
        .size === 6 &&
      research.scenarios.every(
        (row) =>
          ["bear", "base", "bull"].includes(row.scenario) &&
          [
            "FLAT_PRODUCT_CONTINUATION",
            "REALIZATION_AND_COST_CHALLENGE",
          ].includes(row.branch) &&
          row.result.action === "no_order" &&
          row.result.formal_eligibility === false &&
          row.result.economic_approval === false &&
          row.result.price_admission === false &&
          row.result.primary_valuation_changed === false &&
          Array.isArray(row.result.cash_rows) &&
          row.result.cash_rows.every(
            (cash) =>
              Number.isInteger(cash.year) &&
              [
                cash.legacy_profit_cny,
                cash.incremental_cash_income_cny,
                cash.profit_cny,
                cash.distribution_cny,
                cash.closing_cash_cny,
              ].every(number),
          ) &&
          (row.result.valuation.usable === true
            ? row.result.status ===
                "CONDITIONAL_PRODUCT_CONTINUATION_RESEARCH" &&
              number(row.result.valuation.per_share_cny) &&
              reconciled(row.result.valuation.ri_ddm_residual_cny) &&
              number(row.result.valuation.terminal_value_pv_share) &&
              Number(row.result.valuation.terminal_value_pv_share) >= 0 &&
              Number(row.result.valuation.terminal_value_pv_share) <= 1 &&
              row.result.blockers.length === 0
            : row.result.status === "VALUATION_UNSUPPORTED" &&
              row.result.valuation.per_share_cny === null),
      );
  } catch {
    valid = false;
  }
  if (!valid)
    return (
      <p role="status">经营延续研究的来源或假设待核验，暂不展示新金额。</p>
    );
  return (
    <section aria-label="经营延续中心假说">
      <h3>经营延续中心假说 · 未批准</h3>
      <p>
        前五年保留原产品经营路径；第六至十年假设销量、单位实现收入不再增长，成本费用率停在第五年水平。存量盈利与新增留存资金收益分开，不强制经营利润因总
        ROE 下降而下跌。
      </p>
      <p className="value-analysis-boundary">
        这是非压力中心候选研究，不是已选定主估值、正常化盈利或买入价；金额仍按下方历史基准与股数计算。
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>经营情景</th>
              <th>延续条件值（元／股）</th>
              <th>经营恶化挑战（元／股）</th>
              <th>延续值中终端现值占比</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(names).map((name) => {
              const center = research.scenarios.find(
                (row) =>
                  row.scenario === name &&
                  row.branch === "FLAT_PRODUCT_CONTINUATION",
              )!.result;
              const challenge = research.scenarios.find(
                (row) =>
                  row.scenario === name &&
                  row.branch === "REALIZATION_AND_COST_CHALLENGE",
              )!.result;
              return (
                <tr key={name}>
                  <td>{names[name]}</td>
                  <td>
                    {center.valuation.usable
                      ? readinessNumber(center.valuation.per_share_cny)
                      : "不可估值"}
                  </td>
                  <td>
                    {challenge.valuation.usable
                      ? readinessNumber(challenge.valuation.per_share_cny)
                      : "不可估值"}
                  </td>
                  <td>
                    {center.valuation.usable
                      ? Number(
                          center.valuation.terminal_value_pv_share,
                        ).toLocaleString("zh-CN", {
                          style: "percent",
                          minimumFractionDigits: 1,
                          maximumFractionDigits: 1,
                        })
                      : "不可核验"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p>
        经营恶化挑战只在第六至十年将茅台产品单位实现收入每年下调
        1%、成本率较第五年提高 0.5
        个百分点；不是所有产品同步衰退，也不是统计损失边界。
      </p>
      <p>
        终端仍依赖品牌盈利持续、维护与营运资金平衡、资金可得及合法分配，不能因延长显式期便视为低风险。现金收益只计期初资金相对最初资金的增量，终值不再另加一次现金。
      </p>
      {Array.isArray(research.sensitivity_cases) &&
        research.sensitivity_cases.length === 3 &&
        research.sensitivity_cases.every(
          (row) =>
            row?.scenario === "base" &&
            [
              "FINANCIAL_CONTRIBUTION_FADE",
              "COST_OF_EQUITY_PLUS_100BP",
              "FINANCIAL_FADE_AND_HIGHER_REQUIRED_RETURN",
            ].includes(row.branch) &&
            row.result?.action === "no_order" &&
            row.result.formal_eligibility === false &&
            row.result.economic_approval === false &&
            row.result.price_admission === false &&
            row.result.primary_valuation_changed === false &&
            (row.result.valuation?.usable === true
              ? row.result.status ===
                  "CONDITIONAL_PRODUCT_CONTINUATION_RESEARCH" &&
                number(row.result.valuation.per_share_cny) &&
                reconciled(row.result.valuation.ri_ddm_residual_cny) &&
                Array.isArray(row.result.blockers) &&
                row.result.blockers.length === 0
              : row.result.status === "VALUATION_UNSUPPORTED" &&
                row.result.valuation?.per_share_cny === null),
        ) &&
        new Set(research.sensitivity_cases.map((row) => row.branch)).size ===
          3 && (
          <>
            <h4>基准估值依赖哪些假设</h4>
            <p>
              保持前五年不变；第六至十年将金融类报表税前贡献逐步降至历史参考的一半，另测要求回报提高1个百分点。金融贡献不是金融子公司净利润，也不代表母公司可分配现金；这些是未校准挑战，不是预测或买入价。
            </p>
            <table>
              <thead>
                <tr>
                  <th>假设变化</th>
                  <th>每股条件值（元）</th>
                </tr>
              </thead>
              <tbody>
                {research.sensitivity_cases.map((row) => (
                  <tr key={row.branch}>
                    <td>
                      {row.branch === "FINANCIAL_CONTRIBUTION_FADE"
                        ? "金融类贡献逐步减半"
                        : row.branch === "COST_OF_EQUITY_PLUS_100BP"
                          ? "要求回报提高1个百分点"
                          : "两项同时发生"}
                    </td>
                    <td>
                      {row.result.valuation.usable
                        ? readinessNumber(row.result.valuation.per_share_cny)
                        : "现金或终端条件不支持估值"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      <details>
        <summary>中心路径的盈利与资金来源</summary>
        {research.scenarios
          .filter(
            (row) =>
              row.scenario === "base" &&
              row.branch === "FLAT_PRODUCT_CONTINUATION",
          )
          .map((row) => (
            <div key={row.branch} style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>模型年</th>
                    <th>产品关联盈利</th>
                    <th>增量现金收益</th>
                    <th>总归母盈利假说</th>
                    <th>分配假说</th>
                    <th>期末现金代理</th>
                  </tr>
                </thead>
                <tbody>
                  {row.result.cash_rows.map((cash) => (
                    <tr key={cash.year}>
                      <td>{cash.year}</td>
                      <td>{readinessNumber(cash.legacy_profit_cny)}</td>
                      <td>
                        {readinessNumber(cash.incremental_cash_income_cny)}
                      </td>
                      <td>{readinessNumber(cash.profit_cny)}</td>
                      <td>{readinessNumber(cash.distribution_cny)}</td>
                      <td>{readinessNumber(cash.closing_cash_cny)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                产品关联盈利还含历史金融及其他税前余额假说，不是纯经营利润。母公司现金仅作研究锚，不能认定这些款项已可合法分红。
              </p>
            </div>
          ))}
      </details>
    </section>
  );
}
const reasons = (codes: string[]) =>
  codes
    .map((code) => {
      if (code.includes("CASH_FLOOR"))
        return "现金低于研究储备底线，不能维持计划分配";
      if (code.includes("net_maintenance_wc_balanced"))
        return "持续净现金投入与终端全额分红冲突";
      if (code.includes("unremitted")) return "终端仍有未上划资金";
      return "现金、分配或终端假设未满足";
    })
    .filter((value, index, all) => all.indexOf(value) === index)
    .join("；");

export function FiniteAdvantageResearch({
  research,
  symbol,
}: {
  research?: Research;
  symbol?: string;
}) {
  if (!research) return null;
  let valid = false;
  try {
    valid =
      research.schema_version === "finite-advantage-research-v1" &&
      research.symbol === symbol &&
      research.status === "SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED" &&
      research.scope === "ordinary_owner_equivalent_cash_mapping" &&
      research.currency === "CNY" &&
      research.confidence === "LOW" &&
      research.action === "no_order" &&
      research.formal_eligibility === false &&
      research.economic_approval === false &&
      research.price_admission === false &&
      research.primary_valuation_changed === false &&
      research.price_condition_cny === null &&
      isObservedResearchTimestamp(research.input_available_at) &&
      typeof research.basis_date === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(research.basis_date) &&
      isObservedResearchTimestamp(`${research.basis_date}T00:00:00+08:00`) &&
      Array.isArray(research.source_bindings) &&
      research.source_bindings.length > 0 &&
      research.source_bindings.every(
        (ref) =>
          typeof ref.path === "string" &&
          ref.path.trim() &&
          /^[a-f0-9]{64}$/.test(ref.sha256),
      ) &&
      Array.isArray(research.branches) &&
      research.branches.length > 0 &&
      research.branches.every(
        (branch) =>
          ["bear", "base", "bull"].includes(branch.scenario) &&
          [5, 10].includes(branch.fade_years) &&
          branch.result.action === "no_order" &&
          branch.result.formal_eligibility === false &&
          branch.result.economic_approval === false &&
          branch.result.price_admission === false &&
          Array.isArray(branch.result.blockers) &&
          Array.isArray(branch.result.rows) &&
          (branch.result.valuation.usable === true
            ? branch.result.status === "CONDITIONAL_RESEARCH_VALUATION" &&
              branch.result.blockers.length === 0 &&
              number(branch.result.valuation.per_share_cny) &&
              reconciled(branch.result.valuation.ri_ddm_residual_cny)
            : branch.result.status === "VALUATION_UNSUPPORTED" &&
              branch.result.valuation.per_share_cny === null),
      );
  } catch {
    valid = false;
  }
  if (!valid)
    return (
      <p role="status">有限优势现金研究来源或计算待核验，暂不展示金额。</p>
    );
  const baseline = research.branches.filter(
    (branch) => branch.branch === "BALANCED_NET_MAINTENANCE",
  );
  const challenges = research.branches.filter(
    (branch) => branch.branch !== "BALANCED_NET_MAINTENANCE",
  );
  return (
    <section
      aria-label="优势持续期与现金约束估值"
      style={{ minWidth: 0, overflowWrap: "anywhere" }}
    >
      <ProductContinuation research={research.product_continuation} />
      <h3>优势持续期与现金约束估值</h3>
      <p className="value-analysis-boundary">
        低置信度研究假说，未获经济、主估值或交易批准；不是买入价。
      </p>
      <p>
        前五年沿用产品经营假说，之后分别用五年、十年将总权益回报降至权益成本。不再假设永久维持当前超额盈利。
      </p>
      <p>
        估值基准 {research.basis_date}
        。以下为该基准、历史股数下的条件计算，不是今日公允价；原候选与操作资格未改变。
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>经营情景</th>
              <th>五年后衰减期</th>
              <th>每股条件值（元）</th>
            </tr>
          </thead>
          <tbody>
            {baseline.map((branch) => (
              <tr key={`${branch.scenario}-${branch.fade_years}`}>
                <td>{names[branch.scenario]}</td>
                <td>{branch.fade_years} 年</td>
                <td>
                  {branch.result.valuation.usable
                    ? readinessNumber(branch.result.valuation.per_share_cny)
                    : "不可估值"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        上表假设净维持投入与已计入利润的非现金扣减抵消，不代表无需维护；项目资金及基金调用另行扣除。母公司现金只作研究锚，不把集团折旧加回母公司。
      </p>
      <h4>哪些现金假设会使估值不成立</h4>
      {challenges.map((branch) => (
        <p key={`${branch.branch}-${branch.fade_years}`}>
          {branch.branch === "PERSISTENT_10_PERCENT_UNREMITTED"
            ? "持续一成盈利无法上划"
            : branch.branch === "EXTRA_NET_MAINTENANCE_2_PERCENT"
              ? "每年额外净投入：首年盈利的 2%"
              : "每年额外净投入：首年盈利的 5%"}
          ，衰减 {branch.fade_years} 年：
          {branch.result.valuation.usable
            ? "条件计算成立"
            : reasons(branch.result.blockers)}
          。
        </p>
      ))}
      <p>
        2%／5%是未校准现金挑战，不是实际资本开支或行业标准。终端账面定价、现金转化及合法全额分配仍是假说；算式相等不证明预测正确。
      </p>
      <details>
        <summary>逐年利润、分配与现金</summary>
        {baseline
          .filter((branch) => branch.scenario === "base")
          .map((branch) => (
            <div key={branch.fade_years} style={{ overflowX: "auto" }}>
              <h4>基准经营假说 · 衰减 {branch.fade_years} 年</h4>
              <table>
                <thead>
                  <tr>
                    <th>模型年</th>
                    <th>归母盈利假说</th>
                    <th>分配假说</th>
                    <th>期末现金代理</th>
                    <th>期末权益</th>
                  </tr>
                </thead>
                <tbody>
                  {branch.result.rows.map((row) => (
                    <tr key={row.year}>
                      <td>{row.year}</td>
                      <td>{readinessNumber(row.profit_cny)}</td>
                      <td>{readinessNumber(row.distribution_cny)}</td>
                      <td>{readinessNumber(row.closing_cash_cny)}</td>
                      <td>{readinessNumber(row.closing_book_cny)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </details>
    </section>
  );
}
