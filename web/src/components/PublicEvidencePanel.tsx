import { Button } from "antd";
import type { PublicEvidenceStatus } from "../services/api";

const statuses: Record<string, string> = {
  VERIFIED: "来源已核验（非事实完整）",
  PARTIAL: "部分来源可用",
  MISSING: "来源缺失",
  CONFLICT: "来源存在冲突",
  SOURCE_UNAVAILABLE: "来源不可用",
  UNAVAILABLE: "来源不可用",
};
const exchangeNames = { SSE: "上交所", SZSE: "深交所", BSE: "北交所" } as const;
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const nullableText = (value: unknown) =>
  value === null || typeof value === "string";
const count = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

function validEvidence(value: unknown): value is PublicEvidenceStatus {
  if (
    !record(value) ||
    value.schema_version !== "public-evidence-status-v1" ||
    value.action !== "no_order" ||
    value.scope !== "REQUESTED_REPORTS_ONLY" ||
    value.formal_eligibility !== false ||
    value.strict_historical_pit !== false ||
    !["VERIFIED", "PARTIAL", "MISSING", "CONFLICT"].includes(
      String(value.status),
    ) ||
    !nullableText(value.generated_at) ||
    !nullableText(value.reason) ||
    !Array.isArray(value.items) ||
    !record(value.exchanges)
  )
    return false;
  const exchanges = value.exchanges;
  return (
    Object.keys(exchangeNames).every((key) => {
      const exchange = exchanges[key];
      return (
        record(exchange) &&
        count(exchange.requested) &&
        count(exchange.verified) &&
        exchange.verified <= exchange.requested
      );
    }) &&
    value.items.every(
      (item) =>
        record(item) &&
        ["symbol", "issuer_name", "period", "status", "fact_status"].every(
          (key) => typeof item[key] === "string" && item[key].trim(),
        ) &&
        [
          "source_url",
          "sha256",
          "published_date",
          "fetched_at",
          "reason",
        ].every((key) => nullableText(item[key])) &&
        typeof item.reused === "boolean" &&
        count(item.adopted_fact_count) &&
        ["fact_issues", "adopted_fields"].every(
          (key) =>
            !(key in item) ||
            (Array.isArray(item[key]) &&
              item[key].every((value) => typeof value === "string")),
        ),
    )
  );
}

function sourceLink(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) ? url : null;
  } catch {
    return null;
  }
}

export function PublicEvidencePanel({
  evidence,
  loading,
  error,
  retry,
}: {
  evidence?: PublicEvidenceStatus;
  loading: boolean;
  error?: string;
  retry: () => void;
}) {
  const valid = validEvidence(evidence);
  return (
    <section
      aria-label="公开来源覆盖"
      style={{
        marginBottom: 20,
        padding: 16,
        border: "1px solid #d9d9d9",
        borderRadius: 8,
      }}
    >
      <h3>公开来源覆盖</h3>
      <p>
        仅覆盖已请求的报告，不代表全市场覆盖。来源取得不代表事实提取完整或研究获准；来源不可用不等于零候选。
      </p>
      <p>
        只读查看已保存状态；重试仅重新读取，不触发来源采集。不证明严格历史时点可得性，未取得正式准入。action=no_order。
      </p>
      {loading ? (
        <p role="status">正在读取公开来源状态…</p>
      ) : error ? (
        <p role="alert">
          公开来源状态读取失败：{error}{" "}
          <Button onClick={retry}>重试读取</Button>
        </p>
      ) : !valid ? (
        <p role="alert">
          {evidence
            ? "公开来源响应字段缺失或契约不匹配，未展示覆盖数值。"
            : "尚未取得公开来源状态，不能认定没有候选。"}
          <Button onClick={retry}>重试读取</Button>
        </p>
      ) : (
        <>
          <p>
            <strong>{statuses[evidence.status]}</strong> · 状态生成时间：
            {evidence.generated_at || "未提供"}
          </p>
          {evidence.reason && <p>原因：{evidence.reason}</p>}
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(min(100%,180px),1fr))",
              gap: 12,
            }}
          >
            {(Object.keys(exchangeNames) as (keyof typeof exchangeNames)[]).map(
              (key) => (
                <p key={key}>
                  <strong>{exchangeNames[key]}</strong>：已核验{" "}
                  {evidence.exchanges[key].verified} / 已请求{" "}
                  {evidence.exchanges[key].requested} 份报告
                </p>
              ),
            )}
          </div>
          {evidence.items.length ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <caption>
                  已请求报告及原始取得时间（复用旧包不刷新取得时间）
                </caption>
                <thead>
                  <tr>
                    <th scope="col">公司／期间</th>
                    <th scope="col">来源状态</th>
                    <th scope="col">披露与取得时间</th>
                    <th scope="col">事实采用</th>
                    <th scope="col">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.items.map((item, index) => {
                    const url = sourceLink(item.source_url);
                    return (
                      <tr key={item.symbol + item.period + index}>
                        <th
                          scope="row"
                          style={{
                            textAlign: "left",
                            verticalAlign: "top",
                            padding: 8,
                          }}
                        >
                          {item.issuer_name} {item.symbol}
                          <div>{item.period}</div>
                        </th>
                        <td style={{ verticalAlign: "top", padding: 8 }}>
                          {statuses[item.status] ||
                            `来源状态待解释（${item.status}）`}
                          <div>
                            {item.reused
                              ? "复用已存原件（保留原取得时间）"
                              : "未标记复用"}
                          </div>
                          {item.reason && <div>原因：{item.reason}</div>}
                        </td>
                        <td style={{ verticalAlign: "top", padding: 8 }}>
                          披露：{item.published_date || "未提供"}
                          <div>
                            原始取得：
                            {item.fetched_at || "未提供，未用生成时间代替"}
                          </div>
                        </td>
                        <td style={{ verticalAlign: "top", padding: 8 }}>
                          事实状态：{item.fact_status}
                          <div>
                            已采用 {item.adopted_fact_count}{" "}
                            项事实；不代表事实完整
                          </div>
                          {item.adopted_fields !== undefined && (
                            <div>
                              仅已核验字段：
                              {item.adopted_fields.length
                                ? item.adopted_fields.join("、")
                                : "未列出已采纳字段"}
                            </div>
                          )}
                          {item.fact_issues !== undefined && (
                            <div>
                              未采纳原因（现有资产负债表核验记录）：
                              {item.fact_issues.length ? (
                                <ul>
                                  {item.fact_issues.map((issue, i) => (
                                    <li key={i}>{issue}</li>
                                  ))}
                                </ul>
                              ) : (
                                "未记录具体原因；不代表其他事实完整"
                              )}
                            </div>
                          )}
                        </td>
                        <td style={{ verticalAlign: "top", padding: 8 }}>
                          {url ? (
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              查看公开原件
                            </a>
                          ) : (
                            "未提供可用原件链接"
                          )}
                          <details>
                            <summary>来源校验信息</summary>
                            <p style={{ overflowWrap: "anywhere" }}>
                              SHA256：{item.sha256 || "未提供"}
                            </p>
                          </details>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p>未列出已请求报告记录；不代表候选数量为零。</p>
          )}
        </>
      )}
    </section>
  );
}
