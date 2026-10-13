import { Alert, Col, Row, Statistic, Typography } from "antd";
import type { PropsWithChildren } from "react";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { DecisionCard } from "../../components/DecisionCard";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { dailyStatus } from "../../utils/status";
import { codeText, describeCode } from "../../utils/codes";

const HOLDINGS_BLOCKER = "PRIVATE_PORTFOLIO_NOT_CONNECTED";

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
                  value={data.summary.universe_count}
                />
              </Col>
              <Col span={8}>
                <Statistic title="正式复核候选" value={status?.formalCount} />
              </Col>
              <Col span={8}>
                <Statistic title="研究观察" value={status?.watchCount} />
              </Col>
            </Row>

            <Section title="① 持仓需要关注的事项">
              {data.sections.holdings.length > 0 ? (
                data.sections.holdings.map((item) => (
                  <DecisionCard key={item.id} item={item} />
                ))
              ) : data.blockers.includes(HOLDINGS_BLOCKER) ? (
                <Alert
                  type="info"
                  showIcon
                  message="私人组合尚未接入"
                  description="持仓关注事项来自你本人确认的私人台账；在接入并确认持仓之前，这里没有内容可展示，也不代表你的组合为空。"
                />
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="暂无经核验的持仓关注事项"
                  description="当前台账中没有触发关注条件的持仓。"
                />
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
