import React from "react";
import { describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
  useLocation: () => ({ pathname: "/strategy/value" }),
}));
import { catalog, review } from "../../config/strategyArchitecture.v1";
import { ArchitectureView, StageButton, StageDetail } from "./index";
describe("versioned strategy architecture", () => {
  it("pins review separately from disconnected runtime evidence", () => {
    expect(review.baseline).toBe("1cf73655457094fe924001497393f2be6d22fcec");
    expect(review.runtimeEvidence).toBe("NOT_CONNECTED");
    expect(
      catalog.value.stages.find((s) => s.id === "value_price")?.milestone,
    ).toContain("当前价格对齐与G3待完成");
  });
  it.each(["value", "hotspot"] as const)(
    "renders %s with stopping branches and existing destinations",
    (key) => {
      const html = renderToStaticMarkup(<ArchitectureView strategy={key} />);
      for (const text of [
        "不是实时进度",
        "资料不足",
        "无法评价",
        "条件不符",
        "不操作",
        "人工复核",
        "共享组合风险",
        "NOT_CONNECTED",
      ])
        expect(html).toContain(text);
      for (const path of ["/daily", "/history", "/system", "/portfolio"])
        expect(html).toContain('href="' + path + '"');
      expect(html).not.toMatch(/\d+%|ant-progress|ant-tag-success/);
      expect(html).toContain("工程：");
      expect(html).toContain("证据：");
      expect(catalog[key].stages.length).toBeLessThanOrEqual(9);
      const ids = catalog[key].stages.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const [index, stage] of catalog[key].stages.entries()) {
        for (const dep of stage.dependencies)
          expect(ids.slice(0, index)).toContain(dep);
        for (const path of stage.modules)
          expect(existsSync(resolve("..", path)), path).toBe(true);
        const detail = renderToStaticMarkup(<StageDetail stage={stage} />);
        for (const text of [
          stage.existingEvidence,
          stage.evidence,
          stage.nextStep,
          stage.ruleWhy,
        ])
          expect(detail).toContain(text);
      }
    },
  );
  it("selects stable IDs through native button activation", () => {
    const select = vi.fn(),
      stage = catalog.hotspot.stages[2];
    const node = StageButton({ stage, selected: false, onSelect: select });
    expect(node.type).toBe("button");
    expect(node.props["aria-controls"]).toBe("architecture-detail");
    node.props.onClick();
    expect(select).toHaveBeenCalledWith("hotspot_validation");
    expect(
      StageButton({ stage, selected: true, onSelect: select }).props[
        "aria-pressed"
      ],
    ).toBe(true);
  });
  it("preserves historical evidence and independent hotspot dependencies", () => {
    const hotspot = JSON.stringify(catalog.hotspot);
    expect(hotspot).toContain("34次历史触发、32次完整五交易日跟踪、2次右删失");
    expect(hotspot).toContain("NOT_PROVEN");
    expect(
      catalog.hotspot.stages
        .flatMap((s) => s.dependencies)
        .some((id) => id.startsWith("value_")),
    ).toBe(false);
    expect(JSON.stringify(catalog.value)).toContain("2026-06-30");
    expect(JSON.stringify(catalog.value)).toContain("非当前买价");
    expect(catalog.value.stages[0].channels).toHaveLength(4);
  });
  it("registers both routes and menu entries without transports", () => {
    const routes = readFileSync(".umirc.ts", "utf8"),
      menu = readFileSync("src/components/Workbench.tsx", "utf8");
    for (const path of ["/strategy/value", "/strategy/hotspot"]) {
      expect(routes).toContain(path);
      expect(menu).toContain(path);
    }
    const page = readFileSync(
      "src/pages/StrategyArchitecture/index.tsx",
      "utf8",
    );
    expect(page).not.toMatch(/useApi|fetch\(|services\/|localStorage/);
  });
});
