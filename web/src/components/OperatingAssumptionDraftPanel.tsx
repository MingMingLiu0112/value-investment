import { useCallback } from "react";
import { Alert, Button } from "antd";
import { api, type OperatingAssumptionDraftResponse } from "../services/api";
import { useApi } from "../hooks/useApi";
import { DetailSection } from "./DetailSection";

const SCENARIOS = [
  ["bear", "审慎情景"],
  ["base", "基准情景"],
  ["bull", "积极情景"],
] as const;
const UNKNOWN_LABELS: Record<string, string> = {
  normalized_parent_profit_cny: "正常化归母利润",
  tax_rate_assumption: "税率假设",
  parent_attribution_assumption: "归母归属假设",
  normalized_range: "正常化区间",
};

function UnknownItem({ value }: { value: unknown }) {
  if (typeof value === "string")
    return <>{value === "NOT_ESTABLISHED" ? "尚未证明" : value}</>;
  if (value && typeof value === "object" && "field" in value) {
    const item = value as {
      field: string;
      value?: unknown;
      status?: string;
      reason?: string;
    };
    const label = UNKNOWN_LABELS[item.field];
    const reason =
      typeof item.reason === "string" && item.reason.trim()
        ? item.reason
        : undefined;
    const notEstablished =
      item.value === "NOT_ESTABLISHED" ||
      item.status === "NOT_ESTABLISHED" ||
      (typeof item.status === "string" &&
        item.status.endsWith("_NOT_ESTABLISHED"));
    return (
      <>
        <span>
          {label ? label + "：" : ""}
          {reason || (label ? "" : "待核验事项")}
          {reason ? " · " : ""}
          {notEstablished
            ? "尚未证明"
            : item.value === null || item.value === undefined
              ? "未知（不填0）"
              : String(item.value)}
        </span>
        <details>
          <summary>字段与状态明细</summary>
          <p>
            来源字段：<code>{item.field}</code>
          </p>
          {item.status && (
            <p>
              原始状态：<code>{item.status}</code>
            </p>
          )}
        </details>
      </>
    );
  }
  return <>未知项尚未提供可读说明</>;
}

export function OperatingAssumptionDraftView({
  data,
  symbol,
}: {
  data: OperatingAssumptionDraftResponse;
  symbol: string;
}) {
  if (
    data.symbol !== symbol ||
    data.action !== "no_order" ||
    data.formal_eligibility !== false ||
    data.valuation_computed !== false ||
    Boolean(data.assumptions_approved) ||
    Boolean(data.research_admitted) ||
    Boolean(data.approval_changed) ||
    Boolean(data.e2_new_company_compilation)
  )
    return (
      <Alert
        type="warning"
        message="经营假设草案身份或研究边界不符，停止展示"
      />
    );

  if (data.status !== "SOURCE_BOUND_D2_DRAFT") {
    return (
      <section aria-label="D2经营假设草案">
        <h3>D2 · 经营假设与反证草案</h3>
        <Alert
          type="info"
          showIcon
          message={
            data.status === "MISSING_SOURCE"
              ? "经营假设草案来源缺失"
              : "经营假设草案暂不可评估"
          }
          description="尚无可显示的来源绑定草案。来源补齐并核验后再读取；此处不生成新研究、不估值、不审批。"
        />
        {data.missing_sources?.length ? (
          <details>
            <summary>缺失的绑定来源</summary>
            <ul>
              {data.missing_sources.map((ref, index) => (
                <li key={index}>
                  <code>{ref.path}</code>
                  {ref.sha256 ? " · SHA-256 " + ref.sha256 : ""}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>
    );
  }

  if (
    !Array.isArray(data.branches) ||
    data.branches.length === 0 ||
    !Array.isArray(data.source_bindings) ||
    data.source_bindings.length === 0 ||
    !data.input_fingerprint ||
    data.branches.some(
      (branch) =>
        !branch.branch_id ||
        !branch.title ||
        !branch.economic_rationale ||
        !branch.proposal_rationale ||
        !Array.isArray(branch.counter_evidence) ||
        !branch.counter_evidence.length ||
        SCENARIOS.some(
          ([name]) => !branch.scenarios?.[name]?.evidence_ref?.sha256,
        ),
    )
  )
    return (
      <Alert
        type="warning"
        message="经营假设草案分支或来源绑定不完整，停止展示"
      />
    );

  return (
    <section
      aria-label="D2经营假设草案"
      style={{ marginBlock: 20, overflowWrap: "anywhere" }}
    >
      <h3>D2 · 经营假设与反证草案</h3>
      <p>
        {data.company_name || symbol}（{symbol}） · 研究期间：
        {data.as_of || "未提供"} · 草案资料可用时间：
        {data.available_at || "未提供"}
      </p>
      <p>
        仅只读展示既有来源绑定假设，不调用新LLM，不计算估值、不审批、不改变正式资格。
        这些分支是待复核假设，不是官方预测；D2不代表E2首次编译完成。
      </p>
      {data.branches.map((branch) => (
        <article key={branch.branch_id} aria-label={branch.title}>
          <h4>{branch.title}</h4>
          <p>
            <strong>经济理由（假设）：</strong>
            {branch.economic_rationale}
          </p>
          <p>
            <strong>方案理由（假设）：</strong>
            {branch.proposal_rationale}
          </p>
          <h5>关键反证</h5>
          <ul>
            {branch.counter_evidence.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
          <details>
            <summary>年度驱动、终端条件与权益成本假设</summary>
            {SCENARIOS.map(([name, label]) => {
              const scenario = branch.scenarios[name];
              return (
                <section key={name} aria-label={label}>
                  <h5>{label} · 研究假设</h5>
                  <DetailSection
                    title="年度经营与资本驱动"
                    value={scenario.drivers}
                  />
                  {scenario.operating_capital_path !== undefined &&
                    scenario.operating_capital_path !== null && (
                      <DetailSection
                        title="经营与资本路径（后端重算，非估值）"
                        value={scenario.operating_capital_path}
                      />
                    )}
                  <DetailSection
                    title="终端条件（假设）"
                    value={scenario.terminal_policy}
                  />
                  <p>权益成本假设：{scenario.cost_of_equity}</p>
                  <p>原稿分类：{scenario.classification}</p>
                  <DetailSection
                    title="情景字段来源绑定"
                    value={scenario.evidence_ref}
                  />
                </section>
              );
            })}
          </details>
        </article>
      ))}
      <h4>未知与待补证</h4>
      {data.unknowns?.length ? (
        <ul>
          {data.unknowns.map((item, index) => (
            <li key={index}>
              <UnknownItem value={item} />
            </li>
          ))}
        </ul>
      ) : (
        <p>尚未列出可核验未知项，不推定已解决。</p>
      )}
      <h4>失效与重审条件</h4>
      <ul>
        {data.invalidation_conditions?.map((text, index) => (
          <li key={index}>{text}</li>
        ))}
      </ul>
      <h4>研究限制</h4>
      <ul>
        {data.limitations?.map((text, index) => (
          <li key={index}>{text}</li>
        ))}
      </ul>
      <details>
        <summary>历史观察与会计重放（不等于正常化预测）</summary>
        <DetailSection
          title="历史观察及原始验证范围"
          value={data.historical_observations}
        />
        <DetailSection
          title="历史报表重放"
          value={data.historical_statement_replay}
        />
      </details>
      <details>
        <summary>来源绑定、草案指纹及技术明细</summary>
        <p>
          草案输入指纹：<code>{data.input_fingerprint}</code>
        </p>
        <ul>
          {data.source_bindings.map((ref, index) => (
            <li key={index}>
              <code>{ref.path}</code> · SHA-256 <code>{ref.sha256}</code>
            </li>
          ))}
        </ul>
        <DetailSection title="参数研究依据" value={data.parameter_basis} />
        <DetailSection
          title="原报表事实锚点（沿用原准入边界）"
          value={data.fact_anchors}
        />
        <DetailSection
          title="正常化待解决事项"
          value={data.normalization_open_items}
        />
        <DetailSection
          title="经济复核与保证限制"
          value={{
            review: data.economic_review_items,
            assurance: data.assurance_limits,
          }}
        />
      </details>
    </section>
  );
}

export function OperatingAssumptionDraftPanel({ symbol }: { symbol: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.researchAssumptionDraft(symbol, signal),
    [symbol],
  );
  const result = useApi(load);
  if (result.loading) return <p>正在读取D2来源绑定经营假设草案…</p>;
  if (result.error || !result.data)
    return (
      <Alert
        type="info"
        message="经营假设草案来源暂不可核验"
        description={<Button onClick={result.retry}>重新读取草案</Button>}
      />
    );
  return <OperatingAssumptionDraftView data={result.data} symbol={symbol} />;
}
