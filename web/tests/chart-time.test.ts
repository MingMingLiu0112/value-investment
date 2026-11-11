import { expect, it } from "vitest";
import { TickMarkType, type UTCTimestamp } from "lightweight-charts";
import {
  chartTime,
  formatShanghaiChartTime,
  formatShanghaiTick,
} from "../src/utils/chartTime";

it("keeps original UTC timestamp while both crosshair and axis show source Shanghai time", () => {
  const stamp = chartTime("2026-09-22 14:00:00", "60m") as UTCTimestamp;
  expect(stamp).toBe(Date.parse("2026-09-22T06:00:00Z") / 1000);
  expect(formatShanghaiChartTime(stamp)).toBe("2026-09-22 14:00");
  expect(formatShanghaiTick(stamp, TickMarkType.Time)).toBe("14:00");
  expect(formatShanghaiTick(stamp, TickMarkType.DayOfMonth)).toBe("09-22");
});

it("respects Shanghai date rollover and leaves daily business dates unchanged", () => {
  const stamp = (Date.parse("2026-09-22T23:00:00Z") / 1000) as UTCTimestamp;
  expect(formatShanghaiChartTime(stamp)).toBe("2026-09-23 07:00");
  expect(formatShanghaiTick(stamp, TickMarkType.DayOfMonth)).toBe("09-23");
  expect(chartTime("2026-09-22", "daily")).toBe("2026-09-22");
  expect(formatShanghaiChartTime("2026-09-22")).toBe("2026-09-22");
  expect(formatShanghaiChartTime({ year: 2026, month: 9, day: 22 })).toBe(
    "2026-09-22",
  );
  expect(
    formatShanghaiTick({ year: 2026, month: 9, day: 22 }, TickMarkType.Month),
  ).toBe("09月");
});
