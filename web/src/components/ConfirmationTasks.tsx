import { Link } from "@umijs/max";
import { Button } from "antd";
import { useCallback } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { DecisionItem } from "../types/api";
import { fillLink, judgmentState } from "../utils/currentJudgment";

const readableStatuses = new Set([
  "REGISTERED",
  "NOT_REGISTERED",
  "REVIEW_REQUIRED",
]);

function ConfirmationFailure({ retry }: { retry: () => void }) {
  return (
    <li role="alert">
      <span>确认状态读取失败，待确认事项暂未核验。</span>
      <Button type="link" size="small" onClick={retry}>
        重试
      </Button>
    </li>
  );
}

function PersonalPolicyTask({ item }: { item: DecisionItem }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const symbol = item.symbol!;
      const status = await api.valuePolicyStatus(symbol);
      if (status.status === "REGISTERED")
        return { ...status, hasPolicyDraft: false };
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}`,
        { signal, cache: "no-store" },
      );
      const review = await response.json().catch(() => null);
      if (
        response.status === 409 &&
        review?.action === "no_order" &&
        review?.status === "REVIEW_UNAVAILABLE"
      ) {
        // No current review basis means there is no policy draft to offer;
        // the authenticated policy status itself was read successfully.
        return { ...status, hasPolicyDraft: false };
      }
      if (!response.ok) throw new Error("确认状态读取失败");
      if (review?.action !== "no_order") throw new Error("确认状态读取失败");
      const draft = review.draft;
      return {
        ...status,
        hasPolicyDraft:
          draft != null &&
          typeof draft === "object" &&
          !Array.isArray(draft) &&
          draft.basis?.symbol === symbol &&
          Array.isArray(draft.rules),
      };
    },
    [item.symbol],
  );
  const result = useApi(load);
  if (result.loading) return null;
  if (result.error || !result.data || !readableStatuses.has(result.data.status))
    return <ConfirmationFailure retry={result.retry} />;
  const policyPending =
    result.data.status !== "REGISTERED" && result.data.hasPolicyDraft === true;
  const privatePlan =
    result.data.status === "REGISTERED"
      ? result.data.conditional_plan
      : undefined;
  const blockers = [
    ...(item.blockers ?? []),
    ...(item.price_action_plan?.blockers ?? []),
    ...(Array.isArray(privatePlan?.blockers) ? privatePlan.blockers : []),
    ...(Array.isArray(privatePlan?.formal_eligibility_blockers)
      ? privatePlan.formal_eligibility_blockers
      : []),
  ];
  const reviewPending = blockers.some((code) =>
    /G3|valuation_not_approved|human_research_approval/i.test(String(code)),
  );
  if (!policyPending && !reviewPending) return null;
  return (
    <li>
      <span>{item.name ?? item.symbol}：</span>
      {policyPending && (
        <>
          <Link
            to={`/decisions/${encodeURIComponent(item.id)}#personal-value-policy`}
          >
            {result.data.status === "REVIEW_REQUIRED"
              ? "重新复核本人价格政策"
              : "选择并确认本人价格政策"}
          </Link>
          <p>
            核对动作比例、有效期和失效条件后预览并确认；登记不批准估值，也不授予交易资格。
          </p>
        </>
      )}
      {reviewPending && (
        <>
          <Link
            to={`/decisions/${encodeURIComponent(item.id)}#value-review-handoff`}
          >
            准备外部 G3 估值审核交接材料
          </Link>
          <p>
            仍需有权外部审核人及已登记签署身份；本人价格政策登记不替代估值审核。
          </p>
        </>
      )}
    </li>
  );
}

function HotspotReviewTask({ item }: { item: DecisionItem }) {
  if (!item.symbol || !item.price_action_plan) return null;
  const plan = item.price_action_plan;
  return (
    <li>
      <span>
        {item.name ?? item.symbol}：热点条件复核（{judgmentState(item)}）
      </span>
      <p>
        核对日线趋势、60 分钟入场观察价、15
        分钟辅助条件和结构失效价；条件未满足时继续观察，不把 WATCH 当作买入。
      </p>
      <Link to={`/decisions/${encodeURIComponent(item.id)}`}>
        查看热点操作条件
      </Link>{" "}
      <Link to={fillLink(item)}>进入风险试算与成交登记</Link>
      <p>
        当前参考价 {plan.current_reference_price ?? "未核验"}；入场观察价{" "}
        {plan.entry_trigger_price ?? "未形成"}；失效价{" "}
        {plan.invalidation_price ?? "未形成"}。
      </p>
    </li>
  );
}

export function ConfirmationTasks({
  decisions,
  hotspotDecisions = [],
  connected,
  privateReadable = true,
}: {
  decisions: DecisionItem[];
  hotspotDecisions?: DecisionItem[];
  connected: boolean;
  privateReadable?: boolean;
}) {
  const companies = decisions.filter(
    (item) =>
      item.symbol && ["CORE_VALUE", "value"].includes(item.strategy ?? ""),
  );
  return (
    <section
      id="confirmations"
      aria-label="需要我确认"
      style={{ marginTop: 20, scrollMarginTop: 20 }}
    >
      <h2>需要我确认</h2>
      {!connected && (
        <p>
          账户尚未连接。
          <Link to="/portfolio">连接本人账户，核对投资政策与持仓</Link>
        </p>
      )}
      <ul>
        {privateReadable &&
          companies.map((item) => (
            <PersonalPolicyTask key={item.id} item={item} />
          ))}
        {hotspotDecisions
          .filter((item) =>
            ["hotspot", "HOTSPOT_SATELLITE"].includes(item.strategy ?? ""),
          )
          .map((item) => (
            <HotspotReviewTask key={`hotspot-${item.id}`} item={item} />
          ))}
      </ul>
    </section>
  );
}
