import { useEffect, useRef, useState } from "react";
import type {
  PolicyPreview,
  PolicyRegistration,
  PolicyRule,
  PolicySelection,
  ValuePolicyTransport,
} from "../services/valuePolicy";
import { fractionFromPercent } from "../services/valuePolicy";
import { formatUnitPrice } from "../utils/format";

const actions = ["entry", "add", "reduce", "exit"] as const;
const labels = { entry: "建仓", add: "加仓", reduce: "减仓", exit: "退出" };
type RuleInput = {
  enabled: boolean;
  scenario: string;
  percent: string;
  rationale: string;
};

export function RegisteredPolicySummary({
  registered,
}: {
  registered: PolicyRegistration;
}) {
  const selection = registered.registered_policy;
  const draft = selection?.draft;
  const blockers = [
    ...(Array.isArray(registered.conditional_plan.blockers)
      ? registered.conditional_plan.blockers
      : []),
    ...(Array.isArray(registered.conditional_plan.formal_eligibility_blockers)
      ? registered.conditional_plan.formal_eligibility_blockers
      : []),
  ].map(String);
  return (
    <section aria-label="私人条件性计划">
      <p role="status">
        本人政策已登记。条件性计划已重新生成，正式投资资格未因此通过。
      </p>
      {registered.scope === "ISOLATED_TEST" && (
        <p>隔离测试登记，不构成真实政策批准。</p>
      )}
      {draft && (
        <>
          <p>
            本人政策有效期：{draft.effective_from} 至 {draft.effective_through}
          </p>
          <p>政策理由：{draft.rationale}</p>
          <p>分红覆盖风险：{draft.dividend_coverage_risk}</p>
        </>
      )}
      {actions.map((action) => {
        const rule = draft?.rules.find((r) => r.action === action);
        const admittedPrice =
          registered.conditional_plan[`${action}_trigger_price`];
        return (
          <div key={action} style={{ marginBottom: 16 }}>
            <strong>{labels[action]}复核条件</strong>
            {rule ? (
              <>
                <p>
                  私人已登记草稿价：
                  {formatUnitPrice(selection.draft_prices[action])}{" "}
                  元（草稿算术价，未获正式动作资格）
                </p>
                <p>
                  {{ bear: "悲观", base: "基准", bull: "乐观" }[rule.scenario]}
                  情景价值 × {rule.value_fraction}（
                  {(Number(rule.value_fraction) * 100).toLocaleString("zh-CN", {
                    maximumFractionDigits: 8,
                  })}
                  %）；价格{rule.comparison === "LTE" ? "不高于" : "不低于"}
                  此价时复核。
                </p>
                <p>基本面与失效条件：{rule.rationale}</p>
              </>
            ) : (
              <p>本人未选择此动作规则。</p>
            )}
            <p>
              派生计划条件价：
              {admittedPrice == null
                ? "研究或价格条件不足，尚无适用价"
                : `${formatUnitPrice(String(admittedPrice))} 元（条件性复核）`}
            </p>
          </div>
        );
      })}
      <p>当前正式资格：未通过。个人风险资格：尚未核验。</p>
      {blockers.some((b) => /G3|human_research_approval/i.test(b)) && (
        <p>资格原因：G3 人工估值审核尚未通过；本人价格政策登记不替代该审核。</p>
      )}
      <p>
        研究、重大事件、模型有效性、行情及个人风险仍需分别核验。草稿算术价可供本人查看，不能作为正式买卖许可。
      </p>
      <details>
        <summary>查看计划资格与待办</summary>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {JSON.stringify(registered.conditional_plan, null, 2)}
        </pre>
      </details>
    </section>
  );
}

export function ValuePolicyEditor({
  symbol,
  transport,
  initial,
  onRegistered,
}: {
  symbol: string;
  transport: ValuePolicyTransport;
  initial: Partial<PolicySelection>;
  onRegistered?: (result: PolicyRegistration) => void;
}) {
  const [fields, setFields] = useState({
    effective_from: initial.effective_from ?? "",
    effective_through: initial.effective_through ?? "",
    rationale: initial.rationale ?? "",
    dividend_coverage_risk: initial.dividend_coverage_risk ?? "",
  });
  const [rules, setRules] = useState<Record<string, RuleInput>>(() =>
    Object.fromEntries(
      actions.map((action) => [
        action,
        {
          enabled: false,
          scenario: "",
          percent: "",
          rationale: "",
        },
      ]),
    ),
  );
  const [preview, setPreview] = useState<PolicyPreview>();
  const [registered, setRegistered] = useState<PolicyRegistration>();
  const [acknowledged, setAcknowledged] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [expired, setExpired] = useState(false);
  const generation = useRef(0);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusRevision, setStatusRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoadingStatus(true);
    transport
      .status(symbol)
      .then((result) => {
        if (!active) return;
        if (result.status === "REGISTERED") setRegistered(result);
        else if (result.status === "REVIEW_REQUIRED")
          setFailure(result.detail ?? "已登记政策需重新复核");
      })
      .catch((error) => {
        if (active)
          setFailure(
            error instanceof Error ? error.message : "读取私人政策失败",
          );
      })
      .finally(() => {
        if (active) setLoadingStatus(false);
      });
    return () => {
      active = false;
    };
  }, [symbol, transport, statusRevision]);
  useEffect(() => {
    if (!preview) return;
    const remaining = Date.parse(preview.expires_at) - Date.now();
    setExpired(remaining <= 0);
    if (remaining <= 0) return;
    const timer = setTimeout(() => setExpired(true), remaining);
    return () => clearTimeout(timer);
  }, [preview]);
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );
  function invalidate() {
    generation.current += 1;
    setPreview(undefined);
    setRegistered(undefined);
    setAcknowledged(false);
    setNote("");
    setFailure("");
    setExpired(false);
  }
  function changeRule(action: string, patch: Partial<RuleInput>) {
    invalidate();
    setRules((current) => ({
      ...current,
      [action]: { ...current[action], ...patch },
    }));
  }
  async function prepare() {
    invalidate();
    const requestGeneration = generation.current;
    setBusy(true);
    try {
      const selected: PolicyRule[] = actions
        .filter((a) => rules[a].enabled)
        .map((action) => {
          const row = rules[action];
          if (!row.scenario || !row.rationale.trim())
            throw new Error("请填写选中动作的情景和复核条件");
          return {
            action,
            scenario: row.scenario as PolicyRule["scenario"],
            value_fraction: fractionFromPercent(row.percent),
            comparison: action === "entry" || action === "add" ? "LTE" : "GTE",
            rationale: row.rationale,
          };
        });
      const result = await transport.preview(symbol, {
        ...fields,
        rules: selected,
      });
      if (requestGeneration === generation.current) setPreview(result);
    } catch (error) {
      if (requestGeneration === generation.current)
        setFailure(error instanceof Error ? error.message : "预览失败，请重试");
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!preview || expired || !acknowledged || !note.trim()) return;
    setBusy(true);
    setFailure("");
    try {
      const result = await transport.confirm(symbol, {
        preview_id: preview.preview_id,
        acknowledged: true,
        note,
      });
      if (
        result.status !== "REGISTERED" ||
        result.research_approval_changed !== false ||
        result.production_published !== false
      )
        throw new Error("登记结果未通过边界校验，请重试核验");
      setRegistered(result);
      setAcknowledged(false);
      onRegistered?.(result);
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "登记未完成，可重试同一确认",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="本人价格政策选择" style={{ overflowWrap: "anywhere" }}>
      <h4>选择价格复核条件</h4>
      {loadingStatus && <p role="status">正在读取本人已登记政策…</p>}
      <fieldset disabled={busy || loadingStatus} style={{ minWidth: 0 }}>
        {(
          [
            ["effective_from", "生效日期", "date"],
            ["effective_through", "失效日期", "date"],
            ["rationale", "政策选择理由", "text"],
            ["dividend_coverage_risk", "分红覆盖风险", "text"],
          ] as const
        ).map(([key, label, type]) => (
          <label key={key} style={{ display: "block", marginBottom: 12 }}>
            {label}
            <input
              type={type}
              required
              value={fields[key]}
              style={{
                display: "block",
                width: "100%",
                boxSizing: "border-box",
              }}
              onChange={(event) => {
                invalidate();
                setFields({ ...fields, [key]: event.target.value });
              }}
            />
          </label>
        ))}
        {actions.map((action) => (
          <fieldset key={action} style={{ minWidth: 0, marginBottom: 12 }}>
            <legend>
              <label>
                <input
                  type="checkbox"
                  checked={rules[action].enabled}
                  onChange={(event) =>
                    changeRule(action, { enabled: event.target.checked })
                  }
                />
                {labels[action]}复核
              </label>
            </legend>
            {rules[action].enabled && (
              <>
                <label>
                  估值情景{" "}
                  <select
                    value={rules[action].scenario}
                    onChange={(event) =>
                      changeRule(action, { scenario: event.target.value })
                    }
                  >
                    <option value="">请选择</option>
                    <option value="bear">悲观</option>
                    <option value="base">基准</option>
                    <option value="bull">乐观</option>
                  </select>
                </label>
                <label style={{ display: "block", marginTop: 8 }}>
                  情景价值比例（%）{" "}
                  <input
                    inputMode="decimal"
                    value={rules[action].percent}
                    style={{ maxWidth: "100%", boxSizing: "border-box" }}
                    onChange={(event) =>
                      changeRule(action, { percent: event.target.value })
                    }
                  />
                </label>
                <p>
                  价格
                  {action === "entry" || action === "add" ? "不高于" : "不低于"}
                  所选情景价值 × 比例时复核。
                </p>
                <label>
                  基本面与失效复核条件
                  <textarea
                    value={rules[action].rationale}
                    rows={3}
                    style={{
                      display: "block",
                      width: "100%",
                      boxSizing: "border-box",
                    }}
                    onChange={(event) =>
                      changeRule(action, { rationale: event.target.value })
                    }
                  />
                </label>
              </>
            )}
          </fieldset>
        ))}
        <button type="button" onClick={prepare}>
          预览本人政策草稿
        </button>
      </fieldset>
      {failure && (
        <>
          <p role="alert">{failure}</p>
          <button
            type="button"
            disabled={busy || loadingStatus}
            onClick={() => setStatusRevision((r) => r + 1)}
          >
            重试读取本人政策
          </button>
        </>
      )}
      {preview && (
        <section aria-label="本人政策二次确认">
          <h4>登记前复核</h4>
          <p>
            {preview.scope === "ISOLATED_TEST"
              ? "隔离测试政策，不写入真实研究链"
              : "本人私人政策，不写入公共研究链"}
          </p>
          <dl>
            {actions.map((action) => (
              <div key={action}>
                <dt>{labels[action]}草稿价</dt>
                <dd>
                  {preview.preparation.draft_prices[action] == null
                    ? "未选择"
                    : `${formatUnitPrice(preview.preparation.draft_prices[action])} 元（未获正式动作资格）`}
                </dd>
              </div>
            ))}
          </dl>
          <p>预览有效至：{preview.expires_at}</p>
          <p>
            政策准备：
            {preview.preparation.blockers.length
              ? "尚有缺项，不能登记"
              : "可由本人确认登记"}
          </p>
          <p>G3、事件与研究资格独立保留；政策登记不授予个人仓位资格。</p>
          {preview.preparation.existing_research_blockers.length > 0 && (
            <details>
              <summary>研究资格待办</summary>
              <ul>
                {preview.preparation.existing_research_blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </details>
          )}
          <fieldset disabled={busy || !!registered} style={{ minWidth: 0 }}>
            <label>
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              我本人已审阅比例、有效期和条件，理解政策确认不替代
              G3、事件及风险核验。
            </label>
            <label style={{ display: "block", marginTop: 8 }}>
              本人确认意见
              <textarea
                rows={2}
                value={note}
                style={{
                  display: "block",
                  width: "100%",
                  boxSizing: "border-box",
                }}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={
                !acknowledged ||
                !note.trim() ||
                expired ||
                preview.status !== "PREPARED_PENDING_USER_CONFIRMATION"
              }
              onClick={confirm}
            >
              本人确认并不可变登记
            </button>
          </fieldset>
          {expired && <p role="alert">预览已过期，请重新预览。</p>}
        </section>
      )}
      {registered && <RegisteredPolicySummary registered={registered} />}
    </section>
  );
}
