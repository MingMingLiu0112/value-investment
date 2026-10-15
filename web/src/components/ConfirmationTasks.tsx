import { Link } from "@umijs/max";
import { useCallback } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { DecisionItem } from "../types/api";

function PersonalPolicyTask({ item }: { item: DecisionItem }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const status = await api.valuePolicyStatus(item.symbol!);
      if (status.status === "REGISTERED")
        return { ...status, hasPolicyDraft: false };
      try {
        const response = await fetch(
          `/api/v1/value-policy-review/${encodeURIComponent(item.symbol!)}`,
          { signal, cache: "no-store" },
        );
        const review = await response.json();
        const draft = review?.draft;
        return {
          ...status,
          hasPolicyDraft:
            response.ok &&
            review?.action === "no_order" &&
            draft != null &&
            typeof draft === "object" &&
            !Array.isArray(draft) &&
            draft.basis?.symbol === item.symbol &&
            Array.isArray(draft.rules),
        };
      } catch {
        return { ...status, hasPolicyDraft: false };
      }
    },
    [item.symbol],
  );
  const result = useApi(load);
  if (
    result.loading ||
    result.error ||
    !result.data ||
    !["REGISTERED", "NOT_REGISTERED", "REVIEW_REQUIRED"].includes(
      result.data.status,
    )
  )
    return null;
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

export function ConfirmationTasks({
  decisions,
  connected,
}: {
  decisions: DecisionItem[];
  connected: boolean;
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
        {companies.map((item) => (
          <PersonalPolicyTask key={item.id} item={item} />
        ))}
      </ul>
    </section>
  );
}
