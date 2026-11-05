import { describe, expect, it } from "vitest";
import type { DailyPublicPacket } from "../src/types/api";
import { systemActionRows } from "../src/utils/system-actions";

describe("system action projection", () => {
  it("uses published actors and labels without promoting research to admission", () => {
    const packet = {
      company_statuses: {
        "600887": {
          name: "伊利股份",
          valuation_status: { user_label: "估值正在复核" },
          pending_actions: [
            { actor: "HUMAN", code: "EVENT", label: "复核公告" },
            { actor: "HUMAN", code: "EVENT_DUP", label: "复核公告" },
            { actor: "EVIDENCE", code: "MODEL", label: "核验模型" },
          ],
        },
      },
      blockers: ["NO_FORMAL_ADMISSION"],
      formal_admission_count: 0,
    } as unknown as DailyPublicPacket;
    expect(systemActionRows(packet)).toEqual([
      {
        symbol: "600887",
        name: "伊利股份",
        valuation: "估值正在复核",
        actions: [
          { actor: "HUMAN", code: "EVENT", label: "复核公告" },
          { actor: "EVIDENCE", code: "MODEL", label: "核验模型" },
        ],
      },
    ]);
    expect(packet.formal_admission_count).toBe(0);
  });
});
