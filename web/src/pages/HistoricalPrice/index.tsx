import { Link, useParams } from "@umijs/max";
import {
  CandlestickSeries,
  createChart,
  HistogramSeries,
} from "lightweight-charts";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Segmented, Typography } from "antd";
import { RemoteState } from "../../components/RemoteState";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import type { HistoricalBar, HistoricalPriceCase } from "../../types/api";
import {
  chartTime,
  formatShanghaiChartTime,
  formatShanghaiTick,
} from "../../utils/chartTime";
import "./price-chart.css";

type Period = "daily" | "60m" | "15m";

export function PriceChart({
  bars,
  period,
  trigger,
  invalidation,
  reference,
  scope = "历史观察",
}: {
  bars: HistoricalBar[];
  period: Period;
  trigger: number | null;
  invalidation: number | null;
  reference?: number | null;
  scope?: string;
}) {
  const holder = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!holder.current || bars.length === 0) return;
    const node = holder.current;
    const chart = createChart(node, {
      width: node.clientWidth,
      height: 390,
      layout: { background: { color: "#ffffff" }, textColor: "#526168" },
      grid: {
        vertLines: { color: "#edf0ef" },
        horzLines: { color: "#edf0ef" },
      },
      localization: { locale: "zh-CN", timeFormatter: formatShanghaiChartTime },
      timeScale: {
        timeVisible: period !== "daily",
        secondsVisible: false,
        tickMarkFormatter: formatShanghaiTick,
      },
      rightPriceScale: { borderColor: "#d6dcda" },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#b54e40",
      downColor: "#26786d",
      borderUpColor: "#b54e40",
      borderDownColor: "#26786d",
      wickUpColor: "#b54e40",
      wickDownColor: "#26786d",
      priceScaleId: "right",
    });
    candle.setData(
      bars.map((bar) => ({
        time: chartTime(bar.time, period),
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
      })),
    );
    if (trigger !== null && Number.isFinite(trigger))
      candle.createPriceLine({
        price: trigger,
        color: "#ac6640",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "突破观察",
      });
    if (invalidation !== null && Number.isFinite(invalidation))
      candle.createPriceLine({
        price: invalidation,
        color: "#407067",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "结构失效",
      });
    if (reference != null && Number.isFinite(reference))
      candle.createPriceLine({
        price: reference,
        color: "#526168",
        lineWidth: 1,
        lineStyle: 1,
        axisLabelVisible: true,
        title: "已核验收盘参考",
      });
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "",
      priceFormat: { type: "volume" },
    });
    volume
      .priceScale()
      .applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      bars.map((bar) => ({
        time: chartTime(bar.time, period),
        value: Number(bar.volume),
        color: Number(bar.close) >= Number(bar.open) ? "#d9ada6" : "#a8ccc5",
      })),
    );
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, bars.length - 90),
      to: bars.length + 3,
    });
    const observer = new ResizeObserver(() =>
      chart.applyOptions({ width: node.clientWidth }),
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [bars, period, trigger, invalidation, reference]);
  return (
    <div
      className="price-chart"
      ref={holder}
      role="img"
      aria-label={`${period}${scope}K线、成交量、突破观察与结构失效参考线`}
    />
  );
}

function CaseContent({ value }: { value: HistoricalPriceCase }) {
  const [period, setPeriod] = useState<Period>("60m");
  const level = value.levels[period];
  const source = value.source_bindings[period];
  return (
    <main className="historical-price-page">
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
      <PriceChart
        bars={value.bars[period]}
        period={period}
        trigger={Number(level.entry_trigger_price)}
        invalidation={Number(level.invalidation_price)}
      />
      <p className="historical-chart-credit">
        TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc.{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView
        </a>
      </p>
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
    </main>
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
