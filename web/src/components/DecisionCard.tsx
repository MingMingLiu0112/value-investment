import { ArrowRightOutlined } from "@ant-design/icons";
import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import { strategyText } from "../utils/codes";
import {
  judgmentGroup,
  judgmentState,
  judgmentReason,
  hotspotOpportunityQuality,
} from "../utils/currentJudgment";
import { firstResearchText } from "../utils/opportunityView";
import { formatDecimal } from "../utils/format";

export function DecisionCard({ item }: { item: DecisionItem }) {
  const plan = item.price_action_plan;
  const quality = hotspotOpportunityQuality(item);
  const hotspot = ["hotspot", "HOTSPOT_SATELLITE"].includes(
    item.strategy ?? "",
  );
  const valuation =
    plan?.conditional_valuation_range ?? item.research?.valuation ?? plan;
  const trend =
    (
      {
        UPTREND: "上升",
        DOWNTREND: "下降，谨慎观察",
        RANGE: "震荡",
        UNKNOWN: "未确认",
      } as Record<string, string>
    )[plan?.price_behavior?.daily_trend ?? ""] ?? "未确认";
  const risk =
    firstResearchText(
      plan?.counter ?? plan?.counter_evidence ?? item.counter_evidence,
    ) ?? "风险证据尚不完整";
  return (
    <article
      className="decision-compact"
      aria-label={`${item.name || item.symbol} ${strategyText(item.strategy)}`}
    >
      <div className="decision-compact-top">
        <div className="decision-company">
          <strong>{item.name || item.symbol}</strong>
          <span>{item.symbol}</span>
        </div>
        <span
          className={
            judgmentGroup(item) === 0
              ? "decision-state decision-state-formal"
              : "decision-state"
          }
        >
          {judgmentState(item)}
        </span>
      </div>
      <div className="decision-meta">
        {hotspot
          ? `${plan?.daily_selection?.industry ?? "行业未核验"} · 行情 ${plan?.market_trade_date ?? "未核验"}`
          : `价值研究 ${plan?.valuation_date ?? item.as_of ?? "日期未核验"}`}
      </div>
      {quality && (
        <p aria-label="机会质量分类">
          {quality.code ? `${quality.code} · ` : ""}
          {quality.label}：{quality.reason}
        </p>
      )}
      {hotspot && plan?.independent_admission && (
        <p aria-label="独立热点准入">
          {plan.risk_review_eligible
            ? "独立策略条件已通过，可继续个人风险复核；尚无交易许可。"
            : plan.independent_admission.review_status === "MISSING"
              ? "独立热点策略尚未完成授权与证据核验；当前仅观察。"
              : "独立热点条件尚未全部通过；当前仅观察。"}
        </p>
      )}
      <dl className="decision-price-grid">
        <div>
          <dt>核验参考价</dt>
          <dd>
            {plan?.current_reference_price ?? plan?.reference_close ?? "未核验"}
          </dd>
        </div>
        <div>
          <dt>{hotspot ? "入场观察价" : "条件性建仓价"}</dt>
          <dd>{plan?.entry_trigger_price ?? "尚无获准价位"}</dd>
        </div>
        {hotspot ? (
          <>
            <div>
              <dt>结构失效价</dt>
              <dd>{plan?.invalidation_price ?? "未形成"}</dd>
            </div>
            <div>
              <dt>日线趋势</dt>
              <dd>{trend}</dd>
            </div>
          </>
        ) : (
          <>
            <div>
              <dt>研究估值 Bear / Base / Bull</dt>
              <dd>
                {[valuation?.bear, valuation?.base, valuation?.bull]
                  .map((v) => (v == null ? "未形成" : formatDecimal(v)))
                  .join(" / ")}
              </dd>
            </div>
            <div>
              <dt>现价与估值比较</dt>
              <dd>
                {plan?.price_comparison_eligible === true
                  ? "具备比较资格"
                  : "尚未获准，情景不是买价"}
              </dd>
            </div>
          </>
        )}
      </dl>
      {!hotspot && <p className="decision-reason">{judgmentReason(item)}</p>}
      <p className="decision-risk">主要风险：{risk}</p>
      {!hotspot && (
        <details>
          <summary>下次复核事项</summary>
          <p>
            {firstResearchText(item.next_events ?? plan?.next_observation) ??
              "复核研究有效性、重大事件及价格政策；尚未通过时继续观察。"}
          </p>
        </details>
      )}
      <Link
        className="decision-link"
        to={`/decisions/${encodeURIComponent(item.id)}${hotspot ? "?independent_hotspot=true" : ""}`}
      >
        查看操作条件 <ArrowRightOutlined aria-hidden />
      </Link>
    </article>
  );
}
