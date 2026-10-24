import { Alert } from "antd";
import { useCallback, useState } from "react";
import { PrivateValueDecision } from "./PrivateValueDecision";
import { api } from "../services/api";
import type { PolicyHandoff } from "../services/valuePolicy";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";
import { ValuePolicyEditor } from "./ValuePolicyEditor";
import type {
  PolicyRegistration,
  PolicySelection,
  ValuePolicyTransport,
} from "../services/valuePolicy";

type Review = {
  action: "no_order";
  model_review: Record<string, unknown> & {
    findings?: { text: string }[];
    dividend_review?: {
      latest_retained_fact?: string;
      explanation?: string;
      risks?: string[];
    };
  };
  draft: Record<string, unknown>;
  preparation: {
    status: string;
    blockers?: string[];
    draft_prices?: Record<string, unknown>;
  };
};

export function MaterialityHandoff({
  material,
}: {
  material: PolicyHandoff["materiality_handoff"];
}) {
  if (!material || material.status === "NO_MATERIALITY_ANNOUNCEMENTS")
    return null;
  const imported = material.status === "AUTHENTICATED_RESPONSE_IMPORTED";
  return (
    <section aria-label="新增公告材料性审核">
      <h4>新增公告材料性审核</h4>
      <p>状态：{material.status}</p>
      {material.status === "NO_REGISTERED_INCREMENTAL_SCAN" && (
        <p role="alert">
          尚无绑定当前模型版本的完整公告扫描，暂不可签署材料性审核回应。
        </p>
      )}
      <p>
        {imported
          ? "已核验签署回执；仍须重新计算并发布，其他独立门禁不因此通过。"
          : "需有权审核人逐项判断公告影响；本机登录、私人价格政策和 G3 均不能代替这项签署。"}
      </p>
      {material.scan_window && (
        <p>
          扫描期间：{material.scan_window.scan_from} 至{" "}
          {material.scan_window.scan_to}；公告{" "}
          {material.announcements?.length ?? "未核验"} 份。
        </p>
      )}
      {material.reason && <p role="alert">材料暂不可交接：{material.reason}</p>}
      {material.recompute_status === "BLOCKED" && (
        <p role="alert">
          重算暂不可办理：
          {material.recompute_reason ?? "原始研究范围尚未通过核验。"}
        </p>
      )}
      {material.status === "MATERIALITY_HANDOFF_BLOCKED" &&
        material.commands?.prepare_handoff && (
          <details>
            <summary>准备原始签署材料</summary>
            <p>保存对应版本的签署材料后重新读取；此步骤不授予任何审核资格。</p>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {material.commands.prepare_handoff}
            </pre>
          </details>
        )}
      {material.commands &&
        (material.status === "EXTERNAL_SIGNATURE_REQUIRED" || imported) && (
          <details>
            <summary>公告原件、签署回应与办理后验证</summary>
            <DetailSection title="公告证据" value={material.announcements} />
            <DetailSection
              title="待本人签署回应"
              value={material.unsigned_response}
            />
            <p>
              由已登记且有相应权限的审核人签署；不向网页上传私钥。导入后重算，核对新发布版本及剩余限制，再刷新页面。
            </p>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {material.commands.consume_signed_response}
              {"\n"}
              {material.commands.recompute}
            </pre>
          </details>
        )}
    </section>
  );
}

export function HandoffNotReady({
  material,
}: {
  material: Extract<PolicyHandoff, { status: "NOT_READY" }>;
}) {
  return (
    <section aria-label="审核交接尚未就绪">
      <p>审核交接尚未就绪；当前没有可签署的候选回应，研究批准未改变。</p>
      <ul>
        {material.blockers.map((blocker, index) => (
          <li key={index}>{blocker}</li>
        ))}
      </ul>
      {material.bindings && (
        <DetailSection title="当前草案精确版本绑定" value={material.bindings} />
      )}
      <MaterialityHandoff
        material={
          material.materiality_handoff
            ? {
                ...material.materiality_handoff,
                commands: undefined,
                unsigned_response: undefined,
              }
            : undefined
        }
      />
    </section>
  );
}

function ExternalReviewHandoff({
  symbol,
  boundDraft = false,
  transport,
}: {
  symbol: string;
  boundDraft?: boolean;
  transport?: ValuePolicyTransport;
}) {
  const [material, setMaterial] = useState<PolicyHandoff>();
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setMaterial(undefined);
    setFailure("");
    setBusy(true);
    try {
      const result = boundDraft
        ? await (() => {
            if (!transport?.handoff)
              throw new Error("Bound draft handoff transport unavailable");
            return transport.handoff(symbol, true);
          })()
        : await api.valuePolicyHandoff(symbol);
      if (
        result.action !== "no_order" ||
        !["EXTERNAL_SIGNATURE_REQUIRED", "NOT_READY"].includes(result.status) ||
        result.verification.approval_changed !== false ||
        result.verification.research_admitted !== false
      )
        throw new Error("交接材料未通过只读边界校验");
      setMaterial(result);
    } catch {
      setFailure("交接材料暂不可读取，请核对授权后重试。");
    } finally {
      setBusy(false);
    }
  }
  function download() {
    if (!material) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(material, null, 2)], {
        type: "application/json;charset=utf-8",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `value-policy-review-${symbol}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  return (
    <section aria-label="外部估值审核交接" id="value-review-handoff">
      <h4>外部估值审核交接</h4>
      <button type="button" disabled={busy} onClick={load}>
        {busy ? "正在读取…" : "读取本人授权的审核交接材料"}
      </button>
      {failure && <p role="alert">{failure}</p>}
      {material?.status === "NOT_READY" && (
        <HandoffNotReady material={material} />
      )}
      {material?.supplemental_materiality_handoff && (
        <IndependentEventSupplement
          material={material.supplemental_materiality_handoff}
        />
      )}
      {material?.status === "EXTERNAL_SIGNATURE_REQUIRED" && (
        <>
          <p>
            需要外部签署；读取与下载均不改变研究批准。已固定授权根：
            {material.authorization.pinned_root_count}；授权状态：
            {material.authorization.status}。
          </p>
          {material.authorization.pinned_root_count === 0 && (
            <p role="alert">
              尚未登记外部审核签署身份。须先独立审核并登记本人控制密钥的公钥信任根及权限范围；本机登录和价格政策登记均不授予
              G3 审核身份。当前只能读取、下载并准备材料，不能完成有效签署。
            </p>
          )}
          <ol>
            {material.steps.map((step) => (
              <li key={step.id}>{step.action}</li>
            ))}
          </ol>
          <button type="button" onClick={download}>
            下载审核材料 JSON
          </button>
          <MaterialityHandoff material={material.materiality_handoff} />
          <DetailSection title="候选绑定" value={material.candidate_binding} />
          <DetailSection
            title="模型与审核问题"
            value={{
              model_context: material.model_context,
              review_questions: material.review_questions,
              valuation_artifact_sha256: material.valuation_artifact_sha256,
            }}
          />
          <details>
            <summary>未签署响应及外部交接命令</summary>
            <DetailSection
              title="未签署响应"
              value={material.unsigned_response}
            />
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {material.commands.draft_preview}
              {"\n"}
              {material.commands.consume_signed_response}
            </pre>
          </details>
        </>
      )}
    </section>
  );
}

export function IndependentEventSupplement({
  material,
}: {
  material: PolicyHandoff["supplemental_materiality_handoff"];
}) {
  if (!material) return null;
  return (
    <details>
      <summary>独立新版本公告审核材料</summary>
      <p>
        本材料属于单独消费的公告研究版本，不替换上方估值候选，不授予
        G3、当前估值或操作资格。
      </p>
      <MaterialityHandoff material={material} />
    </details>
  );
}

export function ValuePolicyReview({
  symbol,
  boundDraft = false,
  transport,
  onRegistered,
}: {
  symbol: string;
  boundDraft?: boolean;
  transport?: ValuePolicyTransport;
  onRegistered?: (result: PolicyRegistration) => void;
}) {
  const load = useCallback(
    async (signal: AbortSignal): Promise<Review> => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}`,
        { signal },
      );
      const body = await response.json();
      if (!response.ok || body.action !== "no_order")
        throw new Error("研究复核依据未通过当前绑定校验");
      return body;
    },
    [symbol],
  );
  const result = useApi(load);
  const [revision, setRevision] = useState(0);
  const draft = result.data?.draft;
  const basis = draft?.basis as Record<string, unknown> | undefined;
  const draftText = (value: unknown) =>
    typeof value === "string" ? value : "尚未核验";
  return (
    <section aria-label="估值与动作政策复核">
      {transport && (
        <PrivateValueDecision
          key={symbol}
          symbol={symbol}
          transport={transport}
          revision={revision}
        />
      )}
      <ExternalReviewHandoff
        key={`handoff-${symbol}-${boundDraft}`}
        symbol={symbol}
        boundDraft={boundDraft}
        transport={transport}
      />
      <details>
        <summary>查看待确认价格政策</summary>
        {result.loading ? (
          <p>正在核验研究依据…</p>
        ) : result.error || !result.data ? (
          <Alert
            type="info"
            message="此公司尚无可读取的政策复核，不能据此生成操作价"
          />
        ) : (
          <>
            <Alert
              type="warning"
              showIcon
              message="研究复核与政策草案未构成正式操作许可"
              description="价格政策须明确选定条件并由有权用户确认。研究情景不替代操作价，政策确认不替代正式资格与个人风险核验。"
            />
            <p>
              准备状态：
              {result.data.preparation.status === "BLOCKED"
                ? "尚未满足准备条件"
                : result.data.preparation.status}
              。未选择动作比例时，草案操作价保持未知。
            </p>
            <dl style={{ overflowWrap: "anywhere" }}>
              <dt>草案理由</dt>
              <dd>{draftText(draft?.rationale)}</dd>
              <dt>模型版本</dt>
              <dd>{draftText(basis?.model_version)}</dd>
              <dt>拟议有效期（确认后适用）</dt>
              <dd>
                {draftText(draft?.effective_from)} 至{" "}
                {draftText(draft?.effective_through)}
              </dd>
              <dt>分红覆盖风险</dt>
              <dd>{draftText(draft?.dividend_coverage_risk)}</dd>
              {(["entry", "add", "reduce", "exit"] as const).map(
                (action, index) => (
                  <div key={action}>
                    <dt>{["建仓", "加仓", "减仓", "退出"][index]}草案价</dt>
                    <dd>
                      {result.data?.preparation.draft_prices?.[action] == null
                        ? "未形成（待明确动作规则与比例）"
                        : `${String(result.data.preparation.draft_prices[action])}（未批准）`}
                    </dd>
                  </div>
                ),
              )}
            </dl>
            {transport && (
              <ValuePolicyEditor
                key={symbol}
                symbol={symbol}
                transport={transport}
                initial={draft as Partial<PolicySelection>}
                showRegisteredSummary={false}
                onRegistered={(registration) => {
                  setRevision((value) => value + 1);
                  onRegistered?.(registration);
                }}
              />
            )}
            <details>
              <summary>查看估值理由与分红覆盖风险</summary>
              {result.data.model_review.findings?.map((finding, index) => (
                <p key={index}>{finding.text}</p>
              ))}
              <h4>分红事实与覆盖风险</h4>
              <p>
                {result.data.model_review.dividend_review
                  ?.latest_retained_fact ?? "尚未核验"}
              </p>
              <p>{result.data.model_review.dividend_review?.explanation}</p>
              <p>
                {result.data.model_review.dividend_review?.risks?.join("；")}
              </p>
            </details>
            <details>
              <summary>模型口径与完整原始复核</summary>
              <DetailSection
                title="复核原件"
                value={result.data.model_review}
              />
            </details>
            <details>
              <summary>查看价格政策草案及尚未满足的条件</summary>
              <DetailSection
                title="政策草案（未登记）"
                value={result.data.draft}
              />
              <DetailSection
                title="准备结果（未批准）"
                value={result.data.preparation}
              />
            </details>
          </>
        )}
      </details>
    </section>
  );
}
