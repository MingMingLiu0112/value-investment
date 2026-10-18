import {
  Alert,
  Button,
  Empty,
  List,
  Popconfirm,
  Select,
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
  PlayCircleOutlined,
  PauseCircleOutlined,
} from "@ant-design/icons";
import { useCallback, useEffect, useState } from "react";
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

const observationLabels: Record<string, string> = {
  LOCAL_PUBLIC_OBSERVATION_ONLY: "仅观测公开报价；不会产生正式提醒或投资许可。",
  LOCAL_PUBLIC_OBSERVATION_STOPPED: "本次观测已停止，原始来源与记录继续保留。",
  WAITING_FOR_IN_FLIGHT_COLLECTION:
    "正在停止；等待已发出的请求结束，不再发起后续采集。",
  RETAINED_OBSERVATIONS_NO_LOCAL_WORKER:
    "仅显示历史记录；当前服务没有运行观测任务。",
  WORKER_FAILED: "观测任务失败，暂停价格判断。",
  WORKER_OR_STORAGE_FAILED: "观测或存储失败，请检查本地运行状态。",
  RETAINED_EVIDENCE_VERIFICATION_FAILED: "留存原件校验失败，不能使用观测结果。",
  OUTSIDE_EXCHANGE_SESSION: "当前不在交易时段，不能据此判断盘中条件。",
  COLLECTION_OR_EVIDENCE_FAILED: "采集或原始证据核验失败。",
  CROSS_SOURCE_PRICE_CONFLICT: "两个来源的价格不一致。",
  STALE_QUOTE: "报价已过期。",
  DUAL_PROVIDER_EXACT_PRICE_MATCH: "双源价格一致，仍需结合原策略条件复核。",
  EXPLICIT_PRICE_CONDITION_MATCHED: "观测报价已越过参考价，需要复核。",
  EXPLICIT_PRICE_CONDITION_NOT_MATCHED: "观测报价尚未越过参考价。",
  DATA_UNAVAILABLE: "缺少可用报价，暂停条件判断。",
  PLAN_REFERENCE_EXPIRED: "原价格计划已过期，需要更新计划后再观察。",
  QUOTE_PRECEDES_PLAN_AVAILABILITY: "报价早于计划可用时间，不能据此验证条件。",
  STALE_OR_CONFLICTING_CLOCK: "报价过期或时间不一致，暂停条件判断。",
};

const conditionStatusLabels: Record<string, string> = {
  NOT_TRIGGERED: "未满足参考价条件",
  STRUCTURE_OBSERVATION: "报价越过参考价，等待收线复核",
  RISK_REVIEW: "报价跌破失效参考，需风险复核",
  CONDITION_REVIEW: "条件需复核",
  STALE_OR_UNAVAILABLE: "数据不可用，暂停判断",
};

function referenceLabel(kind: string) {
  return kind === "INVALIDATION_REFERENCE_LT" ? "失效参考" : "突破参考";
}

function referenceNextStep(value?: string) {
  if (
    value ===
    "REVIEW_EXISTING_INVALIDATION_WITH_COMPLETED_BAR_STRATEGY_AND_PRIVATE_GATES"
  )
    return "先核对已完成K线和原失效规则，再复核实际持仓与可卖数量；当前不构成卖出许可。";
  if (value === "AWAIT_COMPLETED_BAR_AND_EXISTING_STRATEGY_CONFIRMATION")
    return "等待已完成K线与量价条件确认，再检查策略、事件及个人风险资格；当前不构成买入许可。";
  if (value === "RESTORE_VERIFIED_PLAN_AND_FRESH_QUOTE")
    return "先恢复可核验的有效计划和新鲜报价，当前暂停判断。";
  return "继续观察原参考价条件；不授予交易许可。";
}

export default function ConditionAlerts() {
  const [testOnly, setTestOnly] = useState(false);
  const [pending, setPending] = useState<string>();
  const [symbol, setSymbol] = useState<string>();
  const [interaction, setInteraction] = useState<{
    error: boolean;
    text: string;
  }>();
  const load = useCallback(
    (signal: AbortSignal) => api.conditionAlerts(testOnly, signal),
    [testOnly],
  );
  const result = useApi(load);
  useEffect(() => {
    if (
      testOnly ||
      result.loading ||
      !result.data?.monitor_running ||
      result.error
    )
      return;
    const timer = window.setTimeout(result.retry, 5000);
    return () => window.clearTimeout(timer);
  }, [testOnly, result.loading, result.data, result.error, result.retry]);
  const controlObservation = async (operation: "start" | "stop") => {
    if (pending || testOnly) return;
    setPending("public-observation");
    setInteraction(undefined);
    try {
      const state = await api.controlPublicObservation(
        operation,
        symbol,
        result.data?.public_observation?.session_id,
      );
      setInteraction({
        error: false,
        text:
          observationLabels[state.detail ?? ""] ?? "已更新公开行情观测状态。",
      });
    } catch (error) {
      setInteraction({
        error: true,
        text: error instanceof Error ? error.message : "操作失败，请刷新。",
      });
    } finally {
      setPending(undefined);
      result.retry();
    }
  };
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
                result.data.monitor_running
                  ? "本地公开报价观测中"
                  : "监控未运行"
              }
              description={
                result.data.detail ??
                "仅展示已经留存的历史记录；关闭本地进程后不会持续监控。"
              }
            />
            {!testOnly && result.data.public_observation && (
              <section style={{ marginTop: 16 }}>
                <Typography.Title level={4}>公开行情观测</Typography.Title>
                {result.data.public_observation.choices_status ===
                  "UNAVAILABLE" && (
                  <Alert
                    type="warning"
                    message={result.data.public_observation.choices_detail}
                  />
                )}
                <Typography.Paragraph>
                  {observationLabels[
                    result.data.public_observation.detail ?? ""
                  ] ?? result.data.public_observation.detail}
                </Typography.Paragraph>
                <Space wrap>
                  <Select
                    aria-label="观测证券"
                    placeholder="选择当前候选"
                    style={{ width: 220, maxWidth: "100%" }}
                    value={symbol}
                    disabled={!!pending || result.data.monitor_running}
                    onChange={setSymbol}
                    options={(result.data.public_observation.choices ?? []).map(
                      (item) => ({
                        value: item.symbol,
                        label: `${item.symbol} ${item.company_name}`,
                      }),
                    )}
                  />
                  <Popconfirm
                    title="启动本机有界公开行情观测？"
                    description="每分钟检查，最多十次；按当前计划比较参考价，报价变化不替代收线和风险确认。服务重启后不自动恢复。"
                    okText="启动观测"
                    cancelText="返回"
                    onConfirm={() => controlObservation("start")}
                  >
                    <Button
                      icon={<PlayCircleOutlined />}
                      disabled={
                        !symbol ||
                        !!pending ||
                        result.data.monitor_running ||
                        result.data.public_observation.choices_status ===
                          "UNAVAILABLE"
                      }
                    >
                      启动观测
                    </Button>
                  </Popconfirm>
                  <Button
                    icon={<PauseCircleOutlined />}
                    disabled={!!pending || !result.data.monitor_running}
                    onClick={() => controlObservation("stop")}
                  >
                    停止观测
                  </Button>
                  <Tag>{result.data.public_observation.status}</Tag>
                </Space>
                {result.data.public_observation.condition_observation && (
                  <section style={{ marginTop: 16 }}>
                    <Typography.Title level={4}>
                      计划参考价复核
                    </Typography.Title>
                    <Typography.Paragraph>
                      以下是观测当时的结果，停止观测后不代表当前价格。报价越过参考价仍须完成收线、事件、策略及个人风险复核。
                    </Typography.Paragraph>
                    <List
                      dataSource={
                        result.data.public_observation.condition_observation
                          .states
                      }
                      renderItem={(item) => (
                        <List.Item>
                          <div
                            style={{ minWidth: 0, overflowWrap: "anywhere" }}
                          >
                            <Typography.Text strong>
                              {referenceLabel(item.kind)}：
                              {item.condition.operator === "GT"
                                ? "高于"
                                : "低于"}{" "}
                              {formatUnitPrice(item.condition.threshold)} 元
                            </Typography.Text>
                            <p>
                              {conditionStatusLabels[
                                item.status ?? item.state.status
                              ] ?? "需要复核"}
                            </p>
                            <p>
                              {observationLabels[
                                item.reason ?? item.state.reason
                              ] ??
                                item.reason ??
                                item.state.reason}{" "}
                              · {shanghaiTime(item.state.checked_at)}
                              （北京时间）
                            </p>
                            <p>{referenceNextStep(item.next_step)}</p>
                          </div>
                        </List.Item>
                      )}
                    />
                    <Typography.Link
                      href={`/decisions/hotspot-${result.data.public_observation.symbol}?independent_hotspot=true`}
                    >
                      查看原价格计划与未满足的条件
                    </Typography.Link>
                    <details style={{ marginTop: 12 }}>
                      <summary>本次观测的条件变化历史</summary>
                      <List
                        dataSource={
                          result.data.public_observation
                            .condition_transitions ?? []
                        }
                        locale={{
                          emptyText: "没有新增条件变化；相同状态不会重复提醒",
                        }}
                        renderItem={(item) => (
                          <List.Item>
                            <div
                              style={{ minWidth: 0, overflowWrap: "anywhere" }}
                            >
                              {referenceLabel(item.kind)} ·{" "}
                              {conditionStatusLabels[item.status] ?? "需要复核"}
                              <p>{shanghaiTime(item.checked_at)}（北京时间）</p>
                              <p>
                                {item.price
                                  ? `观测价 ${formatUnitPrice(item.price)} 元；`
                                  : "无可用报价；"}
                                参考价 {formatUnitPrice(item.threshold)} 元
                              </p>
                              <p>{referenceNextStep(item.next_step)}</p>
                            </div>
                          </List.Item>
                        )}
                      />
                    </details>
                  </section>
                )}
                <List
                  dataSource={result.data.public_observation.samples}
                  locale={{ emptyText: "尚无真实公开行情观测记录" }}
                  renderItem={(sample) => (
                    <List.Item>
                      <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                        <Typography.Text strong>
                          {sample.symbol}
                        </Typography.Text>
                        {" · "}
                        {shanghaiTime(sample.checked_at)}（北京时间）
                        <p>
                          {sample.status === "QUOTE_VERIFIED"
                            ? "双源报价核验通过"
                            : "暂停价格判断"}
                          ：{observationLabels[sample.reason] ?? sample.reason}
                        </p>
                        {sample.observation?.price && (
                          <p>
                            观测价格：
                            {formatUnitPrice(sample.observation.price)} 元
                          </p>
                        )}
                        <details>
                          <summary>原始来源与校验</summary>
                          {sample.source_refs.map((source, index) => (
                            <p key={`${source.sha256}-${index}`}>
                              <a
                                href={source.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                公开来源 {index + 1}
                              </a>
                              {" · SHA-256: "}
                              {source.sha256}
                            </p>
                          ))}
                        </details>
                      </div>
                    </List.Item>
                  )}
                />
              </section>
            )}
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
