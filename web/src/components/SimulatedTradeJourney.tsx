import { useState } from "react";
import { Alert, Button, Table } from "antd";

type State = { cash_cny: string; confirmed_fees_cny: string };
type Journey = {
  namespace: "SIMULATED";
  action: "no_order";
  actual_account_used: false;
  strategy_validated: false;
  broker_execution_permission: false;
  steps: {
    label: string;
    sleeve?: string;
    rationale?: string;
    reason?: string;
    quantity?: string;
    price_cny?: string;
    before: State;
    after: State;
  }[];
  checks: Record<string, boolean>;
  assumptions: { entry_thesis: string; initial_cash_cny: string };
};

const labels: Record<string, string> = {
  CORE_BUY: "价值仓建仓",
  HOTSPOT_BUY: "热点仓建仓",
  CORE_ADD: "价值仓加仓",
  HOLD: "继续持有",
  T_PLUS_ONE_REJECTED: "拒绝当日卖出",
  CORE_REDUCE: "价值仓减仓",
  CORE_EXIT: "价值仓退出",
  HOTSPOT_EXIT: "热点仓退出",
};

export function SimulatedTradeJourney() {
  const [data, setData] = useState<Journey>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  async function run() {
    setLoading(true);
    setError(undefined);
    setData(undefined);
    try {
      const response = await fetch("/api/v1/simulated-trade-journey", {
        cache: "no-store",
      });
      const body: Journey = await response.json();
      if (
        !response.ok ||
        body.namespace !== "SIMULATED" ||
        body.action !== "no_order" ||
        body.actual_account_used !== false ||
        body.strategy_validated !== false ||
        body.broker_execution_permission !== false ||
        !Array.isArray(body.steps) ||
        !body.checks ||
        !Object.values(body.checks).every((value) => value === true)
      ) {
        throw new Error("模拟闭环核验未通过，不展示为已完成。");
      }
      setData(body);
    } catch {
      setError("模拟流程暂不可核验，请检查系统状态；私人账户未被修改。");
    } finally {
      setLoading(false);
    }
  }
  return (
    <section aria-label="隔离模拟账户闭环" style={{ marginBlock: 20 }}>
      <h3>隔离模拟账户闭环</h3>
      <Alert
        type="info"
        showIcon
        message="SIMULATED · 仅验收产品流程，不是实盘建议"
        description="固定假设价格、研究逻辑与费率；临时账本结束后删除，不读取或修改私人账户，不证明选股有效。"
      />
      <Button onClick={run} loading={loading} style={{ marginBlock: 12 }}>
        运行双策略模拟闭环
      </Button>
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p>
            初始模拟现金 {data.assumptions.initial_cash_cny}{" "}
            元；以下两策略共用同一现金账户。
          </p>
          <Table
            size="small"
            rowKey="label"
            pagination={false}
            scroll={{ x: 640 }}
            dataSource={data.steps}
            columns={[
              {
                title: "步骤",
                render: (_, row) => labels[row.label] ?? row.label,
              },
              { title: "模拟股数", dataIndex: "quantity" },
              { title: "假设价格", dataIndex: "price_cny" },
              { title: "之前现金", render: (_, row) => row.before.cash_cny },
              { title: "之后现金", render: (_, row) => row.after.cash_cny },
              {
                title: "累计费用",
                render: (_, row) => row.after.confirmed_fees_cny,
              },
            ]}
            expandable={{
              expandedRowRender: (row) => (
                <p style={{ overflowWrap: "anywhere" }}>
                  {row.rationale ?? row.reason}
                </p>
              ),
            }}
          />
          <p>
            已验证：共用现金、成交确认幂等、T+1
            拒绝、重启一致性、临时账本清理。模拟动作不改变当前正式研究准入。
          </p>
        </>
      )}
    </section>
  );
}
