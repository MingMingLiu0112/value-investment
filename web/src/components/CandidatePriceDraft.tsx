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
      {price.alignment && (
        <p>
          以下为草案形成时的说明；最新行情与口径核验结果见下方“当前对齐检查”。
        </p>
      )}
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
            {check.id === "distributions" && object(check.details) && (
              <OpeningActionChain value={check.details.opening_action_chain} />
            )}
            {check.id === "capital_structure" && object(check.details) && (
              <OperatingEventResearch
                value={check.details.opening_action_research}
                opening
              />
            )}
            {check.id === "distributions" && object(check.details) && (
              <BasisFollowup value={check.details.basis_followup} />
            )}
            <CheckInputSources id={check.id} details={check.details} />
            {check.id === "material_events" && object(check.details) && (
              <OperatingEventResearch
                value={check.details.operating_event_research}
              />
            )}
            {check.id === "material_events" && object(check.details) && (
              <CandidateEventImpact
                value={check.details.candidate_event_impact}
              />
            )}
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

function CheckInputSources({ id, details }: { id: string; details: unknown }) {
  if (!["material_events", "financial_updates"].includes(id)) return null;
  const data = object(details) ? details : {};
  return (
    <section
      aria-label={`${alignmentChecks[id as keyof typeof alignmentChecks]}公告来源`}
    >
      <p>
        原件来源与事件准入分开：事实已消费不代表重大性复核通过，也不授予模型有效或当前比较资格。
      </p>
      {(
        [
          ["matched_input_sources", "已匹配输入的公告"],
          ["unresolved_sources", "尚未绑定复核的公告"],
        ] as const
      ).map(([key, label]) => {
        const value = data[key];
        const rows = Array.isArray(value) ? value.filter(object) : [];
        return (
          <section key={key} aria-label={label}>
            <h6>{label}</h6>
            {rows.length ? (
              <ul>
                {rows.map((row, index) => {
                  const consumed =
                    key === "matched_input_sources" &&
                    row.status ===
                      "EXACT_FACT_SOURCE_ALREADY_CONSUMED_NOT_EVENT_APPROVAL";
                  const refs = Array.isArray(row.evidence_refs)
                    ? row.evidence_refs.filter(object)
                    : [];
                  const sourceUrl = text(row.source_url, "");
                  let safeSourceUrl = false;
                  try {
                    safeSourceUrl = ["https:", "http:"].includes(
                      new URL(sourceUrl).protocol,
                    );
                  } catch {}
                  const fields = strings(row.consumed_fact_fields).filter(
                    (field) => field.trim(),
                  );
                  return (
                    <li key={index}>
                      <strong>{text(row.title, "公告标题未提供")}</strong>
                      <p>
                        披露日期：{text(row.published_at, "未提供披露日期")}
                      </p>
                      {consumed ? (
                        <>
                          <p>
                            原件事实已匹配当前输入（非事件批准）。已消费事实字段：
                          </p>
                          {fields.length ? (
                            <ul>
                              {fields.map((field, i) => (
                                <li key={i}>{field}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>未提供已消费事实字段。</p>
                          )}
                        </>
                      ) : (
                        <p>
                          未复核原因：
                          {row.status ===
                          "NOT_BOUND_TO_CURRENT_CANDIDATE_REVIEW"
                            ? "尚未绑定当前候选的复核，不能据此认定重大性已获批准。"
                            : "未提供可识别的复核结论，仍需核对。"}
                          {typeof row.status === "string" && (
                            <>（{row.status}）</>
                          )}
                        </p>
                      )}
                      {typeof row.original_bytes_in_source_closure ===
                        "boolean" && (
                        <p>
                          原件字节在来源闭包中：
                          {row.original_bytes_in_source_closure
                            ? "是；不代表事实已消费或事件获准。"
                            : "否；尚未纳入当前来源闭包。"}
                        </p>
                      )}
                      <p>
                        原件来源（不代表事件准入）：
                        {safeSourceUrl ? (
                          <a
                            href={sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            查看公告原件
                          </a>
                        ) : (
                          "未提供可用公告原件链接"
                        )}
                      </p>
                      <AlignmentEvidence value={refs} />
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>
                {Array.isArray(value) && value.length === 0
                  ? "未列出公告；不代表无重大事件或已通过复核。"
                  : "公告来源明细缺失或格式异常，未推定通过。"}
              </p>
            )}
          </section>
        );
      })}
    </section>
  );
}

const nativeAmount = (value: unknown, unit: string) =>
  typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value)
    ? `${value} ${unit}`
    : "未提供";

function NativeSourceConsumption({
  id,
  value,
}: {
  id: string;
  value: unknown;
}) {
  if (!object(value)) return <p>未提供中报原件字段核验结果。</p>;
  const reports = Array.isArray(value.reports)
    ? value.reports.filter(object)
    : [];
  const inclusion = object(value.distribution_inclusion)
    ? value.distribution_inclusion
    : {};
  const comparisons = Array.isArray(inclusion.comparisons)
    ? inclusion.comparisons.filter(object)
    : [];
  return (
    <section
      aria-label={
        id === "capital_structure"
          ? "中报原件股本与注销核验"
          : "中报原件分配与金额核对"
      }
    >
      <h6>
        {id === "capital_structure"
          ? "中报原件股本与回购注销"
          : "中报分配预案与分红金额核对"}
      </h6>
      <p>
        核验状态：
        {value.status === "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE"
          ? "原件字段已核验，行动链仍不完整"
          : value.status === "NO_SUPPORTED_SOURCE_FIELDS"
            ? "尚无已支持的原件字段"
            : "未提供可识别的核验状态"}
        。
      </p>
      <p>
        以下仅为已列中报披露范围内的事实，非截至当前完整证明；不证明其他待生效方案、后续行动或修订已全部覆盖，不代表重大性批准或当前比较获准。
      </p>
      {reports.length ? (
        <ul>
          {reports.map((report, index) => {
            const terms = object(report.terms) ? report.terms : {};
            const verified = report.status === "NATIVE_REPORT_FIELDS_VERIFIED";
            const url = text(report.source_url, "");
            let safe = false;
            try {
              safe = ["http:", "https:"].includes(new URL(url).protocol);
            } catch {}
            return (
              <li key={index}>
                <p>
                  H1 报告期末：{text(terms.period_end)}；披露日期：
                  {text(report.published_date)}；原件取得时间：
                  {text(report.source_available_at)}。
                </p>
                <p>
                  字段状态：
                  {verified ? "中报原件字段已核验" : "尚未确认字段核验通过"}。
                </p>
                {verified ? (
                  id === "capital_structure" ? (
                    <dl>
                      <dt>H1 期末普通股股数</dt>
                      <dd>
                        {nativeAmount(terms.ordinary_shares, "股")}
                        ；不代表当前股本。
                      </dd>
                      <dt>回购注销股数</dt>
                      <dd>{nativeAmount(terms.cancelled_shares, "股")}</dd>
                      <dt>注销状态</dt>
                      <dd>
                        {terms.cancellation_state ===
                        "DISCLOSED_BUYBACK_COMPLETED_BY_REPORT_END"
                          ? "中报披露截至报告期末已完成回购注销"
                          : "未提供可识别的注销状态"}
                      </dd>
                      <dt>与估值期初已消费事实的匹配</dt>
                      <dd>
                        {report.consumed_opening_fact === true
                          ? "已匹配；不证明后续股本连续性"
                          : report.consumed_opening_fact === false
                            ? "未匹配期初事实"
                            : "未提供匹配结果"}
                      </dd>
                    </dl>
                  ) : (
                    <dl>
                      <dt>半年度利润分配及公积金转增预案</dt>
                      <dd>
                        {terms.interim_proposal_state ===
                        "NO_INTERIM_DISTRIBUTION_OR_CAPITALIZATION_PROPOSED"
                          ? "半年度预案不分配、不转增；不代表截至当前无分配"
                          : "未提供可识别的预案结果"}
                      </dd>
                      <dt>中报披露普通股股利金额</dt>
                      <dd>
                        {nativeAmount(
                          terms.declared_ordinary_dividend_cny,
                          "元",
                        )}
                        ；不代表个人到账或模型已内含。
                      </dd>
                    </dl>
                  )
                ) : (
                  <p>未将未核验字段作为已核验事实展示。</p>
                )}
                {safe && (
                  <p>
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      查看中报原件
                    </a>
                  </p>
                )}
                <AlignmentEvidence value={[report.binding]} />
              </li>
            );
          })}
        </ul>
      ) : (
        <p>未列出可展示的中报字段；不推定无回购注销或无分配。</p>
      )}
      {id === "distributions" && (
        <>
          <h6>中报与分红实施公告金额差异</h6>
          {comparisons.length ? (
            <ul>
              {comparisons.map((row, index) => (
                <li key={index}>
                  <dl>
                    <dt>中报股利金额</dt>
                    <dd>{nativeAmount(row.reported_dividend_cny, "元")}</dd>
                    <dt>实施公告含税总额</dt>
                    <dd>{nativeAmount(row.implementation_total_cny, "元")}</dd>
                    <dt>分红金额差异（中报减实施公告，后端结果）</dt>
                    <dd>{nativeAmount(row.difference_cny, "元")}</dd>
                    <dt>核对结论</dt>
                    <dd>
                      {row.status ===
                      "AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION"
                        ? "存在金额差异，仍需对账；不能认定模型已内含"
                        : row.status ===
                            "AMOUNT_MATCH_NOT_MODEL_INCLUSION_PROOF"
                          ? "金额一致，仍不证明模型已内含"
                          : "未提供可识别的核对结论"}
                    </dd>
                    <dt>本次价格扣减</dt>
                    <dd>
                      {nativeAmount(row.price_deduction_applied, "元/股")}
                      （后端结果；前端不调整价格）
                    </dd>
                  </dl>
                  <AlignmentEvidence
                    value={[
                      row.report_binding,
                      ...(Array.isArray(row.implementation_evidence)
                        ? row.implementation_evidence
                            .filter(object)
                            .map((ref) => ref.binding)
                        : []),
                    ]}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p>未提供分红金额比较，不推定差异为零。</p>
          )}
        </>
      )}
    </section>
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
        <NativeSourceConsumption
          id={id}
          value={ledger.native_source_consumption}
        />
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
      <NativeSourceConsumption
        id={id}
        value={ledger.native_source_consumption}
      />
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
        已列记录中归入本区间的除息权益合计：{text(ledger.period_cash_per_share)}{" "}
        元/股。
      </p>
      <p>
        此合计按除息日期计算，包含尚待支付的权益，不代表现金已到账，也不证明全期间完整覆盖；即使为0，也不能据此认定实际期间无分红。
      </p>
    </section>
  );
}

function OperatingEventResearch({
  value,
  opening = false,
}: {
  value: unknown;
  opening?: boolean;
}) {
  const rows = Array.isArray(value) ? value.filter(object) : [];
  if (!rows.length) return null;
  return (
    <section
      aria-label={opening ? "期初行动与分配授权" : "公告对经营假设的影响"}
    >
      <h6>
        {opening
          ? "期初行动与分配授权 · 已完成与待跟踪分开"
          : "公告对经营假设的影响 · 原件事实与研究结论分开"}
      </h6>
      <p>
        下列金额、日期和事项从公告正文重新提取。已读出事实不等于当前候选已吸收影响，
        不自动修改预测、不代签材料性复核，也不把历史条件参考价升级为当前买价。
      </p>
      {rows.map((row, index) => {
        const facts = Array.isArray(row.facts) ? row.facts.filter(object) : [];
        return (
          <article key={index}>
            <h6>
              {text(row.title)} · {text(row.published_at)}
            </h6>
            {row.status === "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW" &&
            facts.length ? (
              facts.map((fact, i) => {
                const terms = object(fact.terms) ? fact.terms : {};
                return (
                  <div key={i}>
                    <p>
                      原件事实：{text(terms.summary, "原件字段见下方明细。")}
                    </p>
                    <p>
                      候选影响待核：
                      {text(
                        terms.implication,
                        "须复核本候选经营假设及现金路径，尚未认定已吸收。",
                      )}
                    </p>
                    <p>
                      生效日期：
                      {text(
                        terms.effective_date,
                        "未披露明确生效日；不以公告日期代替。",
                      )}
                      ；取得时间：{text(fact.source_available_at)}。
                    </p>
                    <Reasons value={terms.affected_model_fields} />
                    <Reasons value={terms.limitations} />
                    <details>
                      <summary>原件字段、页码与摘录</summary>
                      <pre
                        style={{
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {JSON.stringify(terms, null, 2)}
                      </pre>
                    </details>
                    <AlignmentEvidence value={[fact.binding]} />
                  </div>
                );
              })
            ) : (
              <p>尚未匹配可核验的正文语义消费者，不能仅凭标题认定无影响。</p>
            )}
            <p>候选输入未自动改写；材料性未获批准。action=no_order。</p>
          </article>
        );
      })}
    </section>
  );
}

function OpeningActionChain({ value }: { value: unknown }) {
  if (!object(value)) return null;
  const confirmations = Array.isArray(value.confirmations)
    ? value.confirmations.filter(object)
    : [];
  const links = Array.isArray(value.distribution_links)
    ? value.distribution_links.filter(object)
    : [];
  const pending = Array.isArray(value.outstanding_authorizations)
    ? value.outstanding_authorizations.filter(object)
    : [];
  return (
    <section aria-label="已知期初行动对账">
      <h6>已知期初行动对账 · 不等于当前完整股本链</h6>
      {confirmations.map((row, i) => (
        <p key={i}>
          原件确认注销日期：{text(row.effective_date)}； 注销{" "}
          {text(row.cancelled_shares)} 股，公告时总股数{" "}
          {text(row.issued_shares)} 股；
          {row.matches_consumed_opening_shares === true
            ? "与估值已消费期初股数一致"
            : "与已消费期初股数未核对一致"}
          。 这不是当前股本证明。
        </p>
      ))}
      {links.map((row, i) => (
        <p key={i}>
          年度分配每股 {text(row.annual_cash_per_share)} 元、总额{" "}
          {text(row.annual_total_cash_cny)} 元：
          {row.status === "MATCHED_PREVALUATION_IMPLEMENTATION_TERMS"
            ? "与估值前实施公告金额及对象股数一致"
            : "尚未匹配实施条款"}
          ； 不重复扣减，不证明个人到账，也未消除中报一分钱差异。
        </p>
      ))}
      {pending.map((row, i) => (
        <div key={i}>
          <p>{text(row.authorization_text)}</p>
          <p>
            仍待后续方案、实施或撤销核验；授权不是已定分红，也不是确定现金义务。
          </p>
        </div>
      ))}
      {!confirmations.length && !links.length && !pending.length && (
        <p>尚无受支持原件可以完成该项对账。</p>
      )}
    </section>
  );
}

function BasisFollowup({ value }: { value: unknown }) {
  if (
    !object(value) ||
    value.schema_version !== "candidate-basis-followup-v1" ||
    value.action !== "no_order" ||
    value.current_comparison_granted !== false
  )
    return null;
  const checkpoint = object(value.latest_capital_checkpoint)
    ? value.latest_capital_checkpoint
    : null;
  const interval = object(value.uncovered_capital_interval)
    ? value.uncovered_capital_interval
    : null;
  const reports = Array.isArray(value.interim_report_followups)
    ? value.interim_report_followups.filter(object)
    : [];
  return (
    <section aria-label="股本与中期分配后续核验">
      <h6>已证实到哪一天，后续还缺什么</h6>
      {checkpoint ? (
        <p>
          已核验普通股股数：{text(checkpoint.ordinary_shares)} 股，事实时点{" "}
          {text(checkpoint.as_of)}， 披露日期 {text(checkpoint.published_date)}
          。{text(checkpoint.limitation)}
        </p>
      ) : (
        <p>尚无可消费的原件股本时点。</p>
      )}
      {interval && (
        <p>
          尚未证明连续性的区间：{text(interval.after)} 之后至{" "}
          {text(interval.through)}。 不能把期初股数沿用为当前股数。
        </p>
      )}
      {reports.map((row, i) => (
        <div key={i}>
          <p>
            {text(row.published_date)} 中报后续核验：{text(row.conclusion)}
          </p>
          <AlignmentEvidence value={[row.evidence_binding]} />
        </div>
      ))}
      {value.authorization_followup_required === true && (
        <p>
          中期分红授权仍需跟踪：未确认后续方案、实施或撤销，不填零分红，不认定已经支付。
        </p>
      )}
      <Reasons value={value.next_required_evidence} />
      <p>
        公告检索完成只证明本次取得范围，不证明没有遗漏的有效行动；当前价格比较与人工批准保持原门禁。
      </p>
    </section>
  );
}

function CandidateEventImpact({ value }: { value: unknown }) {
  if (
    !object(value) ||
    value.schema_version !== "candidate-event-impact-draft-v1" ||
    value.materiality_approved !== false ||
    value.action !== "no_order"
  )
    return null;
  const items = Array.isArray(value.items) ? value.items.filter(object) : [];
  if (!items.length) return null;
  return (
    <section aria-label="当前候选事件复核草案">
      <h6>这些公告具体影响本候选的哪些计算？</h6>
      <p>
        未批准复核草案。以下是已消费的条件计算，不是新盈利预测；模型年份不等同公告所属会计年度。
      </p>
      {items.map((item, i) => {
        const changes = Array.isArray(item.derived_price_changes)
          ? item.derived_price_changes.filter(object)
          : [];
        const values = Array.isArray(item.consumed_model_values)
          ? item.consumed_model_values.filter(object)
          : [];
        return (
          <article key={i}>
            <strong>{text(item.title)}</strong>
            <p>{text(item.rationale)}</p>
            {changes.map((change, k) => (
              <p key={k}>
                {change.field === "retail_price"
                  ? "公告平台零售价"
                  : "公告销售合同价"}
                ：{text(change.before)} → {text(change.after)}{" "}
                {text(change.unit)}； 公告价变化{" "}
                {numberText(change.relative_change)
                  ? (Number(change.relative_change) * 100).toFixed(2) + "%"
                  : text(change.relative_change)}
                。 不是整体收入或利润增幅。
              </p>
            ))}
            <p>
              已定位 {values.length}{" "}
              项模型年度字段；未量化盈利影响，不改写原估值。
            </p>
            <Reasons value={item.unresolved_inputs} />
            <details>
              <summary>查看被影响的现有计算与证据</summary>
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {JSON.stringify(values, null, 2)}
              </pre>
              <Reasons value={item.unmapped_model_fields} />
              <AlignmentEvidence value={[item.evidence_binding]} />
            </details>
          </article>
        );
      })}
    </section>
  );
}
