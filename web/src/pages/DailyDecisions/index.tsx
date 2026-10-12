import { Alert, Col, Row, Statistic, Typography } from "antd";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { DecisionTable } from "../../components/DecisionTable";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { dailyStatus } from "../../utils/status";

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
              message={`市场环境：${data.market.status}`}
              description={data.market.reason || "暂无补充说明"}
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
            {status?.noFormalCandidate && (
              <Alert
                style={{ marginTop: 24 }}
                type="warning"
                showIcon
                message="今日没有通过完整准入的交易候选。"
                description={
                  status.watchCount
                    ? `存在 ${status.watchCount} 只研究观察证券，仍需补齐准入条件。`
                    : "目前没有可展示的研究观察证券。"
                }
              />
            )}
            {data.blockers.length > 0 && (
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                message="当前阻塞条件"
                description={
                  <ul>
                    {data.blockers.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                }
              />
            )}
            <DecisionTable
              title="我的持仓今天需要关注"
              items={data.sections.holdings}
              empty="暂无经核验的持仓关注事项"
            />
            <DecisionTable
              title="价值投资 · 新机会"
              items={data.sections.value}
              empty="暂无价值投资候选"
            />
            <DecisionTable
              title="热点追踪 · 新机会"
              items={data.sections.hotspot}
              empty="暂无热点追踪候选"
            />
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
