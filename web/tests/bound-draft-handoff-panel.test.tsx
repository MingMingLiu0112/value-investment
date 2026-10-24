import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
import {
  HandoffNotReady,
  MaterialityHandoff,
} from "../src/components/ValuePolicyReview";
import { createValuePolicyTransport } from "../src/services/valuePolicy";

vi.mock("@umijs/max", () => ({ Link: ({ children }: any) => <>{children}</> }));
vi.mock("../src/components/DetailSection", () => ({
  DetailSection: ({ title, value }: any) => (
    <div>
      {title}
      {JSON.stringify(value)}
    </div>
  ),
}));

afterEach(() => vi.unstubAllGlobals());

describe("bound draft handoff", () => {
  it("shows blockers and exact bindings without signing controls or injected commands", () => {
    const html = renderToStaticMarkup(
      <HandoffNotReady
        material={{
          action: "no_order",
          status: "NOT_READY",
          symbol: "000333",
          blockers: ["EXACT_VERSION_REVIEW_CANDIDATE_MISSING"],
          bindings: {
            draft: { path: "synthetic/draft.json", sha256: "draft-hash" },
            package: { path: "synthetic/package.json", sha256: "package-hash" },
            input_sha256: "descriptor-hash",
          },
          verification: { approval_changed: false, research_admitted: false },
          materiality_handoff: {
            status: "MATERIALITY_HANDOFF_BLOCKED",
            approval_granted: false,
            reason: "INCOMPLETE_COVERAGE",
            commands: {
              consume_signed_response: "INVALID_SIGN",
              recompute: "INVALID_RUN",
            },
          },
        }}
      />,
    );
    for (const text of [
      "EXACT_VERSION_REVIEW_CANDIDATE_MISSING",
      "draft-hash",
      "package-hash",
      "descriptor-hash",
      "INCOMPLETE_COVERAGE",
    ])
      expect(html).toContain(text);
    for (const text of [
      "<button",
      "<pre",
      "INVALID_SIGN",
      "INVALID_RUN",
      "未签署响应",
    ])
      expect(html).not.toContain(text);
  });

  it("renders NOT_READY without optional bindings", () => {
    expect(
      renderToStaticMarkup(
        <HandoffNotReady
          material={{
            action: "no_order",
            status: "NOT_READY",
            symbol: "000333",
            blockers: ["BOUND_DRAFT_UNAVAILABLE"],
            verification: { approval_changed: false, research_admitted: false },
          }}
        />,
      ),
    ).toContain("BOUND_DRAFT_UNAVAILABLE");
  });

  it("keeps missing scan visible without commands", () => {
    const html = renderToStaticMarkup(
      <MaterialityHandoff
        material={{
          status: "NO_REGISTERED_INCREMENTAL_SCAN",
          approval_granted: false,
        }}
      />,
    );
    expect(html).toContain("NO_REGISTERED_INCREMENTAL_SCAN");
    expect(html).toContain("暂不可签署");
    expect(html).not.toContain("<pre");
  });

  it.each([false, true])(
    "requests explicit selector only when opted in: %s",
    async (boundDraft) => {
      const payload = {
        action: "no_order",
        status: "NOT_READY",
        symbol: "000333",
        blockers: [],
      };
      const fetcher = vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => payload });
      vi.stubGlobal("fetch", fetcher);
      const headers = vi
        .fn()
        .mockResolvedValue({ "X-Local-Session": "synthetic-session" });
      const transport = createValuePolicyTransport(headers);
      expect(await transport.handoff!("000333", boundDraft)).toEqual(payload);
      expect(fetcher).toHaveBeenCalledWith(
        `/api/v1/value-policy-review/000333/handoff${boundDraft ? "?bound_draft=true" : ""}`,
        {
          credentials: "same-origin",
          cache: "no-store",
          headers: { "X-Local-Session": "synthetic-session" },
        },
      );
    },
  );
});
