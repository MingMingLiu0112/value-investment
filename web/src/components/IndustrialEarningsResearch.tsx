import { useState } from "react";
import type { IndustrialEarningsResearch as Research } from "../types/api";
import type { FiscalEarningsResearch } from "../types/api";
import { isObservedResearchTimestamp } from "../utils/researchDraftText";
import { readinessNumber } from "../utils/strategyReadiness";

const names = { bear: "保守", base: "基准", bull: "乐观" };
const changes = [
  ["commercial_subtotal_change_cny", "商业小计变化"],
  ["asset_impairment_change_cny", "未来资产损失变化"],
  ["other_pbt_change_cny", "其他税前贡献变化"],
  ["income_tax_change_cny", "税负变化的影响"],
  ["signed_nci_change_cny", "少数股东归属变化的影响"],
] as const;
const columns = [
  ["revenue_cny", "收入"],
  ["commercial_subtotal_cny", "商业小计"],
  ["inventory_impairment_cny", "存货损失"],
  ["goodwill_impairment_cny", "商誉损失"],
  ["other_asset_impairment_cny", "其他资产损失"],
  ["other_pbt_cny", "其他税前贡献"],
  ["group_pbt_cny", "税前利润"],
  ["income_tax_cny", "所得税"],
  ["signed_nci_cny", "少数股东损益"],
  ["parent_profit_cny", "归母利润"],
] as const;
const sha = (s: unknown) => typeof s === "string" && /^[a-f0-9]{64}$/.test(s);
const amount = (v: unknown) =>
  typeof v === "string" &&
  /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(v) &&
  Number.isFinite(Number(v));
const zero = (v: unknown) =>
  typeof v === "string" && /^-?0+(?:\.0+)?(?:[eE][+-]?\d+)?$/.test(v);

function FiscalPeriodResearch({
  fiscal,
  symbol,
  scenario,
}: {
  fiscal?: FiscalEarningsResearch;
  symbol: string;
  scenario: keyof typeof names;
}) {
  if (!fiscal) return null;
  let valid = false;
  try {
    valid =
      fiscal.schema_version === "fiscal-earnings-research-v1" &&
      fiscal.symbol === symbol &&
      fiscal.currency === "CNY" &&
      fiscal.scope === "consolidated" &&
      fiscal.status === "SOURCE_BOUND_FISCAL_RESEARCH_NOT_APPROVED" &&
      fiscal.action === "no_order" &&
      fiscal.confidence === "LOW" &&
      [
        fiscal.formal_eligibility,
        fiscal.economic_approval,
        fiscal.price_admitted,
        fiscal.strategy_admitted,
        fiscal.primary_valuation_usable,
      ].every((v) => v === false) &&
      fiscal.dividend_capacity_cny === null &&
      fiscal.normalized_parent_profit_cny === null &&
      isObservedResearchTimestamp(fiscal.input_available_at) &&
      isObservedResearchTimestamp(fiscal.evaluated_at) &&
      Date.parse(fiscal.input_available_at) <=
        Date.parse(fiscal.evaluated_at) &&
      fiscal.accounting_comparability.perimeter ===
        "AS_REPORTED_NOT_CONSTANT_PERIMETER" &&
      !!fiscal.accounting_comparability.limitations.trim() &&
      fiscal.historical_h2_2025.classification ===
        "DERIVED_FY_MINUS_H1_FROM_SAME_BASIS" &&
      fiscal.source_bindings.length > 0 &&
      fiscal.source_bindings.every(
        (b) => typeof b.path === "string" && sha(b.sha256),
      ) &&
      fiscal.official_sources.length === 2 &&
      fiscal.official_sources.every(
        (b) =>
          /^https:\/\/static\.cninfo\.com\.cn\/finalpage\//.test(
            b.source_url,
          ) &&
          fiscal.source_bindings.some(
            (r) => r.path === b.path && r.sha256 === b.sha256,
          ),
      ) &&
      (Object.keys(names) as (keyof typeof names)[]).every((n) => {
        const s = fiscal.scenarios[n];
        return (
          s.stub.period_start === "2026-07-01" &&
          s.stub.period_end === "2026-12-31" &&
          s.stub.classification === "RESEARCH_ASSUMPTION" &&
          s.fy2026.period_start === "2026-01-01" &&
          s.fy2026.period_end === "2026-12-31" &&
          s.fy2026.classification === "MIXED_ACTUAL_H1_AND_RESEARCH_H2" &&
          amount(s.stub.lines.parent_profit) &&
          amount(s.fy2026.lines.parent_profit) &&
          s.rows.length === 5 &&
          s.rows.every(
            (r, i) =>
              r.year === i + 2027 &&
              r.currency === "CNY" &&
              r.period_start === `${r.year}-01-01` &&
              r.period_end === `${r.year}-12-31` &&
              r.classification === "RESEARCH_ASSUMPTION" &&
              [
                r.revenue_cny,
                r.group_pbt_cny,
                r.income_tax_cny,
                r.signed_nci_cny,
                r.parent_profit_cny,
              ].every(amount) &&
              zero(r.bridge_residual_cny),
          )
        );
      });
  } catch {
    valid = false;
  }
  if (!valid)
    return <p>财政年度研究未通过来源、日期或假设核验，暂不展示金额。</p>;
  const current = fiscal.scenarios[scenario];
  return (
    <section aria-label="财政年度盈利口径">
      <h5>从剩余半年连接财政年度</h5>
      <p>{fiscal.rationale}</p>
      <p>{fiscal.stub_rationale}</p>
      <p>
        当前{names[scenario]}情景：2026下半年归母假设{" "}
        {readinessNumber(current.stub.lines.parent_profit)} 元；2026全年归母研究{" "}
        {readinessNumber(current.fy2026.lines.parent_profit)}{" "}
        元（上半年事实＋下半年假设）。不是已披露全年业绩，不是股利金额。
      </p>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}>
        <table aria-label="财政年度归母研究（元）">
          <caption>完整财政年度条件研究（元人民币）</caption>
          <thead>
            <tr>
              <th>财政年</th>
              <th>收入</th>
              <th>税前利润</th>
              <th>所得税</th>
              <th>少数股东损益</th>
              <th>归母利润</th>
            </tr>
          </thead>
          <tbody>
            {current.rows.map((r) => (
              <tr key={r.year}>
                <th>{r.year}</th>
                {[
                  r.revenue_cny,
                  r.group_pbt_cny,
                  r.income_tax_cny,
                  r.signed_nci_cny,
                  r.parent_profit_cny,
                ].map((v, i) => (
                  <td key={i}>{readinessNumber(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>{fiscal.accounting_comparability.limitations}</p>
      <p>
        集团归母利润不等于母公司现金、可分配利润或买入资格；财政年度对齐不自动延长股东回报政策。
      </p>
    </section>
  );
}

function verified(r: Research, symbol: string): boolean {
  try {
    return (
      r.schema_version === "industrial-earnings-research-v1" &&
      r.symbol === symbol &&
      r.status === "CONDITIONAL_EARNINGS_RESEARCH_NOT_APPROVED" &&
      r.action === "no_order" &&
      r.context_scope ===
        "INDEPENDENT_SOURCE_BOUND_RESEARCH_NOT_CURRENT_VALUATION" &&
      r.confidence === "LOW" &&
      r.formal_eligibility === false &&
      r.primary_valuation_usable === false &&
      r.price_admitted === false &&
      r.strategy_admitted === false &&
      r.economic_approval === false &&
      r.normalized_parent_profit_cny === null &&
      Number.isFinite(Date.parse(r.input_available_at)) &&
      Number.isFinite(Date.parse(r.evaluated_at)) &&
      Date.parse(r.input_available_at) <= Date.parse(r.evaluated_at) &&
      sha(r.policy_binding.sha256) &&
      Array.isArray(r.source_bindings) &&
      r.source_bindings.every(
        (b) => typeof b.path === "string" && sha(b.sha256),
      ) &&
      r.source_bindings.some(
        (b) =>
          b.path === r.policy_binding.path &&
          b.sha256 === r.policy_binding.sha256,
      ) &&
      Array.isArray(r.official_sources) &&
      r.official_sources.length === 2 &&
      r.official_sources.every(
        (b) =>
          /^https:\/\/static\.cninfo\.com\.cn\/finalpage\//.test(
            b.source_url,
          ) &&
          r.source_bindings.some(
            (ref) => ref.path === b.path && ref.sha256 === b.sha256,
          ),
      ) &&
      [r.rationale, r.tax_convention].every(
        (s) => typeof s === "string" && !!s.trim(),
      ) &&
      [r.counter_evidence, r.thesis_breakers, r.unknowns].every(
        (a) =>
          Array.isArray(a) &&
          a.length > 0 &&
          a.every((s) => typeof s === "string" && !!s.trim()),
      ) &&
      (Object.keys(names) as (keyof typeof names)[]).every((key) => {
        const scenario = r.scenarios[key];
        return (
          typeof scenario.rationale === "string" &&
          !!scenario.rationale.trim() &&
          Array.isArray(scenario.rows) &&
          scenario.rows.length === 5 &&
          scenario.rows.every(
            (row, i) =>
              row.year === i + 1 &&
              row.currency === "CNY" &&
              amount(row.bridge_residual_cny) &&
              zero(row.bridge_residual_cny) &&
              amount(
                row.change_from_historical_parent?.parent_profit_change_cny,
              ) &&
              amount(row.change_from_historical_parent?.residual_cny) &&
              zero(row.change_from_historical_parent.residual_cny) &&
              changes.every(([field]) =>
                amount(row.change_from_historical_parent[field]),
              ) &&
              columns.every(([field]) => amount(row[field])),
          )
        );
      })
    );
  } catch {
    return false;
  }
}

export function IndustrialEarningsResearch({
  research,
  fiscal,
  symbol,
}: {
  research?: Research;
  fiscal?: FiscalEarningsResearch;
  symbol: string;
}) {
  const [scenario, setScenario] = useState<keyof typeof names>("base");
  if (!research) return null;
  if (!verified(research, symbol))
    return (
      <p>前瞻经营研究尚未通过来源或假设核验，暂不展示金额；原投资状态不变。</p>
    );
  const current = research.scenarios[scenario];
  return (
    <section
      aria-label="前瞻经营与归母研究"
      style={{ minWidth: 0, overflowWrap: "anywhere" }}
    >
      <h4>未来利润依赖什么</h4>
      <p>
        低置信度条件研究，不是官方预测、已确定的正常化利润或获批估值。不产生买卖价、股数或分红承诺。
      </p>
      <p>
        财务基准 {research.financial_basis}；假设形成{" "}
        {research.input_available_at}。本次原件重验 {research.evaluated_at}
        ，不冒充历史时点可得性。
      </p>
      <p>{research.rationale}</p>
      <label>
        经营研究情景{" "}
        <select
          aria-label="前瞻经营情景"
          value={scenario}
          onChange={(e) => setScenario(e.target.value as keyof typeof names)}
        >
          {Object.entries(names).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <p>{current.rationale}</p>
      <FiscalPeriodResearch
        fiscal={fiscal}
        symbol={symbol}
        scenario={scenario}
      />
      <p>
        商业小计为收入减营业成本、税金及销售、管理、研发费用；不是经常性归母利润或可分配现金。
      </p>
      <h5>第一年相对历史 TTM 归母利润为什么变化</h5>
      <p>
        条件变化{" "}
        {readinessNumber(
          current.rows[0].change_from_historical_parent
            .parent_profit_change_cny,
        )}{" "}
        元。以下正值表示增加、负值表示减少；比较基准是历史归母利润，不是扣非或正常化利润。
      </p>
      <p>
        其中商业小计变化{" "}
        {readinessNumber(
          current.rows[0].change_from_historical_parent
            .commercial_subtotal_change_cny,
        )}{" "}
        元；资产损失变化贡献{" "}
        {readinessNumber(
          current.rows[0].change_from_historical_parent
            .asset_impairment_change_cny,
        )}{" "}
        元。两者不是同一种改善，税负及归属变化也会抵消或增加归母结果。
      </p>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}>
        <table aria-label="归母变化来源（元）">
          <caption>相对历史 TTM 归母的变化来源（元）</caption>
          <thead>
            <tr>
              <th>贡献</th>
              <th>第一年</th>
              <th>第五年</th>
            </tr>
          </thead>
          <tbody>
            {changes.map(([field, label]) => (
              <tr key={field}>
                <th>{label}</th>
                {[0, 4].map((i) => (
                  <td key={i}>
                    {readinessNumber(
                      current.rows[i].change_from_historical_parent[field],
                    )}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <th>归母净变化</th>
              {[0, 4].map((i) => (
                <td key={i}>
                  {readinessNumber(
                    current.rows[i].change_from_historical_parent
                      .parent_profit_change_cny,
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}>
        <table aria-label="逐年经营与利润归属（元）">
          <caption>逐年经营与利润归属（元人民币，研究假设）</caption>
          <thead>
            <tr>
              <th>预测年</th>
              {columns.map(([key, label]) => (
                <th key={key}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {current.rows.map((row) => (
              <tr key={row.year}>
                <td>{row.year}</td>
                {columns.map(([field]) => (
                  <td key={field}>{readinessNumber(row[field])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        归母利润＝税前利润－所得税－有正负号的少数股东损益。未来资产损失减少不等于主营增长；不把历史损失直接加回归母，也不恢复减记权益。
      </p>
      <p>{research.tax_convention}</p>
      <details>
        <summary>反证、失效条件与原件</summary>
        <h5>反证</h5>
        <ul>
          {research.counter_evidence.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <h5>重开研究的条件</h5>
        <ul>
          {research.thesis_breakers.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <h5>仍未知</h5>
        <ul>
          {research.unknowns.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <ul>
          {research.official_sources.map((source) => (
            <li key={source.source_id}>
              <a href={source.source_url} target="_blank" rel="noreferrer">
                {source.source_id}
              </a>{" "}
              · {source.sha256}
            </li>
          ))}
        </ul>
        <p>研究假设与实现指纹</p>
        <ul>
          {research.source_bindings.map((ref) => (
            <li key={ref.path}>
              {ref.path} · {ref.sha256}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
