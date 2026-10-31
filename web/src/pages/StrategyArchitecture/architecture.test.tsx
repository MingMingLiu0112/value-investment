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
    expect(review.baseline).toBe("d01923cd72c3e638bb3df490f9e148abccd82219");
    expect(review.runtimeEvidence).toBe("NOT_CONNECTED");
    expect(catalog.value.stages.find((s) => s.id === "F2")?.evidence).toContain(
      "跨日股本",
    );
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
      expect(catalog[key].stages.length).toBe(key === "value" ? 16 : 8);
      const ids = catalog[key].stages.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const [index, stage] of catalog[key].stages.entries()) {
        for (const dep of stage.dependencies) expect(ids).toContain(dep);
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
    expect(
      catalog.value.stages.find((s) => s.id === "B")?.channels,
    ).toHaveLength(4);
  });
  it("maps all proposal modules with distinct progress axes and no fake first-company completion", () => {
    expect(catalog.value.stages.map((s) => s.id)).toEqual([
      "A",
      "B",
      "C",
      "D1",
      "D2",
      "E1",
      "E2",
      "F1",
      "F2",
      "G1",
      "G2",
      "S1",
      "S2",
      "S3",
      "S4",
      "W1",
    ]);
    for (const stage of catalog.value.stages) {
      expect(stage.progress?.acceptance).toContain("尚未确认");
      expect(stage.progress?.realData).toBeTruthy();
      expect(stage.progress?.consumer).toBeTruthy();
      expect(stage.progress?.economic).toBeTruthy();
      expect(stage.progress?.deployment).toBeTruthy();
    }
    expect(
      catalog.value.stages.find((s) => s.id === "E2")?.dependencies,
    ).not.toContain("E1");
    expect(
      catalog.value.stages.find((s) => s.id === "E2")?.engineeringStatus,
    ).toBe("工程首编与真实来源重算完成／部署待验收");
    expect(catalog.value.stages.find((s) => s.id === "B")?.evidence).toContain(
      "CONFLICT",
    );
    const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
    expect(html).toContain("H1–H4");
    expect(html).toContain("无旧估值");
    expect(html).toContain("用户确认");
    expect(html).toContain("目标输出（不代表已实现）");
    expect(html).toContain("不代表共同前置");
    expect(html).toContain("不阻塞公开研究");
    expect(
      catalog.value.stages.find((s) => s.id === "F1")?.dependencies,
    ).not.toContain("E2");
    expect(html).toContain("/decisions/600887?strategy=value");
    expect(html).toContain('href="/project"');
  });
  it("shows C's four independent frozen states in overview and details without graduating downstream inputs", () => {
    const c = catalog.value.stages.find((stage) => stage.id === "C")!;
    for (const html of [
      renderToStaticMarkup(<ArchitectureView strategy="value" />),
      renderToStaticMarkup(<StageDetail stage={c} />),
      renderToStaticMarkup(
        <StageButton stage={c} selected={true} onSelect={() => {}} />,
      ),
    ]) {
      expect(html).toContain("C模块四轴状态");
      for (const text of [
        "工程闭环完成",
        "固定五家验收通过",
        "部署待验收",
        "用户尚未确认",
      ])
        expect(html).toContain(text);
    }
    expect(c.boundary).toContain("不授予经济、估值或交易资格");
    const detail = renderToStaticMarkup(<StageDetail stage={c} />);
    expect(detail).toContain("已验输入（固定五家范围）");
    expect(detail).toContain("已验输出（固定五家范围）");
    expect(detail).toContain(c.input);
    expect(detail).toContain(c.output);
    for (const id of ["D1", "D2", "E2"]) {
      const stage = catalog.value.stages.find((item) => item.id === id)!;
      expect(stage.engineeringStatus).not.toBe("工程闭环完成");
      const html = renderToStaticMarkup(<StageDetail stage={stage} />);
      expect(html).toContain(stage.input);
      expect(html).toContain(stage.output);
      expect(html).toContain("目标输出（不代表已实现）");
    }
  });
  it("aliases project to the exact existing Value component and replaces the obsolete disconnected-route claim", () => {
    const routes = readFileSync(".umirc.ts", "utf8");
    const component = (path: string) => {
      const declaration = routes
        .split("\n")
        .find((line) => line.includes('path: "' + path + '"'));
      return declaration?.match(/component: "([^"]+)"/)?.[1];
    };
    expect(component("/project")).toBe("./StrategyArchitecture/Value");
    expect(component("/project")).toBe(component("/strategy/value"));
    const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
    expect(html).toContain("/project与/strategy/value复用同一Value组件");
    expect(html).not.toContain("当前工作树没有已接入的/project");
    expect(html).toContain("不因C完成而推定已闭环");
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
