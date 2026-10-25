import { useState } from "react";
import type { IndustrialEarningsResearch as Research } from "../types/api";
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
  /^-?\d+(?:\.\d+)?$/.test(v) &&
  Number.isFinite(Number(v));

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
              Number(row.bridge_residual_cny) === 0 &&
              amount(
                row.change_from_historical_parent?.parent_profit_change_cny,
              ) &&
              amount(row.change_from_historical_parent?.residual_cny) &&
              Number(row.change_from_historical_parent.residual_cny) === 0 &&
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
  symbol,
}: {
  research?: Research;
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
