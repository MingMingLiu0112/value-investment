import type { FiniteAdvantageResearch as Research } from "../types/api";
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
          names[branch.scenario] &&
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
