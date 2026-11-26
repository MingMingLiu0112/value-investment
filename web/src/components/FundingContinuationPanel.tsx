import closeEvidence from "../config/valueCloseEvidence.v1.json";
import { useEffect, useState } from "react";
import { api, ApiError, type FundingContinuation } from "../services/api";

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

function Content({
  task,
  receipt,
  symbol,
}: {
  task: string;
  receipt: string;
  symbol: string;
}) {
  const [record, setRecord] = useState<FundingContinuation>();
  const [status, setStatus] = useState<
    "reading" | "ready" | "running" | "error" | "done"
  >("reading");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api
      .readFundingContinuation(task, receipt, symbol, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (
          value.status !== "REPLAYED" ||
          value.task_id !== task ||
          value.receipt_sha256 !== receipt ||
          value.action !== "no_order"
        )
          throw Error();
        setRecord(value);
        setStatus("done");
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          if (
            cause instanceof ApiError &&
            cause.code === "CONTINUATION_NOT_SEALED"
          ) {
            setStatus("ready");
            return;
          }
          setError(
            cause instanceof ApiError && cause.status === 401
              ? "请解锁本机研究会话。"
              : "已有续跑记录无法核验，请重新打开。",
          );
          setStatus("error");
        }
      });
    return () => controller.abort();
  }, [task, receipt, symbol]);
  async function start() {
    setStatus("running");
    setError("");
    try {
      const result = await api.runFundingContinuation(task, receipt, symbol);
      if (
        result.status !== "REPLAYED" ||
        result.task_id !== task ||
        result.receipt_sha256 !== receipt ||
        result.action !== "no_order"
      )
        throw Error();
      setRecord(result);
      setStatus("done");
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "同版本正在复算或仅供归档读取，请稍后重新打开查看。"
          : "续跑未取得可核验的回执，请重新打开读取任务历史。",
      );
      setStatus("error");
    }
  }
  const checked = record?.fixed_payment_recheck;
  return (
    <>
      {status === "reading" && <p>正在读取此版本的续跑记录…</p>}
      {status === "running" && (
        <p role="status">正在核验原件并逐年重算三情景，完成后封存。</p>
      )}
      {status === "ready" && (
        <button onClick={() => void start()}>
          从已封存阶段续跑 V3 现金复核
        </button>
      )}
      {error && <p role="alert">{error}</p>}
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

export function FundingContinuationPanel(props: {
  task: string;
  receipt: string;
  symbol: string;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      onToggle={(e) => {
        if (e.target === e.currentTarget) setOpened(e.currentTarget.open);
      }}
    >
      <summary>V3 续跑 · 已付款与偿债对账</summary>
      {opened && <Content {...props} />}
      {props.symbol === closeEvidence.symbol &&
        props.receipt === closeEvidence.parent_receipt && (
          <section>
            <h5>F2 收盘证据快照 · {closeEvidence.date}</h5>
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
              元。两路实付凭证待核，中期方案尚缺付款证明。
            </p>
            <p>
              上交所与巨潮公告目录匹配 {closeEvidence.matched}{" "}
              条；完整自然日覆盖至 {closeEvidence.past_complete}
              ，已完成候选材料性批准 {
                closeEvidence.materiality
              } 条。登记候选 {closeEvidence.registered_candidate.slice(0, 12)}{" "}
              与本次融资修订分别核验，当前条件价留空。
            </p>
            <small>
              收盘后取证 · F2 回执 {closeEvidence.report_sha256.slice(0, 12)}
            </small>
          </section>
        )}
    </details>
  );
}
