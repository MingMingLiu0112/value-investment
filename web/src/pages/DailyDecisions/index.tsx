import { Link } from "@umijs/max";
import {
  Alert,
  Col,
  Collapse,
  Descriptions,
  List,
  Row,
  Statistic,
  Tag,
  Typography,
} from "antd";
import type { PropsWithChildren } from "react";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { DecisionCard } from "../../components/DecisionCard";
import { useApi } from "../../hooks/useApi";
import { usePrivateState } from "../../hooks/usePrivateState";
import type { PrivateStateHandle } from "../../hooks/usePrivateState";
import { api } from "../../services/api";
import type {
  DailyDualSleeveSurface,
  DailyPublicPacket,
  DailyResearchStatus,
} from "../../types/api";
import { formatMoney } from "../../utils/format";
import { dailyStatus } from "../../utils/status";
import { codeText, describeCode } from "../../utils/codes";
import {
  dualSleeveLiveUnreadable,
  dualSleeveMismatch,
  dualSleeveView,
} from "../../utils/dualSleeve";
import {
  blockerText,
  excelComparisonText,
  excelNewerSideText,
  freshnessLevel,
  packetDateRows,
  snapshotCutoffLine,
  snapshotIntegrityText,
} from "../../utils/packet";

const HOLDINGS_BLOCKER = "PRIVATE_PORTFOLIO_NOT_CONNECTED";
const PRICE_UNKNOWN = "未知（未接入经核验行情）";

const SLEEVE_TEXT: Record<string, string> = {
  CORE_VALUE: "价值池",
  HOTSPOT_SATELLITE: "情绪卫星仓",
};

function Section({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <section style={{ marginTop: 28 }}>
      <h2 style={{ fontSize: 18, marginBottom: 8 }}>{title}</h2>
      {children}
    </section>
  );
}

function ReasonList({ blockers }: { blockers: string[] }) {
  if (!blockers.length) return null;
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {blockers.map((code) => (
        <li key={code}>{blockerText(code)}</li>
      ))}
    </ul>
  );
}

function opportunityReasons(blockers: string[]): string[] {
  return blockers.filter((code) => code !== HOLDINGS_BLOCKER);
}

const ACTOR_LABEL: Record<string, string> = {
  HUMAN: "人工",
  ENGINEERING: "工程",
  EXTERNAL_DATA: "外部数据",
};

function nextStepRows(packet: DailyPublicPacket) {
  const human: { key: string; text: string }[] = [];
  const engineering: { key: string; text: string }[] = [];
  let externalCount = 0;
  for (const entry of Object.values(packet.company_statuses)) {
    for (const action of entry.pending_actions) {
      const key = `${entry.symbol}:${action.code}`;
      const text = `${entry.name}（${entry.symbol}）：${action.label}`;
      const actor = ACTOR_LABEL[action.actor] ?? action.actor;
      if (action.actor === "HUMAN") human.push({ key, text });
      else if (action.actor === "ENGINEERING")
        engineering.push({ key, text: `【${actor}】${text}` });
      else externalCount += 1;
    }
  }
  return { rows: [...human, ...engineering].slice(0, 6), externalCount };
}

/**
 * TL9 MVP-1 首屏：先回答“这批数据是什么版本、截止到哪天、下一步做什么”。
 * 数据包不可用时 fail-closed，不显示任何推算内容。
 */
function PacketSection({
  packet,
  error,
  retry,
}: {
  packet?: DailyPublicPacket;
  error?: string;
  retry: () => void;
}) {
  if (!packet) {
    return (
      <Alert
        style={{ marginTop: 16 }}
        type={error ? "error" : "info"}
        showIcon
        message={error ? "每日公开数据包读取失败" : "正在读取每日公开数据包…"}
        description={
          error ? (
            <>
              {error}
              <a style={{ marginLeft: 12 }} onClick={retry}>
                重试
              </a>
            </>
          ) : undefined
        }
      />
    );
  }
  if (packet.packet_status !== "CURRENT" || !packet.publication_id) {
    return (
      <Alert
        style={{ marginTop: 16 }}
        type="error"
        showIcon
        message="每日公开数据包不可用（fail-closed）"
        description={
          <>
            <div>
              发布链校验未通过：{packet.chain_error || "原因未提供"}
              ；不会沿用旧版本数据。
            </div>
            {packet.blockers.length > 0 && (
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {packet.blockers.map((code) => (
                  <li key={code}>{blockerText(code)}</li>
                ))}
              </ul>
            )}
          </>
        }
      />
    );
  }
  const { rows, externalCount } = nextStepRows(packet);
  const freshnessItems = [
    { key: "quote", label: "行情", value: packet.data_freshness.quote },
    { key: "research", label: "研究", value: packet.data_freshness.research },
  ];
  return (
    <div style={{ marginTop: 16 }}>
      <Descriptions size="small" bordered column={3}>
        <Descriptions.Item label="数据版本">
          {packet.publication_id}
        </Descriptions.Item>
        <Descriptions.Item label="研究版本">
          {packet.research_version ?? "未提供"}
        </Descriptions.Item>
        <Descriptions.Item label="来源绑定">
          {packet.source_bindings_verified
            ? "全部哈希校验通过（不等于投资准入）"
            : "存在未通过校验的来源（详见下方阻断事项）"}
        </Descriptions.Item>
        {packetDateRows(packet).map((row) => (
          <Descriptions.Item key={row.label} label={row.label}>
            {row.value}
          </Descriptions.Item>
        ))}
      </Descriptions>
      <SnapshotSection />
      {freshnessItems.map((item) => {
        const level = freshnessLevel(item.value.status);
        if (level === "ok") return null;
        return (
          <Alert
            key={item.key}
            style={{ marginTop: 12 }}
            type={level === "warning" ? "warning" : "info"}
            showIcon
            message={`${item.label}新鲜度：${item.value.status}`}
            description={item.value.reason ?? "未提供补充说明"}
          />
        );
      })}
      <Row gutter={24} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Statistic
            title="正式准入公司"
            value={packet.formal_admission_count}
          />
        </Col>
        <Col span={6}>
          <Statistic title="待人工复核" value={packet.pending_review_count} />
        </Col>
        <Col span={6}>
          <Statistic
            title="需要重新研究"
            value={packet.research_counts.needs_re_research_count}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="研究观察线索"
            value={packet.research_counts.lead_count ?? "不可用"}
          />
        </Col>
      </Row>
      {rows.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Typography.Text strong>下一步怎么做（真实待办）</Typography.Text>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {rows.map((row) => (
              <li key={row.key}>{row.text}</li>
            ))}
          </ul>
          {externalCount > 0 && (
            <Typography.Text type="secondary">
              另有 {externalCount} 项等待外部数据（已验证收盘行情或官方披露）。
            </Typography.Text>
          )}
        </div>
      )}
      {packet.blockers.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Typography.Text type="secondary">
            当前阻止正式买卖信号的事项：
          </Typography.Text>
          <ReasonList blockers={packet.blockers} />
        </div>
      )}
      <Collapse
        ghost
        style={{ marginTop: 8 }}
        items={[
          {
            key: "technical",
            label: (
              <Typography.Text strong>证据与技术详情（可展开）</Typography.Text>
            ),
            children: (
              <Descriptions
                bordered
                column={1}
                size="small"
                items={[
                  {
                    key: "schema",
                    label: "数据包结构",
                    children: packet.schema_version,
                  },
                  {
                    key: "engine",
                    label: "引擎版本",
                    children: packet.engine_version ?? "未提供",
                  },
                  {
                    key: "generated",
                    label: "生成时间",
                    children: packet.generated_at,
                  },
                  {
                    key: "quote_bridge",
                    label: "行情桥登记",
                    children: packet.quote_bridge
                      ? `${packet.quote_bridge.path}（${packet.quote_bridge.quotes_registered} 条，登记于 ${
                          packet.quote_bridge.registered_at ?? "未提供"
                        }，SHA-256 ${packet.quote_bridge.sha256 ?? "未提供"}）`
                      : "未提供",
                  },
                  {
                    key: "bindings",
                    label: "来源绑定（角色 / 路径 / SHA-256）",
                    children: (
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {(packet.source_bindings ?? []).map((binding) => (
                          <li key={binding.role + binding.path}>
                            {binding.role}：{binding.path}
                            {binding.sha256_verified === false
                              ? "（哈希校验未通过）"
                              : binding.present === false
                                ? "（文件缺失）"
                                : ""}
                          </li>
                        ))}
                      </ul>
                    ),
                  },
                ]}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

/**
 * TL10-RC：冻结快照与正式 Excel 的只读对照。接口不可用时 fail-closed，
 * 不断言“一致”，也不推导任何投资结论。
 */
function SnapshotSection() {
  const { data, loading, error, retry } = useApi(api.snapshot);
  const retryLink = (
    <a style={{ marginLeft: 12 }} onClick={retry}>
      重试
    </a>
  );
  if (loading) {
    return (
      <Typography.Text
        type="secondary"
        style={{ display: "block", marginTop: 12 }}
      >
        正在读取快照与 Excel 对照…
      </Typography.Text>
    );
  }
  if (!data) {
    return (
      <Alert
        style={{ marginTop: 12 }}
        type="warning"
        showIcon
        message="快照与 Excel 对照读取失败（fail-closed）"
        description={
          <>
            {error ?? "接口未返回数据"}；无法确认快照版本与 Excel
            对照状态，不会断言“一致”。{retryLink}
          </>
        }
      />
    );
  }
  const verified = data.status === "VERIFIED";
  const newer = excelNewerSideText(data.excel_live, data.dates);
  return (
    <div style={{ marginTop: 12 }}>
      <Descriptions
        size="small"
        bordered
        column={3}
        title="快照与 Excel 对照"
        items={[
          {
            key: "version",
            label: "快照版本",
            children: data.publication_id ?? "尚无已验证快照",
          },
          {
            key: "integrity",
            label: "校验状态",
            children: (
              <Tag
                color={
                  verified
                    ? "green"
                    : data.status === "INVALID"
                      ? "red"
                      : "default"
                }
              >
                {snapshotIntegrityText(data)}
              </Tag>
            ),
          },
          {
            key: "published",
            label: "生成 / 发布时间",
            children: `${data.generated_at ?? "未提供"} / ${
              data.published_at ?? "未提供"
            }`,
          },
          {
            key: "cutoff",
            label: "数据截止",
            children: snapshotCutoffLine(data.dates),
          },
          {
            key: "excel",
            label: "Excel 对照",
            children:
              excelComparisonText(data.excel_live) +
              (newer ? `；${newer}` : ""),
          },
          {
            key: "boundary",
            label: "刷新边界",
            children:
              "SAFE_REFRESH 只刷新行情并重建公开快照；重跑研究、事件复核与 G3 估值门仍是人工/工程步骤。",
          },
        ]}
      />
      <Typography.Text
        type="secondary"
        style={{ display: "block", marginTop: 8 }}
      >
        {data.excel_live?.note ?? "只读校验：不覆盖、不重建正式工作簿。"}
      </Typography.Text>
    </div>
  );
}

/**
 * 研究状态只复述已登记行情与研究截止日的真实比较结果：行情晚于研究截止日
 * 即为“需要重新研究”，登记层不预支任何研究批准或价格比较资格。
 */
function ResearchStatusSection({ status }: { status?: DailyResearchStatus }) {
  if (!status || status.status === "UNAVAILABLE") {
    return (
      <Alert
        type="info"
        showIcon
        message="暂无可用的研究状态"
        description="研究状态来自已登记的研究-行情绑定；读取不到时不推测任何公司的覆盖情况。"
      />
    );
  }
  if (status.status === "REGISTRY_UNAVAILABLE") {
    return (
      <Alert
        type="warning"
        showIcon
        message="行情登记文件不可读（登记状态未知）"
        description={
          (status.reason || "行情登记文件无法读取。") +
          " 这不代表没有登记，也不代表登记为空；修复登记文件后重新运行每日工作台。"
        }
      />
    );
  }
  if (!status.rows.length) {
    return (
      <Alert
        type="info"
        showIcon
        message="尚未登记任何公司行情"
        description="登记经核验收盘行情后，这里会逐家显示研究截止日是否仍然覆盖行情日期。"
      />
    );
  }
  return (
    <>
      <Typography.Text type="secondary">
        已登记 {status.registered_count} 家 · 需要重新研究{" "}
        {status.needs_re_research_count ?? 0} 家 · 已具备价格比较准入{" "}
        {status.admitted_count ?? 0} 家
      </Typography.Text>
      <List
        size="small"
        style={{ marginTop: 12 }}
        dataSource={status.rows}
        renderItem={(row) => (
          <List.Item key={row.symbol}>
            <List.Item.Meta
              title={
                <>
                  <Link to={"/decisions/" + encodeURIComponent(row.symbol)}>
                    {row.name}（{row.symbol}）
                  </Link>{" "}
                  {row.needs_re_research ? (
                    <Tag color="orange">需要重新研究</Tag>
                  ) : row.research_covers_close ? (
                    <Tag color="green">研究覆盖核验收盘</Tag>
                  ) : (
                    <Tag>状态待确认</Tag>
                  )}
                </>
              }
              description={
                "研究截止日 " +
                (row.research_day || "未提供") +
                " · 核验收盘日 " +
                (row.quote_date || "未提供") +
                " · " +
                (row.reason ||
                  codeText(row.bridge_status ?? "") ||
                  "状态待确认") +
                (row.next_step ? " 下一步：" + row.next_step : "")
              }
            />
          </List.Item>
        )}
      />
    </>
  );
}

/**
 * ① 持仓需要关注的事项。私人台账只在已授权的本机会话内读取；
 * 未接入经核验收盘价时只复核台账事实，不给出任何加减仓建议。
 */
function HoldingsSection({ state }: { state: PrivateStateHandle }) {
  const retryLink = (
    <a style={{ marginLeft: 12 }} onClick={state.retry}>
      重试
    </a>
  );
  if (state.kind !== "CONNECTED" && state.kind !== "BLOCKED_PRIVATE_INPUT") {
    const type =
      state.kind === "UNAVAILABLE"
        ? "warning"
        : state.kind === "LOCKED"
          ? "info"
          : "info";
    const message = state.label;
    return (
      <Alert
        type={type}
        showIcon
        message={message}
        description={
          <>
            {state.detail}
            {state.nextStep ? (
              <div style={{ marginTop: 4 }}>{state.nextStep}</div>
            ) : null}
            {state.blockers.length > 0 && (
              <ReasonList blockers={state.blockers} />
            )}
            {retryLink}
          </>
        }
      />
    );
  }
  const data = state.portfolio;
  if (!data) {
    return (
      <Typography.Text type="secondary">正在读取私人台账…</Typography.Text>
    );
  }
  const risk = state.risk;
  const blockers = [
    ...(risk?.blockers ?? []),
    ...(risk?.engine?.blockers ?? []),
  ].filter((code, index, all) => all.indexOf(code) === index);
  const priceNotAdmitted =
    data.valuation?.status === "PRICE_NOT_ADMITTED" ||
    data.blockers.includes("PRICE_NOT_ADMITTED");
  return (
    <>
      {state.kind === "BLOCKED_PRIVATE_INPUT" ? (
        <Alert
          type="warning"
          showIcon
          message={state.label}
          description={state.detail}
        />
      ) : priceNotAdmitted ? (
        <Alert
          type="warning"
          showIcon
          message="持仓已接入，但行情未准入"
          description={
            (data.valuation?.reason || "尚未接入经核验的当前行情。") +
            " 在经核验的收盘价接入前，这里只复核台账事实，不给出加减仓建议。"
          }
        />
      ) : null}
      <List
        size="small"
        style={{ marginTop: 12 }}
        dataSource={data.positions}
        locale={{ emptyText: "已确认台账中暂无持仓。" }}
        renderItem={(position) => (
          <List.Item key={position.symbol + position.exchange}>
            <List.Item.Meta
              title={
                position.symbol +
                " · " +
                position.exchange +
                " · 总股数 " +
                position.quantity
              }
              description={
                "成本合计 " +
                formatMoney(position.cost_cny) +
                " 元 · 市值/浮动盈亏：" +
                PRICE_UNKNOWN +
                (position.sleeves.length
                  ? " · " +
                    position.sleeves
                      .map(
                        (row) =>
                          (SLEEVE_TEXT[row.sleeve] ?? row.sleeve) +
                          " " +
                          row.quantity +
                          " 股",
                      )
                      .join("；")
                  : "")
              }
            />
          </List.Item>
        )}
      />
      <Typography.Text
        type="secondary"
        style={{ display: "block", marginTop: 8 }}
      >
        台账版本 {data.revision} · 持仓基准日 {data.as_of || "未提供"}
      </Typography.Text>
      {blockers.length ? (
        <div style={{ marginTop: 12 }}>
          <Typography.Text>双策略风险复核暂缓，还缺以下输入：</Typography.Text>
          <ReasonList blockers={blockers} />
        </div>
      ) : risk ? (
        <Typography.Text
          type="secondary"
          style={{ display: "block", marginTop: 12 }}
        >
          双策略风险复核未返回缺失输入。
        </Typography.Text>
      ) : (
        <Typography.Text
          type="warning"
          style={{ display: "block", marginTop: 12 }}
        >
          双策略风险复核读取失败；读取成功前不展示任何仓位结论，请重试。
        </Typography.Text>
      )}
    </>
  );
}

/**
 * 双策略资金池只复述发布物正式绑定的风险复核结果；私人组合未接入时
 * 明确说明不会给出任何仓位数字，并列出下一步需要用户提供的输入。
 * 发布物状态与当前私人台账明显不一致时，单独提示需要重新运行复核。
 */
function DualSleeveSection({
  surface,
  privateKind,
}: {
  surface?: DailyDualSleeveSurface;
  privateKind: PrivateStateHandle["kind"];
}) {
  const view = dualSleeveView(surface);
  if (!surface || !view) {
    return (
      <Alert
        type="info"
        showIcon
        message="暂无双策略状态"
        description="双策略状态来自当前发布物绑定；读取不到时不推测任何资金池、持仓或仓位。"
      />
    );
  }
  const mismatch = dualSleeveMismatch(surface, privateKind);
  const liveUnreadable = dualSleeveLiveUnreadable(privateKind);
  return (
    <>
      <Descriptions
        bordered
        size="small"
        column={3}
        items={[
          { key: "status", label: "双策略状态", children: view.statusText },
          { key: "portfolio", label: "私人组合", children: view.connectedText },
          { key: "guidance", label: "仓位建议", children: view.guidanceText },
          {
            key: "eligibility",
            label: "交易资格",
            children: view.eligibilityText,
          },
          { key: "authority", label: "决策权限", children: view.authorityText },
          {
            key: "reviewed",
            label: "风险复核时间",
            children: surface.review_generated_at || "未提供",
          },
        ]}
      />
      {mismatch && (
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message="发布物与当前私人台账不一致"
          description={mismatch}
        />
      )}
      {liveUnreadable && (
        <Alert
          style={{ marginTop: 12 }}
          type="info"
          showIcon
          message="上表来自公开发布物（快照），不是当前私人台账读取结果"
          description="私人数据尚未解锁或当前不可用；上表只代表发布物记录，不能当作当前持仓或仓位结论。解锁本机工作台并复核后，以①区实时状态为准。"
        />
      )}
      {view.guidanceMissingReason && (
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message={view.guidanceMissingReason}
          description={
            view.nextInputText ??
            "该状态没有可自动补齐的输入；完成下一步人工确认后再复核。"
          }
        />
      )}
      {surface.source && (
        <Typography.Text
          type="secondary"
          style={{ display: "block", marginTop: 8 }}
        >
          来源：{surface.source}
        </Typography.Text>
      )}
    </>
  );
}

export default function DailyDecisions() {
  const { data, loading, error, retry } = useApi(api.daily);
  const packetState = useApi(api.packet);
  const privateState = usePrivateState();
  const status = data ? dailyStatus(data) : undefined;
  return (
    <Workbench>
      <Typography.Title level={2}>每日建议</Typography.Title>
      <PacketSection
        packet={packetState.data}
        error={packetState.error}
        retry={packetState.retry}
      />
      <RemoteState loading={loading} error={error} retry={retry}>
        {data && (
          <>
            <Alert
              style={{ marginTop: 16 }}
              type="info"
              showIcon
              message={"市场环境：" + describeCode(data.market.status)}
              description={
                data.market.reason
                  ? describeCode(data.market.reason)
                  : "暂无补充说明"
              }
            />
            <Row gutter={24} style={{ marginTop: 24 }}>
              <Col span={8}>
                <Statistic
                  title="全市场扫描"
                  value={data.summary.universe_count ?? "不可用"}
                />
              </Col>
              <Col span={8}>
                <Statistic title="正式复核候选" value={status?.formalCount} />
              </Col>
              <Col span={8}>
                <Statistic
                  title="研究观察"
                  value={status?.watchCount ?? "不可用"}
                />
              </Col>
            </Row>

            <Section title="研究状态与重新研究清单">
              <ResearchStatusSection status={data.research} />
            </Section>

            <Section title="① 持仓需要关注的事项">
              {data.sections.holdings.length > 0 ? (
                data.sections.holdings.map((item) => (
                  <DecisionCard key={item.id} item={item} />
                ))
              ) : (
                <HoldingsSection state={privateState} />
              )}
            </Section>

            <Section title="双策略资金池与仓位护栏">
              <DualSleeveSection
                surface={data.dual_sleeve}
                privateKind={privateState.kind}
              />
            </Section>

            <Section title="② 价值投资机会">
              {data.sections.value.length > 0 ? (
                data.sections.value.map((item) => (
                  <DecisionCard key={item.id} item={item} />
                ))
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="暂无可展示的价值研究候选"
                  description={
                    opportunityReasons(data.blockers).length ? (
                      <ReasonList
                        blockers={opportunityReasons(data.blockers)}
                      />
                    ) : (
                      "当前发布物中没有可展示的研究候选。"
                    )
                  }
                />
              )}
            </Section>

            <Section title="③ 热点追踪">
              {data.sections.hotspot.length > 0 ? (
                data.sections.hotspot.map((item) => (
                  <DecisionCard key={item.id} item={item} />
                ))
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="暂无可展示的热点观察证券"
                  description={
                    opportunityReasons(data.blockers).length ? (
                      <ReasonList
                        blockers={opportunityReasons(data.blockers)}
                      />
                    ) : (
                      "当前没有通过观察门槛的热点条目。"
                    )
                  }
                />
              )}
            </Section>

            <details style={{ marginTop: 28 }}>
              <summary style={{ cursor: "pointer", color: "#5c6b73" }}>
                技术详情（原始代码）
              </summary>
              <ul
                style={{
                  margin: "8px 0 0",
                  paddingLeft: 18,
                  fontSize: 12,
                  lineHeight: 1.8,
                }}
              >
                <li>status: {data.status}</li>
                <li>研究队列快照日期: {data.as_of || "未提供"}</li>
                <li>market.status: {data.market.status}</li>
                <li>market.reason: {data.market.reason ?? "未提供"}</li>
                <li>
                  dual_sleeve.status: {data.dual_sleeve?.status ?? "未提供"}
                </li>
                <li>
                  dual_sleeve.source: {data.dual_sleeve?.source ?? "未绑定"}
                </li>
                <li>
                  dual_sleeve.next_user_input:{" "}
                  {data.dual_sleeve?.next_user_input ?? "无"}
                </li>
                <li>
                  blockers:{" "}
                  {data.blockers.length ? data.blockers.join(", ") : "无"}
                </li>
              </ul>
            </details>
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
