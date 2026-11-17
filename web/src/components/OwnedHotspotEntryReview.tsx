import type { HotspotLifecycleReview } from "../types/api";

export interface OwnedHotspotLifecycle {
  status: "NOT_ASSESSABLE" | "REFERENCE_ONLY";
  ownership_verified: boolean;
  ownership_scope?: "INHERITED_AUTHENTICATED_JOURNAL_CONTEXT";
  pretrade_proven: false;
  personal_add_permission: false;
  formal_eligibility: false;
  position_guidance: null;
  action: "no_order";
  blockers: string[];
  items: {
    status: "NOT_ASSESSABLE" | "REFERENCE_ONLY";
    source_reference_status:
      "SOURCE_REPLAYED" | "UNVERIFIED" | "REFERENCE_ONLY";
    pretrade_proven: false;
    personal_add_permission: false;
    formal_eligibility: false;
    action: "no_order";
    blockers: string[];
    research_reference: HotspotLifecycleReview | null;
    entry_id?: string;
    entry_artifact_id?: string;
    fill_record_sha256: string;
    original_case_binding?: { path: string; sha256: string };
    original_evaluated_at?: string;
    snapshot_recorded_at?: string;
    trade_date?: string;
    execution_at?: null;
    scope?: "ORIGINAL_RESEARCH_REFERENCE_NOT_EXECUTION_CONTINUITY";
  }[];
}

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
function binding(value: unknown): value is { path: string; sha256: string } {
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
function pending(value: unknown): boolean {
  return (
    record(value) &&
    value.action === "no_order" &&
    value.pretrade_proven === false &&
    value.personal_add_permission === false &&
    value.formal_eligibility === false &&
    ["NOT_ASSESSABLE", "REFERENCE_ONLY"].includes(String(value.status)) &&
    strings(value.blockers)
  );
}
function aware(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}
function replayed(
  item: OwnedHotspotLifecycle["items"][number],
  symbol: string,
  currentTradeDate?: string | null,
) {
  const ref = item.research_reference;
  return (
    pending(item) &&
    item.source_reference_status === "SOURCE_REPLAYED" &&
    typeof item.fill_record_sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(item.fill_record_sha256) &&
    item.scope === "ORIGINAL_RESEARCH_REFERENCE_NOT_EXECUTION_CONTINUITY" &&
    item.execution_at === null &&
    typeof item.entry_id === "string" &&
    !!item.entry_id &&
    typeof item.entry_artifact_id === "string" &&
    !!item.entry_artifact_id &&
    binding(item.original_case_binding) &&
    !!ref &&
    ref.schema_version === "hotspot-entry-structure-continuity-v2" &&
    ref.symbol === symbol &&
    ref.action === "no_order" &&
    ref.personal_action === "NO_ACTION" &&
    ref.formal_eligibility === false &&
    ref.trade_eligible === false &&
    ref.risk_review_eligible === false &&
    ref.holding_ownership === "NOT_VERIFIED_HERE" &&
    ref.position_guidance === null &&
    ref.current_conditions_scope === "RAW_UNADJUSTED_NOT_PERSONAL_ACTION" &&
    ref.decision_explanation?.schema_version ===
      "hotspot-lifecycle-explanation-v1" &&
    ref.decision_explanation.action === "no_order" &&
    ref.decision_explanation.selected_review === ref.observed_review &&
    ref.current_data_status === "CURRENT" &&
    ref.source_integrity === "VERIFIED" &&
    strings(ref.blockers) &&
    binding(ref.entry_case_binding) &&
    binding(ref.current_case_binding) &&
    ref.entry_case_binding.path === item.original_case_binding.path &&
    ref.entry_case_binding.sha256 === item.original_case_binding.sha256 &&
    aware(item.original_evaluated_at) &&
    ref.entry_at === item.original_evaluated_at &&
    aware(item.snapshot_recorded_at) &&
    aware(ref.evaluated_at) &&
    Date.parse(item.original_evaluated_at) <=
      Date.parse(item.snapshot_recorded_at) &&
    Date.parse(item.snapshot_recorded_at) <= Date.parse(ref.evaluated_at) &&
    typeof item.trade_date === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(item.trade_date) &&
    (!currentTradeDate ||
      ref.decision_explanation?.current_price_observation?.as_of ===
        currentTradeDate)
  );
}
const reasons: Record<string, string> = {
  EXACT_EXECUTION_TIME_NOT_PROVEN:
    "精确成交时点及当时已知信息未证明，研究参考不能代替成交连续性。",
  VERIFIED_OWNED_CONTEXT_REQUIRED: "尚无已认证的持仓归属上下文。",
  OWNED_BINDINGS_REQUIRED: "缺少原入场的封存绑定。",
  ORIGINAL_BINDING_REQUIRED: "缺少同期登记的原始来源绑定。",
  ENTRY_REFERENCE_MISMATCH: "原 Entry 与封存来源版本不一致。",
  ORIGINAL_CASE_MISMATCH: "原始结构案例与买入时封存版本不一致。",
  ORIGINAL_SOURCE_NOT_REPLAYABLE: "原始结构原件无法核验重放。",
  CURRENT_SOURCE_NOT_REPLAYABLE: "当前结构原件无法核验重放。",
  CURRENT_RULE_MISMATCH: "当前规则与已绑定原件不一致。",
  ENTRY_TIME_MISMATCH: "原入场材料的时间关系未通过核验。",
  PRICE_BASIS_UNKNOWN: "公司行动与价格口径可比性未知，不能假定原价可直接比较。",
  PRICE_BASIS_INCOMPARABLE:
    "原始与当期价格口径不可直接比较，不能据此判断加减仓。",
  ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE:
    "原参考至当前的完整行情存在缺口，不能推断连续性完整。",
};
function gaps(values: string[]) {
  return values.length ? (
    values.map((value, index) => (
      <li key={index}>
        {reasons[value] ?? "该项核验存在未确认缺口，不能视为已完成。"}
      </li>
    ))
  ) : (
    <li>未列出缺口不代表成交连续性或加仓资格已通过。</li>
  );
}
const show = (value: unknown) =>
  typeof value === "string" && value
    ? value
    : typeof value === "number" && Number.isFinite(value)
      ? String(value)
      : "未知";

export function OwnedHotspotEntryReview({
  material,
  symbol,
  strategy,
  ownershipVerified,
  currentTradeDate,
  thesisExit = false,
}: {
  material?: OwnedHotspotLifecycle | null;
  symbol: string;
  strategy: string;
  ownershipVerified?: boolean;
  currentTradeDate?: string | null;
  thesisExit?: boolean;
}) {
  if (!material || !["HOTSPOT_SATELLITE", "hotspot"].includes(strategy))
    return null;
  const valid =
    pending(material) &&
    material.position_guidance === null &&
    Array.isArray(material.items) &&
    material.items.every((item) => record(item) && pending(item));
  return (
    <section
      aria-label="原始波段入场依据核验"
      style={{
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        padding: "12px 0",
      }}
    >
      <h4>原始波段入场依据核验</h4>
      <p>
        此处仅说明原 Entry
        的研究参考与来源绑定。交易前已知信息和精确成交时点尚未证明，不能单独支持继续持有或加仓数量。
      </p>
      {!valid ? (
        <p role="alert">
          入场依据材料缺失、损坏或与当前只读合同不一致，暂不可采信；不改变上方服务端决策。
        </p>
      ) : material.ownership_verified !== true ||
        ownershipVerified !== true ||
        material.ownership_scope !==
          "INHERITED_AUTHENTICATED_JOURNAL_CONTEXT" ? (
        <p role="status">持仓归属来源尚未核验，不能展示为已验证的原入场链。</p>
      ) : (
        <>
          <p>
            持仓归属仅沿用已认证台账上下文；本材料状态仍为不可评价／仅参考，不代表交易前验证完成。
          </p>
          {material.items.length ? (
            material.items.map((item, index) => {
              if (!replayed(item, symbol, currentTradeDate))
                return (
                  <p role="status" key={index}>
                    第 {index + 1}{" "}
                    项原入场来源未核验、仅参考或版本不一致，不能视为已完成。原件与日期暂不可采信。
                  </p>
                );
              const ref = item.research_reference!;
              const comparison = ref.original_entry_comparison;
              return (
                <details key={index}>
                  <summary>
                    原 Entry 研究参考 · 第 {index + 1}{" "}
                    项（来源可重放，非成交连续性证明）
                  </summary>
                  <dl>
                    {[
                      ["原 Entry", item.entry_id],
                      ["登记交易日期（非精确成交时刻）", item.trade_date],
                      ["原始结构评估时点", item.original_evaluated_at],
                      [
                        "记录时封存时点（不证明交易前已知）",
                        item.snapshot_recorded_at,
                      ],
                      ["当期结构核验时点", ref.evaluated_at],
                      [
                        "当期行情日期",
                        ref.decision_explanation?.current_price_observation
                          ?.as_of,
                      ],
                      [
                        "当期原件状态",
                        ref.source_integrity === "VERIFIED"
                          ? "原件完整性已核验；不等于策略或执行获准"
                          : "未知",
                      ],
                      [
                        "研究参考状态",
                        ref.status === "STRUCTURAL_COMPARISON_ONLY"
                          ? "仅结构对比，仍不证明原始成交连续性"
                          : "尚不可评价；不能推断持有或加仓",
                      ],
                      [
                        "原始来源状态",
                        "已完成来源重放，仅限原研究参考，不证明交易前已知",
                      ],
                      [
                        "价格口径可比性",
                        ref.price_comparability?.status === "CONFIRMED"
                          ? "仅此研究窗口同口径已确认"
                          : ref.price_comparability?.status === "INCOMPARABLE"
                            ? "不可直接比较"
                            : "未知，不能假定原价可比",
                      ],
                      [
                        "原始参考保护位（元，未复权）",
                        comparison?.original_protection_price,
                      ],
                      ["首次收盘破位时点", comparison?.first_breach_at],
                      [
                        "连续行情覆盖",
                        comparison?.coverage === "COMPLETE"
                          ? "参考价格窗口完整，仍不等于成交连续性完整"
                          : "未确认完整覆盖",
                      ],
                    ].map(([title, value]) => (
                      <div
                        key={String(title)}
                        style={{ minWidth: 0, marginBottom: 6 }}
                      >
                        <dt>{String(title)}</dt>
                        <dd style={{ marginLeft: 0 }}>{show(value)}</dd>
                      </div>
                    ))}
                  </dl>
                  <p>
                    精确成交时刻：未知；交易前证明：未成立；个人加仓许可：未授予。
                  </p>
                  <h5>仍需处理的连续性缺口</h5>
                  <ul>{gaps([...item.blockers, ...ref.blockers])}</ul>
                  <details>
                    <summary>原始／当期来源与精确版本</summary>
                    <p>
                      原 Entry 产物：<code>{item.entry_artifact_id}</code>
                    </p>
                    {[
                      ["原始案例", item.original_case_binding!],
                      ["当期案例", ref.current_case_binding],
                    ].map(([title, value]) => {
                      const source = value as { path: string; sha256: string };
                      return (
                        <p key={String(title)}>
                          {String(title)}：<code>{source.path}</code>
                          <br />
                          <code>SHA-256 {source.sha256}</code>
                        </p>
                      );
                    })}
                  </details>
                </details>
              );
            })
          ) : (
            <p>尚无可核验的原入场研究参考，不从当前候选反推原入场。</p>
          )}
          <ul>{gaps(material.blockers)}</ul>
        </>
      )}
      {thesisExit && (
        <p>
          上方退出复核来自服务端原始 Thesis
          破坏判断，不是本材料证明了价格连续性；仍以现有可卖数量与风险核验为准。
        </p>
      )}
      <p>
        本材料不修改上方个人动作、复核数量或交易权限；实际买卖仍由本人确认。
      </p>
    </section>
  );
}
