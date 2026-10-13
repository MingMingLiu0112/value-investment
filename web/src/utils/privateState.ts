import { ApiError } from "../services/api";
import type { PortfolioResponse, RiskResponse } from "../types/api";

/**
 * TL9 MVP-3：把“私人组合是否可用于今日判断”收敛成一个状态，供每日页
 * 的所有私人区块共用，避免同一页面同时出现 LOCKED 与 NOT_CONNECTED。
 *
 * - LOCKED：本机工作台尚未解锁，任何私人数据都没有被读取；
 * - NOT_CONNECTED：已解锁但没有真实私人台账（不代表组合为空）；
 * - BLOCKED_PRIVATE_INPUT：有真实持仓，但 IPS/风险输入不完整；
 * - CONNECTED：真实台账可用；是否给出仓位建议仍由风险引擎决定；
 * - UNAVAILABLE：读取失败（目录损坏、校验失败等），fail-closed。
 */
export type PrivateStateKind =
  | "LOADING"
  | "LOCKED"
  | "NOT_CONNECTED"
  | "BLOCKED_PRIVATE_INPUT"
  | "CONNECTED"
  | "UNAVAILABLE";

export interface PrivateStateView {
  kind: PrivateStateKind;
  label: string;
  detail: string;
  nextStep?: string;
  blockers: string[];
}

const PRICE_CODES = new Set(["PRICE_NOT_ADMITTED"]);

export function privateStateFrom(input: {
  portfolio?: PortfolioResponse;
  risk?: RiskResponse;
  error?: unknown;
  loading?: boolean;
}): PrivateStateView {
  const { portfolio, risk, error, loading } = input;
  if (error instanceof ApiError && error.status === 401) {
    return {
      kind: "LOCKED",
      label: "已锁定（尚未解锁）",
      detail:
        "工作台处于锁定状态，系统没有读取任何私人数据；这既不是“未接入”，也不代表组合为空。",
      nextStep:
        "通过本机启动脚本打开一次性解锁链接（run_daily_workbench.ps1 或 start_web_workbench.ps1），解锁后再复核。",
      blockers: [],
    };
  }
  if (error) {
    return {
      kind: "UNAVAILABLE",
      label: "读取失败",
      detail: error instanceof Error ? error.message : "私人状态读取失败。",
      nextStep:
        "确认私人数据目录与授权状态后重试；失败期间不会给出任何仓位数字。",
      blockers: [],
    };
  }
  if (!portfolio || loading) {
    return {
      kind: "LOADING",
      label: "读取中",
      detail: "正在读取私人台账…",
      blockers: [],
    };
  }
  if (portfolio.status === "NOT_CONNECTED") {
    return {
      kind: "NOT_CONNECTED",
      label: "尚未接入",
      detail:
        "没有已确认的真实私人台账；这不代表你的组合为空，也不会生成任何买卖或仓位数字。",
      nextStep:
        "按 M4 流程初始化私人组合并确认真实成交后，再运行双策略风险复核。",
      blockers: portfolio.blockers.filter((code) => !PRICE_CODES.has(code)),
    };
  }
  if (portfolio.status === "CONNECTED") {
    const blockers = [
      ...(risk?.blockers ?? []),
      ...(risk?.engine?.blockers ?? []),
    ].filter(
      (code, index, all) =>
        all.indexOf(code) === index && !PRICE_CODES.has(code),
    );
    if (risk?.status === "BLOCKED_PRIVATE_INPUT") {
      return {
        kind: "BLOCKED_PRIVATE_INPUT",
        label: "已接入，风险输入不完整",
        detail:
          "真实台账已读取；双策略风险引擎列出以下缺失输入，补齐并确认后才会给出仓位建议。",
        nextStep: "补齐下列输入并在组合页确认，然后重新运行双策略风险复核。",
        blockers,
      };
    }
    return {
      kind: "CONNECTED",
      label: "已接入",
      detail: "私人台账已读取；行情与风险约束由各自门禁单独判定。",
      blockers,
    };
  }
  return {
    kind: "UNAVAILABLE",
    label: "不可用",
    detail: "私人台账返回了未识别的状态，按失败关闭处理。",
    nextStep: "检查私人数据目录后重试。",
    blockers: [],
  };
}
