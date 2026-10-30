import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { PublicEvidencePanel } from "../src/components/PublicEvidencePanel";
import { api, type PublicEvidenceStatus } from "../src/services/api";
import { useApi } from "../src/hooks/useApi";
import SystemStatus from "../src/pages/SystemStatus";

const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (node: React.ReactNode) => string;
};
vi.mock("@umijs/max", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));
vi.mock("../src/components/Workbench", () => ({
  Workbench: ({ children }: { children: React.ReactNode }) => (
    <main>{children}</main>
  ),
}));
vi.mock("../src/components/ResearchFunnelAuditPanel", () => ({
  ResearchFunnelAuditPanel: () => null,
}));
vi.mock("../src/hooks/useApi", () => ({ useApi: vi.fn() }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function fixture(): PublicEvidenceStatus {
  return {
    schema_version: "public-evidence-status-v1",
    action: "no_order",
    status: "PARTIAL",
    scope: "REQUESTED_REPORTS_ONLY",
    generated_at: "2026-10-30T12:00:00+08:00",
    reason: "TEST_ONLY 部分来源尚未取得",
    formal_eligibility: false,
    strict_historical_pit: false,
    exchanges: {
      SSE: { requested: 2, verified: 1 },
      SZSE: { requested: 1, verified: 0 },
      BSE: { requested: 0, verified: 0 },
    },
    items: [
      {
        symbol: "600519",
        issuer_name: "TEST_ONLY 示例公司",
        period: "2026-H1",
        status: "VERIFIED",
        source_url: "https://example.org/TEST_ONLY.pdf",
        sha256: "a".repeat(64),
        published_date: "2026-08-15",
        fetched_at: "2026-09-09T03:34:44+00:00",
        reused: true,
        reason: null,
        fact_status: "PARTIAL",
        adopted_fact_count: 4,
      },
      {
        symbol: "000001",
        issuer_name: "TEST_ONLY 未取得",
        period: "2026-Q3",
        status: "SOURCE_UNAVAILABLE",
        source_url: null,
        sha256: null,
        published_date: null,
        fetched_at: null,
        reused: false,
        reason: "TEST_ONLY 原始来源不可用",
        fact_status: "NOT_EXTRACTED",
        adopted_fact_count: 0,
      },
    ],
  };
}
function render(
  evidence = fixture(),
  props: { loading?: boolean; error?: string } = {},
) {
  return renderToStaticMarkup(
    <PublicEvidencePanel
      evidence={evidence}
      loading={false}
      retry={vi.fn()}
      {...props}
    />,
  );
}
it("shows requested-report coverage, adoption limits and original reuse timestamps separately", () => {
  const data = fixture(),
    before = structuredClone(data);
  const html = render(data);
  for (const text of [
    "公开来源覆盖",
    "上交所",
    "深交所",
    "北交所",
    "已核验 1 / 已请求 2",
    "TEST_ONLY 示例公司",
    "2026-H1",
    "2026-08-15",
    "2026-09-09T03:34:44+00:00",
    "复用已存原件（保留原取得时间）",
    "已采用 4 项事实；不代表事实完整",
    "来源不可用不等于零候选",
    "不证明严格历史时点可得性",
    "仅覆盖已请求的报告",
    "不触发来源采集",
    "action=no_order",
  ])
    expect(html).toContain(text);
  expect(html).toContain('href="https://example.org/TEST_ONLY.pdf"');
  expect(html).toContain("<details><summary>来源校验信息</summary>");
  const visible = html.replace(/<details[\s\S]*?<\/details>/g, "");
  expect(visible).not.toContain("a".repeat(64));
  expect(html).toContain("原始取得：2026-09-09T03:34:44+00:00");
  expect(html).not.toContain("原始取得：2026-10-30");
  expect(data).toEqual(before);
});
it.each(["VERIFIED", "PARTIAL", "MISSING", "CONFLICT"] as const)(
  "retains %s source state without inferring fact or research admission",
  (status) => {
    const data = fixture();
    data.status = status;
    const html = render(data);
    expect(html).toContain("不代表事实完整");
    expect(html).toContain("未取得正式准入");
    if (status === "CONFLICT") expect(html).toContain("来源存在冲突");
    if (status === "MISSING") expect(html).toContain("来源缺失");
  },
);
it("does not replace missing acquisition time with generation time or infer zero candidates from an empty list", () => {
  const data = fixture();
  data.items[0].fetched_at = null;
  expect(render(data)).toContain("未提供，未用生成时间代替");
  data.items = [];
  expect(render(data)).toContain("未列出已请求报告记录；不代表候选数量为零");
});
it.each(["javascript:alert(1)", "file:///C:/private.pdf", "/local/source.pdf"])(
  "never links unsafe source %s",
  (url) => {
    const data = fixture();
    data.items[0].source_url = url;
    expect(render(data)).not.toContain('href="' + url + '"');
    expect(render(data)).toContain("未提供可用原件链接");
  },
);
it.each([
  (d: any) => {
    d.schema_version = "unknown";
  },
  (d: any) => {
    d.action = "buy";
  },
  (d: any) => {
    d.scope = "ALL_MARKET";
  },
  (d: any) => {
    d.formal_eligibility = true;
  },
  (d: any) => {
    d.strict_historical_pit = true;
  },
  (d: any) => {
    d.items = [null];
  },
  (d: any) => {
    d.items[0].adopted_fact_count = -1;
  },
  (d: any) => {
    d.items[0].reused = "true";
  },
  (d: any) => {
    d.exchanges.BSE = null;
  },
  (d: any) => {
    d.exchanges.SSE.verified = 3;
  },
])("hides numeric coverage for malformed contracts", (damage) => {
  const data = fixture();
  damage(data);
  const html = render(data);
  expect(html).toContain("未展示覆盖数值");
  expect(html).not.toContain("已核验 1 / 已请求 2");
  expect(html).not.toContain("TEST_ONLY 示例公司");
});
it("keeps errors and loading independent and does not show stale success data", () => {
  const error = render(fixture(), { error: "TEST_ONLY 请求失败" });
  expect(error).toContain("公开来源状态读取失败");
  expect(error).toContain("重试读取");
  expect(error).not.toContain("TEST_ONLY 示例公司");
  const loading = render(fixture(), { loading: true });
  expect(loading).toContain("正在读取公开来源状态");
  expect(loading).not.toContain("TEST_ONLY 示例公司");
  const missing = renderToStaticMarkup(
    <PublicEvidencePanel loading={false} retry={vi.fn()} />,
  );
  expect(missing).toContain("尚未取得公开来源状态，不能认定没有候选");
});
it.each(["error", "loading"])(
  "mounts public evidence above packet %s without requiring packet success",
  (packetState) => {
    vi.stubGlobal("__WEB_BUILD_IDENTITY__", {
      commit: "TEST_ONLY",
      built_at: "TEST_ONLY",
    });
    vi.mocked(useApi).mockImplementation(((load: unknown) =>
      load === api.publicEvidence
        ? { data: fixture(), loading: false, error: undefined, retry: vi.fn() }
        : {
            data: undefined,
            loading: packetState === "loading",
            error:
              packetState === "error"
                ? "TEST_ONLY packet unavailable"
                : undefined,
            retry: vi.fn(),
          }) as typeof useApi);
    const html = renderToStaticMarkup(<SystemStatus />);
    expect(useApi).toHaveBeenCalledWith(api.publicEvidence);
    expect(html).toContain("TEST_ONLY 示例公司");
    if (packetState === "error") {
      expect(html).toContain("TEST_ONLY packet unavailable");
      expect(html.indexOf("公开来源覆盖")).toBeLessThan(
        html.indexOf("TEST_ONLY packet unavailable"),
      );
    }
  },
);
it("uses only the public read endpoint with cancellation and no private session handshake", async () => {
  const fetcher = vi.fn(
    async (_url: RequestInfo | URL, _options?: RequestInit) =>
      new Response(JSON.stringify(fixture()), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("window", {
    sessionStorage: {
      getItem: () => {
        throw new Error("private storage accessed");
      },
    },
  });
  const controller = new AbortController();
  expect(await api.publicEvidence(controller.signal)).toEqual(fixture());
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe("/api/v1/public-evidence");
  expect(options?.signal).toBe(controller.signal);
  expect(options?.method ?? "GET").toBe("GET");
  expect(options?.body).toBeUndefined();
  expect(new Headers(options?.headers).has("X-Local-Session")).toBe(false);
});
it.each([503, 404])(
  "surfaces unavailable public endpoint HTTP %s without a candidate count",
  async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              action: "no_order",
              status: "SOURCE_UNAVAILABLE",
              detail: "TEST_ONLY not ready",
            }),
            { status },
          ),
      ),
    );
    await expect(api.publicEvidence()).rejects.toThrow("TEST_ONLY not ready");
  },
);

it("shows only adopted field names and bound rejection issues without inferring missing currency", async () => {
  const data = fixture();
  data.items[0].adopted_fields = ["debt_ratio"];
  data.items[0].fact_issues = [];
  data.items[1].adopted_fields = [];
  data.items[1].fact_issues = ["MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS"];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(data), { status: 200 })),
  );
  const response = await api.publicEvidence();
  expect(response.items[0].adopted_fields).toEqual(["debt_ratio"]);
  expect(response.items[1].fact_issues).toEqual([
    "MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS",
  ]);
  const html = render(response);
  expect(html).toContain("仅已核验字段：debt_ratio");
  expect(html).toContain("未采纳原因（现有资产负债表核验记录）");
  expect(html).toContain("MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS");
  expect(html).not.toContain("币种缺失");
});
it("keeps old responses without optional field explanations compatible", () => {
  const html = render(fixture());
  expect(html).toContain("TEST_ONLY 示例公司");
  expect(html).not.toContain("仅已核验字段");
  expect(html).not.toContain("未采纳原因");
});
it.each(["fact_issues", "adopted_fields"] as const)(
  "rejects malformed optional %s instead of coercing the payload",
  (field) => {
    for (const value of [null, "debt_ratio", 0, {}, [null], [7], [true]]) {
      const data = fixture();
      (data.items[0] as unknown as Record<string, unknown>)[field] = value;
      const html = render(data);
      expect(html).toContain("未展示覆盖数值");
      expect(html).not.toContain("TEST_ONLY 示例公司");
    }
  },
);
