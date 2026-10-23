import type {
  DecisionItem,
  ValueResearchAnalysis as Analysis,
} from "../types/api";
import { readinessNumber, readinessStrategy } from "../utils/strategyReadiness";
import { normalizeEvidenceLines } from "../utils/researchDetail";
import {
  researchAssumptionName,
  researchSentence,
} from "../utils/researchDraftText";
import "./value-research-analysis.css";
import { AccountingBridgeReview } from "./AccountingBridgeReview";

const scenarios = { bear: "保守 Bear", base: "基准 Base", bull: "乐观 Bull" };

function inputLabel(key: string): string {
  return key === "forecast_roes"
    ? "预测 ROE 路径（各模型期）"
    : researchAssumptionName(key);
}

function inputValue(value: unknown): string {
  return Array.isArray(value)
    ? value.map(readinessNumber).join(" / ")
    : readinessNumber(value);
}

function SensitivityRows({
  rows,
}: {
  rows: NonNullable<Analysis["sensitivity"]>["rows"];
}) {
  return rows.map((row, index) => (
    <div
      className="value-analysis-sensitivity"
      key={`${row.field_path}-${index}`}
    >
      <h4>{inputLabel(row.assumption_name)}</h4>
      <p>依据：{row.basis ? researchSentence(row.basis) : "未提供"}</p>
      <p>
        理由与限制：{row.rationale ? researchSentence(row.rationale) : "未提供"}
      </p>
      <dl className="value-analysis-grid">
        {row.points?.slice(0, 3).map((point, pointIndex) => (
          <div key={`${point.bound}-${pointIndex}`}>
            <dt>
              {scenarios[point.bound as keyof typeof scenarios] || "其他端点"} ·
              输入 {readinessNumber(point.input_value)}
            </dt>
            <dd>
              {point.status === "ARITHMETIC_COMPLETE" ? (
                <>
                  条件计算值 {readinessNumber(point.per_share_value)}
                  ；较基准变化 {readinessNumber(point.delta_from_base)}
                </>
              ) : (
                "该端点未形成可核验结果"
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="value-analysis-muted">
        模型字段 {row.field_path} · 证据引用{" "}
        {row.evidence_refs
          ?.map((ref) => ref.id)
          .filter(Boolean)
          .join("、") || "未提供"}
      </p>
    </div>
  ));
}

export function ValueResearchAnalysis({
  decision,
}: {
  decision: DecisionItem;
}) {
  const analysis = decision.price_action_plan?.research_analysis;
  if (!analysis || readinessStrategy(decision.strategy) !== "CORE_VALUE")
    return null;
  const verified =
    decision.price_action_plan?.action === "no_order" &&
    analysis.schema_version === "value-research-analysis-v1" &&
    analysis.symbol === decision.symbol &&
    analysis.action === "no_order" &&
    analysis.status === "CONDITIONAL_ANALYSIS_VERIFIED" &&
    analysis.arithmetic_complete === true &&
    analysis.economic_assumptions_reviewed === false &&
    analysis.action_admitted === false &&
    analysis.strategy_admitted === false &&
    analysis.price_comparison_eligible === false &&
    Array.isArray(analysis.scenarios) &&
    Array.isArray(analysis.source_bindings) &&
    analysis.source_bindings.length > 0 &&
    analysis.source_bindings.every(
      (binding) =>
        typeof binding?.path === "string" &&
        binding.path.trim() &&
        /^[a-f0-9]{64}$/.test(binding.sha256),
    );
  if (!verified)
    return (
      <p role="status">条件研究分析的来源或重算尚未核验，暂不展示计算结果。</p>
    );
  const sensitivity = Array.isArray(analysis.sensitivity?.rows)
    ? analysis.sensitivity.rows
    : [];
  const priority = [
    "cost_of_equity",
    "terminal_roe",
    "terminal_growth",
    "retention",
  ];
  const ordered = [...sensitivity].sort((a, b) => {
    const rank = (key: string) =>
      priority.includes(key) ? priority.indexOf(key) : priority.length;
    return rank(a.field_path) - rank(b.field_path);
  });
  const counter = normalizeEvidenceLines(analysis.counter_evidence);
  return (
    <details
      className="value-research-analysis"
      aria-label="条件研究分析"
      id="conditional-research-analysis"
    >
      <summary>条件研究分析 · 已完成计算，经济假设未复核</summary>
      <p className="value-analysis-boundary">
        仅条件研究结果，未获操作准入，不是精确合理价。数值保留 2–4
        位小数；不生成买卖价或账户数量。
      </p>
      <p>
        估值基准日 {analysis.valuation_date || "未提供"} · 研究截至{" "}
        {analysis.research_as_of || "未提供"} · 计算时间{" "}
        {analysis.computed_at || "未提供"}
      </p>
      <h3>三情景与实际模型输入</h3>
      {analysis.economic_assessment?.schema_version ===
        "value-economic-assessment-v1" &&
        analysis.economic_assessment.symbol === decision.symbol &&
        analysis.economic_assessment.action === "no_order" &&
        analysis.economic_assessment.primary_valuation_usable === false && (
          <section aria-label="经济性与现金回报核查">
            <h4>经济性与现金回报核查</h4>
            <p>
              {analysis.economic_assessment.model_applicability?.assessment ===
              "STRESS_ONLY"
                ? "当前属于短优势期压力估值，不能充当中性主估值。"
                : "延续经营情景仍需验证竞争优势与衰减，不等于获批主估值。"}
            </p>
            <p>
              历史扣非归母 TTM 利润：
              {readinessNumber(
                analysis.economic_assessment.earnings
                  ?.historical_ex_nonrecurring_ttm_cny,
              )}{" "}
              元。历史利润不等于正常化盈利。
            </p>
            <p>
              正常化盈利和可持续分红能力尚未建立，不据此生成买入价或分红承诺。
            </p>
            <AccountingBridgeReview
              review={analysis.economic_assessment.accounting_bridge_review}
              symbol={decision.symbol}
              descriptor={analysis.input_descriptor_sha256}
            />
            {!!analysis.economic_assessment.historical_cash_observations
              ?.length && (
              <details>
                <summary>已重算的历史现金桥</summary>
                <ul>
                  {analysis.economic_assessment.historical_cash_observations.map(
                    (row) => (
                      <li key={row.id}>
                        {row.id}：{readinessNumber(row.recomputed_value)}{" "}
                        元；仅历史观察
                      </li>
                    ),
                  )}
                </ul>
              </details>
            )}
          </section>
        )}
      <div className="value-analysis-grid">
        {(["bear", "base", "bull"] as const).map((key) => {
          const matches = analysis.scenarios.filter(
            (row) => row?.scenario === key,
          );
          const scenario = matches.length === 1 ? matches[0] : undefined;
          return (
            <section key={key}>
              <h4>{scenarios[key]} · 条件结果</h4>
              <p className="value-analysis-number">
                {readinessNumber(scenario?.per_share_value)}
              </p>
              <details>
                <summary>本情景实际输入</summary>
                <dl className="value-analysis-inputs">
                  {scenario?.inputs &&
                    Object.entries(scenario.inputs).map(([name, value]) => (
                      <div key={name}>
                        <dt>
                          {inputLabel(name)}{" "}
                          <span className="value-analysis-muted">({name})</span>
                        </dt>
                        <dd>{inputValue(value)}</dd>
                      </div>
                    ))}
                </dl>
                {!scenario?.inputs && <p>输入未提供，不能补造假设。</p>}
              </details>
            </section>
          );
        })}
      </div>
      <h3>单因素敏感性</h3>
      <p>
        只改变一项已登记端点，其余输入固定在
        Base；不代表联合情景或获准经济预测。
      </p>
      {ordered.length ? (
        <SensitivityRows rows={ordered.slice(0, 3)} />
      ) : (
        <p>尚无可展示的敏感性结果。</p>
      )}
      {ordered.length > 3 && (
        <details>
          <summary>其余敏感性（{ordered.length - 3} 项）</summary>
          <SensitivityRows rows={ordered.slice(3)} />
        </details>
      )}
      <h3>反证与模型适用性缺口</h3>
      {counter.length ? (
        <ul>
          {counter.map((row, index) => (
            <li key={index}>
              {researchSentence(row.text)}
              {row.evidenceRefs.length > 0 &&
                ` · 证据 ${row.evidenceRefs.join("、")}`}
            </li>
          ))}
        </ul>
      ) : (
        <p>反证未提供，不代表没有风险。</p>
      )}
      {analysis.model_applicability?.blockers?.length ? (
        <ul>
          {analysis.model_applicability.blockers.map((blocker, index) => (
            <li key={index}>{researchSentence(blocker)}</li>
          ))}
        </ul>
      ) : (
        <p>模型适用性缺口清单未提供，不能认定已通过。</p>
      )}
      <details>
        <summary>来源绑定（{analysis.source_bindings.length} 项）</summary>
        <p>后端已核验源文件与消费输入；哈希匹配不批准经济解释。</p>
        <ul>
          {analysis.source_bindings.map((binding, index) => (
            <li key={index}>
              <span>{binding.path}</span>
              <code>SHA-256 {binding.sha256}</code>
            </li>
          ))}
        </ul>
      </details>
      <a href="#value-review-handoff">查看对应版本的估值复核材料</a>
    </details>
  );
}
