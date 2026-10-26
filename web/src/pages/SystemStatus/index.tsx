import { Link } from "@umijs/max";
import { Button, Descriptions, Skeleton, Typography } from "antd";
import { ResearchFunnelAuditPanel } from "../../components/ResearchFunnelAuditPanel";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { describeCode } from "../../utils/codes";
import { systemActionRows } from "../../utils/system-actions";

const actorLabel: Record<string, string> = {
  HUMAN: "需有权人复核",
  EVIDENCE: "需补研究证据",
  EXTERNAL_DATA: "等待外部数据",
  ENGINEERING: "需工程处理",
};

export default function SystemStatus() {
  const { data, loading, error, retry } = useApi(api.packet);
  const snapshot = useApi(api.snapshot);
  const runtime = useApi(api.runtimeIdentity);
  const funnel = useApi(api.researchFunnel);
  const clientBuild = __WEB_BUILD_IDENTITY__;
  const servedBuild = runtime.data?.web_build;
  const clientMatchesServed = Boolean(
    servedBuild &&
    clientBuild.commit === servedBuild.commit &&
    clientBuild.built_at === servedBuild.built_at,
  );
  return (
    <Workbench>
      <Typography.Title level={2}>数据与系统状态</Typography.Title>
      <Typography.Paragraph type="secondary">
        研究依据与发布时间在这里核对，不等于买卖准入。
      </Typography.Paragraph>
      {loading && <Skeleton active />}
      {error && (
        <p role="alert">
          读取失败：{error} <Button onClick={retry}>重试</Button>
        </p>
      )}
      {data && (
        <>
          <Descriptions
            bordered
            size="small"
            column={{ xs: 1, sm: 2 }}
            items={[
              {
                key: "consistency",
                label: "运行版本一致性",
                children: runtime.loading
                  ? "正在核对"
                  : runtime.error
                    ? "无法核对"
                    : runtime.data?.status === "MATCHED" && clientMatchesServed
                      ? runtime.data.publication_registry?.status === "MATCHED"
                        ? "前端、后端、当前源码与发布注册表一致"
                        : "前端、后端与当前源码一致；发布注册表未核验"
                      : "运行状态存在差异；请查看下方版本问题",
              },
              {
                key: "client",
                label: "当前页面前端构建",
                children: `${clientBuild.commit?.slice(0, 12) || "未知"} · ${clientBuild.built_at || "未知时间"}`,
              },
              {
                key: "served",
                label: "服务器 Web 构建",
                children: `${servedBuild?.commit.slice(0, 12) || "未登记"} · ${servedBuild?.built_at || "未知时间"}`,
              },
              {
                key: "backend",
                label: "后端启动时源码",
                children:
                  runtime.data?.backend_loaded_head?.slice(0, 12) || "未核对",
              },
              {
                key: "head",
                label: "当前 Git 源码",
                children:
                  runtime.data?.current_source_head?.slice(0, 12) || "未核对",
              },
              {
                key: "publication",
                label: "当前验证数据包",
                children: runtime.data?.publication.publication_id || "未验证",
              },
              {
                key: "session",
                label: "最新完成交易日",
                children:
                  runtime.data?.publication.dates
                    ?.latest_completed_trade_session || "未验证",
              },
              {
                key: "mismatch",
                label: "版本问题",
                children: runtime.error
                  ? runtime.error
                  : runtime.data?.reasons.map(describeCode).join("、") ||
                    (clientMatchesServed ? "无" : "浏览器页面与服务器构建不同"),
              },
            ]}
          />
          <Descriptions
            bordered
            size="small"
            column={{ xs: 1, sm: 2 }}
            items={[
              {
                key: "status",
                label: "发布状态",
                children: data.packet_status,
              },
              {
                key: "id",
                label: "发布版本",
                children: data.publication_id || "未验证",
              },
              {
                key: "research",
                label: "研究截至",
                children: data.dates.research_as_of || "未验证",
              },
              {
                key: "quote",
                label: "行情日期",
                children: data.dates.quote_trade_date || "未验证",
              },
              {
                key: "model",
                label: "模型有效性",
                children: data.dates.model_validity.status,
              },
              {
                key: "source",
                label: "来源校验",
                children: data.source_bindings_verified
                  ? "来源哈希匹配；不等于投资批准"
                  : "未通过或未完成",
              },
              {
                key: "formal",
                label: "正式准入",
                children: data.formal_admission_count,
              },
              {
                key: "excel",
                label: "Excel 原快照基准日",
                children: data.dates.excel_published_as_of || "未验证",
              },
              {
                key: "excelQuote",
                label: "Excel 登记行情观察日",
                children: data.dates.excel_quote_observation_as_of || "未验证",
              },
              {
                key: "excelPublished",
                label: "Excel 研究更新登记日",
                children: data.dates.decision_published_on || "未验证",
              },
              {
                key: "excelIntegrity",
                label: "唯一 Excel 当前文件核验",
                children: snapshot.loading
                  ? "正在只读核验"
                  : snapshot.error
                    ? "读取失败，不能确认一致"
                    : snapshot.data?.excel_live?.status === "MATCHED"
                      ? "与已登记文件一致；不代表与今日 Web 同日更新"
                      : snapshot.data?.excel_live?.status || "尚未核验",
              },
            ]}
          />
          <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
            Excel
            是独立发布快照。以上日期分别代表原快照、研究更新和行情观察，不能当作今日实时数据。日常决策以当前已验证
            Web 版本及逐证券日期为准。
          </Typography.Paragraph>
          {systemActionRows(data).length > 0 && (
            <section style={{ marginTop: 22 }}>
              <h2 style={{ fontSize: 16 }}>逐证券待办</h2>
              <ul>
                {systemActionRows(data).map((row) => (
                  <li key={row.symbol} style={{ marginBottom: 12 }}>
                    <Link to={`/decisions/${row.symbol}`}>
                      {row.name} {row.symbol}
                    </Link>{" "}
                    · {row.valuation}
                    <div>
                      {actorLabel[row.actions[0].actor] || row.actions[0].actor}
                      ：{row.actions[0].label}
                    </div>
                    {row.actions.length > 1 && (
                      <details>
                        <summary>其余待办（{row.actions.length - 1}）</summary>
                        <ul>
                          {row.actions.slice(1).map((action) => (
                            <li key={`${action.actor}-${action.code}`}>
                              {actorLabel[action.actor] || action.actor}：
                              {action.label}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.blockers.length > 0 && (
            <details style={{ marginTop: 16 }}>
              <summary>原始诊断代码（{data.blockers.length}）</summary>
              <ul>
                {data.blockers.map((code, index) => (
                  <li key={`${index}-${code}`}>{describeCode(code)}</li>
                ))}
              </ul>
            </details>
          )}
          <Link to="/daily">返回今日机会</Link>
        </>
      )}
      <ResearchFunnelAuditPanel
        funnel={funnel.data}
        loading={funnel.loading}
        error={funnel.error}
        retry={funnel.retry}
      />
    </Workbench>
  );
}
