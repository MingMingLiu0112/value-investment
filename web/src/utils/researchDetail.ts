import type { ResearchGateRow, ResearchReadingRow } from "../types/api";

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
