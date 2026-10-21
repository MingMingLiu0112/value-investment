import React from "react";
import { describe, expect, it, vi } from "vitest";
import {
  IndependentEventSupplement,
  MaterialityHandoff,
} from "../src/components/ValuePolicyReview";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({ Link: ({ children }: any) => <>{children}</> }));

describe("scoped materiality handoff", () => {
  it("keeps independently consumed event material separate from current G3 and valuation", () => {
    const html = renderToStaticMarkup(
      <IndependentEventSupplement
        material={{
          status: "EXTERNAL_SIGNATURE_REQUIRED",
          approval_granted: false,
          scan_window: { scan_from: "2026-07-01", scan_to: "2026-10-20" },
          announcements: [{ title: "TEST_ONLY new-context announcement" }],
          commands: {
            consume_signed_response: "TEST_ONLY exact-handoff consume",
            recompute: "TEST_ONLY new-package research",
          },
        }}
      />,
    );
    expect(html).toContain("独立新版本公告审核材料");
    expect(html).toContain("不替换上方估值候选");
    expect(html).toContain("2026-10-20");
    expect(html).toContain("TEST_ONLY exact-handoff consume");
    expect(html).not.toContain("已核验签署回执");
  });
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
