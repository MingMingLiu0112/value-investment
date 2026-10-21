import type { PortfolioReconciliation } from "../types/api";

/**
 * 机器代码到中文短句的统一翻译。
 * 未收录的代码一律返回 null，由调用方决定如何原样展示，绝不猜测含义。
 */
const CODE_TEXT: Record<string, string> = {
  PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED:
    "尚未确认本账户这笔买入的原始投资逻辑",
  AUTHENTICATED_PERSONAL_ENTRY_SUBJECT_REQUIRED: "需要有效的本机本人确认会话",
  OWNED_ENTRY_DEPENDENCIES_REQUIRED:
    "原始投资逻辑与剩余持仓的归属依据尚未完整核验",
  OWNED_CURRENT_ADD_ADVISORY_REQUIRED: "当前研究尚未支持与原逻辑一致的加仓复核",
  CURRENT_STRATEGY_PLAN_UNAVAILABLE: "这笔持仓尚无当前有效的策略计划",
  EXTERNAL_ACCOUNT_RECONCILIATION_MISSING:
    "尚未完成与真实账户或券商对账单的核对",
  HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY:
    "事后补录仅供复盘，不能替代当时可得的投资证据",
  SELL_QUANTITY_MUST_BE_INTEGER_WITHIN_SELLABLE:
    "复核卖出数量超过当前可卖数量或不符合整数股要求",
  OWNED_ENTRY_DEPENDENCIES_INVALID:
    "原投资逻辑的来源、时点或账本绑定未通过核验",
  HELD_ADVISORY_DEPENDENCY_INVALID: "当前持仓研究或策略复核依据未通过校验",
  CURRENT_PLAN_NOT_FORMALLY_ELIGIBLE: "当前证券计划尚未通过适用的正式准入",
  CURRENT_ENTRY_CONDITION_NOT_OBSERVED: "完整价格入场条件尚未满足",
  CURRENT_VALUE_QUOTE_NOT_VERIFIED: "价值计划使用的当前价格尚未核验",
  ACTUAL_RISK_REVIEW_REQUIRED: "真实账户风险未完成有效核验",
  VERIFIED_TRADING_RULE_REQUIRED: "证券交易单位与交易规则尚未核验",
  CONFIRMED_IPS_REQUIRED: "尚未确认个人投资政策及风险上限",
  POSITIVE_ACTUAL_REVIEW_QUANTITY_REQUIRED: "真实资金风险条件下没有可复核数量",
  TEST_ONLY_PLAN_NOT_FORMAL: "测试计划不能用于真实账户交易判断",
  CURRENT_PLAN_EXPIRED: "当前计划已到期，不能继续使用原价位",
  CURRENT_PLAN_ADD_CONDITION_MISSING: "尚无与原买入逻辑一致的加仓条件",
  CURRENT_ADD_CONDITION_NOT_CONFIRMED:
    "专门的加仓条件尚未满足，不能用新建仓条件自动加仓",
  PERSONAL_ENTRY_THESIS_CONFIRMATION_RECORD_UNSUPPORTED:
    "尚未建立本账户原始买入论点的确认绑定，不能证明加仓与原逻辑一致",
  CURRENT_PLAN_NOT_BUY_OR_ADD: "当前计划不支持新建仓或加仓",
  ADD_REQUIRES_SAME_SLEEVE_HOLDING: "该策略尚无实际持仓，不能标记为加仓",
  CASH_ONLY_NO_QUOTE_REQUIRED: "仅现金账户，无需证券行情估值",
  VERIFIED_LATEST_COMPLETED_CLOSE: "按最近已核验收盘价估值",
  no_order: "仅供研究复核，不构成下单",
  RESEARCH_ONLY: "仅研究观察，尚未通过正式准入",
  PENDING_RESEARCH: "研究待办，尚未进入正式准入",
  RESEARCH_REFERENCE: "研究参考，不是买卖信号",
  FORMALLY_ADMITTED_REVIEW: "已进入正式准入复核",
  UNKNOWN: "准入状态未知",
  WATCH: "研究观察",
  UNVERIFIED_PROVIDER_TRADE_DATE: "行情供应商的交易日期尚未独立核实",
  NO_FORMAL_ADMISSION: "目前没有通过全部正式审核条件的买卖候选",
  PUBLICATION_CHAIN_UNAVAILABLE: "发布链不可用（哈希或结构校验未通过）",
  NEEDS_RE_RESEARCH: "需要重新研究以覆盖最新已核验收盘",
  MODEL_VALIDITY_UNKNOWN: "模型有效性未确立",
  VALUE_EXPLANATION_BINDING_UNAVAILABLE: "研究解释绑定不可用",
  REGISTERED_EVIDENCE_CHANGED:
    "登记证据哈希变化：该公司研究结果降级为不可核验，需重新登记证据",
  REGISTERED_RESEARCH_GAP: "注册研究缺项",
  EVENT_MATERIALITY_REVIEW: "事件材料性复核未完成",
  AWAITING_VERIFIED_CLOSE: "等待双源核验收盘行情登记",
  PRIVATE_PORTFOLIO_NOT_CONNECTED: "私人组合尚未接入，无法核对持仓",
  PUBLICATION_UNAVAILABLE: "当前发布物不可用",
  PRICE_NOT_ADMITTED: "当前价格尚未获准用于正式决策",
  ACCOUNT_AS_OF_IN_FUTURE: "账户事实日期晚于当前日期，不能作为当前权益",
  ACCOUNT_FACTS_NOT_YET_AVAILABLE:
    "账户事实确认时间尚未到达，当前权益暂不可核验",
  RESEARCH_ASSESSMENT_NOT_BOUND:
    "当前发布尚未绑定完整研究评估，补行情不足以完成准入",
  VALUATION_NOT_ADMITTED: "估值尚未通过准入",
  SCENARIO_CONFIRMED_IPS_REQUIRED: "情景试算需要先确认本人投资政策",
  SCENARIO_HOLDING_RISK_MISSING: "请明确填写该持仓在资金池内的假设已占用风险",
  SCENARIO_SECURITY_RISK_MISSING: "请明确选择该证券缺少的经济风险假设",
  "portfolio.private_input_missing":
    "尚未提供私人组合输入（IPS、持仓、现金与风险约束）",
  DUAL_SLEEVE_STATUS_UNAVAILABLE: "双策略状态不可用",
  DUAL_SLEEVE_SURFACE_INVALID: "双策略报告未通过校验，已停止展示",
  PRIVATE_ROOT_UNAVAILABLE: "私人数据目录不可用",
  PRIVATE_JOURNAL_INVALID: "私人流水校验失败，已停止投影持仓",
  investable_assets_cny: "可投资资产",
  minimum_cash_cny: "现金底线",
  time_horizon_years: "投资期限",
  concentration_allowed: "是否允许集中",
  risk_tolerance: "风险承受度",
  reconciliation: "尚未执行对账",
  holding_market_value: "正式风险计算缺少已准入的持仓市值",
  DISPLAY_ONLY_HELD_MARK_NOT_FORMAL_PRICE_INPUT:
    "核验收盘可展示市值，尚不能作为正式仓位准入价格",
  max_single_security_pct: "单票上限",
  max_single_industry_pct: "行业上限",
  human_confirmation: "人工确认",
  account_scope: "账户口径",
  holding_quantity_confirmation: "持仓股数的人工确认",
  "security_attributes.missing": "证券风险属性",
  "sleeve_policy.private_input_missing": "双资金池预算",
  cash_reserve: "现金储备",
  "holding.cost_basis_missing": "持仓成本口径",
  "portfolio.nonpositive_equity": "组合净值非正",
  "hotspot.user_risk_policy_missing": "热点仓风险政策",
  actual_namespace: "尚未声明为真实账户口径",
  cash_cny: "尚未提供可用现金",
  LOCKED: "工作台已锁定（尚未解锁）",
  AUTHORIZED: "已解锁",
  SIGNED_OUT: "已退出解锁会话",
  LOCAL_AUTHORIZATION_REQUIRED: "本机工作台尚未解锁，私人数据未被读取",
  AUTHORIZATION_REQUIRED: "本机工作台尚未解锁，私人数据未被读取",
  LOCAL_SESSION_LOCKED: "本机会话已锁定",
  UNLOCK_REJECTED: "解锁链接无效或已过期",
  NOT_CONNECTED: "尚未接入真实私人组合",
  CONNECTED: "已接入真实私人组合",
  BLOCKED_PRIVATE_INPUT: "私人风险输入不完整",
  VALIDATION_FAILED: "输入校验失败",
  UNAVAILABLE: "不可用",
  INVALID: "私人流水校验失败",
  REGISTRY_UNAVAILABLE: "行情登记文件不可读（登记状态未知）",
  QUOTE_REGISTRY_UNAVAILABLE: "行情登记文件不可读，登记状态未知",
  NO_REGISTERED_QUOTES: "尚未登记任何公司行情",
};

/** 已收录则返回中文短句，未收录返回 null。 */
export function codeText(value?: string | null): string | null {
  if (!value) return null;
  return CODE_TEXT[value] ?? null;
}

/** 已收录则返回中文短句，否则原样返回代码；空值返回未提供。 */
export function describeCode(value?: string | null): string {
  if (!value) return "未提供";
  return CODE_TEXT[value] ?? value;
}

export function strategyText(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "value") return "价值投资";
  if (value === "hotspot") return "热点追踪";
  return value;
}

export function reconciliationText(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "RECONCILED") return "已完成对账";
  if (value === "PENDING_RECONCILIATION") return "尚未执行对账";
  return value;
}

const RECONCILIATION_REASON: Record<string, string> = {
  SUPERSEDED_BY_NEWER_FILL:
    "新的已确认成交晚于上次对账，旧快照不再代表当前持仓",
  NO_RECONCILIATION_CONFIRMED: "尚未确认过对账快照",
};

const RECONCILIATION_SCOPE: Record<string, string> = {
  INTERNAL_JOURNAL_REPLAY: "系统内部流水重算（不等于券商对账）",
  EXTERNAL_ACCOUNT_STATEMENT: "外部账户对账凭证",
};

export interface ReconciliationView {
  statusText: string;
  scopeText: string;
  reasonText: string | null;
  reconciledAt: string | null;
}

/**
 * 对账块是可选字段：没有时返回 null，由调用方决定是否展示。
 * 未收录的范围或原因代码原样返回，不猜测含义。
 */
export function reconciliationView(
  value?: PortfolioReconciliation | null,
): ReconciliationView | null {
  if (!value) return null;
  const scope = value.scope;
  return {
    statusText: reconciliationText(value.status),
    scopeText: scope
      ? (RECONCILIATION_SCOPE[scope] ?? scope)
      : "未提供对账范围",
    reasonText: value.reason
      ? (RECONCILIATION_REASON[value.reason] ?? value.reason)
      : null,
    reconciledAt: value.reconciled_at ?? null,
  };
}

const ENGINE_ALERT_TAIL: Record<string, string> = {
  budget_exceeded: "超出资金池预算",
  risk_unknown: "尚未提供承诺风险金额，风险敞口未知",
  risk_budget_exhausted: "风险预算已用尽",
  financing_or_risk_tools_not_supported:
    "输入声明允许融资或风险工具，当前引擎不支持",
  cash_floor_violation: "现金储备低于设定的现金底线",
  reserved_cash: "现金低于保留现金需求",
};

const ALERT_SCOPE: Record<string, string> = {
  CORE_VALUE: "价值池",
  HOTSPOT_SATELLITE: "情绪卫星仓",
  shared: "跨资金池",
  aggregate: "组合层面",
};

/** 引擎提示代码（形如 CORE_VALUE:risk_unknown）转中文；未收录原样返回。 */
export function engineAlertText(value: string): string {
  if (value === "SLEEVE_CASH_OVERDRAWN")
    return "资金池可用现金不足：实际成交及费用超过该池现金，请核对资金分配";
  const parts = value.split(":");
  const scope = ALERT_SCOPE[parts[0]] ?? null;
  const prefix = scope ? scope + "：" : "";
  const tail = parts.slice(1).join(":");
  if (tail.startsWith("single_security_concentration:"))
    return prefix + "单票集中度超限（" + tail.split(":")[1] + "）";
  if (tail.startsWith("liquidity_review:"))
    return prefix + "持仓流动性需人工复核（" + tail.split(":")[1] + "）";
  if (tail.startsWith("industry_concentration:"))
    return prefix + "行业集中度超限（" + tail.split(":")[1] + "）";
  if (tail.startsWith("factor_concentration:"))
    return prefix + "因子集中度超限（" + tail.split(":")[1] + "）";
  if (tail.startsWith("single_security_cap:"))
    return prefix + "单票上限（" + tail.split(":")[1] + "）";
  if (tail.startsWith("industry_cap:"))
    return prefix + "行业上限（" + tail.split(":")[1] + "）";
  const mapped = ENGINE_ALERT_TAIL[tail];
  if (mapped) return prefix + mapped;
  return value;
}
