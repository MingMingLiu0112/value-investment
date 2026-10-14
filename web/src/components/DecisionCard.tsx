import { ArrowRightOutlined } from "@ant-design/icons";
import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import { strategyText } from "../utils/codes";
import {
  judgmentGroup,
  judgmentReason,
  judgmentState,
} from "../utils/currentJudgment";
import { firstResearchText } from "../utils/opportunityView";

/** Compact public research card. The API, not this component, decides eligibility. */
export function DecisionCard({ item }: { item: DecisionItem }) {
  const formal = judgmentGroup(item) === 0;
  const reason =
    judgmentReason(item) ||
    item.reason ||
    item.why_selected ||
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
      <div className="decision-compact-foot">
        <span>
          参考价：
          {item.price_action_plan?.current_reference_price ?? "未获核验"} /
          触发价：
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
