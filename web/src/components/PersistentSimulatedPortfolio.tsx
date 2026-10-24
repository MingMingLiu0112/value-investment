import { useRef, useState } from "react";
import { Alert, Button } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  readSimulatedPortfolio,
  simulatedCommon,
  SimulatedRequestError,
  writeSimulatedPortfolio,
} from "../services/persistentSimulatedPortfolio";
import type {
  PersistentSimulatedWorkbench,
  SimulatedOperation,
  SimulatedSleeve,
  SimulatedWrite,
} from "../types/persistentSimulatedPortfolio";

const inputStyle = {
  display: "block",
  width: "100%",
  minWidth: 0,
  boxSizing: "border-box" as const,
};
const fieldStyle = { minWidth: 0, padding: 0, border: 0, marginBlock: 12 };
const sleeveName = (v: SimulatedSleeve) =>
  v === "CORE_VALUE" ? "价值仓" : "波段仓";

export function PersistentSimulatedPortfolio() {
  const [view, setView] = useState<PersistentSimulatedWorkbench>();
  const [busy, setBusy] = useState(false),
    lock = useRef(false);
  const [error, setError] = useState<string>(),
    [notice, setNotice] = useState<string>();
  const [confirmed, setConfirmed] = useState(false);
  const [retry, setRetry] = useState<{
    operation: SimulatedOperation;
    body: SimulatedWrite;
    accountId: string;
  }>();
  const [cash, setCash] = useState(""),
    [opening, setOpening] = useState("");
  const [fill, setFill] = useState({
    side: "BUY",
    sleeve: "CORE_VALUE",
    symbol: "",
    exchange: "SSE",
    quantity: "",
    price_cny: "",
    fees_cny: "",
    trade_date: "",
  });
  const [entryHash, setEntryHash] = useState(""),
    [sourceId, setSourceId] = useState("");
  const [thesis, setThesis] = useState(""),
    [hold, setHold] = useState(""),
    [breakers, setBreakers] = useState("");
  const [correctionTarget, setCorrectionTarget] = useState<{
    hash: string;
    version: string;
  }>();
  const [changes, setChanges] = useState({
    quantity: "",
    price_cny: "",
    fees_cny: "",
  });
  const [correctionReason, setCorrectionReason] = useState("");
  const correctionSupported =
    view?.account.confirmed_fill_correction === "PRICE_QUANTITY_FEES_ONLY_V1";
  const portfolio = view?.account.portfolio;
  const correctionTrade = portfolio?.trades.find(
    (t) => t.record_sha256 === correctionTarget?.hash,
  );
  const correctionLineage = correctionTarget
    ? view?.account.fill_corrections?.[correctionTarget.hash]
    : undefined;
  const correctionVersion =
    correctionLineage?.effective_version_sha256 ??
    correctionTrade?.record_sha256;
  const nonemptyChanges = Object.fromEntries(
    Object.entries(changes)
      .filter(([, v]) => v.trim())
      .map(([k, v]) => [k, v.trim()]),
  );
  const pending = portfolio?.pending_draft;
  const entry = view?.account.entries.find(
    (row) => row.fill_record_sha256 === entryHash,
  );
  const sources =
    view?.sources.items.filter(
      (row) => row.symbol === entry?.symbol && row.sleeve === entry?.sleeve,
    ) ?? [];
  const selectedSource = sources.find((row) => row.id === sourceId);
  const canWrite = !!view && confirmed && !busy && !retry;
  async function refresh() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    setConfirmed(false);
    setView(undefined);
    setRetry(undefined);
    setCorrectionTarget(undefined);
    try {
      setView(await readSimulatedPortfolio());
    } catch (fault) {
      setError(
        fault instanceof Error ? fault.message : "读取失败，账户状态不可核验。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function mutate(
    operation: SimulatedOperation,
    body: SimulatedWrite,
    isRetry = false,
  ) {
    if (lock.current || !confirmed || (!isRetry && !view)) return;
    const accountId = isRetry ? retry?.accountId : view?.account.account_id;
    if (!accountId) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    setConfirmed(false);
    try {
      const result = await writeSimulatedPortfolio(operation, body);
      if (
        result.account.account_id !== accountId ||
        result.account.revision < body.expected_revision
      )
        throw new SimulatedRequestError(0, true);
      setView(result);
      setRetry(undefined);
      if (operation === "correct-fill") {
        setCorrectionTarget(undefined);
        setChanges({ quantity: "", price_cny: "", fees_cny: "" });
        setCorrectionReason("");
      }
      setNotice(
        operation === "correct-fill"
          ? "模拟成交更正已追加，原交易与原Entry假说未重写；旧对账失效状态请按回执复核，不表示风险通过。"
          : operation === "prepare-fill"
            ? "草稿已保存，现金和持仓尚未确认变动；请检查后另行确认或取消。"
            : operation === "confirm-entry"
              ? "模拟Entry假说已绑定；不是原始PIT入场或研究批准。"
              : operation === "cancel-fill"
                ? "草稿已取消，不是撤销已确认成交。"
                : "模拟记录已保存，可刷新核对恢复；不是实际成交或系统建议。",
      );
    } catch (fault) {
      setView(undefined);
      setError(
        fault instanceof Error ? fault.message : "结果未知，请刷新核对。",
      );
      setRetry(
        fault instanceof SimulatedRequestError && fault.uncertain
          ? { operation, body, accountId }
          : undefined,
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function initialize(event: React.FormEvent) {
    event.preventDefault();
    if (!view || !canWrite) return;
    void mutate("initialize", {
      ...simulatedCommon(view),
      as_of: opening,
      cash_cny: cash,
      confirmed_at: view.server_now,
      confirmation_note: "用户明确确认持久模拟开户；非实盘，未确认IPS",
    });
  }
  function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!view || !canWrite || pending) return;
    void mutate("prepare-fill", {
      ...simulatedCommon(view),
      fill: { ...fill, transaction_id: `SIMULATED-${crypto.randomUUID()}` },
    });
  }
  function resolveDraft(operation: "confirm-fill" | "cancel-fill") {
    if (!view || !pending || !canWrite) return;
    void mutate(operation, {
      ...simulatedCommon(view),
      prepared_record_sha256: pending.prepared_record_sha256,
      confirmed_at: view.server_now,
      confirmation_note:
        operation === "confirm-fill"
          ? "用户检查草稿并明确确认模拟记账，非实际成交"
          : "用户明确取消未确认模拟草稿",
    });
  }
  function bindEntry(event: React.FormEvent) {
    event.preventDefault();
    if (!view || !entry || !selectedSource || !canWrite) return;
    void mutate("confirm-entry", {
      ...simulatedCommon(view),
      fill_record_sha256: entry.fill_record_sha256,
      source_id: selectedSource.id,
      expected_source_binding: { ...selectedSource.candidate_binding },
      narrative: {
        thesis,
        hold_logic: hold,
        invalidation_conditions: breakers
          .split(/\r?\n/)
          .map((v) => v.trim())
          .filter(Boolean),
      },
      confirmation_note:
        "用户明确确认模拟入场假说及当前来源Hash；事后重建不授予策略资格",
    });
  }
  function correctFill(event: React.FormEvent) {
    event.preventDefault();
    if (
      !view ||
      !canWrite ||
      !correctionSupported ||
      pending ||
      !correctionTarget ||
      correctionTarget.version !== correctionVersion ||
      !Object.keys(nonemptyChanges).length ||
      !correctionReason.trim()
    )
      return;
    void mutate("correct-fill", {
      ...simulatedCommon(view),
      target_fill_record_sha256: correctionTarget.hash,
      expected_original_version: correctionTarget.version,
      changes: nonemptyChanges,
      confirmed_at: view.server_now,
      reason: correctionReason.trim(),
    });
  }
  return (
    <section
      aria-label="持久模拟账户"
      style={{
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        marginBlock: 24,
      }}
    >
      <h3>持久模拟账户 · SIMULATED</h3>
      <p>
        手工假设记账会保留，重新打开后可读取恢复。与实盘和临时演练隔离；买卖按钮仅记录人工假设，不是选股、加减仓建议或券商订单。
      </p>
      <p>
        尚未确认IPS，风险及仓位未评估；无市场价格，不显示收益率或估值。
        {!view
          ? "成交更正能力需读取服务器回执确认。"
          : correctionSupported
            ? "仅支持追加价格、数量、费用更正，不改交易身份，不代表完整交易闭环。"
            : "确认后更正暂不支持，不能称为完整交易闭环。"}
      </p>
      <Button
        aria-label="读取 / 刷新模拟账户"
        icon={<ReloadOutlined />}
        loading={busy}
        onClick={() => void refresh()}
      >
        读取 / 刷新模拟账户
      </Button>
      {!view && !error && !busy && (
        <p>尚未读取，不会自动创建账户或发送写入。</p>
      )}
      {busy && <p role="status">正在读取或核验模拟记录，勿重复提交。</p>}
      {error && <Alert type="error" showIcon message={error} />}
      {notice && <p role="status">{notice}</p>}
      <label style={{ display: "block", marginBlock: 12 }}>
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        我确认本次写入仅为持久模拟记账，不是实际成交、策略批准或实盘IPS
      </label>
      {retry && (
        <div>
          <p>
            上次写入结果未知。可先刷新核对；若显式重试，将使用完全相同的幂等键、版本和请求，不按新表单重建。
          </p>
          <Button
            disabled={!confirmed || busy}
            onClick={() => void mutate(retry.operation, retry.body, true)}
          >
            以相同请求重试模拟写入
          </Button>
        </div>
      )}
      {view && (
        <>
          <p>
            账户：{view.account.account_id}；版本：{view.account.revision}
            ；服务器读取时点：{view.server_now}。资格为false，未使用实盘账户。
          </p>
          <p>
            {view.sources.status === "AVAILABLE"
              ? "来源仅供假说引用，不是研究或交易批准。"
              : "研究来源不可用：仍可读取账户、手工记账及处理既有草稿；当前不能绑定新Entry来源。"}
          </p>
          {view.account.status === "NOT_INITIALIZED" ? (
            <form onSubmit={initialize}>
              <fieldset disabled={busy} style={fieldStyle}>
                <legend>初始化模拟账户</legend>
                <label>
                  初始模拟现金（元）
                  <input
                    required
                    inputMode="decimal"
                    style={inputStyle}
                    value={cash}
                    onChange={(e) => setCash(e.target.value)}
                  />
                </label>
                <label>
                  模拟开户日期
                  <input
                    required
                    type="date"
                    style={inputStyle}
                    value={opening}
                    onChange={(e) => setOpening(e.target.value)}
                  />
                </label>
                <Button
                  aria-label="确认初始化模拟账户"
                  htmlType="submit"
                  disabled={!canWrite}
                  icon={<CheckOutlined />}
                >
                  确认初始化模拟账户
                </Button>
              </fieldset>
            </form>
          ) : (
            portfolio && (
              <>
                <h4>共享现金与持仓</h4>
                <p>
                  记账截至 {portfolio.as_of}；共享模拟现金 {portfolio.cash_cny}{" "}
                  元；已实现记账损益 {portfolio.realized_pnl_cny}{" "}
                  元。未接行情，不是总资产市值。
                </p>
                {!portfolio.positions.length && (
                  <p>无已确认模拟持仓；不表示没有投资机会。</p>
                )}
                <ul>
                  {portfolio.positions.map((p) => (
                    <li key={`${p.exchange}-${p.symbol}`}>
                      {p.symbol} · {p.exchange}：{p.quantity} 股，记账成本{" "}
                      {p.cost_cny} 元。
                      <ul>
                        {p.sleeves.map((s) => (
                          <li key={s.sleeve}>
                            {sleeveName(s.sleeve)}：{s.quantity} 股；可卖{" "}
                            {s.sellable_quantity} 股；后续可卖日{" "}
                            {s.next_sell_session ?? "无待解锁日期"}
                            （服务器口径）。
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
                {pending ? (
                  <section aria-label="已保存模拟草稿">
                    <h4>已保存草稿 · 尚未确认成交</h4>
                    <p>
                      {pending.fill.side === "BUY"
                        ? "人工买入假设"
                        : "人工卖出假设"}{" "}
                      · {sleeveName(pending.fill.sleeve)} ·{" "}
                      {pending.fill.symbol} · {pending.fill.exchange}
                    </p>
                    <p>
                      日期 {pending.fill.trade_date}；{pending.fill.quantity}{" "}
                      股；假设价格 {pending.fill.price_cny} 元；假设费用{" "}
                      {pending.fill.fees_cny} 元。
                    </p>
                    <p>
                      确认后模拟现金预览 {pending.cash_cny}{" "}
                      元，不是当前现金或建议。
                    </p>
                    <details>
                      <summary>草稿交易及准备记录</summary>
                      <p>{pending.fill.transaction_id}</p>
                      <p>{pending.prepared_record_sha256}</p>
                    </details>
                    <Button
                      aria-label="确认这笔模拟成交"
                      icon={<CheckOutlined />}
                      disabled={!canWrite}
                      onClick={() => resolveDraft("confirm-fill")}
                    >
                      确认这笔模拟成交
                    </Button>{" "}
                    <Button
                      aria-label="取消未确认草稿"
                      icon={<CloseOutlined />}
                      disabled={!canWrite}
                      onClick={() => resolveDraft("cancel-fill")}
                    >
                      取消未确认草稿
                    </Button>
                  </section>
                ) : (
                  <form onSubmit={prepare}>
                    <fieldset disabled={busy} style={fieldStyle}>
                      <legend>准备人工模拟成交（不是操作建议）</legend>
                      <label>
                        记账方向
                        <select
                          style={inputStyle}
                          value={fill.side}
                          onChange={(e) =>
                            setFill({ ...fill, side: e.target.value })
                          }
                        >
                          <option value="BUY">BUY · 人工买入记账</option>
                          <option value="SELL">SELL · 人工卖出记账</option>
                        </select>
                      </label>
                      <label>
                        记账策略仓
                        <select
                          style={inputStyle}
                          value={fill.sleeve}
                          onChange={(e) =>
                            setFill({ ...fill, sleeve: e.target.value })
                          }
                        >
                          <option value="CORE_VALUE">价值仓 CORE_VALUE</option>
                          <option value="HOTSPOT_SATELLITE">
                            波段仓 HOTSPOT_SATELLITE
                          </option>
                        </select>
                      </label>
                      <label>
                        交易所
                        <select
                          style={inputStyle}
                          value={fill.exchange}
                          onChange={(e) =>
                            setFill({ ...fill, exchange: e.target.value })
                          }
                        >
                          <option value="SSE">上交所 SSE</option>
                          <option value="SZSE">深交所 SZSE</option>
                        </select>
                      </label>
                      {(
                        [
                          ["symbol", "证券代码"],
                          ["quantity", "假设成交股数"],
                          ["price_cny", "假设成交价格（非行情）"],
                          ["fees_cny", "假设成交费用（元）"],
                          ["trade_date", "模拟成交日期"],
                        ] as const
                      ).map(([key, label]) => (
                        <label key={key}>
                          {label}
                          <input
                            required
                            type={key === "trade_date" ? "date" : "text"}
                            style={inputStyle}
                            value={fill[key]}
                            onChange={(e) =>
                              setFill({ ...fill, [key]: e.target.value })
                            }
                          />
                        </label>
                      ))}
                      <p>
                        交易单位、T+1可卖日期由服务器核验。BUY不区分系统开仓/加仓建议；其持有逻辑须另行记录，不能由成交反推批准。
                      </p>
                      <Button htmlType="submit" disabled={!canWrite}>
                        准备模拟草稿
                      </Button>
                    </fieldset>
                  </form>
                )}
                <h4>已确认模拟成交与逐笔费用</h4>
                {!portfolio.trades.length && <p>暂无已确认模拟成交。</p>}
                <ul>
                  {portfolio.trades.map((t) => (
                    <li key={t.record_sha256}>
                      {t.trade_date} · {t.symbol} · {sleeveName(t.sleeve)} ·{" "}
                      {t.side} · {t.quantity} 股；假设价 {t.price_cny} 元，费用{" "}
                      {t.fees_cny} 元。
                      <details>
                        <summary>交易编号与记录Hash</summary>
                        <p>{t.transaction_id}</p>
                        <p>{t.record_sha256}</p>
                      </details>
                    </li>
                  ))}
                </ul>
                {correctionSupported && (
                  <section aria-label="模拟已确认成交更正">
                    <h4>已确认模拟成交更正</h4>
                    <p>
                      只追加价格、数量或费用更正，不制造反向成交；证券、买卖方向、日期和策略仓不可修改。原交易Hash与原Entry假说保留，不自动变成新投资逻辑。
                    </p>
                    <p>
                      {view.account.correction_reconciliation_status ===
                      "INVALIDATED_RECONCILIATION_REQUIRED"
                        ? "旧对账已失效，必须重新核对；原Entry需要复核，风险及仓位未评估。"
                        : view.account.correction_reconciliation_status ===
                            "RECONCILED_AFTER_CORRECTION"
                          ? "服务器记录更正后已重新对账；这不等于风险、原Entry假说或策略获准。"
                          : "尚无成交更正。"}
                    </p>
                    {Object.entries(view.account.fill_corrections ?? {}).map(
                      ([target, c]) => (
                        <section key={target} aria-label="模拟成交原值与有效值">
                          <p>
                            {c.original_fill.symbol} ·{" "}
                            {sleeveName(c.original_fill.sleeve)} ·{" "}
                            {c.original_fill.side} ·{" "}
                            {c.original_fill.trade_date} · 原交易{" "}
                            {c.original_fill.transaction_id}
                          </p>
                          <p>
                            原记录：{c.original_fill.quantity} 股，价格{" "}
                            {c.original_fill.price_cny} 元，费用{" "}
                            {c.original_fill.fees_cny} 元。
                          </p>
                          <p>
                            当前有效记录：{c.effective_fill.quantity} 股，价格{" "}
                            {c.effective_fill.price_cny} 元，费用{" "}
                            {c.effective_fill.fees_cny}{" "}
                            元。仍为人工模拟，不是行情。
                          </p>
                          <details>
                            <summary>原交易、更正链及有效版本Hash</summary>
                            <p>{target}</p>
                            <p>{c.effective_version_sha256}</p>
                            <ul>
                              {c.correction_record_sha256s.map((h) => (
                                <li key={h}>{h}</li>
                              ))}
                            </ul>
                          </details>
                        </section>
                      ),
                    )}
                    <form onSubmit={correctFill}>
                      <fieldset disabled={busy} style={fieldStyle}>
                        <legend>追加模拟成交更正（非实际交易）</legend>
                        <label>
                          选择更正的原交易
                          <select
                            required
                            style={inputStyle}
                            value={correctionTarget?.hash ?? ""}
                            onChange={(e) => {
                              const target = e.target.value;
                              setCorrectionTarget(
                                target
                                  ? {
                                      hash: target,
                                      version:
                                        view.account.fill_corrections?.[target]
                                          ?.effective_version_sha256 ?? target,
                                    }
                                  : undefined,
                              );
                              setChanges({
                                quantity: "",
                                price_cny: "",
                                fees_cny: "",
                              });
                              setCorrectionReason("");
                            }}
                          >
                            <option value="">请选择已确认原交易</option>
                            {portfolio.trades.map((t) => (
                              <option
                                key={t.record_sha256}
                                value={t.record_sha256}
                              >
                                {t.symbol} · {t.side} · {t.trade_date} ·{" "}
                                {t.transaction_id}
                              </option>
                            ))}
                          </select>
                        </label>
                        {correctionTrade && (
                          <>
                            <p>
                              身份固定：{correctionTrade.symbol} ·{" "}
                              {correctionTrade.exchange} ·{" "}
                              {sleeveName(correctionTrade.sleeve)} ·{" "}
                              {correctionTrade.side} ·{" "}
                              {correctionTrade.trade_date}。
                            </p>
                            <p>
                              原值：
                              {
                                (
                                  correctionLineage?.original_fill ??
                                  correctionTrade
                                ).quantity
                              }{" "}
                              股 / 价格{" "}
                              {
                                (
                                  correctionLineage?.original_fill ??
                                  correctionTrade
                                ).price_cny
                              }{" "}
                              元 / 费用{" "}
                              {
                                (
                                  correctionLineage?.original_fill ??
                                  correctionTrade
                                ).fees_cny
                              }{" "}
                              元。
                            </p>
                            <p>
                              当前有效值：{correctionTrade.quantity} 股 / 价格{" "}
                              {correctionTrade.price_cny} 元 / 费用{" "}
                              {correctionTrade.fees_cny} 元。
                            </p>
                            <details>
                              <summary>本次固定目标及版本</summary>
                              <p>{correctionTarget?.hash}</p>
                              <p>{correctionTarget?.version}</p>
                            </details>
                          </>
                        )}
                        {(
                          [
                            ["quantity", "更正后股数"],
                            ["price_cny", "更正后假设价格"],
                            ["fees_cny", "更正后假设费用"],
                          ] as const
                        ).map(([key, label]) => (
                          <label key={key}>
                            {label}
                            <input
                              style={inputStyle}
                              value={changes[key]}
                              onChange={(e) =>
                                setChanges({
                                  ...changes,
                                  [key]: e.target.value,
                                })
                              }
                            />
                          </label>
                        ))}
                        <p>
                          空白字段保持不变，至少填写一项。零股数、现金不足、T+1或非法后继历史由服务器拒绝；不通过反向交易绕过。
                        </p>
                        <label>
                          模拟成交更正原因
                          <textarea
                            required
                            style={inputStyle}
                            value={correctionReason}
                            onChange={(e) =>
                              setCorrectionReason(e.target.value)
                            }
                          />
                        </label>
                        {pending && (
                          <p>
                            存在未处理草稿，不能更正已确认成交。请先处理草稿。
                          </p>
                        )}
                        <Button
                          htmlType="submit"
                          disabled={
                            !canWrite ||
                            !!pending ||
                            !correctionTarget ||
                            correctionTarget.version !== correctionVersion ||
                            !Object.keys(nonemptyChanges).length ||
                            !correctionReason.trim()
                          }
                        >
                          确认追加模拟成交更正
                        </Button>
                      </fieldset>
                    </form>
                  </section>
                )}
                <h4>原Entry假说与剩余量</h4>
                {!view.account.entries.length && (
                  <p>暂无可核对原Entry；成交记录不自动产生投资逻辑。</p>
                )}
                {view.account.entries.map((e) => (
                  <section key={e.fill_record_sha256} aria-label="模拟原Entry">
                    <p>
                      {e.symbol} · {sleeveName(e.sleeve)} · 原交易{" "}
                      {e.transaction_id}；剩余 {e.remaining_quantity} 股。
                    </p>
                    {e.hypothesis ? (
                      <>
                        <p>原假说：{e.hypothesis.thesis}</p>
                        <p>持有理由：{e.hypothesis.hold_logic}</p>
                        <p>
                          失效条件：
                          {e.hypothesis.invalidation_conditions.join("；")}
                        </p>
                        <details>
                          <summary>原Entry来源及确认Hash</summary>
                          <p>{e.hypothesis.research_version}</p>
                          <p>{e.entry_confirmation_sha256}</p>
                        </details>
                      </>
                    ) : (
                      <p>原Entry假说未记录，不能当作已完成买卖一致性核验。</p>
                    )}
                    <p>
                      事后模拟重建：原始PIT未证明，建议资格为false。未提供卖出逐批理由对照，不宣称卖出逻辑已闭环。
                    </p>
                    {e.hypothesis_review_status ===
                      "ACCOUNT_HISTORY_CORRECTED_REVIEW_REQUIRED" && (
                      <p>
                        账户成交历史已更正，原Entry假说未重写，需要重新复核；不是新逻辑已确认。
                      </p>
                    )}
                  </section>
                ))}
                <form onSubmit={bindEntry}>
                  <fieldset disabled={busy} style={fieldStyle}>
                    <legend>记录原Entry人工假说</legend>
                    <label>
                      选择未绑定假说的模拟Entry
                      <select
                        required
                        style={inputStyle}
                        value={entryHash}
                        onChange={(e) => {
                          setEntryHash(e.target.value);
                          setSourceId("");
                        }}
                      >
                        <option value="">请选择</option>
                        {view.account.entries
                          .filter((e) => !e.hypothesis)
                          .map((e) => (
                            <option
                              key={e.fill_record_sha256}
                              value={e.fill_record_sha256}
                            >
                              {e.symbol} · {sleeveName(e.sleeve)} ·{" "}
                              {e.transaction_id}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      选择同证券同策略来源
                      <select
                        required
                        style={inputStyle}
                        value={sourceId}
                        onChange={(e) => setSourceId(e.target.value)}
                      >
                        <option value="">请选择当前来源</option>
                        {sources.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.id} · 仅参考未批准
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedSource && (
                      <details>
                        <summary>本次确认的来源绑定（版本变化将拒绝）</summary>
                        <p>{selectedSource.candidate_binding.path}</p>
                        <p>{selectedSource.candidate_binding.sha256}</p>
                      </details>
                    )}
                    <label>
                      原始投资假说
                      <input
                        required
                        style={inputStyle}
                        value={thesis}
                        onChange={(e) => setThesis(e.target.value)}
                      />
                    </label>
                    <label>
                      继续持有理由
                      <input
                        required
                        style={inputStyle}
                        value={hold}
                        onChange={(e) => setHold(e.target.value)}
                      />
                    </label>
                    <label>
                      失效条件（每行一项）
                      <textarea
                        required
                        style={inputStyle}
                        value={breakers}
                        onChange={(e) => setBreakers(e.target.value)}
                      />
                    </label>
                    <Button
                      htmlType="submit"
                      disabled={
                        !canWrite ||
                        !entry ||
                        !!entry.hypothesis ||
                        !selectedSource
                      }
                    >
                      确认模拟Entry假说
                    </Button>
                  </fieldset>
                </form>
              </>
            )
          )}
        </>
      )}
    </section>
  );
}
