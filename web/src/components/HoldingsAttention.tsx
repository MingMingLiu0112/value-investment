import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import type { PrivateStateHandle } from "../hooks/usePrivateState";
import { blockerText } from "../utils/packet";
import { formatMoney } from "../utils/format";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Checkbox, InputNumber, Select, Space } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api } from "../services/api";
import type { HeldSellReviewRequest } from "../services/api";
import { ActionableDecisionResult } from "./ActionableDecisionResult";
import type { ConditionalAccountDecision } from "./ActionableDecisionResult";

function HeldSellReview({
  decision,
  revision,
  account,
  exchange,
}: {
  decision: ConditionalAccountDecision;
  revision: number;
  account: string;
  exchange: string;
}) {
  const [intent, setIntent] = useState<"REDUCE" | "EXIT">("REDUCE");
  const [quantity, setQuantity] = useState<number | null>(null);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<ConditionalAccountDecision>();
  const requestId = useRef(0);
  const identity = JSON.stringify([revision, account, exchange, decision]);
  useEffect(() => {
    requestId.current += 1;
    setResult(undefined);
    setAck(false);
    setError(undefined);
    return () => {
      requestId.current += 1;
    };
  }, [identity]);
  async function review() {
    if (
      busy ||
      !ack ||
      quantity === null ||
      !Number.isSafeInteger(quantity) ||
      quantity <= 0 ||
      !decision.entry_thesis_record_sha256
    )
      return;
    const id = ++requestId.current;
    setBusy(true);
    setError(undefined);
    setResult(undefined);
    try {
      const request: HeldSellReviewRequest = {
        schema_version: "private-held-sell-review-request-v1",
        action: "no_order",
        expected_revision: revision,
        account_scope: account,
        symbol: decision.symbol,
        exchange,
        sleeve: decision.strategy,
        requested_action: intent,
        requested_quantity: quantity,
        entry_thesis_record_sha256: decision.entry_thesis_record_sha256,
        read_and_confirmed: true,
      };
      const response = await api.reviewHeldSell(request);
      if (id !== requestId.current) return;
      const value = response.actionable_decision;
      if (
        response.schema_version !== "private-held-sell-review-v1" ||
        response.action !== "no_order" ||
        response.ledger_written !== false ||
        response.broker_execution_permission !== false ||
        response.revision !== revision ||
        !response.request ||
        Object.keys(response.request).length !== Object.keys(request).length ||
        (Object.keys(request) as (keyof HeldSellReviewRequest)[]).some(
          (key) => response.request[key] !== request[key],
        ) ||
        value.symbol !== decision.symbol ||
        value.strategy !== decision.strategy ||
        value.entry_thesis_record_sha256 !==
          decision.entry_thesis_record_sha256 ||
        (!["UNASSESSABLE", "NO_TRADE"].includes(value.decision_action) &&
          (value.decision_action !== request.requested_action ||
            value.review_quantity !== request.requested_quantity))
      )
        throw new Error("复核结果与当前持仓版本不一致，请重新读取。");
      setResult(value);
    } catch (cause) {
      if (id === requestId.current)
        setError(
          cause instanceof Error ? cause.message : "复核失败，请重新读取持仓。",
        );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>复核 {decision.symbol} 的减仓或退出数量</summary>
      <p>只核验本人指定数量；不修改持仓，不提交订单。实际成交后请另行登记。</p>
      <Space wrap>
        <Select
          aria-label="卖出复核方向"
          value={intent}
          options={[
            { value: "REDUCE", label: "减仓复核" },
            { value: "EXIT", label: "退出复核" },
          ]}
          onChange={(value) => {
            setIntent(value);
            setResult(undefined);
            setAck(false);
            requestId.current += 1;
          }}
        />
        <InputNumber
          aria-label="卖出复核股数"
          min={1}
          precision={0}
          value={quantity}
          onChange={(value) => {
            setQuantity(value);
            setResult(undefined);
            setAck(false);
            requestId.current += 1;
          }}
        />
        <Checkbox
          checked={ack}
          onChange={(event) => {
            setAck(event.target.checked);
            if (!event.target.checked) {
              requestId.current += 1;
              setResult(undefined);
              setError(undefined);
            }
          }}
        >
          我已核对资金池、原投资逻辑及指定股数
        </Checkbox>
        <Button
          loading={busy}
          disabled={
            !ack || !Number.isSafeInteger(quantity) || (quantity ?? 0) <= 0
          }
          onClick={review}
        >
          核验卖出条件
        </Button>
      </Space>
      {error && <Alert type="error" message={error} />}
      {result && <ActionableDecisionResult decision={result} />}
    </details>
  );
}

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
            {state.heldContinuity?.items.flatMap((row) =>
              (row.actionable_decisions ?? []).map((decision) => (
                <div key={`owned-${row.symbol}-${decision.strategy}`}>
                  <ActionableDecisionResult decision={decision} />
                  {decision.ownership_verified &&
                    decision.entry_thesis_record_sha256 &&
                    portfolio.revision !== undefined &&
                    state.risk?.facts?.account_scope &&
                    portfolio.positions.find(
                      (position) => position.symbol === row.symbol,
                    )?.exchange && (
                      <HeldSellReview
                        decision={decision}
                        revision={portfolio.revision}
                        account={state.risk.facts.account_scope}
                        exchange={
                          portfolio.positions.find(
                            (position) => position.symbol === row.symbol,
                          )!.exchange
                        }
                      />
                    )}
                </div>
              )),
            )}
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
