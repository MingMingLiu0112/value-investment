import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { evaluationFixture } from "./fixtures/strategy-readiness";
import { analysisDecision } from "./fixtures/value-research-analysis";

// Optional installed browser tooling; the application gains no dependency or port.
it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "keeps the full daily page and expanded workflows within desktop and mobile viewports",
  async () => {
    const output = resolve("tests/.tmp/readiness-layout");
    mkdirSync(output, { recursive: true });
    const state = { daily: {} as any, packet: {} as any };
    const value = evaluationFixture();
    value.readiness!.conditional_valuation = {
      bear: "31.000",
      base: "39.500",
      bull: "44.750",
      currency: "CNY",
      as_of: "2026-09-30",
      scope: "UNAPPROVED_RESEARCH_ONLY",
    };
    value.readiness!.price_snapshot = {
      value: "27.960",
      date: "2026-10-21",
      usage: "DISPLAY_ONLY",
    };
    const hotspot = evaluationFixture("HOTSPOT_SATELLITE");
    const publication = {
      packet_status: "CURRENT",
      publication_id: "layout-fixture",
    };
    const decision = (strategy: string) => ({
      id: strategy === "value" ? "600887" : "hotspot-600887",
      symbol: "600887",
      name: "测试证券",
      strategy,
      price_action_plan: {
        action: "no_order",
        signal_state: "WATCH",
        entry_trigger_price: "25.750",
        invalidation_price: "20.250",
        market_trade_date: "2026-10-21",
      },
    });
    state.daily = {
      action: "no_order",
      publication,
      sections: {
        value: [decision("value")],
        hotspot: [decision("hotspot")],
        holdings: [],
      },
      actionable_evaluation: {
        items: [value, hotspot],
        evaluated_count: 0,
        unassessable_count: 2,
        conclusion: "INCOMPLETE_EVALUATION",
      },
    };
    state.packet = {
      action: "no_order",
      ...publication,
      dates: { research_as_of: "2026-09-30", quote_trade_date: "2026-10-21" },
      data_freshness: {
        quote: { status: "FRESH" },
        research: { status: "STALE" },
      },
    };
    const { build } = require("esbuild") as typeof import("esbuild");
    const bundle = await build({
      stdin: {
        contents: `import React from "react"; import {createRoot} from "react-dom/client";
          import Daily from "./src/pages/DailyDecisions";
          import {ValueResearchAnalysis} from "./src/components/ValueResearchAnalysis";
          createRoot(document.getElementById("root")).render(window.__readinessAnalysisOnly
            ? <main style={{width:"min(1120px, 100%)",boxSizing:"border-box",padding:18,margin:"0 auto"}}><ValueResearchAnalysis decision={${JSON.stringify(analysisDecision())}} /></main>
            : <Daily />);`,
        loader: "tsx",
        resolveDir: process.cwd(),
      },
      bundle: true,
      write: false,
      platform: "browser",
      format: "iife",
      jsx: "automatic",
      loader: { ".css": "empty" },
      define: { "process.env.NODE_ENV": '"production"' },
      plugins: [
        {
          name: "readiness-fixture-transports",
          setup(builder) {
            builder.onResolve({ filter: /^@umijs\/max$/ }, () => ({
              path: "router",
              namespace: "readiness",
            }));
            builder.onLoad({ filter: /.*/, namespace: "readiness" }, () => ({
              contents: `import React from "react"; export const Link = ({to, children, ...props}) => React.createElement("a", {...props, href: to}, children); export const useLocation = () => ({pathname: "/daily"});`,
              resolveDir: process.cwd(),
            }));
            builder.onLoad({ filter: /[\\/]hooks[\\/]useApi\.ts$/ }, () => ({
              contents: `const responses = ${JSON.stringify(state)}; export const useApi = load => ({data: responses[load], loading: false, error: undefined, retry: () => {}});`,
            }));
            builder.onLoad({ filter: /[\\/]services[\\/]api\.ts$/ }, () => ({
              contents:
                "export const api = new Proxy({}, {get: (_, key) => key});",
            }));
            builder.onLoad(
              { filter: /[\\/]hooks[\\/]usePrivateState\.ts$/ },
              () => ({
                contents: `export const usePrivateState = () => ({kind: "LOCKED", label: "私人台账未解锁", retry: () => {}});`,
              }),
            );
          },
        },
      ],
    });
    const css = [
      "src/components/strategy-readiness.css",
      "src/components/value-research-analysis.css",
      "src/components/workbench.css",
      "src/pages/DailyDecisions/opportunities.css",
    ]
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");
    const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font-family:"Microsoft YaHei",sans-serif}${css}</style></head><body><div id="root"></div></body></html>`;
    writeFileSync(
      resolve(output, "daily.html"),
      html.replace("</body>", '<script src="daily.js"></script></body>'),
      "utf8",
    );
    writeFileSync(
      resolve(output, "daily.js"),
      bundle.outputFiles[0].text,
      "utf8",
    );
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const previousTemp = { TMP: process.env.TMP, TEMP: process.env.TEMP };
    process.env.TMP = process.env.TEMP = output;
    let browser: any;
    try {
      browser = await chromium.launchPersistentContext(
        resolve(output, "browser-profile"),
        {
          executablePath: process.env.READINESS_BROWSER_PATH,
          headless: true,
          downloadsPath: output,
        },
      );
      const page = await browser.newPage();
      const dimensions: unknown[] = [];
      for (const width of [1440, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.setContent(html);
        await page.addScriptTag({
          content:
            "window.__readinessAnalysisOnly=false;" +
            bundle.outputFiles[0].text,
        });
        await page.locator(".daily-readiness").waitFor({ state: "visible" });
        await page.locator(".readiness-security > summary").first().click();
        await page.locator(".readiness-security > summary").nth(1).focus();
        await page.keyboard.press("Enter");
        expect(await page.locator(".readiness-security[open]").count()).toBe(2);
        const measurement = await page.evaluate(() => ({
          width: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          overflowing: [...document.querySelectorAll(".daily-readiness *")]
            .filter((element) => {
              const bounds = element.getBoundingClientRect();
              return (
                bounds.width > 0 &&
                (bounds.right > window.innerWidth + 1 || bounds.left < -1)
              );
            })
            .map((element) => element.tagName + "." + element.className),
        }));
        dimensions.push(measurement);
        await page.screenshot({
          path: resolve(output, `daily-${width}.png`),
          fullPage: true,
        });
        expect(measurement.overflowing).toEqual([]);
        expect(measurement.scrollWidth).toBeLessThanOrEqual(width);
        await page.locator(".readiness-strategy > summary").first().click();
        expect(await page.locator(".readiness-strategy[open]").count()).toBe(1);
        await page.setContent(html);
        await page.addScriptTag({
          content:
            "window.__readinessAnalysisOnly=true;" + bundle.outputFiles[0].text,
        });
        await page.locator(".value-research-analysis > summary").click();
        await page
          .locator(".value-research-analysis details")
          .evaluateAll((elements: HTMLDetailsElement[]) =>
            elements.forEach((element) => {
              element.open = true;
            }),
          );
        const analysisWidth = await page.evaluate(
          () => document.documentElement.scrollWidth,
        );
        expect(analysisWidth).toBeLessThanOrEqual(width);
        dimensions.push({
          analysisViewport: width,
          scrollWidth: analysisWidth,
        });
        await page.screenshot({
          path: resolve(output, `analysis-${width}.png`),
          fullPage: true,
        });
      }
      writeFileSync(
        resolve(output, "dimensions.json"),
        JSON.stringify(dimensions, null, 2),
        "utf8",
      );
    } finally {
      await browser?.close();
      for (const key of ["TMP", "TEMP"] as const) {
        if (previousTemp[key] === undefined) delete process.env[key];
        else process.env[key] = previousTemp[key];
      }
    }
  },
  60000,
);
