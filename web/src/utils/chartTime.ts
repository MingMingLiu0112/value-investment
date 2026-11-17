import { TickMarkType, type Time, type UTCTimestamp } from "lightweight-charts";

const SHANGHAI = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function chartTime(
  value: string,
  period: "daily" | "60m" | "15m",
): string | UTCTimestamp {
  if (period === "daily") return value;
  return (Date.parse(value.replace(" ", "T") + "+08:00") /
    1000) as UTCTimestamp;
}

function shanghaiParts(time: Time): Record<string, string> {
  const date =
    typeof time === "number"
      ? new Date(time * 1000)
      : typeof time === "string"
        ? new Date(`${time}T00:00:00+08:00`)
        : new Date(Date.UTC(time.year, time.month - 1, time.day));
  return Object.fromEntries(
    SHANGHAI.formatToParts(date).map((part) => [part.type, part.value]),
  );
}

export function formatShanghaiChartTime(time: Time): string {
  const parts = shanghaiParts(time);
  const date = `${parts.year}-${parts.month}-${parts.day}`;
  return typeof time === "number"
    ? `${date} ${parts.hour}:${parts.minute}`
    : date;
}

export function formatShanghaiTick(time: Time, type: TickMarkType): string {
  const parts = shanghaiParts(time);
  if (type === TickMarkType.Year) return parts.year;
  if (type === TickMarkType.Month) return `${parts.month}月`;
  if (type === TickMarkType.DayOfMonth) return `${parts.month}-${parts.day}`;
  return `${parts.hour}:${parts.minute}`;
}
