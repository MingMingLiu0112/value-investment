import {
  ProForm,
  ProFormDatePicker,
  ProFormDateTimePicker,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from "@ant-design/pro-components";
import {
  Alert,
  Button,
  Descriptions,
  Input,
  Popconfirm,
  Space,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { ApiError, api } from "../services/api";
import type { PortfolioDraft } from "../types/api";
import { formatMoney } from "../utils/format";
import { PositionTable, sleeveLabel } from "./PositionTable";

const AMOUNT = /^\d+(\.\d{1,4})?$/;
const SHARES = /^\d+$/;

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function failureMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError)
    return `${cause.code}：${String(cause.detail ?? "")}`;
  return cause instanceof Error ? cause.message : fallback;
}

function DraftReview({
  draft,
  revision,
  onDone,
}: {
  draft: PortfolioDraft;
  revision: number;
  onDone: () => void;
}) {
  const [failure, setFailure] = useState<string>();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const fill = draft.fill as Record<string, unknown>;

  const confirmDraft = async () => {
    setBusy(true);
    setFailure(undefined);
    try {
      await api.confirmFill({
        idempotency_key: crypto.randomUUID(),
        expected_revision: revision,
        prepared_record_sha256: draft.prepared_record_sha256,
        confirmed_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
        confirmation_note: note || "已在工作台确认该笔成交",
      });
      onDone();
    } catch (cause) {
      setFailure(failureMessage(cause, "确认失败"));
    } finally {
      setBusy(false);
    }
  };

  const cancelDraft = async () => {
    setBusy(true);
    setFailure(undefined);
    try {
      await api.cancelFill({
        idempotency_key: crypto.randomUUID(),
        expected_revision: revision,
        prepared_record_sha256: draft.prepared_record_sha256,
        cancelled_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
        reason: note || "录入有误，人工作废",
      });
      onDone();
    } catch (cause) {
      setFailure(failureMessage(cause, "作废失败"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {failure && (
        <Alert
          type="error"
          showIcon
          message="草稿处理失败"
          description={failure}
        />
      )}
      <Alert
        style={{ marginTop: 16 }}
        type="warning"
        showIcon
        message="待确认成交草稿（DRAFT_UNRECONFIRMED）"
        description="草稿尚未计入持仓与现金，确认或作废后才会写入私人台账。"
      />
      <Descriptions
        bordered
        column={2}
        style={{ marginTop: 16 }}
        items={[
          {
            key: "txn",
            label: "成交编号",
            children: text(fill.transaction_id),
          },
          { key: "side", label: "方向", children: text(fill.side) },
          {
            key: "sleeve",
            label: "资金池",
            children: sleeveLabel(text(fill.sleeve)),
          },
          { key: "symbol", label: "证券代码", children: text(fill.symbol) },
          { key: "quantity", label: "股数", children: text(fill.quantity) },
          { key: "price", label: "价格（元）", children: text(fill.price_cny) },
          { key: "fees", label: "费用（元）", children: text(fill.fees_cny) },
          { key: "date", label: "成交日期", children: text(fill.trade_date) },
          {
            key: "cash",
            label: "确认后现金（元）",
            children: formatMoney(draft.cash_cny),
          },
          {
            key: "pnl",
            label: "确认后已实现盈亏（元）",
            children: formatMoney(draft.realized_pnl_cny),
          },
        ]}
      />
      <PositionTable
        title="确认后持仓（预览，尚未写入）"
        positions={draft.positions}
      />
      <Space style={{ marginTop: 16 }} wrap>
        <div>
          <Typography.Text type="secondary">处理说明</Typography.Text>
          <Input
            style={{ width: 320, display: "block" }}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：已核对券商成交单"
          />
        </div>
        <Button type="primary" loading={busy} onClick={confirmDraft}>
          确认成交
        </Button>
        <Popconfirm
          title="作废这笔草稿？"
          description="作废记录会保留在台账中，不会改变持仓。"
          onConfirm={cancelDraft}
        >
          <Button danger loading={busy}>
            作废草稿
          </Button>
        </Popconfirm>
      </Space>
    </>
  );
}

export function FillPanel({
  revision,
  draft,
  onDone,
}: {
  revision: number;
  draft: PortfolioDraft | null;
  onDone: () => void;
}) {
  const [failure, setFailure] = useState<string>();

  if (draft)
    return <DraftReview draft={draft} revision={revision} onDone={onDone} />;

  const submit = async (form: Record<string, unknown>) => {
    setFailure(undefined);
    const side = text(form.side).toUpperCase();
    const nextSell = form.next_sell_session
      ? dayjs(form.next_sell_session as string).format("YYYY-MM-DD")
      : null;
    try {
      await api.prepareFill({
        idempotency_key: crypto.randomUUID(),
        expected_revision: revision,
        note: text(form.note) || null,
        fill: {
          transaction_id: text(form.transaction_id),
          side,
          sleeve: text(form.sleeve).toUpperCase(),
          symbol: text(form.symbol),
          exchange: text(form.exchange).toUpperCase(),
          quantity: text(form.quantity),
          price_cny: text(form.price_cny),
          fees_cny: text(form.fees_cny) || "0",
          trade_date: dayjs(form.trade_date as string).format("YYYY-MM-DD"),
          next_sell_session: side === "BUY" ? nextSell : null,
          trading_unit: side === "BUY" ? text(form.trading_unit) : null,
          corporate_action: false,
        },
      });
      onDone();
    } catch (cause) {
      setFailure(failureMessage(cause, "生成草稿失败"));
    }
  };

  return (
    <>
      <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
        记录一笔成交（先生成草稿）
      </Typography.Title>
      {failure && (
        <Alert
          type="error"
          showIcon
          message="未能生成草稿"
          description={failure}
        />
      )}
      <ProForm
        layout="vertical"
        onFinish={submit}
        submitter={{ searchConfig: { submitText: "生成草稿" } }}
      >
        <ProFormText
          name="transaction_id"
          label="成交编号"
          placeholder="券商成交单编号，用于防重复"
          rules={[{ required: true, message: "请填写成交编号" }]}
        />
        <ProFormSelect
          name="side"
          label="方向"
          initialValue="BUY"
          options={[
            { value: "BUY", label: "买入 BUY" },
            { value: "SELL", label: "卖出 SELL" },
          ]}
          rules={[{ required: true, message: "请选择方向" }]}
        />
        <ProFormSelect
          name="sleeve"
          label="资金池"
          initialValue="CORE_VALUE"
          options={[
            { value: "CORE_VALUE", label: "价值池 CORE_VALUE" },
            {
              value: "HOTSPOT_SATELLITE",
              label: "情绪卫星仓 HOTSPOT_SATELLITE",
            },
          ]}
          rules={[{ required: true, message: "请选择资金池" }]}
        />
        <ProFormText
          name="symbol"
          label="证券代码"
          rules={[{ pattern: /^\d{6}$/, message: "证券代码为 6 位数字" }]}
        />
        <ProFormSelect
          name="exchange"
          label="交易所"
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
          rules={[
            { required: true, message: "请填写股数" },
            { pattern: SHARES, message: "股数为整数" },
          ]}
        />
        <ProFormText
          name="price_cny"
          label="成交价（元）"
          rules={[
            { required: true, message: "请填写成交价" },
            { pattern: AMOUNT, message: "价格只能是非负数字" },
          ]}
        />
        <ProFormText
          name="fees_cny"
          label="费用合计（元）"
          initialValue="0"
          rules={[{ pattern: AMOUNT, message: "费用只能是非负数字" }]}
        />
        <ProFormDatePicker
          name="trade_date"
          label="成交日期"
          initialValue={dayjs()}
          rules={[{ required: true, message: "请选择成交日期" }]}
        />
        <ProFormDatePicker
          name="next_sell_session"
          label="最早可卖日（买入必填）"
          tooltip="用于 T+1 可卖校验，卖出时无需填写"
        />
        <ProFormText
          name="trading_unit"
          label="交易单位（买入必填）"
          initialValue="100"
          rules={[{ pattern: SHARES, message: "交易单位为整数" }]}
        />
        <ProFormTextArea name="note" label="备注" />
      </ProForm>
    </>
  );
}
