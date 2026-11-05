import { ProTable } from "@ant-design/pro-components";
import { Link } from "@umijs/max";
import { Tag } from "antd";
import type { DecisionItem } from "../types/api";
import { statusLabel } from "../utils/presentation";

export function DecisionTable({
  title,
  items,
  empty,
}: {
  title: string;
  items: DecisionItem[];
  empty: string;
}) {
  return (
    <section style={{ marginTop: 28 }}>
      <h2 style={{ fontSize: 18 }}>{title}</h2>
      <ProTable<DecisionItem>
        rowKey="id"
        search={{ labelWidth: "auto" }}
        options={{ density: true, reload: false, setting: false }}
        pagination={{ pageSize: 10 }}
        dataSource={items}
        locale={{ emptyText: empty }}
        scroll={{ x: 780 }}
        columns={[
          {
            title: "证券",
            dataIndex: "name",
            width: 140,
            ellipsis: true,
            sorter: (a, b) =>
              String(a.name || a.symbol || "").localeCompare(
                String(b.name || b.symbol || ""),
                "zh-CN",
              ),
            render: (_, item) => (
              <Link to={`/decisions/${encodeURIComponent(item.id)}`}>
                {item.name || item.symbol || item.id}
              </Link>
            ),
          },
          {
            title: "代码",
            dataIndex: "symbol",
            width: 100,
            render: (_, item) => item.symbol || item.id,
          },
          { title: "策略", dataIndex: "strategy", width: 110, search: false },
          {
            title: "当前状态",
            dataIndex: "status",
            width: 180,
            search: false,
            filters: [
              ...new Set(
                items
                  .map((item) => item.status)
                  .filter((value): value is string => !!value),
              ),
            ].map((value) => ({ text: statusLabel(value), value })),
            onFilter: (value, item) => item.status === value,
            render: (_, item) => <Tag>{statusLabel(item.status)}</Tag>,
          },
          {
            title: "复核动作",
            dataIndex: "candidate_action",
            width: 180,
            search: false,
            render: (_, item) => statusLabel(item.candidate_action),
          },
          {
            title: "主要原因",
            dataIndex: "reason",
            ellipsis: true,
            search: false,
            renderText: (value) => value || "暂无可验证说明",
          },
        ]}
      />
    </section>
  );
}
