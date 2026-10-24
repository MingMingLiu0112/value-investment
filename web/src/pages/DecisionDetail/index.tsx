import { useParams, Link } from "@umijs/max";
import { CurrentHolding } from "./CurrentHolding";
import { ResearchDraftPanel } from "./ResearchDraftPanel";
import { AgentResearchPanel } from "./AgentResearchPanel";
import { useCallback } from "react";
import type { PropsWithChildren } from "react";
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  List,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { DetailSection } from "../../components/DetailSection";
import {
  CurrentJudgmentChart,
  JudgmentSummary,
} from "../../components/CurrentJudgment";
import { fillLink } from "../../utils/currentJudgment";
import { statusLabel } from "../../utils/presentation";
import { codeText, strategyText } from "../../utils/codes";
import {
  firstResearchText,
  publicBlockerText,
} from "../../utils/opportunityView";
import { shortDigest } from "../../utils/history";
import {
  bridgeExecutionView,
  formatScenarioValue,
  gateRowViews,
  marginText,
  nextActionLines,
  normalizeEvidenceLines,
  researchHeadline,
  splitReadingOrder,
  suggestedStateText,
  uniqueBlockerTexts,
  unknownText,
  type EvidenceLine,
  type GateView,
} from "../../utils/researchDetail";
import type {
  DecisionItem,
  ResearchDetail,
  ResearchEvidenceRef,
  ResearchModelValidity,
  ResearchPrice,
  ResearchStatusSummary,
  ResearchSuggestedState,
  ResearchValuation,
  ResearchValuationProvenance,
} from "../../types/api";

const READING_ORDER_PREVIEW = 8;

function Section({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <section style={{ marginTop: 24 }}>
      <Typography.Title level={4} style={{ fontSize: 16 }}>
        {title}
      </Typography.Title>
      {children}
    </section>
  );
}

function SubTitle({ children }: PropsWithChildren) {
  return (
    <Typography.Title level={5} style={{ fontSize: 14, marginTop: 16 }}>
      {children}
    </Typography.Title>
  );
}

function TextLine({
  value,
  empty = "未提供",
}: {
  value?: string | null;
  empty?: string;
}) {
  return (
    <Typography.Text
      style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
    >
      {value || empty}
    </Typography.Text>
  );
}

function BulletList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length)
    return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

function EvidenceList({
  items,
  empty,
}: {
  items: EvidenceLine[];
  empty: string;
}) {
  if (!items.length) return <Alert type="info" showIcon message={empty} />;
  return (
    <List
      size="small"
      bordered
      dataSource={items}
      renderItem={(item) => (
        <List.Item style={{ overflowWrap: "anywhere" }}>
          <div>
            <div>{item.text}</div>
            {item.evidenceRefs.length > 0 && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                证据：{item.evidenceRefs.join("、")}
              </Typography.Text>
            )}
          </div>
        </List.Item>
      )}
    />
  );
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function gateStatusColor(view: GateView): string | undefined {
  if (view.status === "PASS") return "green";
  if (view.status === "BLOCKED") return "red";
  if (view.status === "CONDITIONAL") return "orange";
  return undefined;
}

function LegacyDecision({ decision }: { decision: DecisionItem }) {
  return (
    <>
      <Descriptions
        bordered
        column={1}
        style={{ marginTop: 24 }}
        items={[
          {
            key: "strategy",
            label: "策略",
            children: decision.strategy || "未提供",
          },
          {
            key: "action",
            label: "复核动作",
            children: statusLabel(decision.candidate_action),
          },
          {
            key: "date",
            label: "研究日期",
            children: decision.as_of || "未提供",
          },
          { key: "id", label: "决策 ID", children: decision.id },
        ]}
      />
      <DetailSection title="支持证据" value={decision.support} />
      <DetailSection title="反方分析" value={decision.counter_evidence} />
      <DetailSection title="价格与估值上下文" value={decision.price_context} />
      <DetailSection
        title="下一批事件与复核条件"
        value={decision.next_events}
      />
      <DetailSection title="失效条件" value={decision.thesis_breakers} />
      <DetailSection title="当前阻塞" value={decision.blockers} />
    </>
  );
}

function ResearchDecision({
  decision,
  research,
}: {
  decision: DecisionItem;
  research: ResearchDetail;
}) {
  const researchStatus = (research.research_status ??
    {}) as Partial<ResearchStatusSummary>;
  const valuation = (research.valuation ?? {}) as Partial<ResearchValuation>;
  const validity = (research.model_validity ??
    {}) as Partial<ResearchModelValidity>;
  const price = (research.price ?? {}) as Partial<ResearchPrice>;
  const bridge = bridgeExecutionView(research.price_bridge_execution);
  const state = (research.suggested_state ??
    {}) as Partial<ResearchSuggestedState>;
  const provenance = (research.valuation_provenance ??
    {}) as Partial<ResearchValuationProvenance>;
  const binding = research.research_binding ?? {
    status: "NOT_BOUND",
    path: null,
    sha256: null,
  };

  const gates = gateRowViews(research.gates);
  const reading = splitReadingOrder(
    research.reading_order,
    READING_ORDER_PREVIEW,
  );

  const supportLines = normalizeEvidenceLines(decision.support);
  const counterLines = normalizeEvidenceLines(decision.counter_evidence);
  const breakerLines = normalizeEvidenceLines(decision.thesis_breakers);
  const nextEventLines = normalizeEvidenceLines(research.next_events);

  const priceBlockers = asStringList(price.blockers);
  const currentPrice = price.current_price ?? null;
  const hasPrice = currentPrice !== null && String(currentPrice).trim() !== "";
  const marginBase = marginText(
    research.margin_to_base ?? price.margin_to_base,
  );
  const marginBear = marginText(
    research.margin_to_bear ?? price.margin_to_bear,
  );

  const blockers = uniqueBlockerTexts(asStringList(research.blockers));
  const exitConditions = asStringList(research.exit_conditions);
  const reopenTriggers = asStringList(research.reopen_triggers);
  const evidenceRefs = Array.isArray(research.evidence_refs)
    ? research.evidence_refs
    : [];

  const scenarioRows = [
    {
      key: "bear",
      label: "保守（Bear）",
      value: formatScenarioValue(valuation.bear),
    },
    {
      key: "base",
      label: "基准（Base）",
      value: formatScenarioValue(valuation.base),
    },
    {
      key: "bull",
      label: "乐观（Bull）",
      value: formatScenarioValue(valuation.bull),
    },
  ];

  const reviewMark =
    state.human_review_required === true
      ? "系统标记需要人工复核"
      : state.human_review_required === false
        ? "系统未标记人工复核要求，仍以人工复核为准"
        : "人工复核标记未提供";

  const headline = researchHeadline({
    valuation,
    bridge,
    researchDay: research.decision_cutoff,
    marginToBase: marginBase,
  });
  const nextSteps = nextActionLines(gates, bridge?.nextStep);

  return (
    <>
      <Section title="一句话研究结论">
        <Alert
          type="info"
          showIcon
          message={headline}
          description={
            (state.value ? suggestedStateText(state.value) + "。" : "") +
            (state.boundary ||
              "研究状态不等于买卖信号；系统只输出待人工复核的候选，不下单。")
          }
        />
      </Section>

      <Section title="研究结论与数据日期">
        <Descriptions
          bordered
          column={1}
          size="small"
          items={[
            {
              key: "company",
              label: "公司",
              children:
                research.company_name ||
                decision.name ||
                decision.symbol ||
                "未提供",
            },
            {
              key: "status",
              label: "研究状态",
              children: researchStatus.label || researchStatus.code || "未提供",
            },
            {
              key: "cutoff",
              label: "决策截止日",
              children: research.decision_cutoff || "未提供",
            },
            {
              key: "version",
              label: "研究版本",
              children: research.research_version || "未提供",
            },
            {
              key: "source",
              label: "估值来源版本",
              children: research.source_version || "未提供",
            },
            {
              key: "period",
              label: "财务期间",
              children: researchStatus.financial_period || "未提供",
            },
          ]}
        />
      </Section>

      <Section title="公司投资逻辑">
        {research.thesis ||
        research.return_driver ||
        research.mispricing_hypothesis ? (
          <Descriptions
            bordered
            column={1}
            size="small"
            labelStyle={{ whiteSpace: "nowrap" }}
            items={[
              ...(research.thesis
                ? [
                    {
                      key: "thesis",
                      label: "研究论点",
                      children: <TextLine value={research.thesis} />,
                    },
                  ]
                : []),
              ...(research.return_driver
                ? [
                    {
                      key: "driver",
                      label: "回报来源",
                      children: <TextLine value={research.return_driver} />,
                    },
                  ]
                : []),
              ...(research.mispricing_hypothesis
                ? [
                    {
                      key: "mispricing",
                      label: "错价假设",
                      children: (
                        <TextLine value={research.mispricing_hypothesis} />
                      ),
                    },
                  ]
                : []),
            ]}
          />
        ) : null}
        <SubTitle>支撑逻辑</SubTitle>
        <EvidenceList
          items={supportLines}
          empty="后端尚未提供可核验的支撑逻辑"
        />
        <SubTitle>关键反证</SubTitle>
        <EvidenceList
          items={counterLines}
          empty="后端尚未提供可核验的关键反证"
        />
      </Section>

      <Section title="估值区间与适用模型">
        <Descriptions
          bordered
          column={1}
          size="small"
          items={[
            {
              key: "model",
              label: "适用模型",
              children:
                valuation.model_type || research.valuation_model || "未提供",
            },
            {
              key: "model_version",
              label: "模型版本",
              children: valuation.model_version || "未提供",
            },
            {
              key: "valuation_date",
              label: "估值基准日",
              children: valuation.valuation_date || "未提供",
            },
            {
              key: "confidence",
              label: "置信度",
              children:
                valuation.confidence ||
                research.valuation_confidence ||
                "未提供",
            },
            {
              key: "status",
              label: "估值状态",
              children: valuation.status || "未提供",
            },
          ]}
        />
        <Table
          size="small"
          rowKey="key"
          pagination={false}
          dataSource={scenarioRows}
          columns={[
            { title: "情景", dataIndex: "label", width: 160 },
            {
              title: valuation.currency
                ? `每股价值（${valuation.currency}）`
                : "每股价值",
              dataIndex: "value",
            },
          ]}
        />
        {valuation.scope ? (
          <Typography.Paragraph
            type="secondary"
            style={{ marginTop: 12, whiteSpace: "pre-wrap" }}
          >
            {valuation.scope}
          </Typography.Paragraph>
        ) : null}
      </Section>

      <Section title="价格与估值的关系">
        {hasPrice ? (
          <Descriptions
            bordered
            column={1}
            size="small"
            items={[
              {
                key: "price",
                label: "当前价格",
                children: String(currentPrice),
              },
              {
                key: "price_as_of",
                label: "价格日期",
                children: price.price_as_of || research.price_as_of || "未提供",
              },
              ...(price.attractiveness_label
                ? [
                    {
                      key: "attractiveness",
                      label: "价格吸引力",
                      children: price.attractiveness_label,
                    },
                  ]
                : []),
            ]}
          />
        ) : (
          <Alert
            type="info"
            showIcon
            message="暂不可评估"
            description={
              <div>
                <div>原因：{price.unavailable_reason || "未提供"}</div>
                <div>需要补充：{price.needed_evidence || "未提供"}</div>
              </div>
            }
          />
        )}
        {(marginBase !== null || marginBear !== null) && (
          <Descriptions
            bordered
            column={1}
            size="small"
            style={{ marginTop: 12 }}
            items={[
              ...(marginBase !== null
                ? [
                    {
                      key: "margin_base",
                      label: "相对 Base",
                      children: marginBase,
                    },
                  ]
                : []),
              ...(marginBear !== null
                ? [
                    {
                      key: "margin_bear",
                      label: "相对 Bear",
                      children: marginBear,
                    },
                  ]
                : []),
            ]}
          />
        )}
        <SubTitle>价格阻塞</SubTitle>
        <BulletList items={priceBlockers} empty="未提供价格阻塞说明" />
      </Section>

      <Section title="价格桥接执行（已登记收盘行情）">
        {bridge ? (
          <>
            <Descriptions
              bordered
              column={1}
              size="small"
              items={[
                {
                  key: "bridge_status",
                  label: "价格桥接状态",
                  children: bridge.statusLabel,
                },
                {
                  key: "comparable",
                  label: "当前价格是否具备比较资格",
                  children: bridge.comparableLabel,
                },
                ...bridge.rows.map((row) => ({
                  key: row.key,
                  label: row.label,
                  children: row.value,
                })),
              ]}
            />
            {bridge.reason ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 12 }}
                message={bridge.reason}
                description={
                  bridge.nextStep ? (
                    <div>重开条件：{bridge.nextStep}</div>
                  ) : null
                }
              />
            ) : null}
            {bridge.ladder.length > 0 && (
              <>
                <SubTitle>比较资格阶梯（逐级判定，互不替代）</SubTitle>
                <Descriptions
                  bordered
                  column={1}
                  size="small"
                  items={bridge.ladder.map((row) => ({
                    key: `ladder_${row.key}`,
                    label: row.label,
                    children: (
                      <span>
                        {row.eligible ? "通过" : "未通过"}
                        {row.reason ? `：${row.reason}` : ""}
                      </span>
                    ),
                  }))}
                />
              </>
            )}
            {bridge.sources.length > 0 && (
              <>
                <SubTitle>行情来源（双源已归档）</SubTitle>
                <List
                  size="small"
                  bordered
                  dataSource={bridge.sources}
                  renderItem={(row) => (
                    <List.Item style={{ overflowWrap: "anywhere" }}>
                      <div>
                        <div>
                          <Typography.Link
                            href={row.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {row.label}
                          </Typography.Link>
                        </div>
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 12 }}
                        >
                          SHA-256 {shortDigest(row.sha256) ?? "未提供"}
                        </Typography.Text>
                      </div>
                    </List.Item>
                  )}
                />
              </>
            )}
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            message="尚未登记当前收盘行情绑定"
            description="没有已登记的收盘行情，因此本次没有可执行的价格桥接结果；价格与估值的关系保持暂停。"
          />
        )}
      </Section>

      <Section title="当前缺失的证据与门禁">
        <Table<GateView>
          size="small"
          rowKey="key"
          pagination={false}
          dataSource={gates}
          scroll={{ x: 720 }}
          columns={[
            { title: "门禁", dataIndex: "label", width: 120 },
            {
              title: "状态",
              dataIndex: "statusLabel",
              width: 96,
              render: (value: string, view) => (
                <Tag color={gateStatusColor(view)}>{value}</Tag>
              ),
            },
            {
              title: "原因",
              dataIndex: "reason",
              render: (value: string | null) => value || "未提供",
            },
            {
              title: "下一步",
              dataIndex: "nextAction",
              render: (value: string | null) => value || "未提供",
            },
          ]}
        />
      </Section>

      <Section title="行动状态与变化条件">
        <Alert
          type="info"
          showIcon
          message={suggestedStateText(state.value)}
          description={[
            reviewMark,
            state.boundary ||
              "研究状态不等于买卖信号；系统只输出待人工复核的候选，不下单。",
          ].join("。")}
        />
        <SubTitle>候选说明</SubTitle>
        <TextLine
          value={research.candidate_explanation}
          empty="后端尚未提供候选说明"
        />
        <SubTitle>当前阻塞</SubTitle>
        <BulletList items={blockers} empty="后端未提供阻塞列表" />
        <SubTitle>研究底稿阅读顺序（前 {READING_ORDER_PREVIEW} 条）</SubTitle>
        {reading.leading.length ? (
          <List
            size="small"
            bordered
            dataSource={reading.leading}
            renderItem={(row) => (
              <List.Item style={{ overflowWrap: "anywhere" }}>
                <Typography.Text strong>{row.label}</Typography.Text>：
                {row.value}
              </List.Item>
            )}
          />
        ) : (
          <Typography.Text type="secondary">
            后端未提供底稿阅读顺序
          </Typography.Text>
        )}
      </Section>

      <Section title="风险与失效条件">
        <SubTitle>论点失效条件</SubTitle>
        <EvidenceList items={breakerLines} empty="后端尚未提供失效条件" />
        <SubTitle>退出条件</SubTitle>
        <BulletList items={exitConditions} empty="后端尚未提供退出条件" />
        <SubTitle>重开与复核触发</SubTitle>
        <BulletList items={reopenTriggers} empty="后端尚未提供重开触发" />
        <SubTitle>下一批事件</SubTitle>
        <EvidenceList items={nextEventLines} empty="后端尚未提供下一批事件" />
      </Section>

      <Section title="下一步怎么做">
        <BulletList
          items={nextSteps}
          empty="当前没有需要你处理的步骤；继续按重开与复核触发条件观察。"
        />
      </Section>

      <Section title="官方证据与历史版本入口">
        {evidenceRefs.length ? (
          <List
            size="small"
            bordered
            dataSource={evidenceRefs}
            renderItem={(ref: ResearchEvidenceRef) => (
              <List.Item style={{ overflowWrap: "anywhere" }}>
                <div>
                  <div>
                    <Typography.Text strong>
                      {ref.id || "未提供编号"}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {" "}
                      SHA-256 {shortDigest(ref.sha256) ?? "未提供"}
                    </Typography.Text>
                  </div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    文件位于本地 runtime 归档：{ref.path || "未提供路径"}
                  </Typography.Text>
                </div>
              </List.Item>
            )}
          />
        ) : (
          <Alert type="info" showIcon message="后端未提供官方证据引用" />
        )}
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          研究版本与决策截止日见上方；完整历史版本对比见页面底部的历史判断入口。
        </Typography.Paragraph>
      </Section>

      <Collapse
        ghost
        style={{ marginTop: 24 }}
        items={[
          {
            key: "technical",
            label: <Typography.Text strong>技术详情</Typography.Text>,
            children: (
              <>
                <Descriptions
                  bordered
                  column={1}
                  size="small"
                  items={[
                    {
                      key: "research_version",
                      label: "research_version",
                      children: research.research_version || "未提供",
                    },
                    {
                      key: "decision_cutoff",
                      label: "decision_cutoff",
                      children: research.decision_cutoff || "未提供",
                    },
                    {
                      key: "binding_status",
                      label: "research_binding.status",
                      children: binding.status || "未提供",
                    },
                    {
                      key: "binding_path",
                      label: "research_binding.path",
                      children: binding.path || "未提供",
                    },
                    {
                      key: "binding_sha",
                      label: "research_binding.sha256",
                      children: binding.sha256 || "未提供",
                    },
                    {
                      key: "model_validity",
                      label: "model_validity.status",
                      children: validity.status || "未提供",
                    },
                    {
                      key: "portfolio_input",
                      label: "portfolio_input_status",
                      children: research.portfolio_input_status || "未提供",
                    },
                    {
                      key: "position_guidance",
                      label: "position_guidance",
                      children: unknownText(research.position_guidance),
                    },
                    {
                      key: "quote_admission",
                      label: "quote_admission_status",
                      children:
                        research.quote_admission_status ||
                        price.quote_admission_status ||
                        "未提供",
                    },
                    {
                      key: "bound_decision",
                      label: "valuation_provenance.bound_decision",
                      children: provenance.bound_decision || "未提供",
                    },
                    {
                      key: "bound_version",
                      label: "valuation_provenance.bound_research_version",
                      children: provenance.bound_research_version || "未提供",
                    },
                    {
                      key: "registered_note",
                      label: "valuation_provenance.registered_research_note",
                      children: provenance.registered_research_note || "未提供",
                    },
                  ]}
                />
                <SubTitle>原始门禁键与状态码</SubTitle>
                <BulletList
                  items={gates.map(
                    (view) => `${view.key} — ${view.status ?? "未提供"}`,
                  )}
                  empty="未提供门禁记录"
                />
                <SubTitle>
                  底稿阅读顺序（其余 {reading.trailing.length} 条）
                </SubTitle>
                {reading.trailing.length ? (
                  <List
                    size="small"
                    bordered
                    dataSource={reading.trailing}
                    renderItem={(row) => (
                      <List.Item style={{ overflowWrap: "anywhere" }}>
                        <Typography.Text strong>{row.label}</Typography.Text>：
                        {row.value}
                      </List.Item>
                    )}
                  />
                ) : (
                  <Typography.Text type="secondary">
                    没有更多底稿行
                  </Typography.Text>
                )}
              </>
            ),
          },
        ]}
      />
    </>
  );
}

export default function DecisionDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const load = useCallback(
    (signal: AbortSignal) => api.detail(id, signal),
    [id],
  );
  const { data, loading, error, retry } = useApi(load);
  const packet = useApi(api.packet);
  const decision = data?.decision;
  const progress = data?.financial_progress;
  const replay = data?.review_replay;
  const verifiedProgress =
    progress?.status === "VERIFIED_FACT_ADOPTION" &&
    progress.action === "no_order" &&
    progress.formal_eligibility === false &&
    progress.symbol === decision?.symbol &&
    progress.research_inputs_updated === true &&
    Number.isSafeInteger(progress.adopted_fact_count) &&
    progress.adopted_fact_count > 0 &&
    [progress.quality_coverage_before, progress.quality_coverage_after].every(
      (value) =>
        typeof value === "string" &&
        value.trim() !== "" &&
        Number.isFinite(Number(value)) &&
        Number(value) >= 0 &&
        Number(value) <= 1,
    );
  const research = decision?.research ?? null;
  const chain =
    packet.data?.publication_id &&
    packet.data.publication_id === data?.publication?.publication_id
      ? packet.data.company_statuses?.[decision?.symbol ?? ""]?.decision_chain
      : undefined;
  return (
    <Workbench>
      <Typography.Title level={2}>股票操作计划</Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        {!decision ? (
          <Alert
            type="info"
            showIcon
            message="暂无可核验的操作逻辑"
            description={data?.reason || data?.status || "未找到该决策"}
          />
        ) : (
          <>
            <Typography.Title level={3}>
              {String(decision.name || decision.symbol || decision.id)}{" "}
              {decision.name && decision.symbol}
            </Typography.Title>
            {chain?.research_conclusion?.evidence_verified &&
              chain.research_conclusion.summary && (
                <Alert
                  type="warning"
                  showIcon
                  message="当前研究判断（不构成投资批准）"
                  description={chain.research_conclusion.summary}
                  style={{ marginTop: 12 }}
                />
              )}
            {verifiedProgress && progress && (
              <Typography.Paragraph role="status">
                财务补证已回流研究：已核验采纳 {progress.adopted_fact_count}{" "}
                个派生事实，财务覆盖从{" "}
                {(Number(progress.quality_coverage_before) * 100).toFixed(1)}%
                到 {(Number(progress.quality_coverage_after) * 100).toFixed(1)}
                %。 这是财务输入更新；估值、事件审核和投资资格仍独立核验。
                {Array.isArray(progress.adopted_metrics) &&
                  progress.adopted_metrics
                    .filter(
                      (metric) =>
                        [
                          "debt_ratio",
                          "revenue_yoy",
                          "net_income_yoy",
                        ].includes(metric.field_name) &&
                        metric.unit === "percent" &&
                        typeof metric.value === "string" &&
                        metric.value.trim() !== "" &&
                        Number.isFinite(Number(metric.value)) &&
                        /^\d{4}-12-31$/.test(metric.period_label),
                    )
                    .map((metric) => (
                      <span
                        key={`${metric.field_name}-${metric.period_label}`}
                        style={{ display: "block" }}
                      >
                        {metric.period_label} ·{" "}
                        {
                          {
                            debt_ratio: "资产负债率",
                            revenue_yoy: "营业收入同比",
                            net_income_yoy: "归母净利润同比",
                          }[metric.field_name]
                        }
                        ：{Number(metric.value).toFixed(2)}%
                      </span>
                    ))}
              </Typography.Paragraph>
            )}
            {(replay?.status === "VERIFIED_EXACT_INPUT_REPLAY" ||
              replay?.status === "VERIFIED_NEW_INPUT_CANDIDATE") &&
              replay.symbol === decision.symbol &&
              replay.action === "no_order" &&
              replay.formal_eligibility === false &&
              replay.approval_changed === false &&
              replay.research_admitted === false &&
              replay.price_admitted === false &&
              replay.scope === "UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY" && (
                <Typography.Paragraph role="status">
                  {replay.status === "VERIFIED_NEW_INPUT_CANDIDATE"
                    ? "新来源版本已完成研究消费，可办理精确版本审核；研究日为 "
                    : "原研究已按当前程序核验重放，研究日仍为 "}
                  {replay.research_as_of}
                  {replay.valuation_basis_scope ===
                    "EX_POST_PRIOR_COMPLETED_SESSION" &&
                    replay.valuation_basis_date && (
                      <>
                        ；估值基准为 {replay.valuation_basis_date}
                        收盘，属事后估计，不代表当前行情有效
                      </>
                    )}
                  ；未获经济或买卖批准。{" "}
                  <a href="#value-review-handoff">
                    查看有权审核人的材料与签署路径
                  </a>
                </Typography.Paragraph>
              )}
            {replay?.status === "SOURCE_UNAVAILABLE" && (
              <Typography.Paragraph role="status">
                研究审核材料当前核验未通过，不能据此办理审核或更新操作资格。
              </Typography.Paragraph>
            )}
            <JudgmentSummary
              decision={decision}
              boundDraft={
                data?.research_draft?.schema_version ===
                "public-research-draft-v2"
              }
              personalContext={
                decision.symbol && /^\d{6}$/.test(decision.symbol) ? (
                  <CurrentHolding key={decision.symbol} decision={decision} />
                ) : undefined
              }
            />
            {data?.research_draft && (
              <ResearchDraftPanel draft={data.research_draft} />
            )}
            <Space wrap style={{ margin: "12px 0" }}>
              {decision.symbol && /^\d{6}$/.test(decision.symbol) && (
                <Link to={fillLink(decision)}>
                  <Button type="primary">记录我的实际成交</Button>
                </Link>
              )}
              <Link to="/daily">
                <Button>返回每日建议</Button>
              </Link>
              <Link to="/history">
                <Button>查看历史判断</Button>
              </Link>
            </Space>
            {decision.symbol && /^\d{6}$/.test(decision.symbol) && (
              <AgentResearchPanel
                key={decision.symbol}
                symbol={decision.symbol}
              />
            )}
            {!!chain?.gaps.length && (
              <details>
                <summary>
                  下一步办理路径与未满足条件（{chain.gaps.length}）
                </summary>
                <ul>
                  {chain.gaps.map((gap, index) => (
                    <li key={`${gap.code}-${index}`}>
                      {
                        {
                          ENGINEERING: "工程接线",
                          DATA: "数据待补齐",
                          EVIDENCE: "研究证据不足",
                          HUMAN: "有权审核人办理",
                          STRATEGY: "策略尚未验证",
                          PRIVATE: "本人资料待确认",
                        }[gap.classification]
                      }
                      ：{gap.reason} <Link to={gap.next_url}>查看办理材料</Link>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {(decision.strategy === "hotspot" ||
              decision.strategy === "HOTSPOT_SATELLITE") &&
              decision.price_action_plan && (
                <CurrentJudgmentChart decision={decision} />
              )}
            <details>
              <summary>展开研究底稿、估值与历史资格核验</summary>
              {!decision.price_action_plan && (
                <section aria-label="操作摘要" style={{ maxWidth: 960 }}>
                  <Typography.Text type="secondary">
                    {strategyText(decision.strategy)} ·{" "}
                    {decision.as_of || "研究日期待核验"}
                  </Typography.Text>
                  <Descriptions
                    column={1}
                    size="small"
                    style={{ marginTop: 12 }}
                    items={[
                      {
                        key: "action",
                        label: "当前能做什么",
                        children:
                          "以本页正式操作资格与未满足条件为准；不自动下单",
                      },
                      {
                        key: "reason",
                        label: "为什么关注",
                        children:
                          decision.reason ||
                          decision.why_selected ||
                          "关注理由尚待核验",
                      },
                      {
                        key: "trigger",
                        label: "何时再复核",
                        children:
                          firstResearchText(decision.next_events) ||
                          "触发条件仍待研究",
                      },
                      {
                        key: "risk",
                        label: "关键风险",
                        children:
                          firstResearchText(decision.counter_evidence) ||
                          firstResearchText(decision.thesis_breakers) ||
                          publicBlockerText(decision.blockers?.[0]) ||
                          "主要风险仍待核验",
                      },
                    ]}
                  />
                  {decision.status !== "FORMALLY_ADMITTED_REVIEW" && (
                    <Typography.Text type="secondary">
                      {codeText(decision.blockers?.[0]) ||
                        "研究、价格或组合条件尚未全部通过。"}
                    </Typography.Text>
                  )}
                </section>
              )}
              {research ? (
                <ResearchDecision decision={decision} research={research} />
              ) : decision.price_action_plan ? null : (
                <LegacyDecision decision={decision} />
              )}
            </details>
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
