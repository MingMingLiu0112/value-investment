import { Link } from "@umijs/max";
import { Button, Empty, Skeleton, Typography } from "antd";
import { DecisionCard } from "../../components/DecisionCard";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { usePrivateState } from "../../hooks/usePrivateState";
import { api } from "../../services/api";
import type { DecisionItem } from "../../types/api";
import { describeCode } from "../../utils/codes";
import { strategyCounts } from "../../utils/opportunityView";
import "./opportunities.css";

function StrategySection({
  title,
  horizon,
  items,
  empty,
}: {
  title: string;
  horizon: string;
  items: DecisionItem[];
  empty: string;
}) {
  const counts = strategyCounts(items);
  return (
    <section className="opportunity-strategy" aria-label={title}>
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
      {items.length ? (
        <div className="opportunity-list">
          {items.map((item) => (
            <DecisionCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="opportunity-empty">
          <Empty description={empty} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </section>
  );
}

export default function DailyDecisions() {
  const { data, loading, error, retry } = useApi(api.daily);
  const packet = useApi(api.packet);
  const state = usePrivateState();
  const packetCurrent =
    packet.data?.packet_status === "CURRENT" && !!packet.data.publication_id;
  const usable = !!data && packetCurrent && data.action === "no_order";
  const researchDate = packet.data?.dates.research_as_of ?? data?.as_of ?? null;
  const quoteDate = packet.data?.dates.quote_trade_date ?? null;
  const quoteFresh = packet.data?.data_freshness.quote.status === "FRESH";
  const researchFresh = packet.data?.data_freshness.research.status === "FRESH";
  const subtitle =
    quoteFresh && researchFresh && quoteDate
      ? `截至 ${quoteDate} 收盘，价值投资与热点波段的最新研究结果。`
      : `研究截至 ${researchDate ?? "日期待核验"}；${quoteDate ? `行情日期 ${quoteDate}` : "行情日期待核验"}，未满足的条件不会转成操作建议。`;
  return (
    <Workbench>
      <header className="opportunity-page-head">
        <div>
          <Typography.Title level={2} className="opportunity-title">
            今日投资机会
          </Typography.Title>
          <p className="opportunity-subtitle">{subtitle}</p>
        </div>
        <div className="opportunity-freshness">
          <span>研究 {researchDate ?? "未核验"}</span>
          <Button
            size="small"
            onClick={() => {
              retry();
              packet.retry();
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
              正式复核 <strong>{data.summary.formal_count}</strong>
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
          {data.summary.formal_count === 0 && (
            <p className="opportunity-no-action">
              当前没有满足全部准入条件的候选。以下为研究观察，不是买卖指令。
            </p>
          )}
          <div className="opportunity-grid">
            <StrategySection
              title="价值投资"
              horizon="中长期"
              items={data.sections.value}
              empty="当前没有可展示的价值投资线索"
            />
            <StrategySection
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
        </>
      )}
    </Workbench>
  );
}
