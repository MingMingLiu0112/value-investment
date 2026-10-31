import { useRef, useState } from "react";
import { Alert, Button, Space } from "antd";
import {
  api,
  ApiError,
  type LiveOperatingResearchTask,
  type OperatingResearchModelStatus,
  type PublicOperatingResearchResult,
  type PublicOperatingResearchSuccess,
  type PublicOperatingResearchPartial,
  type OperatingResearchRoleKey,
} from "../services/api";

const LABELS: Record<string, string> = {
  business_drivers: "经营驱动",
  scenarios: "条件情景",
  bear: "压力条件情景",
  base: "中间条件情景（未采用主区间）",
  bull: "修复条件情景",
  counterevidence: "反证",
  invalidation: "失效条件",
  seen_events: "已见事件",
  uncovered: "未覆盖事项",
  dimension: "经济维度",
  growth: "增长",
  profit: "盈利",
  investment: "再投资",
  funding_access: "资金可达性",
  terminal: "终端持续性",
  period_start: "期间起点",
  period_end: "期间终点",
  classification: "性质",
  lower: "下界",
  upper: "上界",
  unit: "单位",
  evidence_ids: "证据编号",
  FORECAST: "条件经营假设",
  UNKNOWN: "未知，未证明",
  ratio: "比率",
  not_quantified: "未量化",
  CNY: "人民币元",
  FUNDAMENTAL: "经营基本面",
  COUNTER_EVIDENCE: "反证与失效",
  EVENT: "事件研究",
  PARTIAL: "部分研究可读，任务未全部完成",
  QUEUED: "已排队",
  RUNNING: "研究中",
  SUCCEEDED: "任务完成",
  FAILED: "任务失败",
  CANCELLED: "已取消",
  WAITING_EVIDENCE: "等待证据",
  thesis: "研究判断",
  summary: "摘要",
  rationale: "理由",
  text: "说明",
  counter_evidence: "反证",
  thesis_breakers: "失效条件",
  next_events: "后续事件",
  findings: "研究发现",
  evidence_refs: "证据引用",
  unknowns: "未知与待补证",
};
function Readable({ value }: { value: unknown }) {
  if (value == null) return <p>未提供，不补零</p>;
  if (Array.isArray(value))
    return (
      <ul>
        {value.map((item, i) => (
          <li key={i}>
            <Readable value={item} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <dl>
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt>{LABELS[key] || key}</dt>
            <dd>
              <Readable value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{LABELS[String(value)] || String(value)}</span>;
}
export function validLiveTask(
  value: unknown,
  symbol: string,
): value is LiveOperatingResearchTask {
  if (!value || typeof value !== "object") return false;
  const row = value as LiveOperatingResearchTask;
  return (
    row.symbol === symbol &&
    typeof row.task_id === "string" &&
    !!row.task_id &&
    typeof row.status === "string" &&
    row.currency === "CNY" &&
    (row.scope === "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" ||
      row.scope === "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH") &&
    row.main_range_adopted === false &&
    row.approval_changed === false &&
    row.formal_fact_count === 0 &&
    row.condition_price === null &&
    row.personal_quantity === null &&
    Number.isInteger(row.new_llm_calls) &&
    row.new_llm_calls >= 0
  );
}
export function LiveOperatingResearchDraft({
  task,
}: {
  task:
    | LiveOperatingResearchTask
    | PublicOperatingResearchSuccess
    | PublicOperatingResearchPartial;
}) {
  return (
    <section aria-label="新Agent经营研究结果">
      {task.scope === "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH" && (
        <Alert type="warning" message="仅测试合同结果，不是真实模型研究" />
      )}
      <p>
        任务：{task.task_id} · {LABELS[task.status] || task.status} · 模型：
        {task.model_id}
      </p>
      {"reserved_cost" in task ? (
        <p>
          新增模型调用：{task.new_llm_calls} · 预留费用（人民币元）：
          {task.reserved_cost} · 已结算费用（人民币元）：{task.settled_cost}
          （用量与费用按配置费率估算，非服务商账单）
        </p>
      ) : (
        <p>
          已记录模型调用：{task.new_llm_calls}
          ；此处仅读取已生成研究，不发起新调用。
        </p>
      )}
      <p>
        研究截止：{task.research_as_of || "未提供"} ·
        经济主区间未采用；审批未改变，正式事实新增 0。
      </p>
      {task.status === "PARTIAL" && "completed_roles" in task ? (
        <Alert
          type="warning"
          message="仅部分角色研究可读，三角色未全部完成，执行状态为失败"
          description={
            <>
              <p>
                已完成：
                {task.completed_roles.map((role) => LABELS[role]).join("、")}
                ；待完成：
                {task.pending_roles.map((role) => LABELS[role]).join("、")}。
              </p>
              <p>
                {task.reason === "DAILY_BUDGET_EXHAUSTED_BEFORE_CALL"
                  ? "事件研究待预算：调用前预算预留被拒，未完成事件模型研究；本轮已停止于每日预算预留，事件待继续。"
                  : "最新执行未完成，待完成角色不能视为已有研究结果。"}
              </p>
              <p>部分草案不代表经营或估值研究充分，经济主区间仍未采用。</p>
            </>
          }
        />
      ) : (
        <p>任务完成仅表示流程完成，不代表经营或估值研究充分。</p>
      )}
      <p>任务成功不等于研究可信；反证本身也可能存在误述，需逐条核验。</p>
      {task.independent_review && (
        <Alert
          type="warning"
          message="独立复核待处理，不代表批准；反证也可能有误述"
          description={
            <ul>
              {task.independent_review.findings.map((finding, index) => (
                <li key={index}>
                  {finding.priority} · {LABELS[finding.role] || finding.role} ·
                  原始条目索引 {finding.claim_index}：{finding.reason}
                </li>
              ))}
            </ul>
          }
        />
      )}
      {task.research_completeness ? (
        <section aria-label="研究完整度">
          <p>
            情景数：{task.research_completeness.scenario_count} · 数值假设数：
            {task.research_completeness.numeric_assumption_count} · 未知假设数：
            {task.research_completeness.unknown_assumption_count}
          </p>
          <Alert
            type="info"
            message={
              task.research_completeness.status ===
              "INSUFFICIENT_FOR_NUMERIC_SCENARIOS"
                ? "数值情景依据不足，不能视为完整数值研究"
                : "研究完整度仍需复核"
            }
            description="经济有效性尚未批准；情景与假设数量不代表经济质量或估值有效性通过。"
          />
        </section>
      ) : (
        <p>尚未提供研究完整度统计，不推定研究充分。</p>
      )}
      {"error_code" in task && task.error_code && (
        <Alert type="info" message={"任务错误：" + task.error_code} />
      )}
      {task.research_draft ? (
        (
          [
            ["FUNDAMENTAL", "经营基本面草案"],
            ["COUNTER_EVIDENCE", "反证与失效草案"],
            ["EVENT", "事件与后续核验草案"],
          ] as const
        )
          .filter(
            ([key]) =>
              task.status !== "PARTIAL" ||
              ("completed_roles" in task && task.completed_roles.includes(key)),
          )
          .map(([key, title]) => (
            <section key={key}>
              <h4>{title}</h4>
              <Readable
                value={
                  task.research_draft?.[key] &&
                  typeof task.research_draft[key] === "object" &&
                  "draft" in task.research_draft[key]
                    ? (task.research_draft[key] as { draft: unknown }).draft
                    : task.research_draft?.[key]
                }
              />
            </section>
          ))
      ) : (
        <p>尚无可读研究草案，不据此补成研究结论。</p>
      )}
      <details>
        <summary>来源、上下文指纹与用量</summary>
        <Readable
          value={{
            source_binding: task.source_binding,
            context_fingerprint: task.context_fingerprint,
            usage: "usage" in task ? task.usage : undefined,
          }}
        />
      </details>
    </section>
  );
}
export function PublicOperatingResearchView({
  value,
  symbol,
}: {
  value: PublicOperatingResearchResult;
  symbol: string;
}) {
  if (
    value.symbol !== symbol ||
    value.action !== "no_order" ||
    value.formal_eligibility !== false
  )
    return (
      <Alert type="warning" message="公开经营研究身份或边界不符，停止展示" />
    );
  if (value.status === "NOT_STARTED") return <p>尚无已生成的公开经营研究。</p>;
  if (value.status === "UNASSESSABLE")
    return (
      <Alert
        type="info"
        message="最新经营研究暂不可核验，不回退展示旧成功结果"
        description={value.reason}
      />
    );
  if (value.status !== "SUCCEEDED" && value.status !== "PARTIAL")
    return <Alert type="warning" message="公开经营研究状态不符，停止展示" />;
  const allRoles: OperatingResearchRoleKey[] = [
    "FUNDAMENTAL",
    "COUNTER_EVIDENCE",
    "EVENT",
  ];
  const partial = value.status === "PARTIAL";
  const completed = partial ? value.completed_roles : allRoles;
  const rolePartitionValid =
    !partial ||
    (value.execution_status === "FAILED" &&
      Array.isArray(value.completed_roles) &&
      value.completed_roles.length > 0 &&
      value.completed_roles.length < allRoles.length &&
      Array.isArray(value.pending_roles) &&
      value.pending_roles.length > 0 &&
      [...value.completed_roles, ...value.pending_roles].length ===
        allRoles.length &&
      new Set([...value.completed_roles, ...value.pending_roles]).size ===
        allRoles.length &&
      [...value.completed_roles, ...value.pending_roles].every((role) =>
        allRoles.includes(role),
      ) &&
      typeof value.reason === "string" &&
      !!value.reason &&
      Object.keys(value.research_draft || {}).length ===
        value.completed_roles.length &&
      Object.keys(value.research_draft || {}).every((role) =>
        value.completed_roles.includes(role as OperatingResearchRoleKey),
      ));
  const source = value.source_binding as { sha256?: unknown } | null;
  const hash = (item: unknown) =>
    typeof item === "string" && /^[a-f0-9]{64}$/.test(item);
  if (
    (value.status !== "SUCCEEDED" && value.status !== "PARTIAL") ||
    !rolePartitionValid ||
    (value.research_completeness != null &&
      value.research_completeness.economic_validation !== "NOT_APPROVED") ||
    value.scope !== "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" ||
    value.main_range_adopted !== false ||
    value.approval_changed !== false ||
    value.formal_fact_count !== 0 ||
    value.condition_price !== null ||
    value.personal_quantity !== null ||
    !value.task_id ||
    !hash(value.context_fingerprint) ||
    !hash(source?.sha256) ||
    !Number.isInteger(value.new_llm_calls) ||
    value.new_llm_calls < 1 ||
    (Array.isArray(completed) ? completed : allRoles).some((role) => {
      const row = value.research_draft?.[role];
      return (
        !row ||
        !row.model_id ||
        !row.generated_at ||
        !Array.isArray(row.source_bindings) ||
        !row.source_bindings.length ||
        row.source_bindings.some(
          (ref) =>
            !ref ||
            typeof ref !== "object" ||
            !hash((ref as { pdf_sha256?: unknown }).pdf_sha256),
        ) ||
        !row.draft ||
        typeof row.draft !== "object" ||
        Array.isArray(row.draft)
      );
    })
  )
    return (
      <Alert
        type="warning"
        message="公开经营研究来源、角色草案或准入边界不完整，停止展示"
      />
    );
  return <LiveOperatingResearchDraft task={value} />;
}
type Operation =
  "status" | "start" | "history" | "refresh" | "cancel" | "resume";
export function LiveOperatingResearchPanel({ symbol }: { symbol: string }) {
  const [opened, setOpened] = useState(false);
  const [publicResult, setPublicResult] =
    useState<PublicOperatingResearchResult>();
  const [publicError, setPublicError] = useState<string>();
  const [model, setModel] = useState<OperatingResearchModelStatus>();
  const [task, setTask] = useState<LiveOperatingResearchTask>();
  const [items, setItems] = useState<LiveOperatingResearchTask[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const lock = useRef(false);
  async function perform(operation: Operation) {
    if (lock.current) return;
    if (
      (operation === "start" || operation === "resume") &&
      model?.status !== "READY"
    )
      return;
    if (["refresh", "cancel", "resume"].includes(operation) && !task) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      if (operation === "status") {
        setOpened(true);
        setPublicResult(undefined);
        setPublicError(undefined);
        const [modelRead, companyRead] = await Promise.allSettled([
          api.operatingResearchModelStatus(),
          api.operatingResearchCompany(symbol),
        ]);
        if (companyRead.status === "fulfilled")
          setPublicResult(companyRead.value);
        else
          setPublicError(
            "公开经营研究暂不可读取，不回退展示旧结果；可手动刷新重试。",
          );
        if (modelRead.status === "rejected") throw modelRead.reason;
        const result = modelRead.value;
        if (
          ![
            "READY",
            "MODEL_AUTHORIZATION_REQUIRED",
            "MODEL_CREDENTIAL_REQUIRED",
          ].includes(result.status)
        )
          throw new Error("Invalid model status");
        if (
          result.status !== "MODEL_AUTHORIZATION_REQUIRED" &&
          (result.currency !== "CNY" ||
            !result.model_id ||
            result.max_run_cost == null ||
            !Number.isFinite(Number(result.max_run_cost)) ||
            result.daily_cost_limit == null ||
            !Number.isFinite(Number(result.daily_cost_limit)))
        )
          throw new Error("Invalid model cost configuration");
        setModel(result);
      } else if (operation === "history") {
        const result = await api.operatingResearchTasks(symbol);
        if (
          !Array.isArray(result.items) ||
          (result.symbol && result.symbol !== symbol)
        )
          throw new Error("Invalid task history");
        setItems(result.items);
      } else {
        const result =
          operation === "start"
            ? await api.createOperatingResearchTask({
                symbol,
                request_key:
                  "live_" +
                  Array.from(crypto.getRandomValues(new Uint8Array(16)), (x) =>
                    x.toString(16).padStart(2, "0"),
                  ).join(""),
              })
            : operation === "refresh"
              ? await api.operatingResearchTask(task!.task_id)
              : operation === "cancel"
                ? await api.cancelOperatingResearchTask(task!.task_id)
                : await api.resumeOperatingResearchTask(task!.task_id);
        if (
          !validLiveTask(result, symbol) ||
          (operation !== "start" && result.task_id !== task!.task_id)
        )
          throw new Error("Invalid research task boundary");
        setTask(result);
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "任务操作需要本机授权；公开研究仍可查看，请解锁后手动重试。"
          : "经营研究操作未完成或响应边界无法核验，请手动重试。",
      );
      if (operation === "status") setModel(undefined);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (!opened)
    return <Button onClick={() => perform("status")}>新Agent经营研究</Button>;
  const ready = model?.status === "READY";
  const active = task?.status === "QUEUED" || task?.status === "RUNNING";
  return (
    <section aria-label="新Agent经营研究" style={{ marginBlock: 20 }}>
      <h3>新Agent经营研究 · {symbol}</h3>
      <p>
        打开此区仅读取模型状态与已生成公开研究，不发起模型调用；点击启动才可能产生新调用费用，与已保存响应重放分开。仅生成未准入的经营研究草案，不采用经济主区间、不审批、不生成条件价或个人数量、不下单。任务状态仅点击读取，不自动轮询。
      </p>
      <section aria-label="已生成的公开经营研究">
        <h4>已生成的公开经营研究</h4>
        {publicError && <Alert type="info" message={publicError} />}
        {publicResult && (
          <PublicOperatingResearchView value={publicResult} symbol={symbol} />
        )}
      </section>
      {error && <Alert type="info" message={error} />}
      <p>
        {ready
          ? "模型已就绪"
          : model?.status === "MODEL_AUTHORIZATION_REQUIRED"
            ? "模型接口、模型或调用配置尚未齐备，不能启动"
            : model?.status === "MODEL_CREDENTIAL_REQUIRED"
              ? "缺少模型凭据，不能启动"
              : "模型状态尚未核验，不能启动"}{" "}
        · 模型：{model?.model_id || "未提供"} · 单次预留上限（人民币元）：
        {model?.max_run_cost ?? "未提供"} · 每日费用上限（人民币元）：
        {model?.daily_cost_limit ?? "未提供"}
        （已授权每日人民币10元；费用按配置费率估算，非账单）
      </p>
      <Space wrap>
        <Button disabled={busy} onClick={() => perform("status")}>
          刷新模型状态
        </Button>
        <Button
          disabled={busy || !ready || active}
          onClick={() => perform("start")}
        >
          启动新研究
        </Button>
        <Button disabled={busy} onClick={() => perform("history")}>
          读取已有经营研究任务
        </Button>
        <Button disabled={busy || !task} onClick={() => perform("refresh")}>
          刷新当前任务
        </Button>
        <Button
          disabled={busy || !task || !active}
          onClick={() => perform("cancel")}
        >
          取消当前任务
        </Button>
        <Button
          disabled={
            busy || !ready || !task || active || task.status === "SUCCEEDED"
          }
          onClick={() => perform("resume")}
        >
          恢复当前任务
        </Button>
      </Space>
      <ul>
        {items.map((row, i) => (
          <li key={i}>
            {validLiveTask(row, symbol) ? (
              <Button disabled={busy} onClick={() => setTask(row)}>
                选择任务 {row.task_id} · {LABELS[row.status] || row.status}
              </Button>
            ) : (
              "任务身份或研究边界不符，不能选择"
            )}
          </li>
        ))}
      </ul>
      {task && <LiveOperatingResearchDraft task={task} />}
    </section>
  );
}
