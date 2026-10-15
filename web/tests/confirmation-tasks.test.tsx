import React from "react";
const { renderToStaticMarkup } = require("react-dom/server");
import { describe, expect, it, vi } from "vitest";
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));
import { ConfirmationTasks } from "../src/components/ConfirmationTasks";
describe("consolidated confirmations", () => {
  it("keeps unknown private facts and research authority independent with working destinations", () => {
    const html = renderToStaticMarkup(
      <ConfirmationTasks
        connected={false}
        decisions={[
          {
            id: "600887",
            symbol: "600887",
            name: "伊利股份",
            price_action_plan: {
              action: "no_order",
              signal_state: "WATCH",
              entry_trigger_price: null,
              invalidation_price: null,
              base: "10.08",
            },
          },
        ]}
      />,
    );
    expect(html).toContain("尚未连接");
    expect(html).toContain("不批准估值");
    expect(html).toContain('href="/portfolio"');
    expect(html).toContain('href="/decisions/600887"');
    expect(html).toContain("不提供一键代签");
    expect(html).toContain("版本或使用范围变化时重新确认");
  });
});
