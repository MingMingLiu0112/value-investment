import { useCallback } from "react";
import { Alert, Descriptions, Typography } from "antd";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { RemoteState } from "../../components/RemoteState";

export function AgentResearchPanel({ symbol }: { symbol: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.agentResearch(symbol, signal),
    [symbol],
  );
  const { data, loading, error, retry } = useApi(load);
  return (
    <details style={{ marginTop: 12 }}>
      <summary>AI 研究材料、反证与来源</summary>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data?.status !== "VERIFIED" ? (
          <Alert
            type="info"
            message="暂无已绑定的 AI 研究材料"
            description={data?.reason}
          />
        ) : (
          <>
            <Alert
              type="warning"
              showIcon
              message="材料绑定已核验，研究草案待复核"
              description="以下为保留的研究材料，不代表当前研究结论、正式批准或交易许可。"
            />
            <Descriptions
              column={1}
              size="small"
              items={[
                {
                  key: "mode",
                  label: "研究方式",
                  children:
                    data.mode === "MOCK"
                      ? "Mock 模拟研究（历史材料）"
                      : data.mode === "OFFLINE_REPLAY"
                        ? "离线回放（历史材料）"
                        : "已保留的大模型研究材料",
                },
                {
                  key: "asof",
                  label: "研究截止时点",
                  children: data.research_as_of || "未提供",
                },
                {
                  key: "model",
                  label: "模型",
                  children: data.model_id || "未提供",
                },
              ]}
            />
            {data.findings.map((finding) => (
              <section key={finding.finding_id}>
                <Typography.Title level={5}>
                  {(
                    {
                      FUNDAMENTAL: "基本面",
                      COUNTER_EVIDENCE: "反面证据",
                      EVENT: "事件研究",
                    } as Record<string, string>
                  )[finding.role] || finding.role}
                </Typography.Title>
                <p>{finding.claim}</p>
                <p>支持依据：{finding.evidence_refs.join("、") || "未列出"}</p>
                <p>
                  反证依据：
                  {finding.counter_evidence_refs.join("、") || "未列出"}
                </p>
                <p>下一步：{finding.proposed_follow_up || "仍需研究复核"}</p>
              </section>
            ))}
            <ul>
              {data.sources.map((source) => (
                <li key={source.evidence_id}>
                  {source.evidence_id}：
                  {source.source_url ? (
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {source.title}
                    </a>
                  ) : (
                    source.title
                  )}{" "}
                  · {source.available_at} · SHA-256 {source.sha256}
                </li>
              ))}
            </ul>
          </>
        )}
      </RemoteState>
    </details>
  );
}
