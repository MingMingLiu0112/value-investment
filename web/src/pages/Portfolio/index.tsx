import {
  Alert,
  Button,
  Col,
  Descriptions,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { DualSleeveRisk } from "../../components/DualSleeveRisk";
import { FillPanel } from "../../components/FillPanel";
import { PortfolioSetupForm } from "../../components/PortfolioSetupForm";
import { PositionTable, sleeveLabel } from "../../components/PositionTable";
import { RemoteState } from "../../components/RemoteState";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { ApiError, api } from "../../services/api";
import type { PortfolioTrade } from "../../types/api";
import { formatMoney } from "../../utils/format";

function failureMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError)
    return `${cause.code}：${String(cause.detail ?? "")}`;
  return cause instanceof Error ? cause.message : fallback;
}

export default function Portfolio() {
  const { data, loading, error, retry } = useApi(api.portfolio);
  const risk = useApi(api.risk);
  const [failure, setFailure] = useState<string>();
  const [reconciling, setReconciling] = useState(false);

  const refreshAll = () => {
    retry();
    risk.retry();
  };

  const reconcile = async () => {
    if (!data) return;
    setReconciling(true);
    setFailure(undefined);
    try {
      await api.reconcile({
        idempotency_key: crypto.randomUUID(),
        expected_revision: data.revision,
        reconciled_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
        confirmation_note: "工作台人工对账",
      });
      refreshAll();
    } catch (cause) {
      setFailure(failureMessage(cause, "对账失败"));
    } finally {
      setReconciling(false);
    }
  };

  return (
    <Workbench>
      <Typography.Title level={2}>我的持仓</Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data && (
          <>
            {failure && (
              <Alert
                type="error"
                showIcon
                message="操作未完成"
                description={failure}
                style={{ marginBottom: 16 }}
              />
            )}
            <Alert
              type="info"
              showIcon
              message={`行情准入：${data.valuation.status}`}
              description={data.valuation.reason}
            />
            {data.status === "NOT_CONNECTED" ? (
              <>
                <Alert
                  style={{ marginTop: 16 }}
                  type="warning"
                  showIcon
                  message="私人组合尚未接入（NOT_CONNECTED）"
                  description="持仓、现金与成本均未经核对，因此不显示任何仓位建议。请在下方逐笔人工确认初始持仓。"
                />
                <PortfolioSetupForm onDone={refreshAll} />
              </>
            ) : (
              <>
                <Row gutter={24} style={{ marginTop: 24 }}>
                  <Col span={6}>
                    <Statistic
                      title="可用现金（元）"
                      value={data.cash_cny ?? "未提供"}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title="已实现盈亏（元）"
                      value={data.realized_pnl_cny ?? "未提供"}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic title="台账版本" value={data.revision} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="已确认成交" value={data.trades.length} />
                  </Col>
                </Row>
                <Descriptions
                  bordered
                  column={2}
                  style={{ marginTop: 16 }}
                  items={[
                    {
                      key: "as_of",
                      label: "持仓基准日",
                      children: data.as_of || "未提供",
                    },
                    {
                      key: "blockers",
                      label: "当前阻塞",
                      children: data.blockers.length ? (
                        <Space wrap>
                          {data.blockers.map((item) => (
                            <Tag key={item}>{item}</Tag>
                          ))}
                        </Space>
                      ) : (
                        "无"
                      ),
                    },
                  ]}
                />
                {data.policy && (
                  <Descriptions
                    title="已记录的风险约束（原始输入）"
                    bordered
                    column={2}
                    style={{ marginTop: 16 }}
                    items={Object.entries(data.policy).map(([key, value]) => ({
                      key,
                      label: key,
                      children: String(value ?? "未提供"),
                    }))}
                  />
                )}
                <PositionTable title="已确认持仓" positions={data.positions} />
                <Typography.Title
                  level={4}
                  style={{ fontSize: 16, marginTop: 24 }}
                >
                  已确认成交记录
                </Typography.Title>
                <Table<PortfolioTrade>
                  rowKey="transaction_id"
                  dataSource={data.trades}
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 900 }}
                  locale={{ emptyText: "暂无已确认成交" }}
                  columns={[
                    { title: "成交编号", dataIndex: "transaction_id" },
                    { title: "方向", dataIndex: "side", width: 90 },
                    {
                      title: "资金池",
                      dataIndex: "sleeve",
                      width: 210,
                      render: (value: string) => (
                        <Tag>{sleeveLabel(value)}</Tag>
                      ),
                    },
                    { title: "代码", dataIndex: "symbol", width: 100 },
                    { title: "股数", dataIndex: "quantity", width: 100 },
                    {
                      title: "价格",
                      dataIndex: "price_cny",
                      width: 120,
                      render: (value: string | null) => formatMoney(value),
                    },
                    {
                      title: "费用",
                      dataIndex: "fees_cny",
                      width: 100,
                      render: (value: string | null) => formatMoney(value),
                    },
                    { title: "成交日", dataIndex: "trade_date", width: 120 },
                  ]}
                />
                <FillPanel
                  revision={data.revision}
                  draft={data.pending_draft}
                  onDone={refreshAll}
                />
                <Space style={{ marginTop: 24 }}>
                  <Button
                    onClick={reconcile}
                    loading={reconciling}
                    disabled={data.trades.length === 0}
                  >
                    生成对账快照
                  </Button>
                  <Button onClick={refreshAll}>刷新</Button>
                </Space>
              </>
            )}
            <DualSleeveRisk
              data={risk.data}
              loading={risk.loading}
              error={risk.error}
              retry={risk.retry}
            />
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
