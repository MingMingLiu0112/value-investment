import React from "react";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: React.ReactElement) => string;
};
import {
  projectConnections,
  projectControl,
  projectFlowStages,
  projectModules,
} from "../src/data/projectControl";

vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  useLocation: () => ({ pathname: "/project" }),
}));

import ProjectControl from "../src/pages/ProjectControl";

describe("architecture and progress contracts", () => {
  it("keeps every flow, dependency, acceptance item and evidence reference resolvable", () => {
    const ids = new Set(projectModules.map((module) => module.id));
    expect(ids.size).toBe(projectModules.length);
    for (const module of projectModules) {
      expect(module.reviewedCommit).toMatch(/^[a-f0-9]{40}$/);
      expect(module.reviewedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(module.inputs.length).toBeGreaterThan(0);
      expect(module.outputs.length).toBeGreaterThan(0);
      expect(module.nextDeliverable.trim()).not.toBe("");
      module.dependencyIds.forEach((id) => expect(ids.has(id)).toBe(true));
      const evidenceIds = new Set(module.evidence.map((item) => item.id));
      expect(evidenceIds.size).toBe(module.evidence.length);
      for (const item of module.evidence) {
        expect(new URL(item.url).protocol).toBe("https:");
        if (item.kind !== "ci") {
          expect(item.url).toMatch(/\/blob\/[a-f0-9]{40}\//);
        }
      }
      for (const criterion of module.criteria) {
        criterion.evidenceIds.forEach((id) =>
          expect(evidenceIds.has(id)).toBe(true),
        );
        if (criterion.status === "met") {
          expect(criterion.evidenceIds.length).toBeGreaterThan(0);
        }
      }
      module.verification.evidenceIds.forEach((id) =>
        expect(evidenceIds.has(id)).toBe(true),
      );
      if (module.ownerReview.status !== "unconfirmed") {
        expect(module.ownerReview.reviewedCommit).toMatch(/^[a-f0-9]{40}$/);
        expect(module.ownerReview.reviewedScope.length).toBeGreaterThan(0);
        expect(module.ownerReview.reviewedAt).not.toBe("");
        expect(
          Boolean(module.ownerReview.userQuote || module.ownerReview.recordRef),
        ).toBe(true);
      }
    }
    for (const edge of projectConnections) {
      expect(ids.has(edge.from)).toBe(true);
      expect(ids.has(edge.to)).toBe(true);
    }
    for (const stage of projectFlowStages) {
      expect(stage.moduleIds.length).toBeGreaterThan(0);
      stage.moduleIds.forEach((id) => expect(ids.has(id)).toBe(true));
    }
    projectControl.batches.forEach((batch) =>
      batch.moduleIds.forEach((id) => expect(ids.has(id)).toBe(true)),
    );
  });

  it("preserves hotspot admission independence from the value valuation and price gates", () => {
    const byId = new Map(projectModules.map((module) => [module.id, module]));
    const dependencies = (
      id: (typeof projectModules)[number]["id"],
      visited = new Set<string>(),
    ): Set<string> => {
      if (visited.has(id)) return visited;
      visited.add(id);
      byId
        .get(id)!
        .dependencyIds.forEach((parent) => dependencies(parent, visited));
      return visited;
    };
    const hotspot = dependencies("H3");
    for (const valueGate of ["E1", "E2", "F1", "F2"]) {
      expect(hotspot.has(valueGate)).toBe(false);
    }
  });

  it("renders the real navigation and three progress axes without a backend or private account", () => {
    const html = renderToStaticMarkup(<ProjectControl />);
    expect(html).toContain('href="/project"');
    expect(html).toContain(projectControl.title);
    expect(html).toContain(projectControl.snapshotCommit.slice(0, 8));
    expect(html).toContain("工程实现");
    expect(html).toContain("业务验证");
    expect(html).toContain("用户验收");
    expect(html).toContain("开发暂缓");
    expect(html).toContain("本机");
    expect(readFileSync(".umirc.ts", "utf8")).toContain(
      '{ path: "/project", component: "./ProjectControl" }',
    );
  });
});
