import { useRef, useState } from "react";
import { Alert, Button, Descriptions, Space } from "antd";
import { api, ApiError, type ResearchTaskResponse } from "../../services/api";

const STATUS_LABELS: Record<ResearchTaskResponse["status"], string> = {
  QUEUED: "已排队",
  RUNNING: "处理中",
  WAITING_EVIDENCE: "等待证据",
  SUCCEEDED: "重放完成",
  FAILED: "处理失败",
  CANCELLED: "已取消",
};

type Operation = "start" | "refresh" | "cancel" | "resume" | "history";

export function newResearchTaskRequestKey(): string {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  return (
    "rt_" +
    Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")
  );
}

function taskError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 401)
    return "任务操作需要本机授权，请使用已解锁的工作台后重试；公开研究仍可查看。";
  if (cause instanceof ApiError)
    return (
      "任务操作未完成（HTTP " +
      cause.status +
      "，" +
      cause.code +
      "），请手动重试。"
    );
  return "任务操作失败或响应无法核验，请手动重试；公开研究仍可查看。";
}

function isTaskForSymbol(
  value: unknown,
  symbol: string,
): value is ResearchTaskResponse {
  if (!value || typeof value !== "object") return false;
  const task = value as Partial<ResearchTaskResponse>;
  return (
    task.symbol === symbol &&
    typeof task.task_id === "string" &&
    task.task_id.length > 0 &&
    typeof task.status === "string" &&
    Object.prototype.hasOwnProperty.call(STATUS_LABELS, task.status) &&
    task.action === "no_order" &&
    task.formal_eligibility === false &&
    task.new_llm_calls === 0 &&
    (task.execution_mode === "SAVED_RESPONSE" ||
      task.execution_mode === "MOCK") &&
    typeof task.workflow === "string" &&
    typeof task.snapshot_status === "string" &&
    typeof task.checkpoint_verified === "boolean" &&
    Number.isFinite(task.attempts) &&
    Number.isFinite(task.provider_requests) &&
    Number.isFinite(task.usage?.prompt_tokens) &&
    Number.isFinite(task.usage?.completion_tokens) &&
    typeof task.record_binding?.path === "string" &&
    typeof task.record_binding?.sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(task.record_binding.sha256)
  );
}

export function ResearchTaskPanel({ symbol }: { symbol: string }) {
  const [saved, setSaved] = useState<ResearchTaskResponse>();
  const [operation, setOperation] = useState<Operation>();
  const [error, setError] = useState<string>();
  const [listing, setListing] = useState<{
    symbol: string;
    items: ResearchTaskResponse[];
  }>();
  const history = listing?.symbol === symbol ? listing.items : undefined;
  const inFlight = useRef(false);
  const task = saved?.symbol === symbol ? saved : undefined;
  const active = task?.status === "QUEUED" || task?.status === "RUNNING";

  async function perform(next: Operation) {
    if (inFlight.current || (next !== "start" && next !== "history" && !task))
      return;
    inFlight.current = true;
    setOperation(next);
    setError(undefined);
    try {
      if (next === "history") {
        const value = await api.researchTasksForSymbol(symbol);
        if (
          value.action !== "no_order" ||
          value.symbol !== symbol ||
          value.scope !== "BOUNDED_TASK_HISTORY" ||
          !Array.isArray(value.items)
        )
          throw new Error("Task history identity or scope differs");
        setListing({ symbol, items: value.items });
        return;
      }
      const value =
        next === "start"
          ? await api.createResearchTask({
              symbol,
              workflow: "legacy",
              request_key: newResearchTaskRequestKey(),
            })
          : next === "refresh"
            ? await api.researchTask(task!.task_id)
            : next === "cancel"
              ? await api.cancelResearchTask(task!.task_id)
              : await api.resumeResearchTask(task!.task_id);
      if (
        !isTaskForSymbol(value, symbol) ||
        (next !== "start" && value.task_id !== task!.task_id)
      )
        throw new Error("Task identity or execution boundary differs");
      setSaved(value);
      setListing((current) =>
        current?.symbol === symbol
          ? {
              ...current,
              items: current.items.map((row) =>
                row?.task_id === value.task_id ? value : row,
              ),
            }
          : current,
      );
    } catch (cause) {
      setError(taskError(cause));
    } finally {
      inFlight.current = false;
      setOperation(undefined);
    }
  }

  return (
    <section aria-label="保留响应研究任务" style={{ marginBlock: 12 }}>
      <h4>保留响应研究任务 · {symbol}</h4>
      <p>
        SAVED_RESPONSE 是已保存响应重放，不是新的 LLM 调用。付费调用为 0；
        仅处理已登记材料，不审批、不改变正式资格、不下单。
        状态仅在点击操作时读取，不自动轮询。刷新页面后可点击
        读取已有任务找回服务端记录； 当前选中任务仅保留在本页，不使用本地存储。
      </p>
      <Space wrap>
        <Button
          disabled={!!operation}
          loading={operation === "history"}
          onClick={() => perform("history")}
        >
          读取已有任务
        </Button>
        <Button
          disabled={!!operation || active}
          loading={operation === "start"}
          onClick={() => perform("start")}
        >
          新增任务
        </Button>
        <Button
          disabled={!!operation || !task}
          loading={operation === "refresh"}
          onClick={() => perform("refresh")}
        >
          手动刷新
        </Button>
        <Button
          disabled={
            !!operation ||
            !task ||
            ["SUCCEEDED", "CANCELLED"].includes(task.status)
          }
          loading={operation === "cancel"}
          onClick={() => perform("cancel")}
        >
          取消任务
        </Button>
        <Button
          disabled={
            !!operation ||
            !task ||
            !["FAILED", "WAITING_EVIDENCE", "RUNNING"].includes(task.status)
          }
          loading={operation === "resume"}
          onClick={() => perform("resume")}
        >
          恢复任务
        </Button>
      </Space>
      {error && (
        <Alert style={{ marginTop: 8 }} type="info" showIcon message={error} />
      )}
      {history && (
        <section aria-label="当前公司已有研究任务" style={{ marginTop: 8 }}>
          <p>仅显示当前公司本次读取的前20条任务；列表不会自动刷新。</p>
          {history.length === 0 ? (
            <p>当前公司暂无可读取的已有任务。</p>
          ) : (
            <ul>
              {history.slice(0, 20).map((item, index) => (
                <li key={index}>
                  {isTaskForSymbol(item, symbol) ? (
                    <>
                      <span>
                        {item.task_id} · {STATUS_LABELS[item.status]}
                        {item.error_code ? " · 错误码：" + item.error_code : ""}
                      </span>{" "}
                      <Button
                        size="small"
                        disabled={!!operation}
                        onClick={() => {
                          if (!inFlight.current) {
                            setSaved(item);
                            setError(undefined);
                          }
                        }}
                      >
                        {"选取任务 " + item.task_id}
                      </Button>
                    </>
                  ) : (
                    <span>任务记录无法核验，未提供操作入口。</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {history.length > 20 && <p>其余任务未在此有限列表展示。</p>}
        </section>
      )}
      {task && (
        <Descriptions
          column={1}
          size="small"
          style={{ marginTop: 8 }}
          items={[
            { key: "task", label: "任务编号", children: task.task_id },
            {
              key: "status",
              label: "任务状态",
              children: STATUS_LABELS[task.status] || task.status,
            },
            { key: "workflow", label: "研究流程", children: task.workflow },
            {
              key: "mode",
              label: "执行方式",
              children:
                task.execution_mode === "SAVED_RESPONSE"
                  ? "已保存响应重放（SAVED_RESPONSE）"
                  : "模拟响应处理（MOCK）",
            },
            {
              key: "snapshot",
              label: "快照核验",
              children: task.snapshot_status,
            },
            {
              key: "checkpoint",
              label: "检查点核验",
              children: task.checkpoint_verified ? "已核验" : "尚未核验",
            },
            {
              key: "findings",
              label: "研究发现数（非审批）",
              children: task.finding_count ?? "尚未产出",
            },
            {
              key: "error",
              label: "任务错误码",
              children: task.error_code || "无",
            },
            { key: "attempts", label: "尝试次数", children: task.attempts },
            {
              key: "requests",
              label: "保留响应处理次数（非新LLM调用）",
              children: task.provider_requests,
            },
            {
              key: "usage",
              label: "模拟用量记账（非付费消耗）",
              children:
                "输入 " +
                task.usage.prompt_tokens +
                " / 输出 " +
                task.usage.completion_tokens,
            },
            {
              key: "binding",
              label: "记录绑定",
              children:
                task.record_binding.path +
                " · SHA-256 " +
                task.record_binding.sha256,
            },
            {
              key: "action",
              label: "操作边界",
              children: "action=no_order；不审批、不改变正式资格",
            },
          ]}
        />
      )}
      {task?.status === "CANCELLED" && (
        <p>已取消任务不会恢复；如需再次处理，可新增任务。</p>
      )}
    </section>
  );
}
