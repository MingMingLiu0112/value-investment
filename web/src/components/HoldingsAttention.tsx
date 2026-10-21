import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import type { PrivateStateHandle } from "../hooks/usePrivateState";
import { blockerText } from "../utils/packet";
import { formatMoney } from "../utils/format";
import { useState } from "react";
import { Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api } from "../services/api";

export function HoldingsAttention({
  state,
  decisions,
  decisionsVerified = false,
}: {
  state: PrivateStateHandle;
  decisions: DecisionItem[];
  decisionsVerified?: boolean;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<string>();
  const portfolio = state.portfolio;
  const connected = portfolio?.status === "CONNECTED";
  const held = new Set(portfolio?.positions.map((row) => row.symbol) ?? []);
  const heldInStrategy = (row: DecisionItem) => {
    const strategy = ["hotspot", "HOTSPOT_SATELLITE"].includes(
      row.strategy ?? "",
    )
      ? "HOTSPOT_SATELLITE"
      : ["value", "CORE_VALUE"].includes(row.strategy ?? "")
        ? "CORE_VALUE"
        : undefined;
    return (
      !!strategy &&
      !!portfolio?.positions.some(
        (position) =>
          position.symbol === row.symbol &&
          position.sleeves?.some(
            (sleeve) =>
              sleeve.sleeve === strategy && Number(sleeve.quantity) > 0,
          ),
      )
    );
  };
  async function refreshHeld() {
    if (!connected || portfolio?.revision === undefined || refreshing) return;
    setRefreshing(true);
    setRefreshResult(undefined);
    try {
      const symbols = Array.from(held);
      let missing = 0;
      for (let offset = 0; offset < symbols.length; offset += 5) {
        const result = await api.refreshHeldContinuity({
          expected_revision: portfolio.revision,
          symbols: symbols.slice(offset, offset + 5),
        });
        missing += result.failures.length;
      }
      setRefreshResult(
        missing
          ? `已完成刷新，${missing} 只证券当前证据未通过；保留持仓并显示风险缺口。`
          : "持仓证据已刷新，正在重新核对当前风险。不会自动下单。",
      );
      state.retry();
    } catch {
      setRefreshResult("刷新未完成，请重新读取持仓后重试；原持仓事实未修改。");
      state.retry();
    } finally {
      setRefreshing(false);
    }
  }
  const changes = decisions.filter(
    (row) =>
      decisionsVerified &&
      held.has(row.symbol ?? "") &&
      heldInStrategy(row) &&
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
        {state.risk?.facts?.account_scope?.startsWith("TEST_ONLY") && (
          <p role="status">
            TEST_ONLY 演练持仓，不是你的真实账户或个人交易建议。
          </p>
        )}
        {connected ? (
          <>
            <p>
              可用现金 {formatMoney(portfolio.cash_cny)} 元；总权益{" "}
              {formatMoney(portfolio.total_equity_cny)} 元；已记录{" "}
              {portfolio.positions.length} 只证券。
            </p>
            {portfolio.positions.length > 0 && (
              <Button
                icon={<ReloadOutlined />}
                loading={refreshing}
                onClick={refreshHeld}
                disabled={portfolio.revision === undefined}
              >
                刷新全部持仓证据
              </Button>
            )}
            {refreshResult && <p role="status">{refreshResult}</p>}
            {changes.map((row) => (
              <p key={row.id}>
                <Link to={`/decisions/${encodeURIComponent(row.id)}`}>
                  {row.name ?? row.symbol}
                </Link>
                ：已出现策略退出或减仓复核事项，需结合可卖数量和个人风险检查。
              </p>
            ))}
            {state.heldContinuity?.items.map((row) => (
              <p key={`held-${row.symbol}`}>
                <Link to={`/portfolio?symbol=${row.symbol}`}>{row.symbol}</Link>
                ：
                {row.selected_today
                  ? "在今日观察名单"
                  : "不在今日榜单，继续按实际持仓跟踪"}
                ；持有 {row.quantity} 股，可卖{" "}
                {row.sellable_quantity ?? "待核验"} 股。
                {row.review_reasons.includes("INVALIDATION_OR_EXIT_REVIEW")
                  ? "结构或原计划失效，优先复核减仓/退出。"
                  : row.review_reasons.includes("DAILY_DOWNTREND_REVIEW")
                    ? "日线下降，需复核原持有依据。"
                    : "继续核对原持有依据及公告。"}
                {row.data_gaps.includes("CURRENT_STRATEGY_PLAN_UNAVAILABLE") &&
                  "当前结构数据未覆盖，不能认定持仓正常。"}
              </p>
            ))}
            {!state.heldContinuity && portfolio.positions.length > 0 && (
              <p>
                完整持仓持续复核尚未读取或账本版本不一致，请刷新；榜单未出现不等于风险解除。
              </p>
            )}
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
            {decisionsVerified &&
              !changes.length &&
              state.risk &&
              !state.heldContinuity?.items.some((row) =>
                row.review_reasons.includes("INVALIDATION_OR_EXIT_REVIEW"),
              ) && (
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
