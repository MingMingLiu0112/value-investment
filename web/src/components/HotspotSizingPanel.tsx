import { ProForm, ProFormText } from "@ant-design/pro-components";
import type { ProFormInstance } from "@ant-design/pro-components";
import { Alert, Descriptions, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../services/api";
import { blockerText } from "../utils/packet";
import type { RiskFacts } from "../types/api";
import type { PrivateRiskContext } from "./PrivateRiskContext";
import { CostAssumptionsPanel } from "./CostAssumptionsPanel";
import { reusableCostFields } from "./PrivateRiskContext";

export type HotspotSizingRequest = {
  symbol: string;
  assumptions: Record<string, string>;
};
export type HotspotSizingResponse = {
  action: "no_order";
  facts?: RiskFacts | null;
  sizing_preview: {
    symbol: string;
    review_quantity: number | null;
    blockers: string[];
    formal_eligibility: boolean | null;
    plan_binding: {
      publication_id: string;
      plan: { entry_trigger_price?: string; invalidation_price?: string };
    } | null;
    sizing_details?: {
      cash_required_cny?: string;
      stressed_loss_cny?: string;
      planned_risk_limit_cny?: string;
      stressed_exit_price_cny?: string;
      full_capital_at_risk_cny?: string;
    } | null;
  };
};

export const sizingFields = [
  ["gap_stress_cny", "跳空压力（元/股）"],
  ["entry_slippage_cny", "买入滑点（元/股）"],
  ["exit_slippage_cny", "卖出滑点（元/股）"],
  ["buy_fee_fraction", "买入费用比率（0 到 1）"],
  ["sell_fee_fraction", "卖出费用比率（0 到 1）"],
  ["minimum_buy_fee_cny", "最低买入费用（元）"],
  ["minimum_sell_fee_cny", "最低卖出费用（元）"],
  ["lot_size", "交易单位（股）"],
  ["max_trade_notional_cny", "本人本笔资金上限（元）"],
] as const;

function gapLabel(code: string) {
  if (code.startsWith("ASSUMPTION_MISSING:")) {
    const key = code.split(":")[1];
    return `尚未填写${sizingFields.find(([name]) => name === key)?.[1] ?? key}`;
  }
  const labels: Record<string, string> = {
    PUBLIC_SNAPSHOT_UNAVAILABLE: "当前公开判断尚不可核验",
    PUBLICATION_VERSION_MISMATCH: "公开判断版本已变化，请刷新",
    CURRENT_PRICE_REGISTRY_CHANGED: "当前价格证据已变化，请刷新",
    CURRENT_PLAN_UNAVAILABLE_OR_CHANGED: "所选证券的当前计划不可核验或已变化",
    CURRENT_PLAN_STALE_OR_INVALIDATED:
      "所选价格计划已过期、失效或不属于今日候选",
    PLAN_PRICE_MISSING: "当前计划缺入场价或保护价",
    PLAN_PROTECTION_INVALID: "当前保护价不低于入场价，无法以损定量",
    CANDIDATE_LIQUIDITY_UNKNOWN: "证券流动性属性尚未核验",
    PRICE_LIMIT_STATE_UNKNOWN: "涨跌停执行状态尚未核验",
    EXTERNAL_ACCOUNT_RECONCILIATION_MISSING:
      "尚未提供本人逐项核对的外部账户对账引用",
  };
  return labels[code] ?? blockerText(code);
}

export function HotspotSizingPanel({
  initialSymbol,
  onPreview,
  context,
  onConfirmCosts,
  onContextRefresh,
  onSymbolChange,
}: {
  initialSymbol?: string;
  onPreview: (request: HotspotSizingRequest) => Promise<HotspotSizingResponse>;
  context?: PrivateRiskContext;
  onConfirmCosts?: (
    body: Record<string, unknown>,
  ) => Promise<{ action: "no_order"; status: string }>;
  onContextRefresh?: () => void;
  onSymbolChange?: (symbol: string) => void;
}) {
  const [result, setResult] = useState<HotspotSizingResponse>();
  const [failure, setFailure] = useState<string>();
  const generation = useRef(0);
  const formRef = useRef<ProFormInstance>();
  useEffect(() => {
    generation.current++;
    setResult(undefined);
    setFailure(undefined);
  }, [initialSymbol, context]);
  const currentContext =
    context?.action === "no_order" && context.symbol === initialSymbol
      ? context
      : undefined;
  const confirmedCosts =
    currentContext?.cost_profile &&
    Date.parse(currentContext.cost_profile.valid_until) > Date.now()
      ? currentContext.cost_profile.costs
      : {};
  useEffect(() => {
    formRef.current?.setFieldsValue(
      Object.fromEntries(
        reusableCostFields.map((key) => [key, confirmedCosts?.[key]]),
      ),
    );
  }, [currentContext?.symbol, currentContext?.revision]);
  const submit = async (form: Record<string, unknown>) => {
    const current = ++generation.current;
    setFailure(undefined);
    setResult(undefined);
    try {
      const assumptions = Object.fromEntries(
        sizingFields.flatMap(([key]) => {
          const value = String(form[key] ?? "").trim();
          return value ? [[key, value]] : [];
        }),
      );
      const response = await onPreview({
        symbol: String(form.symbol ?? "").trim(),
        assumptions,
      });
      if (
        response.action !== "no_order" ||
        !response.sizing_preview ||
        response.sizing_preview.symbol !== String(form.symbol ?? "").trim() ||
        !Array.isArray(response.sizing_preview.blockers)
      )
        throw new Error("仓位试算响应无法核验，请刷新后重试。");
      if (current === generation.current) setResult(response);
      return true;
    } catch (cause) {
      if (current === generation.current)
        setFailure(
          cause instanceof ApiError
            ? String(cause.detail ?? "仓位试算未完成")
            : cause instanceof Error
              ? cause.message
              : "仓位试算未完成",
        );
      return false;
    }
  };
  const preview = result?.sizing_preview;
  return (
    <section aria-label="热点条件性仓位试算">
      <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
        热点条件性仓位试算
      </Typography.Title>
      <Alert
        type="info"
        showIcon
        message="仅供本人风险复核，不代表可以买入，也不保证保护价能够成交"
      />
      {failure && (
        <Alert
          type="error"
          showIcon
          message="仓位试算未完成"
          description={failure}
        />
      )}
      <ProForm
        formRef={formRef}
        layout="vertical"
        onFinish={submit}
        onValuesChange={(changed: Record<string, unknown>) => {
          generation.current++;
          setResult(undefined);
          setFailure(undefined);
          if ("symbol" in changed) {
            formRef.current?.setFieldsValue(
              Object.fromEntries(sizingFields.map(([key]) => [key, undefined])),
            );
            onSymbolChange?.(String(changed.symbol ?? "").trim());
          }
        }}
        submitter={{
          resetButtonProps: false,
          searchConfig: { submitText: "复核条件性数量" },
        }}
      >
        <ProFormText
          name="symbol"
          label="证券代码"
          initialValue={initialSymbol}
          rules={[
            { required: true, message: "请填写证券代码" },
            { pattern: /^\d{6}$/, message: "六位证券代码" },
          ]}
        />
        {currentContext?.policy && (
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: "budget",
                label: "已确认热点资金池（元）",
                children: String(
                  currentContext.policy.hotspot_budget_cny ?? "未知",
                ),
              },
              {
                key: "risk",
                label: "已确认热点单笔风险（%）",
                children: String(
                  currentContext.policy.hotspot_single_trade_risk_pct ?? "未知",
                ),
              },
              {
                key: "reserve",
                label: "已确认现金预留（元）",
                children: String(
                  currentContext.policy.cash_reserve_cny ?? "未知",
                ),
              },
            ]}
          />
        )}
        {currentContext?.rule_gaps.map((gap) => (
          <Alert key={gap} type="warning" message={gap} />
        ))}
        {currentContext?.cost_profile && (
          <Alert
            type="info"
            message="已读取本人确认的成本设定"
            description={`有效期至 ${currentContext.cost_profile.valid_until}`}
          />
        )}
        <ProFormText
          name="max_trade_notional_cny"
          label="本人本笔资金上限（元）"
          rules={[{ pattern: /^\d+(\.\d+)?$/, message: "填写非负数字" }]}
        />
        <details>
          <summary>高级参数：费用、滑点、压力及交易单位</summary>
          <ProForm.Group>
            {sizingFields
              .filter(([key]) => key !== "max_trade_notional_cny")
              .map(([key, label]) => (
                <ProFormText
                  key={key}
                  name={key}
                  label={label}
                  width="md"
                  initialValue={confirmedCosts?.[key]}
                  rules={[
                    {
                      pattern:
                        key === "lot_size" ? /^[1-9]\d*$/ : /^\d+(\.\d+)?$/,
                      message:
                        key === "lot_size"
                          ? "填写正整数交易单位"
                          : "填写非负数字",
                    },
                  ]}
                />
              ))}
          </ProForm.Group>
        </details>
      </ProForm>
      {onConfirmCosts && currentContext && (
        <CostAssumptionsPanel
          revision={currentContext.revision}
          onConfirm={onConfirmCosts}
          onDone={() => {
            generation.current++;
            setResult(undefined);
            onContextRefresh?.();
          }}
        />
      )}
      {preview && (
        <>
          {result?.facts && (
            <Descriptions
              column={1}
              size="small"
              items={[
                {
                  key: "cashFact",
                  label: "账本现金（元）",
                  children: result.facts.cash_cny,
                },
                {
                  key: "costFact",
                  label: "持仓总成本（元）",
                  children: result.facts.cost_basis_total_cny,
                },
                {
                  key: "pnlFact",
                  label: "已实现盈亏（元）",
                  children: result.facts.realized_pnl_cny,
                },
              ]}
            />
          )}
          <Descriptions
            column={1}
            size="small"
            items={[
              { key: "symbol", label: "证券", children: preview.symbol },
              {
                key: "entry",
                label: "核验计划入场价",
                children:
                  preview.plan_binding?.plan.entry_trigger_price ?? "无法核验",
              },
              {
                key: "stop",
                label: "核验计划保护价",
                children:
                  preview.plan_binding?.plan.invalidation_price ?? "无法核验",
              },
              {
                key: "quantity",
                label: "条件性数量上限（股）",
                children:
                  preview.review_quantity == null || preview.blockers.length
                    ? "暂不能计算"
                    : preview.review_quantity,
              },
              {
                key: "cash",
                label: "含费用资金占用（元）",
                children:
                  preview.sizing_details?.cash_required_cny ?? "暂不能计算",
              },
              {
                key: "riskLimit",
                label: "本笔可用风险预算（元）",
                children:
                  preview.sizing_details?.planned_risk_limit_cny ??
                  "尚不能核验",
              },
              {
                key: "loss",
                label: "假设压力损失（元）",
                children:
                  preview.sizing_details?.stressed_loss_cny ?? "暂不能计算",
              },
              {
                key: "stressExit",
                label: "假设压力退出价（元，不保证成交）",
                children:
                  preview.sizing_details?.stressed_exit_price_cny ??
                  "暂不能计算",
              },
              {
                key: "fullCapital",
                label: "全部投入本金风险（元）",
                children:
                  preview.sizing_details?.full_capital_at_risk_cny ??
                  "暂不能计算",
              },
            ]}
          />
          {!!preview.blockers.length && (
            <Alert
              type="warning"
              showIcon
              message="个人仓位条件尚不完整"
              description={
                <ul>
                  {preview.blockers.map((code) => (
                    <li key={code}>{gapLabel(code)}</li>
                  ))}
                </ul>
              }
            />
          )}
        </>
      )}
    </section>
  );
}
