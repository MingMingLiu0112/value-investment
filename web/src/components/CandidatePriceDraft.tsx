import type { JointCapitalReview } from "../services/valuePolicy";

type Review = Readonly<JointCapitalReview>;
const numberText = (value: unknown) =>
  typeof value === "string" &&
  /^\d+(\.\d+)?$/.test(value) &&
  Number.isFinite(Number(value)) &&
  Number(value) > 0;

export function candidatePriceMatches(review: Review): boolean {
  try {
    const price = review.conditional_price;
    if (
      !price ||
      price.status !== "researcher_proposal" ||
      price.schema_version !== "pending-candidate-conditional-price-v1" ||
      price.action !== "no_order" ||
      price.formal_eligibility !== false ||
      price.user_approved !== false ||
      price.formally_prepared !== false ||
      price.quantities !== null ||
      price.sourcebindings?.candidate_sha256 !==
        review.candidate_binding.sha256 ||
      price.price_comparison?.currentpricecomparison !== false ||
      !price.draft ||
      price.draft.basis.symbol !== review.symbol ||
      !price.draft_prices ||
      price.draft_prices.add !== null ||
      price.draft_prices.exit !== null
    )
      return false;
    if (
      !Array.isArray(price.draft.rules) ||
      price.draft.rules.length !== 2 ||
      !Array.isArray(price.reopenconditions) ||
      !price.reopenconditions.every((item) => typeof item === "string") ||
      !price.proposal_validity ||
      typeof price.proposal_validity.current_valid !== "boolean" ||
      ![
        price.draft.rationale,
        price.draft.dividend_coverage_risk,
        price.draft.policy_id,
        price.draft.rule_version,
        price.draft.basis.valuation_date,
        price.proposal_validity.available_at,
        price.proposal_validity.expires_at,
        price.sourcebindings?.policy_artifact_sha256,
      ].every((item) => typeof item === "string" && item.length > 0)
    )
      return false;
    return (
      [
        ["entry", "bear"],
        ["reduce", "bull"],
      ] as const
    ).every(([action, scenario]) => {
      const rows = price.draft!.rules.filter((rule) => rule.action === action);
      const value = review.scenarios.find(
        (row) => row.scenario === scenario,
      )?.valuation_per_share;
      return (
        rows.length === 1 &&
        rows[0].scenario === scenario &&
        rows[0].value_fraction === "1" &&
        rows[0].comparison === (action === "entry" ? "LTE" : "GTE") &&
        typeof rows[0].rationale === "string" &&
        rows[0].rationale.length > 0 &&
        numberText(value) &&
        value === price.draft!.basis[scenario] &&
        value === price.draft_prices![action]
      );
    });
  } catch {
    return false;
  }
}

export function CandidatePriceDraft({ review }: { review: Review }) {
  const price = review.conditional_price;
  if (!price) return null;
  const valid = candidatePriceMatches(review);
  return (
    <section aria-label="本候选条件价格状态">
      <h5>
        {valid
          ? "条件价格草案：未批准的研究复核参考"
          : "条件价格：当前不能给出可靠操作价"}
      </h5>
      <p>
        {typeof price.explanation === "string"
          ? price.explanation
          : "条件价格依据缺失"}
      </p>
      {!valid &&
        Array.isArray(price.reason_codes) &&
        price.reason_codes.length > 0 && (
          <details>
            <summary>未形成草案的具体原因</summary>
            <ul>
              {price.reason_codes
                .filter((reason) => typeof reason === "string")
                .map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
            </ul>
          </details>
        )}
      {valid ? (
        <>
          <p>
            仅对本候选版本成立；不是当前买卖建议。低置信度下，悲观情景也可能高估，不能证明已有足够安全边际。
          </p>
          <dl>
            <dt>研究复核参考价（悲观情景，≤）</dt>
            <dd>{Number(price.draft_prices!.entry).toFixed(2)} 元/股</dd>
            <dt>估值复核参考价（乐观情景，≥）</dt>
            <dd>{Number(price.draft_prices!.reduce).toFixed(2)} 元/股</dd>
          </dl>
          {price.draft!.rules.map((rule) => (
            <p key={rule.action}>
              {rule.action === "entry" ? "关注条件" : "估值风险条件"}：
              {rule.rationale}
            </p>
          ))}
          <p>
            加仓、退出和个人股数：未形成；需原始买入逻辑、持仓与风险条件，不能由参考价代替。
          </p>
          <p>
            估值基准日：{price.draft!.basis.valuation_date}。草案窗口：
            {price.proposal_validity?.available_at} 至{" "}
            {price.proposal_validity?.expires_at}；
            {price.proposal_validity?.current_valid === true
              ? "草案在复核窗口内"
              : "草案不在有效复核窗口内，仅供历史阅读"}
            。
          </p>
          <p>
            尚未进行当前行情比较；股本、期间分配、重大事件与报价资格必须另行核对。
          </p>
          <p>阈值理由：{price.draft!.rationale}</p>
          <p>分配风险：{price.draft!.dividend_coverage_risk}</p>
          <details>
            <summary>版本、来源与重新复核条件</summary>
            <p>
              政策：{price.draft!.policy_id} / {price.draft!.rule_version}
            </p>
            <p>候选 SHA256：{price.sourcebindings?.candidate_sha256}</p>
            <p>政策 SHA256：{price.sourcebindings?.policy_artifact_sha256}</p>
            <ul>
              {(price.reopenconditions || [])
                .filter((x) => typeof x === "string")
                .map((x) => (
                  <li key={x}>{x}</li>
                ))}
            </ul>
          </details>
        </>
      ) : price.status === "researcher_proposal" ? (
        <p role="alert">价格草案与当前候选不一致，不显示参考价。</p>
      ) : null}
      <p>未注册、未批准，不生成正式操作计划；action=no_order。</p>
    </section>
  );
}
