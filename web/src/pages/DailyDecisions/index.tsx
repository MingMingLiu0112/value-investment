import { Link } from "@umijs/max";
import { Button, Empty, Skeleton, Typography } from "antd";
import { DecisionCard } from "../../components/DecisionCard";
import { HoldingsAttention } from "../../components/HoldingsAttention";
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

function updateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "时间未核验"
    : `${date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}（北京时间）`;
}

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
  const update = useApi(api.updateStatus);
  const historical = useApi(api.historicalCases);
  const state = usePrivateState();
  const packetCurrent =
    packet.data?.packet_status === "CURRENT" && !!packet.data.publication_id;
  const usable =
    !!data &&
    !loading &&
    !packet.loading &&
    !error &&
    !packet.error &&
    data.publication?.packet_status === "CURRENT" &&
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
            今日投资决策
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
              update.retry();
              historical.retry();
              state.retry();
            }}
            aria-label="刷新页面数据"
          >
            刷新页面
          </Button>
          <Link to="/system">数据状态</Link>
        </div>
      </header>
      <p className="opportunity-subtitle" role="status">
        最近更新：
        {update.data?.last_run
          ? `${({ SUCCESS: "完成", PARTIAL: "部分完成", BLOCKED: "失败，保留旧快照" } as Record<string, string>)[update.data.last_run.status] ?? "状态未核验"} · ${updateTime(update.data.last_run.finished_at)}`
          : "尚无可核验运行记录"}
        。
        {update.data?.last_run?.status === "BLOCKED" &&
          "以下只能作为旧快照参考，不能当作本次成功更新。"}
      </p>
      <details className="daily-update-help">
        <summary>更新今日数据与首次连接持仓</summary>
        <p>刷新页面只读取已发布数据；更新行情和计算请在本机终端运行：</p>
        <code className="daily-command">
          &amp; 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe'
          -NoProfile -File
          'D:\GPTProject\value-investment\scripts\current\run_daily_workbench.ps1'
          -Mode SAFE_REFRESH -Open
        </code>
        <p>
          上次发布：{packet.data?.generated_at ?? "尚未读取"}
          。研究批准和本人确认不会由刷新代签。
        </p>
      </details>
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
              行情状态{" "}
              <strong>{quoteFresh ? "发布时已核验" : "发布时未获核验"}</strong>
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
              待触发条件{" "}
              <strong>
                {
                  [...data.sections.value, ...data.sections.hotspot].filter(
                    (item) => judgmentGroup(item) === 2,
                  ).length
                }
              </strong>
            </span>
            <span>
              持仓风险复核{" "}
              <strong>
                {state.risk ? state.risk.blockers.length : "待连接核验"}
              </strong>
            </span>
          </div>
          <HoldingsAttention
            state={state}
            decisionsVerified={true}
            decisions={[
              ...data.sections.value,
              ...data.sections.hotspot,
              ...data.sections.holdings,
            ]}
          />
          <section className="daily-tasks" aria-label="今日人工待办">
            <h2>今天需要做什么</h2>
            <p>
              {quoteFresh
                ? "查看候选的确认与失效条件；未满足就继续观察。"
                : "先更新或核验行情；旧快照不能当作今天的新判断。"}{" "}
              {state.portfolio?.status === "CONNECTED"
                ? "复核持仓风险，并录入你已经实际完成的成交。"
                : "连接持仓后，确认真实资金和投资政策，才可计算个人风险。"}
            </p>
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
