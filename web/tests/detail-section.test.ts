import { describe, expect, it } from "vitest";
import { leaves } from "../src/components/DetailSection";

describe("detail section flattening", () => {
  it("keeps explicitly unavailable fields visible instead of hiding them", () => {
    const lines = leaves({
      current_price: null,
      margin_to_base: null,
      quote_status: "PENDING_EXTERNAL_DATA",
    });
    expect(lines).toContain("current_price：未提供");
    expect(lines).toContain("margin_to_base：未提供");
    expect(lines).toContain("quote_status：PENDING_EXTERNAL_DATA");
  });

  it("still skips empty containers so sections can report themselves empty", () => {
    expect(leaves({})).toEqual([]);
    expect(leaves(null)).toEqual([]);
    expect(leaves([])).toEqual([]);
  });
});
