import {
  Alert,
  Button,
  Col,
  Descriptions,
  Row,
  Segmented,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { Link, useLocation } from "@umijs/max";
import { useCallback, useEffect, useState } from "react";
import { DualSleeveRisk } from "../../components/DualSleeveRisk";
import { HotspotSizingPanel } from "../../components/HotspotSizingPanel";
import type { SizingAssumptionsSelection } from "../../components/HotspotSizingPanel";
import { FillPanel, fillContextFromSearch } from "../../components/FillPanel";
import type { PreparedRecordingRisk } from "../../components/FillPanel";
import type { FillContext } from "../../components/FillPanel";
import { PortfolioSetupForm } from "../../components/PortfolioSetupForm";
import { PositionTable } from "../../components/PositionTable";
import { PortfolioPolicyPanel } from "../../components/PortfolioPolicyPanel";
import { ConfirmedTrades } from "../../components/ConfirmedTrades";
import { PrivateRetrospectivePanel } from "../../components/PrivateRetrospectivePanel";
import { RemoteState } from "../../components/RemoteState";
import { Workbench } from "../../components/Workbench";
import { usePrivateState } from "../../hooks/usePrivateState";
import type { PrivateStateHandle } from "../../hooks/usePrivateState";
import { api } from "../../services/api";
import { reconciliationView } from "../../utils/codes";
import { describeCode } from "../../utils/codes";
import { blockerText } from "../../utils/packet";
import { HoldingsAttention } from "../../components/HoldingsAttention";
import { useApi } from "../../hooks/useApi";
import { PortfolioReconciliationPanel } from "../../components/PortfolioReconciliationPanel";
import { EntryThesisPanel } from "../../components/EntryThesisPanel";
import { CommittedRiskPanel } from "../../components/CommittedRiskPanel";
import { SimulatedTradeJourney } from "../../components/SimulatedTradeJourney";

/**
 * TL10-RC：私人状态来自与每日页共用的 usePrivateState；台账损坏或目录
 * 不可用时按 UNAVAILABLE 如实报出，不显示成“尚未接入”，也不展示任何数字。
 */
function PrivateStateAlert({ state }: { state: PrivateStateHandle }) {
  const type =
    state.kind === "UNAVAILABLE"
      ? "warning"
      : state.kind === "LOCKED"
        ? "info"
        : "warning";
  return (
    <Alert
      style={{ marginTop: 16 }}
      type={type}
      showIcon
      message={state.label}
      description={
        <>
          <div>{state.detail}</div>
          {state.nextStep && (
            <div style={{ marginTop: 4 }}>{state.nextStep}</div>
          )}
          {state.blockers.length > 0 && (
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {state.blockers.map((code) => (
                <li key={code}>{blockerText(code)}</li>
              ))}
            </ul>
          )}
          <a style={{ marginLeft: 12 }} onClick={state.retry}>
            重试
          </a>
        </>
      }
    />
  );
}

export default function Portfolio() {
  const location = useLocation();
  const context = fillContextFromSearch(location.search);
  // A different security/strategy/version must not inherit unsaved sizing or
  // prepared fill state. Fragment-only navigation preserves the current form.
  return (
    <PortfolioContext
      key={JSON.stringify(context)}
      context={context}
      hash={location.hash}
    />
  );
}

function PortfolioContext({
  context,
  hash,
}: {
  context: FillContext;
  hash: string;
}) {
  const {
    symbol: initialSymbol,
    strategy: initialSleeve,
    decision_id: initialDecisionId,
    research_version: initialResearchVersion,
  } = context;
  const [entrySaved, setEntrySaved] = useState<{
    fill: string;
    message: string;
  }>();
  const [sizingSymbol, setSizingSymbol] = useState(initialSymbol ?? "");
  const [sizingSleeve, setSizingSleeve] = useState<
    "CORE_VALUE" | "HOTSPOT_SATELLITE"
  >(initialSleeve === "CORE_VALUE" ? "CORE_VALUE" : "HOTSPOT_SATELLITE");
  const [riskAssumptions, setRiskAssumptions] = useState<
    (SizingAssumptionsSelection & { revision: number; account: string }) | null
  >(null);
  const [preparedRisk, setPreparedRisk] = useState<PreparedRecordingRisk>();
  const loadRiskContext = useCallback(
    (signal: AbortSignal) => {
      if (!/^\d{6}$/.test(sizingSymbol))
        return Promise.reject(new Error("请选择六位证券代码"));
      return api.riskContext(sizingSymbol, signal);
    },
    [sizingSymbol],
  );
  const riskContext = useApi(loadRiskContext);
  const state = usePrivateState();
  const judgments = useApi(api.daily);
  const data = state.portfolio;
  const risk = state.risk;
  const reconciliation = reconciliationView(data?.reconciliation);
  const account = risk?.facts?.account_scope ?? "";
  const captureRequest = useCallback(
    (selection: SizingAssumptionsSelection | null) => {
      setRiskAssumptions(
        selection && data
          ? {
              ...selection,
              assumptions: { ...selection.assumptions },
              revision: data.revision,
              account,
            }
          : null,
      );
    },
    [data?.revision, account],
  );

  const refreshAll = () => {
    setRiskAssumptions(null);
    state.retry();
    riskContext.retry();
    judgments.retry();
  };

  useEffect(() => {
    if (state.kind === "LOADING" || !data) return;
    const id = hash.slice(1);
    if (
      ![
        "portfolio-positions",
        "portfolio-risk",
        "portfolio-sizing",
        "portfolio-fill",
        "portfolio-setup",
      ].includes(id)
    )
      return;
    const target =
      document.getElementById(id) ??
      (data.status === "NOT_CONNECTED"
        ? document.getElementById("portfolio-setup")
        : null);
    if (target instanceof HTMLDetailsElement) target.open = true;
    target?.scrollIntoView({ block: "start" });
  }, [hash, state.kind, data?.status]);

  if (state.kind === "LOADING") {
    return (
      <Workbench>
        <Typography.Title level={2}>我的持仓</Typography.Title>
        <RemoteState loading error={undefined} retry={state.retry} />
      </Workbench>
    );
  }
  if (state.kind === "LOCKED" || state.kind === "UNAVAILABLE" || !data) {
    return (
      <Workbench>
        <Typography.Title level={2}>我的持仓</Typography.Title>
        <PrivateStateAlert state={state} />
        <SimulatedTradeJourney />
      </Workbench>
    );
  }
  return (
    <Workbench>
      <Typography.Title level={2}>我的持仓</Typography.Title>
      <SimulatedTradeJourney />
      <nav className="portfolio-navigation" aria-label="持仓工作入口">
        <Link to="/daily">返回今日双策略</Link>
        {data.status === "NOT_CONNECTED" ? (
          <a href="#portfolio-setup">填写初始账户与持仓</a>
        ) : (
          <>
            <a href="#portfolio-positions">已确认持仓</a>
            <a href="#portfolio-risk">两策略风险</a>
            <a
              href="#portfolio-sizing"
              onClick={() => {
                const target = document.getElementById("portfolio-sizing");
                if (target instanceof HTMLDetailsElement) target.open = true;
              }}
            >
              条件仓位试算
            </a>
            <a href="#portfolio-fill">记录实际成交</a>
          </>
        )}
      </nav>
      {initialSymbol && (
        <p role="status">
          当前复核 {initialSymbol} ·{" "}
          {initialSleeve === "CORE_VALUE"
            ? "价值投资"
            : initialSleeve === "HOTSPOT_SATELLITE"
              ? "热点波段"
              : "策略待本人选择"}
          。 仅带入证券与研究身份，不预填成交价格或数量，也不代表获准交易。
        </p>
      )}
      {risk?.facts?.account_scope?.startsWith("TEST_ONLY") && (
        <Alert
          type="warning"
          showIcon
          message="TEST_ONLY 隔离演练账户"
          description="以下资金、持仓及成交仅用于工程验证，不是你的真实账户，不能据此形成个人交易建议。"
        />
      )}
      <Alert
        type="info"
        showIcon
        message={`行情状态：${describeCode(data.valuation.status)}`}
        description={data.valuation.reason}
      />
      {data.status === "NOT_CONNECTED" ? (
        <>
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message={state.label}
            description={
              <>
                {state.detail}
                <div style={{ marginTop: 4 }}>
                  请在下方逐笔人工确认初始持仓；确认真实成交后不再显示本提示。
                </div>
              </>
            }
          />
          <section id="portfolio-setup" aria-label="初始化账户与持仓">
            <PortfolioSetupForm onDone={refreshAll} />
          </section>
        </>
      ) : (
        <>
          {state.kind === "BLOCKED_PRIVATE_INPUT" && (
            <Alert
              style={{ marginTop: 16 }}
              type="warning"
              showIcon
              message={state.label}
              description={state.detail}
            />
          )}
          <Row gutter={24} style={{ marginTop: 24 }}>
            <Col xs={12} md={6}>
              <Statistic
                title="总权益（元，核验口径）"
                value={data.total_equity_cny ?? "未核验"}
                precision={2}
              />
            </Col>
            <Col xs={12} md={6}>
              <Statistic
                title="可用现金（元）"
                value={data.cash_cny ?? "未提供"}
                precision={2}
              />
            </Col>
            <Col xs={12} md={6}>
              <Statistic
                title="已实现盈亏（元）"
                value={data.realized_pnl_cny ?? "未提供"}
                precision={2}
              />
            </Col>
            <Col xs={12} md={6}>
              <Statistic
                title="浮动盈亏（元，核验行情）"
                value={data.unrealized_pnl_total_cny ?? "未核验"}
                precision={2}
              />
            </Col>
            {data.sleeve_summaries?.map((sleeve) => (
              <Col xs={12} md={6} key={sleeve.sleeve}>
                <Statistic
                  title={
                    sleeve.sleeve === "CORE_VALUE" ? "价值池仓位" : "热点池仓位"
                  }
                  value={
                    sleeve.weight_pct == null
                      ? "未核验"
                      : Number(sleeve.weight_pct)
                  }
                  precision={2}
                  suffix={sleeve.weight_pct != null ? "%" : undefined}
                />
                <small>持仓成本 {sleeve.cost_basis_cny} 元</small>
              </Col>
            ))}
            <Col xs={12} md={6}>
              <Statistic
                title="总仓位"
                value={
                  data.total_position_weight_pct == null
                    ? "未核验"
                    : Number(data.total_position_weight_pct)
                }
                precision={2}
                suffix={
                  data.total_position_weight_pct != null ? "%" : undefined
                }
              />
            </Col>
            <Col xs={12} md={6}>
              <Statistic
                title="已确认现金预留（元）"
                value={data.confirmed_cash_reserve_cny ?? "尚未确认"}
              />
            </Col>
          </Row>
          <HoldingsAttention
            state={state}
            decisionsVerified={
              !!judgments.data &&
              !judgments.loading &&
              !judgments.error &&
              judgments.data.publication?.packet_status === "CURRENT"
            }
            decisions={
              judgments.data
                ? [
                    ...judgments.data.sections.value,
                    ...judgments.data.sections.hotspot,
                    ...judgments.data.sections.holdings,
                  ]
                : []
            }
          />
          {entrySaved && <Alert type="success" message={entrySaved.message} />}
          <EntryThesisPanel
            revision={data.revision}
            onDone={refreshAll}
            initialFill={entrySaved?.fill}
            onSaved={(fill, message) => setEntrySaved({ fill, message })}
          />
          <Descriptions
            bordered
            column={2}
            style={{ marginTop: 16 }}
            items={[
              {
                key: "reconciliation",
                label: "对账状态",
                children: reconciliation ? (
                  <Space direction="vertical" size={0}>
                    <span>{reconciliation.statusText}</span>
                    <Typography.Text type="secondary">
                      范围：{reconciliation.scopeText}
                    </Typography.Text>
                    {reconciliation.reasonText && (
                      <Typography.Text type="warning">
                        {reconciliation.reasonText}
                      </Typography.Text>
                    )}
                    {reconciliation.reconciledAt && (
                      <Typography.Text type="secondary">
                        对账时间：{reconciliation.reconciledAt}
                      </Typography.Text>
                    )}
                  </Space>
                ) : (
                  "尚未执行对账"
                ),
              },
              {
                key: "as_of",
                label: "最新账本事实日期",
                children: data.as_of || "未提供",
              },
              {
                key: "blockers",
                label: "当前阻塞",
                children: data.blockers.length ? (
                  <Space wrap>
                    {data.blockers.map((item) => (
                      <Tag key={item}>{item}</Tag>
                    ))}
                  </Space>
                ) : (
                  "无"
                ),
              },
            ]}
          />
          {data.policy && (
            <details style={{ marginTop: 16 }}>
              <summary>历史初始约束与台账修订 {data.revision}</summary>
              <Descriptions
                title="已记录的风险约束（原始输入）"
                bordered
                column={2}
                style={{ marginTop: 16 }}
                items={Object.entries(data.policy).map(([key, value]) => ({
                  key,
                  label: key,
                  children: String(value ?? "未提供"),
                }))}
              />
            </details>
          )}
          <section id="portfolio-positions" aria-label="已确认持仓">
            <PositionTable title="已确认持仓" positions={data.positions} />
          </section>
          <section id="portfolio-risk" aria-label="双策略风险核验">
            <DualSleeveRisk
              data={risk}
              loading={false}
              error={
                risk
                  ? undefined
                  : "双策略风险复核读取失败；读取成功前不展示任何仓位结论，请重试。"
              }
              retry={state.retry}
            />
            <PortfolioPolicyPanel
              revision={data.revision}
              fillPending={!!data.pending_draft}
              onDone={refreshAll}
            />
            <CommittedRiskPanel
              key={`risk-basis-${data.revision}`}
              revision={data.revision}
              onDone={refreshAll}
            />
          </section>
          <details id="portfolio-sizing" style={{ marginTop: 16 }}>
            <summary>查看条件性仓位上限</summary>
            <Segmented
              aria-label="仓位试算策略"
              value={sizingSleeve}
              options={[
                { label: "价值仓", value: "CORE_VALUE" },
                { label: "热点仓", value: "HOTSPOT_SATELLITE" },
              ]}
              onChange={(value) =>
                setSizingSleeve(value as "CORE_VALUE" | "HOTSPOT_SATELLITE")
              }
            />
            <HotspotSizingPanel
              key={sizingSleeve}
              sleeve={sizingSleeve}
              initialSymbol={sizingSymbol || undefined}
              onPreview={api.riskPreview}
              context={
                !riskContext.loading && !riskContext.error
                  ? riskContext.data
                  : undefined
              }
              onConfirmCosts={api.confirmCosts}
              onContextRefresh={refreshAll}
              onSymbolChange={setSizingSymbol}
              onRequest={captureRequest}
            />
          </details>
          <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
            已确认成交记录
          </Typography.Title>
          <ConfirmedTrades trades={data.trades} />
          <PrivateRetrospectivePanel trades={data.trades} />
          <section id="portfolio-fill" aria-label="记录实际成交">
            <FillPanel
              revision={data.revision}
              draft={data.pending_draft}
              onDone={refreshAll}
              initialSymbol={initialSymbol}
              initialSleeve={initialSleeve}
              initialDecisionId={initialDecisionId}
              initialResearchVersion={initialResearchVersion}
              preparedRisk={preparedRisk}
              onPreparedRisk={setPreparedRisk}
              riskAssumptions={
                riskAssumptions?.revision === data.revision &&
                riskAssumptions.account === account &&
                riskAssumptions.symbol === sizingSymbol &&
                riskAssumptions.sleeve === sizingSleeve
                  ? riskAssumptions
                  : undefined
              }
            />
          </section>
          <PortfolioReconciliationPanel
            portfolio={data}
            onConfirm={api.confirmReconciliation}
            onDone={refreshAll}
          />
          <Space style={{ marginTop: 24 }}>
            <Button onClick={refreshAll}>刷新</Button>
          </Space>
        </>
      )}
    </Workbench>
  );
}
