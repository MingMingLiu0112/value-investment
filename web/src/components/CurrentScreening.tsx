import { Link } from "@umijs/max";
import { Input, Select, Table } from "antd";
import { useMemo, useState } from "react";
import type {
  CurrentScreening as Screening,
  ScanLead,
} from "../types/discovery";
import type { DecisionItem } from "../types/api";

const channels: Record<string, string> = {
  quality: "质量",
  value: "价值",
  dividend_cash_return: "股息现金回报",
  cyclical: "周期价值",
};
const fields: Record<string, string> = {
  total_revenue: "营业总收入",
  net_income: "归母净利润",
  roe_weighted: "加权 ROE",
  gross_margin: "毛利率",
  eps_reported: "每股收益",
  bvps: "每股净资产",
  operating_cash_flow_per_share: "每股经营现金流",
  total_revenue_yoy: "营业总收入同比",
  parent_net_income_yoy: "归母净利润同比",
};

function Evidence({ lead }: { lead: ScanLead }) {
  return (
    <div className="scan-evidence">
      <strong>入选原因</strong>
      <ul>
        {lead.screening_reasons.map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>
      <p>下一步：{lead.next_required_evidence}</p>
      <p>筛选证据：{lead.evidence_ids.join(" · ")}</p>
      {(lead.financial_observations?.length ?? 0) > 0 ? (
        <>
          <strong>已采集财务原值（第三方观察值，未获官方财报准入）</strong>
          <div className="scan-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>指标</th>
                  <th>原值 / 单位</th>
                  <th>报告期</th>
                  <th>证据</th>
                </tr>
              </thead>
              <tbody>
                {lead.financial_observations?.map((point) => (
                  <tr key={point.field_name}>
                    <td>{fields[point.field_name] ?? point.field_name}</td>
                    <td>
                      {point.value} / {point.unit}
                    </td>
                    <td>{point.period_label}</td>
                    <td>
                      <a
                        href={
                          /^https:\/\//.test(point.source_url)
                            ? point.source_url
                            : undefined
                        }
                        target="_blank"
                        rel="noreferrer"
                      >
                        原始出处
                      </a>
                      <details>
                        <summary>时间与文件指纹</summary>
                        <div>首次可得：{point.available_at}</div>
                        <code>{point.raw_file_hash}</code>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p>
          该公司本轮未展示已核验来源的补充财务原值；不能据此视为零值或财务差。
        </p>
      )}
    </div>
  );
}

export function CurrentScreening({
  scan,
  decisions,
}: {
  scan: Screening;
  decisions: DecisionItem[];
}) {
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("all");
  const rows = useMemo(
    () =>
      (scan.details?.leads ?? []).filter(
        (lead) =>
          (channel === "all" || lead.channels.includes(channel)) &&
          `${lead.symbol} ${lead.company_name}`.includes(query.trim()),
      ),
    [scan.details, channel, query],
  );
  const financial = scan.details?.financial;
  const scope = scan.screening_scope;
  const venueNames: Record<string, string> = {
    SSE: "上交所",
    SZSE: "深交所",
    BSE: "北交所",
  };
  return (
    <section aria-label="本次全市场初筛" className="current-screening">
      <h3>{scope ? "本次已覆盖市场初筛" : "本次全市场初筛"}（尚非交易机会）</h3>
      {scan.status !== "VERIFIED_RESEARCH_SCAN" ? (
        <p>本次初筛清单无法核验，不能据此判断市场没有机会。</p>
      ) : (
        <>
          {scope && (
            <>
              <p role="status">
                部分市场覆盖：已核验清单来自
                {scope.covered_venues
                  .map((venue) => venueNames[venue] ?? venue)
                  .join("、")}
                ；
                {scope.failed_venues
                  .map((venue) => venueNames[venue] ?? venue)
                  .join("、")}
                采集失败，不能判断该市场有无机会。未匹配已观察官方清单的报价已单独排除，
                不视为退市，也不算作本范围内缺失行情。
              </p>
              <details>
                <summary>未匹配报价数量（按供应商，不是去重公司数）</summary>
                <ul>
                  {Object.entries(scope.quote_coverage).map(
                    ([provider, item]) => (
                      <li key={provider}>
                        {provider === "tencent"
                          ? "腾讯"
                          : provider === "sina"
                            ? "新浪"
                            : provider}
                        ：{item.excluded_row_count} 条
                      </li>
                    ),
                  )}
                </ul>
              </details>
            </>
          )}
          <p>
            {scan.as_of} · 覆盖 {scan.universe_count} 只，去重研究线索{" "}
            {scan.lead_count} 只，Quality 通过{" "}
            {scan.channel_counts?.quality ?? "未核验"} 只。
            {scan.quote_date_verification !== "VERIFIED" &&
              (scope
                ? " 已覆盖市场行情日期仍需独立核验。"
                : " 全市场行情日期仍需独立核验。")}
          </p>
          <p>
            以下是待研究的初筛线索，不是买入名单。下方正式研究列表和投资建议仍使用各自已发布版本。
          </p>
          {financial?.status === "PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS" && (
            <p>
              财务报告期 {financial.period}：采集 {financial.provider_rows} 家、
              {financial.observation_count} 个观察值， 本轮补充{" "}
              {financial.adopted_observation_count}{" "}
              个。数据已取得不等于完成审计；质量准入还需要官方财报、口径及现金转换核验。
            </p>
          )}
          {scan.details?.status === "SOURCE_REVALIDATED" ? (
            <>
              <div className="scan-filters">
                <Input
                  aria-label="搜索本次初筛公司"
                  placeholder="公司 / 代码"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  allowClear
                />
                <Select
                  aria-label="初筛通道"
                  value={channel}
                  onChange={setChannel}
                  options={[
                    { value: "all", label: "全部通道" },
                    ...Object.entries(channels).map(([value, label]) => ({
                      value,
                      label,
                    })),
                  ]}
                />
                <span>{rows.length} 家</span>
              </div>
              <Table<ScanLead>
                rowKey="symbol"
                size="small"
                dataSource={rows}
                pagination={{ pageSize: 8, showSizeChanger: false }}
                scroll={{ x: 620 }}
                expandable={{
                  expandedRowRender: (lead) => <Evidence lead={lead} />,
                }}
                columns={[
                  {
                    title: "公司",
                    key: "company",
                    render: (_, lead) => (
                      <span>
                        {lead.company_name} · {lead.symbol}
                      </span>
                    ),
                  },
                  {
                    title: "入选通道",
                    key: "channels",
                    render: (_, lead) =>
                      lead.channels
                        .map((key) => channels[key] ?? key)
                        .join(" / "),
                  },
                  {
                    title: "研究衔接",
                    key: "research",
                    render: (_, lead) => {
                      const decision = decisions.find(
                        (item) => item.symbol === lead.symbol,
                      );
                      return decision ? (
                        <Link
                          to={`/decisions/${encodeURIComponent(decision.id)}`}
                        >
                          查看已有研究
                        </Link>
                      ) : (
                        "待官方补证与适用模型研究"
                      );
                    },
                  },
                ]}
              />
            </>
          ) : (
            <p>候选明细的回执或原件无法核验，暂不展示公司清单。</p>
          )}
          {financial?.status === "PUBLIC_SUPPLEMENT_REVALIDATION_FAILED" && (
            <p>财务补充原件校验失败，已停止展示相关数值。</p>
          )}
        </>
      )}
    </section>
  );
}
