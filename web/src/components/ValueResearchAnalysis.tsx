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
import { PublicJointCapitalReview } from "./JointCapitalReview";
import { SourceNativeCashReview } from "./SourceNativeCashReview";
import { OperatingEarningsBridge } from "./OperatingEarningsBridge";
import { IndustrialEarningsResearch } from "./IndustrialEarningsResearch";
import { ParentCashResearch } from "./ParentCashResearch";
import { FiniteAdvantageResearch } from "./FiniteAdvantageResearch";

const scenarios = { bear: "保守 Bear", base: "基准 Base", bull: "乐观 Bull" };

function inputLabel(key: string, v4 = false): string {
  return key === "forecast_roes"
    ? "预测 ROE 路径（各模型期）"
    : v4 && key === "terminal_growth"
      ? "账面留存诊断比例（不参与 v4 尾值定价）"
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
  const analysis =
    decision.research_analysis ?? decision.price_action_plan?.research_analysis;
  if (!analysis || readinessStrategy(decision.strategy) !== "CORE_VALUE")
    return null;
  const verified =
    (decision.price_action_plan?.action === "no_order" ||
      (!decision.price_action_plan && decision.action === "no_order")) &&
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
      <>
        <p role="status">
          {analysis.blockers?.some((reason) =>
            reason.includes("implementation drift"),
          )
            ? "旧估值候选绑定的是旧程序版本，当前不能重放，暂不展示计算结果。"
            : "条件研究分析的来源或重算尚未核验，暂不展示计算结果。"}
        </p>
        {analysis.status === "SOURCE_OR_REPLAY_UNAVAILABLE" &&
          decision.price_action_plan?.action === "no_order" &&
          analysis.symbol === decision.symbol && (
            <>
              <OperatingEarningsBridge analysis={analysis} />
              <FiniteAdvantageResearch
                research={analysis.finite_advantage_research}
                symbol={decision.symbol}
              />
              <IndustrialEarningsResearch
                research={analysis.industrial_earnings_research}
                fiscal={analysis.fiscal_earnings_research}
                symbol={decision.symbol}
              />
              <ParentCashResearch
                research={analysis.parent_cash_research}
                symbol={decision.symbol}
              />
            </>
          )}
      </>
    );
  const sensitivity = Array.isArray(analysis.sensitivity?.rows)
    ? analysis.sensitivity.rows
    : [];
  const v4 =
    analysis.valuation?.model_version === "residual-income-equity-path-v4";
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
  const cash = analysis.economic_assessment?.cash_conversion_diagnostic;
  const cashSources = analysis.economic_assessment?.source_bindings;
  const candidate = analysis.review_binding?.candidate_binding;
  const cashVerified =
    cash?.status === "SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE" &&
    cash.scope ===
      "HISTORICAL_FINANCIAL_FLOW_DIAGNOSTIC_NOT_NORMALIZED_OR_DISTRIBUTABLE" &&
    cash.symbol === decision.symbol &&
    cash.action === "no_order" &&
    /^[a-f0-9]{64}$/.test(analysis.input_descriptor_sha256 ?? "") &&
    cash.input_descriptor_sha256 === analysis.input_descriptor_sha256 &&
    !!candidate &&
    cash.candidate_binding?.path === candidate.path &&
    cash.candidate_binding?.sha256 === candidate.sha256 &&
    cash.primary_valuation_usable === false &&
    cash.normalized_parent_profit_cny === null &&
    cash.g3_changed === false &&
    cash.approval_changed === false &&
    cash.price_admitted === false &&
    cash.strategy_admitted === false &&
    cash.historical_pit_admitted === false &&
    Array.isArray(cashSources) &&
    Array.isArray(cash.source_bindings) &&
    Array.isArray(cash.execution_bindings) &&
    !!cash.source_bindings?.length &&
    !!cash.execution_bindings?.length &&
    [...cash.source_bindings, ...cash.execution_bindings, candidate].every(
      (ref) =>
        !!ref &&
        typeof ref.path === "string" &&
        !!ref.path.trim() &&
        /^[a-f0-9]{64}$/.test(ref.sha256) &&
        cashSources.some(
          (bound) => bound?.path === ref.path && bound?.sha256 === ref.sha256,
        ),
    ) &&
    Array.isArray(cash.rows) &&
    cash.rows?.length === 2 &&
    cash.rows.every(
      (row) =>
        !!row &&
        Number.isInteger(row.physical_page) &&
        row.physical_page > 0 &&
        cash.source_bindings?.some(
          (ref) =>
            ref.path === row.source_binding?.path &&
            ref.sha256 === row.source_binding?.sha256,
        ),
    ) &&
    !!cash.calculation &&
    typeof cash.counter_evidence === "string" &&
    !!cash.counter_evidence.trim() &&
    [
      cash.calculation.reported_cfo_change_cny,
      cash.calculation.identified_outflow_direction_contribution_cny,
    ].every(
      (value) =>
        typeof value === "string" &&
        value.trim() !== "" &&
        Number.isFinite(Number(value)),
    ) &&
    (cash.calculation.contribution_fraction_of_reported_change === null ||
      (typeof cash.calculation.contribution_fraction_of_reported_change ===
        "string" &&
        cash.calculation.contribution_fraction_of_reported_change.trim() !==
          "" &&
        Number.isFinite(
          Number(cash.calculation.contribution_fraction_of_reported_change),
        )));
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
      <FiniteAdvantageResearch
        research={analysis.finite_advantage_research}
        symbol={decision.symbol}
      />
      <IndustrialEarningsResearch
        research={analysis.industrial_earnings_research}
        fiscal={analysis.fiscal_earnings_research}
        symbol={decision.symbol ?? ""}
      />
      <ParentCashResearch
        research={analysis.parent_cash_research}
        symbol={decision.symbol ?? ""}
      />
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
                : "延续经营情景的盈利、资本成本与终端假设仍待复核，不等于获批主估值。"}
            </p>
            {analysis.economic_assessment.model_applicability?.reasons?.map(
              (reason) => (
                <p key={reason}>{reason}</p>
              ),
            )}
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
            <OperatingEarningsBridge analysis={analysis} />
            {cashVerified && cash?.calculation && (
              <p>
                现金流反证：合并经营现金流同比变化{" "}
                {readinessNumber(cash.calculation.reported_cfo_change_cny)} 元；
                其中已识别的央行及同业资金流出项方向变化贡献{" "}
                {readinessNumber(
                  cash.calculation
                    .identified_outflow_direction_contribution_cny,
                )}{" "}
                元
                {cash.calculation.contribution_fraction_of_reported_change !==
                  null &&
                  `（占同比变动 ${new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 }).format(Number(cash.calculation.contribution_fraction_of_reported_change))}）`}
                。{cash.counter_evidence} 原件第{" "}
                {Array.from(
                  new Set(cash.rows.map((row) => row.physical_page)),
                ).join("、")}{" "}
                页。 这不是正常化现金或可持续分红结论，不改变估值及交易资格。
              </p>
            )}
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
                        {row.id.endsWith("_cash_residual") &&
                        row.evidence?.length ? (
                          <details>
                            <summary>母公司现金余额与流量原文</summary>
                            <p>
                              对账成立不等于自由现金或可持续分红；融资、维护投入与可动用性仍需核验。
                            </p>
                            <ul>
                              {row.evidence.map((fact) => (
                                <li key={`${fact.period}-${fact.label}`}>
                                  {fact.period} · {fact.label}：
                                  {readinessNumber(fact.value)} 元； 原件第{" "}
                                  {fact.physical_page} 页；SHA-256 {fact.sha256}
                                  {fact.source_url && (
                                    <a
                                      href={fact.source_url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      原始出处
                                    </a>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : null}
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
                          {inputLabel(name, v4)}{" "}
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
      <PublicJointCapitalReview analysis={analysis} symbol={analysis.symbol} />
      <SourceNativeCashReview analysis={analysis} symbol={decision.symbol!} />
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
