import type { DecisionItem } from "../types/api";
import { codeText } from "./codes";

export function firstResearchText(value: unknown): string | null {
  if (typeof value === "string") return value.trim() || null;
  if (Array.isArray(value)) {
    for (const entry of value) {
      const text = firstResearchText(entry);
      if (text) return text;
    }
  }
  if (value && typeof value === "object" && "text" in value) {
    return firstResearchText((value as { text: unknown }).text);
  }
  return null;
}

/** Presentation grouping uses retained scenario data, never a security allowlist. */
export function hasValuationResult(item: DecisionItem): boolean {
  const candidates = [
    item.research?.valuation,
    item.price_action_plan?.conditional_valuation_range,
    item.price_action_plan,
  ];
  return candidates.some(
    (value) =>
      value &&
      ["bear", "base", "bull"].every((key) => {
        const raw = (value as Record<string, unknown>)[key];
        return (
          ((typeof raw === "string" && raw.trim() !== "") ||
            typeof raw === "number") &&
          Number.isFinite(Number(raw)) &&
          Number(raw) > 0
        );
      }),
  );
}

export function publicBlockerText(value?: string): string | null {
  if (!value) return null;
  return codeText(value) ?? (/\p{Script=Han}/u.test(value) ? value : null);
}

/** Count only backend-declared admission; presentation never upgrades research. */
export function strategyCounts(items: DecisionItem[]) {
  let formal = 0;
  let pending = 0;
  let watch = 0;
  for (const item of items) {
    if (item.status === "FORMALLY_ADMITTED_REVIEW") formal += 1;
    else if (
      item.status === "TRIGGER_PENDING" ||
      item.status === "PENDING_CONFIRMATION"
    )
      pending += 1;
    else watch += 1;
  }
  return { formal, pending, watch };
}
