import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";

// Exercise the real React page/forms, with no server, private files or API writes.
it.skipIf(!process.env.READINESS_PLAYWRIGHT_MODULE)(
  "keeps portfolio handoffs scoped across React navigation and delayed account reads",
  async () => {
    const output = resolve("tests/.tmp/portfolio-navigation");
    mkdirSync(output, { recursive: true });
    const { build } = require("esbuild") as typeof import("esbuild");
    const bundle = await build({
      stdin: {
        contents: `import React from "react"; import {createRoot} from "react-dom/client";
          import Portfolio from "./src/pages/Portfolio";
          import {Link} from "@umijs/max";
          createRoot(document.getElementById("root")).render(<>
            <nav aria-label="Test-only route controls">
              <Link to="/portfolio?symbol=300364&strategy=hotspot&decision_id=hotspot-300364&research_version=v2#portfolio-sizing">Test hotspot handoff</Link>
            </nav><Portfolio /></>);`,
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
          name: "isolated-portfolio-transports",
          setup(builder) {
            builder.onResolve({ filter: /^@umijs\/max$/ }, () => ({
              path: "router",
              namespace: "portfolio-test",
            }));
            builder.onLoad(
              { filter: /.*/, namespace: "portfolio-test" },
              () => ({
                contents: `import React, {useSyncExternalStore} from "react";
              const subscribe = fn => { window.addEventListener("test-route", fn); return () => window.removeEventListener("test-route", fn); };
              export const useLocation = () => {
                useSyncExternalStore(subscribe, () => window.__routeVersion);
                return window.__location;
              };
              export const Link = ({to, children, ...props}) => <a {...props} href={to} onClick={event => {
                event.preventDefault(); const url = new URL(to, "https://test.invalid");
                window.__location = {pathname:url.pathname,search:url.search,hash:url.hash};
                window.__routeVersion++; window.dispatchEvent(new Event("test-route"));
              }}>{children}</a>;`,
                loader: "jsx",
                resolveDir: process.cwd(),
              }),
            );
            builder.onLoad({ filter: /[\\/]services[\\/]api\.ts$/ }, () => ({
              contents: `export class ApiError extends Error {};
              export const api = new Proxy({}, {get: (_, key) => (...args) => { window.__apiCalls.push(String(key)); return Promise.reject(new Error("Test forbids API calls")); }});`,
            }));
            builder.onLoad({ filter: /[\\/]hooks[\\/]useApi\.ts$/ }, () => ({
              contents:
                "export const useApi = () => ({data:undefined, loading:false, error:undefined, retry:() => {}});",
            }));
            builder.onLoad(
              { filter: /[\\/]hooks[\\/]usePrivateState\.ts$/ },
              () => ({
                contents: `import {useLocation} from "@umijs/max";
              export const usePrivateState = () => { useLocation(); return {...window.__privateState, retry:() => {}}; };`,
              }),
            );
          },
        },
      ],
    });
    const { chromium } = require(process.env.READINESS_PLAYWRIGHT_MODULE!);
    const oldTemp = { TMP: process.env.TMP, TEMP: process.env.TEMP };
    process.env.TMP = process.env.TEMP = output;
    let browser: any;
    try {
      browser = await chromium.launchPersistentContext(
        resolve(output, "profile"),
        {
          executablePath: process.env.READINESS_BROWSER_PATH,
          headless: true,
          downloadsPath: output,
        },
      );
      const page = await browser.newPage();
      const errors: string[] = [];
      page.on("pageerror", (error: Error) => errors.push(error.message));
      await page.route("**/*", (route: any) => route.abort());
      const css = readFileSync("src/components/workbench.css", "utf8");
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.setContent(
        `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><style>body{margin:0}${css}</style></head><body><div id="root"></div></body></html>`,
      );
      await page.evaluate(() => {
        Object.assign(window, {
          __routeVersion: 0,
          __apiCalls: [],
          __location: {
            pathname: "/portfolio",
            search:
              "?symbol=600887&strategy=value&decision_id=600887&research_version=v1",
            hash: "#portfolio-fill",
          },
          __privateState: { kind: "LOADING", blockers: [] },
        });
      });
      await page.addScriptTag({ content: bundle.outputFiles[0].text });
      await page.getByRole("heading", { name: "我的持仓" }).waitFor();
      expect(await page.locator("#portfolio-fill").count()).toBe(0);
      await page.evaluate(() => {
        const test = window as any;
        test.__privateState = {
          kind: "BLOCKED_PRIVATE_INPUT",
          label: "测试账户，风险资料待完善",
          detail: "TEST_ONLY",
          blockers: [],
          portfolio: {
            status: "CONNECTED",
            revision: 1,
            cash_cny: "10000",
            total_equity_cny: "10000",
            positions: [],
            trades: [],
            blockers: [],
            valuation: {
              status: "CASH_ONLY_NO_QUOTE_REQUIRED",
              reason: "TEST_ONLY",
            },
          },
        };
        test.__routeVersion++;
        window.dispatchEvent(new Event("test-route"));
      });
      const fill = page.locator("#portfolio-fill");
      await fill.getByLabel("证券代码", { exact: true }).waitFor();
      expect(
        await fill.getByLabel("证券代码", { exact: true }).inputValue(),
      ).toBe("600887");
      expect(await fill.getByLabel("股数", { exact: true }).inputValue()).toBe(
        "",
      );
      expect(
        await fill.getByLabel("成交价（元）", { exact: true }).inputValue(),
      ).toBe("");
      expect(
        await fill.evaluate(
          (node: HTMLElement) => node.getBoundingClientRect().top,
        ),
      ).toBeLessThan(180);
      await fill.getByLabel("股数", { exact: true }).fill("100");
      await fill.getByLabel("成交价（元）", { exact: true }).fill("25");
      await page
        .getByRole("link", { name: "条件仓位试算", exact: true })
        .click();
      expect(
        await page.locator("#portfolio-sizing").getAttribute("open"),
      ).not.toBeNull();
      expect(await fill.getByLabel("股数", { exact: true }).inputValue()).toBe(
        "100",
      );
      await page.getByRole("link", { name: "Test hotspot handoff" }).click();
      await page.waitForFunction(
        () =>
          document.querySelector<HTMLInputElement>(
            "#portfolio-fill input[id$='symbol']",
          )?.value === "300364",
      );
      expect(await fill.getByLabel("股数", { exact: true }).inputValue()).toBe(
        "",
      );
      expect(
        await fill.getByLabel("成交价（元）", { exact: true }).inputValue(),
      ).toBe("");
      expect(
        await fill
          .getByText("情绪卫星仓 HOTSPOT_SATELLITE", { exact: true })
          .count(),
      ).toBeGreaterThan(0);
      const sizing = page.locator("#portfolio-sizing");
      expect(await sizing.getAttribute("open")).not.toBeNull();
      expect(
        await sizing.getByLabel("证券代码", { exact: true }).inputValue(),
      ).toBe("300364");
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        const nav = page.getByRole("navigation", { name: "持仓工作入口" });
        await nav.scrollIntoViewIfNeeded();
        const overflow = await nav.evaluate((node: HTMLElement) =>
          [...node.children].some(
            (child) => child.getBoundingClientRect().right > innerWidth + 1,
          ),
        );
        expect(overflow).toBe(false);
        await page.screenshot({
          path: resolve(output, `portfolio-${width}.png`),
          fullPage: true,
        });
      }
      await page.evaluate(() => {
        const test = window as any;
        test.__privateState.portfolio.status = "NOT_CONNECTED";
        test.__routeVersion++;
        window.dispatchEvent(new Event("test-route"));
      });
      await page.locator("#portfolio-setup").waitFor();
      expect(await page.locator("#portfolio-fill").count()).toBe(0);
      expect(
        await page.getByRole("link", { name: "填写初始账户与持仓" }).count(),
      ).toBe(1);
      expect(await page.evaluate(() => (window as any).__apiCalls)).toEqual([]);
      expect(errors).toEqual([]);
      writeFileSync(
        resolve(output, "result.json"),
        JSON.stringify(
          {
            action: "no_order",
            fixture: "TEST_ONLY",
            real_api_calls: 0,
            delayed_account_anchor: "PASS",
            same_page_context_reset: "PASS",
            fragment_preserves_input: "PASS",
            existing_forms_only: true,
            console_errors: errors,
          },
          null,
          2,
        ),
      );
    } finally {
      await browser?.close();
      for (const key of ["TMP", "TEMP"] as const) {
        if (oldTemp[key] === undefined) delete process.env[key];
        else process.env[key] = oldTemp[key];
      }
    }
  },
  90000,
);
