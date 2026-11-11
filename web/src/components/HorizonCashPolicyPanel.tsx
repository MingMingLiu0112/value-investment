import { useEffect, useRef, useState } from "react";
import { Alert, Button, Space } from "antd";
import {
  api,
  ApiError,
  type HorizonCashPolicyE2Input,
  type HorizonCashPolicyTask,
} from "../services/api";
import { Readable } from "./LiveOperatingResearchPanel";

function valid(value: HorizonCashPolicyTask | undefined, symbol: string) {
  return Boolean(
    value &&
    value.action === "no_order" &&
    value.symbol === symbol &&
    /^rt-[0-9a-f]{32}$/.test(value.task_id),
  );
}
function validE2Input(value: HorizonCashPolicyE2Input | undefined) {
  return Boolean(
    value &&
    value.action === "no_order" &&
    value.formal_eligibility === false &&
    value.condition_price === null &&
    typeof value.status === "string" &&
    value.status.length > 0,
  );
}
function safeReason(cause: unknown) {
  if (!(cause instanceof ApiError) || typeof cause.detail !== "string")
    return null;
  return /^[A-Z0-9_:-]{3,160}$/.test(cause.detail) ? cause.detail : null;
}
export function HorizonCashPolicyPanel({ symbol }: { symbol: string }) {
  const [opened, setOpened] = useState(false);
  const [task, setTask] = useState<HorizonCashPolicyTask>();
  const [e2Input, setE2Input] = useState<HorizonCashPolicyE2Input>();
  const [kind, setKind] = useState<"annual" | "compact">("annual");
  const [history, setHistory] = useState<HorizonCashPolicyTask[]>();
  const [historyKind, setHistoryKind] = useState<"annual" | "compact">(
    "annual",
  );
  const [annualHistory, setAnnualHistory] = useState<HorizonCashPolicyTask[]>();
  const [annualTaskId, setAnnualTaskId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const lock = useRef(false);
  useEffect(() => {
    setOpened(false);
    setTask(undefined);
    setE2Input(undefined);
    setKind("annual");
    setHistory(undefined);
    setHistoryKind("annual");
    setAnnualHistory(undefined);
    setAnnualTaskId(undefined);
    setBusy(false);
    setError(undefined);
  }, [symbol]);
  useEffect(() => {
    if (!opened || !task || !["QUEUED", "RUNNING"].includes(task.status))
      return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const next =
          kind === "compact"
            ? await api.compactCashPolicyTask(task.task_id)
            : await api.horizonCashPolicyTask(task.task_id);
        if (!cancelled && valid(next, symbol)) setTask(next);
      } catch {
        if (!cancelled)
          setError("D2现金政策任务状态暂不可读；未重新发起模型调用。");
      }
    }, 3000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [opened, task, symbol, kind]);
  async function run(
    operation: "start" | "startCompact" | "refresh" | "cancel" | "resume",
  ) {
    if (lock.current || (!operation.startsWith("start") && !task)) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result =
        operation === "start" || operation === "startCompact"
          ? await (
              operation === "startCompact"
                ? api.createCompactCashPolicyTask
                : api.createHorizonCashPolicyTask
            )({
              symbol,
              years: [new Date().getFullYear()],
              request_key: "cash_" + crypto.randomUUID().replace(/-/g, ""),
            })
          : operation === "refresh"
            ? await (kind === "compact"
                ? api.compactCashPolicyTask(task!.task_id)
                : api.horizonCashPolicyTask(task!.task_id))
            : await (kind === "compact"
                ? api.controlCompactCashPolicyTask(task!.task_id, operation)
                : api.controlHorizonCashPolicyTask(task!.task_id, operation));
      if (!valid(result, symbol))
        throw new Error("Invalid D2 cash-policy task boundary");
      setE2Input(undefined);
      setTask(result);
      if (operation === "start" || operation === "startCompact")
        setKind(operation === "startCompact" ? "compact" : "annual");
    } catch (cause) {
      const reason = safeReason(cause);
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "启动或读取D2现金政策研究需要本机授权；不会影响公开研究阅读。"
          : reason
            ? `D2现金政策任务被拒绝：${reason}；未启动重复模型调用。`
            : "D2现金政策任务未通过来源、预算或结构化输出校验；请查看任务状态后再决定是否重试。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function loadHistory(selectedKind: "annual" | "compact") {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result =
        selectedKind === "annual"
          ? await api.horizonCashPolicyHistory(symbol)
          : await api.compactCashPolicyHistory(symbol);
      if (
        result.action !== "no_order" ||
        result.symbol !== symbol ||
        !Array.isArray(result.items) ||
        result.items.some((row) => !valid(row, symbol))
      )
        throw new Error("INVALID_COMPACT_HISTORY");
      setHistory(result.items);
      setHistoryKind(selectedKind);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "读取D2历史任务需要本机授权；公开研究仍可阅读。"
          : "现金政策任务历史暂不可读；未发起模型调用。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function readE2Input() {
    if (!task || busy || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result =
        kind === "compact"
          ? annualTaskId
            ? await api.splitD2E2Input(task.task_id, annualTaskId)
            : await api.compactCashPolicyE2Input(task.task_id)
          : await api.horizonCashPolicyE2Input(task.task_id);
      if (!validE2Input(result))
        throw new Error("INVALID_E2_READINESS_PROJECTION");
      setE2Input(result);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "读取E2接线需要本机授权；不会影响公开研究阅读。"
          : cause instanceof ApiError && cause.status === 503
            ? "E2接线读取正被发布锁保护，请稍后手动重试；未重新发起模型调用。"
            : "该任务尚未形成可被E2消费的完整现金政策；未触发新的模型调用。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function loadAnnualHistory() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.annualOperatingHistory(symbol);
      if (
        result.action !== "no_order" ||
        result.symbol !== symbol ||
        !Array.isArray(result.items) ||
        result.items.some((row) => !valid(row, symbol))
      )
        throw new Error("INVALID_ANNUAL_HISTORY");
      setAnnualHistory(result.items);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "查看独立年度经营任务需要本机授权；公开研究仍可阅读。"
          : "独立年度经营任务历史不可读；不自动匹配不同版本的研究。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function startAnchoredAnnual() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.createAnchoredAnnualTask({
        symbol,
        years: [new Date().getFullYear()],
        request_key: "annual_" + crypto.randomUUID().replace(/-/g, ""),
      });
      if (!valid(result, symbol))
        throw new Error("INVALID_ANNUAL_TASK_BOUNDARY");
      setAnnualHistory((current) => [
        result,
        ...(current || []).filter((row) => row.task_id !== result.task_id),
      ]);
      setAnnualTaskId(undefined);
      setE2Input(undefined);
    } catch (cause) {
      const reason = safeReason(cause);
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "启动年度经营研究需要本机授权；不会影响公开研究阅读。"
          : reason
            ? `年度经营任务被拒绝：${reason}；没有自动重试付费调用。`
            : "年度经营任务未通过来源或预算预检；没有自动重试付费调用。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (!opened)
    return <Button onClick={() => setOpened(true)}>D2 股东现金政策研究</Button>;
  const active = Boolean(task && ["QUEUED", "RUNNING"].includes(task.status));
  return (
    <section aria-label="D2 股东现金政策研究" style={{ marginTop: 12 }}>
      <h4>D2 股东现金政策研究 · {symbol}</h4>
      <p>
        为年度经营情景补充派息、可达利润、准备金、维持投入、营运资本和资金承诺。未知项保持未知；结果不产生估值、条件价格、审批或订单。
      </p>
      {error && <Alert type="warning" message={error} />}
      <Space wrap>
        <Button disabled={busy || active} onClick={() => run("start")}>
          启动年度研究
        </Button>
        <Button disabled={busy || active} onClick={() => run("startCompact")}>
          启动紧凑现金政策研究
        </Button>
        <Button disabled={busy} onClick={() => loadHistory("annual")}>
          读取年度研究历史
        </Button>
        <Button disabled={busy} onClick={() => loadHistory("compact")}>
          读取紧凑研究历史
        </Button>
        <Button disabled={busy} onClick={loadAnnualHistory}>
          读取独立年度经营历史
        </Button>
        <Button disabled={busy} onClick={startAnchoredAnnual}>
          启动同源年度经营研究
        </Button>
        <Button disabled={busy || !task} onClick={() => run("refresh")}>
          读取当前任务
        </Button>
        <Button
          disabled={busy || task?.status !== "SUCCEEDED"}
          onClick={readE2Input}
        >
          检查E2接线
        </Button>
        <Button disabled={busy || !active} onClick={() => run("cancel")}>
          取消
        </Button>
        <Button
          disabled={
            busy ||
            !task ||
            active ||
            ["SUCCEEDED", "CANCELLED"].includes(task.status)
          }
          onClick={() => run("resume")}
        >
          恢复
        </Button>
      </Space>
      {history && (
        <div
          aria-label={
            historyKind === "annual" ? "D2年度研究历史" : "D2紧凑研究历史"
          }
        >
          {history.length === 0 ? (
            <p>尚无封存任务</p>
          ) : (
            history.map((row) => (
              <Button
                key={row.task_id}
                onClick={() => {
                  setKind(historyKind);
                  setTask(row);
                  setAnnualTaskId(undefined);
                  setE2Input(undefined);
                }}
              >
                {row.task_id} ·{" "}
                {row.persisted_status && row.persisted_status !== row.status
                  ? `封存${row.persisted_status} / 当前${row.status}`
                  : row.status}
              </Button>
            ))
          )}
        </div>
      )}
      {annualHistory && (
        <div aria-label="独立年度经营研究历史">
          <p>
            选择一条已成功的年度经营研究，与当前紧凑现金政策做同源E2检查；服务端会逐项核对原件，选择不授予投资资格。
          </p>
          {annualHistory.length === 0 && <p>尚无独立年度经营封存任务。</p>}
          {annualHistory.map((row) => (
            <Button
              key={row.task_id}
              disabled={row.status !== "SUCCEEDED"}
              aria-pressed={annualTaskId === row.task_id}
              onClick={() => {
                setAnnualTaskId(row.task_id);
                setE2Input(undefined);
              }}
            >
              {row.task_id} · {row.status}
            </Button>
          ))}
        </div>
      )}
      {task && (
        <>
          <p>
            任务：{task.task_id} · 类型：
            {kind === "compact" ? "紧凑现金政策" : "年度经营与现金政策"} ·
            状态：{task.status} · 资格：未批准
          </p>
          {task.persisted_status && task.persisted_status !== task.status && (
            <Alert
              type="warning"
              message={`封存执行状态：${task.persisted_status}；当前来源/实现校验：${task.status}。历史结果不能自动升级为当前研究。`}
            />
          )}
          {task.error_code && <Alert type="info" message={task.error_code} />}
          {task.sealed_response_diagnostic?.status ===
            "REJECTED_RESPONSE_DIAGNOSTIC_ONLY" && (
            <Alert
              type="warning"
              message="封存模型响应未通过现金政策合同，不能进入 E2"
              description={`未量化或缺失：${[...new Set(task.sealed_response_diagnostic.missing_terms.map((row) => row.term))].join("、") || "结构字段错误"}。这是未验证响应的字段诊断，不是研究事实、估值输入或交易资格。`}
            />
          )}
          {task.cash_policy_completeness?.status ===
            "INCOMPLETE_UNKNOWN_TERMS" && (
            <Alert
              type="warning"
              message="已读取封存研究，但现金政策尚不能进入估值"
              description={`尚缺 ${[...new Set(task.cash_policy_completeness.missing_terms.map((row) => row.term))].join("、")}；任务原状态为 ${task.persisted_status || task.status}。这些内容仅供诊断，不代表研究准入或交易资格。`}
            />
          )}
          {task.economic_validation?.status === "REJECTED" && (
            <Alert
              type="error"
              message="经济口径核验未通过：股东回报规划以归母净利润为分母，模型把它解释成母公司净利润；该结果不能进入估值或条件价格。"
              description={task.economic_validation.reason}
            />
          )}
          {task.research_result && <Readable value={task.research_result} />}
        </>
      )}
      {e2Input && (
        <>
          <p>E2现金政策交接：{e2Input.status}</p>
          {kind === "compact" && annualTaskId && (
            <p>
              独立年度经营任务：{annualTaskId}
              ；仅在同一原件与事实、同一年份且两项均成功时交接。
            </p>
          )}
          {e2Input.annual_operating_status && (
            <p>
              {annualTaskId && kind === "compact"
                ? "同源独立年度经营编译"
                : "同任务年度经营编译"}
              ：{e2Input.annual_operating_status}
            </p>
          )}
          {e2Input.annual_operating_error && (
            <Alert
              type="warning"
              message={`年度经营输入缺口：${e2Input.annual_operating_error}`}
            />
          )}
          {e2Input.blockers && (
            <Readable
              value={{ blockers: e2Input.blockers, scope: e2Input.scope }}
            />
          )}
          {e2Input.reason && <Alert type="info" message={e2Input.reason} />}
        </>
      )}
    </section>
  );
}
