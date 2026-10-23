import type { PolicyHandoff } from "../services/valuePolicy";
import {
  jointCapitalReviewMatches,
  jointRowFields,
  jointTerminalFields,
} from "../services/valuePolicy";

const limitations: Record<string, string> = {
  "Maintenance equals scaled DA only by assumption.":
    "维持资本开支等于按收入缩放的折旧摊销，仅为假设。",
  "Parent cash conversion and terminal marginal return remain unapproved.":
    "归母盈利现金转换及终端边际回报仍未获批准。",
};

const names: Record<string, string> = {
  bear: "谨慎情景",
  base: "中性条件情景",
  bull: "乐观情景",
  revenue: "营业收入",
  cost: "营业成本",
  legacy_pre_tax_profit: "存量业务税前盈利",
  legacy_parent_profit: "存量业务归母盈利",
  new_operating_profit: "新增经营资本盈利",
  new_liquidity_profit: "新增流动资本盈利",
  profit: "归母盈利合计",
  opening_book: "期初权益",
  roe: "当年 ROE（非 ROIC）",
  retained: "留存盈利",
  dividend: "条件分配金额",
  closing_book: "期末权益",
  net_operating_addition: "新增经营资本",
  net_liquidity_addition: "新增流动资本",
  maintenance_capex_assumption: "维持资本开支假设",
  cash_open: "期初现金代理",
  cash_close: "期末现金代理",
  retention: "盈利留存比例",
  operating_allocation: "留存转经营资本比例",
  new_operating_return: "新增经营资本回报假设",
  new_liquidity_return: "新增流动资本回报假设",
  parent_cash_conversion: "归母盈利现金转换假设",
  terminal_growth: "终端增长假设",
  terminal_profit_scale: "终端盈利缩放倍数",
  terminal_roe: "终端 ROE 假设（非已验证 ROIC）",
  terminal_profit: "终端盈利",
  terminal_book: "终端权益",
  terminal_retention: "终端留存比例",
  terminal_net_operating_investment: "终端新增经营投入",
  terminal_new_liquidity_investment: "终端新增流动投入",
  terminal_dividend: "终端条件分配",
  revenue_growth: "收入增速假设",
  cost_ratio: "成本率假设",
};
const ratios = new Set([
  "roe",
  "retention",
  "operating_allocation",
  "new_operating_return",
  "new_liquidity_return",
  "parent_cash_conversion",
  "terminal_growth",
  "terminal_roe",
  "terminal_retention",
  "revenue_growth",
  "cost_ratio",
]);

function Value({ name, value }: { name: string; value: unknown }) {
  const number = Number(value);
  const display =
    name === "terminal_profit_scale"
      ? `${number.toFixed(2)} 倍`
      : ratios.has(name)
        ? `${(number * 100).toFixed(2)}%`
        : `${(number / 1e8).toFixed(2)} 亿元`;
  return (
    <div style={{ minWidth: 0 }}>
      <dt>{names[name] ?? name}</dt>
      <dd style={{ marginLeft: 0 }}>
        {display}
        <details>
          <summary>
            完整值
            {ratios.has(name)
              ? "（比例）"
              : name === "terminal_profit_scale"
                ? "（倍数）"
                : "（元）"}
          </summary>
          <code>{String(value)}</code>
        </details>
      </dd>
    </div>
  );
}

function Funding({ status }: { status: string }) {
  return status === "FAIL" ? (
    <p role="alert">
      FAIL：假设路径存在现金资金缺口；负值按原账本保留，不能认定可分红。
    </p>
  ) : (
    <p>
      PASS：仅表示本组假设下的现金资金演算通过，不代表可分红能力、经济假设或策略批准。
    </p>
  );
}

export function JointCapitalReview({
  handoff,
  symbol,
}: {
  handoff: PolicyHandoff;
  symbol: string;
}) {
  if (
    handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED" ||
    !handoff.economic_review_materials?.joint_capital_review
  )
    return null;
  if (!jointCapitalReviewMatches(handoff, symbol))
    return (
      <p role="alert">
        联合资本路径字段缺失、数值无效或身份绑定不一致，暂不可展示为核验账本；请重新读取。
      </p>
    );
  const review = handoff.economic_review_materials.joint_capital_review;
  return (
    <section
      aria-label="联合资本路径待审"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h4>联合资本路径：三情景五年条件演算</h4>
      <p>
        以下全部未来年度均为未获批准的研究假设，不是正常化事实或分红承诺。现金与资金口径为
        proxy（代理），不证明母公司现金可上划或法定可分配。
      </p>
      {review.date_scope === "DATED_CONDITIONAL_MODEL" ? (
        <p>
          资料基准：{review.basis_at}；估值时点：{review.valuation_at}
          。不是最新行情日期。
        </p>
      ) : (
        <p role="alert">
          未建立定价时点：旧模型无已绑定的资料基准／估值日期；仅为未定日条件模型，不能当作当前价值。
        </p>
      )}
      <p>盈利 → 留存 → 经营资本／流动资本 → 条件分配 → 期末权益与现金代理</p>
      {review.scenarios.map((scenario) => (
        <details key={scenario.scenario} open>
          <summary>{names[scenario.scenario]} · 待审假设</summary>
          <p>
            条件估值：{Number(scenario.valuation_per_share).toFixed(2)}{" "}
            元／股；不是批准主估值或交易价格。
          </p>
          <details>
            <summary>每股估值完整值（元／股）</summary>
            <code>{scenario.valuation_per_share}</code>
          </details>
          <Funding status={scenario.ledger.cash_funding_status} />
          <h5>共同驱动假设</h5>
          <dl
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(min(100%,220px),1fr))",
              gap: 12,
            }}
          >
            {Object.entries(scenario.drivers)
              .filter(([key]) => key !== "years")
              .map(([key, value]) => (
                <Value key={key} name={key} value={value} />
              ))}
          </dl>
          {scenario.ledger.rows.map((row, index) => (
            <details key={row.year}>
              <summary>
                第 {row.year} 年 · 未来假设 ·{" "}
                {row.cash_funding_status === "FAIL"
                  ? "资金演算 FAIL，有缺口"
                  : "资金演算 PASS，非批准"}
              </summary>
              <Funding status={String(row.cash_funding_status)} />
              <dl
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit,minmax(min(100%,220px),1fr))",
                  gap: 12,
                }}
              >
                <Value
                  name="revenue_growth"
                  value={scenario.drivers.years[index].revenue_growth}
                />
                <Value
                  name="cost_ratio"
                  value={scenario.drivers.years[index].cost_ratio}
                />
                {jointRowFields.map((key) => (
                  <Value key={key} name={key} value={row[key]} />
                ))}
              </dl>
            </details>
          ))}
          <details>
            <summary>终端条件（仍属假设）</summary>
            <p>
              终端 ROE 不等于已验证
              ROIC；终端增长、再投入与分配约束仍须经济判断。
            </p>
            <dl
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit,minmax(min(100%,220px),1fr))",
                gap: 12,
              }}
            >
              {jointTerminalFields.map((key) => (
                <Value key={key} name={key} value={scenario.ledger[key]} />
              ))}
            </dl>
          </details>
          <h5>反证与未解决条件</h5>
          <p>
            若归母现金转换不足、维持投入高于折旧摊销代理，或新增资本回报下降，本路径可能无法支持所列分配。以下限制来自原账本；具体反证见本次五组待审材料。
          </p>
          <ul>
            {scenario.ledger.limitations.map((text, index) => (
              <li key={index}>{limitations[text] ?? text}</li>
            ))}
          </ul>
        </details>
      ))}
      <details>
        <summary>原候选、提案与政策版本</summary>
        <p>
          选择：{review.selected_choice}；输入：
          <code>{review.input_descriptor_sha256}</code>
        </p>
        {[
          review.candidate_binding,
          review.proposal_binding,
          review.policy_binding,
        ].map((item, i) => (
          <p key={i}>
            <code>{item.path}</code>
            <br />
            <code>{item.sha256}</code>
          </p>
        ))}
      </details>
      <p>
        只读材料；正式批准、价格资格、仓位与操作状态均不改变。action=no_order。
      </p>
    </section>
  );
}
