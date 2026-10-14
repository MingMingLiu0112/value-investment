import { ArrowRightOutlined } from "@ant-design/icons";
import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import { strategyText } from "../utils/codes";
import {
  judgmentGroup,
  judgmentReason,
  judgmentState,
  missingPricePolicies,
} from "../utils/currentJudgment";
import { firstResearchText } from "../utils/opportunityView";
import { decisionEligibility } from "../utils/decisionEligibility";
import { formatDecimal } from "../utils/format";

/** Compact public research card. The API, not this component, decides eligibility. */
export function DecisionCard({ item }: { item: DecisionItem }) {
  const formal = judgmentGroup(item) === 0;
  const eligibility = decisionEligibility(item);
  const reason =
    item.why_selected ||
    item.price_action_plan?.watch_reason ||
    judgmentReason(item) ||
    item.reason ||
    item.candidate_explanation ||
    "尚无可核验的关注理由";
  return (
    <article
      className="decision-compact"
      aria-label={`${item.name || item.symbol} ${strategyText(item.strategy)}`}
    >
      <div className="decision-compact-top">
        <div className="decision-company">
          <strong>{item.name || item.symbol || "名称待核验"}</strong>
          <span>{item.symbol || "代码待核验"}</span>
        </div>
        <span
          className={
            formal ? "decision-state decision-state-formal" : "decision-state"
          }
        >
          {judgmentState(item)}
        </span>
      </div>
      <div className="decision-meta">
        {strategyText(item.strategy)} · 数据{" "}
        {item.price_action_plan?.market_trade_date ||
          item.as_of ||
          "日期待核验"}
      </div>
      <p className="decision-reason">{reason}</p>
      {item.price_action_plan?.price_behavior && (
        <div className="decision-meta">
          结构质量：
          {(
            {
              UNFAVORABLE_DAILY_TREND: "日线下降，谨慎观察",
              INSUFFICIENT_UPPER_SPACE: "上方空间不足以覆盖价格风险",
              UNKNOWN: "证据不足",
              RESEARCH_ONLY: "仅研究观察，尚未获准",
            } as Record<string, string>
          )[item.price_action_plan.price_behavior.observation_quality] ??
            "待核验"}
        </div>
      )}
      {missingPricePolicies(item) && (
        <div className="decision-meta">{missingPricePolicies(item)}</div>
      )}
      {item.price_action_plan?.daily_selection && (
        <div className="decision-meta">
          当日观察序位 {item.price_action_plan.daily_selection.rank ?? "未提供"}{" "}
          · {item.price_action_plan.daily_selection.industry ?? "行业未核验"} ·
          行业相对涨跌{" "}
          {formatDecimal(
            item.price_action_plan.daily_selection
              .industry_relative_strength_percent,
          )}{" "}
          个百分点（覆盖样本）
        </div>
      )}
      <p className="decision-reason">
        支持：
        {firstResearchText(
          item.price_action_plan?.support ??
            item.price_action_plan?.supporting_facts ??
            item.support,
        ) ?? "尚未提供"}
        <br />
        反证：
        {firstResearchText(
          item.price_action_plan?.counter ??
            item.price_action_plan?.counter_evidence ??
            item.counter_evidence,
        ) ?? "尚未提供，不能视为无风险"}
      </p>
      <div className="decision-meta">
        研究意图：{eligibility.intent} · 证券资格：{eligibility.formal} ·
        个人资格：{eligibility.portfolio}
      </div>
      <div className="decision-compact-foot">
        <span>
          参考价：
          {item.price_action_plan?.current_reference_price ??
            item.price_action_plan?.reference_close ??
            "未获核验"}{" "}
          / 触发价：
          {item.price_action_plan?.entry_trigger_price ?? "尚无有效价位"}
        </span>
        <span>
          失效：
          {item.price_action_plan?.invalidation_price ??
            firstResearchText(item.thesis_breakers) ??
            "条件尚待核验"}
        </span>
      </div>
      <Link
        className="decision-link"
        to={`/decisions/${encodeURIComponent(item.id)}`}
      >
        查看详细依据 <ArrowRightOutlined aria-hidden />
      </Link>
    </article>
  );
}
