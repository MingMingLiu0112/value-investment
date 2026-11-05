import type { AccountingBridgeReview as Review } from "../types/api";
import { readinessNumber } from "../utils/strategyReadiness";

const terms: Record<string, string> = {
  opening_cash_and_equivalents_cny: "期初现金及等价物",
  cfo_cny: "经营现金净流量",
  cfi_cny: "投资现金净流量",
  cff_cny: "筹资现金净流量",
  opening_equity_cny: "期初权益",
  net_profit_cny: "本期利润",
  distribution_signed_cny: "股东分配变动",
  net_owner_capital_change_signed_cny: "股东资本净变动",
};

function filingUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

export function AccountingBridgeReview({
  review,
  symbol,
  descriptor,
}: {
  review: Review | undefined;
  symbol: string;
  descriptor: string | undefined;
}) {
  if (!review) return null;
  const bound =
    review.schema_version === "economic-review-bundle-v1" &&
    review.symbol === symbol &&
    review.action === "no_order" &&
    review.primary_valuation_usable === false &&
    review.economic_approval_granted === false &&
    !!descriptor &&
    /^[a-f0-9]{64}$/.test(descriptor) &&
    review.input_descriptor_sha256 === descriptor &&
    /^[a-f0-9]{64}$/.test(review.bundle_sha256) &&
    Array.isArray(review.source_bindings) &&
    review.source_bindings.length > 0 &&
    Array.isArray(review.bridge_results) &&
    Array.isArray(review.unknown_fields);
  if (!bound)
    return (
      <p role="status">财务桥接材料与当前估值版本未匹配，暂不展示金额。</p>
    );
  if (review.status === "NO_SUPPORTED_BOUND_BRIDGE")
    return <p>当前估值版本尚无可核验的历史现金与权益桥接材料。</p>;
  const rows = review.bridge_results;
  if (
    review.status !== "HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL" ||
    rows.length === 0 ||
    rows.some(
      (row) =>
        row.unit !== "CNY" ||
        row.assurance !==
          "BOUND_RESEARCH_ARITHMETIC_NOT_NEW_PDF_ROW_CERTIFICATION" ||
        !review.source_bindings.some(
          (binding) =>
            binding.path === row.source_binding?.path &&
            binding.sha256 === row.source_binding?.sha256 &&
            /^[a-f0-9]{64}$/.test(binding.sha256),
        ),
    )
  )
    return <p role="status">历史财务桥接未完成核验，暂不展示金额。</p>;
  return (
    <details className="accounting-bridge-review">
      <summary>历史现金与权益核验 · {rows.length} 项</summary>
      <p>
        已核对留存材料和计算关系；其中派生调节项仍需对照财报原文，不能据此认定未来分红能力或主估值已通过。
      </p>
      {rows.map((row) => (
        <section key={`${row.kind}-${row.period}-${row.entity_scope}`}>
          <h4>
            {row.period === "FY2025"
              ? "2025 年度"
              : row.period === "H1_2026"
                ? "2026 年上半年"
                : row.period}
            {" · "}
            {row.entity_scope === "issuer_parent_standalone"
              ? "上市母公司"
              : "合并归母"}
            {row.kind === "parent_cash" ? "现金" : "权益"}
          </h4>
          <dl className="value-analysis-grid">
            <div>
              <dt>重算期末余额（元）</dt>
              <dd>{readinessNumber(row.computed_closing_cny)}</dd>
            </div>
            <div>
              <dt>材料期末余额（元）</dt>
              <dd>{readinessNumber(row.reported_closing_cny)}</dd>
            </div>
            <div>
              <dt>核对差额（元）</dt>
              <dd>{readinessNumber(row.difference_cny)}</dd>
            </div>
          </dl>
          <details>
            <summary>计算项与财报出处</summary>
            <dl className="value-analysis-inputs">
              {Object.entries(row.terms).map(([name, value]) => (
                <div key={name}>
                  <dt>{terms[name] || name}（元）</dt>
                  <dd>{readinessNumber(value)}</dd>
                </div>
              ))}
              <div>
                <dt>
                  {row.reported_adjustment === null
                    ? "派生调节项（未独立核验原文，元）"
                    : "材料列示调节项（元）"}
                </dt>
                <dd>
                  {readinessNumber(
                    row.reported_adjustment ?? row.derived_adjustment_cny,
                  )}
                </dd>
              </div>
            </dl>
            <p>财报物理页码：{row.physical_pages.join("、")}</p>
            {filingUrl(row.source_url) ? (
              <a
                href={filingUrl(row.source_url)}
                target="_blank"
                rel="noopener noreferrer"
              >
                查看财报原文
              </a>
            ) : (
              <p>原文链接不可用</p>
            )}
            <code>SHA-256 {row.source_binding.sha256}</code>
          </details>
        </section>
      ))}
      <p>
        {review.unknown_fields.length > 0
          ? `材料保留 ${review.unknown_fields.length} 处未确定字段，前瞻经济审核仍未完成。`
          : "未列出空值不代表经济假设已获审核。"}
      </p>
      <code>审核材料指纹 {review.bundle_sha256}</code>
    </details>
  );
}
