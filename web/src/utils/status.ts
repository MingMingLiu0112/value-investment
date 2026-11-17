import type { DailyResponse } from "../types/api";

export function dailyStatus(data: DailyResponse) {
  return {
    formalCount: data.summary.formal_count,
    watchCount: data.summary.watch_count,
    noFormalCandidate: data.summary.formal_count === 0,
  };
}
