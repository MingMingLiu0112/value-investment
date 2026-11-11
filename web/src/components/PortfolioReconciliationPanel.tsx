import {
  Alert,
  Button,
  Checkbox,
  Input,
  Radio,
  Select,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useEffect, useRef, useState } from "react";
import type { PortfolioResponse, WriteResponse } from "../types/api";
import { PositionTable } from "./PositionTable";
import { retryableWrite } from "./PrivateRiskContext";
import { reconciliationConfirmation } from "./reconciliationConfirmation";
import type { ReconciliationMode } from "./reconciliationConfirmation";

export function PortfolioReconciliationPanel({
  portfolio,
  onConfirm,
  onDone,
}: {
  portfolio: PortfolioResponse;
  onConfirm: (body: Record<string, unknown>) => Promise<WriteResponse>;
  onDone: () => void;
}) {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<ReconciliationMode>("INTERNAL");
  const [evidenceId, setEvidenceId] = useState("");
  const [evidenceKind, setEvidenceKind] = useState<string>();
  const lock = useRef(false);
  const attempt = useRef(retryableWrite());
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setChecks({});
    setNote("");
    setFailure(undefined);
    setNotice(undefined);
    setMode("INTERNAL");
    setEvidenceId("");
    setEvidenceKind(undefined);
    attempt.current.clear();
  }, [portfolio.revision]);
  const external = mode === "EXTERNAL";
  const rows = [
    [
      "cash_checked",
      `现金 ${portfolio.cash_cny ?? "未知"} 元与${external ? "本人提供的外部对账单" : "记录"}一致`,
    ],
    [
      "positions_checked",
      `已逐项核对下方持仓数量及总成本${external ? "，与本人提供的外部对账单一致" : ""}`,
    ],
    [
      "fills_checked",
      `已核对 ${portfolio.trades.length} 笔已确认成交，无遗漏或重复${external ? "，与本人提供的外部对账单一致" : ""}`,
    ],
  ];
  const ready =
    !portfolio.pending_draft &&
    portfolio.cash_cny != null &&
    (!external || (!!evidenceId.trim() && !!evidenceKind)) &&
    rows.every(([key]) => checks[key]) &&
    !!note.trim();
  const confirm = async () => {
    if (!ready || lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure(undefined);
    const current = generation.current;
    const confirmation = reconciliationConfirmation({
      mode,
      evidenceId,
      evidenceKind,
      note,
      checks,
    });
    const identity = JSON.stringify([portfolio.revision, confirmation]);
    const body = attempt.current.body(identity, () => ({
      idempotency_key: crypto.randomUUID(),
      expected_revision: portfolio.revision,
      reconciled_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
      ...confirmation,
    }));
    try {
      const response = await onConfirm(body);
      if (response.action !== "no_order" || response.status !== "RECONCILED")
        throw new Error("对账确认状态无法核验，请刷新后检查。");
      if (
        response.reconciliation_scope !==
        (external ? "EXTERNAL_ACCOUNT_STATEMENT" : "INTERNAL_JOURNAL_REPLAY")
      )
        throw new Error("返回的对账范围与本人选择不一致，请刷新检查。");
      if (current === generation.current) {
        attempt.current.clear();
        setChecks({});
        setNote("");
        setNotice(
          external
            ? "外部对账引用及本人核对结果已记录；系统未自动连接券商。"
            : "内部流水对账已确认；尚未核验外部券商对账单。",
        );
        onDone();
      }
    } catch (cause) {
      if (current === generation.current)
        setFailure(
          cause instanceof Error
            ? cause.message
            : "对账未完成，请重试或刷新账本",
        );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return (
    <section aria-label="本人对账确认">
      <Typography.Title level={4}>本人对账确认</Typography.Title>
      <Alert
        type="info"
        showIcon
        message="核对已记录的现金、持仓和成交"
        description={
          external
            ? "这是本人提供的对账引用及逐项核对结果，系统没有自动连接券商，也未自动验证凭证原件。"
            : "本次确认范围为系统内部流水重算。外部账户余额和券商对账单尚未核验，相关风险限制仍保留。"
        }
      />
      <Radio.Group
        aria-label="对账范围"
        value={mode}
        disabled={busy}
        onChange={(event) => {
          setMode(event.target.value);
          setChecks({});
          setNotice(undefined);
          setFailure(undefined);
        }}
        options={[
          { value: "INTERNAL", label: "内部流水核对" },
          { value: "EXTERNAL", label: "本人提供外部对账引用" },
        ]}
      />
      {external && (
        <div>
          <Select
            aria-label="对账凭证类型"
            placeholder="选择本人持有的凭证类型"
            value={evidenceKind}
            disabled={busy}
            style={{ width: "100%", maxWidth: 320 }}
            onChange={(value) => {
              setEvidenceKind(value);
              setChecks({});
            }}
            options={[
              { value: "broker_statement", label: "券商对账单" },
              { value: "account_statement", label: "账户对账单" },
              { value: "custodian_statement", label: "托管机构对账单" },
            ]}
          />
          <Input
            aria-label="真实对账单引用编号"
            placeholder="真实对账单编号或可回查引用"
            value={evidenceId}
            disabled={busy}
            onChange={(event) => {
              setEvidenceId(event.target.value);
              setChecks({});
            }}
          />
        </div>
      )}
      <PositionTable title="本次待核对持仓" positions={portfolio.positions} />
      {portfolio.pending_draft && (
        <Alert type="warning" message="请先确认或作废成交草稿" />
      )}
      {!portfolio.trades.length && (
        <Alert type="info" message="尚无成交，本次核对已确认的初始现金与持仓" />
      )}
      {rows.map(([key, label]) => (
        <div key={key}>
          <Checkbox
            disabled={busy}
            checked={!!checks[key]}
            onChange={(event) =>
              setChecks((previous) => ({
                ...previous,
                [key]: event.target.checked,
              }))
            }
          >
            {label}
          </Checkbox>
        </div>
      ))}
      <Input.TextArea
        aria-label="本人对账说明"
        value={note}
        disabled={busy}
        placeholder="填写本次核对范围及结果"
        onChange={(event) => setNote(event.target.value)}
      />
      <Button
        type="primary"
        loading={busy}
        disabled={!ready || busy}
        onClick={confirm}
      >
        {external ? "本人确认外部引用及对账结果" : "本人确认内部对账"}
      </Button>
      {failure && <Alert type="error" message={failure} />}
      {notice && <Alert type="success" message={notice} />}
    </section>
  );
}

export const ReconciliationPanel = PortfolioReconciliationPanel;
