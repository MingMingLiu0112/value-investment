import { useEffect, useState } from "react";
import type {
  PolicyStatus,
  PolicyRegistration,
  ValuePolicyTransport,
} from "../services/valuePolicy";
import { RegisteredPolicySummary } from "./ValuePolicyEditor";
import { Link } from "@umijs/max";

export function PersonalInvestmentPlan({
  symbol,
  registered,
}: {
  symbol: string;
  registered: PolicyRegistration;
}) {
  const plan = registered.conditional_plan;
  const params = new URLSearchParams({ symbol, strategy: "value" });
  if (typeof plan.research_version === "string")
    params.set("research_version", plan.research_version);
  return (
    <>
      <h4>我的投资计划</h4>
      <p>
        适用研究版本：{String(plan.research_version ?? "未提供")}；模型版本：
        {String(plan.model_version ?? "未提供")}；计划时点：
        {String(plan.decision_as_of ?? "未提供")}。
      </p>
      <p>
        条件观察：
        {(["entry", "add", "reduce", "exit"] as const)
          .map((action, index) => {
            const condition = plan[`${action}_condition`];
            const triggered =
              condition && typeof condition === "object"
                ? (condition as Record<string, unknown>).triggered
                : undefined;
            return `${["建仓", "加仓", "减仓", "退出"][index]}${triggered === true ? "已满足价格条件，仍须独立核验资格" : triggered === false ? "未满足价格条件" : "尚未核验"}`;
          })
          .join("；")}
        。
      </p>
      <p>本人政策已登记；正式研究与个人风险资格仍独立核验。</p>
      <details>
        <summary>查看本人已登记价格、完整条件与限制</summary>
        <RegisteredPolicySummary registered={registered} />
      </details>
      <p>
        私人草案算术价、研究适用条件价、个人风险资格与实际成交分别核验；政策登记不代表已经成交。
      </p>
      <Link to={`/portfolio?${params.toString()}`}>检查我的仓位</Link>
      {" · "}
      <Link to="/history">查看实际成交与判断记录</Link>
    </>
  );
}

export function PrivateValueDecision({
  symbol,
  transport,
  revision = 0,
}: {
  symbol: string;
  transport: ValuePolicyTransport;
  revision?: number;
}) {
  const [state, setState] = useState<{
    symbol: string;
    revision: number;
    status?: PolicyStatus;
    error?: boolean;
  }>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const refresh = () => {
      setState(undefined);
      setRetry((value) => value + 1);
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);
  useEffect(() => {
    let active = true;
    setState(undefined);
    transport
      .status(symbol)
      .then((status) => {
        if (active) setState({ symbol, revision, status });
      })
      .catch(() => {
        if (active) setState({ symbol, revision, error: true });
      });
    return () => {
      active = false;
    };
  }, [symbol, transport, revision, retry]);
  const current =
    state?.symbol === symbol && state.revision === revision ? state : undefined;
  return (
    <section
      aria-label="本人当前价格政策"
      id="personal-value-policy"
      style={{ overflowWrap: "anywhere" }}
    >
      <h3>本人当前价格政策</h3>
      {!current ? (
        <p role="status">正在核验本人政策与当前条件…</p>
      ) : current.error ? (
        <p role="alert">私人政策未能读取，请使用已授权会话重新核验。</p>
      ) : current.status?.status === "REGISTERED" ? (
        <PersonalInvestmentPlan symbol={symbol} registered={current.status} />
      ) : (
        <p role="status">
          {current.status?.status === "REVIEW_REQUIRED"
            ? "本人已登记政策需要重新复核，当前不沿用旧计划。"
            : "本人尚未登记价格政策。"}
        </p>
      )}
      <button
        type="button"
        onClick={() => {
          setState(undefined);
          setRetry((value) => value + 1);
        }}
      >
        重新读取本人政策
      </button>
    </section>
  );
}
