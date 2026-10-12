import { useParams, Link } from "@umijs/max";
import { useCallback } from "react";
import { Alert, Descriptions, Typography, Button, Space } from "antd";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { DetailSection } from "../../components/DetailSection";
import { statusLabel } from "../../utils/presentation";

export default function DecisionDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const load = useCallback(
    (signal: AbortSignal) => api.detail(id, signal),
    [id],
  );
  const { data, loading, error, retry } = useApi(load);
  const decision = data?.decision;
  return (
    <Workbench>
      <Typography.Title level={2}>操作逻辑详情</Typography.Title>
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
              {String(decision.name || decision.symbol || decision.id)}
            </Typography.Title>
            <Alert
              showIcon
              type="info"
              message={String(decision.reason || "当前研究尚未提供一句话结论")}
              description={`决策状态：${statusLabel(decision.status || data?.status)}。所有操作均需人工复核。`}
            />
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
            <DetailSection
              title="价格与估值上下文"
              value={decision.price_context}
            />
            <DetailSection
              title="下一批事件与复核条件"
              value={decision.next_events}
            />
            <DetailSection title="失效条件" value={decision.thesis_breakers} />
            <DetailSection title="当前阻塞" value={decision.blockers} />
          </>
        )}
        <Space style={{ marginTop: 24 }}>
          <Link to="/daily">
            <Button>返回每日建议</Button>
          </Link>
          <Link to="/history">
            <Button>查看历史判断</Button>
          </Link>
        </Space>
      </RemoteState>
    </Workbench>
  );
}
