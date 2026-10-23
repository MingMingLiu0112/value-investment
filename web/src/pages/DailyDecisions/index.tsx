import { Link } from "@umijs/max";
import { useState } from "react";
import { Button, Empty, Skeleton, Typography } from "antd";
import { DecisionCard } from "../../components/DecisionCard";
import { HoldingsAttention } from "../../components/HoldingsAttention";
import { ConfirmationTasks } from "../../components/ConfirmationTasks";
import { DailyStrategyReadiness } from "../../components/StrategyReadiness";
import { CurrentScreening } from "../../components/CurrentScreening";
import { DualStrategySelection } from "../../components/DualStrategySelection";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { usePrivateState } from "../../hooks/usePrivateState";
import { api } from "../../services/api";
import type { DailyEvaluationItem, DecisionItem } from "../../types/api";
import { describeCode } from "../../utils/codes";
import { hasValuationResult } from "../../utils/opportunityView";
import { blockerText } from "../../utils/packet";
import {
  readinessDetailUrl,
  readinessStrategy,
} from "../../utils/strategyReadiness";
import {
  judgmentGroup,
  judgmentGroups,
  publicationVersionsMatch,
  hotspotOpportunityQuality,
} from "../../utils/currentJudgment";
import "./opportunities.css";

function updateTime(value: string | null | undefined): string {
  if (value == null || value.trim() === "") return "更新尚未完成，暂无完成时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "时间未核验"
    : `${date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}（北京时间）`;
}

function unavailableDependencyText(value?: string | null): string {
  const code = value?.split(":", 1)[0].trim();
  if (
    code === "VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE" ||
    code === "VALUE_DISCOVERY_RECEIPT_UNAVAILABLE"
  )
    return "价值投资初筛的来源回执缺失或未通过核验，补齐并核验后才能展示候选。";
  // Only translate the code; backend diagnostics can contain local source paths.
  if (code && /^[A-Za-z][A-Za-z0-9_.]*$/.test(code)) {
    const translated = blockerText(describeCode(code));
    if (translated !== code) return translated;
  }
  return "当前结果所需的来源依赖缺失或未通过核验。";
}

function StrategySection({
  title,
  horizon,
  items,
  empty,
  id,
  foldUnvalued = false,
  evaluations = [],
}: {
  title: string;
  horizon: string;
  items: DecisionItem[];
  empty: string;
  id: string;
  foldUnvalued?: boolean;
  evaluations?: DailyEvaluationItem[];
}) {
  const evaluationFor = (item: DecisionItem) =>
    evaluations.find(
      (row) =>
        row.symbol === item.symbol &&
        readinessStrategy(row.strategy) === readinessStrategy(item.strategy),
    );
  const groupFor = (item: DecisionItem) =>
    evaluationFor(item)?.decision_action === "NO_TRADE"
      ? 5
      : judgmentGroup(item);
  const card = (item: DecisionItem) => (
    <DecisionCard key={item.id} item={item} evaluation={evaluationFor(item)} />
  );
  const main = foldUnvalued
    ? items.filter(hasValuationResult)
    : [...items].sort((a, b) => {
        const score = (item: DecisionItem) => {
          const code = hotspotOpportunityQuality(item)?.code;
          return code ? { D: 4, C: 3, B: 2, A: 1, E: 0 }[code] : -1;
        };
        return score(b) - score(a);
      });
  const other = foldUnvalued
    ? items.filter((item) => !hasValuationResult(item))
    : [];
  const counts = {
    formal: items.filter((item) => groupFor(item) === 0).length,
    pending: items.filter((item) => [1, 2].includes(groupFor(item))).length,
    watch: items.filter((item) => [3, 4].includes(groupFor(item))).length,
    noTrade: items.filter((item) => groupFor(item) === 5).length,
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
          {!!counts.noTrade && (
            <span>
              <strong>{counts.noTrade}</strong> 暂不新建仓
            </span>
          )}
        </div>
      </div>
      {!foldUnvalued &&
        !items.some((item) =>
          ["B", "C", "D"].includes(hotspotOpportunityQuality(item)?.code ?? ""),
        ) && (
          <p role="status">
            当前展示的热点计划中，尚无已确认的入场结构；未覆盖证券不作结论。
          </p>
        )}
      {main.length ? (
        <div className="opportunity-list">
          {judgmentGroups.map((label, group) => {
            const rows = main.filter((item) => groupFor(item) === group);
            if (group === 4 && rows.length)
              return (
                <details key={label} aria-label="已失效或等待补齐数据">
                  <summary>
                    已失效 / 等待重新形成结构或补齐数据（{rows.length}）
                  </summary>
                  {rows.map(card)}
                </details>
              );
            return rows.length ? (
              <section key={label} aria-label={label}>
                <h3>
                  {group === 5 &&
                  rows.some(
                    (item) =>
                      evaluationFor(item)?.decision_action === "NO_TRADE",
                  )
                    ? "已评价，暂不新建仓"
                    : label}
                </h3>
                {rows.map(card)}
              </section>
            ) : null;
          })}
        </div>
      ) : (
        <div className="opportunity-empty">
          {other.length ? (
            <>
              <p>
                {other.length}{" "}
                家公司尚无可用的价值投资操作价；可查看已发布研究及未满足条件。
              </p>
              <nav aria-label="价值研究快捷入口">
                {other.map((item) => (
                  <span key={item.id}>
                    <Link to={`/decisions/${encodeURIComponent(item.id)}`}>
                      {item.name} {item.symbol}
                    </Link>{" "}
                  </span>
                ))}
              </nav>
            </>
          ) : (
            <Empty description={empty} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </div>
      )}
      {!!other.length && (
        <details aria-label="其他待研究公司">
          <summary>其他待研究公司（{other.length}）</summary>
          {other.map(card)}
        </details>
      )}
    </section>
  );
}

export default function DailyDecisions() {
  const [selectionRevision, setSelectionRevision] = useState(0);
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
  // Daily already carries the independent hotspot contract. Keep its plan,
  // readiness, counts and explanation from the same response on every refresh.
  const hotspotItems = data?.sections.hotspot ?? [];
  const hotspotDates = usable
    ? [
        ...new Set(
          hotspotItems
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
  const dailyUnavailable =
    data?.status === "UNAVAILABLE" ||
    data?.publication?.packet_status === "UNAVAILABLE";
  const versionMismatch =
    !dailyUnavailable &&
    data?.publication?.packet_status === "CURRENT" &&
    packetCurrent &&
    !!data.publication.publication_id?.trim() &&
    !!packet.data?.publication_id?.trim() &&
    !publicationVersionsMatch(
      data.publication.publication_id,
      packet.data?.publication_id,
    );
  const stopReason =
    error ||
    packet.error ||
    (dailyUnavailable
      ? unavailableDependencyText(
          data?.gate_code || data?.blockers?.[0] || data?.reason,
        )
      : null) ||
    (packet.data?.chain_error
      ? unavailableDependencyText(packet.data.chain_error)
      : null) ||
    (versionMismatch ? "判断与快照版本不一致，请刷新后重试。" : null) ||
    "正式发布链尚未就绪。";
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
              setSelectionRevision((value) => value + 1);
            }}
            aria-label="刷新页面数据"
          >
            刷新页面
          </Button>
          <Link to="/system">数据状态</Link>
        </div>
      </header>
      <nav className="daily-navigation" aria-label="今日工作入口">
        {usable && (
          <>
            <a href="#daily-value">价值投资观察</a>
            <a href="#daily-hotspot">热点波段观察</a>
            <a href="#confirmations">待我确认</a>
          </>
        )}
        <Link to="/portfolio">
          {state.portfolio?.status === "CONNECTED"
            ? "持仓与风险"
            : "连接我的持仓"}
        </Link>
        {state.portfolio?.status === "CONNECTED" && (
          <Link to="/portfolio#portfolio-fill">记录实际成交</Link>
        )}
      </nav>
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
        <Typography.Paragraph
          className="daily-command"
          copyable={{
            text: "& 'C:\\Users\\we\\AppData\\Local\\Programs\\PowerShell\\7\\pwsh.exe' -NoProfile -File 'D:\\GPTProject\\value-investment\\scripts\\current\\run_daily_workbench.ps1' -Mode SAFE_REFRESH -Open",
          }}
        >
          {
            "& 'C:\\Users\\we\\AppData\\Local\\Programs\\PowerShell\\7\\pwsh.exe' -NoProfile -File 'D:\\GPTProject\\value-investment\\scripts\\current\\run_daily_workbench.ps1' -Mode SAFE_REFRESH -Open"
          }
        </Typography.Paragraph>
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
          <p>{stopReason}</p>
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
              已登记证券级复核{" "}
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
          <section
            className="daily-action-conclusion"
            aria-label="明确行动结论"
          >
            <h2>
              {data.actionable_evaluation?.conclusion ===
              "NO_QUALIFIED_NEW_TRADE"
                ? "本次已评价范围内，无符合全部条件的新交易机会。"
                : "本次未形成完整有效的选股决策，不能据此判断市场没有机会。"}
            </h2>
            <p>
              当前发布公司中已评价后暂不新建仓{" "}
              {data.actionable_evaluation?.evaluated_count ?? 0} 家；
              证据或资格不足{" "}
              {data.actionable_evaluation?.unassessable_count ?? "未核验"} 家。
              公共计划不包含个人账户容量，不能计为个人可操作机会。
              暂不新建仓不代表应继续持有；已有持仓的加减仓与退出须独立复核。
            </p>
            <details>
              <summary>逐公司结论与统计范围</summary>
              <ul>
                {data.actionable_evaluation?.items.map((item) => (
                  <li key={`${item.strategy}-${item.symbol}`}>
                    <Link
                      to={readinessDetailUrl(
                        item,
                        [...data.sections.value, ...data.sections.hotspot].find(
                          (row) =>
                            row.symbol === item.symbol &&
                            readinessStrategy(row.strategy) ===
                              readinessStrategy(item.strategy),
                        ),
                      )}
                    >
                      {item.company_name || item.symbol} · {item.symbol}
                    </Link>
                    {item.decision_action === "UNASSESSABLE"
                      ? " · 无法评价 — "
                      : " · 暂不新建仓 — "}
                    {item.decision_reason}
                  </li>
                ))}
              </ul>
            </details>
          </section>
          <DailyStrategyReadiness
            items={data.actionable_evaluation?.items ?? []}
            decisions={[...data.sections.value, ...data.sections.hotspot]}
            companyStatuses={
              packet.data?.source_bindings_verified === true
                ? packet.data.company_statuses
                : undefined
            }
          />
          <DualStrategySelection key={selectionRevision} />
          {update.data?.last_run?.screening && (
            <details>
              <summary>原始初筛与来源核验</summary>
              <CurrentScreening
                scan={update.data.last_run.screening}
                decisions={data.sections.value}
              />
            </details>
          )}
          {update.data?.last_run?.research_priority && (
            <section aria-label="证据研究队列">
              <h3>研究推进</h3>
              {update.data.last_run.research_priority.status ===
              "VERIFIED_RESEARCH_PRIORITY" ? (
                <p>
                  {update.data.last_run.research_priority.as_of}
                  ：年度质量证据可完整评分的深研线索{" "}
                  {
                    update.data.last_run.research_priority.deep_research_count
                  }{" "}
                  家；需要补证{" "}
                  {update.data.last_run.research_priority.enrichment_count}{" "}
                  家，本轮优先处理{" "}
                  {
                    update.data.last_run.research_priority
                      .selected_enrichment_count
                  }{" "}
                  家。 队列选择不代表补证成功、估值获准或交易资格。
                  {update.data.last_run.research_priority.execution?.status ===
                    "VERIFIED_RESEARCH_EXECUTION" && (
                    <>
                      实际执行补证{" "}
                      {
                        update.data.last_run.research_priority.execution
                          .attempted_count
                      }{" "}
                      家， 完成质量重评{" "}
                      {
                        update.data.last_run.research_priority.execution
                          .reevaluated_count
                      }{" "}
                      家， 仍有数据或口径缺口{" "}
                      {
                        update.data.last_run.research_priority.execution
                          .data_gap_count
                      }{" "}
                      家。
                      {update.data.last_run.research_priority.execution
                        .verified_adopted_fact_count != null && (
                        <span>
                          {" "}
                          已核验采纳{" "}
                          {
                            update.data.last_run.research_priority.execution
                              .verified_adopted_fact_count
                          }{" "}
                          个派生事实，
                          {
                            update.data.last_run.research_priority.execution
                              .research_inputs_updated_count
                          }{" "}
                          家已更新研究输入；经济审核独立保留。
                        </span>
                      )}
                      {update.data.last_run.research_priority.execution.items?.map(
                        (item) => (
                          <span key={item.symbol}>
                            {" "}
                            {item.company_name}（{item.symbol}）：
                            {item.extracted_candidates == null
                              ? "原件未通过提取核验。"
                              : `提取 ${item.extracted_candidates} 个候选，匹配留存事实 ${item.matched_candidates ?? "未核验"} 个；匹配不代表新增事实准入。`}
                            {item.adoption?.status ===
                              "VERIFIED_FACT_ADOPTION" && (
                              <span>
                                {" "}
                                已核验采纳 {
                                  item.adoption.adopted_fact_count
                                }{" "}
                                个派生事实；财务覆盖{" "}
                                {item.adoption.quality_coverage_before} →{" "}
                                {item.adoption.quality_coverage_after}；
                                {item.adoption.research_inputs_updated
                                  ? "已更新研究输入"
                                  : "尚未关联研究版本"}
                                。
                              </span>
                            )}
                          </span>
                        ),
                      )}
                    </>
                  )}
                </p>
              ) : (
                <p>研究队列未通过来源校验，不能展示为本轮完成的研究。</p>
              )}
            </section>
          )}
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
            <a href="#confirmations">查看需要我确认的事项</a>
          </section>
          {![...data.sections.value, ...hotspotItems].some(
            (item) => judgmentGroup(item) === 0,
          ) && (
            <p className="opportunity-no-action">
              当前正式操作候选为 0。以下为研究观察，不是买卖指令。
            </p>
          )}
          <div className="opportunity-grid">
            <StrategySection
              id="daily-value"
              foldUnvalued
              title="价值投资"
              horizon="中长期"
              items={data.sections.value}
              evaluations={data.actionable_evaluation?.items}
              empty="当前没有可展示的价值投资线索"
            />
            <StrategySection
              id="daily-hotspot"
              title="热点波段"
              horizon="短中期"
              items={hotspotItems}
              evaluations={data.actionable_evaluation?.items}
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
          <ConfirmationTasks
            decisions={data.sections.value}
            hotspotDecisions={hotspotItems}
            connected={state.portfolio?.status === "CONNECTED"}
            privateReadable={!!state.portfolio}
          />
        </>
      )}
    </Workbench>
  );
}
