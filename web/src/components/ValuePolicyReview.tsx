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
  return (
    <section aria-label="估值与动作政策复核">
      <h3>估值与动作政策复核</h3>
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
            description="伊利当前模型对超额盈利优势的持续期假设较短。估值与市场价格存在显著分歧，不能直接把研究情景当作买价，也不能通过调整参数制造买点。价格政策须明确选定条件并由有权用户确认。"
          />
          {result.data.model_review.findings?.map((finding, index) => (
            <p key={index}>{finding.text}</p>
          ))}
          <h4>分红事实与覆盖风险</h4>
          <p>
            {result.data.model_review.dividend_review?.latest_retained_fact ??
              "尚未核验"}
          </p>
          <p>{result.data.model_review.dividend_review?.explanation}</p>
          <p>{result.data.model_review.dividend_review?.risks?.join("；")}</p>
          <details>
            <summary>模型口径与完整原始复核</summary>
            <DetailSection title="复核原件" value={result.data.model_review} />
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
    </section>
  );
}
