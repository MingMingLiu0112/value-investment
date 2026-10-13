import type { DailyPublicPacket } from "../types/api";
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
