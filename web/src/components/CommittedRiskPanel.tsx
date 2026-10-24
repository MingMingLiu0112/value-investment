import { Alert, Button, Checkbox, Input, Modal, Space, Typography } from "antd";
import { useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import {
  committedRiskConfirmation,
  verifyCommittedRiskResponse,
  type RiskAmount,
} from "../services/committedRisk";
import { retryableWrite } from "./PrivateRiskContext";
import { RemoteState } from "./RemoteState";

export function CommittedRiskPanel({
  revision,
  onDone,
}: {
  revision: number;
  onDone: () => void;
}) {
  const result = useApi(api.committedRisk);
  const [amounts, setAmounts] = useState<Record<string, Partial<RiskAmount>>>(
    {},
  );
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [pending, setPending] =
    useState<ReturnType<typeof committedRiskConfirmation>>();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const locked = useRef(false);
  const attempt = useRef(retryableWrite());
  const data = result.data;
  function prepare() {
    if (!data || result.loading || busy) return;
    setFailure(undefined);
    setNotice(undefined);
    try {
      const rows = data.allocations.map((row) => {
        const edited = amounts[`${row.sleeve}:${row.symbol}`];
        return {
          symbol: row.symbol,
          sleeve: row.sleeve,
          committed_risk_cny:
            edited?.committed_risk_cny ?? row.committed_risk_cny ?? "",
          evidence_ref: edited?.evidence_ref ?? row.evidence_ref ?? "",
        };
      });
      setPending(committedRiskConfirmation(data, revision, rows, note, ack));
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "无法确认风险依据。");
    }
  }
  async function confirm() {
    if (
      !pending ||
      !data ||
      !ack ||
      locked.current ||
      data.revision !== revision
    )
      return;
    locked.current = true;
    setBusy(true);
    try {
      const request = attempt.current.body(JSON.stringify(pending), () => ({
        ...pending,
        idempotency_key: crypto.randomUUID(),
      }));
      const response = await api.confirmCommittedRisk(request);
      verifyCommittedRiskResponse(response, pending);
      attempt.current.clear();
      setPending(undefined);
      setAck(false);
      setAmounts({});
      setNotice(
        "本人风险依据已保存；其他研究、行情和账户限制仍独立核验，不授予交易资格。",
      );
      result.retry();
      onDone();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "保存失败，请重试。");
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <section aria-label="本人风险占用确认" style={{ marginTop: 16 }}>
      <Typography.Title level={4}>已有持仓风险占用</Typography.Title>
      <RemoteState
        loading={result.loading}
        error={result.error}
        retry={result.retry}
      >
        {data && (
          <>
            <Alert
              type="info"
              message="本人声明的风险金额与依据"
              description="未知风险请保留空缺。金额不由成本、预算或止损文字推断；确认风险依据不等于研究批准或可买入股数。"
            />
            {data.account_scope?.startsWith("TEST_ONLY") && (
              <Alert
                type="warning"
                message="TEST_ONLY：仅保存隔离演练声明，不属于真实账户批准。"
              />
            )}
            <Typography.Paragraph>
              账户 {data.account_scope ?? "未连接"} · 台账版本 {data.revision} ·{" "}
              {data.confirmation_status === "CONFIRMED"
                ? "已保存本人确认"
                : "请核对当前分池持仓"}
            </Typography.Paragraph>
            {data.allocations.map((row) => {
              const key = `${row.sleeve}:${row.symbol}`;
              const edited = amounts[key];
              const change = (
                field: "committed_risk_cny" | "evidence_ref",
                value: string,
              ) => {
                setAmounts((current) => ({
                  ...current,
                  [key]: { ...current[key], [field]: value },
                }));
                setAck(false);
                setPending(undefined);
              };
              return (
                <div key={key} style={{ margin: "12px 0" }}>
                  <Typography.Paragraph>
                    {row.symbol} ·{" "}
                    {row.sleeve === "CORE_VALUE" ? "价值池" : "热点池"} ·{" "}
                    {row.quantity} 股 · 成本 {row.cost_basis_cny} 元
                  </Typography.Paragraph>
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <label>
                      风险占用金额（元）
                      <Input
                        aria-label={`${key} 风险占用金额`}
                        inputMode="decimal"
                        disabled={busy}
                        value={
                          edited?.committed_risk_cny ??
                          row.committed_risk_cny ??
                          ""
                        }
                        onChange={(event) =>
                          change("committed_risk_cny", event.target.value)
                        }
                      />
                    </label>
                    <label>
                      金额依据与回查引用
                      <Input
                        aria-label={`${key} 风险依据`}
                        disabled={busy}
                        value={edited?.evidence_ref ?? row.evidence_ref ?? ""}
                        onChange={(event) =>
                          change("evidence_ref", event.target.value)
                        }
                      />
                    </label>
                  </Space>
                </div>
              );
            })}
            {!data.allocations.length && (
              <Typography.Paragraph>
                当前没有可确认的分池持仓。
              </Typography.Paragraph>
            )}
            {!!data.allocations.length && (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Input.TextArea
                  aria-label="风险占用确认说明"
                  disabled={busy}
                  value={note}
                  onChange={(event) => {
                    setNote(event.target.value);
                    setAck(false);
                    setPending(undefined);
                  }}
                />
                <Checkbox
                  disabled={busy}
                  checked={ack}
                  onChange={(event) => {
                    setAck(event.target.checked);
                    if (!event.target.checked) setPending(undefined);
                  }}
                >
                  我已核对以上金额与依据，理解其不代表批准买卖
                </Checkbox>
                <Button
                  disabled={
                    !ack || !note.trim() || busy || revision !== data.revision
                  }
                  onClick={prepare}
                >
                  核对风险占用
                </Button>
              </Space>
            )}
          </>
        )}
      </RemoteState>
      {failure && <Alert type="error" message={failure} />}
      {notice && <Alert type="success" message={notice} />}
      <Modal
        title="再次确认本人风险依据"
        open={!!pending}
        onCancel={() => {
          if (!busy) setPending(undefined);
        }}
        onOk={confirm}
        confirmLoading={busy}
        okText="确认保存风险依据"
        cancelText="返回修改"
        closable={!busy}
        maskClosable={!busy}
      >
        <p>
          仅登记当前账户和台账版本的风险占用，不改变现金、持仓或真实成交，不批准交易。
        </p>
        {pending?.amounts.map((row) => (
          <p key={`${row.sleeve}:${row.symbol}`}>
            {row.symbol} · {row.sleeve === "CORE_VALUE" ? "价值池" : "热点池"} ·{" "}
            {row.committed_risk_cny} 元 · {row.evidence_ref}
          </p>
        ))}
        <p>{pending?.confirmation_note}</p>
      </Modal>
    </section>
  );
}
