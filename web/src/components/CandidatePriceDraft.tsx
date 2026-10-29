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
      (price.price_comparison?.currentpricecomparison !== undefined &&
        typeof price.price_comparison.currentpricecomparison !== "boolean") ||
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
      <CandidateAlignment review={review} />
      <p>未注册、未批准，不生成正式操作计划；action=no_order。</p>
    </section>
  );
}

const alignmentChecks = {
  quote: "行情资格",
  capital_structure: "股本与公司行动",
  distributions: "期间分配与模型内含",
  material_events: "重大事件",
  financial_updates: "新财报与输入更新",
} as const;
const text = (value: unknown, fallback = "未提供") =>
  typeof value === "string" && value.length > 0 ? value : fallback;
const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
function Reasons({ value }: { value: unknown }) {
  const rows = strings(value);
  return rows.length ? (
    <ul>
      {rows.map((reason, index) => (
        <li key={index}>{reason}</li>
      ))}
    </ul>
  ) : null;
}
function AlignmentEvidence({ value }: { value: unknown }) {
  const rows = Array.isArray(value)
    ? value.filter(
        (item) =>
          object(item) &&
          typeof item.path === "string" &&
          typeof item.sha256 === "string",
      )
    : [];
  return rows.length ? (
    <details>
      <summary>证据路径与 SHA256（{rows.length}）</summary>
      <ul style={{ overflowWrap: "anywhere" }}>
        {rows.map((ref, index) => (
          <li key={index}>
            <code>{ref.path}</code>
            <br />
            <code>{ref.sha256}</code>
          </li>
        ))}
      </ul>
    </details>
  ) : (
    <p>未提供证据绑定。</p>
  );
}
export function candidateAlignmentMatches(review: Review): boolean {
  const alignment = review.conditional_price?.alignment;
  return (
    !!alignment &&
    alignment.schema_version === "pending-candidate-alignment-v1" &&
    alignment.action === "no_order" &&
    alignment.formal_eligibility === false &&
    typeof review.candidate_binding?.sha256 === "string" &&
    typeof review.input_descriptor_sha256 === "string" &&
    alignment.candidate_binding?.sha256 === review.candidate_binding.sha256 &&
    alignment.candidate_binding?.path === review.candidate_binding.path &&
    alignment.input_descriptor_sha256 === review.input_descriptor_sha256 &&
    typeof review.conditional_price?.draft?.basis?.valuation_date ===
      "string" &&
    alignment.valuation_date ===
      review.conditional_price.draft.basis.valuation_date
  );
}
function CandidateAlignment({ review }: { review: Review }) {
  const price = review.conditional_price;
  const alignment = price?.alignment;
  if (!alignment)
    return (
      <p>
        尚未进行当前行情比较；未提供当前对齐检查，历史草案仍按原估值日阅读。
      </p>
    );
  if (!candidateAlignmentMatches(review))
    return (
      <section aria-label="当前对齐检查">
        <p role="alert">
          当前对齐证据与候选/输入/估值日期不匹配或字段不完整，不能用于当前比较；历史草案独立保留。
        </p>
      </section>
    );
  const quote = alignment.quote;
  const checks = Array.isArray(alignment.checks)
    ? alignment.checks.filter(
        (item) => object(item) && typeof item.id === "string",
      )
    : [];
  const qualified =
    quote?.status === "QUALIFIED" &&
    numberText(quote.current_price) &&
    typeof quote.quote_date === "string" &&
    quote.quote_date === quote.latest_completed_session;
  const researchComparison = candidateResearchComparisonMatches(review);
  const missing = Object.keys(alignmentChecks).filter(
    (id) => !checks.some((item) => item.id === id),
  );
  return (
    <section aria-label="当前对齐检查">
      <h5>
        当前对齐检查：
        {researchComparison
          ? "当前研究比较口径已核验，仍未批准"
          : "口径待核，不能进行当前价值比较"}
      </h5>
      <p>
        估值日期：{text(alignment.valuation_date)}；核验时点：
        {text(alignment.evaluated_at)}。
      </p>
      <details>
        <summary>原始对齐状态与比较标记</summary>
        <p>
          {text(alignment.status)} /{" "}
          {typeof alignment.currentpricecomparison === "boolean"
            ? String(alignment.currentpricecomparison)
            : "未提供"}
        </p>
      </details>
      <p>
        {text(
          alignment.explanation,
          "报价、股本、分配、事件与模型有效性分别核验。",
        )}
      </p>
      <details>
        <summary>对齐未完成的原因代码</summary>
        <Reasons value={alignment.reason_codes} />
      </details>
      <h6>当前报价 · 独立市场事实</h6>
      <p>
        {qualified
          ? "报价已核验；价值比较口径须另核。"
          : "报价待核验，暂不作为合格当前报价。"}
      </p>
      <details>
        <summary>原始报价状态</summary>
        <p>
          {text(quote?.status)} / {text(quote?.native_status)}
        </p>
        <Reasons value={quote?.reason_codes} />
      </details>
      <p>
        当前价：
        {qualified ? quote!.current_price + " 元/股" : "未提供合格当前报价"}；
        报价日期：{text(quote?.quote_date)}；最近完成交易日：
        {text(quote?.latest_completed_session)}。
      </p>
      <p>
        报价合格不代表经济口径已对齐。本页不计算当前折价、安全边际或买卖结论，不改变原估值日期。
      </p>
      <p>{text(quote?.explanation, "未提供报价说明。")}</p>

      {quote?.bundle_binding && (
        <AlignmentEvidence value={[quote.bundle_binding]} />
      )}
      <ol>
        {checks.map((check, index) => (
          <li key={check.id + index}>
            <strong>
              {alignmentChecks[check.id as keyof typeof alignmentChecks] ||
                check.id}
            </strong>
            {" · "}
            {(
              {
                PASS: "证据检查通过（非批准）",
                BLOCKED: "受阻",
                MISSING: "缺证",
                UNKNOWN: "未知",
              } as Record<string, string>
            )[text(check.status)] || "状态待核"}
            <p>{text(check.explanation, "未提供检查说明。")}</p>
            <CheckReconciliation id={check.id} details={check.details} />
            <details>
              <summary>检查原因代码</summary>
              <Reasons value={check.reason_codes} />
            </details>
            <AlignmentEvidence value={check.evidence_bindings} />
            {object(check.details) && (
              <details>
                <summary>核验细节 · {check.id}</summary>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {JSON.stringify(check.details, null, 2)}
                </pre>
              </details>
            )}
          </li>
        ))}
      </ol>
      {missing.length > 0 && (
        <p>
          缺少检查：
          {missing
            .map((id) => alignmentChecks[id as keyof typeof alignmentChecks])
            .join("、")}
          ；未推定通过。
        </p>
      )}
      <p>
        {researchComparison
          ? "模型有效性与价格桥接已核验，仍不代表投资批准。"
          : "模型有效性或价格桥接口径待核，保留历史研究参考价。"}
      </p>
      <details>
        <summary>模型与桥接原始状态及原因</summary>
        <p>
          {text(alignment.model_validity?.status)} /{" "}
          {text(alignment.price_bridge?.bridge_status)}
        </p>
        <Reasons value={alignment.model_validity?.blockers} />
        <Reasons value={alignment.price_bridge?.blockers} />
      </details>
      <p>
        模型/桥接状态是后端核验结果，不能替代G3、策略批准或个人风险复核。跨日是否可比由证据核验结果决定。
      </p>
      <AlignmentEvidence value={alignment.evidence_bindings} />
    </section>
  );
}

const emptyReasons = (value: unknown) =>
  Array.isArray(value) && value.length === 0;
export function candidateResearchComparisonMatches(review: Review): boolean {
  if (!candidatePriceMatches(review) || !candidateAlignmentMatches(review))
    return false;
  const price = review.conditional_price!;
  const alignment = price.alignment!;
  const quote = alignment.quote;
  const bridge = alignment.price_bridge;
  const validity = alignment.model_validity;
  const checks = alignment.checks;
  if (!quote || !bridge || !validity || !Array.isArray(checks)) return false;
  return (
    alignment.status === "ALIGNED_FOR_RESEARCH_COMPARISON" &&
    alignment.currentpricecomparison === true &&
    price.proposal_validity?.current_valid === true &&
    quote.status === "QUALIFIED" &&
    numberText(quote.current_price) &&
    typeof quote.quote_date === "string" &&
    quote.quote_date === quote.latest_completed_session &&
    alignment.quote_date === quote.quote_date &&
    emptyReasons(quote.reason_codes) &&
    checks.length === Object.keys(alignmentChecks).length &&
    Object.keys(alignmentChecks).every((id) => {
      const rows = checks.filter((item) => object(item) && item.id === id);
      return (
        rows.length === 1 &&
        rows[0].status === "PASS" &&
        emptyReasons(rows[0].reason_codes)
      );
    }) &&
    emptyReasons(alignment.reason_codes) &&
    validity.status === "VALID" &&
    emptyReasons(validity.blockers) &&
    validity.symbol === review.symbol &&
    validity.model_as_of === alignment.valuation_date &&
    bridge.bridge_status === "READY" &&
    emptyReasons(bridge.blockers) &&
    bridge.model_validity_status === "VALID" &&
    bridge.quote_status === "verified_close" &&
    bridge.symbol === review.symbol &&
    bridge.quote_symbol === review.symbol &&
    bridge.valuation_date === alignment.valuation_date &&
    bridge.model_as_of === alignment.valuation_date &&
    bridge.quote_date === quote.quote_date &&
    bridge.current_price === quote.current_price &&
    typeof price.sourcebindings?.model_version === "string" &&
    bridge.model_version === price.sourcebindings.model_version &&
    bridge.valuation_bear_value === price.draft!.basis.bear &&
    bridge.valuation_base_value === price.draft!.basis.base
  );
}

function CheckReconciliation({
  id,
  details,
}: {
  id: string;
  details: unknown;
}) {
  if (!object(details) || !object(details.reconciliation)) return null;
  const ledger = details.reconciliation;
  if (id === "capital_structure")
    return (
      <section aria-label="已核验股本与当前缺口">
        <dl>
          <dt>估值日股本（已消费口径）</dt>
          <dd>{text(ledger.opening_shares)} 股</dd>
          <dt>当前股本</dt>
          <dd>
            {ledger.closing_shares == null
              ? "尚未核验，不能认定股本未变"
              : text(ledger.closing_shares) + " 股"}
          </dd>
          <dt>仅按已列行动计算的期末股数</dt>
          <dd>
            {text(ledger.calculated_closing_shares)} 股；不是当前股本确认。
          </dd>
        </dl>
        <p>
          核验状态：{text(ledger.status)}
          。期初待生效行动与后续完整实施链仍须分别核验。
        </p>
      </section>
    );
  if (id !== "distributions") return null;
  const rows = Array.isArray(ledger.distributions)
    ? ledger.distributions.filter(object)
    : [];
  const treatments: Record<string, string> = {
    BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL:
      "公告列示的除息日、现金发放日均在估值日前；不重复扣减，未验证个人实际到账",
    IN_PERIOD_MODEL_INCLUSION_REQUIRES_RECOMPUTATION:
      "区间内分配，是否已内含需重新核验",
    PENDING_PAYMENT_REQUIRES_REVIEW: "尚待支付，需要复核",
    OPENING_EX_ENTITLEMENT_PAID_IN_PERIOD_REQUIRES_REVIEW:
      "期初已除息、区间内支付，需复核权利归属",
  };
  return (
    <section aria-label="已核验公告分配条款与期间覆盖边界">
      <h6>已列公告分配条款</h6>
      {rows.length ? (
        <ul>
          {rows.map((row, index) => (
            <li key={index}>
              <dl>
                <dt>已核验公告每股现金分配条款</dt>
                <dd>
                  {text(row.verified_cash_per_share)} 元/股
                  {row.amount_basis === "implemented_gross_entitlement"
                    ? "（含税权益口径）"
                    : ""}
                </dd>
                <dt>登记 / 除息 / 支付日期</dt>
                <dd>
                  {text(row.record_date)} / {text(row.ex_date)} /{" "}
                  {text(row.cash_payment_date)}
                </dd>
                <dt>区间处理</dt>
                <dd>
                  {treatments[text(row.period_treatment)] ||
                    "处理方式待核验，不能推定已内含（见核验细节）"}
                </dd>
                <dt>本次已应用价格扣减</dt>
                <dd>
                  {text(row.price_deduction_applied)}{" "}
                  元/股（后端结果；前端不再调整价格）
                </dd>
              </dl>
              <AlignmentEvidence
                value={
                  Array.isArray(row.evidence)
                    ? row.evidence.filter(object).map((item) => item.binding)
                    : []
                }
              />
            </li>
          ))}
        </ul>
      ) : (
        <p>未列出可展示的分配记录；不表示没有分配。</p>
      )}
      <p>
        已列记录中归入本区间的现金合计：{text(ledger.period_cash_per_share)}{" "}
        元/股。
      </p>
      <p>
        此合计只反映已列记录的计算，不证明全期间完整覆盖；即使为0，也不能据此认定实际期间无分红。
      </p>
    </section>
  );
}
