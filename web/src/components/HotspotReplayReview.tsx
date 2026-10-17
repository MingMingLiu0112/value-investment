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
              回放生成于 {result.data.computed_at}；历史检验不能声称前瞻样本外。
            </p>
            <Table
              size="small"
              rowKey="symbol"
              pagination={false}
              scroll={{ x: 600 }}
              dataSource={result.data.items.map((row) => ({
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
                value={result.data.limitations}
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
