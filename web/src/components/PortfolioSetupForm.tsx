import {
  ProForm,
  ProFormDatePicker,
  ProFormDateTimePicker,
  ProFormList,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from "@ant-design/pro-components";
import { Alert } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { ApiError, api } from "../services/api";

const AMOUNT = /^\d+(\.\d{1,4})?$/;
const SHARES = /^\d+$/;

function text(value: unknown): string {
  return String(value ?? "").trim();
}

export function PortfolioSetupForm({ onDone }: { onDone: () => void }) {
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState<string>();

  const submit = async (form: Record<string, unknown>) => {
    setFailure(undefined);
    setNotice(undefined);
    const rows = (form.holdings as Record<string, unknown>[] | undefined) ?? [];
    const holdings = rows.map((row) => ({
      symbol: text(row.symbol),
      exchange: text(row.exchange).toUpperCase(),
      quantity: text(row.quantity),
      cost_basis_cny: text(row.cost_basis_cny),
    }));
    const sleeveAllocations: Record<string, Record<string, string>> = {};
    rows.forEach((row, index) => {
      sleeveAllocations[holdings[index].symbol] = {
        CORE_VALUE: text(row.core_quantity) || "0",
        HOTSPOT_SATELLITE: text(row.satellite_quantity) || "0",
      };
    });
    const policy: Record<string, string> = {};
    for (const field of [
      "investable_assets_cny",
      "minimum_cash_cny",
      "max_single_security_pct",
      "max_single_industry_pct",
    ]) {
      const value = text(form[field]);
      if (value) policy[field] = value;
    }
    const risk = text(form.risk_tolerance);
    if (risk) policy.risk_tolerance = risk;
    try {
      await api.initializePortfolio({
        idempotency_key: crypto.randomUUID(),
        expected_revision: 0,
        account_scope: text(form.account_scope),
        as_of: dayjs(form.as_of as string).format("YYYY-MM-DD"),
        cash_cny: text(form.cash_cny),
        holdings,
        sleeve_allocations: sleeveAllocations,
        policy,
        confirmation_note: text(form.confirmation_note),
        confirmed_at: dayjs(form.confirmed_at as string).format(
          "YYYY-MM-DDTHH:mm:ssZ",
        ),
      });
      setNotice("初始持仓已记录为人工确认结果。");
      onDone();
    } catch (cause) {
      if (cause instanceof ApiError)
        setFailure(`${cause.code}：${String(cause.detail ?? "")}`);
      else
        setFailure(
          cause instanceof Error ? cause.message : "提交失败，请稍后重试",
        );
    }
  };

  return (
    <ProForm
      layout="vertical"
      onFinish={submit}
      submitter={{ searchConfig: { submitText: "确认并记录初始持仓" } }}
    >
      {failure && (
        <Alert
          type="error"
          showIcon
          message="未能记录初始持仓"
          description={failure}
        />
      )}
      {notice && <Alert type="success" showIcon message={notice} />}
      <ProFormText
        name="account_scope"
        label="账户标识"
        placeholder="例如本人 A 股账户"
        rules={[{ required: true, message: "请填写账户标识" }]}
      />
      <ProFormDatePicker
        name="as_of"
        label="持仓核对日期"
        rules={[{ required: true, message: "请选择持仓核对日期" }]}
      />
      <ProFormText
        name="cash_cny"
        label="可用现金（元）"
        placeholder="例如 50000.00"
        rules={[
          { required: true, message: "请填写可用现金" },
          { pattern: AMOUNT, message: "现金只能是非负数字" },
        ]}
      />
      <ProFormList
        name="holdings"
        label="初始持仓（逐笔人工核对）"
        min={1}
        creatorButtonProps={{ creatorButtonText: "添加一只持仓" }}
        copyIconProps={false}
      >
        <ProFormText
          name="symbol"
          label="证券代码"
          width="sm"
          rules={[{ pattern: /^\d{6}$/, message: "证券代码为 6 位数字" }]}
        />
        <ProFormSelect
          name="exchange"
          label="交易所"
          width="sm"
          options={[
            { value: "SSE", label: "上交所 SSE" },
            { value: "SZSE", label: "深交所 SZSE" },
            { value: "BSE", label: "北交所 BSE" },
          ]}
          rules={[{ required: true, message: "请选择交易所" }]}
        />
        <ProFormText
          name="quantity"
          label="股数"
          width="sm"
          rules={[
            { required: true, message: "请填写股数" },
            { pattern: SHARES, message: "股数为整数" },
          ]}
        />
        <ProFormText
          name="cost_basis_cny"
          label="持仓成本合计（元）"
          width="sm"
          rules={[
            { required: true, message: "请填写持仓成本合计" },
            { pattern: AMOUNT, message: "成本只能是非负数字" },
          ]}
        />
        <ProFormText
          name="core_quantity"
          label="其中价值池股数"
          width="sm"
          rules={[
            { required: true, message: "请填写价值池股数，没有则填 0" },
            { pattern: SHARES, message: "股数为整数" },
          ]}
        />
        <ProFormText
          name="satellite_quantity"
          label="其中情绪卫星仓股数"
          width="sm"
          rules={[
            { required: true, message: "请填写卫星仓股数，没有则填 0" },
            { pattern: SHARES, message: "股数为整数" },
          ]}
        />
      </ProFormList>
      <ProFormText
        name="investable_assets_cny"
        label="可投资总资产（元）"
        placeholder="用于风险预算的公开数字，可留空"
        rules={[{ pattern: AMOUNT, message: "只能是非负数字" }]}
      />
      <ProFormText
        name="minimum_cash_cny"
        label="现金底线（元）"
        rules={[{ pattern: AMOUNT, message: "只能是非负数字" }]}
      />
      <ProFormText
        name="max_single_security_pct"
        label="单只上限（%）"
        rules={[{ pattern: AMOUNT, message: "只能是非负数字" }]}
      />
      <ProFormText
        name="max_single_industry_pct"
        label="单行业上限（%）"
        rules={[{ pattern: AMOUNT, message: "只能是非负数字" }]}
      />
      <ProFormText
        name="risk_tolerance"
        label="风险偏好说明"
        placeholder="例如：可承受单只 20% 回撤"
      />
      <ProFormDateTimePicker
        name="confirmed_at"
        label="确认时间"
        initialValue={dayjs()}
        rules={[{ required: true, message: "请选择确认时间" }]}
      />
      <ProFormTextArea
        name="confirmation_note"
        label="确认说明"
        placeholder="例如：已与券商对账单逐笔核对"
        rules={[{ required: true, message: "请填写确认说明" }]}
      />
    </ProForm>
  );
}
