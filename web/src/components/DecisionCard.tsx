import { ArrowRightOutlined } from "@ant-design/icons";
import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import { describeCode, strategyText } from "../utils/codes";
import { firstResearchText, publicBlockerText } from "../utils/opportunityView";

/** Compact public research card. The API, not this component, decides eligibility. */
export function DecisionCard({ item }: { item: DecisionItem }) {
  const formal = item.status === "FORMALLY_ADMITTED_REVIEW";
  const reason =
    item.reason ||
    item.why_selected ||
    item.candidate_explanation ||
    "尚无可核验的关注理由";
  const trigger = firstResearchText(item.next_events) || "触发条件仍待研究";
  const risk =
    firstResearchText(item.counter_evidence) ||
    firstResearchText(item.thesis_breakers) ||
    (item.blockers?.length
      ? publicBlockerText(item.blockers[0]) || "研究准入条件尚待核验"
      : "主要风险仍待核验");
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
          {formal
            ? describeCode(item.candidate_action || item.status)
            : describeCode(item.status)}
        </span>
      </div>
      <div className="decision-meta">
        {strategyText(item.strategy)} · 数据 {item.as_of || "日期待核验"} ·
        价格尚未获本判断准入
      </div>
      <p className="decision-reason">{reason}</p>
      <div className="decision-compact-foot">
        <span>触发：{trigger}</span>
        <span>风险：{risk}</span>
      </div>
      <Link
        className="decision-link"
        to={`/decisions/${encodeURIComponent(item.id)}`}
      >
        查看操作逻辑 <ArrowRightOutlined aria-hidden />
      </Link>
    </article>
  );
}
