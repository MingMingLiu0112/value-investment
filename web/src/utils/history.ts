import type { ResearchComparison } from "../types/api";

/** SHA-256 只展示前 12 位，足够人工比对，避免整页长字符串。 */
export function shortDigest(sha256?: string | null): string | null {
  if (!sha256) return null;
  return sha256.length > 12 ? sha256.slice(0, 12) : sha256;
}

/** 只描述机械对比结果，不对判断强弱下结论。 */
export function comparisonSummary(comparison: ResearchComparison): string {
  if (comparison.status === "PREVIOUS_UNAVAILABLE") {
    return "只有一个可复算版本，暂无法比较";
  }
  if (comparison.status !== "COMPARED") {
    return "未执行比较（status=" + comparison.status + "）";
  }
  if (comparison.observation === "UNCHANGED") {
    return "已比较：未发现字段变化";
  }
  if (comparison.observation === "EVIDENCE_UPDATED") {
    const count = comparison.changed_fields?.length ?? 0;
    return "已比较：发现 " + count + " 个字段变化";
  }
  return "已比较：观察结论 " + (comparison.observation ?? "UNKNOWN");
}
