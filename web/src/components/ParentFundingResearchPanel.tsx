import { Alert } from "antd";
import type { ParentFundingReview } from "../services/api";

const FACTS = [
  ["parent_cash_equivalents", "母公司期末现金及现金等价物"],
  ["parent_dividend_payable", "母公司已宣派应付股利（已预留）"],
  ["parent_retained_profit", "母公司未分配利润（账面，非已证法律上限）"],
] as const;
function yi(value: unknown) {
  if (
    typeof value !== "string" ||
    !/^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(value)
  )
    return "未知，不补零";
  const amount = Number(value.replace(/,/g, ""));
  return Number.isFinite(amount)
    ? (amount / 100000000).toLocaleString("en-US", {
        minimumFractionDigits: 4,
        maximumFractionDigits: 4,
      })
    : "未知，不补零";
}
function text(value: unknown) {
  return typeof value === "string" && value && value !== "UNKNOWN"
    ? value
    : "未知，不推定";
}
export function ParentFundingResearchPanel({
  value,
  symbol,
}: {
  value: ParentFundingReview;
  symbol: string;
}) {
  if (
    value.action !== "no_order" ||
    value.formal_eligibility !== false ||
    (value.current_capacity_proven !== undefined &&
      value.current_capacity_proven !== false) ||
    (value.symbol !== undefined && value.symbol !== symbol)
  )
    return (
      <Alert
        type="warning"
        message="母公司资金包身份或边界不符，本区停止展示；其他研究保留"
      />
    );
  if (value.status !== "HISTORICAL_PARENT_REVIEW")
    return (
      <section aria-label="母公司历史资金研究">
        <h3>母公司历史资金研究</h3>
        <Alert
          type="info"
          message={
            value.status === "NOT_STARTED"
              ? "尚无母公司历史资金研究包，不推定资金为零"
              : "母公司资金原件暂不可核验，其他模块保留"
          }
          description={value.reason || value.error_code}
        />
      </section>
    );
  const review = value.review;
  const facts = Array.isArray(review?.evidence) ? review.evidence : [];
  const result = review?.result;
  if (
    value.current_capacity_proven !== false ||
    !review ||
    review.action !== "no_order" ||
    !result ||
    result.action !== "no_order" ||
    result.current_capacity_proven !== false ||
    result.approved !== false ||
    result.status !== "INCOMPLETE_OBLIGATIONS" ||
    result.conditional_distribution_ceiling !== null ||
    result.conditional_shortfall !== null ||
    !review.debt_review ||
    FACTS.some(([field]) => {
      const matches = facts.filter((item) => item.field === field);
      return (
        matches.length !== 1 ||
        matches[0].scope !== "parent" ||
        matches[0].unit !== "CNY" ||
        matches[0].period_end !== review.period
      );
    })
  )
    return (
      <Alert
        type="warning"
        message="历史母公司资金证据或未知义务边界不完整，不能展示可分配上限；其他研究保留"
      />
    );
  const fact = (field: string) => facts.find((item) => item.field === field)!;
  const debt = review.debt_review,
    post = review.post_h1_bridge;
  const pages = [
    ...(review.debt_evidence || []),
    ...(review.historical_capex ? [review.historical_capex] : []),
    ...(review.retained_profit_evidence
      ? [review.retained_profit_evidence]
      : []),
    ...(post?.amount_evidence ? [post.amount_evidence] : []),
    ...(post?.timing_evidence ? [post.timing_evidence] : []),
  ];
  return (
    <section aria-label="母公司历史资金研究">
      <h3>母公司历史资金研究（非今日可分配现金）</h3>
      <p>
        历史基准：{review.period}
        ；仅母公司口径。金额单位亿元，仅作单位换算与展示四舍五入，不在页面重算资金能力。
      </p>
      <Alert
        type="warning"
        message="未知义务尚未补齐，当前可分配能力未证明"
        description="历史现金扣除已宣派股利后的静态余量，绝非今日可分配钱；未分配利润不是现金或已核定的法定分配上限。"
      />
      <table>
        <caption>来源事实与后端静态勾稽（亿元；不是额外分红承诺）</caption>
        <thead>
          <tr>
            <th>项目</th>
            <th>历史金额</th>
          </tr>
        </thead>
        <tbody>
          {FACTS.map(([field, label]) => (
            <tr key={field}>
              <th>{label}</th>
              <td>{yi(fact(field).value)}</td>
            </tr>
          ))}
          <tr>
            <th>期末现金及现金等价物－已宣派股利：静态余量</th>
            <td>{yi(result.static_after_declared_dividend)}</td>
          </tr>
        </tbody>
      </table>
      {value.cash_input_comparison && (
        <>
          <p>
            {value.cash_input_comparison.status ===
            "AMOUNT_EQUAL_NOT_MAPPING_VERIFIED"
              ? "历史静态余额与模型现金输入金额相等；不证明自动派生或来源映射"
              : value.cash_input_comparison.status === "AMOUNT_DIFFERENT"
                ? "历史静态余额与模型现金输入金额不同，须核查；来源映射未证明，不授予资格"
                : "历史静态余额与模型现金输入金额不可评估，不推定相等或来源映射，不授予资格"}
            （{value.cash_input_comparison.status}）。
            {value.cash_input_comparison.reason}
          </p>
          <p>
            历史静态余量：
            {yi(value.cash_input_comparison.source_static_remainder_cny)}
            亿元；模型期初现金：
            {yi(value.cash_input_comparison.model_opening_cash_cny)}亿元；
            模型财务基准：
            {text(value.cash_input_comparison.model_financial_basis)}
            ；原模型口径标签：{text(value.cash_input_comparison.model_scope)}
            （映射未获验证）。
          </p>
          <p>
            该核对不证明owner-equivalent映射/经营准备金/到期义务或法律分配能力，不能把全部资金包当作当前合格。
          </p>
        </>
      )}
      <p>
        条件分配上限：未知（保持空）；条件缺口：未知（保持空）。义务未完整核验，不将空值写成零、不推断有无资金缺口。
      </p>
      <table>
        <caption>母公司待核义务（亿元）</caption>
        <tbody>
          <tr>
            <th>一年内到期的非流动负债</th>
            <td>{yi(debt.parent_current_noncurrent_liabilities)}</td>
            <td>本金与利息拆分未知，不按合并附注推定归母。</td>
          </tr>
          <tr>
            <th>其他应付款（排除股利）</th>
            <td>{yi(debt.other_payables_ex_dividend)}</td>
            <td>现金支付时点：{text(debt.other_payables_cash_timing)}。</td>
          </tr>
        </tbody>
      </table>
      <p>
        合并口径本金、利息与租赁拆分不能归给母公司，也不与母公司义务相加；到期负债与其他应付未被机械全额扣作今日资金用途。
      </p>
      <p>
        历史资本开支已包含在期末现金，不能再扣一次
        {review.historical_capex
          ? "（原件金额：" + review.historical_capex.amount + "元）"
          : ""}
        。
        未来必要投入、经营准备金及法律调整仍须验证；计算参数cash_floor默认为0不等于无需经营准备金。
      </p>
      {post && (
        <section aria-label="H1后股利实施安排">
          <h4>报告期后股利实施安排（非当前母现金滚动证明）</h4>
          <p>
            财政归属：{post.fiscal_attribution}；公告计划日期：
            {post.scheduled_date}。 实施安排不等于账户到账，不属于新年度分红。
          </p>
          <p>
            本项已在H1应付股利中预留，本次新增现金扣减：
            {text(post.additional_cash_deduction)}元，不重复扣除。
            当前母公司现金：未知（保持空），不得把静态余量当作今日余额。
          </p>
        </section>
      )}
      <p>
        本包不批准投资或分红，不生成条件价与个人数量；不修改其他D2、现金或估值结果。
      </p>
      <details>
        <summary>来源绑定、母公司原始事实与逐页证据</summary>
        <p>
          原始母公司事实快照SHA-256：<code>{review.native_sha256}</code>
        </p>
        <ul>
          {facts.map((item, i) => (
            <li key={i}>
              {item.field}：{item.value}元 · {item.scope} · {item.period_end} ·
              物理页 {item.physical_page} · 来源 {item.source_id}
            </li>
          ))}
        </ul>
        <ul>
          {Object.entries(review.sources || {}).map(([id, source]) => (
            <li key={id}>
              {id} · SHA-256 <code>{source.sha256}</code> · 可用时间{" "}
              {text(source.available_at)}
            </li>
          ))}
        </ul>
        {pages.map((page, i) => (
          <section key={i}>
            <p>
              物理页 {page.physical_page} · 原件SHA-256：
              <code>{page.source.sha256}</code>
            </p>
            <blockquote>{page.excerpt}</blockquote>
          </section>
        ))}
      </details>
    </section>
  );
}
