import { Link } from "@umijs/max";
import { Descriptions, Table, Tag } from "antd";
import type { PortfolioTrade } from "../types/api";
import { formatMoney, formatUnitPrice } from "../utils/format";
import { sleeveLabel } from "./PositionTable";

/** Original ledger references remain visible even when current research changes. */
export function ConfirmedTrades({ trades }: { trades: PortfolioTrade[] }) {
  return (
    <Table<PortfolioTrade>
      rowKey="transaction_id"
      dataSource={[...trades].reverse()}
      pagination={{ pageSize: 10 }}
      scroll={{ x: 1100 }}
      locale={{
        emptyText: "台账未记录已确认成交；不能据此推断是否在外部账户执行",
      }}
      expandable={{
        expandedRowRender: (row) => (
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: "decision",
                label: "成交时关联判断 ID",
                children: row.decision_id ?? "未关联",
              },
              {
                key: "research",
                label: "成交时研究版本（原记录）",
                children: row.research_version ?? "未关联",
              },
              {
                key: "publication",
                label: "成交时发布版本",
                children: row.publication_id ?? "原记录未提供",
              },
              {
                key: "confirmed",
                label: "本人确认时间",
                children: row.confirmed_at,
              },
              {
                key: "snapshot",
                label: "录入时保存的原判断",
                children: row.judgment_snapshot ? (
                  <div>
                    <div>
                      发布版本 {row.judgment_snapshot.publication_id}；保存时间{" "}
                      {row.judgment_snapshot.recorded_at}
                    </div>
                    <div>
                      原观察价{" "}
                      {row.judgment_snapshot.plan.entry_trigger_price ??
                        "未提供"}
                      ；原失效参考{" "}
                      {row.judgment_snapshot.plan.invalidation_price ??
                        "未提供"}
                      ；原证券资格{" "}
                      {row.judgment_snapshot.plan.formal_eligibility === true
                        ? "通过"
                        : "未通过"}
                    </div>
                    <div>
                      该快照保留录入时的判断，不能证明实际成交前已知这些条件。成交时个人风险未追溯核验。
                    </div>
                  </div>
                ) : (
                  "历史记录没有判断快照，不能用当前价格条件补写"
                ),
              },
              {
                key: "digest",
                label: "成交记录 SHA256",
                children: (
                  <span style={{ overflowWrap: "anywhere" }}>
                    {row.record_sha256 ?? "未提供"}
                  </span>
                ),
              },
              {
                key: "current",
                label: "后续复核",
                children: row.decision_id ? (
                  <Link
                    to={`/decisions/${encodeURIComponent(row.decision_id)}`}
                  >
                    查看当前操作逻辑（不代表成交时版本）
                  </Link>
                ) : (
                  "无已绑定判断"
                ),
              },
            ]}
          />
        ),
      }}
      columns={[
        { title: "成交日", dataIndex: "trade_date", width: 120 },
        { title: "代码", dataIndex: "symbol", width: 100 },
        {
          title: "方向",
          dataIndex: "side",
          width: 80,
          render: (value) =>
            value === "BUY" ? "买入" : value === "SELL" ? "卖出" : value,
        },
        {
          title: "资金池",
          dataIndex: "sleeve",
          width: 190,
          render: (value) => <Tag>{sleeveLabel(value)}</Tag>,
        },
        { title: "实际股数", dataIndex: "quantity", width: 110 },
        {
          title: "实际成交价",
          dataIndex: "price_cny",
          width: 130,
          render: formatUnitPrice,
        },
        {
          title: "实际费用",
          dataIndex: "fees_cny",
          width: 110,
          render: formatMoney,
        },
        {
          title: "原研究版本",
          dataIndex: "research_version",
          render: (value) => value ?? "未关联",
        },
        { title: "成交编号", dataIndex: "transaction_id" },
      ]}
    />
  );
}
