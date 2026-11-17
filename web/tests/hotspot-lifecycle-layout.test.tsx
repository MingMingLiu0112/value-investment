import React from "react";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { HotspotLifecycleReview } from "../src/components/HotspotLifecycleReview";
import {
  lifecycleFixture,
  lifecycleHeldFixture,
  lifecyclePlan,
} from "./fixtures/hotspot-lifecycle";
const { renderToStaticMarkup } = require("react-dom/server");

it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "keeps expanded lifecycle steps, original levels and folded hashes inside 320/390 widths",
  async () => {
    const output = resolve("../.tmp/hotspot-lifecycle-layout");
    mkdirSync(output, { recursive: true });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const context = await chromium.launchPersistentContext(
      resolve(output, "browser-profile"),
      {
        executablePath: process.env.READINESS_BROWSER_PATH,
        headless: true,
        downloadsPath: output,
      },
    );
    const measurements: unknown[] = [];
    try {
      const page = await context.newPage();
      for (const [name, review] of [
        ["no-entry", lifecycleFixture()],
        ["reference-only-not-owned", lifecycleHeldFixture()],
      ] as const) {
        const body = renderToStaticMarkup(
          <HotspotLifecycleReview
            review={review}
            symbol="600519"
            plan={lifecyclePlan()}
          />,
        );
        for (const width of [390, 320]) {
          await page.setViewportSize({ width, height: 900 });
          await page.setContent(
            `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font-family:Arial,sans-serif;font-size:14px;line-height:1.6}main{box-sizing:border-box;max-width:1100px;width:100%;padding:16px;margin:auto}h3{font-size:18px}h4{font-size:15px}</style><main>${body}</main></html>`,
          );
          await page
            .locator("details")
            .evaluateAll((elements: HTMLDetailsElement[]) =>
              elements.forEach((element) => {
                element.open = true;
              }),
            );
          expect(await page.locator("main").innerText()).toContain(
            "不授予个人加仓或交易权限",
          );
          const size = await page.evaluate(() => ({
            width: innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            overflowing: [...document.querySelectorAll("main *")]
              .filter((element) => {
                const bounds = element.getBoundingClientRect();
                return (
                  bounds.width > 0 &&
                  (bounds.right > innerWidth + 1 || bounds.left < -1)
                );
              })
              .map((element) => element.tagName),
          }));
          expect(size.scrollWidth).toBeLessThanOrEqual(width);
          expect(size.overflowing).toEqual([]);
          measurements.push({ name, ...size });
          await page.screenshot({
            path: resolve(output, `${name}-${width}.png`),
            fullPage: true,
          });
        }
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(measurements, null, 2),
      );
    } finally {
      await context.close();
    }
  },
  90000,
);
