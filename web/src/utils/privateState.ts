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
 * - UNAVAILABLE：读取失败（目录不可用、流水校验失败、其他读错误），fail-closed。
 *   台账损坏与目录不可用即使落在 NOT_CONNECTED 响应里，也按 UNAVAILABLE 如实报出，
 *   不再显示成“尚未接入”。
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
  /** 本次读取前该页面是否已持有解锁会话（用于区分从未解锁与会话失效）。 */
  hadSession?: boolean;
}): PrivateStateView {
  const { portfolio, risk, error, loading, hadSession } = input;
  if (error instanceof ApiError && error.status === 401) {
    if (hadSession) {
      return {
        kind: "LOCKED",
        label: "解锁会话已过期",
        detail:
          "本次读取被拒绝：本机工作台的解锁会话已失效（例如服务重启），系统没有读取任何私人数据。",
        nextStep:
          "请重新运行本机启动脚本（run_daily_workbench.ps1 或 start_web_workbench.ps1）打开一次性解锁链接，然后重试。",
        blockers: [],
      };
    }
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
    const blockers = portfolio.blockers.filter(
      (code) => !PRICE_CODES.has(code),
    );
    if (blockers.includes("PRIVATE_JOURNAL_INVALID")) {
      return {
        kind: "UNAVAILABLE",
        label: "私人台账校验失败（已停止投影）",
        detail:
          "私人流水校验未通过，系统已停止投影持仓与现金；当前不会显示任何台账或仓位数字。这不代表你的组合为空。",
        nextStep:
          "检查私人数据目录中的流水文件，修复后重新运行每日工作台并重试。",
        blockers,
      };
    }
    if (blockers.includes("PRIVATE_ROOT_UNAVAILABLE")) {
      return {
        kind: "UNAVAILABLE",
        label: "私人数据目录不可用",
        detail:
          "私人数据目录当前不可读（未配置或不可访问），系统没有读取到任何台账内容；这不代表你的组合为空。",
        nextStep:
          "确认私人数据目录已配置且可访问，然后重新运行每日工作台并重试。",
        blockers,
      };
    }
    return {
      kind: "NOT_CONNECTED",
      label: "尚未接入",
      detail:
        "没有已确认的真实私人台账；这不代表你的组合为空，也不会生成任何买卖或仓位数字。",
      nextStep:
        "按 M4 流程初始化私人组合并确认真实成交后，再运行双策略风险复核。",
      blockers,
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
