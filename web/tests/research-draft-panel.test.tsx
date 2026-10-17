import React from "react";
import { describe, expect, it, vi } from "vitest";
import type { ResearchDraft } from "../src/types/api";

const { renderToStaticMarkup } = require("react-dom/server");

vi.mock("antd", () => {
  const Title = ({ children }: any) => <h3>{children}</h3>;
  const Text = ({ children }: any) => <span>{children}</span>;
  const ListItem = ({ children }: any) => <li>{children}</li>;
  const List = ({ dataSource = [], renderItem }: any) => (
    <ul>
      {dataSource.map((item: any, index: number) => (
        <li key={index}>{renderItem(item)}</li>
      ))}
    </ul>
  );
  (List as any).Item = ListItem;
  return {
    Alert: ({ message, description }: any) => (
      <div>
        {message}
        {description}
      </div>
    ),
    Descriptions: ({ items }: any) => (
      <dl>
        {items.map((item: any) => (
          <div key={item.key}>
            <dt>{item.label}</dt>
            <dd>{item.children}</dd>
          </div>
        ))}
      </dl>
    ),
    List,
    Table: ({ dataSource = [] }: any) => (
      <table>
        <tbody>
          {dataSource.map((row: any) => (
            <tr key={row.scenario}>
              <td>{row.scenario}</td>
              <td>{row.display_value}</td>
              <td>{row.terminal_residual_contribution_ratio}</td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
    Tag: ({ children }: any) => <span>{children}</span>,
    Typography: { Title, Text },
  };
});

import { ResearchDraftPanel } from "../src/pages/DecisionDetail/ResearchDraftPanel";

const draft = {
  schema_version: "public-research-draft-v1",
  action: "no_order",
  symbol: "000333",
  company_name: "美的集团",
  run_id: "midea-draft-test",
  research_version: "midea-draft-test-v1",
  status: "RESEARCH_DRAFT_NOT_APPROVED",
  research_as_of: "2026-10-16",
  available_at: "2026-10-17T10:22:15+00:00",
  financial_period: "2026-06-30",
  summary: "条件性研究摘要",
  valuation: {
    model_type: "residual_income_or_equity_value",
    model_version: "residual-income-equity-shared-dated-v2",
    valuation_date: "2026-10-16",
    status: "conditional_research_only",
    confidence: "低",
    currency: "CNY",
    scope:
      "conditional residual income with an algebraic dividend-path cross-check; not evidence of issuer distributable cash or dividend sustainability",
    scenarios: [
      {
        scenario: "bear",
        per_share_value: "36.0121",
        terminal_residual_contribution_ratio: "0.04",
      },
      {
        scenario: "base",
        per_share_value: "45.7417",
        terminal_residual_contribution_ratio: "0.15",
      },
      {
        scenario: "bull",
        per_share_value: "58.1686",
        terminal_residual_contribution_ratio: "0.26",
      },
    ],
    assumptions: [
      {
        name: "cost_of_equity",
        bear: "0.09",
        base: "0.09",
        bull: "0.09",
        rationale:
          "Candidate five-year ROE path anchored on audited FY2025 and unaudited H1 2026.",
      },
      {
        name: "retention",
        bear: "0.40",
        base: "0.35",
        bull: "0.30",
        rationale:
          "The bear case retains more capital to defend operations; the bull case distributes more of higher earnings.",
      },
    ],
  },
  model_validity: {
    status: "UNKNOWN",
    blockers: [
      "EVENT_MATERIALITY_PENDING_HUMAN_REVIEW",
      "Four 2026-10-14 and 2026-10-17 announcements remain PENDING_HUMAN_REVIEW.",
    ],
  },
  quote_fact: {
    quote_date: "2026-10-16",
    current_price: "84.60",
    currency: "CNY",
    status: "VERIFIED_CLOSE_NOT_ADMITTED",
  },
  price_bridge: {
    status: "INVALID",
    price_admitted: false,
    margin_to_bear: null,
    margin_to_base: null,
    blockers: ["MODEL_VALIDITY_UNKNOWN"],
    reason: "模型有效性尚未建立。",
    needed_evidence: "完成公告材料性复核。",
  },
  gates: { results: { G0_证据门: true, G3_估值门: false } },
  events: {
    status: "PENDING_HUMAN_REVIEW",
    pending_count: 1,
    items: [
      {
        announcement_id: "1225603532",
        title: "股东会决议公告",
        published_at: "2026-10-14",
        review_status: "PENDING_HUMAN_REVIEW",
        source_url: "https://static.cninfo.com.cn/finalpage/example.PDF",
      },
    ],
  },
  counter_evidence: ["半年报利润下降", "模型有效性只能保持UNKNOWN。"],
  thesis_breakers: ["ROE持续低于门槛"],
  next_events: ["下一期定期报告"],
  reopen_triggers: ["完成公告复核"],
  limitations: ["候选假设未经人工批准"],
  boundary: "研究草稿不等于买卖建议，正式决策仍为待研究。",
  evidence: [
    {
      id: "annual",
      title: "年度报告",
      url: "https://static.cninfo.com.cn/finalpage/annual.PDF",
      sha256: "a".repeat(64),
    },
    {
      id: "quote",
      title: "收盘行情封包",
      url: "runtime/quote-sessions/example/bundle.json",
      sha256: "b".repeat(64),
    },
  ],
  version_comparison: {
    from: {
      status: "INSUFFICIENT_PUBLIC_EVIDENCE",
      research_version: "old-v5",
    },
    to: { status: "RESEARCH_DRAFT_NOT_APPROVED", research_version: "new-v1" },
    changed: ["共享剩余收益模型已执行"],
    unchanged: ["正式G3仍未通过"],
  },
} satisfies ResearchDraft;

describe("research draft panel", () => {
  it("renders the unapproved draft, price rejection and evidence without execution fields", () => {
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={draft} />);
    expect(html).toContain("研究草稿（未批准）");
    expect(html).toContain("residual-income-equity-shared-dated-v2");
    expect(html).toContain("45.74");
    expect(html).toContain("84.60");
    expect(html).toContain("价格准入");
    expect(html).toContain("不允许正式价格比较");
    expect(html).toContain("公告材料性待人工复核");
    expect(html).toContain("股权成本");
    expect(html).toContain(
      "条件性剩余收益估值，并以股利路径作代数交叉核对；不证明发行人可分配现金或分红可持续性",
    );
    expect(html).toContain(
      "五年 ROE 路径以经审计的 2025 年年报和未经审计的 2026 年中报为锚。",
    );
    expect(html).toContain(
      "保守情景保留更多资本以支持经营，乐观情景分配更多较高盈利。",
    );
    expect(html).not.toContain(
      "The bear case retains more capital to defend operations",
    );
    expect(html).toContain("2026-10-14 与 2026-10-17 的四项公告仍待人工复核。");
    expect(html).toContain("正式研究仍待完成");
    expect(html).toContain("https://static.cninfo.com.cn/finalpage/annual.PDF");
    expect(html).toContain("runtime/quote-sessions/example/bundle.json");
    expect(html).not.toContain(
      'href="runtime/quote-sessions/example/bundle.json"',
    );
    expect(html).not.toContain("position_guidance");
    expect(html).not.toContain("目标仓位");
    expect(html).not.toContain("BUY_CANDIDATE");
    expect(html).not.toContain("SELL_CANDIDATE");
    for (const code of [
      "RESEARCH_DRAFT_NOT_APPROVED",
      "EVENT_MATERIALITY_PENDING_HUMAN_REVIEW",
      "EVENT_COVERAGE_INCOMPLETE",
      "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN",
      "PENDING_HUMAN_REVIEW",
      "INVALID",
      "UNKNOWN",
    ])
      expect(html).not.toContain(code);
  });
});
