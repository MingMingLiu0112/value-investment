import { Link } from "@umijs/max";
import { usePrivateState } from "../../hooks/usePrivateState";
import { sleeveLabel } from "../../components/PositionTable";
import { fillLink } from "../../utils/currentJudgment";
import {
  formatDecimal,
  formatMoney,
  formatUnitPrice,
} from "../../utils/format";
import { blockerText } from "../../utils/packet";
import type { DecisionItem } from "../../types/api";

export function CurrentHolding({ decision }: { decision: DecisionItem }) {
  const state = usePrivateState();
  const readable =
    ["CONNECTED", "BLOCKED_PRIVATE_INPUT"].includes(state.kind) &&
    state.portfolio?.status === "CONNECTED";
  const portfolio = readable ? state.portfolio : undefined;
  const position = portfolio?.positions.find(
    (row) => row.symbol === decision.symbol,
  );
  return (
    <section aria-label="当前个人持仓" style={{ overflowWrap: "anywhere" }}>
      <h4>当前个人持仓</h4>
      {!portfolio ? (
        <p>
          {state.label}。{state.detail} 当前是否持仓未知。
        </p>
      ) : (
        <>
          <p>
            台账时点：{portfolio.as_of ?? "未提供"}；可用现金{" "}
            {formatMoney(portfolio.cash_cny)} 元。
          </p>
          {position ? (
            <>
              <p>
                已确认持有 {position.quantity} 股；每股成本{" "}
                {formatUnitPrice(position.average_cost_cny)} 元；成本金额{" "}
                {formatMoney(position.cost_cny)} 元。市值{" "}
                {position.market_value_cny == null
                  ? "未核验"
                  : `${formatMoney(position.market_value_cny)} 元`}
                ；仓位占比{" "}
                {position.weight_pct == null
                  ? "未核验"
                  : `${formatDecimal(position.weight_pct)}%`}
                。
              </p>
              {position.sleeves.map((row) => (
                <p key={row.sleeve}>
                  {sleeveLabel(row.sleeve)}：{row.quantity} 股；可卖{" "}
                  {row.sellable_quantity} 股；下次可卖日{" "}
                  {row.next_sell_session ?? "以当前台账可卖数量为准"}。
                </p>
              ))}
            </>
          ) : (
            <p>当前已确认台账未记录该证券持仓；不代表账户外不存在持仓。</p>
          )}
          <p>
            {state.risk
              ? `个人风险复核：${state.risk.blockers.length ? state.risk.blockers.slice(0, 3).map(blockerText).join("；") : "以组合页完整风险核验为准，未据此授予操作数量"}`
              : "个人风险尚未读取成功，不能认定持仓风险已通过。"}
          </p>
          <p>
            持仓与可卖数量不是减仓或退出指令；新增风险、预算和正式数量需在仓位页独立复核。
          </p>
        </>
      )}
      <Link to={fillLink(decision)}>检查我的仓位</Link>
      {typeof state.retry === "function" && (
        <button type="button" onClick={state.retry} style={{ marginLeft: 12 }}>
          重新读取持仓
        </button>
      )}
    </section>
  );
}
