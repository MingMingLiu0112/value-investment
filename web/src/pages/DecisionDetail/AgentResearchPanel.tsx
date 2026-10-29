import { useCallback, useState } from "react";
import { Alert, Button, Descriptions, Segmented, Tag, Typography } from "antd";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { RemoteState } from "../../components/RemoteState";

const WORKFLOW_LABELS: Record<string, string> = {
  event: "公告事件",
  financial: "财报",
  hotspot: "热点",
  retrospective: "测试复盘",
  legacy: "历史综合",
};

const MODE_LABELS: Record<string, string> = {
  MOCK: "Mock 模拟",
  OFFLINE_REPLAY: "离线回放",
  LIVE: "大模型研究",
};

function shortSha(value: string): string {
  return value.slice(0, 12);
}

export function AgentResearchPanel({ symbol }: { symbol: string }) {
  const [workflow, setWorkflow] = useState<string | undefined>();
  const [reviewTarget, setReviewTarget] = useState<
    { symbol: string; name: string | null; workflow: string } | undefined
  >();
  const activeSymbol = reviewTarget?.symbol ?? symbol;
  const load = useCallback(
    (signal: AbortSignal) => api.agentResearch(activeSymbol, signal, workflow),
    [activeSymbol, workflow],
  );
  const { data, loading, error, retry } = useApi(load);
  const queue = useApi(api.agentResearchStatus);
  const queueItems = queue.data?.review_queue ?? [];

  const openReviewItem = (item: (typeof queueItems)[number]) => {
    setReviewTarget({
      symbol: item.symbol,
      name: item.name,
      workflow: item.workflow,
    });
    setWorkflow(item.workflow);
  };

  return (
    <details
      open
      style={{ marginTop: 12, minWidth: 0, overflowWrap: "anywhere" }}
    >
      <summary>
        AI 研究材料、反证与来源
        {queueItems.length ? ` · 待复核 ${queueItems.length}` : ""}
      </summary>
      <section style={{ marginTop: 12 }} aria-label="待人工复核队列">
        <Typography.Title level={5}>待人工复核队列</Typography.Title>
        <RemoteState
          loading={queue.loading}
          error={queue.error}
          retry={queue.retry}
        >
          {queueItems.length === 0 ? (
            <Alert
              type="info"
              showIcon
              message={
                queue.data?.status === "UNAVAILABLE"
                  ? "研究复核队列暂不可用"
                  : "暂无待人工复核的已登记研究草稿"
              }
              description={
                queue.data?.failures?.length
                  ? `有 ${queue.data.failures.length} 项登记未能核验；未核验材料不会进入复核队列。`
                  : "仅展示已登记且绑定核验通过、仍待人工复核的研究草案。"
              }
            />
          ) : (
            <>
              <Alert
                type="warning"
                showIcon
                message={`${queueItems.length} 项跨公司研究草稿待人工复核`}
                description="只读队列：action=no_order；审批保持不变；正式资格保持不变；不得据此下单。"
              />
              <div role="list" style={{ marginTop: 8 }}>
                {queueItems.map((item) => {
                  const source = item.source_scope;
                  return (
                    <div
                      role="listitem"
                      key={`${item.symbol}-${item.workflow}`}
                      style={{
                        borderBottom: "1px solid #f0f0f0",
                        padding: "10px 0",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          gap: 6,
                          alignItems: "center",
                        }}
                      >
                        <strong>
                          {item.name
                            ? `${item.name}（${item.symbol}）`
                            : item.symbol}
                        </strong>
                        <Tag>
                          {WORKFLOW_LABELS[item.workflow] || item.workflow}
                        </Tag>
                        <Tag color="gold">待人工复核</Tag>
                        {source.test_only && (
                          <Tag color="red">Mock/测试材料，非正式证据</Tag>
                        )}
                        {source.excerpt_origin ===
                          "DERIVED_FROM_VERIFIED_PLAN" && (
                          <Tag color="blue">DERIVED_FROM_VERIFIED_PLAN</Tag>
                        )}
                      </div>
                      <div>
                        研究截止：{item.research_as_of || "未提供"} · 材料生成：
                        {item.available_at || "未提供"}
                        {item.source_available_at
                          ? ` · 来源可用：${item.source_available_at}`
                          : ""}
                      </div>
                      <div>
                        来源范围：{source.scope}
                        {source.data_scope
                          ? ` · 数据范围：${source.data_scope}`
                          : ""}
                        {` · ${MODE_LABELS[source.mode] || source.mode}`} ·
                        非正式证据
                      </div>
                      <div>
                        绑定：packet {item.packet_binding.path} @ SHA-256{" "}
                        {shortSha(item.packet_binding.sha256)} · registration{" "}
                        {item.registration_binding.path} @ SHA-256{" "}
                        {shortSha(item.registration_binding.sha256)}
                      </div>
                      <div>
                        复核原因：{item.pending_findings_count}{" "}
                        条研究结论仍需人工核对证据与语义。
                      </div>
                      <div>
                        下一步：打开已登记草稿逐条复核；不生成订单，不改变审批或正式资格。
                      </div>
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => openReviewItem(item)}
                      >
                        打开该研究草稿
                      </Button>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </RemoteState>
      </section>
      {reviewTarget && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 12 }}
          message={`正在查看队列目标：${
            reviewTarget.name
              ? `${reviewTarget.name}（${reviewTarget.symbol}）`
              : reviewTarget.symbol
          } · ${WORKFLOW_LABELS[reviewTarget.workflow] || reviewTarget.workflow}`}
          action={
            <Button
              size="small"
              onClick={() => {
                setReviewTarget(undefined);
                setWorkflow(undefined);
              }}
            >
              返回当前股票
            </Button>
          }
        />
      )}
      <Segmented
        aria-label="研究材料类型"
        value={workflow || data?.workflow || "legacy"}
        options={[
          { label: WORKFLOW_LABELS.event, value: "event" },
          { label: WORKFLOW_LABELS.financial, value: "financial" },
          { label: WORKFLOW_LABELS.hotspot, value: "hotspot" },
          { label: WORKFLOW_LABELS.retrospective, value: "retrospective" },
          { label: WORKFLOW_LABELS.legacy, value: "legacy" },
        ]}
        onChange={(value) => {
          const next = String(value);
          if (reviewTarget && next !== reviewTarget.workflow)
            setReviewTarget(undefined);
          setWorkflow(next);
        }}
        style={{ marginBlock: 12, maxWidth: "100%", overflowX: "auto" }}
      />
      <RemoteState loading={loading} error={error} retry={retry}>
        {data?.status !== "VERIFIED" ? (
          <Alert
            type="info"
            message="暂无已绑定的 AI 研究材料"
            description={
              data?.reason === "WORKFLOW_NOT_REGISTERED"
                ? "该类研究草稿尚未生成并登记，其他研究材料不会代替此项。"
                : data?.reason
            }
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
