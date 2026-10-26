import { Alert, Table } from "antd";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";
import { HistoricalActionLineageReview } from "./HistoricalActionLineageReview";
import { SimulatedHotspotLifecycleReview } from "./SimulatedHotspotLifecycleReview";

type Segment = {
  trigger_count: number;
  mature_five_session_count: number;
  failure_proxy_count: number;
  failure_proxy_denominator: number;
  false_breakout_proxy_count: number;
  false_breakout_proxy_denominator: number;
};
type Replay = {
  historical_action_lineage?: unknown;
  simulated_hotspot_lifecycle?: unknown;
  action: "no_order";
  computed_at: string;
  items: { symbol: string; v1_segments: { validation: Segment } }[];
  limitations: string[];
  execution_validation?: {
    action: "no_order";
    formal_eligibility: false;
    summary: {
      assumed_state_closed_trade_count: number;
      strict_closed_trade_count: number;
      assumed_state_open_positions: number;
      assumed_state_right_censored_intentions: number;
    };
    costs: {
      commission_rate: string;
      minimum_commission_cny: string;
      slippage_bps: string;
    };
    case_results: {
      symbol: string;
      cost_multiplier: string;
      folds: {
        net_pnl_cny: string;
        total_fees_cny: string;
        total_slippage_cny: string;
      }[];
    }[];
    parameter_fingerprint: string;
    source_fingerprint: string;
    gaps: string[];
  };
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
          description="信号随访可能重叠，不能当作个人真实成交亏损。下方执行实验使用假设费用和成交约定，不是个人实际成交，也不是独立样本外优势证明。"
        />
        {result.data && !result.error ? (
          <>
            <HistoricalActionLineageReview
              value={result.data.historical_action_lineage}
            />
            <SimulatedHotspotLifecycleReview
              value={result.data.simulated_hotspot_lifecycle}
            />
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
            {result.data.execution_validation?.action === "no_order" &&
              result.data.execution_validation.formal_eligibility === false && (
                <section aria-label="规则到成交的费用实验">
                  <h4>规则到成交的费用实验</h4>
                  <p>
                    假设正常交易状态下，模拟平仓{" "}
                    {
                      result.data.execution_validation.summary
                        .assumed_state_closed_trade_count
                    }{" "}
                    笔； 严格历史状态核验模式平仓{" "}
                    {
                      result.data.execution_validation.summary
                        .strict_closed_trade_count
                    }{" "}
                    笔。 未平仓{" "}
                    {
                      result.data.execution_validation.summary
                        .assumed_state_open_positions
                    }{" "}
                    笔，待执行截尾{" "}
                    {
                      result.data.execution_validation.summary
                        .assumed_state_right_censored_intentions
                    }{" "}
                    笔。
                  </p>
                  <p>
                    严格模式缺历史停牌与涨跌停状态，不把假设成交当作已验证成交。各公司、各窗口独立重置资金，不能合并成组合收益率。
                  </p>
                  <p>
                    实验佣金比率{" "}
                    {result.data.execution_validation.costs.commission_rate}
                    ，最低佣金{" "}
                    {
                      result.data.execution_validation.costs
                        .minimum_commission_cny
                    }{" "}
                    元，滑点{" "}
                    {result.data.execution_validation.costs.slippage_bps}{" "}
                    bps；不是个人已确认费率。
                  </p>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="symbol"
                    scroll={{ x: 540 }}
                    dataSource={result.data.execution_validation.case_results
                      .filter((row) => row.cost_multiplier === "1")
                      .map((row) => ({
                        symbol: row.symbol,
                        pnl: row.folds
                          .reduce(
                            (sum, fold) => sum + Number(fold.net_pnl_cny),
                            0,
                          )
                          .toFixed(2),
                        fees: row.folds
                          .reduce(
                            (sum, fold) => sum + Number(fold.total_fees_cny),
                            0,
                          )
                          .toFixed(2),
                        slippage: row.folds
                          .reduce(
                            (sum, fold) =>
                              sum + Number(fold.total_slippage_cny),
                            0,
                          )
                          .toFixed(2),
                      }))}
                    columns={[
                      { title: "代码", dataIndex: "symbol" },
                      { title: "分窗净损益合计（元）", dataIndex: "pnl" },
                      { title: "费用（元）", dataIndex: "fees" },
                      { title: "滑点影响（元）", dataIndex: "slippage" },
                    ]}
                  />
                  <p style={{ overflowWrap: "anywhere" }}>
                    参数指纹{" "}
                    {result.data.execution_validation.parameter_fingerprint}
                    ；来源指纹{" "}
                    {result.data.execution_validation.source_fingerprint}
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
