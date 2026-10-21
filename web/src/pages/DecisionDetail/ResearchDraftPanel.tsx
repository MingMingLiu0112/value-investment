import { Alert, Descriptions, List, Table, Tag, Typography } from "antd";
import type { ResearchDraft, ResearchDraftAssumption } from "../../types/api";
import { formatScenarioValue } from "../../utils/researchDetail";
import { shortDigest } from "../../utils/history";
import {
  researchAssumptionName,
  researchChangeText,
  researchConfidenceText,
  researchForecastOrdinals,
  researchGateText,
  researchSentence,
  researchStatusText,
} from "../../utils/researchDraftText";

const LABEL_STYLE = { width: 132, whiteSpace: "nowrap" as const };
const FINANCIAL_LABELS: Record<string, string> = {
  period_end: "期间截止",
  fy2025_parent_profit_cny: "2025 全年归母净利润（元）",
  fy2025_parent_equity_cny: "2025 年末归母权益（元）",
  fy2025_weighted_roe: "2025 全年加权 ROE（比率）",
  h1_2026_revenue_cny: "2026 上半年合并收入（元）",
  h1_2026_parent_profit_cny: "2026 上半年归母净利润（元）",
  h1_2026_adjusted_parent_profit_cny: "2026 上半年扣非归母净利润（元）",
  h1_2026_adjusted_parent_profit_yoy: "扣非归母净利润同比（比率）",
  h1_2026_parent_equity_cny: "2026 半年末归母权益（元）",
  h1_2026_roe: "2026 上半年加权 ROE（比率）",
  ordinary_shares_20260630: "2026 半年末普通股分母（股）",
  h1_2026_parent_equity_thousand_cny: "2026 半年末归母权益原值（千元）",
  a_ordinary_shares_excluding_treasury: "A 股扣库存股（股）",
  h_ordinary_shares: "H 股（股）",
};

function httpUrl(value?: string | null): string | null {
  return value && /^https?:\/\//i.test(value) ? value : null;
}

function evidenceLocation(value?: string | null) {
  const url = httpUrl(value);
  if (url) {
    return (
      <a href={url} target="_blank" rel="noreferrer">
        打开来源
      </a>
    );
  }
  return (
    <Typography.Text type="secondary">
      本地证据：{value || "未提供定位"}
    </Typography.Text>
  );
}

function ListOrEmpty({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length)
    return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(item) => (
        <List.Item style={{ overflowWrap: "anywhere" }}>{item}</List.Item>
      )}
    />
  );
}

export function ResearchDraftPanel({ draft }: { draft: ResearchDraft }) {
  const scenarios = draft.valuation.scenarios.map((row) => ({
    ...row,
    display_value: formatScenarioValue(row.per_share_value),
  }));
  const gateRows = Object.entries(draft.gates?.results ?? {}).map(
    ([name, passed]) => ({
      name,
      passed,
    }),
  );
  const pendingCount = draft.events?.pending_count ?? 0;
  const comparison = draft.version_comparison;
  const verification =
    draft.schema_version === "public-research-draft-v2" &&
    draft.input_verification?.status === "SOURCE_AND_MODEL_INPUTS_MATCH" &&
    draft.input_verification.economic_approval === false
      ? draft.input_verification
      : null;
  const datedAnnualModel =
    draft.valuation.model_type === "residual_income_or_equity_value" &&
    draft.valuation.model_version === "residual-income-equity-shared-dated-v2";
  const forecastOrdinals = datedAnnualModel
    ? researchForecastOrdinals(
        draft.valuation.assumptions.map((row) => row.name),
      )
    : new Map<string, number>();
  const verifiedAnnualBasis =
    verification && datedAnnualModel ? verification.basis_date : null;

  return (
    <section
      aria-label="研究草稿（未批准）"
      style={{ maxWidth: 1120, marginTop: 24 }}
    >
      <Alert
        type="warning"
        showIcon
        message="研究草稿（未批准）"
        description="以下内容是条件性研究结果，用于审阅经济假设和证据，不替代正式研究、G3 批准或本人投资决策。"
      />

      <Descriptions
        bordered
        column={1}
        size="small"
        labelStyle={LABEL_STYLE}
        style={{ marginTop: 16 }}
        items={[
          {
            key: "status",
            label: "研究状态",
            children: <Tag color="orange">研究草稿，未获批准</Tag>,
          },
          {
            key: "version",
            label: "研究版本",
            children: draft.research_version,
          },
          { key: "cutoff", label: "研究截止", children: draft.research_as_of },
          {
            key: "period",
            label: "财务期间",
            children: draft.financial_period,
          },
          { key: "summary", label: "研究摘要", children: draft.summary },
          {
            key: "change",
            label: "旧版与新版",
            children: `${comparison.from.research_version}（${researchStatusText(comparison.from.status)}）→ ${comparison.to.research_version}（${researchStatusText(comparison.to.status)}）`,
          },
          {
            key: "changed",
            label: "本次新增",
            children:
              comparison.changed.map(researchChangeText).join("；") || "未提供",
          },
          {
            key: "unchanged",
            label: "仍未改变",
            children:
              comparison.unchanged.map(researchChangeText).join("；") ||
              "未提供",
          },
        ]}
      />

      {Object.keys(draft.financial_facts ?? {}).length > 0 && (
        <section aria-label="财务事实" style={{ marginTop: 16 }}>
          <Typography.Title level={5} style={{ fontSize: 14 }}>
            财务事实
          </Typography.Title>
          <Descriptions
            bordered
            column={1}
            size="small"
            labelStyle={{ overflowWrap: "anywhere" }}
            items={Object.entries(draft.financial_facts ?? {}).map(
              ([key, value]) => ({
                key,
                label: FINANCIAL_LABELS[key] ?? key,
                children: value ?? "未提供",
              }),
            )}
          />
        </section>
      )}

      {verification && (
        <section aria-label="财务输入溯源" style={{ marginTop: 16 }}>
          <Typography.Title level={5} style={{ fontSize: 14 }}>
            财务输入溯源
          </Typography.Title>
          <Typography.Paragraph>
            来源与模型输入一致；经济假设及估值尚未经批准。
          </Typography.Paragraph>
          <Descriptions
            bordered
            column={1}
            size="small"
            labelStyle={LABEL_STYLE}
            items={[
              {
                key: "basis",
                label: "资本基准日",
                children: verification.basis_date,
              },
              {
                key: "shares",
                label: "普通股口径",
                children:
                  verification.share_basis ===
                  "ordinary_shares_excluding_treasury"
                    ? "普通股合计（剔除库存股）"
                    : verification.share_basis === "issued_ordinary_shares"
                      ? "已发行普通股合计"
                      : "未提供有效股数口径",
              },
              {
                key: "cutoff",
                label: "证据截止时间",
                children: verification.cutoff_at,
              },
              {
                key: "computed",
                label: "计算输出时间",
                children: verification.computed_at,
              },
              {
                key: "valuation",
                label: "估值日期",
                children: draft.valuation.valuation_date,
              },
              {
                key: "inputs",
                label: "输入版本",
                children: (
                  <span title={verification.input_sha256}>
                    {shortDigest(verification.input_sha256)}
                  </span>
                ),
              },
            ]}
          />
          <List
            size="small"
            dataSource={verification.capital_inputs}
            renderItem={(input) => (
              <List.Item style={{ overflowWrap: "anywhere" }}>
                <div>
                  <Typography.Text strong>
                    {input.field === "start_book_equity" ||
                    input.field === "operating_inputs.start_book_equity"
                      ? "归母权益"
                      : input.field === "ordinary_shares" ||
                          input.field === "operating_inputs.ordinary_shares"
                        ? "普通股分母"
                        : input.field}
                    ：{input.value}{" "}
                    {input.unit === "CNY"
                      ? "元"
                      : input.unit === "shares"
                        ? "股"
                        : input.unit}
                  </Typography.Text>
                  <div>
                    期间截止 {input.period_end}；来源 {input.source_id}，第{" "}
                    {input.physical_page} 页
                  </div>
                  <div>
                    {input.normalization_rule === "SUM_COMPONENTS"
                      ? `股数组件合计：${input.component_values.join(" + ")}`
                      : input.normalization_rule === "CNY_THOUSANDS_TO_CNY"
                        ? `千元转元：${input.component_values.join("，")} 千元 × 1000`
                        : input.normalization_rule === "DIRECT"
                          ? "直接采用原始披露值"
                          : "未提供有效归一化依据"}
                  </div>
                </div>
              </List.Item>
            )}
          />
        </section>
      )}

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        条件性估值
      </Typography.Title>
      <Descriptions
        bordered
        column={1}
        size="small"
        labelStyle={LABEL_STYLE}
        items={[
          {
            key: "model",
            label: "估值模型",
            children: draft.valuation.model_version,
          },
          {
            key: "confidence",
            label: "研究置信度",
            children: researchConfidenceText(draft.valuation.confidence),
          },
          {
            key: "scope",
            label: "计算口径",
            children: draft.valuation.scope
              ? researchSentence(draft.valuation.scope)
              : "未提供",
          },
          {
            key: "validity",
            label: "模型有效性",
            children: researchStatusText(draft.model_validity.status),
          },
          {
            key: "validity_blockers",
            label: "模型有效性阻塞",
            children:
              draft.model_validity.blockers.map(researchSentence).join("；") ||
              "未提供",
          },
        ]}
      />
      <Table
        size="small"
        pagination={false}
        style={{ marginTop: 12 }}
        rowKey="scenario"
        dataSource={scenarios}
        columns={[
          {
            title: "情景",
            dataIndex: "scenario",
            render: (value: string) =>
              ({ bear: "Bear", base: "Base", bull: "Bull" })[value] ?? value,
          },
          { title: "每股权益价值（人民币）", dataIndex: "display_value" },
          {
            title: "终端剩余收益贡献",
            dataIndex: "terminal_residual_contribution_ratio",
            render: (value?: string) => value || "未提供",
          },
        ]}
      />

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        关键假设
      </Typography.Title>
      <List
        size="small"
        bordered
        dataSource={draft.valuation.assumptions}
        renderItem={(row: ResearchDraftAssumption) => (
          <List.Item style={{ overflowWrap: "anywhere" }}>
            <div>
              <Typography.Text strong>
                {researchAssumptionName(row.name, {
                  ordinal: forecastOrdinals.get(row.name) ?? 0,
                  verifiedAnnualBasis,
                })}
              </Typography.Text>
              <div>
                Bear {String(row.bear ?? "未提供")} / Base{" "}
                {String(row.base ?? "未提供")} / Bull{" "}
                {String(row.bull ?? "未提供")}
              </div>
              <Typography.Text type="secondary">
                {researchSentence(row.rationale || row.basis || "未提供依据")}
              </Typography.Text>
            </div>
          </List.Item>
        )}
      />

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        报价事实与价格桥
      </Typography.Title>
      <Descriptions
        bordered
        column={1}
        size="small"
        labelStyle={LABEL_STYLE}
        items={[
          {
            key: "quote",
            label: "已核验收盘价（未准入）",
            children: `${draft.quote_fact.current_price} ${draft.quote_fact.currency}，${draft.quote_fact.quote_date}`,
          },
          {
            key: "bridge",
            label: "价格桥",
            children: researchStatusText(draft.price_bridge.status),
          },
          { key: "admitted", label: "价格准入", children: "否" },
          {
            key: "reason",
            label: "拒绝比较原因",
            children: draft.price_bridge.reason || "未提供",
          },
          {
            key: "needed",
            label: "重开所需证据",
            children: draft.price_bridge.needed_evidence || "未提供",
          },
        ]}
      />

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        研究门与重大事件
      </Typography.Title>
      <Descriptions
        bordered
        column={1}
        size="small"
        labelStyle={LABEL_STYLE}
        items={[
          {
            key: "gates",
            label: "研究门",
            children: gateRows.length
              ? gateRows
                  .map(
                    (row) =>
                      `${researchGateText(row.name)}：${row.passed ? "通过" : "未通过"}`,
                  )
                  .join("；")
              : "未提供",
          },
          {
            key: "events",
            label: "重大事件",
            children: `状态 ${researchStatusText(draft.events?.status)}；覆盖情况 ${researchStatusText(draft.events?.coverage_status)}；待人工复核 ${pendingCount} 项`,
          },
        ]}
      />
      <List
        size="small"
        bordered
        dataSource={draft.events?.items ?? []}
        renderItem={(event) => (
          <List.Item style={{ overflowWrap: "anywhere" }}>
            <div>
              <div>{event.title || event.announcement_id || "未命名公告"}</div>
              <Typography.Text type="secondary">
                {event.published_at || "时间未提供"} ·{" "}
                {researchStatusText(event.review_status)}
              </Typography.Text>
              <div>{evidenceLocation(event.source_url)}</div>
            </div>
          </List.Item>
        )}
      />

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        反证、失效与重开条件
      </Typography.Title>
      <Typography.Text strong>反证</Typography.Text>
      <ListOrEmpty
        items={draft.counter_evidence.map(researchSentence)}
        empty="未提供反证"
      />
      <Typography.Text strong>论点失效条件</Typography.Text>
      <ListOrEmpty
        items={draft.thesis_breakers.map(researchSentence)}
        empty="未提供失效条件"
      />
      <Typography.Text strong>重开与复核条件</Typography.Text>
      <ListOrEmpty
        items={draft.reopen_triggers.map(researchSentence)}
        empty="未提供重开条件"
      />

      <Typography.Title level={5} style={{ fontSize: 14, marginTop: 20 }}>
        证据与限制
      </Typography.Title>
      <List
        size="small"
        bordered
        dataSource={draft.evidence}
        renderItem={(evidence) => (
          <List.Item style={{ overflowWrap: "anywhere" }}>
            <div>
              <Typography.Text strong>
                {evidence.title || evidence.id}
              </Typography.Text>
              <div>{evidenceLocation(evidence.url)}</div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                SHA-256 {shortDigest(evidence.sha256) || "未提供"}
              </Typography.Text>
            </div>
          </List.Item>
        )}
      />
      <ListOrEmpty
        items={draft.limitations.map(researchSentence)}
        empty="未提供研究限制"
      />
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="正式研究仍待完成"
        description={draft.boundary}
      />
    </section>
  );
}
