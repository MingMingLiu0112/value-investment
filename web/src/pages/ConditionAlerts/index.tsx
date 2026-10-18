import {
  Alert,
  Button,
  Empty,
  List,
  Popconfirm,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { CheckOutlined, ReloadOutlined } from "@ant-design/icons";
import { useCallback, useState } from "react";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";

const eventLabels: Record<string, string> = {
  PRICE_ATTRACTIVENESS_CHANGED: "价格条件变化",
  SOURCE_SCAN_FAILED: "数据不可用，暂停条件判断",
  SOURCE_SCAN_RECOVERED: "数据恢复，重新复核条件",
};

export default function ConditionAlerts() {
  const [testOnly, setTestOnly] = useState(false);
  const [pending, setPending] = useState<string>();
  const [interaction, setInteraction] = useState<{
    error: boolean;
    text: string;
  }>();
  const load = useCallback(
    (signal: AbortSignal) => api.conditionAlerts(testOnly, signal),
    [testOnly],
  );
  const result = useApi(load);
  const acknowledge = async (alertId: string) => {
    const snapshot = result.data?.snapshot_sha256;
    if (!testOnly || !snapshot || pending) return;
    setPending(alertId);
    setInteraction(undefined);
    try {
      await api.acknowledgeConditionAlert(alertId, snapshot);
      setInteraction({
        error: false,
        text: "已记录阅读确认；未批准研究或交易。",
      });
    } catch (error) {
      setInteraction({
        error: true,
        text:
          error instanceof Error ? error.message : "确认失败，请重新读取记录。",
      });
    } finally {
      setPending(undefined);
      result.retry();
    }
  };
  return (
    <Workbench>
      <Space
        style={{
          width: "100%",
          justifyContent: "space-between",
          flexWrap: "wrap",
        }}
      >
        <Typography.Title level={2}>提醒与待办</Typography.Title>
        <Space>
          <Switch
            checked={testOnly}
            disabled={!!pending}
            onChange={(checked) => {
              setInteraction(undefined);
              setTestOnly(checked);
            }}
            aria-label="隔离演练记录"
          />
          隔离演练记录
          <Button
            icon={<ReloadOutlined />}
            disabled={!!pending}
            onClick={result.retry}
          >
            刷新记录
          </Button>
        </Space>
      </Space>
      {testOnly && (
        <Alert
          type="warning"
          showIcon
          message="TEST_ONLY 隔离演练，不是实际交易时段提醒或操作许可。"
        />
      )}
      {interaction && (
        <Alert
          type={interaction.error ? "error" : "success"}
          showIcon
          message={interaction.text}
        />
      )}
      <RemoteState
        loading={
          result.loading ||
          (!!result.data && result.data.test_only !== testOnly)
        }
        error={result.error}
        retry={result.retry}
      >
        {result.data && (
          <>
            <Alert
              style={{ marginTop: 16 }}
              type="info"
              showIcon
              message={
                result.data.monitor_running ? "监控进程运行中" : "监控未运行"
              }
              description={
                result.data.detail ??
                "仅展示已经留存的历史记录；关闭本地进程后不会持续监控。"
              }
            />
            <Typography.Title level={4}>条件变化记录</Typography.Title>
            {!result.data.history.length ? (
              <Empty description="暂无可核验的条件变化记录" />
            ) : (
              <List
                dataSource={result.data.history}
                renderItem={(event) => {
                  const alert = result.data?.alerts.find(
                    (item) => item.event_id === event.event_id,
                  );
                  const acknowledged = alert?.status === "ACKNOWLEDGED";
                  return (
                    <List.Item>
                      <div>
                        <Space wrap>
                          <Typography.Text strong>
                            {event.symbol}
                          </Typography.Text>
                          <Tag>
                            {eventLabels[event.event_type] ?? "条件复核"}
                          </Tag>
                          <Typography.Text>{event.detected_at}</Typography.Text>
                        </Space>
                        <p>请结合本次观测与原计划复核；此记录不批准交易。</p>
                        {acknowledged ? (
                          <Tag color="green">已阅</Tag>
                        ) : (
                          testOnly &&
                          alert &&
                          alert.available_operations.includes("ACKNOWLEDGE") &&
                          result.data?.snapshot_sha256 && (
                            <Popconfirm
                              title="确认已阅读这条隔离提醒？"
                              description="只记录已阅，不批准研究、投资政策或交易。"
                              okText="确认已阅"
                              cancelText="返回"
                              onConfirm={() => acknowledge(alert.alert_id)}
                            >
                              <Button
                                icon={<CheckOutlined />}
                                loading={pending === alert.alert_id}
                                disabled={
                                  !!pending && pending !== alert.alert_id
                                }
                              >
                                标为已阅
                              </Button>
                            </Popconfirm>
                          )
                        )}
                        <details>
                          <summary>查看原始记录标识</summary>
                          <p>{event.reason}</p>
                          <Typography.Text type="secondary">
                            {event.source_event_id}
                          </Typography.Text>
                        </details>
                      </div>
                    </List.Item>
                  );
                }}
              />
            )}
            <Typography.Text type="secondary">
              {result.data.alerts.length}{" "}
              条已持久化提醒；条件观察不授予交易资格。
            </Typography.Text>
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
