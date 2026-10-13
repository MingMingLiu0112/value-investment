import { Alert, Descriptions, List, Table, Tag, Typography } from "antd";
import type {
  RiskEngineReport,
  RiskEngineSleeveReview,
  RiskFacts,
  RiskFactsPosition,
  RiskResponse,
} from "../types/api";
import {
  codeText,
  describeCode,
  engineAlertText,
  reconciliationText,
} from "../utils/codes";
import { formatMoney } from "../utils/format";
import { RemoteState } from "./RemoteState";

const PRICE_UNKNOWN = "未知（未接入经核验行情）";
type SleeveRow = { key: string } & RiskEngineSleeveReview;

const SLEEVE_TEXT: Record<string, string> = {
  CORE_VALUE: "价值池",
  HOTSPOT_SATELLITE: "情绪卫星仓",
};

function sleeveText(value: string): string {
  return SLEEVE_TEXT[value] ?? value;
}

function money(value?: string | number | null): string {
  return formatMoney(value);
}

function FactsBlock({ facts }: { facts: RiskFacts }) {
  return (
    <>
      <Descriptions
        bordered
        size="small"
        column={3}
        items={[
          {
            key: "scope",
            label: "账户口径",
            children: facts.account_scope || "未提供",
          },
          {
            key: "as_of",
            label: "持仓基准日",
            children: facts.as_of || "未提供",
          },
          { key: "revision", label: "台账修订", children: facts.revision },
          { key: "cash", label: "现金（元）", children: money(facts.cash_cny) },
          {
            key: "cost",
            label: "成本口径资金占用（元）",
            children: money(facts.cost_basis_total_cny),
          },
          {
            key: "fills",
            label: "已确认成交数",
            children: facts.confirmed_fill_count,
          },
          {
            key: "reconcile",
            label: "对账状态",
            children: reconciliationText(facts.reconciliation_status),
          },
          {
            key: "price",
            label: "行情状态",
            children: describeCode(facts.price_status),
          },
        ]}
      />
      {facts.price_reason && (
        <Typography.Text
          type="secondary"
          style={{ display: "block", marginTop: 8 }}
        >
          {facts.price_reason}
        </Typography.Text>
      )}
      <Table<RiskFactsPosition>
        size="small"
        rowKey={(row) => row.symbol + "-" + row.exchange}
        dataSource={facts.positions}
        pagination={false}
        style={{ marginTop: 12 }}
        scroll={{ x: 900 }}
        locale={{ emptyText: "暂无经确认的持仓" }}
        columns={[
          { title: "代码", dataIndex: "symbol", width: 100 },
          { title: "交易所", dataIndex: "exchange", width: 90 },
          { title: "总股数", dataIndex: "quantity", width: 90 },
          {
            title: "成本口径（元）",
            dataIndex: "cost_basis_cny",
            width: 150,
            render: (value: string) => money(value),
          },
          {
            title: "各资金池股数",
            dataIndex: "sleeves",
            render: (rows: RiskFactsPosition["sleeves"]) =>
              rows
                .map(
                  (row) => sleeveText(row.sleeve) + " " + row.quantity + " 股",
                )
                .join("；"),
          },
          {
            title: "市值",
            dataIndex: "market_value_cny",
            width: 170,
            render: (value: string | null) =>
              value ? money(value) : PRICE_UNKNOWN,
          },
          {
            title: "浮动盈亏",
            dataIndex: "unrealized_pnl_cny",
            width: 170,
            render: (value: string | null) =>
              value ? money(value) : PRICE_UNKNOWN,
          },
        ]}
      />
    </>
  );
}

function SleeveReviewTable({
  sleeves,
}: {
  sleeves: Record<string, RiskEngineSleeveReview>;
}) {
  const rows: SleeveRow[] = Object.entries(sleeves).map(([key, value]) => ({
    key,
    ...value,
  }));
  return (
    <Table<SleeveRow>
      size="small"
      rowKey="key"
      dataSource={rows}
      pagination={false}
      style={{ marginTop: 12 }}
      scroll={{ x: 900 }}
      columns={[
        {
          title: "资金池",
          dataIndex: "key",
          width: 150,
          render: (key: string) => <Tag>{sleeveText(key)}</Tag>,
        },
        {
          title: "预算（元）",
          dataIndex: "budget_cny",
          width: 130,
          render: (value: string) => money(value),
        },
        {
          title: "已用资金（元）",
          dataIndex: "used_funds_cny",
          width: 130,
          render: (value: string) => money(value),
        },
        {
          title: "可用资金（元）",
          dataIndex: "available_funds_cny",
          width: 130,
          render: (value: string) => money(value),
        },
        {
          title: "风险预算（元）",
          dataIndex: "risk_budget_cny",
          width: 130,
          render: (value: string) => money(value),
        },
        {
          title: "已承诺风险（元）",
          dataIndex: "committed_risk_cny",
          width: 140,
          render: (value: string | null) => (value ? money(value) : "未提供"),
        },
      ]}
    />
  );
}

function TradeNotice({ engine }: { engine: RiskEngineReport }) {
  const tradeable = engine.trade_eligible === true;
  return (
    <Alert
      style={{ marginTop: 12 }}
      type={tradeable ? "error" : "info"}
      showIcon
      message={
        tradeable ? "引擎声明可交易，请人工复核" : "仅供研究复核，不构成下单"
      }
      description={
        "引擎结论：trade_eligible=" +
        String(engine.trade_eligible) +
        "，acceptance_authority=" +
        String(engine.acceptance_authority) +
        "。工作台不会产生任何委托或仓位指令。"
      }
    />
  );
}

function EngineBlock({ data }: { data: RiskResponse }) {
  const engine = data.engine;
  if (data.status === "NOT_CONNECTED") {
    return (
      <Alert
        style={{ marginTop: 12 }}
        type="info"
        showIcon
        message="私人组合尚未接入"
        description="在确认初始持仓之前，双策略风险复核没有可用的现金、成本与持仓事实，不会给出任何风险数字。"
      />
    );
  }
  if (data.status === "BLOCKED_PRIVATE_INPUT") {
    return (
      <>
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message="双策略风险复核暂缓：还缺以下私人输入"
          description={
            <div>
              <p style={{ margin: "0 0 8px" }}>
                以下清单来自风险引擎的缺口列表；在补齐之前，引擎不会给出任何风险数字、仓位或交易建议。
              </p>
              <List
                size="small"
                dataSource={data.blockers}
                renderItem={(code) => (
                  <List.Item style={{ padding: "2px 0" }}>
                    □ {codeText(code) ?? code}
                  </List.Item>
                )}
              />
            </div>
          }
        />
        {engine && <TradeNotice engine={engine} />}
      </>
    );
  }
  if (
    data.status === "RISK_REVIEW_CALCULATED" ||
    data.status === "REVIEW_REQUIRED"
  ) {
    const sleeves = engine?.sleeves ?? null;
    const aggregate = engine?.aggregate ?? null;
    const alerts = engine?.blockers ?? [];
    return (
      <>
        <Alert
          style={{ marginTop: 12 }}
          type={data.status === "REVIEW_REQUIRED" ? "warning" : "success"}
          showIcon
          message={
            data.status === "REVIEW_REQUIRED"
              ? "风险复核已完成，但存在需要人工复核的事项"
              : "风险复核已完成"
          }
          description="以下数字由双策略风险引擎基于已确认的私人台账计算，仅供研究复核。"
        />
        {sleeves && Object.keys(sleeves).length > 0 && (
          <SleeveReviewTable sleeves={sleeves} />
        )}
        {aggregate && (
          <Descriptions
            bordered
            size="small"
            column={3}
            style={{ marginTop: 12 }}
            items={[
              {
                key: "total",
                label: "总资产（元）",
                children: money(aggregate.total_assets_cny),
              },
              {
                key: "cash",
                label: "现金（元）",
                children: money(aggregate.cash_cny),
              },
              {
                key: "reserve",
                label: "现金储备（元）",
                children: money(aggregate.reserve_cny),
              },
            ]}
          />
        )}
        {alerts.length > 0 && (
          <List
            size="small"
            bordered
            style={{ marginTop: 12 }}
            header={<Typography.Text strong>引擎提示</Typography.Text>}
            dataSource={alerts}
            renderItem={(code) => (
              <List.Item>{engineAlertText(code)}</List.Item>
            )}
          />
        )}
        {engine && <TradeNotice engine={engine} />}
      </>
    );
  }
  if (
    data.status === "PRIVATE_ROOT_UNAVAILABLE" ||
    data.status === "PRIVATE_JOURNAL_INVALID"
  ) {
    return (
      <Alert
        style={{ marginTop: 12 }}
        type="error"
        showIcon
        message={describeCode(data.status)}
        description="无法安全读取私人台账，已停止投影任何持仓与风险数字。"
      />
    );
  }
  return (
    <Alert
      style={{ marginTop: 12 }}
      type="info"
      showIcon
      message={"风险复核状态：" + describeCode(data.status)}
      description="当前没有可展示的风险引擎结论。"
    />
  );
}

export function DualSleeveRisk({
  data,
  loading,
  error,
  retry,
}: {
  data?: RiskResponse;
  loading: boolean;
  error?: string;
  retry: () => void;
}) {
  return (
    <section style={{ marginTop: 32 }}>
      <Typography.Title level={4} style={{ fontSize: 16 }}>
        双策略风险
      </Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data && (
          <>
            {data.facts && <FactsBlock facts={data.facts} />}
            <EngineBlock data={data} />
            <details style={{ marginTop: 8 }}>
              <summary style={{ cursor: "pointer", color: "#5c6b73" }}>
                技术详情（原始代码）
              </summary>
              <pre
                style={{
                  marginTop: 8,
                  maxHeight: 260,
                  overflow: "auto",
                  fontSize: 12,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {JSON.stringify(
                  {
                    status: data.status,
                    blockers: data.blockers,
                    engine: data.engine
                      ? {
                          status: data.engine.status,
                          blockers: data.engine.blockers,
                          trade_eligible: data.engine.trade_eligible,
                          acceptance_authority:
                            data.engine.acceptance_authority,
                        }
                      : null,
                    facts: data.facts
                      ? {
                          revision: data.facts.revision,
                          reconciliation_status:
                            data.facts.reconciliation_status,
                          price_status: data.facts.price_status,
                        }
                      : null,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        )}
      </RemoteState>
    </section>
  );
}
