import React from "react";
import { describe, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
import { RuntimeResults, ModuleRuntimePanel } from "./ModuleRuntimePanel";
import { api, type ValueWorkbenchResponse } from "../services/api";

describe("actual runtime evidence separate from capability descriptions", () => {
  it("retains exact failures and does not infer an E1 run from a valuation", () => {
    const data = {
      symbol: "TEST_ONLY",
      action: "no_order",
      formal_eligibility: false,
      quantity: null,
      schema_version: "value-transparent-workbench-v1",
      sections: [
        {
          id: "valuation",
          title: "估值",
          status: "SOURCE_BOUND_RESULTS",
          summary: "TEST_ONLY",
          data: {
            native_results: {
              first_input: { receipt_binding: { sha256: "TEST_HASH" } },
            },
          },
          blockers: [],
        },
        {
          id: "price",
          title: "价格",
          status: "UNASSESSABLE",
          summary: "缺股本核验",
          data: null,
          blockers: ["SHARE_CONTINUITY_MISSING"],
        },
      ],
    } as ValueWorkbenchResponse;
    const html = renderToStaticMarkup(<RuntimeResults data={data} />);
    expect(html).toContain("TEST_HASH");
    expect(html).toContain("SHARE_CONTINUITY_MISSING");
    expect(html).toContain("E1 · 未提供产物 · NO_VERIFIED_RECORD");
    expect(html).toContain("不证明今日执行过扫描");
  });
  it("initial render does not read authorized task history or start work", () => {
    const tasks = vi.spyOn(api, "valueWorkbenchTasks");
    const live = vi.spyOn(api, "recentHorizonCashPolicyTasks");
    const create = vi.spyOn(api, "createValueWorkbenchTask");
    renderToStaticMarkup(<ModuleRuntimePanel />);
    expect(tasks).not.toHaveBeenCalled();
    expect(live).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});
