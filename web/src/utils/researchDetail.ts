import type {
  PriceBridgeCompatibility,
  PriceBridgeExecution,
  ResearchGateRow,
  ResearchReadingRow,
  ResearchValuation,
} from "../types/api";

export interface EvidenceLine {
  text: string;
  evidenceRefs: string[];
}

export interface GateView {
  key: string;
  label: string;
  status: string | null;
  statusLabel: string;
  reason: string | null;
  nextAction: string | null;
}

export interface BridgeExecutionView {
  status: string;
  statusLabel: string;
  comparableLabel: string;
  comparable: boolean;
  quoteDate: string | null;
  displayPrice: string | null;
  rows: Array<{ key: string; label: string; value: string }>;
  ladder: Array<{
    key: string;
    label: string;
    eligible: boolean;
    reason: string | null;
  }>;
  reason: string | null;
  nextStep: string | null;
  sources: Array<{ label: string; url: string; sha256: string | null }>;
}

/**
 * 共享价格桥接的准入状态；未收录的代码原样返回，不推测含义。
 */
const BRIDGE_STATUS_TEXT: Record<string, string> = {
  INCREMENTAL_VALIDITY_BLOCKED:
    "增量有效性未通过，行情核验状态与具体缺口分别列示",
  QUOTE_VERIFIED_WITH_INCREMENTAL_VALIDITY:
    "增量复核支持条件性价格比较，正式决策仍须独立批准",
  QUOTE_VERIFIED_FOR_RESEARCH_INPUT: "行情已核验，可作为研究输入",
  QUOTE_VERIFIED_BUT_RESEARCH_STALE: "行情已核验，但晚于研究截止日",
  HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY: "仅展示的历史核验收盘",
  NOT_ADMITTED: "未准入",
  PENDING_EXTERNAL_DATA: "尚无已核验收盘",
  POINTER_UNAVAILABLE: "未登记当前行情绑定",
};

export function bridgeStatusLabel(status?: string | null): string {
  if (!status) return "未提供";
  return BRIDGE_STATUS_TEXT[status] ?? status;
}

function text(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const asText = typeof value === "string" ? value.trim() : String(value);
  return asText ? asText : null;
}

/**
 * 只整理共享程序真正执行过的准入结果：状态码转中文，字段缺失显示未提供，
 * 不新增价格、边际或仓位推断。
 */
export function bridgeExecutionView(
  execution?: PriceBridgeExecution | null,
): BridgeExecutionView | null {
  if (!execution || typeof execution !== "object") return null;
  const status = text(execution.status);
  if (!status) return null;
  const comparable = execution.comparison_eligible === true;
  const price = text(execution.display_price);
  const quoteDate = text(execution.quote_date);
  const rows = [
    {
      key: "quote_date",
      label: "已核验行情日期",
      value: quoteDate ?? "未提供",
    },
    {
      key: "display_price",
      label: "已核验收盘价",
      value: price ? `${price} 元` : "未提供",
    },
    {
      key: "research_day",
      label: "研究截止日",
      value: text(execution.research_day) ?? "未提供",
    },
    {
      key: "research_version",
      label: "登记研究版本",
      value: text(execution.research_version) ?? "未提供",
    },
    {
      key: "collected_at",
      label: "行情采集时间",
      value: text(execution.collected_at) ?? "未提供",
    },
    {
      key: "latest_completed_session",
      label: "最近已完成交易日",
      value: text(execution.latest_completed_session) ?? "未提供",
    },
    {
      key: "bundle",
      label: "行情包（SHA-256）",
      value: execution.bundle_path
        ? `${execution.bundle_path} / ${execution.bundle_sha256 ?? "未提供"}`
        : "未提供",
    },
    {
      key: "pointer",
      label: "登记文件（SHA-256）",
      value: execution.pointer_path
        ? `${execution.pointer_path} / ${execution.pointer_sha256 ?? "未提供"}`
        : "未提供",
    },
  ];
  if (execution.incremental_validity) {
    const incremental = execution.incremental_validity;
    rows.push(
      {
        key: "incremental_cutoff",
        label: "增量公告复核截止日（不改原研究截止）",
        value: text(incremental.review_cutoff) ?? "未提供",
      },
      {
        key: "incremental_announcements",
        label: "已绑定新增公告数",
        value: text(incremental.announcement_count) ?? "未提供",
      },
      {
        key: "incremental_status",
        label: "增量模型有效性",
        value: text(incremental.status) ?? "未提供",
      },
      {
        key: "incremental_blockers",
        label: "增量复核未通过条件",
        value:
          incremental.blockers.join("；") ||
          "无已返回阻塞；仍需核对独立正式资格",
      },
    );
  }
  const sources = (Array.isArray(execution.sources) ? execution.sources : [])
    .filter((row) => row && text(row.source_url))
    .map((row) => ({
      label: text(row.provider) ?? "来源",
      url: text(row.source_url) as string,
      sha256: text(row.sha256),
    }));
  return {
    status,
    statusLabel: bridgeStatusLabel(status),
    comparable,
    comparableLabel: comparable ? "已具备比较资格" : "尚不具备比较资格",
    quoteDate,
    displayPrice: price,
    rows,
    ladder: compatibilityLadder(execution.compatibility),
    reason: text(execution.reason),
    nextStep: text(execution.next_step),
    sources,
  };
}

const LADDER_LABELS: Array<{
  key: keyof PriceBridgeCompatibility;
  label: string;
}> = [
  { key: "verified_quote", label: "报价双源核验" },
  { key: "research_compatible", label: "研究覆盖报价日" },
  { key: "historical_reconstruction_eligible", label: "历史重建对比资格" },
  { key: "comparison_eligible", label: "价格比较准入" },
  { key: "formal_decision_eligible", label: "正式决策资格" },
];

/** 兼容性阶梯：只复制执行层的布尔结论，未提供的步骤不展示。 */
export function compatibilityLadder(
  compatibility?: PriceBridgeCompatibility | null,
): Array<{
  key: string;
  label: string;
  eligible: boolean;
  reason: string | null;
}> {
  if (!compatibility || typeof compatibility !== "object") return [];
  const rows: Array<{
    key: string;
    label: string;
    eligible: boolean;
    reason: string | null;
  }> = [];
  for (const step of LADDER_LABELS) {
    const item = compatibility[step.key];
    if (!item || typeof item.eligible !== "boolean") continue;
    rows.push({
      key: step.key,
      label: step.label,
      eligible: item.eligible,
      reason: text(item.reason),
    });
  }
  return rows;
}

/** The published decision process order is frozen by the read model. */
export const GATE_ORDER = [
  "financial_facts",
  "business_quality",
  "model_applicability",
  "valuation",
  "price_bridge",
  "research_gate",
  "portfolio_gate",
  "decision_gate",
] as const;

const GATE_LABELS: Record<string, string> = {
  financial_facts: "财务事实",
  business_quality: "商业质量",
  model_applicability: "模型适用性",
  valuation: "估值",
  price_bridge: "价格桥接",
  research_gate: "研究门",
  portfolio_gate: "组合门",
  decision_gate: "决策门",
};

/**
 * 只翻译已在真实产物中出现过的阻塞原文；未收录的文本原样返回，
 * 不推测含义，也不生成新的研究结论。
 */
const BLOCKER_TEXT: Record<string, string> = {
  "formal G3 human valuation approval not present": "缺少正式 G3 人工估值批准",
  "issuer-specific beta evidence missing; generic beta=1 assumption used":
    "缺少发行人特定贝塔证据，暂用通用 beta=1 假设",
  "ROIC and incremental ROIC remain unverified": "ROIC 与增量 ROIC 尚未核验",
  "H1 2026 interim report is unaudited": "2026 年半年报尚未审计",
  pending_economic_model_review: "经济模型复核待完成",
  pending_complete_event_materiality_review: "重大事件的完整性复核待完成",
  G3_估值门: "G3 估值门尚未通过",
  等待已验证收盘行情: "等待已验证的收盘行情",
  price_bridge_pending_external_data: "价格桥接等待外部数据",
  research_case_valuation_not_approved: "研究底稿估值尚未获批准",
  valuation_status_not_approved_for_research: "估值状态尚未获准用于研究结论",
  model_validity_unavailable: "模型有效性尚未提供",
  event_materiality_review_unavailable: "重大事件复核尚未完成",
  decision_dependency_artifacts_unavailable: "决策依赖产物不可用",
  predecision_eligibility_unavailable: "前置决策资格尚未提供",
  human_research_approval_not_resolved: "人工研究批准尚未完成",
  VALUE_EXPLANATION_BINDING_UNAVAILABLE: "已发布决策解释的绑定不可用",
};

/** 门禁键转中文短名；未收录返回 null，由调用方决定如何展示。 */
export function gateLabel(key?: string | null): string | null {
  if (!key) return null;
  return GATE_LABELS[key] ?? null;
}

/** PASS/BLOCKED/CONDITIONAL 转友好状态；null 为未提供，其他代码原样返回。 */
export function gateStatusLabel(status?: string | null): string {
  if (!status) return "未提供";
  if (status === "PASS") return "已通过";
  if (status === "BLOCKED") return "未通过";
  if (status === "CONDITIONAL") return "有条件";
  return status;
}

/**
 * 按冻结的八行顺序整理门禁；缺失行以对应键补位并标记未提供。
 */
export function gateRowViews(
  gates?: Array<ResearchGateRow | null> | null,
): GateView[] {
  const source = Array.isArray(gates) ? gates : [];
  return GATE_ORDER.map((fallbackKey, index) => {
    const row = source[index] ?? null;
    const key = row?.key || fallbackKey;
    return {
      key,
      label: gateLabel(key) ?? "其他门禁",
      status: row?.status ?? null,
      statusLabel: gateStatusLabel(row?.status),
      reason: row?.reason ?? null,
      nextAction: row?.next_action ?? null,
    };
  });
}

/**
 * 估值情景仅做两位小数展示舍入，不改变或重新计算存储值；
 * null/空值显示暂不可用，非数值原文返回。
 */
export function formatScenarioValue(value: unknown): string {
  if (value === null || value === undefined) return "暂不可用";
  const text = typeof value === "string" ? value.trim() : String(value);
  if (!text) return "暂不可用";
  const parsed = typeof value === "number" ? value : Number(text);
  if (!Number.isFinite(parsed)) return text;
  return parsed.toFixed(2);
}

/** 差价字段仅在 payload 确实带值时展示，原样输出不做换算。 */
export function marginText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = typeof value === "string" ? value.trim() : String(value);
  return text ? text : null;
}

export function suggestedStateText(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "NO_ACTION" || value === "no_order")
    return "当前无合法动作候选";
  return value;
}

function headlineValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = typeof value === "string" ? value.trim() : String(value);
  if (!text) return null;
  const parsed = typeof value === "number" ? value : Number(text);
  if (!Number.isFinite(parsed)) return text;
  return parsed.toFixed(2);
}

export interface HeadlineInput {
  valuation?: Partial<ResearchValuation> | null;
  bridge?: BridgeExecutionView | null;
  researchDay?: string | null;
  marginToBase?: string | null;
}

/**
 * 一句话研究结论：只根据真实估值字段、价格桥接执行结果和登记日期拼装，
 * 不按公司写死文案；价格不具备比较资格时不暗示任何安全边际。
 */
export function researchHeadline(input: HeadlineInput): string {
  const valuation = input.valuation ?? {};
  const hasScenarios = [valuation.bear, valuation.base, valuation.bull].some(
    (value) => headlineValue(value) !== null,
  );
  const day = text(valuation.valuation_date) ?? text(input.researchDay);
  const dayText = day ? `研究截止 ${day}` : "研究截止日期未提供";
  if (!hasScenarios) {
    return "尚无可用估值研究：没有可复核的 Bear/Base/Bull 结果，暂不能评估价格与估值的关系。";
  }
  const base = headlineValue(valuation.base);
  const baseText = base !== null ? `基准 ${base} 元，` : "";
  const bridge = input.bridge;
  if (bridge?.comparable) {
    const margin = text(input.marginToBase);
    const marginText = margin ? `安全边际：${margin}；` : "";
    return (
      `已有条件性估值（${baseText}${dayText}），已核验收盘行情在研究覆盖范围内，` +
      `可以合法比较；${marginText}正式买卖仍需通过人工与决策门禁。`
    );
  }
  if (bridge?.status === "QUOTE_VERIFIED_BUT_RESEARCH_STALE") {
    const quoteBits = [
      text(bridge.quoteDate),
      text(bridge.displayPrice) ? `${text(bridge.displayPrice)} 元` : null,
    ].filter((bit): bit is string => bit !== null);
    const quoteText = quoteBits.length ? `（${quoteBits.join("，")}）` : "";
    return (
      `已有条件性估值研究（${baseText}${dayText}），但已核验收盘价${quoteText}晚于研究截止日，` +
      "暂不能形成正式价格判断；需先完成研究重登记与事件复核。"
    );
  }
  if (bridge) {
    return `已有条件性估值研究（${baseText}${dayText}），但${bridge.statusLabel}，暂不能进行正式价格比较。`;
  }
  return `已有条件性估值研究（${baseText}${dayText}），但尚未登记经核验的收盘行情，暂不能进行价格比较。`;
}

export interface NextActionGate {
  label: string;
  status: string | null;
  statusLabel: string;
  nextAction: string | null;
}

/**
 * 下一步怎么做：只汇总发布物里已有的下一步字段——价格桥接的 next_step
 * 和各门禁的 next_action；相同动作合并展示，不新增任何前端建议。
 */
export function nextActionLines(
  gates: NextActionGate[],
  bridgeNextStep?: string | null,
): string[] {
  const lines: string[] = [];
  const bridgeStep = (bridgeNextStep ?? "").trim();
  if (bridgeStep) lines.push(bridgeStep);
  const grouped = new Map<string, string[]>();
  for (const gate of gates) {
    const action = (gate.nextAction ?? "").trim();
    if (!action || gate.status === "PASS" || action === bridgeStep) continue;
    const labels = grouped.get(action) ?? [];
    labels.push(gate.label);
    grouped.set(action, labels);
  }
  for (const [action, labels] of grouped) {
    lines.push(`${action}（${labels.join("、")}）`);
  }
  return lines;
}

/** 去掉 research_case: 作用域前缀并翻译已收录阻塞；未知文本保持原样。 */
export function blockerText(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "未提供";
  const scoped = trimmed.startsWith("research_case:")
    ? trimmed.slice("research_case:".length).trim()
    : trimmed;
  return BLOCKER_TEXT[trimmed] ?? BLOCKER_TEXT[scoped] ?? scoped;
}

/**
 * 同一阻塞常同时以裸码和 research_case: 前缀副本出现；按展示文本去重，
 * 保留首次出现的顺序，不合并不同含义的条目。
 */
export function uniqueBlockerTexts(values: readonly string[]): string[] {
  const seen: string[] = [];
  for (const value of values) {
    const text = blockerText(value);
    if (!seen.includes(text)) seen.push(text);
  }
  return seen;
}

/**
 * support/counter_evidence/next_events 既可能是 {kind,text,evidence_refs}
 * 也可能是旧载荷里的字符串；只提取确实存在的文本，不拼装内容。
 */
export function normalizeEvidenceLines(value: unknown): EvidenceLine[] {
  if (value === null || value === undefined) return [];
  if (typeof value === "string") {
    const text = value.trim();
    return text ? [{ text, evidenceRefs: [] }] : [];
  }
  if (Array.isArray(value)) return value.flatMap(normalizeEvidenceLines);
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const text = typeof record.text === "string" ? record.text.trim() : "";
    if (!text) return [];
    const evidenceRefs = Array.isArray(record.evidence_refs)
      ? record.evidence_refs.filter(
          (ref): ref is string => typeof ref === "string",
        )
      : [];
    return [{ text, evidenceRefs }];
  }
  return [];
}

/** 底稿阅读顺序只展开前 limit 条，其余留给折叠技术区。 */
export function splitReadingOrder(
  rows?: ResearchReadingRow[] | null,
  limit = 8,
): { leading: ResearchReadingRow[]; trailing: ResearchReadingRow[] } {
  const safeLimit = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 8;
  const all = (Array.isArray(rows) ? rows : []).filter(
    (row): row is ResearchReadingRow =>
      Boolean(row) &&
      typeof row === "object" &&
      typeof row.label === "string" &&
      typeof row.value === "string",
  );
  return { leading: all.slice(0, safeLimit), trailing: all.slice(safeLimit) };
}

/** 技术详情区的未知字段安全转文本，null 明确显示未提供。 */
export function unknownText(value: unknown): string {
  if (value === null || value === undefined) return "未提供";
  if (typeof value === "string") return value.trim() ? value : "未提供";
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "未提供";
  }
}
