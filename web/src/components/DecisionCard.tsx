import { Link } from "@umijs/max";
import { Card, Descriptions, Space, Tag, Typography } from "antd";
import type { DecisionItem } from "../types/api";
import { describeCode, strategyText } from "../utils/codes";
import { leaves } from "./DetailSection";

const DETAIL_PREVIEW_LINES = 4;

function EvidenceLines({ value, empty }: { value: unknown; empty: string }) {
  const lines = leaves(value);
  if (!lines.length)
    return <Typography.Text type="secondary">{empty}</Typography.Text>;
  const preview = lines.slice(0, DETAIL_PREVIEW_LINES);
  const rest = lines.length - preview.length;
  return (
    <div style={{ overflowWrap: "anywhere" }}>
      {preview.map((line, index) => (
        <div key={index}>{line}</div>
      ))}
      {rest > 0 && (
        <Typography.Text type="secondary">
          另有 {rest} 条依据，见操作逻辑详情
        </Typography.Text>
      )}
    </div>
  );
}

/** 每日候选卡片：只渲染接口返回的内容，缺失字段明确标注。 */
export function DecisionCard({ item }: { item: DecisionItem }) {
  const blockers = item.blockers ?? [];
  const channels = item.channels ?? [];
  return (
    <Card
      size="small"
      style={{ marginTop: 12 }}
      title={
        <Space wrap size={8}>
          <Link to={"/decisions/" + encodeURIComponent(item.id)}>
            {item.name || item.symbol || item.id}
          </Link>
          <Tag>{strategyText(item.strategy)}</Tag>
          <Tag>{describeCode(item.status)}</Tag>
        </Space>
      }
    >
      <Descriptions
        size="small"
        column={2}
        colon={false}
        labelStyle={{ color: "#5c6b73", whiteSpace: "nowrap" }}
        items={[
          {
            key: "why",
            label: "为什么关注",
            span: 2,
            children: item.reason || item.why_selected || "接口未返回关注原因",
          },
          {
            key: "action",
            label: "研究动作",
            children: item.candidate_action
              ? describeCode(item.candidate_action)
              : "接口未返回研究动作",
          },
          {
            key: "admission",
            label: "是否已通过正式准入",
            children: item.status
              ? describeCode(item.status)
              : "接口未返回准入状态",
          },
          {
            key: "support",
            label: "关键支持证据",
            span: 2,
            children: (
              <EvidenceLines
                value={item.support}
                empty="接口未返回可核验的支持证据"
              />
            ),
          },
          {
            key: "counter",
            label: "最大反证",
            span: 2,
            children: (
              <EvidenceLines
                value={item.counter_evidence}
                empty="接口未返回可核验的反证"
              />
            ),
          },
          {
            key: "missing",
            label: "目前还缺什么",
            span: 2,
            children: blockers.length
              ? blockers.join("；")
              : "接口未返回缺失项清单",
          },
          {
            key: "next",
            label: "下一次触发复核的条件",
            span: 2,
            children: (
              <EvidenceLines
                value={item.next_events}
                empty="接口未返回触发条件"
              />
            ),
          },
        ]}
      />
      <details style={{ marginTop: 8 }}>
        <summary style={{ cursor: "pointer", color: "#5c6b73" }}>
          技术详情（原始代码）
        </summary>
        <ul
          style={{
            margin: "8px 0 0",
            paddingLeft: 18,
            fontSize: 12,
            lineHeight: 1.8,
          }}
        >
          <li>id: {item.id}</li>
          <li>status: {item.status ?? "未提供"}</li>
          <li>candidate_action: {item.candidate_action ?? "未提供"}</li>
          <li>blockers: {blockers.length ? blockers.join(", ") : "无"}</li>
          <li>channels: {channels.length ? channels.join(", ") : "无"}</li>
        </ul>
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
          {JSON.stringify(item, null, 2)}
        </pre>
      </details>
    </Card>
  );
}
