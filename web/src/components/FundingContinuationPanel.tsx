import { MultiyearResult, verifyMultiyear } from "./MultiyearResult";
import closeEvidence from "../config/valueCloseEvidence.v1.json";
import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type FundingContinuation,
  type InstallmentContinuation,
  type MultiyearContinuation,
  type MaturityContinuation,
} from "../services/api";

const lines = [
  ["opening_cash_cny", "年初现金"],
  ["operating_cash_cny", "经营净流入"],
  ["investment_cash_cny", "投资收益收现"],
  ["new_borrowing_cny", "新融资流入"],
  ["known_principal_cny", "按合同到期本金"],
  ["assumed_other_repayment_cny", "期限未明、情景假设当年偿还"],
  ["interest_cny", "付息合计"],
  ["maintenance_capex_cny", "维持投入"],
  ["growth_capex_cny", "增长投入"],
  ["commitments_cny", "资本承诺支出"],
  ["other_required_cash_cny", "其他必要付现"],
  ["cash_before_distribution_cny", "分配前现金"],
  ["floor_cny", "研究假设的最低现金余额"],
  ["shortfall_cny", "低于底线"],
] as const;

const yi = (s: string) => (Number(s) / 1e8).toFixed(2);

type PanelProps = { task: string; receipt: string; symbol: string };
type Replay = FundingContinuation | MaturityContinuation;

const scenarioLabels = { bear: "悲观", base: "基准", bull: "乐观" } as const;
const yiliOriginals = [
  {
    key: "FY25",
    sha: "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac",
    title: "伊利股份 2025 年年度报告",
    url: "https://static.cninfo.com.cn/finalpage/2026-04-30/1225259562.PDF",
    pages: [74, 75],
  },
  {
    key: "9M26",
    sha: "e165e6ee19441a1c0a59199991016bbf78098073981c469f3432e533cb3ce7a0",
    title: "伊利股份 2026 年第三季度报告",
    url: "https://static.cninfo.com.cn/finalpage/2026-10-30/1225644500.PDF",
    pages: [12, 14],
  },
  {
    key: "mtn",
    sha: "edabd3c9460cc610c00b271f9b93b7c21badddfe33d9b3e3cd87afb90fca93e3",
    title: "伊利股份 35 亿元中期票据发行结果公告",
    url: "https://static.cninfo.com.cn/finalpage/2026-10-30/1225644498.PDF",
    pages: [1],
  },
  {
    key: "scp",
    sha: "bb98b2d13f492eed41c090e96156af41c41bdb1ef2a4d4d5a07ae197d5281d19",
    title: "伊利股份五期超短期融资券发行结果公告",
    url: "https://static.cninfo.com.cn/finalpage/2026-10-14/1225603138.PDF",
    pages: [1, 2, 3],
  },
];
const paymentLabels = {
  CALCULATED_CONDITIONAL: "条件测算",
  BEFORE_FIRST_FAILURE: "仅通过现金预检",
  NOT_COMPLETED: "支付未完成",
  NOT_REACHED: "未执行",
} as const;

function OriginalLinks({
  symbol,
  sources,
}: {
  symbol: string;
  sources: Record<string, string>;
}) {
  return (
    <section aria-label="原件链接">
      <h5>已核验原件 · 静态链接目录</h5>
      <ul>
        {Object.entries(sources).map(([key, digest]) => {
          const source =
            symbol === "600887" &&
            yiliOriginals.find(
              (item) => item.key === key && item.sha === digest,
            );
          return (
            <li key={key}>
              {source ? (
                <>
                  {source.title}{" "}
                  {source.pages.map((page) => (
                    <span key={page}>
                      {" "}
                      <a
                        href={source.url + "#page=" + page}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={source.title + "物理页 " + page}
                      >
                        物理页 {page}
                      </a>{" "}
                    </span>
                  ))}
                </>
              ) : (
                key + "（目录无匹配链接）"
              )}{" "}
              <code style={{ overflowWrap: "anywhere" }}>{digest}</code>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const sha256 = /^[0-9a-f]{64}$/;
function verifyReplay(value: Replay, props: PanelProps, maturity: boolean) {
  if (
    value.status !== "REPLAYED" ||
    value.task_id !== props.task ||
    value.receipt_sha256 !== props.receipt ||
    value.action !== "no_order" ||
    !sha256.test(value.continuation_sha256)
  )
    throw Error("回执身份不匹配");
  if (!maturity) {
    if (!("fixed_payment_recheck" in value) || !value.fixed_payment_recheck)
      throw Error("缺少已付款复核");
    return value;
  }
  if (!("maturity_recheck" in value)) throw Error("缺少偿债期限复核");
  const check = value.maturity_recheck;
  if (
    value.continuation_version !== "maturity-v1" ||
    value.symbol !== props.symbol ||
    value.formal_eligibility !== false ||
    value.current_comparable !== false ||
    value.new_llm_calls !== 0 ||
    check?.schema_version !== "parent-cash-maturity-recheck-v1" ||
    check.task_id !== props.task ||
    check.parent_receipt !== props.receipt ||
    check.symbol !== props.symbol ||
    !sha256.test(value.reassessment_spec_sha256) ||
    check.predecessor_input !== value.reassessment_spec_sha256 ||
    !value.valuation_date ||
    check.valuation_date !== value.valuation_date ||
    check.action !== "no_order" ||
    check.formal_eligibility !== false ||
    check.current_comparable !== false ||
    !sha256.test(check.maturity_evidence?.source_matrix_sha256) ||
    !["CALCULATED", "REJECTED"].includes(check.status)
  )
    throw Error("偿债期限复核绑定未通过");
  const evidence = check.maturity_evidence;
  const decimal = (v: unknown) =>
    typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v);
  if (
    !Number.isInteger(evidence.year) ||
    !Number.isInteger(evidence.zero_new_borrowing_from_year) ||
    !Number.isInteger(evidence.first_year) ||
    !evidence.sources ||
    !Object.values(evidence.sources).every(
      (v) => typeof v === "string" && sha256.test(v),
    ) ||
    typeof check.current_research_range_adopted !== "boolean" ||
    ![
      evidence.known_principal_cny,
      evidence.proxy_residual_cny,
      evidence.proxy_repayment_min_cny,
      evidence.proxy_repayment_max_cny,
      evidence.total_repayment_min_cny,
      evidence.total_repayment_max_cny,
      evidence.first_year_issue_proceeds_assumed_at_par_cny,
      evidence.first_year_contractual_maturities_cny,
      evidence.opening_reported_debt_cny,
      evidence.reported_9m_borrowing_cny,
      evidence.reported_9m_repayment_cny,
      evidence.q3_carrying_basket_cny,
      evidence.proxy_minus_basket_cny,
      evidence.q3_short_borrowing_cny,
      evidence.registration_ceiling_cny,
      evidence.observed_issuance_cny,
      evidence.assumed_future_borrowing_cny,
    ].every(decimal) ||
    ![
      evidence.actual_unknown_maturity_cny,
      evidence.actual_total_principal_upper_cny,
    ].every((v) => v === null || decimal(v)) ||
    !evidence.q3_basket_components_cny ||
    !Object.values(evidence.q3_basket_components_cny).every(decimal)
  )
    throw Error("偿债依据不完整");
  for (const group of [check.scenarios, check.alternative_scenarios]) {
    for (const name of ["bear", "base", "bull"] as const) {
      const row = group?.[name];
      if (
        !Array.isArray(row?.financing_rows) ||
        row.financing_rows_basis !== "CONDITIONAL_PAYMENT_PLAN" ||
        !row.financing_rows.every(
          (line) =>
            line &&
            Object.prototype.hasOwnProperty.call(
              paymentLabels,
              line.payment_status,
            ),
        ) ||
        (row.status === "REJECTED" &&
          (!Number.isInteger(row.first_failed_year) || !row.reason)) ||
        (row.status === "CALCULATED" &&
          (row.first_failed_year !== null || !decimal(row.per_share_value))) ||
        !["CALCULATED", "REJECTED"].includes(row.status)
      )
        throw Error("偿债情景记录不完整");
    }
  }
  return value;
}

const cny = (amount: string | null) =>
  amount === null
    ? "未核定"
    : amount.replace(/^(-?\d+)/, (integer) =>
        integer.replace(/\B(?=(\d{3})+(?!\d))/g, ","),
      );
function MaturityResult({ record }: { record: MaturityContinuation }) {
  const check = record.maturity_recheck;
  const evidence = check.maturity_evidence;
  return (
    <>
      <p>
        封存时间 {record.completed_at} · 估值基准日 {record.valuation_date} ·
        原任务 {record.task_id}（{record.paid_task_status}） · 模型调用{" "}
        {record.new_llm_calls} 次
      </p>
      <p>
        续跑回执{" "}
        <code style={{ overflowWrap: "anywhere" }}>
          {record.continuation_sha256}
        </code>
      </p>
      <h5>{evidence.year} 年偿债本金区间（元）</h5>
      <p>
        按已识别合同到期的本金下限 {cny(evidence.known_principal_cny)}
        ，实际全部到期本金上限 {cny(evidence.actual_total_principal_upper_cny)}
        。其余债务实际到期额 {cny(evidence.actual_unknown_maturity_cny)}。
      </p>
      <p>
        模型滚算的剩余本金 {cny(evidence.proxy_residual_cny)}
        。假设从这笔余额中偿还 {cny(evidence.proxy_repayment_min_cny)} 至{" "}
        {cny(evidence.proxy_repayment_max_cny)}{" "}
        元。加上已知到期本金，池内条件还本合计{" "}
        {cny(evidence.total_repayment_min_cny)} 至{" "}
        {cny(evidence.total_repayment_max_cny)} 元。
      </p>
      <details>
        <summary>余额计算依据（元）</summary>
        <p>
          期初报告债务 {cny(evidence.opening_reported_debt_cny)} ＋ 前九个月借款{" "}
          {cny(evidence.reported_9m_borrowing_cny)} − 前九个月还款{" "}
          {cny(evidence.reported_9m_repayment_cny)} ＝ 代理余额{" "}
          {cny(evidence.proxy_residual_cny)}。
        </p>
        <p>
          {evidence.first_year} 年四季度已披露发行{" "}
          {cny(evidence.observed_issuance_cny)} 元，假设按面值到账{" "}
          {cny(evidence.first_year_issue_proceeds_assumed_at_par_cny)}{" "}
          元，按情景扣除当年合同到期{" "}
          {cny(evidence.first_year_contractual_maturities_cny)}{" "}
          元，并单列次年已知到期 {cny(evidence.known_principal_cny)} 元。
        </p>
        <p>
          三季度末账面项目合计 {cny(evidence.q3_carrying_basket_cny)}
          ，代理余额与账面合计相差 {cny(evidence.proxy_minus_basket_cny)}{" "}
          元。合计含其他流动负债整行，可用于对账，逐笔本金仍需核验。
        </p>
        <ul>
          {Object.entries(evidence.q3_basket_components_cny).map(
            ([label, amount]) => (
              <li key={label}>
                {label} {cny(amount)} 元
              </li>
            ),
          )}
        </ul>
        <p>
          三季度末短期借款账面额 {cny(evidence.q3_short_borrowing_cny)}{" "}
          元，一年窗口为 {evidence.short_borrowing_window_start} 至{" "}
          {evidence.short_borrowing_window_end}，窗口内各年的还款分配待核。
        </p>
        <p>
          注册额度上限 {cny(evidence.registration_ceiling_cny)}{" "}
          元，路径假设未来新增借款 {cny(evidence.assumed_future_borrowing_cny)}{" "}
          元。
        </p>
      </details>
      <p>
        原件证据矩阵 SHA-256{" "}
        <code style={{ overflowWrap: "anywhere" }}>
          {evidence.source_matrix_sha256}
        </code>
      </p>
      <OriginalLinks symbol={record.symbol} sources={evidence.sources} />
      <p>
        自{evidence.zero_new_borrowing_from_year}年起假设
        {Number(evidence.assumed_future_borrowing_cny) === 0
          ? "零新增融资"
          : "新增融资 " + cny(evidence.assumed_future_borrowing_cny) + " 元"}
        。
      </p>
      {[check.scenarios, check.alternative_scenarios].some((group) =>
        Object.values(group).some((row) => row.status === "REJECTED"),
      ) && (
        <p>
          拒绝年度及之后列出的还本均为未获现金支持的计划，期末零不代表已还清。
        </p>
      )}
      {(["scenarios", "alternative_scenarios"] as const).map((key) => (
        <section key={key}>
          <h5>
            {(
              {
                FULL_PROXY_REPAYMENT_IN_BOUNDARY_YEAR: `假设 ${evidence.year} 年还清代理余额`,
                KNOWN_ONLY_THEN_FULL_PROXY_REPAYMENT_NEXT_YEAR_STRESS: `假设 ${evidence.year} 年仅偿还已知到期本金，余额结转至 ${evidence.year + 1} 年偿清`,
              } as Record<string, string>
            )[
              key === "scenarios"
                ? check.scenario_basis
                : check.alternative_basis
            ] ?? "其他条件还款计划"}
          </h5>
          {(["bear", "base", "bull"] as const).map((name) => {
            const row = check[key][name];
            return (
              <details key={name}>
                <summary>
                  {scenarioLabels[name]} ·{" "}
                  {row.status === "REJECTED"
                    ? `已拒绝（${row.first_failed_year} 年${row.ledger ? "，缺口 " + yi(row.ledger.shortfall_cny) + " 亿元" : ""}）`
                    : `已计算 · ${Number(row.per_share_value).toFixed(4)} 元／期初普通股`}
                </summary>
                {row.status === "REJECTED" ? (
                  <>
                    <p>
                      拒绝原因 {row.reason}。首次拒绝年份为{" "}
                      {row.first_failed_year} 年。
                    </p>
                    {row.ledger && (
                      <p>
                        {row.ledger.year} 年分配前现金{" "}
                        {yi(row.ledger.cash_before_distribution_cny)}{" "}
                        亿元，最低余额 {yi(row.ledger.floor_cny)} 亿元，缺口{" "}
                        {yi(row.ledger.shortfall_cny)} 亿元。
                      </p>
                    )}
                  </>
                ) : (
                  <p>年度表为本情景的条件还款计划。</p>
                )}
                <div style={{ overflowX: "auto" }}>
                  <table>
                    <caption>情景还款计划（亿元）</caption>
                    <thead>
                      <tr>
                        {[
                          "年",
                          "计划状态",
                          "已知到期本金",
                          "期初代理余额",
                          "假设偿还代理本金",
                          "期末代理余额",
                          "新增借款",
                          "利息",
                        ].map((label) => (
                          <th key={label} scope="col">
                            {label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {row.financing_rows.map((line) => (
                        <tr key={line.year}>
                          <th scope="row">{line.year}</th>
                          <td>{paymentLabels[line.payment_status]}</td>
                          {[
                            line.known_principal_cny,
                            line.opening_proxy_residual_cny,
                            line.assumed_proxy_repayment_cny,
                            line.closing_proxy_residual_cny,
                            line.new_borrowing_cny,
                            line.interest_cny,
                          ].map((value, index) => (
                            <td key={index}>{yi(value)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            );
          })}
        </section>
      ))}
      <p>
        主路径三情景复核{check.status === "REJECTED" ? "已拒绝" : "已计算"}。
        {check.current_research_range_adopted
          ? "已采用当前研究区间。"
          : "当前研究区间未采用。"}
      </p>
    </>
  );
}

function Content({
  task,
  receipt,
  symbol,
  maturity = false,
}: PanelProps & { maturity?: boolean }) {
  const [record, setRecord] = useState<Replay>();
  const [status, setStatus] = useState<
    "reading" | "ready" | "running" | "error" | "done"
  >("reading");
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const read = maturity
      ? api.readMaturityContinuation
      : api.readFundingContinuation;
    setStatus("reading");
    setError("");
    setRecord(undefined);
    read(task, receipt, symbol, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setRecord(verifyReplay(value, { task, receipt, symbol }, maturity));
        setStatus("done");
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        if (
          cause instanceof ApiError &&
          cause.status === 404 &&
          cause.code === "CONTINUATION_NOT_SEALED"
        ) {
          setStatus("ready");
          return;
        }
        setError(
          cause instanceof ApiError && cause.status === 401
            ? "请解锁本机研究会话。"
            : "已有续跑记录无法核验，请刷新历史。",
        );
        setStatus("error");
      });
    return () => controller.abort();
  }, [task, receipt, symbol, maturity, refresh]);

  async function start() {
    if (status !== "ready") return;
    setStatus("running");
    setError("");
    try {
      const run = maturity
        ? api.runMaturityContinuation
        : api.runFundingContinuation;
      const value = await run(task, receipt, symbol);
      setRecord(verifyReplay(value, { task, receipt, symbol }, maturity));
      setStatus("done");
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === "CONTINUATION_IN_PROGRESS"
          ? "同版本正在复算，请稍后刷新历史。"
          : "续跑未取得可核验的回执，请刷新历史。",
      );
      setStatus("error");
    }
  }
  const checked =
    record && "fixed_payment_recheck" in record
      ? record.fixed_payment_recheck
      : undefined;
  return (
    <>
      {status === "reading" && <p>正在读取此版本的续跑记录…</p>}
      {status === "running" && (
        <p role="status">正在核验原件并逐年重算三情景，完成后封存。</p>
      )}
      {status === "ready" && (
        <button onClick={() => void start()}>
          {maturity
            ? "从已封存输入复算偿债期限"
            : "从已封存阶段续跑 V3 现金复核"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {status !== "reading" && status !== "running" && (
        <button onClick={() => setRefresh((n) => n + 1)}>
          {maturity ? "刷新偿债期限历史" : "刷新已付款复核历史"}
        </button>
      )}
      {record && "maturity_recheck" in record && (
        <MaturityResult record={record} />
      )}
      {checked && record && (
        <>
          <p>
            已封存 {record.continuation_sha256.slice(0, 12)} · 原任务{" "}
            {record.task_id} · 模型调用 {record.new_llm_calls} 次
          </p>
          <p>
            {checked.source_payment.through} 已付回购{" "}
            {Number(checked.source_payment.paid_cny).toLocaleString("zh-CN")}{" "}
            元（不含费用），从可选分配移至已付分配，仅计一次。中期分红付款年份仍为假设。
          </p>
          {(["bear", "base", "bull"] as const).map((n) => {
            const row = checked.scenarios[n];
            const l = row.ledger;
            return (
              <section key={n}>
                <strong>
                  {{ bear: "悲观", base: "基准", bull: "乐观" }[n]} ·{" "}
                  {row.status === "CALCULATED" && row.per_share_value
                    ? Number(row.per_share_value).toFixed(2) +
                      " 元／期初普通股（单项）"
                    : "现金底线未通过"}
                </strong>
                {l && (
                  <>
                    <p>
                      {l.year} 年缺口由 {yi(checked.predecessor_shortfall_cny)}{" "}
                      亿元修订为 {yi(l.shortfall_cny)}{" "}
                      亿元。已取消可选分配；当年已排定分配{" "}
                      {yi(l.scheduled_distribution_cny)} 亿元。
                    </p>
                    <table>
                      <caption>{l.year} 年母公司现金对账（亿元）</caption>
                      <tbody>
                        {lines.map(([key, label]) => (
                          <tr key={key}>
                            <th scope="row">{label}</th>
                            <td>{yi(l[key])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p>
                      合同到期日 {l.maturity_dates.join("、")}
                      。总付息中，到期票息 {yi(l.coupon_component_cny)}{" "}
                      亿元，其余融资估计 {yi(l.other_interest_cny)}{" "}
                      亿元。现金底线
                      {l.floor_equals_opening_basis
                        ? "沿用估值基准日的母公司现金余额"
                        : "按本情景设定"}
                      ，作为余额约束。
                    </p>
                    <p>
                      保持其他现金项不变，只偿还已知本金时，分配前现金为{" "}
                      {yi(l.cash_if_unknown_not_due_cny)} 亿元，比底线多{" "}
                      {yi(l.coverage_before_unknown_repayment_cny)}{" "}
                      亿元。剩余本金实际到期日、续借到账情况仍待核验。
                    </p>
                  </>
                )}
              </section>
            );
          })}
          {checked.status === "REJECTED" && (
            <p>完整三情景区间未采用，当前条件价留空。</p>
          )}
        </>
      )}
    </>
  );
}

function InstallmentPanel({
  task,
  receipt,
  symbol,
  multiyear = false,
}: PanelProps & { multiyear?: boolean }) {
  const [record, setRecord] = useState<
    InstallmentContinuation | MultiyearContinuation
  >();
  const title = multiyear ? "多年度分期偿债研究" : "分期偿债研究";
  const label = multiyear
    ? "按多年经营现金续算并封存"
    : "按经营现金分期续算并封存";
  const [status, setStatus] = useState("reading");
  const [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    (multiyear
      ? api
          .readMultiyearContinuation(task, receipt, symbol, controller.signal)
          .then((value) => verifyMultiyear(value, task, receipt, symbol))
      : api.readInstallmentContinuation(
          task,
          receipt,
          symbol,
          controller.signal,
        )
    )
      .then((value) => {
        if (!controller.signal.aborted) {
          setRecord(value);
          setStatus("done");
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (
          error instanceof ApiError &&
          error.status === 404 &&
          error.code === "CONTINUATION_NOT_SEALED"
        )
          setStatus("ready");
        else {
          setMessage(String(error));
          setStatus("error");
        }
      });
    return () => controller.abort();
  }, [task, receipt, symbol, multiyear]);
  async function run() {
    setStatus("running");
    try {
      const value = multiyear
        ? verifyMultiyear(
            await api.runMultiyearContinuation(task, receipt, symbol),
            task,
            receipt,
            symbol,
          )
        : await api.runInstallmentContinuation(task, receipt, symbol);
      setRecord(value);
      setStatus("done");
    } catch (error) {
      setMessage(String(error));
      setStatus("error");
    }
  }
  const linked =
    record?.task_id === task &&
    record?.receipt_sha256 === receipt &&
    record.symbol === symbol &&
    record.action === "no_order" &&
    record.continuation_version ===
      (multiyear ? "multiyear-v1" : "installment-v1");
  return (
    <section aria-label={title}>
      <h5>{title}</h5>
      {status === "ready" && <button onClick={run}>{label}</button>}
      {status === "reading" && <p>正在读取分期研究历史…</p>}
      {status === "running" && (
        <p role="status">正在核验原件、复算并保存三种情景…</p>
      )}
      {status === "error" && (
        <p role="alert">分期研究读取或执行失败。{message}</p>
      )}
      {status === "done" && !linked && <p>回执与当前研究版本无法核对。</p>}
      {linked && record.continuation_version === "multiyear-v1" && (
        <MultiyearResult record={record} />
      )}
      {linked && record.continuation_version === "installment-v1" && (
        <>
          <p>{record.installment_recheck.base_basis}</p>
          {(["bear", "base", "bull"] as const).map((name) => {
            const row = record.installment_recheck.scenarios[name];
            return (
              <div key={name}>
                <strong>
                  {{ bear: "承压", base: "中心", bull: "乐观" }[name]}
                </strong>
                {row.status === "CALCULATED" ? (
                  <span>　条件估值 {row.per_share_value} 元/股</span>
                ) : (
                  <span>
                    　{row.first_failed_year} 年资金约束未通过
                    {row.ledger &&
                      "，距现金底线 " + yi(row.ledger.shortfall_cny) + " 亿元"}
                  </span>
                )}
                {name === "base" &&
                  row.financing_rows.slice(0, 2).map((year) => (
                    <p key={year.year}>
                      {year.year} 年 · 合同本金 {yi(year.known_principal_cny)}{" "}
                      亿元，期限未明本金假设偿还{" "}
                      {yi(year.assumed_proxy_repayment_cny)} 亿元，假设付息{" "}
                      {yi(year.interest_cny)} 亿元，剩余期限未明本金{" "}
                      {yi(year.closing_proxy_residual_cny)} 亿元。
                    </p>
                  ))}
              </div>
            );
          })}
          <small>未批准条件研究 · 封存回执 {record.continuation_sha256}</small>
        </>
      )}
    </section>
  );
}

export function FundingContinuationPanel(props: {
  task: string;
  receipt: string;
  symbol: string;
}) {
  const [opened, setOpened] = useState(false);
  const shareCheck = closeEvidence.market_cap_continuity_check;
  const dividend = closeEvidence.ordinary_dividend_cash_reconciliation;
  const events = closeEvidence.material_event_review;
  return (
    <details
      onToggle={(e) => {
        if (e.target === e.currentTarget) setOpened(e.currentTarget.open);
      }}
    >
      <summary>V3 续跑 · 已付款与偿债对账</summary>
      {opened && (
        <Content key={props.task + props.receipt + props.symbol} {...props} />
      )}
      {props.symbol === closeEvidence.symbol &&
        props.receipt === closeEvidence.parent_receipt && (
          <section>
            {opened && (
              <section aria-label="偿债期限复核">
                <InstallmentPanel
                  key={props.receipt + props.task + props.symbol}
                  {...props}
                />
                <InstallmentPanel
                  key={
                    "multiyear-v1" + props.receipt + props.task + props.symbol
                  }
                  {...props}
                  multiyear
                />
                <h5>偿债期限复核</h5>
                <Content
                  key={
                    "maturity-v1" + props.task + props.receipt + props.symbol
                  }
                  {...props}
                  maturity
                />
              </section>
            )}
            <h5>F2 静态收盘证据快照 · {closeEvidence.date}</h5>
            <p>
              <a
                href={closeEvidence.quote_source}
                target="_blank"
                rel="noreferrer"
              >
                巨潮收盘行情
              </a>{" "}
              {closeEvidence.close.toFixed(2)} 元，行情字段直接给出总股本{" "}
              {closeEvidence.quoted_shares.toLocaleString("zh-CN")}{" "}
              股。与发行人此前披露一致；当日登记股数及期间注销生效链仍待核。
            </p>
            <p>
              <a
                href="https://static.cninfo.com.cn/finalpage/2026-05-29/1225335436.PDF"
                target="_blank"
                rel="noreferrer"
              >
                年度分红实施公告
              </a>
              对应的公司自发毛额测算{" "}
              {Number(closeEvidence.direct_gross).toLocaleString("zh-CN", {
                minimumFractionDigits: 2,
              })}{" "}
              元，结算机构代发毛额测算{" "}
              {Number(closeEvidence.clearing_gross).toLocaleString("zh-CN", {
                minimumFractionDigits: 2,
              })}{" "}
              元。分渠道实付回执：公司自发{" "}
              {cny(dividend.route_settlement_cny.issuer_direct)}
              ，中国结算上海分公司代发{" "}
              {cny(dividend.route_settlement_cny.china_clear_shanghai)}（元）。
            </p>
            {shareCheck.method ===
              "intersection_of_rounded_daily_market_cap_ranges_assuming_constant_shares" && (
              <p>
                {shareCheck.from_date} 至 {shareCheck.through_date} 共{" "}
                {shareCheck.sessions} 个交易日的收盘观测。按市值取整步长{" "}
                {shareCheck.market_cap_rounding_step_cny}{" "}
                元反算，各日区间的交集支持恒定分母假设：总股本{" "}
                {shareCheck.constant_total_shares.toLocaleString("zh-CN")}{" "}
                股，流通股本{" "}
                {shareCheck.constant_float_shares.toLocaleString("zh-CN")}{" "}
                股，匹配 {shareCheck.matched_sessions} 个交易日。单看{" "}
                {shareCheck.through_date} 的取整市值，总股本范围为{" "}
                {shareCheck.close_day_total_shares_range
                  .map((n) => n.toLocaleString("zh-CN"))
                  .join(" 至 ")}{" "}
                股。最近一次发行人精确披露日为{" "}
                {shareCheck.last_exact_issuer_date}
                。逐日登记股数仍待登记凭证核验。测算回执{" "}
                {shareCheck.receipt_sha256.slice(0, 12)}。
              </p>
            )}
            {dividend.scope ===
              "ordinary_share_cash_derived_from_financial_statements" && (
              <p>
                <a href={dividend.source_url} target="_blank" rel="noreferrer">
                  半年报普通股现金合计勾稽
                </a>
                （截至 {dividend.period_end}）：现金分红相关减少额{" "}
                {cny(dividend.cash_decrease_cny)} 元，扣除少数股东股利付现{" "}
                {cny(dividend.minority_dividend_cash_paid_cny)}{" "}
                元，推得普通股现金分红合计{" "}
                {cny(dividend.ordinary_share_cash_cny)} 元。按应付股利变动推得{" "}
                {cny(dividend.payables_implied_cash_cny)} 元，两种口径差额{" "}
                {cny(dividend.reconciliation_difference_cny)}{" "}
                元，普通股应付股利净增加{" "}
                {cny(dividend.ordinary_payable_net_increase_cny)}{" "}
                元。该合计为财务报表勾稽。核验公司自发和结算机构代发各自的实际付现金额仍需分渠道付款凭证。勾稽回执{" "}
                {dividend.receipt_sha256.slice(0, 12)}。
              </p>
            )}
            {events.scope ===
              "matched_public_announcements_for_registered_candidate" && (
              <section>
                <h5>候选材料性审核</h5>
                <ul>
                  {closeEvidence.public_event_followup.map(
                    ({ summary, source_url }) => (
                      <li key={source_url}>
                        {summary}{" "}
                        <a href={source_url} target="_blank" rel="noreferrer">
                          公告原件
                        </a>
                      </li>
                    ),
                  )}
                </ul>
                <p>
                  两站目录匹配原件 {events.matched_originals} 份，本候选已批准{" "}
                  {events.candidate_approved} 份，尚缺本候选材料性批准{" "}
                  {events.without_candidate_approval} 份。登记候选{" "}
                  {closeEvidence.registered_candidate.slice(0, 12)}。
                </p>
                <p>
                  目录完整覆盖至 {events.complete_through}。巨潮于{" "}
                  {events.cninfo_day_observed_at} 观测当日{" "}
                  {events.cninfo_day_count} 条，上交所于{" "}
                  {events.sse_day_observed_at} 观测当日 {events.sse_day_count}{" "}
                  条。
                  {events.full_day_elapsed ? (
                    "当日已结束。"
                  ) : (
                    <>
                      当日尚未结束，最早完整日复核时间{" "}
                      {events.earliest_full_day_recheck}。
                    </>
                  )}
                </p>
              </section>
            )}
            <small>
              收盘后取证 · F2 回执 {closeEvidence.report_sha256.slice(0, 12)}
            </small>
          </section>
        )}
    </details>
  );
}
