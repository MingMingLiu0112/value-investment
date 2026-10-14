import { Alert } from "antd";
import { useCallback } from "react";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";

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

export function ValuePolicyReview({ symbol }: { symbol: string }) {
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
  const draft = result.data?.draft;
  const basis = draft?.basis as Record<string, unknown> | undefined;
  const draftText = (value: unknown) =>
    typeof value === "string" ? value : "尚未核验";
  return (
    <section aria-label="估值与动作政策复核">
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
              {(["open", "add", "reduce", "exit"] as const).map(
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
