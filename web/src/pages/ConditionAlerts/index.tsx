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
import {
  CheckOutlined,
  CloseOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useCallback, useState } from "react";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { formatUnitPrice } from "../../utils/format";

function shanghaiTime(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        dateStyle: "short",
        timeStyle: "medium",
        hour12: false,
      }).format(date)
    : "时间不可核验";
}

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
  const operate = async (
    alertId: string,
    operation: "acknowledge" | "cancel" | "expire",
  ) => {
    const snapshot = result.data?.snapshot_sha256;
    if (!testOnly || !snapshot || pending) return;
    setPending(alertId);
    setInteraction(undefined);
    try {
      if (operation === "acknowledge")
        await api.acknowledgeConditionAlert(alertId, snapshot);
      else await api.transitionConditionAlert(alertId, operation, snapshot);
      setInteraction({
        error: false,
        text:
          operation === "acknowledge"
            ? "已记录阅读确认；未批准研究或交易。"
            : operation === "cancel"
              ? "已取消本条通知；原风险与研究待办仍保留。"
              : "已记录通知到期；原风险与研究待办仍保留。",
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
            {result.data.condition && (
              <Typography.Paragraph style={{ marginTop: 16 }}>
                {result.data.condition.symbol} ·{" "}
                {result.data.condition.strategy === "CORE_VALUE"
                  ? "价值投资"
                  : "热点波段"}{" "}
                ·{" "}
                {result.data.condition.input_kind === "QUOTE"
                  ? "报价观察"
                  : `${result.data.condition.period} 完成收线观察`}
                ：{result.data.condition.operator === "GT" ? "高于" : "低于"}{" "}
                {formatUnitPrice(result.data.condition.threshold)}{" "}
                元时复核。此条件不代表买卖许可。
              </Typography.Paragraph>
            )}
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
                  const terminalLabel = acknowledged
                    ? "已阅"
                    : alert?.status === "CANCELLED"
                      ? "通知已取消"
                      : alert?.status === "EXPIRED"
                        ? "通知已到期"
                        : undefined;
                  return (
                    <List.Item>
                      <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                        <Space wrap>
                          <Typography.Text strong>
                            {event.symbol}
                          </Typography.Text>
                          <Tag>
                            {eventLabels[event.event_type] ?? "条件复核"}
                          </Tag>
                          <Typography.Text>
                            {shanghaiTime(event.detected_at)}（北京时间）
                          </Typography.Text>
                        </Space>
                        <p>请结合本次观测与原计划复核；此记录不批准交易。</p>
                        {terminalLabel ? (
                          <Tag color={acknowledged ? "green" : "default"}>
                            {terminalLabel}
                          </Tag>
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
                              onConfirm={() =>
                                operate(alert.alert_id, "acknowledge")
                              }
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
                        {testOnly &&
                          alert &&
                          result.data?.snapshot_sha256 &&
                          !terminalLabel && (
                            <Space wrap style={{ marginLeft: 8 }}>
                              {(["cancel", "expire"] as const)
                                .filter((operation) =>
                                  alert.available_operations.includes(
                                    operation.toUpperCase(),
                                  ),
                                )
                                .map((operation) => (
                                  <Popconfirm
                                    key={operation}
                                    title={
                                      operation === "cancel"
                                        ? "取消本条通知？"
                                        : "按交易日收盘期限确认通知到期？"
                                    }
                                    description="仅终止这条通知；原风险、研究待办及历史继续保留。"
                                    okText="确认"
                                    cancelText="返回"
                                    onConfirm={() =>
                                      operate(alert.alert_id, operation)
                                    }
                                  >
                                    <Button
                                      icon={
                                        operation === "cancel" ? (
                                          <CloseOutlined />
                                        ) : (
                                          <ClockCircleOutlined />
                                        )
                                      }
                                      disabled={!!pending}
                                    >
                                      {operation === "cancel"
                                        ? "取消通知"
                                        : "标记到期"}
                                    </Button>
                                  </Popconfirm>
                                ))}
                            </Space>
                          )}
                        <details>
                          <summary>查看来源与记录</summary>
                          {alert?.expiry_at && (
                            <p>
                              价格观察通知期限：{shanghaiTime(alert.expiry_at)}
                              （北京时间）。到期不解除风险复核。
                            </p>
                          )}
                          {event.effective_at && (
                            <p>
                              来源时间：{shanghaiTime(event.effective_at)}
                              （北京时间）
                            </p>
                          )}
                          {event.evidence_refs?.map((ref, index) => {
                            if (
                              !ref.source_url ||
                              !/^https?:\/\//.test(ref.source_url)
                            )
                              return null;
                            return (
                              <p
                                key={index}
                                style={{ overflowWrap: "anywhere" }}
                              >
                                <Typography.Link
                                  href={ref.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  原始来源
                                </Typography.Link>
                                {ref.sha256 && (
                                  <span> · SHA-256：{ref.sha256}</span>
                                )}
                              </p>
                            );
                          })}
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
