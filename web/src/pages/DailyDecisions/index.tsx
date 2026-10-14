import { Link } from "@umijs/max";
import { Button, Empty, Skeleton, Typography } from "antd";
import { DecisionCard } from "../../components/DecisionCard";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { usePrivateState } from "../../hooks/usePrivateState";
import { api } from "../../services/api";
import type { DecisionItem } from "../../types/api";
import { describeCode } from "../../utils/codes";
import { hasValuationResult } from "../../utils/opportunityView";
import {
  judgmentGroup,
  judgmentGroups,
  publicationVersionsMatch,
} from "../../utils/currentJudgment";
import "./opportunities.css";

function StrategySection({
  title,
  horizon,
  items,
  empty,
  id,
  foldUnvalued = false,
}: {
  title: string;
  horizon: string;
  items: DecisionItem[];
  empty: string;
  id: string;
  foldUnvalued?: boolean;
}) {
  const main = foldUnvalued ? items.filter(hasValuationResult) : items;
  const other = foldUnvalued
    ? items.filter((item) => !hasValuationResult(item))
    : [];
  const counts = {
    formal: items.filter((item) => judgmentGroup(item) === 0).length,
    pending: items.filter((item) => [1, 2].includes(judgmentGroup(item)))
      .length,
    watch: items.filter((item) => judgmentGroup(item) >= 3).length,
  };
  return (
    <section id={id} className="opportunity-strategy" aria-label={title}>
      <div className="opportunity-strategy-head">
        <div>
          <span className="opportunity-horizon">{horizon}</span>
          <h2>{title}</h2>
        </div>
        <div className="opportunity-counts" aria-label="候选数量">
          <span>
            <strong>{counts.formal}</strong> 正式复核
          </span>
          <span>
            <strong>{counts.pending}</strong> 待确认
          </span>
          <span>
            <strong>{counts.watch}</strong> 研究观察
          </span>
        </div>
      </div>
      {main.length ? (
        <div className="opportunity-list">
          {judgmentGroups.map((label, group) => {
            const rows = main.filter((item) => judgmentGroup(item) === group);
            if (group === 4 && rows.length)
              return (
                <details key={label} aria-label="已失效或等待补齐数据">
                  <summary>
                    已失效 / 等待重新形成结构或补齐数据（{rows.length}）
                  </summary>
                  {rows.map((item) => (
                    <DecisionCard key={item.id} item={item} />
                  ))}
                </details>
              );
            return rows.length ? (
              <section key={label} aria-label={label}>
                <h3>{label}</h3>
                {rows.map((item) => (
                  <DecisionCard key={item.id} item={item} />
                ))}
              </section>
            ) : null;
          })}
        </div>
      ) : (
        <div className="opportunity-empty">
          <Empty description={empty} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
      {!!other.length && (
        <details aria-label="其他待研究公司">
          <summary>其他待研究公司（{other.length}）</summary>
          {other.map((item) => (
            <DecisionCard key={item.id} item={item} />
          ))}
        </details>
      )}
    </section>
  );
}

export default function DailyDecisions() {
  const { data, loading, error, retry } = useApi(api.daily);
  const packet = useApi(api.packet);
  const historical = useApi(api.historicalCases);
  const state = usePrivateState();
  const packetCurrent =
    packet.data?.packet_status === "CURRENT" && !!packet.data.publication_id;
  const usable =
    !!data &&
    packetCurrent &&
    data.action === "no_order" &&
    publicationVersionsMatch(
      data.publication?.publication_id,
      packet.data?.publication_id,
    );
  const researchDate = packet.data?.dates.research_as_of ?? data?.as_of ?? null;
  const quoteDate = packet.data?.dates.quote_trade_date ?? null;
  const hotspotDates = usable
    ? [
        ...new Set(
          data.sections.hotspot
            .map((item) => item.price_action_plan?.market_trade_date)
            .filter(Boolean),
        ),
      ].join("、")
    : "";
  const quoteFresh = packet.data?.data_freshness.quote.status === "FRESH";
  const researchFresh = packet.data?.data_freshness.research.status === "FRESH";
  const subtitle =
    quoteFresh && researchFresh && quoteDate
      ? `价值研究价格参考截至 ${quoteDate} 收盘；热点行情日期分别核验。`
      : `研究截至 ${researchDate ?? "日期待核验"}；${quoteDate ? `行情日期 ${quoteDate}` : "行情日期待核验"}，未满足的条件不会转成操作建议。`;
  return (
    <Workbench>
      <header className="opportunity-page-head">
        <div>
          <Typography.Title level={2} className="opportunity-title">
            今日投资机会
          </Typography.Title>
          <p className="opportunity-subtitle">{subtitle}</p>
          {usable && (
            <p className="opportunity-subtitle">
              价值价格核验日期 {quoteDate ?? "未提供"}；热点已完成交易日{" "}
              {hotspotDates || "当前行情尚未核验"}。
            </p>
          )}
        </div>
        <div className="opportunity-freshness">
          <span>研究 {researchDate ?? "未核验"}</span>
          <Button
            size="small"
            onClick={() => {
              retry();
              packet.retry();
              historical.retry();
              state.retry();
            }}
            aria-label="刷新页面数据"
          >
            刷新
          </Button>
          <Link to="/system">数据状态</Link>
        </div>
      </header>
      {(loading || packet.loading) && (
        <Skeleton active paragraph={{ rows: 8 }} />
      )}
      {!loading && !packet.loading && !usable && (
        <div className="opportunity-stop" role="status">
          <strong>当前结果不可核验，已停止展示候选。</strong>
          <p>
            {error ||
              packet.error ||
              packet.data?.chain_error ||
              (data?.publication?.publication_id !== packet.data?.publication_id
                ? "判断与快照版本不一致，请刷新后重试。"
                : null) ||
              "正式发布链尚未就绪。"}
          </p>
          <Button
            onClick={() => {
              retry();
              packet.retry();
            }}
          >
            重试
          </Button>
        </div>
      )}
      {usable && data && (
        <>
          <div className="opportunity-strip">
            <span>
              全市场扫描{" "}
              <strong>{data.summary.universe_count ?? "待核验"}</strong>
            </span>
            <span>
              正式复核{" "}
              <strong>
                {
                  [...data.sections.value, ...data.sections.hotspot].filter(
                    (item) => judgmentGroup(item) === 0,
                  ).length
                }
              </strong>
            </span>
            <span>
              研究线索 <strong>{data.summary.watch_count ?? "待核验"}</strong>
            </span>
            <span>
              市场环境 <strong>{describeCode(data.market.status)}</strong>
            </span>
          </div>
          <section className="opportunity-holdings">
            <div>
              <h2>我的持仓今天需要关注</h2>
              <p>
                {state.label}。{state.detail}
              </p>
            </div>
            <Link to="/portfolio">查看持仓与风险</Link>
          </section>
          {![...data.sections.value, ...data.sections.hotspot].some(
            (item) => judgmentGroup(item) === 0,
          ) && (
            <p className="opportunity-no-action">
              当前正式操作候选为 0。以下为研究观察，不是买卖指令。
            </p>
          )}
          <div className="opportunity-grid">
            <div
              style={{ gridColumn: "1 / -1", display: "flex", gap: 24 }}
              aria-label="策略快捷跳转"
            >
              <a href="#daily-value">价值投资</a>
              <a href="#daily-hotspot">热点波段</a>
            </div>
            <StrategySection
              id="daily-value"
              foldUnvalued
              title="价值投资"
              horizon="中长期"
              items={data.sections.value}
              empty="当前没有可展示的价值投资线索"
            />
            <StrategySection
              id="daily-hotspot"
              title="热点波段"
              horizon="短中期"
              items={data.sections.hotspot}
              empty="当前没有通过观察条件的热点候选；不会凑出买点"
            />
          </div>
          {data.sections.holdings.length > 0 && (
            <section className="opportunity-held-list">
              <h2>持仓复核事项</h2>
              {data.sections.holdings.map((item) => (
                <DecisionCard key={item.id} item={item} />
              ))}
            </section>
          )}
          {!!historical.data?.items.length && (
            <details
              className="opportunity-historical"
              aria-label="历史价格结构验证"
            >
              <summary>历史价格结构验证（非当前候选）</summary>
              <p>以下是已归档行情的计算案例，不计入今天的候选或正式复核。</p>
              {historical.data.items.map((item) => (
                <Link
                  key={`${item.symbol}-${item.market_trade_date}`}
                  to={`/historical-price/${item.symbol}/${item.market_trade_date}`}
                >
                  {item.symbol} · {item.market_trade_date} · 60 分钟突破观察{" "}
                  {item.levels["60m"].entry_trigger_price} / 失效参考{" "}
                  {item.levels["60m"].invalidation_price}
                </Link>
              ))}
            </details>
          )}
        </>
      )}
    </Workbench>
  );
}
