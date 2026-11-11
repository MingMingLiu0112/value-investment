import { ValueTrackingResearchPool } from "../../components/ValueTrackingResearchPool";
import { SseMainScreeningPanel } from "../../components/SseMainScreeningPanel";
import "./workbench.css";
import { useCallback, useState } from "react";
import { Link } from "@umijs/max";
import { Alert, Button, Card, Space, Typography } from "antd";
import { api, ApiError, type HorizonCashPolicyTask } from "../../services/api";
import { useApi } from "../../hooks/useApi";
import { Workbench } from "../../components/Workbench";
import { ValueWorkbenchSections } from "../../components/ValueWorkbenchSections";
import { TransparentTaskControls } from "../../components/TransparentTaskControls";
import { LiveOperatingResearchPanel } from "../../components/LiveOperatingResearchPanel";
import { HorizonCashPolicyPanel } from "../../components/HorizonCashPolicyPanel";
import type { SelectionRow } from "../../types/selection";

export function historicalTaskReadError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 401)
    return "本机研究会话未解锁或已过期；请用启动脚本的一次性链接重新打开。";
  if (cause instanceof ApiError && cause.status === 422) {
    const reason =
      typeof cause.detail === "string" &&
      /^[A-Z0-9_:-]{3,160}$/.test(cause.detail)
        ? cause.detail
        : cause.code;
    return "封存任务来源或版本校验未通过：" + reason + "；没有回退旧结果。";
  }
  return "封存研究任务暂不可读；不影响公开候选阅读，也不会启动模型。";
}
export function CandidateChoices({
  items,
  selected,
  onSelect,
}: {
  items: SelectionRow[];
  selected?: string;
  onSelect: (symbol: string) => void;
}) {
  return (
    <section aria-label="实际研究候选">
      <h2>选择要了解的公司</h2>
      <p>来自现有四通道筛选的实际研究候选，不是买入名单。无需输入证券代码。</p>
      <Space wrap>
        {items.map((row, i) => (
          <Button
            key={row.symbol + "-" + i}
            aria-pressed={selected === row.symbol}
            onClick={() => onSelect(row.symbol)}
          >
            {row.company_name || row.name || row.symbol} · {row.symbol}
          </Button>
        ))}
      </Space>
      {items.length === 0 && (
        <Alert
          type="info"
          message="本次没有可显示的研究候选；不补造公司列表，请先核对现有筛选来源。"
        />
      )}
    </section>
  );
}
export function CompanyWorkbench({ symbol }: { symbol: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.valueWorkbench(symbol, signal),
    [symbol],
  );
  const result = useApi(load);
  return (
    <>
      <Space wrap>
        <Button onClick={result.retry} disabled={result.loading}>
          重新读取公开研究
        </Button>
        <Link to={"/decisions/" + symbol + "?strategy=value"}>
          已有公司详情
        </Link>
      </Space>
      <TransparentTaskControls
        key={symbol}
        symbol={symbol}
        onTerminal={result.retry}
      />
      <p>
        <Link
          to={
            "/portfolio?symbol=" +
            encodeURIComponent(symbol) +
            "&strategy=value#portfolio-fill"
          }
        >
          记录已实际发生的成交（进入既有准备/确认）
        </Link>
        ；这里不预填数量、不提交交易或跳过账户核验。
      </p>
      <p>
        公开读取不启动新模型、不刷新来源日期。运行状态、研究是否充分、经济批准与部署版本分开看待。
      </p>
      {result.loading && (
        <p role="status">
          正在读取来源绑定的研究链，期间可能含原生冷重放计算……
        </p>
      )}
      {result.error && (
        <Alert
          type="warning"
          message="本次公开研究读取失败，不显示旧成功结果"
          description={result.error}
        />
      )}
      {!result.loading && !result.error && result.data?.symbol === symbol && (
        <ValueWorkbenchSections value={result.data} symbol={symbol} />
      )}
      <Card title="新的真实经营研究（可选）" style={{ marginTop: 16 }}>
        <p>
          这里复用原有模型授权、预算与任务流程；打开只读配置与公开结果，启动须再显式点击，不会自动调用模型。
        </p>
        <LiveOperatingResearchPanel key={symbol} symbol={symbol} />
        <HorizonCashPolicyPanel key={"cash-policy-" + symbol} symbol={symbol} />
      </Card>
    </>
  );
}
export function selectWorkbenchCompany(
  picked: string | undefined,
  registered: SelectionRow[],
  candidates: SelectionRow[],
  waiting: boolean,
  historicalTaskSymbols: string[] = [],
) {
  return [...registered, ...candidates].some((row) => row.symbol === picked) ||
    historicalTaskSymbols.includes(picked || "")
    ? picked
    : waiting
      ? undefined
      : registered[0]?.symbol || candidates[0]?.symbol;
}
export default function ValueWorkbench() {
  const selection = useApi(api.strategySelection);
  const registered = useApi(api.valueWorkbenchCompanies);
  const [picked, setPicked] = useState<string>();
  const [historicalTasks, setHistoricalTasks] =
    useState<HorizonCashPolicyTask[]>();
  const [historicalError, setHistoricalError] = useState<string>();
  const [historicalBusy, setHistoricalBusy] = useState(false);
  async function readHistoricalTasks() {
    if (historicalBusy) return;
    setHistoricalBusy(true);
    setHistoricalError(undefined);
    try {
      const result = await api.recentHorizonCashPolicyTasks();
      if (
        result.action !== "no_order" ||
        result.scope !== "HISTORICAL_D2_TASKS_NOT_CURRENT_CANDIDATES" ||
        !Array.isArray(result.items) ||
        result.items.some(
          (row) =>
            !/^[0-9]{6}$/.test(row.symbol) ||
            row.action !== "no_order" ||
            row.formal_eligibility !== false ||
            !/^rt-[0-9a-f]{32}$/.test(row.task_id),
        )
      ) {
        throw new Error("INVALID_HISTORICAL_D2_TASK_BOUNDARY");
      }
      setHistoricalTasks(result.items);
    } catch (cause) {
      setHistoricalError(historicalTaskReadError(cause));
    } finally {
      setHistoricalBusy(false);
    }
  }
  const valid = selection.data?.action === "no_order";
  const candidates =
    valid && Array.isArray(selection.data?.value.shortlist)
      ? selection.data.value.shortlist.filter((row) =>
          /^[0-9]{6}$/.test(row.symbol),
        )
      : [];
  const registeredValid =
    registered.data?.action === "no_order" &&
    registered.data.formal_eligibility === false &&
    registered.data.scope ===
      "REGISTERED_RESEARCH_ENTRIES_NOT_CURRENT_SHORTLIST";
  const registeredItems: SelectionRow[] =
    !registered.loading &&
    !registered.error &&
    registeredValid &&
    Array.isArray(registered.data?.items)
      ? registered.data.items
          .filter(
            (row) =>
              /^[0-9]{6}$/.test(row.symbol) &&
              row.action === "no_order" &&
              row.formal_eligibility === false &&
              row.research_verified === false &&
              row.current_candidate === null,
          )
          .map((row) => ({
            symbol: row.symbol,
            name: typeof row.name === "string" ? row.name : undefined,
          }))
          .sort((a, b) => a.symbol.localeCompare(b.symbol))
      : [];
  const symbol = selectWorkbenchCompany(
    picked,
    registeredItems,
    candidates,
    registered.loading,
    historicalTasks?.map((row) => row.symbol),
  );
  return (
    <Workbench>
      <div className="value-workbench">
        <Typography.Title level={2}>价值研究透明工作台</Typography.Title>
        <p>
          从为什么关注一家公司，到经营假设、股东现金、条件估值与当前决定，逐环节查看依据和未解决的问题。
        </p>
        <Space wrap>
          <Link to="/project">模块进度与实现说明</Link>
          <Link to="/system">当前服务与数据状态</Link>
          <Link to="/daily">全部研究候选</Link>
        </Space>
        <Alert
          type="warning"
          message="本工作台提供研究解释与真实任务操作，不批准投资、不读取个人账户、不下单。"
        />
        <ValueTrackingResearchPool load={api.sseResearchQueue} />
        <SseMainScreeningPanel load={api.sseMainScreening} />
        <section aria-label="封存D2研究任务（非当前候选）">
          <h2>封存D2研究任务（非当前候选）</h2>
          <p>
            仅在主动读取后显示已有任务；失败研究也保留，不能据此认定股票值得买入。
          </p>
          <Button disabled={historicalBusy} onClick={readHistoricalTasks}>
            读取封存任务
          </Button>
          {historicalError && (
            <Alert type="warning" message={historicalError} />
          )}
          {historicalTasks && historicalTasks.length === 0 && (
            <p>尚无V10/V11封存任务。</p>
          )}
          <Space wrap>
            {historicalTasks?.map((row) => (
              <Button
                key={row.task_id}
                aria-pressed={symbol === row.symbol}
                onClick={() => setPicked(row.symbol)}
              >
                {row.symbol} · {row.workflow} · {row.status}
              </Button>
            ))}
          </Space>
        </section>
        {selection.loading && <p role="status">正在读取实际候选列表……</p>}
        {selection.error && (
          <Alert
            type="warning"
            message="候选来源读取失败"
            description={selection.error}
          />
        )}
        <Button onClick={selection.retry} disabled={selection.loading}>
          刷新候选列表
        </Button>
        {!selection.loading && !selection.error && valid && (
          <>
            <p>
              筛选资料日期：
              {selection.data?.value.quote_date ||
                selection.data?.value.trade_date ||
                "未提供"}
              ；评估时点：{selection.data?.evaluated_at || "未提供"}。
              {selection.data?.value.screening_scope?.all_a_complete === true
                ? "按来源声明完整覆盖"
                : "覆盖有限，不能称全A当前完成"}
              。
            </p>
            <CandidateChoices
              items={candidates}
              selected={symbol}
              onSelect={setPicked}
            />
          </>
        )}
        <section aria-label="已登记研究">
          <h2>已登记研究（非当前入池）</h2>
          <p>
            按证券代码排序，不是推荐顺序；登记仅说明有研究入口，打开后才重新核验原件与当前实现。不会因当前筛选排除就隐藏旧研究。
          </p>
          <Button disabled={registered.loading} onClick={registered.retry}>
            刷新已登记研究
          </Button>
          {registered.loading && <p role="status">正在读取登记入口……</p>}
          {registered.error && (
            <Alert
              type="warning"
              message="登记入口读取失败，不显示缓存的成功状态"
              description={registered.error}
            />
          )}
          {registered.data?.status === "UNASSESSABLE" && (
            <Alert
              type="warning"
              message="登记来源均不可核验，不等于这些公司没有研究；不使用旧成功替代本次失败。"
            />
          )}
          {registered.data?.status === "PARTIAL" && (
            <p>
              部分登记来源不可读取；其余登记项仍待逐项重验，不能据此称研究已通过。
            </p>
          )}
          <Space wrap>
            {registeredItems.map((row) => (
              <Button
                key={row.symbol}
                aria-pressed={symbol === row.symbol}
                onClick={() => setPicked(row.symbol)}
              >
                {row.name || "已登记研究"} · {row.symbol}
              </Button>
            ))}
          </Space>
          {!registered.loading &&
            !registered.error &&
            registeredValid &&
            registeredItems.length === 0 && (
              <p>当前无可枚举的已登记研究入口，不虚构公司。</p>
            )}
        </section>
        {symbol && <CompanyWorkbench key={symbol} symbol={symbol} />}
        {!selection.loading && !selection.error && !valid && (
          <Alert type="error" message="候选接口边界不符，停止自动选择公司。" />
        )}
      </div>
    </Workbench>
  );
}
