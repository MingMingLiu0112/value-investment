import { Alert, Table } from "antd";
import { api } from "../services/api";
import { useApi } from "../hooks/useApi";

export function ActualAccountObservations() {
  const result = useApi(api.accountObservations);
  if (result.loading) return <p>正在核验实盘账户持仓快照…</p>;
  if (result.error)
    return (
      <Alert
        type="warning"
        message="实盘账户快照暂不可核验，未改动账户账本。"
      />
    );
  if (
    !result.data ||
    result.data.action !== "no_order" ||
    !Array.isArray(result.data.accounts)
  )
    return null;
  return (
    <section aria-label="独立实盘账户持仓观察">
      {result.data.unavailable_count > 0 && (
        <Alert
          type="warning"
          message="部分账户截图或快照指纹异常，已停止展示对应账户。"
        />
      )}
      {result.data.accounts
        .filter(
          (account) =>
            account.active_trading_ledger === false &&
            account.trade_eligible === false,
        )
        .map((account) => (
          <section key={account.snapshot_sha256} style={{ marginBlock: 20 }}>
            <h3>{account.account_label} · 实盘持仓观察</h3>
            <p>
              {account.snapshot_date} {account.displayed_clock_time} ·
              用户提供的券商截图，不是实时行情。股数由市值和价格推算，可卖数量未知。
            </p>
            <p>
              总资产 {account.observed_totals.total_assets_cny} 元 · 股票市值{" "}
              {account.observed_totals.securities_market_value_cny} 元 ·
              可用资金 {account.observed_totals.available_funds_cny} 元 ·
              显示仓位 {account.observed_totals.displayed_position_pct}%
            </p>
            <Table
              size="small"
              rowKey="symbol"
              pagination={false}
              scroll={{ x: 720 }}
              dataSource={account.holdings}
              columns={[
                {
                  title: "股票",
                  render: (_, row) => `${row.name} ${row.symbol}`,
                },
                { title: "推算股数", dataIndex: "quantity_inferred" },
                {
                  title: "券商成本/股",
                  dataIndex: "displayed_cost_per_share_cny",
                },
                { title: "截图价格", dataIndex: "displayed_price_cny" },
                { title: "截图市值", dataIndex: "market_value_cny" },
                { title: "显示仓位%", dataIndex: "displayed_weight_pct" },
              ]}
            />
            <p>
              历史持仓暂未分配长线/波段策略，未并入其他账户。尚未核验买入日期、可卖数量与原始买入逻辑，不生成可操作股数。
            </p>
            <details>
              <summary>截图对账与版本</summary>
              <p>
                顶部市值与逐股合计差额：
                {account.reconciliation.header_market_value_minus_rows_cny}{" "}
                元；总资产与顶部市值、可用资金差额：
                {
                  account.reconciliation
                    .total_assets_minus_header_market_value_and_available_funds_cny
                }{" "}
                元。原样保留，未补成现金或费用。
              </p>
              <p style={{ overflowWrap: "anywhere" }}>
                快照 SHA-256：{account.snapshot_sha256}
              </p>
            </details>
          </section>
        ))}
    </section>
  );
}
