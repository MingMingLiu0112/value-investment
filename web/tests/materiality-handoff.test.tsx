import React from "react";
import { describe, expect, it, vi } from "vitest";
import { MaterialityHandoff } from "../src/components/ValuePolicyReview";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({ Link: ({ children }: any) => <>{children}</> }));

describe("scoped materiality handoff", () => {
  it("keeps an imported signature separate from publication and investment permission", () => {
    const html = renderToStaticMarkup(
      <MaterialityHandoff
        material={{
          status: "AUTHENTICATED_RESPONSE_IMPORTED",
          approval_granted: false,
          scan_window: { scan_from: "2026-10-11", scan_to: "2026-10-15" },
          announcements: [{ title: "TEST_ONLY 公告" }],
          commands: {
            consume_signed_response: "TEST_ONLY consume",
            recompute: "TEST_ONLY recheck",
          },
        }}
      />,
    );
    expect(html).toContain("已核验签署回执");
    expect(html).toContain("仍须重新计算并发布");
    expect(html).toContain("公告 1 份");
    expect(html).toContain("TEST_ONLY recheck");
    expect(html).not.toContain("正式可买入");
  });

  it("shows a blocked handoff without a nonfunctional approval command", () => {
    const html = renderToStaticMarkup(
      <MaterialityHandoff
        material={{
          status: "MATERIALITY_HANDOFF_BLOCKED",
          approval_granted: false,
          reason: "证据绑定未通过",
        }}
      />,
    );
    expect(html).toContain("证据绑定未通过");
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<pre");
  });
});
