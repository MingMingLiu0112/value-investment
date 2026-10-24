import { Alert, Button, Descriptions, Skeleton, Typography } from "antd";
import type { ResearchFunnelStatus } from "../types/api";
import {
  funnelBlockerText,
  funnelChannelRows,
  funnelEvidenceRows,
  funnelStatusText,
} from "../utils/research-funnel";

interface ResearchFunnelAuditPanelProps {
  funnel?: ResearchFunnelStatus;
  loading: boolean;
  error?: string;
  retry: () => void;
}

export function ResearchFunnelAuditPanel({
  funnel,
  loading,
  error,
  retry,
}: ResearchFunnelAuditPanelProps) {
  const rows = funnel ? funnelEvidenceRows(funnel) : [];
  const channels = funnel ? funnelChannelRows(funnel) : [];

  return (
    <section style={{ marginTop: 26 }}>
      <Typography.Title level={3}>全市场研究漏斗审计</Typography.Title>
      {loading && <Skeleton active paragraph={{ rows: 3 }} />}
      {error && (
        <Alert
          type="error"
          showIcon
          message={`漏斗审计读取失败：${error}`}
          action={<Button onClick={retry}>重试</Button>}
        />
      )}
      {!loading && !error && funnel && funnel.status !== "VERIFIED" && (
        <Alert
          type="warning"
          showIcon
          message={funnelStatusText(funnel.status)}
          description={`原因：${funnel.reason || "未提供"}`}
        />
      )}
      {!loading && !error && funnel?.status === "VERIFIED" && (
        <>
          <Alert
            type="warning"
            showIcon
            message="只读审计，不构成买卖建议"
            description="LEAD、通道 PASS 和研究队列入选均不代表正式估值通过，也不代表可以买入。"
          />
          <Descriptions
            bordered
            size="small"
            column={{ xs: 1, sm: 2 }}
            style={{ marginTop: 14 }}
            items={rows.map((row) => ({
              key: row.label,
              label: row.label,
              children: row.value,
            }))}
          />
          {funnel.blockers.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <Typography.Text strong>当前阻断事实</Typography.Text>
              <ul>
                {funnel.blockers.map((code) => (
                  <li key={code}>{funnelBlockerText(code)}</li>
                ))}
              </ul>
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <Typography.Text strong>四类通道</Typography.Text>
            <ul>
              {channels.map((row) => (
                <li key={row.key} style={{ marginBottom: 8 }}>
                  <strong>{row.channel}</strong>：通过 {row.passed}
                  {row.gap ? ` · ${row.gap}` : ""}
                  <div style={{ color: "rgba(0,0,0,.55)" }}>
                    首要原因：{row.reason}
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <details style={{ marginTop: 14 }}>
            <summary>审计依据与哈希</summary>
            <Descriptions
              bordered
              size="small"
              column={1}
              items={[
                {
                  key: "asof",
                  label: "审计截止",
                  children: funnel.as_of || "未提供",
                },
                {
                  key: "task",
                  label: "任务版本",
                  children: funnel.task_id || "未提供",
                },
                {
                  key: "review",
                  label: "人工复核",
                  children: funnel.review?.status || "未提供",
                },
                {
                  key: "audit",
                  label: "审计 SHA-256",
                  children: funnel.audit_sha256 || "未提供",
                },
                {
                  key: "manifest",
                  label: "Manifest",
                  children: funnel.artifacts?.manifest.path || "未提供",
                },
              ]}
            />
          </details>
        </>
      )}
    </section>
  );
}
