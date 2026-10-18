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
    Typography: {
      Title,
      Text,
      Paragraph: ({ children }: any) => <p>{children}</p>,
    },
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
  const verifiedDraft: ResearchDraft = {
    ...draft,
    schema_version: "public-research-draft-v2",
    input_verification: {
      status: "SOURCE_AND_MODEL_INPUTS_MATCH",
      input_sha256: "c".repeat(64),
      computed_at: "2026-10-18T10:00:00+08:00",
      cutoff_at: "2026-10-17T18:00:00+08:00",
      basis_date: "2026-06-30",
      share_basis: "ordinary_shares_excluding_treasury",
      economic_approval: false,
      capital_inputs: [
        {
          field: "start_book_equity",
          value: "212861055000",
          unit: "CNY",
          scope: "consolidated_parent_equity",
          period_end: "2026-06-30",
          source_id: "half-year-report",
          physical_page: 7,
          normalization_rule: "CNY_THOUSANDS_TO_CNY",
          component_values: ["212861055"],
        },
        {
          field: "ordinary_shares",
          value: "7464347335",
          unit: "shares",
          scope: "ordinary_shares_excluding_treasury",
          period_end: "2026-06-30",
          source_id: "hkex-monthly-return",
          physical_page: 2,
          normalization_rule: "SUM_COMPONENTS",
          component_values: ["6700000000", "764347335"],
        },
      ],
    },
  };

  it("shows server-verified capital inputs and dated normalization without economic approval", () => {
    const html = renderToStaticMarkup(
      <ResearchDraftPanel draft={verifiedDraft} />,
    );
    for (const text of [
      "财务输入溯源",
      "归母权益",
      "212861055000",
      "普通股分母",
      "7464347335",
      "普通股合计（剔除库存股）",
      "half-year-report",
      "hkex-monthly-return",
      "212861055 千元 × 1000",
      "6700000000 + 764347335",
      "2026-10-17T18:00:00+08:00",
      "2026-10-18T10:00:00+08:00",
      "来源与模型输入一致；经济假设及估值尚未经批准。",
      "研究草稿（未批准）",
      "不允许正式价格比较",
    ])
      expect(html).toContain(text);
    expect(html).toContain("第 7 页");
    expect(html).toContain("第 2 页");
    expect(html).not.toContain("研究已批准");
    expect(html).not.toContain("position_guidance");
  });

  it("keeps legacy presentation unchanged even with injected verification metadata", () => {
    const legacyWithMetadata = {
      ...verifiedDraft,
      schema_version: "public-research-draft-v1" as const,
    };
    const legacy = renderToStaticMarkup(<ResearchDraftPanel draft={draft} />);
    expect(
      renderToStaticMarkup(<ResearchDraftPanel draft={legacyWithMetadata} />),
    ).toBe(legacy);
    expect(legacy).not.toContain("财务输入溯源");
  });

  it("supports an explicit issued-share basis and direct source values without modifying input", () => {
    const direct: ResearchDraft = {
      ...verifiedDraft,
      input_verification: {
        ...verifiedDraft.input_verification!,
        share_basis: "issued_ordinary_shares",
        capital_inputs: verifiedDraft.input_verification!.capital_inputs.map(
          (row) => ({
            ...row,
            normalization_rule: "DIRECT",
            component_values: [],
          }),
        ),
      },
    };
    const before = JSON.stringify(direct);
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={direct} />);
    expect(html).toContain("已发行普通股合计");
    expect(html).toContain("直接采用原始披露值");
    expect(html).not.toContain("千元转元：");
    expect(JSON.stringify(direct)).toBe(before);
  });

  it("does not turn an unknown normalization rule into a direct-value assertion", () => {
    const unknown: ResearchDraft = {
      ...verifiedDraft,
      input_verification: {
        ...verifiedDraft.input_verification!,
        capital_inputs: verifiedDraft.input_verification!.capital_inputs.map(
          (row) => ({
            ...row,
            normalization_rule: "UNKNOWN",
          }),
        ),
      },
    };
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={unknown} />);
    expect(html).toContain("未提供有效归一化依据");
    expect(html).not.toContain("直接采用原始披露值");
  });

  it("does not present economic approval as an input verification result", () => {
    const invalid = {
      ...verifiedDraft,
      input_verification: {
        ...verifiedDraft.input_verification!,
        economic_approval: true,
      },
    } as unknown as ResearchDraft;
    const html = renderToStaticMarkup(<ResearchDraftPanel draft={invalid} />);
    expect(html).not.toContain("财务输入溯源");
    expect(html).toContain("研究草稿（未批准）");
    expect(html).toContain("正式研究仍待完成");
  });

  it("does not display verification when the server match status is absent", () => {
    const missing = { ...verifiedDraft, input_verification: undefined };
    expect(
      renderToStaticMarkup(<ResearchDraftPanel draft={missing} />),
    ).not.toContain("财务输入溯源");
    const unknown = {
      ...verifiedDraft,
      input_verification: {
        ...verifiedDraft.input_verification!,
        status: "UNKNOWN",
      },
    } as unknown as ResearchDraft;
    expect(
      renderToStaticMarkup(<ResearchDraftPanel draft={unknown} />),
    ).not.toContain("财务输入溯源");
  });

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
