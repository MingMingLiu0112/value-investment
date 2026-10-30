import { defineConfig } from "@umijs/max";
import { readFileSync } from "node:fs";

const buildIdentity = (() => {
  try {
    return JSON.parse(readFileSync(".build-info.json", "utf8"));
  } catch {
    return { commit: null, built_at: null, source_dirty: true };
  }
})();

export default defineConfig({
  define: { __WEB_BUILD_IDENTITY__: buildIdentity },
  npmClient: "npm",
  hash: true,
  locale: { default: "zh-CN", antd: true, baseSeparator: "-" },
  routes: [
    { path: "/", redirect: "/daily" },
    { path: "/daily", component: "./DailyDecisions" },
    { path: "/decisions/:id", component: "./DecisionDetail" },
    { path: "/historical-price/:symbol/:day", component: "./HistoricalPrice" },
    { path: "/portfolio", component: "./Portfolio" },
    { path: "/history", component: "./DecisionHistory" },
    { path: "/alerts", component: "./ConditionAlerts" },
    { path: "/project", component: "./ProjectControl" },
    { path: "/system", component: "./SystemStatus" },
    { path: "/strategy/value", component: "./StrategyArchitecture/Value" },
    { path: "/strategy/hotspot", component: "./StrategyArchitecture/Hotspot" },
  ],
  proxy: { "/api": { target: "http://127.0.0.1:8001", changeOrigin: true } },
  title: "双策略投资助手",
});
