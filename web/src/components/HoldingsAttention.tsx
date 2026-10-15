import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import type { PrivateStateHandle } from "../hooks/usePrivateState";
import { blockerText } from "../utils/packet";
import { formatMoney } from "../utils/format";

export function HoldingsAttention({
  state,
  decisions,
  decisionsVerified = false,
}: {
  state: PrivateStateHandle;
  decisions: DecisionItem[];
  decisionsVerified?: boolean;
}) {
  const portfolio = state.portfolio;
  const connected = portfolio?.status === "CONNECTED";
  const held = new Set(portfolio?.positions.map((row) => row.symbol) ?? []);
  const changes = decisions.filter(
    (row) =>
      decisionsVerified &&
      held.has(row.symbol ?? "") &&
      (["REDUCE", "EXIT", "EXIT_REVIEW"].includes(
        row.action_intent ?? row.price_action_plan?.action_intent ?? "",
      ) ||
        (row.price_action_plan?.action === "no_order" &&
          ![
            "STALE",
            "EXPIRED",
            "BLOCKED",
            "HISTORICAL_OBSERVATION_NOT_ADMITTED",
          ].includes(row.price_action_plan.signal_state) &&
          ["hotspot", "HOTSPOT_SATELLITE"].includes(row.strategy ?? "") &&
          (row.price_action_plan.conditional_action_rules?.REDUCE?.observed ===
            true ||
            row.price_action_plan.conditional_action_rules?.EXIT?.observed ===
              true)) ||
        row.price_action_plan?.signal_state === "TRIGGER_REJECTED"),
  );
  return (
    <section className="opportunity-holdings" aria-label="持仓今日复核">
      <div>
        <h2>我的持仓今天需要关注</h2>
        {connected ? (
          <>
            <p>
              可用现金 {formatMoney(portfolio.cash_cny)} 元；总权益{" "}
              {formatMoney(portfolio.total_equity_cny)} 元；已记录{" "}
              {portfolio.positions.length} 只证券。
            </p>
            {changes.map((row) => (
              <p key={row.id}>
                <Link to={`/decisions/${encodeURIComponent(row.id)}`}>
                  {row.name ?? row.symbol}
                </Link>
                ：已出现策略退出或减仓复核事项，需结合可卖数量和个人风险检查。
              </p>
            ))}
            {!!state.risk?.blockers.length && (
              <p>
                风险复核未通过：
                {state.risk.blockers.slice(0, 3).map(blockerText).join("；")}
                。缺少研究数据不等于应当卖出。
              </p>
            )}
            {!state.risk && <p>风险尚未读取，不能认定当前持仓正常。</p>}
            {!decisionsVerified && (
              <p>
                策略复核未知：公开判断正在读取、读取失败或版本不可核验，不能认定没有退出事项。
              </p>
            )}
            {decisionsVerified && !changes.length && state.risk && (
              <p>
                当前已读取的策略中未发现新增退出复核；未覆盖证券和风险缺口仍需检查。
              </p>
            )}
          </>
        ) : (
          <>
            <p>{state.label}。尚未读取持仓时，不能判断你的仓位或风险。</p>
            <p>
              公开研究可直接查看。运行本机启动命令后，通过终端提供的一次性授权链接进入私人页面；首次进入可初始化账户、填写投资政策并逐项确认。
            </p>
          </>
        )}
      </div>
      <Link to="/portfolio">
        {connected ? "查看持仓与风险" : "连接我的持仓"}
      </Link>
    </section>
  );
}
