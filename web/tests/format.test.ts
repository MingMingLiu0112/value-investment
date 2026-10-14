import { describe, expect, it } from "vitest";
import {
  formatDecimal,
  formatMoney,
  formatUnitPrice,
} from "../src/utils/format";

describe("money presentation", () => {
  it("rounds relative strength, market changes and ratios only for presentation", () => {
    const source = "3.505814812256627960463050843";
    expect(formatDecimal(source)).toBe("3.51");
    expect(formatDecimal("-1.810183760989091417929155417")).toBe("-1.81");
    expect(formatDecimal("0.6320420394038465979969764911")).toBe("0.63");
    expect(formatDecimal(null)).toBe("—");
    expect(source).toBe("3.505814812256627960463050843");
  });
  it("trims backend decimal strings to two places with separators", () => {
    expect(formatMoney("500000.00")).toBe("500,000.00");
    expect(formatMoney("199995.00")).toBe("199,995.00");
    expect(formatMoney("-1234.5")).toBe("-1,234.50");
  });

  it("keeps fee-diluted per-share cost readable instead of raw Decimal", () => {
    expect(formatUnitPrice("1500.00416666666666666666667")).toBe("1,500.0042");
    expect(formatUnitPrice("1500.00")).toBe("1,500.00");
  });

  it("does not invent values for absent or unparsable input", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("未提供")).toBe("未提供");
  });
});
