import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * TL10-RC：/daily 与 /portfolio 必须报告同一份私人状态。
 *
 * 仓库没有可用的组件渲染测试依赖（不得修改 package.json），因此这里
 * 校验两页确实接到共享的 usePrivateState，页面不再各自读取私人接口、
 * 也不再自造状态标签；标签本身由 privateStateFrom 的单元测试覆盖。
 */
const here = dirname(fileURLToPath(import.meta.url));
const read = (relative: string) =>
  readFileSync(join(here, "..", relative), "utf8");

const daily = read("src/pages/DailyDecisions/index.tsx");
const portfolio = read("src/pages/Portfolio/index.tsx");

describe("shared private state between daily and portfolio", () => {
  it("wires both pages to the same usePrivateState hook", () => {
    expect(daily).toContain('from "../../hooks/usePrivateState"');
    expect(portfolio).toContain('from "../../hooks/usePrivateState"');
    expect(daily).toContain("usePrivateState()");
    expect(portfolio).toContain("usePrivateState()");
  });

  it("keeps the portfolio page from reading the private endpoints on its own", () => {
    expect(portfolio).not.toContain("api.portfolio(");
    expect(portfolio).not.toContain("api.risk(");
    expect(portfolio).not.toContain("useApi(api.portfolio");
  });

  it("renders the shared label instead of a locally invented one", () => {
    expect(daily).toContain("<HoldingsAttention");
    expect(read("src/components/HoldingsAttention.tsx")).toContain(
      "state.label",
    );
    expect(portfolio).toContain("state.label");
  });
});
