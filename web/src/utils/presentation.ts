const labels: Record<string, string> = {
  BUY_CANDIDATE: "建仓复核候选",
  ADD_CANDIDATE: "加仓复核候选",
  HOLD: "持有复核",
  TRIM_CANDIDATE: "减仓复核候选",
  SELL_CANDIDATE: "退出复核候选",
  NO_ACTION: "无正式动作",
  HOT_WATCH: "热点观察",
  SETUP_FORMING: "形态形成中",
  ENTRY_REVIEW_CANDIDATE: "入场复核候选",
  EXIT_REVIEW_CANDIDATE: "退出复核候选",
  INVALIDATED: "判断失效",
  WATCH: "研究观察",
  PENDING_REVIEW: "待复核",
  PENDING_CONFIRMATION: "待确认",
  RESEARCH_REFERENCE: "研究参考",
  FORMALLY_ADMITTED_REVIEW: "正式准入复核",
  NOT_CONNECTED: "私人组合未接入",
};
export function statusLabel(value?: string): string {
  if (!value) return "未提供";
  return labels[value] ? `${labels[value]} · ${value}` : value;
}
