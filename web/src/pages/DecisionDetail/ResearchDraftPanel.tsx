import { Alert, Descriptions, List, Table, Tag, Typography } from "antd";
import type {
  ResearchDraft,
  ResearchOnlyDraft,
  ValuationResearchDraft,
  ResearchDraftAssumption,
} from "../../types/api";
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
  if (draft.schema_version === "public-research-only-draft-v1") {
    return <ResearchOnlyDraftPanel draft={draft} />;
  }
  if (
    draft.schema_version !== "public-research-draft-v1" &&
    draft.schema_version !== "public-research-draft-v2"
  ) {
    return <Alert type="warning" message="无法核验研究草稿版本" />;
  }
  return <ValuationResearchDraftPanel draft={draft} />;
}

const OBSERVATION_LABELS: Record<string, string> = {
  operating_cash_flow: "经营活动现金净额",
  reported_asset_purchase_cash: "购建资产支付现金（非完整资本开支）",
  investing_cash_flow: "投资活动现金净额",
  financing_cash_flow: "筹资活动现金净额",
  combined_distributions_and_interest_paid:
    "分配股利、利润或偿付利息支付现金（合并项）",
};
const TOPIC_LABELS: Record<string, string> = {
  CASH_CONVERSION: "现金转换",
  CONCESSION: "特许经营",
  CAPEX: "资本开支",
  FINANCING: "融资与偿债",
  DIVIDEND: "分红能力",
};
const RESEARCH_ONLY_BLOCKERS: Record<string, string> = {
  MODEL_APPLICABILITY_UNASSESSED_RESEARCH_ONLY:
    "尚未选定适用估值模型，不能给出合理价值或交易判断。",
  NORMALIZED_CASH_AND_REINVESTMENT_NOT_RECONCILED:
    "正常化现金与再投资义务尚未核清。",
  RESTATED_H1_COMPARATIVES_REQUIRE_SCOPE_RECONCILIATION:
    "半年报比较数据存在重述，不能未经口径核对直接拼接 TTM。",
  UNVERIFIED_PROVIDER_TRADE_DATE: "初筛行情交易日期尚未核验，未用于价格判断。",
  BSE_COVERAGE_MISSING: "本次初筛未覆盖北交所，不代表全市场覆盖。",
  NO_HUMAN_ECONOMIC_APPROVAL: "尚未完成经济研究人工准入。",
};

function ResearchOnlyDraftPanel({ draft }: { draft: ResearchOnlyDraft }) {
  const verification = draft.input_verification;
  // This checks display-contract integrity, not authenticity of original files.
  const sha256 = (value: unknown) =>
    typeof value === "string" &&
    value.length === 64 &&
    /^[0-9a-f]{64}$/.test(value);
  const evidenceIds = new Set<string>();
  const evidenceValid =
    Array.isArray(draft.evidence) &&
    draft.evidence.length > 0 &&
    draft.evidence.every((ref) => {
      if (
        !ref ||
        typeof ref.id !== "string" ||
        !ref.id.trim() ||
        ref.id !== ref.id.trim() ||
        !sha256(ref.sha256) ||
        evidenceIds.has(ref.id)
      )
        return false;
      evidenceIds.add(ref.id);
      return true;
    });
  const observationRefsValid =
    Array.isArray(draft.observations) &&
    draft.observations.every(
      (row) =>
        row &&
        Array.isArray(row.evidence_refs) &&
        row.evidence_refs.length > 0 &&
        new Set(row.evidence_refs).size === row.evidence_refs.length &&
        row.evidence_refs.every(
          (id) => typeof id === "string" && evidenceIds.has(id),
        ),
    );
  if (
    draft.action !== "no_order" ||
    draft.research_mode !== "research_only_v1" ||
    draft.status !== "RESEARCH_DRAFT_NOT_APPROVED" ||
    draft.assessment_status !== "UNASSESSABLE" ||
    draft.native_status !== "UNSUPPORTED" ||
    draft.observations_verified !== false ||
    draft.confidence !== "LOW" ||
    verification?.status !== "SOURCE_INPUTS_MATCH_NO_VALUATION" ||
    verification.economic_approval !== false ||
    verification.source_contract_status !==
      "SOURCE_CUTOFF_VALIDATED_NO_SCENARIOS_OR_FACT_ADMISSION" ||
    verification.input_sha256 !== draft.research_input_binding?.input_sha256 ||
    !sha256(verification.input_sha256) ||
    !sha256(draft.research_input_binding?.input_sha256) ||
    !sha256(draft.research_input_binding?.package?.sha256) ||
    !evidenceValid ||
    !observationRefsValid ||
    [
      draft.valuation,
      draft.model_validity,
      draft.quote_fact,
      draft.price_bridge,
      draft.gates,
    ].some((v) => v !== null) ||
    !Array.isArray(draft.observations) ||
    !Array.isArray(draft.evidence) ||
    !Array.isArray(draft.research_topics)
  ) {
    return <Alert type="warning" message="研究草稿不可核验，未展示观测数值" />;
  }
  return (
    <section style={{ minWidth: 0, overflowWrap: "anywhere" }}>
      <Typography.Title level={4}>
        {draft.company_name} · 初步研究
      </Typography.Title>
      <Alert
        type="warning"
        message="模型尚未适用 · 资料不足（UNASSESSABLE）"
        description={draft.summary}
      />
      <p>
        <Tag>官方原文观测 · 未准入</Tag>
        <Tag>低置信度</Tag>
        <Tag>非买卖建议</Tag>
      </p>
      <Descriptions
        column={1}
        size="small"
        items={[
          {
            key: "period",
            label: "财务期间",
            children: draft.financial_period,
          },
          {
            key: "research",
            label: "研究日期",
            children: draft.research_as_of,
          },
          {
            key: "cutoff",
            label: "知识截止",
            children: verification.cutoff_at,
          },
          {
            key: "available",
            label: "草稿可得时间",
            children: draft.available_at,
          },
          {
            key: "version",
            label: "研究版本",
            children: draft.research_version,
          },
        ]}
      />
      <Typography.Title level={5}>研究逻辑与待核问题</Typography.Title>
      <Typography.Paragraph>{draft.thesis}</Typography.Paragraph>
      <Typography.Paragraph>
        回报来源：{draft.return_driver}
      </Typography.Paragraph>
      <Typography.Paragraph>
        误定价假设：{draft.mispricing_hypothesis}
      </Typography.Paragraph>
      {draft.research_topics.map((topic) => (
        <div key={topic.id}>
          <Typography.Text strong>
            {TOPIC_LABELS[topic.id] ?? topic.id}
          </Typography.Text>
          <Typography.Paragraph>{topic.explanation}</Typography.Paragraph>
          <ul>
            {topic.missing.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
          <Typography.Text type="secondary">
            依据：{topic.evidence_refs.join("、")}
          </Typography.Text>
        </div>
      ))}
      <Typography.Title level={5}>
        报表观测（不是标准化自由现金流）
      </Typography.Title>
      <div style={{ maxWidth: "100%", overflowX: "auto" }}>
        <table
          style={{ width: "100%", minWidth: 560, borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              {[
                "项目 / 口径",
                "期间 / 原值",
                "比较期间 / 原值",
                "原文依据",
              ].map((t) => (
                <th key={t} style={{ textAlign: "left", padding: 8 }}>
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {draft.observations.map((row, i) => (
              <tr key={i}>
                <td style={{ padding: 8 }}>
                  {OBSERVATION_LABELS[row.field_name] ?? row.field_name}
                  <br />
                  {row.statement_scope === "consolidated"
                    ? "合并口径"
                    : (row.statement_scope ?? "口径待核")}{" "}
                  · {row.unit ?? "单位待核"}
                </td>
                <td style={{ padding: 8 }}>
                  {row.period_label ?? "期间待核"}
                  <br />
                  {row.value ?? "缺失（不补零）"}
                </td>
                <td style={{ padding: 8 }}>
                  {row.prior_period_label ?? "比较期待核"}
                  <br />
                  {row.prior_value ?? "缺失（不补零）"}
                </td>
                <td style={{ padding: 8 }}>{row.evidence_refs.join("、")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Typography.Title level={5}>反证与未完成事项</Typography.Title>
      <ul>
        {draft.counter_evidence.map((row, i) => (
          <li key={i}>
            {typeof row === "string" ? (
              row
            ) : (
              <>
                {row.text}
                {row.evidence_refs?.length ? (
                  <div>依据：{row.evidence_refs.join("、")}</div>
                ) : null}
              </>
            )}
          </li>
        ))}
      </ul>
      <ul>
        {draft.blockers.map((text, i) => (
          <li key={i}>{RESEARCH_ONLY_BLOCKERS[text] ?? text}</li>
        ))}
      </ul>
      <Typography.Title level={5}>原始出处</Typography.Title>
      <ul>
        {draft.evidence.map((ref) => (
          <li key={ref.id}>
            {httpUrl(ref.url) ? (
              <a href={ref.url!} target="_blank" rel="noreferrer">
                {ref.title ?? ref.id}
              </a>
            ) : (
              ref.id
            )}{" "}
            第{ref.physical_page ?? ref.page ?? "待核"}页
            <div>
              发布：{ref.published_at ?? ref.published_date ?? "日期待核"}
              ；实际取得：{ref.retrieved_at}；可得：{ref.available_at}
            </div>
            <div>SHA-256：{ref.sha256}</div>
            {ref.excerpt && <div>{ref.excerpt}</div>}
          </li>
        ))}
      </ul>
      <Typography.Paragraph>{draft.boundary}</Typography.Paragraph>
    </section>
  );
}

function ValuationResearchDraftPanel({
  draft,
}: {
  draft: ValuationResearchDraft;
}) {
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
