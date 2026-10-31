import type { ParentCashResearch as Research } from "../types/api";
import { readinessNumber } from "../utils/strategyReadiness";
import { isObservedResearchTimestamp as observedTime } from "../utils/researchDraftText";

const fields = [
  ["opening_cash_and_equivalents_cny", "期初现金等价物"],
  ["cfo_cny", "经营现金净额"],
  ["cfi_cny", "投资现金净额"],
  ["cff_cny", "筹资现金净额"],
  ["fx_cny", "汇率影响"],
  ["closing_cash_and_equivalents_cny", "期末现金等价物"],
] as const;
const amount = (v: unknown) =>
  typeof v === "string" &&
  /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(v) &&
  Number.isFinite(Number(v));
const hash = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const zero = (v: unknown) =>
  typeof v === "string" && /^-?0+(?:\.0+)?(?:[eE][+-]?\d+)?$/.test(v);
function verified(r: Research, symbol: string): boolean {
  try {
    return (
      r.schema_version === "parent-cash-research-v1" &&
      r.symbol === symbol &&
      r.status === "SOURCE_REPLAYED_HISTORICAL_PARENT_CASH" &&
      r.action === "no_order" &&
      [
        r.formal_eligibility,
        r.economic_approval,
        r.primary_valuation_usable,
        r.price_admitted,
        r.strategy_admitted,
      ].every((v) => v === false) &&
      r.distribution_capacity_status === "UNKNOWN" &&
      r.future_distributable_cash_cny === null &&
      r.ordinary_dividends_paid_cny === null &&
      r.upstream_dividends_received_cny === null &&
      r.parent_restricted_cash_cny === null &&
      r.continuity_status === "PASS" &&
      r.historical_cash_reconciliation_status === "PASS" &&
      observedTime(r.evaluated_at) &&
      r.source_bindings.length > 0 &&
      r.source_bindings.every(
        (b) => typeof b.path === "string" && hash(b.sha256),
      ) &&
      r.historical_statements.length === 2 &&
      ["FY2025", "H12026"].every((period) =>
        r.historical_statements.some((s) => s.periods[0] === period),
      ) &&
      r.historical_statements.every(
        (s) =>
          s.symbol === symbol &&
          s.statement_scope === "listed_parent_only" &&
          ["FY2025|FY2024", "H12026|H12025"].includes(s.periods.join("|")) &&
          /^https:\/\/static\.cninfo\.com\.cn\/finalpage\//.test(
            s.source_binding.source_url,
          ) &&
          r.source_bindings.some(
            (b) =>
              b.path === s.source_binding.path &&
              b.sha256 === s.source_binding.sha256,
          ) &&
          s.balances.length === 2 &&
          s.balances.every(
            (b, i) =>
              b.period === s.periods[i] &&
              fields.every(([key]) => amount(b[key])) &&
              amount(b.reported_net_change_cny) &&
              amount(b.mixed_distribution_interest_paid_cny) &&
              amount(b.cash_residual_cny) &&
              zero(b.cash_residual_cny) &&
              amount(b.movement_residual_cny) &&
              zero(b.movement_residual_cny),
          ),
      )
    );
  } catch {
    return false;
  }
}

export function ParentCashResearch({
  research,
  symbol,
}: {
  research?: Research;
  symbol: string;
}) {
  if (!research) return null;
  if (!verified(research, symbol))
    return (
      <p>母公司现金原件或对账未通过核验，暂不展示金额；分红能力仍未知。</p>
    );
  const rows = research.historical_statements.map((s) => s.balances[0]);
  return (
    <section aria-label="母公司现金与分红约束">
      <h4>利润能否成为股东现金</h4>
      <p>
        以下为母公司法人历史现金，不是合并自由现金流，也不是未来可分配金额。半年现金流不年化；分红能力仍未知。
      </p>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}>
        <table aria-label="母公司历史现金对账（元）">
          <caption>母公司历史现金对账（元人民币）</caption>
          <thead>
            <tr>
              <th>期间</th>
              {fields.map(([key, label]) => (
                <th key={key}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.period}>
                <th>{row.period}</th>
                {fields.map(([key]) => (
                  <td key={key}>{readinessNumber(row[key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        经营、投资、筹资和汇率影响与期末现金精确对账，但不证明现金可分配。分配股利、利润或偿付利息的合并支付行不能全部算作普通股分红；投资收益收款不能全部算作子公司上划。
      </p>
      <p>
        未来维持投入、再融资、受限资金及法定分配约束尚需研究，不能用历史现金余额承诺分红或提高买入资格。
      </p>
      <details>
        <summary>现金原件与重验日期</summary>
        <p>重验：{research.evaluated_at}；不是历史时点可得性证明。</p>
        {research.historical_statements.map((s) => (
          <p key={s.periods[0]}>
            <a
              href={s.source_binding.source_url}
              target="_blank"
              rel="noreferrer"
            >
              {s.periods[0]} 原件
            </a>{" "}
            · SHA-256 {s.source_binding.sha256}
          </p>
        ))}
      </details>
    </section>
  );
}
