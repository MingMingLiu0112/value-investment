import React from "react";
import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import {
  HistoricalActionLineageReview,
  verifiedHistoricalActionLineage,
} from "../src/components/HistoricalActionLineageReview";
const { renderToStaticMarkup } = require("react-dom/server");
const binding = (name: string) => ({
  path: `runtime/${name}.pdf`,
  sha256: "a".repeat(64),
  url: "https://static.cninfo.com.cn/finalpage/2025-05-20/1234567890.PDF",
});
const fixture = () => ({
  schema_version: "historical-official-action-lineage-v1",
  action: "no_order",
  status: "HISTORICAL_SOURCE_REPLAYED",
  scope: "HISTORICAL_FILING_RELATION_NOT_CURRENT_CANDIDATE_OR_TRADE",
  symbol: "301061",
  evaluated_at: "2026-10-24T03:00:00+08:00",
  source_available_at: "2026-10-24T02:13:20+08:00",
  filing_window: { start: "2025-05-20", end: "2025-05-21" },
  observation_binding: binding("observation"),
  evidence_bindings: [
    binding("observation"),
    binding("original"),
    binding("amendment"),
  ],
  complete_chain_proven: false,
  comparison_allowed: false,
  historical_pit_proven: false,
  formal_eligibility: false,
  strategy_validation: "NOT_PROVEN",
  lineage_review: {
    schema_version: "hotspot-source-action-lineage-v1",
    action: "no_order",
    complete_chain_proven: false,
    comparison_allowed: false,
    historical_availability_proven: false,
    evidence_bindings: [binding("original"), binding("amendment")],
    unresolved: [],
    links: [
      {
        relation_status: "EXPLICIT_TARGET_MATCH",
        action: "no_order",
        original_number: "2025-021",
        amendment_number: "2025-022",
        original_published_date: "2025-05-20",
        amendment_published_date: "2025-05-20",
        changed_section: "七、股份变动情况表",
        effect_status: "CORRECTION_DECLARED",
        cancellation_asserted_by_this_document: false,
        complete_chain_proven: false,
        comparison_allowed: false,
        original_binding: binding("original"),
        amendment_binding: binding("amendment"),
      },
    ],
  },
});
it("shows the historical original relationship without changing current ownership or price basis", () => {
  const data = fixture(),
    before = structuredClone(data);
  expect(verifiedHistoricalActionLineage(data)).toBe(true);
  const html = renderToStaticMarkup(
    <HistoricalActionLineageReview value={data} />,
  );
  for (const label of [
    "301061",
    "2025-021",
    "2025-022",
    "股份变动情况表",
    "本文件是否明确撤销：",
    "不是当前候选",
    "不改原保护位",
  ])
    expect(html).toContain(label);
  expect(html).not.toContain("<button");
  expect(data).toEqual(before);
});
it.each(["historical_pit_proven", "formal_eligibility", "comparison_allowed"])(
  "rejects an upgraded %s",
  (key) => {
    expect(verifiedHistoricalActionLineage({ ...fixture(), [key]: true })).toBe(
      false,
    );
  },
);
it("rejects source mismatch and contradiction, without making an empty-case verdict", () => {
  const data = fixture();
  data.lineage_review.links[0].original_binding.sha256 = "f".repeat(64);
  expect(verifiedHistoricalActionLineage(data)).toBe(false);
  const conflict = fixture();
  conflict.lineage_review.links[0].cancellation_asserted_by_this_document = true;
  expect(verifiedHistoricalActionLineage(conflict)).toBe(false);
  expect(
    renderToStaticMarkup(
      <HistoricalActionLineageReview
        value={{ action: "no_order", status: "UNAVAILABLE" }}
      />,
    ),
  ).toContain("暂不可核验");
});
it("rejects malformed render fields and links not pinned to the original", () => {
  const malformed = fixture();
  (malformed.lineage_review.links[0] as any).changed_section = {
    unexpected: true,
  };
  expect(verifiedHistoricalActionLineage(malformed)).toBe(false);
  expect(() =>
    renderToStaticMarkup(<HistoricalActionLineageReview value={malformed} />),
  ).not.toThrow();
  const wrongDate = fixture();
  wrongDate.lineage_review.links[0].original_binding.url =
    "https://static.cninfo.com.cn/finalpage/2099-01-01/9999999999.PDF";
  expect(verifiedHistoricalActionLineage(wrongDate)).toBe(false);
  const wrongOriginal = fixture();
  wrongOriginal.lineage_review.links[0].original_binding.url =
    "https://static.cninfo.com.cn/finalpage/2025-05-20/9999999999.PDF";
  expect(verifiedHistoricalActionLineage(wrongOriginal)).toBe(false);
});
it.skipIf(!process.env.HISTORICAL_ACTION_LINEAGE_JSON)(
  "renders the actual source-replayed official example",
  () => {
    const data = JSON.parse(
      readFileSync(process.env.HISTORICAL_ACTION_LINEAGE_JSON!, "utf8"),
    );
    expect(verifiedHistoricalActionLineage(data)).toBe(true);
    expect(
      renderToStaticMarkup(<HistoricalActionLineageReview value={data} />),
    ).toContain("2025-022");
  },
);
