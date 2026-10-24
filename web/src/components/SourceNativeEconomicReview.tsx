import { useRef, useState } from "react";
import { Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type {
  EconomicBinding,
  EconomicReview,
} from "../services/sourceNativeEconomicReview";
import {
  verifiedEconomicReview,
  verifiedReplacementBear,
} from "../services/sourceNativeEconomicReview";
import { readinessNumber } from "../utils/strategyReadiness";

const percent = (value: string) =>
  new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Number(value));
const labels = { bear: "保守", base: "基准", bull: "乐观" };

export function EconomicReviewResult({ value }: { value: EconomicReview }) {
  const [scenario, setScenario] = useState<"bear" | "base" | "bull">("base");
  const row = value.scenarios.find((s) => s.scenario === scenario)!;
  return (
    <>
      <p>
        低置信度条件研究；财务基准 {value.share_basis.financial_basis}
        ，历史普通股分母 {readinessNumber(
          value.share_basis.ordinary_shares,
        )}{" "}
        股。未核验当前股本或价格资格。
      </p>
      <label>
        条件情景{" "}
        <select
          aria-label="经济复核情景"
          value={scenario}
          onChange={(event) =>
            setScenario(event.target.value as typeof scenario)
          }
        >
          {(["bear", "base", "bull"] as const).map((name) => (
            <option key={name} value={name}>
              {labels[name]}
            </option>
          ))}
        </select>
      </label>
      <dl className="value-analysis-grid">
        <div>
          <dt>原候选条件值（元/历史股，未批准）</dt>
          <dd>
            {readinessNumber(row.original.candidate_per_historical_share_cny)}
          </dd>
        </div>
        <div>
          <dt>未来股利终值占模型总值</dt>
          <dd>{percent(row.original.ddm_terminal_fraction)}</dd>
        </div>
        <div>
          <dt>RI终端剩余收益占模型总值</dt>
          <dd>{percent(row.original.ri_terminal_fraction)}</dd>
        </div>
        <div>
          <dt>资本成本提高2个百分点的条件值（元/历史股）</dt>
          <dd>
            {row.ke_plus_200bp.status === "CONDITIONAL_KERNEL_SENSITIVITY"
              ? readinessNumber(
                  row.ke_plus_200bp.result!.per_historical_share_cny,
                )
              : "现有内核不支持此挑战"}
          </dd>
        </div>
        <div>
          <dt>首年母公司现金超过分析底线的模型缓冲（元）</dt>
          <dd>
            {readinessNumber(
              row.first_year_boundary.original_cash_above_floor_cny,
            )}
          </dd>
        </div>
        <div>
          <dt>其他假设固定时，首年延迟比例的现金边界</dt>
          <dd>
            {percent(row.first_year_boundary.cash_only_delay_boundary_fraction)}
            {!row.first_year_boundary.boundary_within_zero_one &&
              "（落在0–100%之外，不是可行安全比例）"}
          </dd>
        </div>
      </dl>
      <p>
        两种终端占比口径不同，不能相加。终端占比较高说明价值依赖长期假设；窄幅三情景不能覆盖共同风险。
      </p>
      {value.unsupported_challenges?.length ? (
        <div aria-label="当前模型无法估值的条件">
          <h5>以下条件不输出估值</h5>
          <ul>
            {value.unsupported_challenges.map((item) => (
              <li key={item.id}>{item.reason}</li>
            ))}
          </ul>
          <p>这不是零估值或买卖信号；不得沿用原终端给这些条件计算目标价。</p>
        </div>
      ) : null}
      <p>
        首年现金边界仅为固定盈利、分配、分析底线及付款假设下的关系，不是长期安全阈值、延迟概率或分红保证。资本成本挑战不是当前目标价或获批的新估值。
      </p>
      {value.replacement_bear &&
        verifiedReplacementBear(value.replacement_bear, value) && (
          <section aria-label="经营侵蚀替代bear比较">
            <h5>经营侵蚀替代 bear：未批准的条件研究</h5>
            <p>
              旧 bear{" "}
              {readinessNumber(
                value.replacement_bear.original_bear.per_historical_share_cny,
              )}
              ； 替代 bear{" "}
              {readinessNumber(
                value.replacement_bear.replacement_bear
                  .per_historical_share_cny,
              )}
              ； 差额{" "}
              {readinessNumber(
                value.replacement_bear.difference_per_historical_share_cny,
              )}{" "}
              元／历史股。base/bull 参数及现金路径保持原样。
            </p>
            <p>
              混合实现收入代理不是纯售价；连续五年递推与 H1
              成本率持续全年均为研究假设，季节性或结构恢复可能推翻假设。 仍为
              LOW
              条件研究，不是完整下行、公允价批准、入场价或买入资格。此处沿用首年暂留、次年回款，不是下面的持续暂留逆境。
            </p>
            <ol>
              {value.replacement_bear.operating_rows.map((operating, i) => {
                const cash = value.replacement_bear!.annual_cash_rows[i];
                return (
                  <li key={operating.year}>
                    第{operating.year}年：收入{" "}
                    {readinessNumber(operating.revenue)}元； 经营桥盈利{" "}
                    {readinessNumber(operating.legacy_ex_parent)}元；
                    含增量现金收益盈利 {readinessNumber(cash.profit)}
                    元；期末现金 {readinessNumber(cash.cash_close)}元； 期末权益{" "}
                    {readinessNumber(cash.book_close)}元。
                  </li>
                );
              })}
            </ol>
            <p>
              来源观察时间：{value.replacement_bear.observed_at}
              。反证与否决条件：
            </p>
            <ul>
              {value.replacement_bear.negative_conditions.map(
                (condition, i) => (
                  <li key={i}>{condition}</li>
                ),
              )}
            </ul>
            <details>
              <summary>新旧候选绑定</summary>
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {JSON.stringify(
                  {
                    baseline: value.replacement_bear.baseline_candidate_binding,
                    replacement:
                      value.replacement_bear.replacement_candidate_binding,
                    evidence: value.replacement_bear.evidence_binding,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
        )}
      {value.joint_adverse_cash && (
        <section aria-label="联合逆境现金诊断">
          <h5>盈利下降与持续资金暂留：联合逆境反例</h5>
          {value.joint_adverse_cash.status === "UNSUPPORTED" ? (
            <p>
              证据或计算条件不足，暂不展示逆境数值：
              {value.joint_adverse_cash.reason}
            </p>
          ) : (
            <>
              <p>
                将已披露年度扣非同比{" "}
                {percent(value.joint_adverse_cash.disclosed_annual_growth!)}
                机械重复五年，并假设每年10%资金暂留、五年不回收，保留原项目付款和90%计划分配。
                这是反例，不是盈利预测或公司资金危机判断。
              </p>
              <p>
                {value.joint_adverse_cash.first_cash_failure_year !== null
                  ? `第${value.joint_adverse_cash.first_cash_failure_year}年首次低于母公司现金分析底线。`
                  : "已计算期间未突破母公司现金分析底线。"}
                {value.joint_adverse_cash.first_retained_profit_failure_year !==
                null
                  ? `第${value.joint_adverse_cash.first_retained_profit_failure_year}年首次突破留存利润约束。`
                  : "已计算期间未突破留存利润约束。"}
                暂留资产仍属股东，不把未回收等同永久损失；终端分配不受此诊断支持，不计算新估值或入场价。
              </p>
              <ol>
                {value.joint_adverse_cash.rows.map((cash) => (
                  <li key={cash.year}>
                    第{cash.year}年：归母盈利 {readinessNumber(cash.P)}元；
                    母公司假设资金 {readinessNumber(cash.M)}元； 累计暂留{" "}
                    {readinessNumber(cash.U)}元； 计划分配{" "}
                    {readinessNumber(cash.D)}元； 母公司期末现金{" "}
                    {readinessNumber(cash.C)}元； 现金底线余量{" "}
                    {readinessNumber(cash.cash_margin)}元。
                    {cash.status === "UNFUNDED_PLAN" &&
                      "原分配计划不可满足约束，非实际已支付股息。"}
                  </li>
                ))}
              </ol>
              <p>
                暂留比例与利润留存率均为10%，因此母公司假设资金M与计划分配D抵消。
                这条路径的现金下降来自项目付款及基金调用，不是盈利下降带来的额外现金冲击；不能重复扣减。
                本诊断未证明支付日流动性或法定可分配资格。
              </p>
            </>
          )}
        </section>
      )}
      <h5>五组经济复核仍需判断的事实与假设</h5>
      <ul>
        {value.five_groups.map((group) => (
          <li key={group.id}>
            <strong>{group.title}：</strong>
            {group.interpretation}
          </li>
        ))}
      </ul>
      <p>
        正常化利润未在此确认；主估值、事件有效性、当前价格和用户策略确认仍分别验收。本结果不能直接形成买入或加仓资格。
      </p>
      <details>
        <summary>候选版本与证据引用</summary>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {JSON.stringify(
            {
              candidate: value.candidate_binding,
              sources: value.source_bindings,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </>
  );
}

export function SourceNativeEconomicReview({
  symbol,
  candidate,
}: {
  symbol: string;
  candidate: EconomicBinding;
}) {
  const [value, setValue] = useState<EconomicReview>();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const visible =
    value && verifiedEconomicReview(value, symbol, candidate)
      ? value
      : undefined;
  async function read() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setValue(undefined);
    setError(false);
    try {
      const response = await fetch(
        `/api/v1/value-economic-review/${encodeURIComponent(symbol)}`,
        { cache: "no-store", credentials: "same-origin" },
      );
      if (!response.ok) throw new Error("unavailable");
      const result = await response.json();
      if (!verifiedEconomicReview(result, symbol, candidate))
        throw new Error("identity");
      setValue(result);
    } catch {
      setError(true);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      aria-label="经济复核与共同风险"
      style={{
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        marginBlock: 16,
      }}
    >
      <h4>经济复核与共同风险</h4>
      <Button
        icon={<ReloadOutlined />}
        loading={busy}
        onClick={() => void read()}
      >
        读取经济复核
      </Button>
      {(error || (value && !visible)) && (
        <p role="status">
          当前候选或经济复核来源未能核验，暂不展示本附录数值。请核对候选版本；不影响保留原研究记录。
        </p>
      )}
      {visible && <EconomicReviewResult value={visible} />}
    </section>
  );
}
