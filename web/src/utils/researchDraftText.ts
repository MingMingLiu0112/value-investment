const STATUS_TEXT: Record<string, string> = {
  RESEARCH_DRAFT_NOT_APPROVED: "研究草稿，未获批准",
  DRAFT_NOT_APPROVED: "研究草稿，未获批准",
  INSUFFICIENT_PUBLIC_EVIDENCE: "公开证据不足",
  UNKNOWN: "尚未确立",
  INVALID: "不允许正式价格比较",
  PENDING_HUMAN_REVIEW: "待人工复核",
  INCOMPLETE: "不完整",
  VERIFIED_CLOSE_NOT_ADMITTED: "收盘已核验，价格未准入",
  MODEL_VALIDITY_UNKNOWN: "模型有效性未确立",
  EVENT_MATERIALITY_PENDING_HUMAN_REVIEW: "公告材料性待人工复核",
  EVENT_COVERAGE_INCOMPLETE: "公告检索覆盖不完整",
  STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN: "严格同期规则的信息时点尚未证明",
};

const CHANGE_TEXT: Record<string, string> = {
  research_inputs_migrated_to_source_bound_v2_contract:
    "研究输入已迁移到可追溯的 v2 合约",
  nine_financial_facts_now_have_physical_page_anchors:
    "九项财务事实已绑定到原始财报页码",
  all_nine_scenario_assumptions_now_bind_to_the_hash_bound_memo:
    "九项情景假设已绑定到带哈希的假设备忘录",
  four_announcements_covered_including_2026_10_17_buyback_progress:
    "已覆盖四项公告，包括 2026-10-17 回购进展",
  event_coverage_is_honestly_incomplete: "事件覆盖仍不完整，未将缺口视为通过",
  evidence_stop_resolution_is_now_append_only_and_reusable_for_normal_research:
    "证据缺口处理已追加留存并可复用于常规研究",
  bear_base_bull_values_unchanged: "Bear / Base / Bull 数值未变化",
  human_research_approval_absent: "尚无正式人工研究批准",
  formal_G3_absent: "G3 正式研究门尚未通过",
  event_materiality_pending_human_review: "公告材料性仍待人工复核",
  strict_contemporaneous_pit_not_proven: "严格同期规则的信息时点尚未证明",
  price_admitted_false: "价格尚未准入",
  position_guidance_null: "未生成仓位指引",
  action_no_order: "不构成下单指令",
};

const EXACT_SENTENCE_TEXT: Record<string, string> = {
  "conditional residual income with an algebraic dividend-path cross-check; not evidence of issuer distributable cash or dividend sustainability":
    "条件性剩余收益估值，并以股利路径作代数交叉核对；不证明发行人可分配现金或分红可持续性",
  "Candidate 9% equity hurdle applied to all scenarios.":
    "所有情景统一采用 9% 的候选权益门槛。",
  "No issuer-specific beta estimate is admitted; a common hurdle keeps the draft internally consistent.":
    "尚无经准入的公司特定贝塔估计；统一门槛仅用于保持草案内部一致。",
  "Candidate five-year ROE path anchored on audited FY2025 and unaudited H1 2026.":
    "五年 ROE 路径以经审计的 2025 年年报和未经审计的 2026 年中报为锚。",
  "The path allows margin and competitive pressure while preserving a quality-compounder base case.":
    "该路径计入利润率与竞争压力，同时保留质量复利公司的基准情景。",
  "Terminal ROE remains above or near the equity hurdle by scenario without assuming permanent high excess returns.":
    "各情景的终端 ROE 仍高于或接近权益门槛，但不假设永久高超额收益。",
  "Growth is capped below the 9% equity hurdle in every scenario.":
    "所有情景的增长均低于 9% 权益门槛。",
  "The base case retains more capital to defend operations; the bull case distributes more of higher earnings.":
    "基准情景保留更多资本支持经营，乐观情景分配更多较高盈利。",
  "The bear case retains more capital to defend operations; the bull case distributes more of higher earnings.":
    "保守情景保留更多资本以支持经营，乐观情景分配更多较高盈利。",
  "event scan coverage is incomplete": "公告检索覆盖不完整",
  "EVENT_COVERAGE_INCOMPLETE: the CNINFO snapshot was captured before the research day closed.":
    "公告检索不完整：巨潮快照在研究日结束前获取。",
  "Four 2026-10-14 and 2026-10-17 announcements remain PENDING_HUMAN_REVIEW.":
    "2026-10-14 与 2026-10-17 的四项公告仍待人工复核。",
  "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN: CNINFO provided date-level times and retained files were acquired after the research cutoff.":
    "严格同期信息时点尚未证明：巨潮仅提供日期级时间，留存文件在研究截止后才取得。",
};

const CONFIDENCE_TEXT: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

const ASSUMPTION_TEXT: Record<string, string> = {
  cost_of_equity: "股权成本",
  terminal_roe: "终端 ROE",
  terminal_growth: "终端增长",
  retention: "利润留存率",
  payout_ratio: "派息率",
};

function isMachineToken(value: string): boolean {
  return /^[A-Za-z][A-Za-z0-9_.:-]*$/.test(value) && /[_:.]/.test(value);
}

export function researchStatusText(value?: string | null): string {
  if (!value) return "未提供";
  return STATUS_TEXT[value] ?? (isMachineToken(value) ? "状态待复核" : value);
}

export function researchConfidenceText(value?: string | null): string {
  if (!value) return "未提供";
  return CONFIDENCE_TEXT[value.toLowerCase()] ?? value;
}

export function researchAssumptionName(value: string): string {
  const roeYear = /^forecast_roe_(\d{4})$/.exec(value);
  if (roeYear) return `${roeYear[1]} 年预测 ROE`;
  return ASSUMPTION_TEXT[value] ?? "其他估值假设";
}

export function researchChangeText(value: string): string {
  return CHANGE_TEXT[value] ?? researchSentence(value);
}

export function researchGateText(value: string): string {
  return value
    .split("_")
    .join(" ")
    .replace(/^G(\d)\s*/, "G$1 · ");
}

export function researchSentence(value: string): string {
  const exact = EXACT_SENTENCE_TEXT[value];
  if (exact) return exact;
  let translated = value;
  const ordered = Object.entries(STATUS_TEXT).sort(
    ([left], [right]) => right.length - left.length,
  );
  for (const [code, label] of ordered) {
    translated = translated.split(code).join(label);
  }
  return translated
    .split("contemporaneous PIT")
    .join("严格同期信息时点")
    .split("PriceBridge")
    .join("价格桥");
}
