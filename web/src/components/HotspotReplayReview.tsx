import { Alert, Table } from "antd";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";

type Segment = {
  trigger_count: number;
  mature_five_session_count: number;
  failure_proxy_count: number;
  failure_proxy_denominator: number;
  false_breakout_proxy_count: number;
  false_breakout_proxy_denominator: number;
};
type Replay = {
  action: "no_order";
  computed_at: string;
  items: { symbol: string; v1_segments: { validation: Segment } }[];
  limitations: string[];
  retained_validation?: {
    evaluated_at: string;
    partitions: {
      start_date: string;
      validation_start: string;
      end_date: string;
    };
    items: { symbol: string; v1_segments: { validation: Segment } }[];
    signal_event_count: number;
    mature_five_session_count: number;
    right_censored_count: number;
    trade_count: null;
    formal_eligibility: false;
    strategy_validation: "NOT_PROVEN";
    limitations: string[];
  };
};
async function load(signal: AbortSignal): Promise<Replay> {
  const response = await fetch("/api/v1/hotspot-replay-review", { signal });
  const body = await response.json();
  if (!response.ok || body.action !== "no_order")
    throw new Error("回放证据绑定未通过");
  return body;
}
export function HotspotReplayReview() {
  const result = useApi(load);
  return (
    <section aria-label="历史信号质量复核">
      <details>
        <summary>查看热点历史信号检验（非实际成交）</summary>
        <Alert
          type="info"
          message="冻结历史样本的描述性检验，尚未证明策略优势"
          description="信号随访可能重叠。失效和假突破是价格路径代理，不能当作个人真实成交亏损；费用、滑点、可成交性及净收益仍未验证。"
        />
        {result.data && !result.error ? (
          <>
            <p>
              回放生成于{" "}
              {result.data.retained_validation?.evaluated_at ??
                result.data.computed_at}
              ；历史检验不能声称前瞻样本外。
            </p>
            {result.data.retained_validation && (
              <section aria-label="留存样本价格路径检验">
                <p>
                  历史价格路径（
                  {
                    result.data.retained_validation.partitions.start_date
                  } 至 {result.data.retained_validation.partitions.end_date}）：
                  {result.data.retained_validation.signal_event_count} 次触发，
                  {
                    result.data.retained_validation.mature_five_session_count
                  }{" "}
                  次完整五日随访，
                  {result.data.retained_validation.right_censored_count}{" "}
                  次随访窗口尚未完整。
                </p>
                <p>
                  实际成交数：未核验。以上触发可能重叠；历史选股范围、当时可得信息、费用及可成交性尚未证明，不能据此判断策略净收益或批准买入。
                </p>
                <p>
                  下表仅列冻结验证窗口（
                  {
                    result.data.retained_validation.partitions.validation_start
                  }{" "}
                  至 {result.data.retained_validation.partitions.end_date}
                  ）的分公司随访，不是独立样本外交易。
                </p>
              </section>
            )}
            <Table
              size="small"
              rowKey="symbol"
              pagination={false}
              scroll={{ x: 600 }}
              dataSource={(
                result.data.retained_validation?.items ?? result.data.items
              ).map((row) => ({
                symbol: row.symbol,
                ...row.v1_segments.validation,
              }))}
              columns={[
                { title: "代码", dataIndex: "symbol" },
                { title: "触发数", dataIndex: "trigger_count" },
                {
                  title: "完整五日随访",
                  dataIndex: "mature_five_session_count",
                },
                {
                  title: "失效代理",
                  render: (_, row) =>
                    `${row.failure_proxy_count}/${row.failure_proxy_denominator}`,
                },
                {
                  title: "假突破代理",
                  render: (_, row) =>
                    `${row.false_breakout_proxy_count}/${row.false_breakout_proxy_denominator}`,
                },
              ]}
            />
            <details>
              <summary>查看验证限制</summary>
              <DetailSection
                title="限制与未知结果"
                value={
                  result.data.retained_validation?.limitations ??
                  result.data.limitations
                }
              />
            </details>
          </>
        ) : (
          <p>{result.loading ? "正在核验回放…" : "回放证据暂不可用"}</p>
        )}
      </details>
    </section>
  );
}
