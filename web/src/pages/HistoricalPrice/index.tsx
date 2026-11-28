import { Link, useParams } from "@umijs/max";
import { useCallback, useState } from "react";
import { Alert, Segmented, Typography } from "antd";
import { RemoteState } from "../../components/RemoteState";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import type { HistoricalPriceCase } from "../../types/api";
import "./price-chart.css";

type Period = "daily" | "60m" | "15m";

function CaseContent({ value }: { value: HistoricalPriceCase }) {
  const [period, setPeriod] = useState<Period>("60m");
  const level = value.levels[period];
  const source = value.source_bindings[period];
  return (
    <section className="historical-price-page">
      <div className="historical-price-heading">
        <div>
          <Typography.Title level={2}>
            {value.symbol} 历史价格结构
          </Typography.Title>
          <p>截至 {value.market_trade_date} 收盘 · 新浪单源原件 · 非今日机会</p>
        </div>
        <Link to="/daily">返回今日机会</Link>
      </div>
      <Alert
        type="warning"
        showIcon
        message="历史观察，未获正式交易辅助资格"
        description={
          value.close_crosscheck?.status === "VERIFIED_HISTORICAL_CLOSE"
            ? "历史收盘已获腾讯、搜狐双源核验；分钟结构仍是单源，事件、复权及个人风险门禁未通过。价格不是委托或止损指令，系统不会下单。"
            : "未完成双源收盘、事件及个人风险门禁；所有价格是研究参考，不是委托价或止损指令，系统不会下单。"
        }
      />
      <div className="historical-price-metrics">
        <div>
          <small>历史收盘</small>
          <strong>{level.reference_close}</strong>
        </div>
        <div>
          <small>突破观察价</small>
          <strong>{level.entry_trigger_price}</strong>
        </div>
        <div>
          <small>结构失效参考</small>
          <strong>{level.invalidation_price}</strong>
        </div>
        <div>
          <small>量比（近五根）</small>
          <strong>{Number(level.volume_ratio).toFixed(2)}</strong>
        </div>
      </div>
      <Segmented
        className="historical-period"
        value={period}
        onChange={(next) => setPeriod(next as Period)}
        options={[
          { label: "日线（派生）", value: "daily" },
          { label: "60 分钟", value: "60m" },
          { label: "15 分钟", value: "15m" },
        ]}
      />
      <details className="historical-price-source">
        <summary>查看最近 10 条已完成行情</summary>
        <div className="workbench-table-scroll">
          <table aria-label="历史行情证据">
            <thead>
              <tr>
                <th scope="col">时间</th>
                <th scope="col">开盘</th>
                <th scope="col">最高</th>
                <th scope="col">最低</th>
                <th scope="col">收盘</th>
                <th scope="col">成交量</th>
              </tr>
            </thead>
            <tbody>
              {value.bars[period]
                .slice(-10)
                .reverse()
                .map((bar) => (
                  <tr key={bar.time}>
                    <td>{bar.time}</td>
                    <td>{bar.open}</td>
                    <td>{bar.high}</td>
                    <td>{bar.low}</td>
                    <td>{bar.close}</td>
                    <td>{bar.volume}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
      <section className="historical-price-logic">
        <h3>价格条件怎么算</h3>
        <p>
          取最近一根已完成 K
          线之前的五根：最高价的最大值为突破观察价，最低价的最小值为结构失效参考。只有完成收盘价高于突破价，且当根成交量不少于前五根均量的
          1.2 倍，才算本周期历史突破观察。
        </p>
        <p>
          本周期结果：
          {level.breakout_observed
            ? "历史结构与量能同时满足"
            : "尚未同时满足收盘突破与量能确认"}
          。规则 {level.rule_version}；观察窗口 {level.window} 根；最后 K 线{" "}
          {level.last_bar}。
        </p>
        <p>
          没有可信目标价，因此不计算风险收益比；后续收盘跌破结构低点仅触发重新研究，不自动卖出。
        </p>
      </section>
      <details className="historical-price-source">
        <summary>查看原始来源与校验</summary>
        <p>
          来源：
          <a href={source.source_url} target="_blank" rel="noreferrer">
            新浪原始 K 线响应
          </a>
        </p>
        <p>
          采集时间：{source.fetched_at} · 复权：{source.adjustment}
        </p>
        <p>
          历史收盘：
          {value.close_crosscheck?.status === "VERIFIED_HISTORICAL_CLOSE"
            ? "腾讯 / 搜狐双源核验 " + value.close_crosscheck.price + " 元"
            : "尚未绑定双源收盘核验"}
        </p>
        {value.close_crosscheck && (
          <p>
            双源清单：<code>{value.close_crosscheck.manifest_path}</code> ·
            SHA-256 <code>{value.close_crosscheck.manifest_sha256}</code>
          </p>
        )}
        <p>
          原件 SHA-256：<code>{source.sha256}</code>
        </p>
        <p>
          口径：{source.scope}。日线由同一来源 60
          分钟完整交易时段聚合，不是独立日线。
        </p>
      </details>
    </section>
  );
}

export default function HistoricalPrice() {
  const { symbol = "", day = "" } = useParams<{
    symbol: string;
    day: string;
  }>();
  const load = useCallback(
    (signal: AbortSignal) => api.historicalCase(symbol, day, signal),
    [symbol, day],
  );
  const { data, loading, error, retry } = useApi(load);
  return (
    <Workbench>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data?.signal_state === "HISTORICAL_OBSERVATION_NOT_ADMITTED" ? (
          <CaseContent value={data} />
        ) : (
          <Alert type="info" showIcon message="历史价格原件不可用或校验失败" />
        )}
      </RemoteState>
    </Workbench>
  );
}
