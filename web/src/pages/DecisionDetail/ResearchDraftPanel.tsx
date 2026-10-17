import { Alert, Descriptions, List, Table, Tag, Typography } from "antd";
import type { ResearchDraft, ResearchDraftAssumption } from "../../types/api";
import { formatScenarioValue } from "../../utils/researchDetail";
import { shortDigest } from "../../utils/history";
import {
  researchAssumptionName,
  researchChangeText,
  researchConfidenceText,
  researchGateText,
  researchSentence,
  researchStatusText,
} from "../../utils/researchDraftText";

const LABEL_STYLE = { width: 132, whiteSpace: "nowrap" as const };

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
                {researchAssumptionName(row.name)}
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
