import { useCallback, useState } from "react";
import { Alert, Button, Card, Select } from "antd";
import { Link } from "@umijs/max";
import {
  api,
  type ValueWorkbenchResponse,
  type ValueWorkbenchTask,
} from "../services/api";
import { useApi } from "../hooks/useApi";
import { taskFailure } from "./TransparentTaskControls";

const modules = [
  ["A", "evidence"],
  ["B", "selection"],
  ["C", "profile"],
  ["D2", "assumptions"],
  ["E1", "update_run_not_projected"],
  ["E2", "cash"],
  ["F1", "valuation"],
  ["F2", "price"],
  ["G1", "decision"],
] as const;

export function RuntimeResults({ data }: { data: ValueWorkbenchResponse }) {
  return (
    <>
      <p>
        以下为本次请求实际读取并核验的产物，不是模块工程完成率，也不证明今日执行过扫描。历史期间以原生结果为准。
      </p>
      {modules.map(([id, sectionId]) => {
        const section = data.sections.find((s) => s.id === sectionId);
        return (
          <details key={id}>
            <summary>
              {id} · {section?.title || "未提供产物"} ·{" "}
              {section?.status || "NO_VERIFIED_RECORD"}
            </summary>
            <p>{section?.summary}</p>
            <p>
              该结果不自动证明相邻模块消费了同一次运行；请核对下列版本与绑定。
            </p>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {JSON.stringify(
                {
                  blockers: section?.blockers ?? ["NO_VERIFIED_RECORD"],
                  native_results: section?.data?.native_results,
                  source_bindings: section?.data?.source_bindings,
                },
                null,
                2,
              )}
            </pre>
          </details>
        );
      })}
    </>
  );
}

function CompanyRuntime({ symbol }: { symbol: string }) {
  const loadFirst = useCallback(
    (signal: AbortSignal) => api.firstResearchInput(symbol, signal),
    [symbol],
  );
  const first = useApi(loadFirst);
  const load = useCallback(
    (signal: AbortSignal) => api.valueWorkbench(symbol, signal),
    [symbol],
  );
  const result = useApi(load);
  const [tasks, setTasks] = useState<ValueWorkbenchTask[] | null>(null);
  const [live, setLive] = useState<unknown[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const readTasks = async () => {
    setBusy(true);
    setErrors([]);
    setTasks(null);
    setLive(null);
    const responses = await Promise.allSettled([
      api.valueWorkbenchTasks(symbol),
      api.recentHorizonCashPolicyTasks(),
    ]);
    const messages: string[] = [];
    if (responses[0].status === "fulfilled") setTasks(responses[0].value.items);
    else messages.push("模块任务：" + taskFailure(responses[0].reason));
    if (responses[1].status === "fulfilled")
      setLive(responses[1].value.items.filter((t) => t.symbol === symbol));
    else messages.push("D1/D2模型任务：" + taskFailure(responses[1].reason));
    setErrors([...new Set(messages)]);
    setBusy(false);
  };
  return (
    <>
      <Button onClick={result.retry} disabled={result.loading}>
        重新核验公开产物
      </Button>
      <Link to={`/decisions/${symbol}?strategy=value`}>
        {" "}
        打开公司研究与条件价格
      </Link>
      {result.loading && (
        <p role="status">正在读取来源绑定产物；不启动研究或模型调用。</p>
      )}
      {result.error && (
        <Alert
          type="error"
          message="公开产物读取失败；不是零结果或执行成功。"
        />
      )}
      {!result.loading && !result.error && result.data && (
        <RuntimeResults data={result.data} />
      )}
      <details>
        <summary>E1 → E2/F1/F2 · 当前注册首编与后继版本消费</summary>
        {first.loading && <p>正在核验当前注册回执及后继链。</p>}
        {first.error && <p>当前首编接口读取失败；不显示旧成功结果。</p>}
        {!first.loading && !first.error && first.data && (
          <>
            <p>
              当前首编：{first.data.status}；后继：
              {first.data.successor_update?.status || "未返回后继记录"}
            </p>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {JSON.stringify(first.data, null, 2)}
            </pre>
          </>
        )}
      </details>
      <h3>D1 / D2 / G2 · 实际持久任务</h3>
      <p>
        仅在点击后读取现有任务服务；需要本机研究授权，不读取私人持仓。任务执行成功与经济输入可用分开判断。
      </p>
      <Button onClick={readTasks} loading={busy}>
        读取实际任务记录
      </Button>
      {errors.map((error) => (
        <Alert key={error} type="warning" message={error} />
      ))}
      {tasks !== null && (
        <>
          <p>模块任务 {tasks.length} 条；无记录不等于模块未实现。</p>
          {tasks.map((t) => (
            <details key={t.task_id}>
              <summary>
                {t.module_id} · {t.operation} · {t.status} · {t.task_id}
              </summary>
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {JSON.stringify(
                  {
                    run_id: t.run_id,
                    module_version: t.module_version,
                    started_at: t.started_at,
                    finished_at: t.finished_at,
                    current_step: t.current_step,
                    steps: t.steps,
                    input_binding: t.input_binding,
                    current_validation: t.current_validation,
                    currently_consumable: t.currently_consumable,
                    error: t.error_code,
                    result: t.result,
                    warnings: t.warnings,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))}
        </>
      )}
      {live !== null && (
        <>
          <p>
            D1/D2近期历史任务 {live.length}{" "}
            条（有界列表，不代表全部历史或当前候选）。
          </p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(live, null, 2)}
          </pre>
        </>
      )}
    </>
  );
}

export function ModuleRuntimePanel() {
  const loadCatalog = useCallback(
    (signal: AbortSignal) => api.valueModuleCatalog(signal),
    [],
  );
  const metadata = useApi(loadCatalog);
  const load = useCallback(
    (signal: AbortSignal) => api.valueWorkbenchCompanies(signal),
    [],
  );
  const registered = useApi(load);
  const [symbol, setSymbol] = useState<string>();
  return (
    <Card title="实际运行与产物核验（独立于人工进度说明）">
      <details>
        <summary>当前研究入口与历史版本边界</summary>
        <p>
          仅显式指定V25合同才是当前研究入口。省略版本仍走旧兼容服务，不会自动升级。历史读取与实验创建分别保留，不改写旧证据。
        </p>
        {metadata.error && <p>版本目录读取失败，不能确认当前入口。</p>}
        {!metadata.error &&
          metadata.data?.modules
            .filter((m) => m.version_policy)
            .map((m) => (
              <details key={m.module_id}>
                <summary>
                  {m.module_id} · 当前入口 / 历史读取 / 显式实验
                </summary>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {JSON.stringify(m.version_policy, null, 2)}
                </pre>
              </details>
            ))}
      </details>
      <p>
        公司列表来自当前注册表，不是买入名单。选择公司后读取现有消费者；不会采集新数据、启动模型或修改批准。
      </p>
      {registered.error && (
        <Alert
          type="error"
          message="注册表读取失败，无法确认公司范围；未回退为零公司。"
        />
      )}
      <Select
        aria-label="选择运行核验公司"
        placeholder="选择已注册公司"
        style={{ minWidth: 230 }}
        value={symbol}
        onChange={setSymbol}
        loading={registered.loading}
        options={registered.data?.items.map((row) => ({
          value: row.symbol,
          label: `${row.name || "已注册研究"} · ${row.symbol}`,
        }))}
      />
      {registered.data && (
        <p>注册来源状态：{registered.data.status}；登记不等于已重验。</p>
      )}
      {symbol && <CompanyRuntime key={symbol} symbol={symbol} />}
    </Card>
  );
}
