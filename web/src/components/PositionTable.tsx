import { Table, Tag, Typography } from "antd";
import type { PortfolioPosition } from "../types/api";
import { formatMoney, formatUnitPrice } from "../utils/format";

const SLEEVE_LABEL: Record<string, string> = {
  CORE_VALUE: "价值池",
  HOTSPOT_SATELLITE: "情绪卫星仓",
};

export function sleeveLabel(value?: string): string {
  if (!value) return "未提供";
  return SLEEVE_LABEL[value] ? `${SLEEVE_LABEL[value]} · ${value}` : value;
}

export function PositionTable({
  positions,
  title,
}: {
  positions: PortfolioPosition[];
  title: string;
}) {
  return (
    <>
      <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
        {title}
      </Typography.Title>
      <Table<PortfolioPosition>
        rowKey={(row) => `${row.symbol}-${row.exchange}`}
        dataSource={positions}
        pagination={false}
        scroll={{ x: 880 }}
        locale={{ emptyText: "暂无经人工确认的持仓" }}
        expandable={{
          expandedRowRender: (row) => (
            <Table
              rowKey="sleeve"
              size="small"
              pagination={false}
              dataSource={row.sleeves}
              columns={[
                {
                  title: "资金池",
                  dataIndex: "sleeve",
                  render: (value: string) => <Tag>{sleeveLabel(value)}</Tag>,
                },
                { title: "股数", dataIndex: "quantity", width: 110 },
                {
                  title: "可卖股数",
                  dataIndex: "sellable_quantity",
                  width: 110,
                },
                {
                  title: "下次可卖日",
                  dataIndex: "next_sell_session",
                  width: 140,
                  render: (value: string | null) => value || "T+1 已满足",
                },
                {
                  title: "分池成本",
                  dataIndex: "cost_cny",
                  width: 150,
                  render: (value: string | null) => formatMoney(value),
                },
              ]}
            />
          ),
        }}
        columns={[
          { title: "代码", dataIndex: "symbol", width: 100 },
          { title: "交易所", dataIndex: "exchange", width: 100 },
          { title: "总股数", dataIndex: "quantity", width: 110 },
          {
            title: "持仓成本",
            dataIndex: "cost_cny",
            width: 150,
            render: (value: string | null) => formatMoney(value),
          },
          {
            title: "每股成本",
            dataIndex: "average_cost_cny",
            width: 130,
            render: (value: string | null) => formatUnitPrice(value),
          },
          {
            title: "市值",
            dataIndex: "market_value_cny",
            width: 150,
            render: (value: string | null) =>
              value ? formatMoney(value) : "行情未准入",
          },
          {
            title: "浮动盈亏",
            dataIndex: "floating_pnl_cny",
            width: 150,
            render: (value: string | null) =>
              value ? formatMoney(value) : "行情未准入",
          },
        ]}
      />
    </>
  );
}
