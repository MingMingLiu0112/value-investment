import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { economicRef, economicFixture } from "./fixtures/sourceNativeEconomic";

const hooks = vi.hoisted(() => ({ values: [] as any[], cursor: 0 }));
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState(initial: any) {
      const index = hooks.cursor++;
      if (!(index in hooks.values))
        hooks.values[index] =
          typeof initial === "function" ? initial() : initial;
      return [
        hooks.values[index],
        (next: any) => {
          hooks.values[index] =
            typeof next === "function" ? next(hooks.values[index]) : next;
        },
      ];
    },
    useRef(initial: any) {
      const index = hooks.cursor++;
      if (!(index in hooks.values)) hooks.values[index] = { current: initial };
      return hooks.values[index];
    },
  };
});
import {
  EconomicReviewResult,
  SourceNativeEconomicReview,
} from "../src/components/SourceNativeEconomicReview";

const nextRef = {
  ...economicRef,
  path: "runtime/TEST_ONLY_RELOCATED_SAME_BYTES/candidate.json",
};
function render(candidate = economicRef) {
  hooks.cursor = 0;
  return SourceNativeEconomicReview({ symbol: "600519", candidate });
}
function nodes(value: any): any[] {
  if (Array.isArray(value)) return value.flatMap(nodes);
  if (!React.isValidElement(value)) return [];
  const element = value as React.ReactElement<any>;
  return [element, ...nodes(element.props.children)];
}
function click(tree: any) {
  const button = nodes(tree).find(
    (node) => typeof node.props.onClick === "function",
  );
  expect(button).toBeDefined();
  button.props.onClick();
}
function hasResult(tree: any) {
  return nodes(tree).some((node) => node.type === EconomicReviewResult);
}
function mismatchShown(tree: any) {
  return nodes(tree).some((node) => node.props.role === "status");
}

beforeEach(() => {
  hooks.values = [];
  hooks.cursor = 0;
  vi.restoreAllMocks();
});

it("withdraws loaded numbers when the path changes but the SHA stays identical", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    json: async () => economicFixture(),
  } as Response);
  click(render());
  await vi.waitFor(() => expect(hooks.values[0]).toBeDefined());
  expect(hasResult(render())).toBe(true);
  const changed = render(nextRef);
  expect(hasResult(changed)).toBe(false);
  expect(mismatchShown(changed)).toBe(true);
});

it("does not display a late response for the previous path in the current candidate", async () => {
  let finish!: (value: Response) => void;
  vi.spyOn(globalThis, "fetch").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  click(render());
  expect(hasResult(render(nextRef))).toBe(false);
  finish({ ok: true, json: async () => economicFixture() } as Response);
  await vi.waitFor(() => expect(hooks.values[0]).toBeDefined());
  const current = render(nextRef);
  expect(hasResult(current)).toBe(false);
  expect(mismatchShown(current)).toBe(true);
});
