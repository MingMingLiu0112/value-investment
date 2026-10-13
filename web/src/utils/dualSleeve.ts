import type { DailyDualSleeveSurface } from "../types/api";
import { codeText } from "./codes";
import { statusLabel } from "./presentation";
import type { PrivateStateKind } from "./privateState";

/**
 * 双策略状态只做“翻译 + 解释”，不计算任何资金池、持仓或仓位；
 * position_guidance 为空时必须说明真实原因和下一步需要用户提供的输入。
 */
export interface DualSleeveView {
  statusText: string;
  connectedText: string;
  guidanceText: string;
  guidanceMissingReason: string | null;
  nextInputText: string | null;
  eligibilityText: string;
  authorityText: string;
}

const NEXT_INPUT_TEXT: Record<string, string> = {
  PRIVATE_PORTFOLIO_INPUT_REQUIRED:
    "下一步需要你本人提供：投资目标与 IPS、当前持仓、现金与风险约束（私人组合输入），保存后重新运行双策略复核。",
  PRIVATE_INPUT_INCOMPLETE:
    "私人输入不完整：补齐上面列出的缺失项后重新运行双策略复核。",
};

function blockerTexts(blockers: string[]): string[] {
  return blockers.map((code) => codeText(code) ?? code);
}

/**
 * 发布物里的组合接入状态与当前私人台账明显不一致时，返回需要展示的原因；
 * 台账读不到（LOCKED / LOADING / UNAVAILABLE）时不下结论，避免误报。
 */
export function dualSleeveMismatch(
  surface: DailyDualSleeveSurface,
  privateKind: PrivateStateKind,
): string | null {
  const liveConnected =
    privateKind === "CONNECTED" || privateKind === "BLOCKED_PRIVATE_INPUT";
  const publishedConnected = surface.portfolio_connected === true;
  if (publishedConnected && privateKind === "NOT_CONNECTED") {
    return "发布物显示私人组合已接入，但当前读不到真实台账；请检查私人数据目录后重新运行双策略复核。";
  }
  if (!publishedConnected && liveConnected) {
    return "双策略复核发布物尚未包含最新私人组合；请重新运行双策略复核后再参考这里的结论。";
  }
  return null;
}

export function dualSleeveView(
  surface?: DailyDualSleeveSurface | null,
): DualSleeveView | null {
  if (!surface) return null;
  const guidanceAvailable = surface.position_guidance_available === true;
  const blockers = blockerTexts(surface.blockers ?? []);
  let guidanceMissingReason: string | null = null;
  if (!guidanceAvailable) {
    if (surface.status === "NOT_CONNECTED") {
      guidanceMissingReason =
        "尚未接入真实私人组合，系统不会给出任何买多少/卖多少的仓位数字。";
    } else if (surface.status === "BLOCKED_PRIVATE_INPUT") {
      guidanceMissingReason = blockers.length
        ? "私人输入不完整，仓位建议已停止计算：" + blockers.join("；")
        : "私人输入不完整，仓位建议已停止计算。";
    } else if (
      surface.status === "RISK_REVIEW_CALCULATED" ||
      surface.status === "REVIEW_REQUIRED"
    ) {
      guidanceMissingReason =
        "风险复核已计算，但当前版本仍不产出个性化仓位建议；任何仓位仍需人工决策。";
    } else {
      guidanceMissingReason = "当前状态不可用于生成仓位建议。";
    }
  }
  return {
    statusText: statusLabel(surface.status),
    connectedText: surface.portfolio_connected ? "已接入" : "未接入",
    guidanceText: guidanceAvailable ? "已生成（详见双策略复核）" : "尚未生成",
    guidanceMissingReason,
    nextInputText: surface.next_user_input
      ? (NEXT_INPUT_TEXT[surface.next_user_input] ?? surface.next_user_input)
      : null,
    eligibilityText: surface.trade_eligible
      ? "引擎标记为可交易（仍需人工决策）"
      : "未开启交易资格",
    authorityText:
      !surface.acceptance_authority || surface.acceptance_authority === "NONE"
        ? "无自动决策权限，全部人工确认"
        : surface.acceptance_authority,
  };
}
