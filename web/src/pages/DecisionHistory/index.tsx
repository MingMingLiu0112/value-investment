import {
  Alert,
  Col,
  Descriptions,
  List,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { PropsWithChildren } from "react";
import { useState } from "react";
import { Link } from "@umijs/max";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { ConfirmedTrades } from "../../components/ConfirmedTrades";
import { HotspotReplayReview } from "../../components/HotspotReplayReview";
import { usePrivateState } from "../../hooks/usePrivateState";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import type {
  ResearchEvidenceRow,
  ResearchFieldChange,
  ResearchHistoryItem,
  ResearchVersionRow,
} from "../../types/api";
import { describeCode } from "../../utils/codes";
import { comparisonSummary, shortDigest } from "../../utils/history";

const UNNAMED_GROUP = "未命名复核组";

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

function summaryValue(value: unknown): string {
  if (value === undefined) return "未提供";
  if (value === null) return "null";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

interface FieldChangeRow {
  key: string;
  before: unknown;
  after: unknown;
}

function VersionsTable({ versions }: { versions: ResearchVersionRow[] }) {
  return (
    <Table<ResearchVersionRow>
      size="small"
      rowKey="version_label"
      dataSource={versions}
      pagination={false}
      scroll={{ x: 640 }}
      locale={{ emptyText: "没有可按 SHA-256 复算的版本" }}
      columns={[
        { title: "版本", dataIndex: "version_label" },
        { title: "研究日期", dataIndex: "research_date", width: 110 },
        {
          title: "SHA-256（前12位）",
          dataIndex: "sha256",
          width: 170,
          render: (value: string) => shortDigest(value) ?? "未提供",
        },
        {
          title: "当前发布物",
          dataIndex: "bound_to_current_publication",
          width: 120,
          render: (value: boolean) =>
            value ? <Tag color="blue">已绑定</Tag> : <Tag>未绑定</Tag>,
        },
      ]}
    />
  );
}

function HistoryDetail({ item }: { item: ResearchHistoryItem }) {
  const attention = item.attention;
  const comparison = item.comparison;
  const changedFields = comparison.changed_fields ?? [];
  const fieldChanges: FieldChangeRow[] = Object.entries(
    comparison.field_changes ?? {},
  ).map(([key, change]) => {
    const value = (change ?? {}) as ResearchFieldChange;
    return { key, before: value.before, after: value.after };
  });
  const groups = comparison.review_group_changes ?? {
    added: [],
    removed: [],
    changed: [],
  };
  const triggers = attention?.reopen_triggers ?? [];
  const reviewItems = item.review_items ?? [];
  const assumptions = item.assumptions ?? null;
  return (
    <>
      <Space wrap size={8}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {item.symbol}
        </Typography.Title>
        <Tag>{describeCode(item.status)}</Tag>
        <Tag>{describeCode(item.candidate_action)}</Tag>
      </Space>
      <Typography.Text
        type="secondary"
        style={{ display: "block", marginTop: 8 }}
      >
        最新版本：{item.latest_version_label}；当前发布物绑定的研究版本：
        {item.published_research_version || "未绑定"}
      </Typography.Text>

      <Section title="① 当初为什么关注">
        <Descriptions
          bordered
          size="small"
          column={1}
          items={[
            {
              key: "choice",
              label: "研究选择（choice_id）",
              children: attention?.choice_id || "未提供",
            },
            {
              key: "confidence",
              label: "信心水平",
              children: attention?.confidence || "未提供",
            },
            {
              key: "reason",
              label: "关注理由",
              children: <TextLine value={attention?.reason} />,
            },
          ]}
        />
      </Section>

      <Section title="② 当时依靠哪些证据">
        <Table<ResearchEvidenceRow>
          size="small"
          rowKey="path"
          dataSource={item.evidence ?? []}
          pagination={false}
          locale={{ emptyText: "未提供可核验证据文件" }}
          columns={[
            {
              title: "证据文件",
              dataIndex: "path",
              render: (value: string) => (
                <Typography.Text style={{ overflowWrap: "anywhere" }}>
                  {value}
                </Typography.Text>
              ),
            },
            {
              title: "SHA-256（前12位）",
              dataIndex: "sha256",
              width: 170,
              render: (value: string | null) => shortDigest(value) ?? "未提供",
            },
          ]}
        />
        <Descriptions
          bordered
          size="small"
          column={3}
          style={{ marginTop: 12 }}
          title="收入增长假设（income_growth）"
          items={[
            {
              key: "bear",
              label: "bear（悲观）",
              children: assumptions?.bear ?? "未提供",
            },
            {
              key: "base",
              label: "base（基准）",
              children: assumptions?.base ?? "未提供",
            },
            {
              key: "bull",
              label: "bull（乐观）",
              children: assumptions?.bull ?? "未提供",
            },
          ]}
        />
      </Section>

      <Section title="③ 当时最担心什么">
        <Descriptions
          bordered
          size="small"
          column={1}
          items={[
            {
              key: "countercase",
              label: "最大反证",
              children: <TextLine value={attention?.countercase} />,
            },
            {
              key: "limits",
              label: "保障限制（assurance_limits）",
              children: (
                <BulletList
                  items={item.assurance_limits ?? []}
                  empty="未提供"
                />
              ),
            },
          ]}
        />
      </Section>

      <Section title="④ 现在发生了什么">
        <Alert
          showIcon
          type={
            comparison.status === "COMPARED" &&
            comparison.observation === "UNCHANGED"
              ? "success"
              : "info"
          }
          message={comparisonSummary(comparison)}
          description={
            comparison.status === "COMPARED"
              ? "对比 " +
                (comparison.from_version || "未提供") +
                " → " +
                (comparison.to_version || "未提供") +
                "；准入等级影响：" +
                (comparison.admission_effect === "NONE"
                  ? "无（不改变任何准入等级）"
                  : comparison.admission_effect || "未提供")
              : comparison.reason || "没有足够的版本做机械对比。"
          }
        />
        {comparison.status === "COMPARED" && (
          <Descriptions
            bordered
            size="small"
            column={1}
            style={{ marginTop: 12 }}
            title="字段与复核组的机械变化"
            items={[
              {
                key: "fields",
                label: "变化字段（changed_fields）",
                children: changedFields.length
                  ? changedFields.join("、")
                  : "无",
              },
              {
                key: "groups",
                label: "复核组变化",
                children:
                  "新增 " +
                  (groups.added.length ? groups.added.join("、") : "无") +
                  "；移除 " +
                  (groups.removed.length ? groups.removed.join("、") : "无") +
                  "；修改 " +
                  (groups.changed.length ? groups.changed.join("、") : "无"),
              },
            ]}
          />
        )}
      </Section>

      <Section title="⑤ 哪些判断保持成立 / 哪些假设被削弱">
        <Alert
          type="info"
          showIcon
          message="这里只报告机械字段差异"
          description="是否会削弱或推翻原有判断由人工复核决定，本页不代替你下结论。"
        />
        <Table<FieldChangeRow>
          size="small"
          rowKey="key"
          style={{ marginTop: 12 }}
          dataSource={fieldChanges}
          pagination={false}
          scroll={{ x: 640 }}
          locale={{ emptyText: "无字段差异记录" }}
          columns={[
            { title: "字段", dataIndex: "key", width: 220 },
            {
              title: "之前",
              dataIndex: "before",
              render: (value: unknown) => summaryValue(value),
            },
            {
              title: "之后",
              dataIndex: "after",
              render: (value: unknown) => summaryValue(value),
            },
          ]}
        />
        {reviewItems.length ? (
          reviewItems.map((row, index) => (
            <Descriptions
              key={row.id ?? index}
              bordered
              size="small"
              column={1}
              style={{ marginTop: 12 }}
              title={"复核组 " + (row.id || UNNAMED_GROUP)}
              items={[
                {
                  key: "question",
                  label: "待复核问题",
                  children: <TextLine value={row.question} />,
                },
                {
                  key: "support",
                  label: "支持证据",
                  children: <TextLine value={row.support} />,
                },
                {
                  key: "countercase",
                  label: "反证",
                  children: <TextLine value={row.countercase} />,
                },
                {
                  key: "impact",
                  label: "影响",
                  children: <TextLine value={row.impact} />,
                },
                {
                  key: "paths",
                  label: "关联字段",
                  children: row.field_paths?.length
                    ? row.field_paths.join("、")
                    : "未提供",
                },
              ]}
            />
          ))
        ) : (
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message="未提供人工复核组记录"
          />
        )}
      </Section>

      <Section title="⑥ 接下来需要复核什么">
        <Descriptions
          bordered
          size="small"
          column={1}
          items={[
            {
              key: "triggers",
              label: "复核触发条件（reopen_triggers）",
              children: <BulletList items={triggers} empty="未提供" />,
            },
            {
              key: "questions",
              label: "复核组问题",
              children: reviewItems.length ? (
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {reviewItems.map((row, index) => (
                    <li key={row.id ?? index}>
                      {(row.id ? row.id + "：" : "") +
                        (row.question || "未提供")}
                    </li>
                  ))}
                </ul>
              ) : (
                "未提供"
              ),
            },
          ]}
        />
      </Section>

      <Section title="研究版本（可按 SHA-256 复算）">
        <VersionsTable versions={item.versions ?? []} />
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", color: "#5c6b73" }}>
            技术详情（原始数据）
          </summary>
          <pre
            style={{
              marginTop: 8,
              maxHeight: 320,
              overflow: "auto",
              fontSize: 12,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {JSON.stringify(item, null, 2)}
          </pre>
        </details>
      </Section>
    </>
  );
}

export default function DecisionHistory() {
  const { data, loading, error, retry } = useApi(api.history);
  const [selectedId, setSelectedId] = useState<string>();
  const privateState = usePrivateState();
  const items = data?.items ?? [];
  const current = items.find((item) => item.id === selectedId) ?? items[0];
  return (
    <Workbench>
      <Typography.Title level={2}>复盘</Typography.Title>
      {privateState.risk?.facts?.account_scope?.startsWith("TEST_ONLY") && (
        <Alert
          type="warning"
          showIcon
          message="TEST_ONLY 隔离演练复盘"
          description="以下账户成交用于工程验收，不是本人真实成交，也不代表策略表现或投资资格。"
        />
      )}
      <Section title="我的实际成交与原判断版本">
        {privateState.portfolio &&
        !["LOADING", "LOCKED", "UNAVAILABLE"].includes(privateState.kind) ? (
          <>
            <Typography.Paragraph type="secondary">
              同一私人台账的已确认记录；当前研究更新不会覆盖原关联版本。未记录成交不等于未执行，尚无核验结果时不补算收益或原判断失效。
            </Typography.Paragraph>
            <ConfirmedTrades trades={privateState.portfolio.trades} />
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            message={privateState.label}
            description={privateState.detail}
          />
        )}
      </Section>
      <Typography.Title level={3}>研究快照与判断变化</Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        <Section title="热点观察变化">
          {data?.observation_changes?.status === "SOURCE_REVALIDATED" ? (
            <>
              <p>
                截至 {data.observation_changes.completed_session}{" "}
                的已核验观察记录；不代表交易批准。
              </p>
              <List
                dataSource={data.observation_changes.items}
                locale={{ emptyText: "该次已核验记录没有观察对象" }}
                renderItem={(item) => (
                  <List.Item>
                    <Space wrap>
                      <Link to={`/decisions/hotspot-${item.symbol}`}>
                        {item.symbol}
                      </Link>
                      <span>
                        {
                          {
                            new: "新入选",
                            continue: "继续观察",
                            approach: "接近条件",
                            triggered: "已观察到条件",
                            invalid: "结构不符合",
                            expired: "计划已过期",
                            left: "已退出观察",
                          }[item.transition]
                        }
                      </span>
                      {item.trend_strengthened && (
                        <Tag color="green">趋势增强</Tag>
                      )}
                      {!item.selected_today && <span>保留观察历史</span>}
                      <Typography.Text type="secondary">
                        行情日 {item.market_trade_date}
                      </Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            </>
          ) : (
            <Alert
              type="info"
              showIcon
              message="当前跨日观察记录尚未通过来源复算"
              description="这不等于没有变化；既有研究历史和本人已确认成交仍在本页保留。"
            />
          )}
        </Section>
        <Section title="每日公开发布版本">
          {data?.published_decision_history?.history?.length ? (
            <List
              size="small"
              bordered
              dataSource={[...data.published_decision_history.history].reverse()}
              renderItem={(row) => (
                <List.Item>
                  <Space direction="vertical" size={2}>
                    <Typography.Text strong>
                      {row.published_at || "发布时间未提供"} · {row.publication_id}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      决策截止 {row.decision_cutoff || "未提供"}；研究版本 {row.research_version || "未提供"}；
                      数据包 SHA-256 {shortDigest(row.packet_sha256) || "未提供"}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      仅证明该公开发布版本可复核，动作固定为 no_order，不代表历史买卖或策略收益。
                    </Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          ) : (
            <Alert
              type="info"
              showIcon
              message={
                data?.published_decision_history?.status === "CURRENT_ONLY"
                  ? "当前有发布版本，但尚无可复核的历史发布记录"
                  : "尚无可复核的每日公开发布版本"
              }
              description={
                data?.published_decision_history?.note ||
                "缺少经 SHA-256 校验的发布回执时，页面不会补造历史记录。"
              }
            />
          )}
        </Section>
        {data &&
          (items.length === 0 ? (
            <Alert
              type="info"
              showIcon
              message="尚未接入可复算的研究历史"
              description={
                data.note || "没有找到可按 SHA-256 复算的研究版本文件。"
              }
            />
          ) : (
            <>
              <Typography.Text type="secondary">
                共 {data.counts?.symbols ?? items.length} 只证券、
                {data.counts?.versions ?? 0} 个研究版本。
              </Typography.Text>
              <Row gutter={24} style={{ marginTop: 16 }}>
                <Col xs={24} md={8}>
                  <List
                    size="small"
                    bordered
                    dataSource={items}
                    renderItem={(item) => (
                      <List.Item
                        role="button"
                        tabIndex={0}
                        aria-pressed={current?.id === item.id}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedId(item.id);
                          }
                        }}
                        onClick={() => setSelectedId(item.id)}
                        style={{
                          cursor: "pointer",
                          background:
                            current?.id === item.id ? "#f0f5ff" : undefined,
                        }}
                      >
                        <List.Item.Meta
                          title={
                            <Space size={8}>
                              <span>{item.symbol}</span>
                              <Tag>{describeCode(item.status)}</Tag>
                            </Space>
                          }
                          description={item.latest_version_label}
                        />
                      </List.Item>
                    )}
                  />
                </Col>
                <Col xs={24} md={16}>
                  {current && (
                    <>
                      <p>
                        {current.symbol} · {describeCode(current.status)} ·{" "}
                        {current.latest_version_label}
                      </p>
                      <p>
                        研究快照不等于实际执行；个人成交与结果以上方已确认台账为准。
                      </p>
                      <details key={current.id}>
                        <summary>展开所选研究的依据、版本与变化</summary>
                        <HistoryDetail item={current} />
                      </details>
                    </>
                  )}
                </Col>
              </Row>
            </>
          ))}
      </RemoteState>
      {data?.note && items.length > 0 && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
          {data.note}
        </Typography.Paragraph>
      )}
      <HotspotReplayReview />
    </Workbench>
  );
}
