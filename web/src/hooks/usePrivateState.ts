import { useEffect, useState } from "react";
import { api, ApiError, hadSessionToken } from "../services/api";
import type { PortfolioResponse, RiskResponse } from "../types/api";
import { privateStateFrom } from "../utils/privateState";
import type { PrivateStateView } from "../utils/privateState";

export interface PrivateStateHandle extends PrivateStateView {
  retry: () => void;
  /** 仅在已解锁且台账可读时存在；供页面渲染持仓事实，不做任何推算。 */
  portfolio?: PortfolioResponse;
  risk?: RiskResponse;
}

/**
 * TL9 MVP-3：每日页只调用一次私人接口，把 LOCKED / NOT_CONNECTED /
 * BLOCKED_PRIVATE_INPUT / CONNECTED 映射成一个共用状态给所有私人区块。
 */
export function usePrivateState(): PrivateStateHandle {
  const [portfolio, setPortfolio] = useState<PortfolioResponse>();
  const [risk, setRisk] = useState<RiskResponse>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [hadSession, setHadSession] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // Capture before the read: forgetSession() may run during a 401 retry.
    setHadSession(hadSessionToken());
    setLoading(true);
    setError(undefined);
    (async () => {
      let nextPortfolio: PortfolioResponse | undefined;
      try {
        nextPortfolio = await api.portfolio(controller.signal);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setPortfolio(undefined);
        setRisk(undefined);
        setError(cause);
        setLoading(false);
        return;
      }
      let nextRisk: RiskResponse | undefined;
      if (nextPortfolio.status === "CONNECTED") {
        try {
          nextRisk = await api.risk(controller.signal);
        } catch (cause) {
          if (controller.signal.aborted) return;
          if (cause instanceof ApiError && cause.status === 401) {
            // 会话在读风险时失效：整体回到锁定态，不展示半截私人结果。
            setPortfolio(undefined);
            setRisk(undefined);
            setError(cause);
            setLoading(false);
            return;
          }
          // 台账可读但风险复核读取失败：仍按台账事实展示，风险缺口 fail-closed。
          nextRisk = undefined;
        }
      }
      if (controller.signal.aborted) return;
      setPortfolio(nextPortfolio);
      setRisk(nextRisk);
      setError(undefined);
      setLoading(false);
    })();
    return () => controller.abort();
  }, [revision]);

  const view = privateStateFrom({
    portfolio,
    risk,
    error,
    loading,
    hadSession,
  });
  return {
    ...view,
    retry: () => setRevision((value) => value + 1),
    portfolio,
    risk,
  };
}
