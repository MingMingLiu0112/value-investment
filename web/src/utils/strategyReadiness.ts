import type {
  DailyEvaluationItem,
  DecisionItem,
  ReadinessStatus,
  StrategyReadiness,
} from "../types/api";
import { formatUnitPrice } from "./format";

export type ReadinessStrategy = "CORE_VALUE" | "HOTSPOT_SATELLITE";

export function readinessStrategy(value?: string): ReadinessStrategy | null {
  if (value === "CORE_VALUE" || value === "value") return "CORE_VALUE";
  if (value === "HOTSPOT_SATELLITE" || value === "hotspot")
    return "HOTSPOT_SATELLITE";
  return null;
}

export const readinessStatusText: Record<ReadinessStatus, string> = {
  READY: "已核验",
  PARTIAL: "部分形成",
  PENDING: "待完成",
  NOT_EVALUATED: "未核验",
};

export function verifiedReadiness(
  value: StrategyReadiness | null | undefined,
  strategy: ReadinessStrategy | null,
): StrategyReadiness | null {
  return value &&
    strategy &&
    value.schema_version === "strategy-readiness-v1" &&
    value.strategy === strategy &&
    value.action === "no_order" &&
    value.authorization_granted === false &&
    Array.isArray(value.steps)
    ? value
    : null;
}

export function readinessSteps(
  value: StrategyReadiness | null,
  strategy: ReadinessStrategy,
): StrategyReadiness["steps"] {
  const hotspot = strategy === "HOTSPOT_SATELLITE";
  const stages = [
    ["screen", "初筛入选"],
    ...(hotspot
      ? [
          ["structure", "价格结构形成"],
          ["validation", "回放与策略验证"],
        ]
      : [
          ["research", "公司研究形成"],
          ["valuation", "情景估值与假设"],
          ["model_validity", "重大事件与模型有效性"],
        ]),
    ["price", "当前报价与计划有效性"],
    ["action_policy", "条件操作计划"],
    ["portfolio", "个人组合容量"],
    ["human_decision", "人工复核"],
  ];
  return stages.map(([key, label]) => {
    const matches = value?.steps.filter((step) => step?.key === key) ?? [];
    const step = matches.length === 1 ? matches[0] : undefined;
    const validStatus =
      step &&
      Object.prototype.hasOwnProperty.call(readinessStatusText, step.status);
    return {
      key,
      label:
        typeof step?.label === "string" && step.label.trim()
          ? step.label
          : label,
      status: validStatus ? step.status : "NOT_EVALUATED",
      reason:
        typeof step?.reason === "string" && step.reason.trim()
          ? step.reason
          : "本阶段未提供可核验说明。",
    };
  });
}

export function readinessGapLabel(category?: string): string {
  const labels: Record<string, string> = {
    NOT_READY: "前置条件未就绪",
    UNDER_REVIEW: "审核进行中",
    MODEL_NOT_RUN: "模型尚未运行",
    DISPLAY_ONLY: "行情仅供展示",
    VALIDATION_GAP: "策略验证存在缺口",
    PRIVATE: "个人组合待核验",
    HUMAN: "人工复核待完成",
    RESEARCH: "研究输入待补齐",
    REVIEW: "研究与操作资格待复核",
    DATA: "当前结构或数据不可用",
    STRATEGY_VALIDATION: "策略验证存在缺口",
  };
  return (category && labels[category]) || "未完成项";
}

export function readinessCurrentStage(
  value: StrategyReadiness | null,
  strategy: ReadinessStrategy,
): string {
  if (!value) return "就绪阶段未核验";
  const first = readinessSteps(value, strategy).find(
    (step) => step.status !== "READY",
  );
  return first
    ? `${first.label} · ${readinessStatusText[first.status]}`
    : "阶段核验完成，仍未授予操作批准";
}

export function readinessDetailUrl(
  item: Pick<DailyEvaluationItem, "symbol" | "strategy">,
  decision?: DecisionItem,
): string {
  const strategy = readinessStrategy(item.strategy);
  const matchingDecision =
    decision?.symbol === item.symbol &&
    readinessStrategy(decision.strategy) === strategy;
  const id = matchingDecision
    ? decision.id
    : `${strategy === "HOTSPOT_SATELLITE" ? "hotspot-" : ""}${item.symbol}`;
  return `/decisions/${encodeURIComponent(id)}${strategy === "HOTSPOT_SATELLITE" ? "?independent_hotspot=true" : ""}`;
}

/** Readiness may navigate to existing pages, never an external or executable URL. */
export function readinessActionUrl(value?: string | null): string | null {
  if (!value || /[\\\s\u0000-\u001f]/.test(value)) return null;
  try {
    const base = "https://workbench.invalid";
    const parsed = new URL(value, base);
    if (!value.startsWith("/") || parsed.origin !== base) return null;
    if (
      !/^\/(?:daily|portfolio|history|alerts|system)\/?$/.test(
        parsed.pathname,
      ) &&
      !/^\/decisions\/[^/]+$/.test(parsed.pathname)
    )
      return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

export function readinessNumber(value: unknown): string {
  if (
    (typeof value !== "number" && typeof value !== "string") ||
    (typeof value === "string" && !value.trim()) ||
    !Number.isFinite(Number(value))
  )
    return "未提供";
  return formatUnitPrice(value);
}
