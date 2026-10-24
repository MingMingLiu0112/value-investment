import { describe, expect, it } from "vitest";
import { dailyStatus } from "../src/utils/status";
import type { DailyResponse } from "../src/types/api";

describe("daily status semantics", () => {
  it("keeps zero formal candidates when research observations exist", () => {
    const response: DailyResponse = {
      action: "no_order",
      status: "BLOCKED",
      market: { status: "WATCH" },
      summary: { universe_count: 20, formal_count: 0, watch_count: 2 },
      sections: {
        holdings: [],
        value: [{ id: "watch-1", status: "WATCH" }],
        hotspot: [],
      },
      blockers: ["审批未完成"],
    };
    expect(dailyStatus(response)).toEqual({
      formalCount: 0,
      watchCount: 2,
      noFormalCandidate: true,
    });
    expect(response.sections.value[0].status).toBe("WATCH");
  });
});
