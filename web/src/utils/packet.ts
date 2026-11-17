import type {
  DailyPublicPacket,
  DailyPublicSnapshot,
  ExcelLiveCheck,
  PacketDates,
} from "../types/api";
import { codeText, engineAlertText } from "./codes";

/**
 * TL9 MVP-1：每日公开数据包的展示工具。
 * 只翻译已发布字段，不推算任何投资结论；未收录的代码原样展示。
 */

/** 形如 CODE 或 CODE:标的 的机器代码转中文；未收录时原样返回。 */
export function blockerText(value: string): string {
  const engineAlert = engineAlertText(value);
  if (engineAlert !== value) return engineAlert;
  const [head, ...rest] = value.split(":");
  const base = codeText(head) ?? head;
  return rest.length ? `${base}（${rest.join(":")}）` : base;
}

export interface PacketDateRow {
  label: string;
  value: string;
}

export function packetDateRows(packet: DailyPublicPacket): PacketDateRow[] {
  const dates = packet.dates;
  return [
    { label: "研究截止日", value: dates.research_as_of ?? "未提供" },
    { label: "已登记行情日", value: dates.quote_trade_date ?? "未提供" },
    {
      label: "最近已完成交易日",
      value: dates.latest_completed_trade_session ?? "未提供",
    },
    { label: "决策发布日", value: dates.decision_published_on ?? "未提供" },
    {
      label: "Excel 快照时点",
      value: dates.excel_published_as_of ?? "未提供",
    },
  ];
}

export type FreshnessLevel = "ok" | "warning" | "unknown";

const FRESHNESS_OK = new Set(["FRESH", "COVERS", "SNAPSHOT", "CURRENT"]);
const FRESHNESS_WARNING = new Set(["STALE"]);

export function freshnessLevel(status?: string | null): FreshnessLevel {
  if (!status) return "unknown";
  if (FRESHNESS_OK.has(status)) return "ok";
  if (FRESHNESS_WARNING.has(status)) return "warning";
  return "unknown";
}

/** TL10-RC：快照指针原因码 → 中文；未收录时原样展示，绝不猜测含义。 */
const SNAPSHOT_REASONS: Record<string, string> = {
  SNAPSHOT_POINTER_MISSING: "尚未发布过任何已验证快照",
  SNAPSHOT_POINTER_UNREADABLE: "快照指针文件无法读取",
  SNAPSHOT_POINTER_INVALID: "快照指针结构或状态不合法",
  SNAPSHOT_ARTIFACT_MISSING: "快照文件缺失",
  SNAPSHOT_ARTIFACT_UNREADABLE: "快照文件无法读取",
  SNAPSHOT_ARTIFACT_HASH_MISMATCH: "快照文件哈希与发布记录不一致（已停止使用）",
  SNAPSHOT_ARTIFACT_CONTRACT_INVALID: "快照文件不符合只读决策契约",
  SNAPSHOT_CONTENT_DIGEST_MISMATCH: "快照内容摘要与发布记录不一致",
  SNAPSHOT_IDENTITY_MISMATCH: "快照标识与发布记录不一致",
  SNAPSHOT_CONTENT_TAMPERED: "快照内容校验未通过（已停止使用）",
};

export function snapshotReasonText(reason?: string | null): string {
  if (!reason) return "原因未提供";
  return SNAPSHOT_REASONS[reason] ?? reason;
}

/** 快照校验状态：只有 VERIFIED 才说“已校验哈希”，其余按原因如实说明。 */
export function snapshotIntegrityText(
  snapshot?: Pick<DailyPublicSnapshot, "status" | "reason"> | null,
): string {
  if (!snapshot) return "快照状态尚未读取";
  if (snapshot.status === "VERIFIED") return "已校验哈希（SHA-256 复核通过）";
  const reason = snapshotReasonText(snapshot.reason);
  if (snapshot.status === "INVALID") return `快照校验失败：${reason}`;
  if (snapshot.status === "UNAVAILABLE") return `尚无已验证快照：${reason}`;
  return `快照状态未知：${snapshot.status}`;
}

/** 快照覆盖的数据截止（行情 / 研究 / Excel 快照），缺失时如实标注。 */
export function snapshotCutoffLine(
  dates?: Pick<
    PacketDates,
    "quote_trade_date" | "research_as_of" | "excel_published_as_of"
  > | null,
): string {
  if (!dates) return "未提供";
  return (
    `行情 ${dates.quote_trade_date ?? "未提供"}` +
    ` · 研究截止 ${dates.research_as_of ?? "未提供"}` +
    ` · Excel 快照 ${dates.excel_published_as_of ?? "未提供"}`
  );
}

/** Excel 对照状态 → 中文；绝不把未知状态说成“一致”。 */
export function excelComparisonText(
  excel?: Pick<ExcelLiveCheck, "status"> | null,
): string {
  const status = excel?.status;
  if (!status) return "未执行只读校验";
  switch (status) {
    case "MATCHED":
      return "与正式 Excel 一致";
    case "DIFFERENT":
      return "与正式 Excel 不一致（转人工处理，不自动同步）";
    case "NOT_VERIFIED":
      return "未校验（缺少可核对的哈希或文件）";
    case "NOT_RESOLVED":
      return "未解析到正式 Excel 路径";
    default:
      return `对照状态未知：${status}`;
  }
}

function dateOnly(value?: string | null): string | null {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  return match ? match[1] : null;
}

/** 指针记录与快照记录的 Excel 时点谁更新；任一侧缺失时不作判断。 */
export function excelNewerSideText(
  excel?: Pick<ExcelLiveCheck, "pointer_published_as_of"> | null,
  dates?: Pick<PacketDates, "excel_published_as_of"> | null,
): string | null {
  const pointer = dateOnly(excel?.pointer_published_as_of);
  const recorded = dateOnly(dates?.excel_published_as_of);
  if (!pointer || !recorded) return null;
  if (pointer === recorded) return `两侧记录同一 Excel 快照时点（${recorded}）`;
  if (pointer > recorded) {
    return `正式工作簿指针 ${pointer} 新于快照记录的 Excel 时点 ${recorded}；以人工核对为准`;
  }
  return `快照记录的 Excel 时点 ${recorded} 新于正式工作簿指针 ${pointer}；以人工核对为准`;
}
