type ObjectValue = Record<string, any>;
const object = (v: unknown): v is ObjectValue =>
  !!v && typeof v === "object" && !Array.isArray(v);
const numberText = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d+(?:\.\d+)?$/.test(v) &&
  Number.isFinite(Number(v));
const day = (v: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v;
const stamp = (v: unknown): v is string =>
  typeof v === "string" &&
  day(v.slice(0, 10)) &&
  /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
  Number.isFinite(Date.parse(v));
const bound = (v: unknown) =>
  object(v) &&
  typeof v.path === "string" &&
  v.path.startsWith("runtime/") &&
  !v.path.split(/[\\/]/).includes("..") &&
  /^[a-f0-9]{64}$/.test(v.sha256);
const noPermissions = (v: ObjectValue) =>
  v.action === "no_order" &&
  v.namespace === "SIMULATED" &&
  v.actual_account_used === false &&
  v.actual_owned_entry_created === false &&
  v.formal_eligibility === false &&
  v.broker_execution_permission === false &&
  v.trade_eligible === false &&
  v.position_guidance === null &&
  v.strategy_validation === "NOT_PROVEN";
const intents = { ADD: "加仓", REDUCE: "减仓", EXIT: "退出" };
const sourceLabels: Record<string, string> = {
  ORIGIN_NOT_ATTESTED: "公开归档原件Hash已核，但来源身份与历史可得性未独立认证",
  TEST_ONLY: "合成测试来源",
  SIMULATED: "模拟来源",
  MIXED_OR_UNVERIFIED_SOURCES: "混合或未核清来源",
};
const reviewStates = [
  "UNKNOWN",
  "WATCH",
  "ENTRY_OBSERVATION",
  "EXIT_STRUCTURE_REVIEW",
  "REDUCE_STRUCTURE_REVIEW",
  "ADD_STRUCTURE_REVIEW",
  "HOLD_STRUCTURE_OBSERVATION",
];

export function verifiedSimulatedHotspotLifecycle(value: unknown): boolean {
  if (
    !object(value) ||
    value.schema_version !== "hotspot-simulated-lifecycle-read-v1" ||
    value.status !== "VERIFIED_HISTORICAL_SIMULATION" ||
    value.verified !== true ||
    value.verification_scope !==
      "HASH_NATIVE_REPLAY_AND_SIMULATED_ACCOUNTING_ONLY" ||
    value.historical_only !== true ||
    value.current_signal !== false ||
    value.current_pit !== false ||
    !noPermissions(value) ||
    !stamp(value.verified_at) ||
    !bound(value.receipt_binding) ||
    !Number.isInteger(value.source_file_count) ||
    value.source_file_count < 1
  )
    return false;
  const report = value.report;
  if (
    !object(report) ||
    report.schema_version !== "hotspot-simulated-lifecycle-v1" ||
    !noPermissions(report) ||
    report.scope !== "RETAINED_SOURCE_RETROSPECTIVE_NOT_PIT_OOS_OR_SHADOW" ||
    !/^\d{6}$/.test(report.symbol) ||
    !stamp(report.generated_at) ||
    Date.parse(report.generated_at) > Date.parse(value.verified_at) ||
    !Object.keys(sourceLabels).includes(report.market_source_scope) ||
    report.simulated_fill_count !== 1 ||
    report.followup_fill_count !== 0 ||
    !object(report.entry_reference) ||
    !stamp(report.entry_reference.assumed_entry_at) ||
    report.entry_reference.symbol !== report.symbol ||
    !numberText(report.entry_reference.reference_close) ||
    !numberText(report.entry_reference.original_protection_price) ||
    Number(report.entry_reference.reference_close) <= 0 ||
    Number(report.entry_reference.original_protection_price) <= 0 ||
    report.entry_reference.entry_origin !==
      "DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED" ||
    report.entry_reference.fill_scope !==
      "HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL" ||
    !/^[a-f0-9]{64}$/.test(report.entry_freeze_sha256) ||
    !object(report.journal_receipt) ||
    !bound(report.journal_receipt) ||
    report.journal_receipt.namespace !== "SIMULATED" ||
    report.journal_receipt.retained !== true ||
    report.journal_receipt.record_count !== 3 ||
    report.journal_receipt.restart_verified !== true ||
    report.journal_receipt.unchanged_by_followup !== true ||
    report.journal_receipt.confirmation_idempotent !== true ||
    !object(report.simulated_accounting) ||
    !numberText(report.simulated_accounting.cash_cny) ||
    !Array.isArray(report.steps) ||
    !report.steps.length ||
    report.steps.length > 32
  )
    return false;
  let previous = Date.parse(report.entry_reference.assumed_entry_at);
  return report.steps.every((step: unknown) => {
    if (
      !object(step) ||
      step.namespace !== "SIMULATED" ||
      step.action !== "no_order" ||
      !object(step.lifecycle_review) ||
      !object(step.intentions)
    )
      return false;
    const review = step.lifecycle_review;
    if (
      !stamp(review.evaluated_at) ||
      Date.parse(review.evaluated_at) < previous ||
      Date.parse(review.evaluated_at) <=
        Date.parse(report.entry_reference.assumed_entry_at) ||
      Date.parse(review.evaluated_at) > Date.parse(report.generated_at) ||
      review.symbol !== report.symbol ||
      review.action !== "no_order" ||
      !object(review.decision_explanation) ||
      !reviewStates.includes(review.decision_explanation.selected_review) ||
      !Array.isArray(review.decision_explanation.decision_path) ||
      !object(review.price_comparability) ||
      typeof review.price_comparability.status !== "string"
    )
      return false;
    previous = Date.parse(review.evaluated_at);
    const protection = review.decision_explanation.decision_path.find(
      (row: ObjectValue) => row?.check === "ORIGINAL_PROTECTION",
    )?.values;
    if (
      protection !== undefined &&
      (!object(protection) ||
        protection.original_protection_price !==
          report.entry_reference.original_protection_price)
    )
      return false;
    if (
      review.current_conditions !== undefined &&
      (!object(review.current_conditions) ||
        Object.keys(intents).some(
          (intent) =>
            !object(review.current_conditions[intent]) ||
            typeof review.current_conditions[intent].rule !== "string",
        ))
    )
      return false;
    return Object.keys(intents).every((intent) => {
      const row = step.intentions[intent];
      return (
        object(row) &&
        row.action === "no_order" &&
        row.status === "REVIEW_ONLY_NO_SIMULATED_FOLLOWUP_FILL" &&
        (typeof row.observed === "boolean" || row.observed === null) &&
        Array.isArray(row.blockers) &&
        row.blockers.includes("SIMULATED_ENTRY_IS_NOT_VERIFIED_OWNERSHIP") &&
        row.blockers.includes("INDEPENDENT_STRATEGY_ADMISSION_NOT_PROVEN")
      );
    });
  });
}

export function SimulatedHotspotLifecycleReview({
  value,
}: {
  value?: unknown;
}) {
  if (value == null) return null;
  if (!verifiedSimulatedHotspotLifecycle(value))
    return (
      <p role="alert">
        波段封存演练暂不可核验；不据此判断当前持仓或发出加减仓信号。
      </p>
    );
  const data = value as ObjectValue,
    report = data.report,
    entry = report.entry_reference;
  const scope = sourceLabels[report.market_source_scope];
  return (
    <section
      aria-label="封存波段模拟入场与后续复核"
      style={{ minWidth: 0, overflowWrap: "anywhere", marginBlock: 16 }}
    >
      <h4>封存波段模拟入场与后续复核 · {report.symbol}</h4>
      <p>
        {scope}。这是事后演练，不是当前候选、真实持仓、样本外验证或真实Shadow。
      </p>
      <p>
        假设入场时点 {entry.assumed_entry_at}；按封存收盘价{" "}
        {entry.reference_close}{" "}
        元假设100股入场，费用假设5元。不是策略触发，也不是建议价格或数量。
      </p>
      <p>
        <strong>原入场保护参考：{entry.original_protection_price} 元</strong>
        。价格口径未核清时不折算为当前可执行保护价。
      </p>
      {report.steps.map((step: ObjectValue, index: number) => {
        const review = step.lifecycle_review;
        const protection = review.decision_explanation.decision_path.find(
          (row: ObjectValue) => row?.check === "ORIGINAL_PROTECTION",
        )?.values;
        return (
          <div key={index}>
            <h5>后续复核 {review.evaluated_at}</h5>
            <p>
              最终结果：
              {review.decision_explanation.selected_review === "UNKNOWN"
                ? "无法评估可执行动作"
                : "仅历史复核，不是当前许可"}
              ；公司行动价格口径：
              {review.price_comparability.status === "UNKNOWN"
                ? "尚未核清"
                : review.price_comparability.status}
              。
            </p>
            {object(protection) &&
              numberText(protection.current_rolling_protection_price) && (
                <p>
                  该时点滚动参考 {protection.current_rolling_protection_price}{" "}
                  元；原入场保护位未被替换。
                </p>
              )}
            <ul>
              {Object.entries(intents).map(([intent, label]) => (
                <li key={intent}>
                  {label}原始结构观察：
                  {step.intentions[intent].observed === null
                    ? "无法核验"
                    : step.intentions[intent].observed
                      ? "已触及"
                      : "未触及"}
                  ；未生成后续成交，模拟Entry不证明真实可卖数量，独立策略未准入。
                </li>
              ))}
            </ul>
            <details>
              <summary>该时点的结构规则说明</summary>
              {object(review.current_conditions) ? (
                <ul>
                  {Object.entries(intents).map(([intent, label]) => (
                    <li key={intent}>
                      {label}：{review.current_conditions[intent].rule}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>未返回可核验的原规则，不能由观察标签推断操作逻辑。</p>
              )}
              <p>
                原始未复权结构观察不等于同口径的交易条件，公司行动与策略准入限制仍有效。
              </p>
            </details>
          </div>
        );
      })}
      <p>
        隔离模拟账户余额 {report.simulated_accounting.cash_cny}{" "}
        元；仅1笔假设入场、后续成交0笔。两个策略尚未据此完成同一账户的真实资料仓位验收。
      </p>
      <details>
        <summary>演练来源与账本绑定</summary>
        <p>
          封存生成 {report.generated_at}；只读复核 {data.verified_at}；原件{" "}
          {data.source_file_count} 件。
        </p>
        <p>
          <code>{data.receipt_binding.path}</code>
          <br />
          <code>{data.receipt_binding.sha256}</code>
        </p>
        <p>
          <code>{report.journal_receipt.path}</code>
          <br />
          <code>{report.journal_receipt.sha256}</code>
        </p>
      </details>
    </section>
  );
}
