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
