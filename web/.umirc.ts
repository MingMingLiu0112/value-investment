import { defineConfig } from "@umijs/max";

export default defineConfig({
  npmClient: "npm",
  locale: { default: "zh-CN", antd: true, baseSeparator: "-" },
  routes: [
    { path: "/", redirect: "/daily" },
    { path: "/daily", component: "./DailyDecisions" },
    { path: "/decisions/:id", component: "./DecisionDetail" },
    { path: "/portfolio", component: "./Portfolio" },
    { path: "/history", component: "./DecisionHistory" },
    { path: "/system", component: "./SystemStatus" },
  ],
  proxy: { "/api": { target: "http://localhost:8001", changeOrigin: true } },
  title: "双策略投资助手",
});
