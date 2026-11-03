import type React from "react";
import { MainValuationRevalidationPanel } from "./MainValuationRevalidationPanel";
import { amount as researchAmount } from "./FirstResearchInputPanel";
import { Readable } from "./LiveOperatingResearchPanel";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, InputNumber, Space } from "antd";
import {
  api,
  ApiError,
  type ValueWorkbenchTask,
  type ValueWorkbenchTaskCreate,
  type ValueWorkbenchTaskHistory,
  type PreparedWorkbenchOperation,
} from "../services/api";

const active = (task?: ValueWorkbenchTask) =>
  !!task && ["QUEUED", "RUNNING"].includes(task.status);
const labels: Record<string, string> = {
  IDLE: "尚未启动",
  QUEUED: "排队中",
  RUNNING: "执行中",
  SUCCESS: "执行成功（非投资批准）",
  PARTIAL: "部分完成，仍有缺口",
  BLOCKED: "阻断，需补齐条件",
  FAILED: "执行失败",
  CANCELLED: "已取消",
};
export function validWorkbenchTask(
  value: unknown,
  symbol: string,
): value is ValueWorkbenchTask {
  const row = value as ValueWorkbenchTask | null;
  return (
    !!row &&
    row.symbol === symbol &&
    typeof row.task_id === "string" &&
    /^rt-[a-f0-9]{32}$/.test(row.task_id) &&
    row.action === "no_order" &&
    row.formal_eligibility === false &&
    row.new_llm_calls === 0 &&
    Object.prototype.hasOwnProperty.call(labels, row.status) &&
    row.native_metadata?.new_llm_calls === 0 &&
    row.native_metadata.approval_changed === false
  );
}
export function taskFailure(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 401)
    return "任务操作需要本机授权；仍可阅读公开研究。";
  if (cause instanceof ApiError && cause.status === 403)
    return "服务端拒绝该操作的授权或能力条件；不自动重试，公开研究仍可阅读。";
  if (cause instanceof ApiError && typeof cause.detail === "string")
    return (
      "任务读取或执行失败：" +
      cause.detail.slice(0, 400) +
      "；原记录保留，可手动刷新，不自动重启。"
    );
  return "任务操作未完成，请核对来源、原生输入或运行限制后手动处理；不会自动重启任务。";
}
export function watchWorkbenchTask(
  symbol: string,
  id: string,
  onValue: (task: ValueWorkbenchTask) => void,
  onError: (error: unknown) => void,
) {
  let stopped = false,
    timer: ReturnType<typeof setTimeout> | undefined;
  const controller = new AbortController();
  const tick = async () => {
    try {
      const value = await api.valueWorkbenchTask(id, controller.signal);
      if (stopped) return;
      if (!validWorkbenchTask(value, symbol) || value.task_id !== id)
        throw new Error("TASK_BINDING_INVALID");
      onValue(value);
      if (active(value)) timer = setTimeout(tick, 3000);
    } catch (cause) {
      if (!stopped) onError(cause);
    }
  };
  timer = setTimeout(tick, 3000);
  return () => {
    stopped = true;
    controller.abort();
    if (timer) clearTimeout(timer);
  };
}
export const SIMULATION_FIELDS: Record<
  string,
  { title: string; unit: string }
> = {
  cost_of_equity: { title: "股权回报要求", unit: "比率" },
  profit_scale: { title: "终值利润规模系数", unit: "倍数" },
  target_payout_ratio: { title: "条件分配比例", unit: "比率" },
  accessible_profit_ratio: { title: "股东可达盈利比例（假设）", unit: "比率" },
  reserve_ratio: { title: "资金准备比例（假设）", unit: "比率" },
  net_maintenance_cash_cny: {
    title: "维护投入净现金（假设）",
    unit: "人民币元",
  },
  operating_wc_cash_cny: {
    title: "营运资金现金变化（假设）",
    unit: "人民币元",
  },
};
const OPERATION_LABELS: Record<string, string> = {
  FRESH_PUBLIC_SCAN: "更新公开初筛",
  VALUE_RESEARCH_REFRESH: "自动筛选与研究补证",
  REPLAY_SELECTION: "重放已绑定筛选",
  RECALCULATE_MAIN: "重算条件估值",
  SIMULATE_ASSUMPTIONS: "调整假设并独立模拟",
  VERIFY_EVIDENCE: "核验原件闭包",
  REVIEW_NOTE: "追加人工复核意见（非批准）",
};
export function preparedTaskPayload(
  row: PreparedWorkbenchOperation | undefined,
  options: {
    network: boolean;
    limit: number;
    scenario: string;
    field: string;
    value: string;
    rationale: string;
    opinion: string;
  },
) {
  if (!row?.enabled || !row.prepared_payload)
    throw new Error("请先读取服务端绑定；当前操作输入不可用");
  const payload = { ...row.prepared_payload };
  if (
    row.operation === "FRESH_PUBLIC_SCAN" ||
    row.operation === "VALUE_RESEARCH_REFRESH"
  ) {
    if (
      !options.network ||
      !Number.isInteger(options.limit) ||
      options.limit < 1 ||
      options.limit > 50
    )
      throw new Error("需明确允许本次公开联网，并选择1–50的范围");
    Object.assign(payload, {
      network_authorized: true,
      ...(row.operation === "VALUE_RESEARCH_REFRESH"
        ? {
            tracking_budget: options.limit,
            source_mode: "FRESH",
            operating_budget: 0,
          }
        : { max_per_channel: options.limit }),
    });
  } else if (row.operation === "SIMULATE_ASSUMPTIONS") {
    if (
      !["bear", "base", "bull"].includes(options.scenario) ||
      !options.rationale.trim() ||
      options.rationale.length > 2000 ||
      options.value.length > 80 ||
      !/^[-]?[0-9]+(?:\.[0-9]+)?$/.test(options.value)
    )
      throw new Error("请提供情景、明确小数数值与理由");
    const annual = /^annual\.(10|[1-9])\.([a-z_]+)$/.exec(options.field);
    const key =
      options.field === "cost_of_equity"
        ? "cost_of_equity"
        : options.field.startsWith("terminal.")
          ? options.field.slice(9)
          : annual?.[2];
    if (
      !key ||
      (key === "cost_of_equity" && options.field !== "cost_of_equity") ||
      !SIMULATION_FIELDS[key] ||
      (key === "profit_scale" && options.field !== "terminal.profit_scale")
    )
      throw new Error("只允许中文白名单内的研究假设");
    Object.assign(payload, {
      scenario: options.scenario,
      changes: [{ field: options.field, value: options.value }],
      rationale: options.rationale.trim(),
    });
  } else if (row.operation === "REVIEW_NOTE") {
    if (!options.opinion.trim() || options.opinion.length > 4000)
      throw new Error("请填写复核意见（最多4000字）");
    payload.opinion = options.opinion.trim();
  }
  return payload;
}
const resultObject = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};
const textValue = (value: unknown) =>
  value == null ? "未提供" : String(value);
const channelNames: Record<string, string> = {
  quality: "质量初筛",
  dividend_cash_return: "现金回报初筛",
  cash_return: "现金回报初筛",
  durable_income: "现金回报初筛",
  value: "价值初筛",
  cyclical: "周期初筛",
};
function TaskSelectionResult({ data }: { data: Record<string, any> }) {
  const coverage = resultObject(data.coverage),
    health = resultObject(data.data_health),
    counts = resultObject(data.channel_counts);
  const scope = resultObject(data.screening_scope);
  const rows = Array.isArray(data.shortlist)
    ? data.shortlist
    : Array.isArray(data.items)
      ? data.items
      : null;
  return (
    <section>
      <h4>本次独立筛选结果（不是当前入池或买入名单）</h4>
      <p>
        资料/行情日期：{textValue(data.quote_date)}；来源可得时点：
        {textValue(data.available_at)}；报告生成：
        {textValue(data.generated_at || data.evaluated_at)}；研究时点：
        {textValue(data.as_of)}。
      </p>
      <p>
        覆盖公司：{textValue(coverage.universe_count ?? health.universe_count)}
        ；已匹配行情：{textValue(health.matched_quote_count)}；缺失行情：
        {textValue(health.missing_quote_count)}；报价冲突：
        {textValue(health.price_conflict_count)}。
      </p>
      <p>
        已覆盖市场：
        {Array.isArray(scope.covered_venues)
          ? scope.covered_venues.join("、")
          : "未提供"}
        ；缺失市场：
        {Array.isArray(scope.failed_venues)
          ? scope.failed_venues.join("、")
          : "未提供"}
        。
        {scope.all_a_complete === true
          ? "来源声明全A范围完整，仍不代表财务事实完整"
          : "未证明全A覆盖完整"}
        。
      </p>
      {data.quote_date_verification === "UNVERIFIED_PROVIDER_TRADE_DATE" && (
        <p>供应商交易日未独立核验，不把日期当作当前合格报价。</p>
      )}
      {Object.keys(counts).length > 0 && (
        <div className="task-result-scroll">
          <table>
            <caption>原生run_once实际通道候选数量</caption>
            <thead>
              <tr>
                <th>通道</th>
                <th>数量</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(counts).map(([key, value]) => (
                <tr key={key}>
                  <td>{channelNames[key] || key}</td>
                  <td>{textValue(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows ? (
        <>
          <p>
            本次返回候选明细{rows.length}
            条；数量以原生输出为准，不假定等于全市场总数。
          </p>
          <div className="task-result-scroll">
            <table>
              <thead>
                <tr>
                  <th>公司</th>
                  <th>通道/状态</th>
                  <th>原始研究理由</th>
                  <th>缺口/排除</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row: any, i: number) => (
                  <tr key={i}>
                    <td>
                      {/^[0-9]{6}$/.test(row.symbol) ? (
                        <a
                          href={"/decisions/" + row.symbol + "?strategy=value"}
                        >
                          {textValue(row.company_name || row.name)} ·{" "}
                          {row.symbol}
                        </a>
                      ) : (
                        <>
                          {textValue(row.company_name || row.name)} ·{" "}
                          {textValue(row.symbol)}
                        </>
                      )}
                    </td>
                    <td>
                      {channelNames[row.channel] ||
                        row.selection_status ||
                        row.channel ||
                        "未提供"}
                    </td>
                    <td>
                      {Array.isArray(row.reasons)
                        ? row.reasons.join("；")
                        : textValue(row.reason || row.explanation)}
                    </td>
                    <td>
                      {Array.isArray(row.blockers)
                        ? row.blockers.join("；")
                        : textValue(row.blockers)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p>
          任务响应尚未提供已核验的候选内容；不从文件路径推断候选为空或筛选成功。
        </p>
      )}
      <details>
        <summary>通道覆盖、来源取得时间与排除细节</summary>
        <Readable
          value={{
            coverage_counts: data.coverage_counts,
            coverage: data.coverage,
            source_times: data.source_times,
            source_bindings: data.source_bindings,
            blockers: data.blockers || health.blockers,
          }}
        />
      </details>
    </section>
  );
}
export function TransparentTaskResult({
  task,
  parameterLabels = SIMULATION_FIELDS,
}: {
  task: ValueWorkbenchTask;
  parameterLabels?: Record<string, { title: string; unit: string }>;
}) {
  if (!task.result)
    return (
      <p>
        本次任务尚未返回可消费的独立结果正文；反馈或文件位置不等于研究结果。
      </p>
    );
  if (
    !validWorkbenchTask(task, task.symbol) ||
    task.current_validation !== "VERIFIED" ||
    task.currently_consumable !== true
  )
    return (
      <Alert
        type="warning"
        message="本次任务输出尚未通过当前来源/输入核验，不展示旧结果正文"
      />
    );
  const packet = resultObject(task.result),
    data = resultObject(packet.result);
  if (
    packet.operation !== task.operation ||
    packet.action !== "no_order" ||
    packet.formal_eligibility !== false ||
    packet.approval_changed !== false ||
    packet.current_published !== false ||
    packet.new_llm_calls !== 0 ||
    !Object.keys(data).length ||
    (data.symbol != null && data.symbol !== task.symbol)
  )
    return (
      <Alert
        type="warning"
        message="任务输出身份、权限或结果合同不符，停止展示"
      />
    );
  let body: React.ReactNode;
  switch (task.operation) {
    case "RECALCULATE_MAIN":
      body = (
        <MainValuationRevalidationPanel value={data} symbol={task.symbol} />
      );
      break;
    case "SIMULATE_ASSUMPTIONS": {
      if (
        data.scope !== "SOURCE_BOUND_USER_ASSUMPTION_SIMULATION_NOT_ADOPTED" ||
        data.action !== "no_order" ||
        data.formal_eligibility !== false ||
        data.main_range_adopted !== false
      )
        return (
          <Alert type="warning" message="模拟结果未采用边界不符，停止展示" />
        );
      const calculation = resultObject(data.calculation),
        baseline = resultObject(data.baseline_calculation),
        ledger = resultObject(data.ledger),
        rows = Array.isArray(ledger.rows) ? ledger.rows : [];
      const metrics = [
        ["条件每股计算值（元/股）", "per_share_value"],
        ["RI股权价值（人民币元）", "conditional_equity_value_cny"],
        [
          "DDM交叉核对股权价值（人民币元）",
          "dividend_crosscheck_equity_value_cny",
        ],
      ] as const;
      body = (
        <section>
          <h4>本次独立条件模拟 · 未采用</h4>
          <p>
            这是共享模型对用户假设的计算，不改变正式研究、事实、批准或当前买价。基线未返回数值就显示未提供，不以页面其他版本顶替。
          </p>
          <div className="task-result-scroll">
            <table>
              <caption>模拟与绑定基线（仅展示后端值，不在Web重算）</caption>
              <thead>
                <tr>
                  <th>指标</th>
                  <th>本次模拟</th>
                  <th>同版本基线</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map(([title, key]) => (
                  <tr key={key}>
                    <td>{title}</td>
                    <td>
                      {researchAmount(
                        key === "per_share_value"
                          ? (calculation.per_share_value ?? calculation.value)
                          : calculation[key],
                      )}
                    </td>
                    <td>
                      {researchAmount(
                        key === "per_share_value"
                          ? (baseline.per_share_value ?? baseline.value)
                          : baseline[key],
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            RI/DDM原始差额（人民币元）：
            <code>
              {textValue(calculation.dividend_crosscheck_difference_cny)}
            </code>
            ；展示四舍五入不代表经济一致性已批准。
          </p>
          <h4>明确提交的变更与理由</h4>
          <ul>
            {(Array.isArray(data.changes) ? data.changes : []).map(
              (change: any, i: number) => {
                const field = String(change.field || ""),
                  key = field.split(".").pop() || "",
                  label = parameterLabels[key];
                return (
                  <li key={i}>
                    {label?.title || "研究假设"}：{textValue(change.value)}（
                    {label?.unit || "单位未提供"}）；适用范围：
                    {field.startsWith("annual.")
                      ? "第" + field.split(".")[1] + "模型年"
                      : field.startsWith("terminal.")
                        ? "终值阶段"
                        : "整条路径"}
                    <details>
                      <summary>原生字段</summary>
                      <code>{field}</code>
                    </details>
                  </li>
                );
              },
            )}
          </ul>
          <p>用户理由：{textValue(data.rationale)}</p>
          <details open>
            <summary>本次模型年度现金账（{rows.length}行）</summary>
            <p>
              金额单位人民币元。旧义务偿付不是本期新分红；完整原值在次级详情保留。
            </p>
            <div className="task-result-scroll">
              <table>
                <thead>
                  <tr>
                    <th>模型年/期间</th>
                    <th>归母利润</th>
                    <th>可达利润</th>
                    <th>必要现金使用</th>
                    <th>新分配</th>
                    <th>期末现金</th>
                    <th>期末净资产</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: any, i: number) => (
                    <tr key={i}>
                      <td>
                        {textValue(row.year)}：{textValue(row.period_start)}～
                        {textValue(row.period_end)}
                      </td>
                      {[
                        "profit",
                        "accessible_profit",
                        "mandatory_cash",
                        "distribution",
                        "closing_cash",
                        "closing_book",
                      ].map((key) => (
                        <td key={key}>{researchAmount(row[key])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length === 0 && <p>本次未提供年度现金行，不补空账本。</p>}
          </details>
          <details>
            <summary>共享模型完整计算、账本与基线绑定</summary>
            <Readable
              value={{
                calculation: data.calculation,
                ledger: data.ledger,
                baseline_binding: data.baseline_binding,
                source_bindings: data.source_bindings,
              }}
            />
          </details>
        </section>
      );
      break;
    }
    case "VALUE_RESEARCH_REFRESH": {
      const latest = resultObject(data.latest_research);
      body = (
        <>
          <p>
            自动筛选与补证周期：{textValue(data.status)}。本轮不产生批准或订单。
          </p>
          <p>
            初筛候选：{textValue(latest.candidate_count)}；研究跟踪：
            {textValue(latest.tracking_count)}。
          </p>
          <p>财务补证完成后仍需企业经营、适用估值与价格核验，不能据此买入。</p>
          <a href="/strategy/value">查看已核验股票池与每家公司的实际缺口</a>
          {data.stop_reason ? (
            <p>停止原因：{textValue(data.stop_reason)}</p>
          ) : null}
          <details>
            <summary>实际阶段、批次与研究记录</summary>
            <pre>
              {JSON.stringify(
                {
                  stages: data.stages,
                  batches: data.batches,
                  operating_research: data.operating_research,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      );
      break;
    }
    case "FRESH_PUBLIC_SCAN":
      body = <TaskSelectionResult data={data} />;
      break;
    case "REPLAY_SELECTION": {
      const selection = resultObject(
        data.selection ?? data.selection_content ?? packet.selection_content,
      );
      body = (
        <>
          <p>这是独立历史筛选重放，不是重新采集或发布当前候选。</p>
          {Object.keys(selection).length ? (
            <TaskSelectionResult data={selection} />
          ) : (
            <>
              <p>
                原生批次状态：{textValue(data.status)}；观察范围：
                {textValue(
                  resultObject(resultObject(data.metrics).coverage)
                    .universe_count,
                )}
                。
              </p>
              <Alert
                type="warning"
                message="本次响应缺少selection内容，不能仅凭selection.json路径展示候选或宣布重放业务完成"
              />
            </>
          )}
        </>
      );
      break;
    }
    case "VERIFY_EVIDENCE": {
      const refs = Array.isArray(data.source_bindings)
        ? data.source_bindings
        : [];
      const valid = refs.every(
        (ref: any) =>
          typeof ref.path === "string" &&
          typeof ref.sha256 === "string" &&
          /^[a-f0-9]{64}$/.test(ref.sha256),
      );
      body = (
        <section>
          <h4>原件闭包核验结果</h4>
          <p>
            包状态：{textValue(data.bundle_status)}；
            {valid
              ? "当前核验绑定文件数：" + refs.length
              : "绑定明细不完整，不能声称文件核验通过"}
            。
          </p>
          <p>
            范围仅为请求报告的来源闭包，不证明完整财报、全市场覆盖、历史PIT或投资资格。
          </p>
          <details>
            <summary>逐文件SHA256范围</summary>
            <ul>
              {refs.map((ref: any, i: number) => (
                <li key={i}>
                  <span>{textValue(ref.path)}</span>
                  <br />
                  <code>{textValue(ref.sha256)}</code>
                </li>
              ))}
            </ul>
          </details>
        </section>
      );
      break;
    }
    case "REVIEW_NOTE":
      if (
        data.scope !== "COMMENT_NOT_G3_APPROVAL" ||
        data.action !== "no_order" ||
        data.formal_eligibility !== false ||
        data.approval_changed !== false ||
        data.signed !== false
      )
        return (
          <Alert
            type="warning"
            message="评论结果权限合同不符，不能展示为独立批准"
          />
        );
      body = (
        <section>
          <h4>已追加的人工复核意见（非G3批准）</h4>
          <blockquote>{textValue(data.opinion)}</blockquote>
          <p>
            记录时间：{textValue(data.recorded_at)}；目标版本SHA256：
            <code>{textValue(resultObject(data.target_binding).sha256)}</code>。
          </p>
          <p>仅登记意见，不签字批准、不改变主研究、正式资格或订单。</p>
          <details>
            <summary>目标原件位置</summary>
            <span>{textValue(resultObject(data.target_binding).path)}</span>
          </details>
        </section>
      );
      break;
    default:
      body = <p>当前操作没有已适配的结果展示，不以原始JSON充当投资解释。</p>;
  }
  return (
    <section aria-label="本次任务独立结果">
      <Alert
        type="info"
        message="本次任务的独立输出：未发布当前、未改变批准，不是当前买价或个人数量"
      />
      {body}
    </section>
  );
}

export function TaskRunFeedback({ task }: { task: ValueWorkbenchTask }) {
  const fields = [
    ["模块", task.module_id],
    ["模块版本", task.module_version],
    ["运行ID", task.run_id],
    [
      "输入版本（原生输入SHA）",
      task.input_binding?.sha256 || task.input_sha256,
    ],
    ["开始时间", task.started_at],
    ["结束时间", task.finished_at],
    ["耗时（秒，服务端观测）", task.duration_seconds],
    ["当前步骤", task.current_step],
  ] as const;
  return (
    <section aria-label="真实运行反馈">
      <h4>真实运行反馈</h4>
      <dl>
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {value == null
                ? label === "开始时间" || label === "运行ID"
                  ? "未提供 / 未开始"
                  : "未提供"
                : String(value)}
            </dd>
          </div>
        ))}
      </dl>
      <p>
        可重试：
        {task.retry_allowed === true
          ? "服务端允许"
          : task.retry_allowed === false
            ? "服务端不允许"
            : "未提供；先刷新任务核对"}
        。耗时不用于估算完成百分比，进度只显示实际完成步骤。
      </p>
      {task.current_validation === "UNASSESSABLE" && (
        <Alert
          type="warning"
          message="历史执行状态保留，但当前输入或来源不可核验，不能当作当前有效成果"
          description={task.current_validation_reason}
        />
      )}
      {task.warnings?.length ? (
        <details>
          <summary>本次运行警告</summary>
          <ul>
            {task.warnings.map((warning, i) => (
              <li key={i}>
                <code>{warning}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
export function TransparentTaskControls({
  symbol,
  onTerminal,
}: {
  symbol: string;
  onTerminal?: () => void;
}) {
  const [task, setTask] = useState<ValueWorkbenchTask>();
  const [items, setItems] = useState<ValueWorkbenchTask[]>([]);
  const [history, setHistory] = useState<ValueWorkbenchTaskHistory["history"]>(
    [],
  );
  const [busy, setBusy] = useState(false);
  const [following, setFollowing] = useState(true);
  const [error, setError] = useState<string>();
  const [network, setNetwork] = useState(false);
  const [limit, setLimit] = useState(30);
  const [prepared, setPrepared] = useState<PreparedWorkbenchOperation[]>([]);
  const [selectedOperation, setSelectedOperation] = useState(
    "VALUE_RESEARCH_REFRESH",
  );
  const [scenario, setScenario] = useState("bear");
  const [parameter, setParameter] = useState("cost_of_equity");
  const [period, setPeriod] = useState("annual");
  const [year, setYear] = useState("1");
  const [decimal, setDecimal] = useState("");
  const [rationale, setRationale] = useState("");
  const [opinion, setOpinion] = useState("");
  const selected = prepared.find((row) => row.operation === selectedOperation);
  const field =
    parameter === "cost_of_equity"
      ? parameter
      : parameter === "profit_scale"
        ? "terminal.profit_scale"
        : (period === "terminal" ? "terminal" : "annual." + year) +
          "." +
          parameter;
  const options = {
    network,
    limit,
    scenario,
    field,
    value: decimal,
    rationale,
    opinion,
  };
  let startReason = "";
  try {
    preparedTaskPayload(selected, options);
  } catch (cause) {
    startReason = cause instanceof Error ? cause.message : "输入尚未齐备";
  }

  const selectedId = useRef<string>();
  const lock = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!task || !active(task) || !following || busy) return;
    return watchWorkbenchTask(
      symbol,
      task.task_id,
      (value) => {
        if (
          lock.current ||
          !mounted.current ||
          selectedId.current !== value.task_id
        )
          return;
        setTask(value);
        setError(undefined);
        if (!active(value)) onTerminal?.();
      },
      (cause) => {
        if (!mounted.current || selectedId.current !== task.task_id) return;
        setError(taskFailure(cause));
        setFollowing(false);
      },
    );
  }, [symbol, task?.task_id, task?.status, following, busy]);
  type Control =
    | "prepare"
    | "list"
    | "history"
    | "refresh"
    | "cancel"
    | "retry"
    | "resume"
    | "start";
  async function perform(operation: Control) {
    if (
      lock.current ||
      (operation === "start" && (!!startReason || active(task)))
    )
      return;
    if (!["prepare", "list", "start"].includes(operation) && !task) return;
    if (operation === "cancel" && !active(task)) return;
    if (operation === "resume" && !task?.resume_required) return;
    if (
      operation === "retry" &&
      (!task ||
        task.retry_allowed !== true ||
        !["FAILED", "BLOCKED", "CANCELLED"].includes(task.status) ||
        task.resume_required)
    )
      return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      if (operation === "prepare") {
        setPrepared([]);
        const result = await api.valueWorkbenchTaskInputs(symbol);
        if (
          result.symbol !== symbol ||
          result.action !== "no_order" ||
          result.formal_eligibility !== false ||
          result.tasks_started !== 0 ||
          !Array.isArray(result.operations)
        )
          throw new Error("PREPARATION_BOUNDARY_INVALID");
        if (mounted.current) setPrepared(result.operations);
        return;
      }
      if (operation === "list") {
        setItems([]);
        const result = await api.valueWorkbenchTasks(symbol);
        if (
          result.action !== "no_order" ||
          result.formal_eligibility !== false ||
          result.symbol !== symbol ||
          !Array.isArray(result.items)
        )
          throw new Error("HISTORY_BINDING_INVALID");
        if (mounted.current) setItems(result.items);
        return;
      }
      if (operation === "history") {
        setHistory([]);
        const result = await api.valueWorkbenchTaskHistory(task!.task_id);
        if (
          result.task_id !== task!.task_id ||
          result.action !== "no_order" ||
          result.formal_eligibility !== false ||
          !Array.isArray(result.history)
        )
          throw new Error("HISTORY_BINDING_INVALID");
        if (mounted.current) setHistory(result.history);
        return;
      }
      const createRequest = (): ValueWorkbenchTaskCreate => ({
        module_id: selected!.module_id,
        operation: selected!.operation,
        symbol,
        timeout_seconds:
          selectedOperation === "VALUE_RESEARCH_REFRESH" ? 1800 : 300,
        request_key:
          "workbench_" +
          Array.from(crypto.getRandomValues(new Uint8Array(16)), (x) =>
            x.toString(16).padStart(2, "0"),
          ).join(""),
        payload: preparedTaskPayload(selected, options),
      });
      const value =
        operation === "start"
          ? await api.createValueWorkbenchTask(createRequest())
          : operation === "refresh"
            ? await api.valueWorkbenchTask(task!.task_id)
            : await api.controlValueWorkbenchTask(
                task!.task_id,
                operation as "cancel" | "retry" | "resume",
              );
      if (
        !validWorkbenchTask(value, symbol) ||
        (operation === "start" && value.operation !== selected!.operation) ||
        (operation !== "start" &&
          operation !== "retry" &&
          value.task_id !== task!.task_id)
      )
        throw new Error("TASK_BINDING_INVALID");
      if (!mounted.current) return;
      selectedId.current = value.task_id;
      setTask(value);
      setHistory([]);
      setFollowing(true);
      if (!active(value)) onTerminal?.();
    } catch (cause) {
      if (operation === "refresh") setFollowing(false);
      if (mounted.current) setError(taskFailure(cause));
    } finally {
      lock.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section aria-label="原生价值研究任务">
      <h2>任务操作与真实进度</h2>
      <p>
        这里执行原生公开数据任务，不调用LLM、不批准投资。浏览器只读取实际任务记录；关页不等于取消后台任务。
      </p>
      <Button disabled={busy} onClick={() => perform("prepare")}>
        读取可执行操作与绑定
      </Button>
      <p>
        服务端自动选择并核验来源；用户无需填写路径、SHA或JSON。准备输入本身不创建任务、不联网采集、不调用模型。
      </p>
      {prepared.length > 0 && (
        <label>
          选择操作
          <select
            value={selectedOperation}
            onChange={(event) => setSelectedOperation(event.target.value)}
          >
            {prepared.map((row) => (
              <option key={row.operation} value={row.operation}>
                {OPERATION_LABELS[row.operation] || row.operation}
                {row.enabled ? "" : "（不可用）"}
              </option>
            ))}
          </select>
        </label>
      )}
      {selected && !selected.enabled && (
        <Alert
          type="warning"
          message="该操作的原生输入尚不可用"
          description={selected.reason || "服务端未提供所需绑定"}
        />
      )}
      {["FRESH_PUBLIC_SCAN", "VALUE_RESEARCH_REFRESH"].includes(
        selectedOperation,
      ) && (
        <>
          <label>
            <input
              type="checkbox"
              checked={network}
              onChange={(event) => setNetwork(event.target.checked)}
            />
            {selectedOperation === "VALUE_RESEARCH_REFRESH"
              ? "允许本次公开扫描、财务原件补证与股票池更新（不下单、不调用付费模型）"
              : "明确允许本次联网更新公开初筛"}
          </label>
          <label>
            {selectedOperation === "VALUE_RESEARCH_REFRESH"
              ? "研究跟踪预算（1–50，不是选股门槛）"
              : "每通道最多观察数量（1–50）"}
            <InputNumber
              min={1}
              max={50}
              precision={0}
              value={limit}
              onChange={(value) =>
                setLimit(
                  typeof value === "number" && Number.isInteger(value)
                    ? Math.min(50, Math.max(1, value))
                    : 10,
                )
              }
            />
          </label>
        </>
      )}
      {selectedOperation === "SIMULATE_ASSUMPTIONS" && (
        <fieldset>
          <legend>独立条件模拟（不改变正式版本）</legend>
          <p>
            每次明确变更一项白名单研究假设；其余基线来自服务端绑定。比率用小数，例如0.10表示10%，不是输入10。
          </p>
          <label>
            情景
            <select
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
            >
              <option value="bear">压力情景</option>
              <option value="base">中间条件情景（未采用Base）</option>
              <option value="bull">修复情景</option>
            </select>
          </label>
          <label>
            参数
            <select
              value={parameter}
              onChange={(event) => setParameter(event.target.value)}
            >
              {Object.entries(SIMULATION_FIELDS).map(([key, item]) => (
                <option key={key} value={key}>
                  {item.title}（{item.unit}）
                </option>
              ))}
            </select>
          </label>
          {!["cost_of_equity", "profit_scale"].includes(parameter) && (
            <>
              <label>
                适用期间
                <select
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                >
                  <option value="annual">指定模型年</option>
                  <option value="terminal">终值阶段</option>
                </select>
              </label>
              {period === "annual" && (
                <label>
                  模型年
                  <select
                    value={year}
                    onChange={(event) => setYear(event.target.value)}
                  >
                    {Array.from({ length: 10 }, (_, i) => (
                      <option key={i} value={String(i + 1)}>
                        第{i + 1}模型年
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          )}
          <label>
            数值（{SIMULATION_FIELDS[parameter].unit}）
            <input
              inputMode="decimal"
              value={decimal}
              onChange={(event) => setDecimal(event.target.value)}
              placeholder="填写明确小数"
            />
          </label>
          <label>
            变更理由与锚点
            <textarea
              value={rationale}
              maxLength={2000}
              onChange={(event) => setRationale(event.target.value)}
            />
          </label>
          <p>
            这里只改研究假设，不改事实、已绑定债务/股利、本金或批准。成功输出独立留存，不自动替换主研究版本。
          </p>
        </fieldset>
      )}
      {selectedOperation === "REVIEW_NOTE" && (
        <label>
          人工复核意见（针对服务端核验的原件版本，非签字批准）
          <textarea
            value={opinion}
            maxLength={4000}
            onChange={(event) => setOpinion(event.target.value)}
          />
        </label>
      )}
      {startReason && <p>执行未启用：{startReason}</p>}
      {error && <Alert type="warning" message={error} />}
      <Space wrap>
        <Button
          disabled={busy || !!startReason || active(task)}
          onClick={() => perform("start")}
        >
          执行所选操作
        </Button>
        <Button disabled={busy} onClick={() => perform("list")}>
          读取任务列表
        </Button>
        <Button disabled={busy || !task} onClick={() => perform("history")}>
          查看所选任务历史
        </Button>
        <Button disabled={busy || !task} onClick={() => perform("refresh")}>
          刷新所选任务
        </Button>
        <Button
          disabled={busy || !active(task)}
          onClick={() => perform("cancel")}
        >
          取消所选任务
        </Button>
        <Button
          disabled={
            busy ||
            !task ||
            task.retry_allowed !== true ||
            !["FAILED", "BLOCKED", "CANCELLED"].includes(task.status) ||
            !!task.resume_required
          }
          onClick={() => perform("retry")}
        >
          重试所选任务
        </Button>
        <Button
          disabled={busy || !task?.resume_required}
          onClick={() => perform("resume")}
        >
          恢复所选任务
        </Button>
        <Button
          disabled={!task || !active(task)}
          onClick={() => setFollowing((value) => !value)}
        >
          {following ? "暂停自动跟踪" : "继续自动跟踪"}
        </Button>
      </Space>
      <p>
        恢复仅用于服务端明确标记需要恢复的中断任务；失败、阻断或已取消任务可新建重试，成功任务不重试。
      </p>
      <p>
        每3秒仅读取所选运行中任务，不重叠请求；终态、失败、切换公司或离页即停止。重试产生新的尝试/子任务，恢复沿原任务，均不冒充先前成功。
      </p>
      <ul>
        {items.map((row, index) => (
          <li key={index}>
            {validWorkbenchTask(row, symbol) ? (
              <Button
                disabled={busy}
                onClick={() => {
                  selectedId.current = row.task_id;
                  setTask(row);
                  setHistory([]);
                  setFollowing(true);
                  setError(undefined);
                }}
              >
                选择任务 {row.task_id} · {labels[row.status]}
              </Button>
            ) : (
              "任务身份或边界不符，不能选择"
            )}
          </li>
        ))}
      </ul>
      {task && (
        <section aria-live="polite">
          <TaskRunFeedback task={task} />
          <TransparentTaskResult task={task} />
          <h3>所选任务：{labels[task.status]}</h3>
          <p>
            {task.task_id} · 操作 {task.operation}
          </p>
          <p>
            已完成步骤：{task.completed_steps ?? "未提供"} /{" "}
            {task.total_steps ?? "未提供"}
            ；仅为真实步骤计数，不是耗时预测百分比。
          </p>
          {task.resume_required && (
            <Alert
              type="warning"
              message="需显式恢复，不能把重启前运行中状态当作成功。"
            />
          )}
          {task.error_code && (
            <Alert
              type="warning"
              message="任务有未解决错误，请查看原始原因后处理"
              description={<code>{task.error_code}</code>}
            />
          )}
          <ol>
            {task.steps?.map((step, i) => (
              <li key={i}>
                {(
                  {
                    VERIFY_INPUT: "核验输入",
                    EXECUTE_NATIVE: "执行原生消费者",
                    VERIFY_OUTPUT: "核验输出",
                  } as Record<string, string>
                )[step.name] || step.name}{" "}
                · {labels[step.status] || step.status}
              </li>
            ))}
          </ol>
          <p>
            新增模型调用0；正式资格未改变，不下单。输出是否完整与来源是否合格须单独核验。
          </p>
        </section>
      )}
      {history.length > 0 && (
        <details open>
          <summary>不可变任务历史（{history.length}条）</summary>
          <ol>
            {history.map((entry, i) => (
              <li key={i}>
                版本{String(entry.record.version ?? i + 1)} ·{" "}
                {String(entry.record.updated_at || "时间未提供")} ·{" "}
                {labels[String(entry.record.status)] ||
                  String(entry.record.status)}
                {Boolean(entry.record.error_code) && (
                  <span> · {String(entry.record.error_code)}</span>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
