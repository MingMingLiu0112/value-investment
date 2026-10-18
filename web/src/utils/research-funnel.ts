import type { ResearchFunnelStatus } from "../types/api";

const channelLabels: Record<string, string> = {
  quality: "质量",
  value: "估值",
  dividend_cash_return: "现金回报",
  cyclical: "周期",
};

const blockerLabels: Record<string, string> = {
  QUOTE_DATE_UNVERIFIED: "行情交易日尚未通过独立校验",
  QUALITY_ZERO_PASS: "当前快照没有通过质量门禁的证券",
  CAPITAL_RETURN_UNAVAILABLE: "缺少可接受的资本回报 / ROIC 事实",
  HUMAN_REVIEW_PENDING: "人工研究复核尚未完成",
  QUEUE_IS_DATA_CHECK_ONLY: "研究队列入选只表示待补数据，不是买入信号",
};

export function funnelStatusText(
  status: ResearchFunnelStatus["status"],
): string {
  if (status === "VERIFIED") return "审计文件哈希复核通过";
  if (status === "UNAVAILABLE") return "当前没有可用的审计产物";
  return "审计文件校验失败，已停止展示";
}

export function funnelBlockerText(code: string): string {
  return blockerLabels[code] || code;
}

export function funnelChannelLabel(key: string): string {
  return channelLabels[key] || key;
}

export function funnelEvidenceRows(
  funnel: ResearchFunnelStatus,
): Array<{ label: string; value: string }> {
  if (funnel.status !== "VERIFIED" || !funnel.universe || !funnel.evidence) {
    return [];
  }
  const { universe, evidence, queue, quote } = funnel;
  return [
    {
      label: "全市场覆盖",
      value: `${universe.securities} 只证券 · ${universe.industries_mapped} 条行业映射 · ${universe.market_snapshots} 条行情快照`,
    },
    {
      label: "初筛结果",
      value: `${universe.leads} 个 LEAD · 研究队列 ${queue?.entry_count ?? 0} 个 · 待补数据 ${queue?.selected_count ?? 0} 个 · 预算延后 ${queue?.deferred_count ?? 0} 个`,
    },
    {
      label: "财务证据",
      value: `${evidence.financial_symbols} 家公司 · ${evidence.financial_points} 个财务点 · 同期完整 ${evidence.same_period_complete_symbols} 家`,
    },
    {
      label: "质量门禁",
      value: `PASS ${evidence.quality_pass} · 数据缺口 ${evidence.quality_data_gap} · 证据不足 ${evidence.quality_insufficient_evidence}`,
    },
    {
      label: "行情日期",
      value: quote
        ? `${quote.date || "未提供"} · 已验证 ${quote.verified_count} 条 · 未验证 ${quote.unverified_count} 条`
        : "未提供",
    },
    {
      label: "资本回报",
      value: evidence.capital_return_status || "未评估",
    },
  ];
}

export function funnelChannelRows(funnel: ResearchFunnelStatus): Array<{
  key: string;
  channel: string;
  passed: number;
  gap: string;
  reason: string;
}> {
  return funnel.channels.map((row) => ({
    key: row.key,
    channel: funnelChannelLabel(row.key),
    passed: row.pass_count,
    gap: [
      row.data_gap_count ? `缺数据 ${row.data_gap_count}` : "",
      row.insufficient_evidence_count
        ? `缺证据 ${row.insufficient_evidence_count}`
        : "",
      row.rejected_count ? `未达门槛 ${row.rejected_count}` : "",
      row.not_evaluated_count ? `不适用 ${row.not_evaluated_count}` : "",
      row.budget_excluded_count
        ? `展示预算外 ${row.budget_excluded_count}`
        : "",
      row.unsupported_count ? `画像未支持 ${row.unsupported_count}` : "",
    ]
      .filter(Boolean)
      .join(" · "),
    reason: row.top_reason || "未提供原因",
  }));
}
