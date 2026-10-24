import React from "react";
import { expect, it, vi } from "vitest";
import { CurrentScreening } from "../src/components/CurrentScreening";
import type { CurrentScreening as Screening } from "../src/types/discovery";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
}));
vi.mock("antd", () => ({
  Input: () => <input />,
  Select: () => <select />,
  Table: ({ dataSource, columns, expandable }: any) => (
    <div>
      {dataSource.map((row: any) => (
        <div key={row.symbol}>
          {columns.map((col: any) => (
            <span key={col.key}>{col.render(null, row)}</span>
          ))}
          {expandable.expandedRowRender(row)}
        </div>
      ))}
    </div>
  ),
}));
const scan: Screening = {
  status: "VERIFIED_RESEARCH_SCAN",
  scope: "RESEARCH_LEADS_NOT_ACTIONS",
  lead_count: 1,
  details: {
    status: "SOURCE_REVALIDATED",
    leads: [
      {
        symbol: "600001",
        company_name: "测试公司",
        channels: ["dividend_cash_return"],
        screening_reasons: ["现金回报线索"],
        next_required_evidence: "核验官方现金流",
        evidence_ids: ["financial"],
        financial_observations: [
          {
            field_name: "roe_weighted",
            value: "0",
            unit: "percent",
            period_label: "2025-12-31",
            available_at: "2026-10-22T12:00:00Z",
            source_name: "Provider",
            source_url: "https://example.test/source",
            raw_file_hash: "a".repeat(64),
            validation_status: "unverified",
          },
        ],
      },
    ],
    financial: {
      status: "PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS",
      period: "2025-12-31",
      provider_rows: 1,
      observation_count: 1,
      adopted_observation_count: 1,
    },
  },
};
it("shows source-bound leads, raw zero and uncertainty without creating a decision", () => {
  const html = renderToStaticMarkup(
    <CurrentScreening scan={scan} decisions={[]} />,
  );
  for (const text of [
    "测试公司",
    "股息现金回报",
    "现金回报线索",
    "0",
    "percent",
    "未获官方财报准入",
    "首次可得",
    "待官方补证与适用模型研究",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("/decisions/");
});
it("links only an existing published research identity", () => {
  const html = renderToStaticMarkup(
    <CurrentScreening
      scan={scan}
      decisions={[{ id: "published-600001", symbol: "600001" }]}
    />,
  );
  expect(html).toContain("/decisions/published-600001");
});
it("shows observed venues and failures without calling partial coverage all-market complete", () => {
  const partial: Screening = {
    ...scan,
    universe_count: 5224,
    screening_scope: {
      all_a_complete: false,
      covered_venues: ["SZSE", "SSE"],
      failed_venues: ["BSE"],
      observed_universe_count: 5224,
      quote_coverage: { tencent: { excluded_row_count: 353 } },
    },
  };
  const html = renderToStaticMarkup(
    <CurrentScreening scan={partial} decisions={[]} />,
  );
  for (const text of [
    "本次已覆盖市场初筛",
    "深交所、上交所",
    "北交所",
    "采集失败",
    "不视为退市",
    "5224",
    "353",
    "按供应商，不是去重公司数",
  ])
    expect(html).toContain(text);
  expect(html).not.toContain("本次全市场初筛（尚非交易机会）");
  expect(html).toContain("测试公司");
});
it.each(["summary", "sources"])(
  "hides forged rows when %s is unverified",
  (kind) => {
    const invalid = structuredClone(scan);
    if (kind === "summary") invalid.status = "UNVERIFIED";
    else invalid.details!.status = "SOURCE_REVALIDATION_FAILED";
    const html = renderToStaticMarkup(
      <CurrentScreening scan={invalid} decisions={[]} />,
    );
    expect(html).not.toContain("测试公司");
    expect(html).not.toContain("example.test/source");
  },
);
