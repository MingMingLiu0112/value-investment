import { Alert, Button, Checkbox, Input, Select, Space } from "antd";
import { useEffect, useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { thesisConfirmationBody } from "../services/entryThesis";
import { retryableWrite } from "./PrivateRiskContext";
import { RemoteState } from "./RemoteState";

export function EntryThesisPanel({
  revision,
  onDone,
  initialFill,
  onSaved,
}: {
  revision: number;
  onDone: () => void;
  initialFill?: string;
  onSaved?: (fill: string, message: string) => void;
}) {
  const result = useApi(api.entryThesis);
  const [fill, setFill] = useState<string | undefined>(initialFill);
  const [planIndex, setPlanIndex] = useState<number>(-1);
  const [mode, setMode] = useState("HISTORICAL_RECONSTRUCTION");
  const [thesis, setThesis] = useState("");
  const [hold, setHold] = useState("");
  const [breakers, setBreakers] = useState("");
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const lock = useRef(false);
  const attempt = useRef(retryableWrite());
  const data = result.data;
  const item = data?.items.find((row) => row.fill_record_sha256 === fill);
  const plan = planIndex >= 0 ? item?.candidate_plans[planIndex] : undefined;
  useEffect(() => {
    setAck(false);
    setNote("");
    setFailure(undefined);
    attempt.current.clear();
  }, [revision, data?.revision, fill, planIndex, mode]);
  const refresh = () => {
    result.retry();
    onDone();
  };
  async function save(revoke = false) {
    if (lock.current || !data || !item || data.revision !== revision) return;
    lock.current = true;
    setBusy(true);
    setFailure(undefined);
    setNotice(undefined);
    try {
      if (!ack || !note.trim()) throw new Error("请阅读并填写本次确认说明。");
      const body = revoke
        ? {
            expected_revision: data.revision,
            confirmation_record_sha256: item.current_binding?.record_sha256,
            confirmation_note: note.trim(),
            read_and_confirmed: true,
          }
        : thesisConfirmationBody(data, item, {
            note,
            acknowledged: ack,
            plan,
            mode,
            thesis,
            hold,
            breakers,
          });
      if (revoke && !item.current_binding)
        throw new Error("没有可撤销的当前确认。");
      const request = attempt.current.body(
        JSON.stringify([revoke, body]),
        () => ({ ...body, idempotency_key: crypto.randomUUID() }),
      );
      const response = await (revoke
        ? api.revokeEntryThesis(request)
        : api.confirmEntryThesis(request));
      if (
        response.action !== "no_order" ||
        response.status !==
          (revoke
            ? "PERSONAL_ENTRY_THESIS_REVOKED"
            : "PERSONAL_ENTRY_THESIS_CONFIRMED")
      )
        throw new Error("确认结果无法核验，请刷新台账。");
      attempt.current.clear();
      const message = revoke
        ? "已追加撤销记录，原确认历史保留。"
        : "本人确认已保存；不改变持仓，也不授予交易资格。";
      if (onSaved) onSaved(item.fill_record_sha256, message);
      else setNotice(message);
      refresh();
    } catch (cause) {
      setFailure(
        cause instanceof Error ? cause.message : "保存失败，请刷新后核对。",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <section aria-label="原始投资逻辑确认" style={{ marginTop: 24 }}>
      <h3>原始投资逻辑</h3>
      <RemoteState
        loading={result.loading}
        error={result.error}
        retry={result.retry}
      >
        {data && (
          <>
            {data.account_scope?.startsWith("TEST_ONLY") && (
              <Alert
                type="warning"
                message="TEST_ONLY 演练确认，不属于真实账户"
              />
            )}
            {data.revision !== revision && (
              <Alert
                type="warning"
                message="账本版本已变化，请重新读取后确认"
                action={<Button onClick={refresh}>重新读取</Button>}
              />
            )}
            {!data.items.length ? (
              <p>尚无可绑定的已确认买入。初始持仓不会被伪造成历史成交。</p>
            ) : (
              <>
                <Select
                  aria-label="选择已确认买入"
                  placeholder="选择已确认买入"
                  value={fill}
                  style={{ width: "100%" }}
                  onChange={(value) => {
                    setFill(value);
                    setPlanIndex(-1);
                    setMode("HISTORICAL_RECONSTRUCTION");
                  }}
                  options={data.items.map((row) => ({
                    value: row.fill_record_sha256,
                    disabled: Number(row.remaining_quantity) <= 0,
                    label: `${row.symbol} · ${row.sleeve === "CORE_VALUE" ? "价值池" : "热点池"} · ${row.trade_date} · ${row.transaction_id} · 剩余 ${row.remaining_quantity} 股`,
                  }))}
                />
                {item && (
                  <>
                    <p>
                      原成交价 {item.price_cny}{" "}
                      元；本次只确认投资逻辑，不修改成交、现金或股数。
                    </p>
                    {item.current_binding && (
                      <Alert
                        type="info"
                        message={
                          item.current_binding.binding_mode ===
                          "HISTORICAL_RECONSTRUCTION"
                            ? "已确认 · 事后补录，不证明买入时已存在该证据"
                            : "已确认 · 原研究绑定，仍需当前资格与风险复核"
                        }
                        description={item.current_binding.confirmation_note}
                      />
                    )}
                    {item.current_binding?.reconstruction && (
                      <div aria-label="已保存的事后投资逻辑">
                        <p>
                          买入理由：{item.current_binding.reconstruction.thesis}
                        </p>
                        <p>
                          持有逻辑：
                          {item.current_binding.reconstruction.hold_logic}
                        </p>
                        <ul>
                          {item.current_binding.reconstruction.invalidation_conditions.map(
                            (reason, index) => (
                              <li key={index}>{reason}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                    {item.current_binding?.thesis && (
                      <div aria-label="已保存的原研究逻辑">
                        <p>买入理由：{item.current_binding.thesis}</p>
                        <p>持有逻辑：{item.current_binding.hold_logic}</p>
                        <ul>
                          {item.current_binding.invalidation_conditions?.map(
                            (reason, index) => (
                              <li key={index}>{reason}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                    <Select
                      aria-label="选择投资逻辑依据"
                      value={planIndex}
                      style={{ width: "100%" }}
                      onChange={(value) => {
                        setPlanIndex(value);
                        setMode(
                          value < 0
                            ? "HISTORICAL_RECONSTRUCTION"
                            : item.candidate_plans[value].binding_modes[0],
                        );
                      }}
                      options={[
                        {
                          value: -1,
                          label: "现在补录本人投资理由（事后重建）",
                        },
                        ...item.candidate_plans.map((row, index) => ({
                          value: index,
                          label: `已核验研究 ${row.entry_artifact_id}`,
                        })),
                      ]}
                    />
                    {plan ? (
                      <>
                        <p>{plan.thesis}</p>
                        <p>持有逻辑：{plan.hold_logic}</p>
                        <ul>
                          {plan.invalidation_conditions.map((reason, index) => (
                            <li key={index}>{reason}</li>
                          ))}
                        </ul>
                        <Select
                          aria-label="确认口径"
                          value={mode}
                          onChange={setMode}
                          options={plan.binding_modes.map((value) => ({
                            value,
                            label:
                              value === "CONTEMPORANEOUS"
                                ? "买入时已有来源证据"
                                : "现在事后关联研究",
                          }))}
                        />
                      </>
                    ) : (
                      <>
                        <p>
                          事后补录保存的是现在的本人陈述，不能回填历史证据，也不代表研究或策略已获批准。
                        </p>
                        <label>
                          为什么买入
                          <Input.TextArea
                            aria-label="为什么买入"
                            value={thesis}
                            maxLength={8000}
                            onChange={(e) => setThesis(e.target.value)}
                          />
                        </label>
                        <label>
                          为什么继续持有
                          <Input.TextArea
                            aria-label="为什么继续持有"
                            value={hold}
                            maxLength={8000}
                            onChange={(e) => setHold(e.target.value)}
                          />
                        </label>
                        <label>
                          什么事实会使逻辑失效
                          <Input.TextArea
                            aria-label="什么事实会使逻辑失效"
                            value={breakers}
                            maxLength={8000}
                            onChange={(e) => setBreakers(e.target.value)}
                          />
                        </label>
                      </>
                    )}
                    <label>
                      本次确认或更正说明
                      <Input.TextArea
                        aria-label="本次确认或更正说明"
                        value={note}
                        maxLength={8000}
                        onChange={(e) => setNote(e.target.value)}
                      />
                    </label>
                    <Checkbox
                      checked={ack}
                      onChange={(e) => setAck(e.target.checked)}
                    >
                      我已阅读并确认上述理由属于该笔买入；事后补录不冒充历史研究。
                    </Checkbox>
                    <Space wrap style={{ marginTop: 12 }}>
                      <Button
                        type="primary"
                        loading={busy}
                        disabled={
                          !ack || !note.trim() || data.revision !== revision
                        }
                        onClick={() => save()}
                      >
                        保存本人确认
                      </Button>
                      {item.current_binding && (
                        <Button
                          danger
                          disabled={
                            busy ||
                            !ack ||
                            !note.trim() ||
                            data.revision !== revision
                          }
                          onClick={() => save(true)}
                        >
                          撤销当前确认
                        </Button>
                      )}
                    </Space>
                    {!!item.history.length && (
                      <details>
                        <summary>
                          确认与更正历史（{item.history.length}）
                        </summary>
                        <ul>
                          {item.history.map((row) => (
                            <li key={row.record_sha256}>
                              {row.recorded_at} ·{" "}
                              {row.kind === "PERSONAL_ENTRY_THESIS_REVOKED"
                                ? "撤销"
                                : "确认"}{" "}
                              · {row.confirmation_note}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </RemoteState>
      {failure && <Alert type="error" message={failure} />}
      {notice && <Alert type="success" message={notice} />}
    </section>
  );
}
