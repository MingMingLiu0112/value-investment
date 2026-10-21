import {
  ProForm,
  ProFormDatePicker,
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
import { useRef, useState } from "react";
import { ApiError, api } from "../services/api";
import type { PortfolioDraft } from "../types/api";
import { formatMoney } from "../utils/format";
import { PositionTable, sleeveLabel } from "./PositionTable";
import { retryableWrite } from "./PrivateRiskContext";

const AMOUNT = /^\d+(\.\d{1,4})?$/;
const SHARES = /^\d+$/;

export function fillBudgetWarning(response: unknown): string | undefined {
  const review = (
    response as { sleeve_cash_review?: { blockers?: string[] } } | null
  )?.sleeve_cash_review;
  if (review?.blockers?.includes("SLEEVE_CASH_OVERDRAWN"))
    return "真实成交已记录，但含费用的资金池预算已超支。暂停新增买入，核对券商成交及两策略预算；不要删除真实成交来掩盖超支。";
  return undefined;
}

export type FillContext = {
  symbol?: string;
  strategy?: "CORE_VALUE" | "HOTSPOT_SATELLITE";
  decision_id?: string;
  research_version?: string;
};

export function fillContextFromSearch(search: string): FillContext {
  const params = new URLSearchParams(search);
  const strategy = params.get("strategy");
  return {
    symbol: /^\d{6}$/.test(params.get("symbol") ?? "")
      ? params.get("symbol")!
      : undefined,
    strategy:
      strategy === "hotspot" || strategy === "HOTSPOT_SATELLITE"
        ? "HOTSPOT_SATELLITE"
        : strategy === "value" || strategy === "CORE_VALUE"
          ? "CORE_VALUE"
          : undefined,
    decision_id: params.get("decision_id") || undefined,
    research_version: params.get("research_version") || undefined,
  };
}

function text(value: unknown): string {
  return String(value ?? "").trim();
}

export function failureMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    const messages: Record<string, string> = {
      "confirmation requires a timezone-aware time after trade":
        "确认时间不能早于实际成交日期。未来日期的成交尚不能确认，请核对成交日期并在实际成交后确认；不要修改日期来绕过校验。",
      "trade date precedes confirmed state":
        "成交日期早于账户核对日期或上一笔已确认成交日期，无法按当前台账录入。请核对实际成交日期；需要补录历史成交时，应先核对账户基线，不要为了通过校验修改实际日期。",
      "insufficient sellable shares":
        "所选资金池中的可卖股数不足。请核对资金池、卖出数量及最早可卖日；买入股票受 T+1 限制时，当日不可卖出。",
      "BUY requires an explicit later sell session":
        "买入需要填写晚于成交日期的最早可卖交易日。请按券商记录核对 T+1 可卖日，周末或休市日不能当作下一交易日。",
      "BUY requires an explicit trading unit dividing quantity":
        "买入股数必须符合所填交易单位。请核对实际股数和该证券的交易单位。",
      "SELL cannot specify next sell session":
        "卖出无需填写最早可卖日，请清除该字段后重试。",
    };
    const translated = messages[String(cause.detail ?? "")];
    if (translated) return translated;
    return `${cause.code}：${String(cause.detail ?? "")}`;
  }
  return cause instanceof Error ? cause.message : fallback;
}

export function fillFailure(
  cause: unknown,
  fallback: string,
): { message: string; refreshRequired: boolean } {
  return {
    message: failureMessage(cause, fallback),
    refreshRequired:
      cause instanceof ApiError &&
      cause.status === 409 &&
      cause.code === "VERSION_CONFLICT",
  };
}

export function clearRejectedAttempt(
  attempt: ReturnType<typeof retryableWrite>,
  cause: unknown,
) {
  // A server rejection did not commit this attempt. A lost response may have.
  if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500)
    attempt.clear();
}

function DraftReview({
  draft,
  revision,
  onDone,
}: {
  draft: PortfolioDraft;
  revision: number;
  onDone: (warning?: string) => void;
}) {
  const [failure, setFailure] = useState<{
    message: string;
    refreshRequired: boolean;
  }>();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const confirmAttempt = useRef(retryableWrite());
  const cancelAttempt = useRef(retryableWrite());
  const fill = draft.fill as Record<string, unknown>;

  const confirmDraft = async () => {
    if (lock.current || !note.trim()) return;
    lock.current = true;
    setBusy(true);
    setFailure(undefined);
    try {
      const response = await api.confirmFill(
        confirmAttempt.current.body(
          JSON.stringify([revision, draft.prepared_record_sha256, note.trim()]),
          () => ({
            idempotency_key: crypto.randomUUID(),
            expected_revision: revision,
            prepared_record_sha256: draft.prepared_record_sha256,
            confirmed_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
            confirmation_note: note.trim(),
          }),
        ),
      );
      confirmAttempt.current.clear();
      onDone(fillBudgetWarning(response));
    } catch (cause) {
      clearRejectedAttempt(confirmAttempt.current, cause);
      setFailure(fillFailure(cause, "确认失败"));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const cancelDraft = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure(undefined);
    try {
      await api.cancelFill(
        cancelAttempt.current.body(
          JSON.stringify([revision, draft.prepared_record_sha256, note]),
          () => ({
            idempotency_key: crypto.randomUUID(),
            expected_revision: revision,
            prepared_record_sha256: draft.prepared_record_sha256,
            cancelled_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
            reason: note || "录入有误，人工作废",
          }),
        ),
      );
      cancelAttempt.current.clear();
      onDone();
    } catch (cause) {
      clearRejectedAttempt(cancelAttempt.current, cause);
      setFailure(fillFailure(cause, "作废失败"));
    } finally {
      lock.current = false;
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
          description={failure.message}
          action={
            failure.refreshRequired ? (
              <Button onClick={() => onDone()}>刷新台账</Button>
            ) : undefined
          }
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
            key: "decision",
            label: "关联判断",
            children: text(fill.decision_id) || "未关联",
          },
          {
            key: "research",
            label: "研究版本",
            children: text(fill.research_version) || "未关联",
          },
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
            aria-label="成交处理说明"
            style={{ width: 320, display: "block" }}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：已核对券商成交单"
          />
        </div>
        <Button
          type="primary"
          loading={busy}
          disabled={!note.trim()}
          onClick={confirmDraft}
        >
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
  initialSymbol,
  initialSleeve,
  initialDecisionId,
  initialResearchVersion,
}: {
  revision: number;
  draft: PortfolioDraft | null;
  onDone: () => void;
  initialSymbol?: string;
  initialSleeve?: "CORE_VALUE" | "HOTSPOT_SATELLITE";
  initialDecisionId?: string;
  initialResearchVersion?: string;
}) {
  const [budgetWarning, setBudgetWarning] = useState<string | null>(null);
  const [failure, setFailure] = useState<{
    message: string;
    refreshRequired: boolean;
  }>();
  const prepareLock = useRef(false);
  const prepareAttempt = useRef(retryableWrite());
  const context = fillContextFromSearch(
    typeof window === "undefined" ? "" : window.location.search,
  );
  const decisionId = initialDecisionId ?? context.decision_id;
  const researchVersion = initialResearchVersion ?? context.research_version;
  const linkedSymbol = initialSymbol ?? context.symbol;
  const linkedSleeve = initialSleeve ?? context.strategy;

  if (draft)
    return (
      <DraftReview
        draft={draft}
        revision={revision}
        onDone={(warning) => {
          setBudgetWarning(warning ?? null);
          onDone();
        }}
      />
    );

  const submit = async (form: Record<string, unknown>) => {
    if (prepareLock.current) return false;
    prepareLock.current = true;
    setFailure(undefined);
    const side = text(form.side).toUpperCase();
    const nextSell = form.next_sell_session
      ? dayjs(form.next_sell_session as string).format("YYYY-MM-DD")
      : null;
    try {
      if (side === "BUY" && (!nextSell || !text(form.trading_unit)))
        throw new Error("买入请填写券商确认的最早可卖日和交易单位。");
      const contextMatches =
        text(form.symbol) === linkedSymbol &&
        text(form.sleeve).toUpperCase() === linkedSleeve;
      const payload = {
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
          fees_cny: text(form.fees_cny),
          decision_id: contextMatches ? (decisionId ?? null) : null,
          research_version: contextMatches ? (researchVersion ?? null) : null,
          trade_date: dayjs(form.trade_date as string).format("YYYY-MM-DD"),
          next_sell_session: side === "BUY" ? nextSell : null,
          trading_unit: side === "BUY" ? text(form.trading_unit) : null,
          corporate_action: false,
        },
      };
      await api.prepareFill(
        prepareAttempt.current.body(JSON.stringify(payload), () => ({
          ...payload,
          idempotency_key: crypto.randomUUID(),
        })),
      );
      prepareAttempt.current.clear();
      onDone();
      return true;
    } catch (cause) {
      clearRejectedAttempt(prepareAttempt.current, cause);
      setFailure(fillFailure(cause, "生成草稿失败"));
      return false;
    } finally {
      prepareLock.current = false;
    }
  };

  return (
    <>
      {budgetWarning && (
        <Alert
          type="warning"
          showIcon
          message="成交后预算异常"
          description={budgetWarning}
        />
      )}
      <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
        记录一笔成交（先生成草稿）
      </Typography.Title>
      {failure && (
        <Alert
          type="error"
          showIcon
          message="未能生成草稿"
          description={failure.message}
          action={
            failure.refreshRequired ? (
              <Button onClick={onDone}>刷新台账</Button>
            ) : undefined
          }
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
          options={[
            { value: "BUY", label: "买入 BUY" },
            { value: "SELL", label: "卖出 SELL" },
          ]}
          rules={[{ required: true, message: "请选择方向" }]}
        />
        <ProFormSelect
          name="sleeve"
          label="资金池"
          initialValue={linkedSleeve}
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
          initialValue={initialSymbol ?? context.symbol}
          rules={[
            { required: true, message: "请填写证券代码" },
            { pattern: /^\d{6}$/, message: "证券代码为 6 位数字" },
          ]}
        />
        <ProFormSelect
          name="exchange"
          label="交易所"
          options={[
            { value: "SSE", label: "上交所 SSE" },
            { value: "SZSE", label: "深交所 SZSE" },
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
          rules={[
            { required: true, message: "请填写实际费用，无费用请填 0" },
            { pattern: AMOUNT, message: "费用只能是非负数字" },
          ]}
        />
        <ProFormDatePicker
          name="trade_date"
          label="成交日期"
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
          rules={[{ pattern: SHARES, message: "交易单位为整数" }]}
        />
        <ProFormTextArea name="note" label="备注" />
      </ProForm>
    </>
  );
}
