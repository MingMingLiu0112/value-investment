import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import { Link } from "@umijs/max";
import type {
  DailyEvaluationItem,
  DecisionItem,
  CurrentPricePlan,
  PacketCompanyStatus,
  PlanCondition,
  StrategyReadiness as ReadinessContract,
} from "../types/api";
import {
  readinessActionUrl,
  readinessCurrentStage,
  readinessDetailUrl,
  readinessGapLabel,
  readinessNumber,
  readinessStatusText,
  readinessSteps,
  readinessStrategy,
  verifiedReadiness,
  type ReadinessStrategy,
} from "../utils/strategyReadiness";
import "./strategy-readiness.css";
import { fillLink } from "../utils/currentJudgment";

function conditionPrice(
  condition?: PlanCondition | null,
): string | null | undefined {
  return typeof condition === "object" && condition && !Array.isArray(condition)
    ? condition.price
    : undefined;
}

function ConditionalResults({
  readiness,
  plan,
  strategy,
}: {
  readiness: ReadinessContract;
  plan?: CurrentPricePlan | null;
  strategy: ReadinessStrategy;
}) {
  const valuation = readiness.conditional_valuation;
  const quote = readiness.price_snapshot;
  const isValue = strategy === "CORE_VALUE";
  const valueAvailable =
    isValue && valuation?.scope === "UNAPPROVED_RESEARCH_ONLY";
  const planAvailable = plan?.action === "no_order";
  return (
    <section className="readiness-results" aria-label="已形成的条件结果">
      <h4>已形成的条件结果</h4>
      <p className="readiness-boundary">
        <InfoCircleOutlined aria-hidden /> 研究 / 观察，未获操作批准。 数值保留
        2–4 位小数，不是精确合理价，也不代表个人可操作。
      </p>
      {isValue && (
        <>
          <h5>条件估值 · 未获批准</h5>
          {valueAvailable ? (
            <>
              <dl className="readiness-numbers">
                {(["bear", "base", "bull"] as const).map((scenario) => (
                  <div key={scenario}>
                    <dt>
                      {
                        {
                          bear: "保守 Bear",
                          base: "基准 Base",
                          bull: "乐观 Bull",
                        }[scenario]
                      }
                    </dt>
                    <dd>{readinessNumber(valuation[scenario])}</dd>
                  </div>
                ))}
              </dl>
              <p>
                币种 {valuation.currency || "未提供"} · 研究日{" "}
                {valuation.as_of || "未提供"}。Base 不等于已验证合理价值。
              </p>
            </>
          ) : (
            <p>尚无可展示的条件估值；不补算、不推定模型已运行。</p>
          )}
        </>
      )}
      <h5>参考行情 · 仅供展示</h5>
      <p>
        {quote?.usage === "DISPLAY_ONLY"
          ? `${readinessNumber(quote.value)} · ${quote.date || "日期未提供"}`
          : "尚无用途已核验的行情快照"}
        。行情展示不代表报价与计划当前有效。
      </p>
      <h5>条件操作价 · 观察用，未获批准</h5>
      {planAvailable ? (
        <>
          <dl className="readiness-numbers">
            <div>
              <dt>{isValue ? "条件建仓参考" : "入场观察参考"}</dt>
              <dd>
                {readinessNumber(
                  plan.entry_trigger_price ??
                    conditionPrice(plan.entry_condition) ??
                    plan.conditional_action_rules?.OPEN?.price,
                )}
              </dd>
            </div>
            <div>
              <dt>条件加仓参考</dt>
              <dd>
                {readinessNumber(
                  conditionPrice(plan.add_condition) ??
                    plan.conditional_action_rules?.ADD?.price,
                )}
              </dd>
            </div>
            <div>
              <dt>条件减仓参考</dt>
              <dd>
                {readinessNumber(
                  conditionPrice(plan.reduce_condition) ??
                    plan.conditional_action_rules?.REDUCE?.price,
                )}
              </dd>
            </div>
            <div>
              <dt>条件退出参考</dt>
              <dd>
                {readinessNumber(
                  conditionPrice(plan.exit_condition) ??
                    plan.conditional_action_rules?.EXIT?.price,
                )}
              </dd>
            </div>
            <div>
              <dt>失效参考</dt>
              <dd>{readinessNumber(plan.invalidation_price)}</dd>
            </div>
          </dl>
          <p>
            计划行情日 {plan.market_trade_date || "未提供"} · 有效期{" "}
            {plan.expires_after_session || "未提供，需重新核验"}。
            价格到达不替代计划、策略验证、组合容量和人工复核。
            加减仓及退出还需核对实际持仓和可卖数量。
          </p>
        </>
      ) : (
        <p>尚无可核验的条件操作价。</p>
      )}
    </section>
  );
}

export function StrategyReadinessPanel({
  item,
  decision,
  company,
}: {
  item: DailyEvaluationItem;
  decision?: DecisionItem;
  company?: PacketCompanyStatus;
}) {
  const strategy = readinessStrategy(item.strategy);
  const readiness = verifiedReadiness(item.readiness, strategy);
  const detailUrl = readinessDetailUrl(item, decision);
  if (!strategy || !readiness)
    return (
      <section className="strategy-readiness" aria-label="策略就绪阶段">
        <p role="status">
          {item.readiness
            ? "就绪信息无法核验；保留原判断，不提供阶段通过结论。"
            : "尚未提供就绪信息，各阶段未核验；原判断与处理入口保留。"}
        </p>
        <Link to={detailUrl}>查看现有研究与操作条件</Link>
      </section>
    );
  const steps = readinessSteps(readiness, strategy);
  const pending = steps.filter((step) => step.status !== "READY");
  const gap = readiness.primary_gap;
  const gapUrl = readinessActionUrl(gap?.url);
  const plan =
    decision?.symbol === item.symbol &&
    readinessStrategy(decision.strategy) === strategy
      ? decision.price_action_plan
      : undefined;
  const portfolioUrl =
    decision?.symbol === item.symbol &&
    readinessStrategy(decision.strategy) === strategy
      ? fillLink(decision)
      : `/portfolio?${new URLSearchParams({ symbol: item.symbol, strategy: strategy === "CORE_VALUE" ? "value" : "hotspot" })}`;
  return (
    <section className="strategy-readiness" aria-label="策略就绪阶段">
      <div className="readiness-heading">
        <h3>当前阶段：{readinessCurrentStage(readiness, strategy)}</h3>
        <span>
          {steps.length - pending.length} / {steps.length} 项已核验
        </span>
      </div>
      <p className="readiness-boundary">
        阶段就绪不授予操作资格；仍需本人复核，不自动下单。
      </p>
      {strategy === "CORE_VALUE" && (
        <p aria-label="估值状态边界">
          估值状态：
          {company?.symbol === item.symbol &&
          company.valuation_status?.code === "NOT_READY"
            ? "尚未就绪（NOT_READY），不代表模型从未运行。"
            : company?.symbol === item.symbol &&
                company.valuation_status?.code === "UNDER_REVIEW"
              ? "正在复核（UNDER_REVIEW），已有情景也不代表获准。"
              : "未提供明确的就绪或复核状态。"}
          {readiness.primary_gap?.category === "MODEL_NOT_RUN"
            ? "模型运行：明确未运行。"
            : "模型是否运行需独立记录，不能由缺少估值或审核状态推断。"}
        </p>
      )}
      {strategy === "HOTSPOT_SATELLITE" && (
        <p>
          {readiness.independent_of_value_valuation === true
            ? "热点独立核验价格结构、回放与风险，价值估值不是前置。"
            : "热点独立性尚未核验；不能据此认定策略准入。"}
        </p>
      )}
      <ol className="readiness-steps">
        {steps.map((step) => (
          <li key={step.key} data-status={step.status}>
            <div className="readiness-step-head">
              {step.status === "READY" ? (
                <CheckCircleOutlined aria-hidden />
              ) : step.status === "NOT_EVALUATED" ? (
                <InfoCircleOutlined aria-hidden />
              ) : (
                <ClockCircleOutlined aria-hidden />
              )}
              <strong>{step.label}</strong>
              <span>{readinessStatusText[step.status]}</span>
            </div>
            <p>{step.reason}</p>
          </li>
        ))}
      </ol>
      <section className="readiness-next" aria-label="主要未完成项">
        <h4>{readinessGapLabel(gap?.category)}</h4>
        <p>{gap?.summary || "主要待办未提供，不能认定缺口已经清除。"}</p>
        {gap?.next_action && <p>下一步：{gap.next_action}</p>}
        {gapUrl ? (
          <Link to={gapUrl}>
            {gap?.next_action || "查看处理入口"}{" "}
            <ArrowRightOutlined aria-hidden />
          </Link>
        ) : (
          <Link to={detailUrl}>查看现有研究与操作条件</Link>
        )}
        {!!pending.length && (
          <p className="readiness-muted">
            仍待核验：{pending.map((step) => step.label).join("、")}。
          </p>
        )}
      </section>
      <ConditionalResults
        readiness={readiness}
        plan={plan}
        strategy={strategy}
      />
      <nav className="readiness-links" aria-label="现有处理入口">
        <Link to={detailUrl}>
          查看完整操作条件 <ArrowRightOutlined aria-hidden />
        </Link>
        {strategy === "CORE_VALUE" ? (
          <Link to={`${detailUrl}#value-review-handoff`}>查看估值复核材料</Link>
        ) : (
          <Link to="/history">查看回放与策略证据</Link>
        )}
        <Link to={`${portfolioUrl}#portfolio-sizing`}>核验真实组合容量</Link>
        <Link to="/system">查看数据状态</Link>
      </nav>
    </section>
  );
}

export function DailyStrategyReadiness({
  items,
  decisions,
  companyStatuses,
}: {
  items: DailyEvaluationItem[];
  decisions: DecisionItem[];
  companyStatuses?: Record<string, PacketCompanyStatus>;
}) {
  if (!items.some((item) => item.readiness != null)) return null;
  const strategies = [
    {
      key: "CORE_VALUE",
      label: "价值投资",
      path: "初筛 → 公司研究 → 估值验证 → 报价与计划 → 组合容量 → 人工复核",
    },
    {
      key: "HOTSPOT_SATELLITE",
      label: "热点波段",
      path: "初筛 → 价格结构 → 回放验证 → 报价与计划 → 组合容量 → 人工复核",
    },
  ] as const;
  return (
    <section className="daily-readiness" aria-label="每日双策略流程">
      <h2>两条策略，分别推进</h2>
      <p>初筛入选仅是研究起点；已算出结果、验证通过与个人操作资格分别核验。</p>
      <div className="readiness-strategies">
        {strategies.map((strategy) => {
          const rows = items.filter(
            (item) => readinessStrategy(item.strategy) === strategy.key,
          );
          return (
            <details key={strategy.key} open className="readiness-strategy">
              <summary>
                <strong>{strategy.label}</strong>
                <span>已发布记录 {rows.length} 只</span>
              </summary>
              <p className="readiness-path">{strategy.path}</p>
              {rows.length === 0 && (
                <p>本策略尚无就绪记录，不能判断没有机会。</p>
              )}
              {rows.map((item) => {
                const readiness = verifiedReadiness(
                  item.readiness,
                  strategy.key,
                );
                const decision = decisions.find(
                  (row) =>
                    row.symbol === item.symbol &&
                    readinessStrategy(row.strategy) === strategy.key,
                );
                return (
                  <details
                    className="readiness-security"
                    key={`${strategy.key}-${item.symbol}`}
                  >
                    <summary>
                      <strong>
                        {item.company_name || decision?.name || item.symbol} ·{" "}
                        {item.symbol}
                      </strong>
                      <span>
                        {readinessCurrentStage(readiness, strategy.key)}
                      </span>
                      <span className="readiness-muted">
                        {item.decision_action === "UNASSESSABLE"
                          ? "无法评价"
                          : item.decision_action === "NO_TRADE"
                            ? "已评价，暂不新建仓"
                            : "原判断未核验"}
                        {readiness?.primary_gap &&
                          ` · ${readinessGapLabel(readiness.primary_gap.category)}`}
                      </span>
                    </summary>
                    <p>{item.decision_reason}</p>
                    <StrategyReadinessPanel
                      item={item}
                      decision={decision}
                      company={companyStatuses?.[item.symbol]}
                    />
                  </details>
                );
              })}
            </details>
          );
        })}
      </div>
    </section>
  );
}
