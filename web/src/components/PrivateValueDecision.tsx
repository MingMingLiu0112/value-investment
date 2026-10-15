import { useEffect, useState } from "react";
import type {
  PolicyStatus,
  ValuePolicyTransport,
} from "../services/valuePolicy";
import { RegisteredPolicySummary } from "./ValuePolicyEditor";

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
        <RegisteredPolicySummary registered={current.status} />
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
