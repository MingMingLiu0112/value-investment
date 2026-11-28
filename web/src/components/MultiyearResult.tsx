import type { MultiyearContinuation, MultiyearScenario } from "../services/api";

const names = ["bear", "base", "bull"] as const;
const labels = {
  bear: "承压（Bear）",
  base: "基准（Base）",
  bull: "乐观（Bull）",
};
const payment = {
  CALCULATED_CONDITIONAL: "条件测算",
  BEFORE_FIRST_FAILURE: "通过现金预检",
  NOT_COMPLETED: "支付未完成",
  NOT_REACHED: "未执行",
};
const groups = [
  "scenarios",
  "original_installment_stress",
  "early_maturity_stress",
] as const;
const titles = {
  scenarios: "多年度分期",
  original_installment_stress: "次年集中还款压力",
  early_maturity_stress: "提前到期压力",
};
const decimal = (value: unknown) =>
  typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value);
const yi = (value: string) => (Number(value) / 1e8).toFixed(2);
const digest = (v: unknown) =>
  typeof v === "string" && /^[0-9a-f]{64}$/.test(v);

function validScenario(row: MultiyearScenario) {
  if (
    !row ||
    row.financing_rows_basis !== "CONDITIONAL_PAYMENT_PLAN" ||
    !Array.isArray(row.financing_rows) ||
    !row.financing_rows.every(
      (line) =>
        line &&
        Number.isInteger(line.year) &&
        Object.prototype.hasOwnProperty.call(payment, line.payment_status) &&
        [
          line.known_principal_cny,
          line.assumed_proxy_repayment_cny,
          line.interest_cny,
          line.new_borrowing_cny,
          line.closing_proxy_residual_cny,
        ].every(decimal),
    )
  )
    return false;
  if (row.status === "REJECTED")
    return (
      Number.isInteger(row.first_failed_year) &&
      !!row.reason &&
      [
        row.ledger?.shortfall_cny,
        row.ledger?.remaining_proxy_principal_cny,
      ].every((v) => v === undefined || decimal(v))
    );
  return (
    row.status === "CALCULATED" &&
    row.first_failed_year === null &&
    decimal(row.per_share_value) &&
    Array.isArray(row.annual_rows) &&
    row.annual_rows.length > 0 &&
    row.annual_rows.every(
      (line) =>
        line &&
        Number.isInteger(line.year) &&
        decimal(line.closing_cash_cny) &&
        decimal(line.closing_debt_cny),
    )
  );
}

export function verifyMultiyear(
  value: MultiyearContinuation,
  task: string,
  receipt: string,
  symbol: string,
) {
  const body = value.multiyear_recheck;
  if (
    value.status !== "REPLAYED" ||
    value.continuation_version !== "multiyear-v1" ||
    body?.schema_version !== "parent-cash-multiyear-recheck-v1" ||
    value.task_id !== task ||
    body.task_id !== task ||
    value.receipt_sha256 !== receipt ||
    body.parent_receipt !== receipt ||
    !digest(value.continuation_sha256) ||
    !digest(value.reassessment_spec_sha256) ||
    body.predecessor_input !== value.reassessment_spec_sha256 ||
    value.symbol !== symbol ||
    body.symbol !== symbol ||
    !value.valuation_date ||
    body.valuation_date !== value.valuation_date ||
    value.action !== "no_order" ||
    body.action !== "no_order" ||
    value.formal_eligibility !== false ||
    body.formal_eligibility !== false ||
    value.current_comparable !== false ||
    body.current_comparable !== false ||
    value.new_llm_calls !== 0 ||
    value.new_model_cost_cny !== 0 ||
    body.current_research_range_adopted !== false ||
    body.financing_condition_verified !== false ||
    !body.base_basis ||
    !groups.every((group) =>
      names.every((name) => validScenario(body[group]?.[name])),
    ) ||
    body.unverified_financing_fallback_status !==
      (names.some(
        (name) => body.early_maturity_stress[name].status === "REJECTED",
      )
        ? "REJECTED"
        : "CALCULATED") ||
    body.status !==
      (names.some((name) => body.scenarios[name].status === "REJECTED")
        ? "REJECTED"
        : "CALCULATED")
  )
    throw Error("多年度复算回执无法核验");
  return value;
}

function Rejection({
  row,
}: {
  row: Extract<MultiyearScenario, { status: "REJECTED" }>;
}) {
  return (
    <strong>
      已拒绝 · {row.first_failed_year} 年 · {row.reason}
      {row.ledger?.shortfall_cny !== undefined &&
        "，距现金底线 " + yi(row.ledger.shortfall_cny) + " 亿元"}
      {row.ledger?.remaining_proxy_principal_cny !== undefined &&
        "，终值前尚余本金 " +
          yi(row.ledger.remaining_proxy_principal_cny) +
          " 亿元"}
    </strong>
  );
}

function AnnualPlan({ row }: { row: MultiyearScenario }) {
  const plan = new Map(row.financing_rows.map((line) => [line.year, line]));
  const cash = new Map(
    (row.status === "CALCULATED" ? row.annual_rows : []).map((line) => [
      line.year,
      line,
    ]),
  );
  const years = [...new Set([...plan.keys(), ...cash.keys()])].sort(
    (a, b) => a - b,
  );
  return (
    <>
      {row.status === "REJECTED" ? (
        <Rejection row={row} />
      ) : (
        <p>条件估值 {Number(row.per_share_value).toFixed(4)} 元/股</p>
      )}
      {years.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table>
            <caption>逐年现金与还本计划（亿元）</caption>
            <thead>
              <tr>
                {[
                  "年份",
                  "支付状态",
                  "合同本金到期",
                  "假设偿还未知本金",
                  "假设新增融资",
                  "条件利息",
                  "剩余未知本金",
                  "期末现金",
                  "期末债务",
                ].map((label) => (
                  <th key={label} scope="col">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {years.map((year) => {
                const line = plan.get(year),
                  balance = cash.get(year);
                return (
                  <tr key={year}>
                    <th scope="row">{year}</th>
                    <td>{line ? payment[line.payment_status] : "期初年度"}</td>
                    {[
                      line?.known_principal_cny,
                      line?.assumed_proxy_repayment_cny,
                      line?.new_borrowing_cny,
                      line?.interest_cny,
                      line?.closing_proxy_residual_cny,
                      balance?.closing_cash_cny,
                      balance?.closing_debt_cny,
                    ].map((v, i) => (
                      <td key={i}>{v === undefined ? "—" : yi(v)}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function MultiyearResult({ record }: { record: MultiyearContinuation }) {
  const check = record.multiyear_recheck;
  const stress = check.original_installment_stress.bear;
  const lastPayments = names.flatMap((name) => {
    const row = check.scenarios[name];
    if (row.status !== "CALCULATED") return [];
    const years = row.financing_rows
      .filter((line) => Number(line.assumed_proxy_repayment_cny) > 0)
      .map((line) => line.year);
    return years.length
      ? [labels[name] + "至 " + Math.max(...years) + " 年"]
      : [];
  });
  return (
    <>
      <p>
        原付费任务 {record.paid_task_status} · 本次模型调用{" "}
        {record.new_llm_calls} 次 · 新增模型费用 {record.new_model_cost_cny} 元
      </p>
      <p>
        <strong>连续展期条件</strong>　{lastPayments.join("，")}
        。债权人须允许剩余本金持续保留至各笔计划还款日；中途到期的贷款须逐次取得展期。展期本身没有现金流入，现有证据未确认这些未来展期。
      </p>
      <p>
        <strong>
          展期条件未核实 · 提前到期回退结果
          {check.unverified_financing_fallback_status === "REJECTED"
            ? "已拒绝"
            : "条件测算"}
        </strong>
      </p>
      {stress.status === "REJECTED" && (
        <p>
          <strong>剩余本金集中还款压力 · {labels.bear}</strong>　
          <Rejection row={stress} />
        </p>
      )}
      <p>{check.base_basis}</p>
      <p>
        2025 年末剩余授信 602.15
        亿元，仅证明历史融资渠道。半年报披露流动性管理，DFI
        注册后每期须单独发行。这三项资料均未计入未来可用现金或本次模型的正式依据。{" "}
        <a
          href="https://notice.10jqka.com.cn/api/pdf/65e1b00158579b76.pdf#page=130"
          target="_blank"
          rel="noreferrer"
        >
          第十期超短融基础募集说明书第 130 页
        </a>{" "}
        ·{" "}
        <a
          href="https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF#page=189"
          target="_blank"
          rel="noreferrer"
        >
          2026 半年报物理第 189 页
        </a>{" "}
        ·{" "}
        <a
          href="https://www.nafmii.org.cn/cpxl/zwrzgj/dcmzcfxtzs/DFI/202609/P020260915489390859483.pdf#page=2"
          target="_blank"
          rel="noreferrer"
        >
          DFI 注册通知第 2 页
        </a>
      </p>
      {groups.map((group) => (
        <section key={group} aria-label={titles[group]}>
          <h5>{titles[group]}</h5>
          {names.map((name) => (
            <details key={name} open={group === "scenarios"}>
              <summary>
                {labels[name]} ·{" "}
                {check[group][name].status === "REJECTED"
                  ? "已拒绝"
                  : "条件测算"}
              </summary>
              <AnnualPlan row={check[group][name]} />
            </details>
          ))}
        </section>
      ))}
      <small>当前研究区间未采用 · 封存回执 {record.continuation_sha256}</small>
    </>
  );
}
