import type {
  CurrentPricePlan,
  HotspotLifecycleReview as Review,
} from "../types/api";

// Presentation vocabulary mirrors report_text.py; no trading rule is evaluated here.
const labels: Record<string, string> = {
  CURRENT_DATA: "当前行情证据",
  ENTRY_REFERENCE: "原始参考证据",
  ENTRY_RULE_COMPATIBILITY: "本次重算规则兼容性",
  PRICE_COMPARABILITY: "公司行动与价格口径可比性",
  ORIGINAL_PROTECTION: "原始参考保护价",
  CONTINUITY_COVERAGE: "连续行情覆盖",
  CURRENT_EXIT: "当前退出结构条件",
  CURRENT_REDUCE: "当前减仓结构条件",
  CURRENT_ADD: "当前加仓结构条件",
  CURRENT_OPEN: "当前开仓结构条件",
  STRUCTURE_QUALITY: "价格行为质量",
  OPPORTUNITY_QUALITY: "多周期机会分级",
  UNKNOWN: "未知",
  WATCH: "继续观察",
  ENTRY_OBSERVATION: "开仓结构观察",
  EXIT_STRUCTURE_REVIEW: "退出结构复核",
  REDUCE_STRUCTURE_REVIEW: "减仓结构复核",
  ADD_STRUCTURE_REVIEW: "加仓结构复核",
  HOLD_STRUCTURE_OBSERVATION: "维持结构观察",
  CONFIRMED: "同口径覆盖已确认，仅限此证据范围",
  INCOMPARABLE: "不宜直接比较",
  CURRENT: "当前可用",
  STALE: "已过期",
  INVALID: "无效",
  VERIFIED_REFERENCE_ONLY: "仅参考证据已核验，不代表真实入场或持仓",
  UNVERIFIED: "未核验",
  NOT_SUPPLIED: "未提供",
  MATCH: "一致",
  MISMATCH: "不一致",
  NOT_EVALUATED: "未评估（不等于未触发）",
  BREACHED: "已观察到破位",
  NO_OBSERVED_BREACH: "未观察到破位（不证明未曾发生）",
  COMPLETE: "覆盖完整",
  INCOMPLETE: "覆盖不完整",
  OBSERVED: "已观察到条件",
  NOT_OBSERVED: "本次未观察到条件",
  RESEARCH_ONLY: "仅供研究",
  UNFAVORABLE_DAILY_TREND: "日线趋势不利",
  INSUFFICIENT_UPPER_SPACE: "上方空间不足",
  ACTIVE_ONLY: "仅活跃观察",
  CONFLICT_OR_REJECTED: "存在结构冲突或已拒绝",
  STRUCTURE_QUALIFIED_OBSERVATION: "结构合格观察",
  PRICE_BASIS_UNKNOWN: "公司行动覆盖未核验，不能假定价格可直接比较",
  PRICE_BASIS_INCOMPARABLE: "跨越分配事件，不复权价格不能直接比较",
  CURRENT_DATA_UNAVAILABLE: "当前行情证据不可用，无法判断结构",
  ENTRY_STRUCTURE_OBSERVED: "当前开仓结构条件已观察到，仅供研究",
  ENTRY_STRUCTURE_NOT_QUALIFIED: "当前开仓结构尚不满足观察条件",
  ENTRY_EVIDENCE_UNAVAILABLE: "原始参考在指定入场时点不可用",
  ENTRY_CURRENT_RULE_MISMATCH: "原始与当前参考的本次重算规则不一致",
  ORIGINAL_PROTECTION_BREACHED: "曾收盘跌破原始保护价；后来恢复不能抹去破位",
  CURRENT_PROTECTION_BREACHED: "当前保护条件触发破位结构复核",
  ENTRY_TO_CURRENT_DATA_INCOMPLETE:
    "入场至当前数据不完整，不能确认持有或加仓结构",
  CURRENT_REDUCTION_CONDITION_OBSERVED: "已观察到减仓结构条件，仅供复核",
  CURRENT_ADD_CONDITION_OBSERVED: "已观察到加仓结构条件，仅供复核",
  NO_STRUCTURAL_CHANGE_OBSERVED: "本次未观察到需要改变结构观察状态的条件",
  ADD_CONDITION_NOT_OBSERVED: "未观察到加仓结构条件",
  ADD_STRUCTURE_QUALITY_NOT_USABLE: "加仓结构质量不可用于当前判断",
  OWNED_ENTRY_THESIS: "核验真实持仓归属及原始入场论据",
  CORPORATE_ACTION_COMPARABILITY: "核验公司行动与价格口径可比性",
  INDEPENDENT_STRATEGY_ADMISSION: "完成独立策略准入复核",
  EVENT_RISK: "复核事件风险",
  PORTFOLIO_CAPACITY: "复核组合容量与约束",
  SELLABLE_QUANTITY_T_PLUS_ONE_AND_EXECUTION: "复核可卖数量、T+1 与执行条件",
  LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE: "最近已完成时段的双源收盘观察",
  LAST_COMPLETED_CLOSE_DISPLAY_ONLY: "最近已完成收盘，仅供展示",
  HISTORICAL_CLOSE_NOT_CURRENT_QUOTE: "历史收盘，非当前报价",
  VERIFIED: "原件完整性已核验",
  NOT_VERIFIED: "原件未核验",
};
const fields: Record<string, string> = {
  original_protection_price: "原始参考保护价（元）",
  current_rolling_protection_price: "当前滚动保护价（元）",
  first_breach_at: "首次收盘破位时点",
  first_breach_close: "首次破位收盘价（元）",
  breach_count: "收盘破位次数",
  inspected_bar_count: "已检查 K 线数量",
  missing_completed_bars: "缺失已完成 K 线",
  coverage: "数据覆盖",
  entry_at: "参考入场时点",
  observed: "是否观察到条件",
  current_pit: "当前 PIT 标志",
  source_integrity: "原件完整性",
  current: "当前参考",
  entry: "原始参考",
  price: "价格（元）",
  rule: "条件规则",
  intent: "结构动作",
  requires_existing_holding: "是否要求已有持仓",
  formal_eligibility: "正式准入",
  personal_permission: "个人权限",
  blockers: "阻断原因",
  status: "状态",
  window_start: "价格窗口起日",
  window_end: "价格窗口止日",
  crossing_events: "跨越的已收录事件",
  ex_date: "除息除权日",
  complete_corporate_action_coverage: "全部公司行动覆盖是否已证明",
  historical_availability_proven: "历史可得性是否已证明",
  adjusted_protection_price: "已核验调整后保护价",
  observation_quality: "观察质量",
  structure_tier: "结构等级",
  structure_reasons: "分级原因",
  daily_trend: "日线趋势",
  risk_reward_ratio: "结构距离比",
  risk_reward_scope: "距离比口径",
  risk_reward_blocker: "距离比缺失原因",
  rule_version: "规则版本",
};
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
function binding(value: unknown): boolean {
  return (
    record(value) &&
    typeof value.path === "string" &&
    !!value.path &&
    !/^(?:[\\/]|[a-z]+:)/i.test(value.path) &&
    !value.path.split(/[\\/]/).includes("..") &&
    typeof value.sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(value.sha256)
  );
}
function bound(review: Review, symbol: string, plan?: CurrentPricePlan | null) {
  try {
    const explain = review.decision_explanation;
    return (
      review.schema_version === "hotspot-entry-structure-continuity-v2" &&
      review.symbol === symbol &&
      review.action === "no_order" &&
      review.personal_action === "NO_ACTION" &&
      review.formal_eligibility === false &&
      review.trade_eligible === false &&
      review.risk_review_eligible === false &&
      review.position_guidance === null &&
      review.holding_ownership === "NOT_VERIFIED_HERE" &&
      review.current_conditions_scope ===
        "RAW_UNADJUSTED_NOT_PERSONAL_ACTION" &&
      binding(review.current_case_binding) &&
      (review.entry_case_binding === null ||
        binding(review.entry_case_binding)) &&
      !!plan &&
      plan.action === "no_order" &&
      plan.signal_state !== "BLOCKED" &&
      plan.candidate_lifecycle !== "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY" &&
      plan.case_path === review.current_case_binding.path &&
      plan.case_sha256 === review.current_case_binding.sha256 &&
      !!explain &&
      explain.schema_version === "hotspot-lifecycle-explanation-v1" &&
      explain.action === "no_order" &&
      explain.selected_review === review.observed_review &&
      explain.source_scope ===
        "REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS" &&
      (!explain.current_price_observation ||
        explain.current_price_observation.as_of === plan.market_trade_date) &&
      strings(review.blockers) &&
      strings(review.required_external_reviews) &&
      strings(explain.why_not_add) &&
      strings(explain.required_external_reviews) &&
      JSON.stringify(review.required_external_reviews) ===
        JSON.stringify(explain.required_external_reviews) &&
      Array.isArray(explain.decision_path) &&
      explain.decision_path.every(
        (step) =>
          record(step) &&
          typeof step.check === "string" &&
          typeof step.outcome === "string" &&
          record(step.values) &&
          Array.isArray(step.evidence_bindings) &&
          step.evidence_bindings.every(binding),
      )
    );
  } catch {
    return false;
  }
}
function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未知";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value))
    return value.length
      ? value.map(text).join("；")
      : "无列明项，不代表已完成核验";
  if (record(value))
    return (
      Object.entries(value)
        .filter(([key]) => !/binding|sha256/.test(key))
        .map(([key, item]) => `${fields[key] ?? key}：${text(item)}`)
        .join("；") || "未知"
    );
  return labels[String(value)] ?? String(value);
}

/** Check producer postconditions, never select or recalculate a trading rule. */
function consistentState(review: Review, plan: CurrentPricePlan) {
  const explanation = review.decision_explanation;
  const outcome = (check: string) => {
    const matches = explanation.decision_path.filter(
      (step) => step.check === check,
    );
    return matches.length === 1 ? matches[0].outcome : undefined;
  };
  const hasEntry = review.entry_case_binding !== null;
  if (
    hasEntry !==
    (typeof review.entry_at === "string" && !!review.entry_at.trim())
  )
    return false;
  if (plan.signal_state === "STALE" && review.current_data_status === "CURRENT")
    return false;
  if (
    outcome("CURRENT_DATA") &&
    outcome("CURRENT_DATA") !== review.current_data_status
  )
    return false;
  if (
    review.price_comparability &&
    outcome("PRICE_COMPARABILITY") &&
    outcome("PRICE_COMPARABILITY") !== review.price_comparability.status
  )
    return false;
  if (review.current_data_status !== "CURRENT")
    return (
      review.status === "NOT_ASSESSABLE" &&
      review.observed_review === "UNKNOWN" &&
      explanation.current_price_observation === null &&
      explanation.decision_path
        .filter((step) => /^CURRENT_(ADD|REDUCE|EXIT|OPEN)$/.test(step.check))
        .every((step) => step.outcome === "NOT_EVALUATED")
    );
  if (review.status === "NOT_ASSESSABLE")
    return review.observed_review === "UNKNOWN";
  if (review.source_integrity !== "VERIFIED") return false;
  if (review.status === "CURRENT_STRUCTURE_ONLY")
    return (
      !hasEntry &&
      ["WATCH", "ENTRY_OBSERVATION"].includes(review.observed_review)
    );
  if (
    review.status !== "STRUCTURAL_COMPARISON_ONLY" ||
    !hasEntry ||
    !record(review.original_entry_comparison) ||
    review.price_comparability?.status !== "CONFIRMED" ||
    outcome("CURRENT_DATA") !== "CURRENT" ||
    outcome("ENTRY_REFERENCE") !== "VERIFIED_REFERENCE_ONLY" ||
    outcome("ENTRY_RULE_COMPATIBILITY") !== "MATCH" ||
    outcome("PRICE_COMPARABILITY") !== "CONFIRMED"
  )
    return false;
  const versions = explanation.recomputed_rule_versions;
  if (!versions?.entry || versions.current !== versions.entry) return false;
  const firstBreach = review.original_entry_comparison.first_breach_at;
  if (firstBreach !== null && (typeof firstBreach !== "string" || !firstBreach))
    return false;
  if (
    outcome("ORIGINAL_PROTECTION") !==
    (firstBreach ? "BREACHED" : "NO_OBSERVED_BREACH")
  )
    return false;
  // EXIT may retain a known earlier breach even when later bar coverage has gaps.
  if (review.observed_review === "EXIT_STRUCTURE_REVIEW")
    return (
      outcome("ORIGINAL_PROTECTION") === "BREACHED" ||
      outcome("CURRENT_EXIT") === "OBSERVED"
    );
  if (firstBreach || outcome("CURRENT_EXIT") !== "NOT_OBSERVED") return false;
  if (
    review.original_entry_comparison.coverage !== "COMPLETE" ||
    outcome("CONTINUITY_COVERAGE") !== "COMPLETE"
  )
    return false;
  if (review.observed_review === "ADD_STRUCTURE_REVIEW")
    return (
      outcome("CURRENT_REDUCE") === "NOT_OBSERVED" &&
      outcome("CURRENT_ADD") === "OBSERVED" &&
      outcome("STRUCTURE_QUALITY") === "RESEARCH_ONLY"
    );
  if (review.observed_review === "REDUCE_STRUCTURE_REVIEW")
    return outcome("CURRENT_REDUCE") === "OBSERVED";
  return (
    review.observed_review === "HOLD_STRUCTURE_OBSERVATION" &&
    outcome("CURRENT_REDUCE") === "NOT_OBSERVED" &&
    (outcome("CURRENT_ADD") === "NOT_OBSERVED" ||
      (outcome("CURRENT_ADD") === "OBSERVED" &&
        !!outcome("STRUCTURE_QUALITY") &&
        outcome("STRUCTURE_QUALITY") !== "RESEARCH_ONLY" &&
        outcome("STRUCTURE_QUALITY") !== "NOT_EVALUATED"))
  );
}
function Evidence({
  bindings,
}: {
  bindings: { path: string; sha256: string }[];
}) {
  return (
    <details>
      <summary>原件引用与 Hash</summary>
      {bindings.length ? (
        <ul>
          {bindings.map((ref, index) => (
            <li key={index}>
              <code>{ref.path}</code>
              <br />
              <code>SHA-256 {ref.sha256}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>本步未提供证据绑定，不能视为已核验。</p>
      )}
    </details>
  );
}

export function HotspotLifecycleReview({
  review,
  symbol,
  plan,
  available = true,
}: {
  review?: Review | null;
  symbol: string;
  plan?: CurrentPricePlan | null;
  available?: boolean;
}) {
  if (!available || !review)
    return (
      <section aria-label="波段结构连续性复核">
        <h3>波段结构连续性复核</h3>
        <p role="status">
          结构连续性材料尚未接入或当前不可核验，暂不可评价；这不等于没有机会或未触发风险。
        </p>
      </section>
    );
  if (!bound(review, symbol, plan))
    return (
      <section aria-label="波段结构连续性复核">
        <h3>波段结构连续性复核</h3>
        <p role="alert">
          结构连续性材料与当前证券、父计划来源或只读合同不匹配，暂不可评价。
        </p>
      </section>
    );
  if (!consistentState(review, plan!))
    return (
      <section
        aria-label="波段结构连续性复核"
        style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
      >
        <h3>波段结构连续性复核</h3>
        <p role="alert">
          父计划、入场参考、价格可比性或评估状态互相矛盾，暂不可评价；不采纳为当前持有、加仓、减仓或退出结论。
        </p>
        <details>
          <summary>原报告历史说明（不作为当前动作）</summary>
          <p>
            原报告评估时点：{text(review.evaluated_at)}；原报告依据：
            {text(review.decision_explanation.basis_code)}
            。参考证据不是已核验持仓归属。
          </p>
          {review.original_entry_comparison && (
            <dl>
              {Object.entries(review.original_entry_comparison).map(
                ([key, value]) => (
                  <div key={key}>
                    <dt>{fields[key] ?? key}</dt>
                    <dd style={{ marginLeft: 0 }}>{text(value)}</dd>
                  </div>
                ),
              )}
            </dl>
          )}
          <p>
            保留原始保护价与首次破位记录，不将未复权历史记录升级为有效动作。
          </p>
          <Evidence
            bindings={[
              review.current_case_binding,
              ...(review.entry_case_binding ? [review.entry_case_binding] : []),
            ]}
          />
        </details>
      </section>
    );
  const explain = review.decision_explanation;
  const price = explain.current_price_observation;
  const comparison = review.original_entry_comparison;
  return (
    <section
      aria-label="波段结构连续性复核"
      style={{
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        padding: "12px 0",
      }}
    >
      <h3>波段结构连续性复核</h3>
      <p>
        仅供研究与结构复核，不授予个人加仓或交易权限。参考案例不等于真实持仓、入场论据或成交记录。
      </p>
      {!review.entry_case_binding && (
        <p role="status">未提供原入场，仅当前结构观察；不是持有或加仓结论。</p>
      )}
      <p>
        本次观察：<strong>{text(explain.selected_review)}</strong>；判定依据：
        {text(explain.basis_code)}。
      </p>
      <p>
        行情状态：{text(review.current_data_status)}；原件状态：
        {text(review.source_integrity)}；评估时点：{text(review.evaluated_at)}。
      </p>
      <p>
        价格观察（元）：{text(price?.price)}；观察日期：{text(price?.as_of)}
        ；原件可得时点：{text(price?.available_at)}。
        {text(price?.reference_price_scope)}；不是盘中实时价，也不等于当前
        PIT、策略或交易准入。
      </p>
      <p>未评估不等于未触发；维持结构观察不代表原始投资论据已经验证。</p>
      {comparison && (
        <details>
          <summary>原始保护位与破位记录（原始未复权观察）</summary>
          <dl>
            {Object.entries(comparison).map(([key, value]) => (
              <div key={key} style={{ minWidth: 0 }}>
                <dt>{fields[key] ?? key}</dt>
                <dd style={{ marginLeft: 0 }}>{text(value)}</dd>
              </div>
            ))}
          </dl>
          <p>
            后来恢复或滚动保护价降低不能抹去首次破位；这些记录不是已核验可比性的加仓或退出动作。
          </p>
        </details>
      )}
      {review.unadjusted_structural_observation && (
        <p role="status">
          保留未复权原始结构记录，但不将其作为有效持有、加仓或退出结论；以价格可比性核验和外部复核为准。
        </p>
      )}
      <details>
        <summary>
          中文判定步骤与实际输入 · {explain.decision_path.length} 项
        </summary>
        {explain.decision_path.length ? (
          <ol>
            {explain.decision_path.map((step, index) => (
              <li key={index}>
                <strong>{text(step.check)}</strong>：{text(step.outcome)}。
                <dl>
                  {Object.entries(step.values)
                    .filter(([key]) => !/binding|sha256/.test(key))
                    .map(([key, value]) => (
                      <div key={key}>
                        <dt>{fields[key] ?? key}</dt>
                        <dd style={{ marginLeft: 0 }}>{text(value)}</dd>
                      </div>
                    ))}
                </dl>
                <Evidence bindings={step.evidence_bindings} />
              </li>
            ))}
          </ol>
        ) : (
          <p>未提供判定路径，不能视为已完成评估。</p>
        )}
      </details>
      <h4>为何不能据此加仓</h4>
      {explain.why_not_add.length ? (
        <ul>
          {explain.why_not_add.map((reason, index) => (
            <li key={index}>{text(reason)}</li>
          ))}
        </ul>
      ) : (
        <p>结构层面的未加仓原因未列明，不代表已获加仓权限。</p>
      )}
      <h4>仍需独立复核</h4>
      {explain.required_external_reviews.length ? (
        <ul>
          {explain.required_external_reviews.map((reason, index) => (
            <li key={index}>{text(reason)}</li>
          ))}
        </ul>
      ) : (
        <p>外部复核事项未列明，不能视为已完成。</p>
      )}
      <details>
        <summary>规则版本、阻断项与原件</summary>
        <p>
          当前参考重算规则：{text(explain.recomputed_rule_versions?.current)}
          ；原始参考重算规则：{text(explain.recomputed_rule_versions?.entry)}。
          本次重算不证明原入场当时实际采用了这些规则。
        </p>
        <p>
          参考入场时点：{text(review.entry_at)}；策略验证：
          {text(review.strategy_validation)}；个人动作：不采取动作。
        </p>
        <ul>
          {review.blockers.map((reason, index) => (
            <li key={index}>{text(reason)}</li>
          ))}
        </ul>
        <Evidence
          bindings={[
            review.current_case_binding,
            ...(review.entry_case_binding ? [review.entry_case_binding] : []),
          ]}
        />
      </details>
    </section>
  );
}
