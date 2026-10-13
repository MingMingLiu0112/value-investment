import { Link } from "@umijs/max";
import { Alert, Col, List, Row, Statistic, Tag, Typography } from "antd";
import type { PropsWithChildren } from "react";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { DecisionCard } from "../../components/DecisionCard";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import type { DailyResearchStatus } from "../../types/api";
import { formatMoney } from "../../utils/format";
import { dailyStatus } from "../../utils/status";
import { codeText, describeCode } from "../../utils/codes";

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
        <li key={code}>{codeText(code) ?? code}</li>
      ))}
    </ul>
  );
}

function opportunityReasons(blockers: string[]): string[] {
  return blockers.filter((code) => code !== HOLDINGS_BLOCKER);
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
function HoldingsSection() {
  const portfolio = useApi(api.portfolio);
  const risk = useApi(api.risk);
  if (portfolio.error) {
    return (
      <Alert
        type="warning"
        showIcon
        message="私人台账读取失败"
        description={portfolio.error}
      />
    );
  }
  const data = portfolio.data;
  if (!data) {
    return (
      <Typography.Text type="secondary">正在读取私人台账…</Typography.Text>
    );
  }
  if (data.status !== "CONNECTED") {
    const blocker = data.blockers.find((code) => code !== "PRICE_NOT_ADMITTED");
    return (
      <Alert
        type="info"
        showIcon
        message={
          blocker
            ? (codeText(blocker) ?? "私人组合尚未接入")
            : "私人组合尚未接入"
        }
        description="持仓关注事项来自你本人确认的私人台账；在接入并确认持仓之前，这里没有内容可展示，也不代表你的组合为空。"
      />
    );
  }
  const blockers = [
    ...(risk.data?.blockers ?? []),
    ...(risk.data?.engine?.blockers ?? []),
  ].filter((code, index, all) => all.indexOf(code) === index);
  return (
    <>
      <Alert
        type="warning"
        showIcon
        message="持仓已接入，但行情未准入"
        description={
          (data.valuation?.reason || "尚未接入经核验的当前行情。") +
          " 在经核验的收盘价接入前，这里只复核台账事实，不给出加减仓建议。"
        }
      />
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
      <div style={{ marginTop: 12 }}>
        <Typography.Text>双策略风险复核暂缓，还缺以下输入：</Typography.Text>
        {blockers.length ? (
          <ReasonList blockers={blockers} />
        ) : (
          <Typography.Text type="secondary" style={{ display: "block" }}>
            {risk.loading ? "正在读取风险复核…" : "风险引擎未返回缺失项。"}
          </Typography.Text>
        )}
      </div>
    </>
  );
}

export default function DailyDecisions() {
  const { data, loading, error, retry } = useApi(api.daily);
  const status = data ? dailyStatus(data) : undefined;
  return (
    <Workbench>
      <Typography.Title level={2}>每日建议</Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data && (
          <>
            <Typography.Text type="secondary">
              数据截至：{data.as_of || "未提供"}
            </Typography.Text>
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
                <HoldingsSection />
              )}
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
                <li>market.status: {data.market.status}</li>
                <li>market.reason: {data.market.reason ?? "未提供"}</li>
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
