import { DetailSection } from "./DetailSection";
import { useCallback } from "react";
import { Alert, Button, Descriptions, Tag } from "antd";
import { api } from "../services/api";
import { useApi } from "../hooks/useApi";

export interface CompanyProfile {
  schema_version: string;
  symbol: string;
  status: string;
  action: "no_order";
  formal_eligibility: false;
  profile?: Record<string, unknown> | null;
  business_model?: string | null;
  business_explanation?: string | null;
  economic_evidence?: unknown;
  route_qualification?: {
    status: string;
    economic_quality_proven?: boolean;
    moat_proven?: boolean;
  };
  route?: {
    status: string;
    selected_model: string;
    required_inputs?: string[];
    blockers?: string[];
  } | null;
  evidence_refs?: {
    id?: string;
    url?: string;
    source_url?: string;
    sha256?: string;
    page?: number;
    excerpt?: string;
  }[];
  blockers?: string[];
  counter_evidence?: string[];
  invalidation_conditions?: string[];
  as_of?: string;
}
const profileNames: Record<string, string> = {
  quality_compounder: "消费品股东权益研究模板（质量未确认）",
  mature_manufacturing: "成熟制造业研究模板",
  cyclical_cash_return: "周期现金回报研究模板",
};
const modelNames: Record<string, string> = {
  residual_income_or_equity_value: "剩余收益／股东权益价值",
  fcff: "企业自由现金流",
  cyclical_normalized: "周期正常化估值",
};
const display = (value: unknown) =>
  typeof value === "string" ? value : "尚未形成可核验结论";
function safeUrl(value?: string) {
  try {
    return value && new URL(value).protocol === "https:" ? value : undefined;
  } catch {
    return undefined;
  }
}
export function CompanyProfileView({
  data,
  symbol,
}: {
  data: CompanyProfile;
  symbol: string;
}) {
  if (
    data.schema_version !== "company-research-profile-v1" ||
    data.symbol !== symbol ||
    data.action !== "no_order" ||
    data.formal_eligibility !== false
  ) {
    return (
      <Alert type="warning" message="企业画像身份或权限合同不一致，停止展示" />
    );
  }
  return (
    <section aria-label="企业画像与模型适用性">
      <h3>企业画像与模型适用性</h3>
      <Tag>
        {data.status === "SOURCE_BOUND_PROFILE"
          ? "来源绑定的条件画像"
          : "画像尚不可评价"}
      </Tag>
      <p>解释模型选择，不代表企业质量已获确认，也不授予估值或交易资格。</p>
      <Descriptions
        column={1}
        bordered
        size="small"
        items={[
          {
            key: "date",
            label: "研究资料日期",
            children: data.as_of || "尚未核验",
          },
          {
            key: "business",
            label: "企业如何赚钱",
            children: display(data.business_model),
          },
          {
            key: "profile",
            label: "适用企业类型",
            children:
              profileNames[display(data.profile?.profile_id)] ||
              display(data.profile?.profile_id),
          },
          {
            key: "model",
            label: "适用模型",
            children: data.route
              ? modelNames[data.route.selected_model] ||
                data.route.selected_model
              : "不能确定适用模型",
          },
          {
            key: "route",
            label: "路由结果",
            children:
              data.route?.status === "SUPPORTED"
                ? "已有模型支持，仍需经济复核"
                : data.route?.status || "尚未形成",
          },
          {
            key: "inputs",
            label: "模型要求的输入",
            children:
              data.route?.required_inputs?.join("、") || "需先确认模型适用性",
          },
        ]}
      />
      <p>{data.business_explanation || "资本与股东现金路径尚待补充说明"}</p>
      <p>
        业务类型匹配只支持条件模型研究；持续高回报、护城河与分配能力仍需独立核验。
      </p>
      <details>
        <summary>经营与资本约束的既有研究依据</summary>
        <DetailSection
          title="来源绑定经营与资本输入（沿用原准入边界）"
          value={data.economic_evidence}
        />
      </details>
      <h4>最强反证</h4>
      <ul>
        {(data.counter_evidence?.length
          ? data.counter_evidence
          : ["尚无充分反证材料，不能据此确认优势"]
        ).map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      <h4>何时重新判断</h4>
      <ul>
        {(data.invalidation_conditions?.length
          ? data.invalidation_conditions
          : ["业务或资本结构变化后重新核验"]
        ).map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      {!!data.blockers?.length && (
        <Alert
          type="warning"
          message="尚未满足的条件"
          description={data.blockers.join("；")}
        />
      )}
      <details>
        <summary>原始证据与出处</summary>
        {data.evidence_refs?.length ? (
          <ul>
            {data.evidence_refs.map((source, i) => (
              <li key={i}>
                {safeUrl(source.source_url || source.url) ? (
                  <a
                    href={safeUrl(source.source_url || source.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.id || "官方来源"}
                  </a>
                ) : (
                  source.id || "来源定位待核验"
                )}{" "}
                {source.page ? "第" + source.page + "页" : ""} {source.excerpt}{" "}
                {source.sha256 && <code>{source.sha256}</code>}
              </li>
            ))}
          </ul>
        ) : (
          <p>未形成可核验证据，不自动使用通用模型。</p>
        )}
      </details>
    </section>
  );
}
export function CompanyProfilePanel({ symbol }: { symbol: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.companyProfile(symbol, signal),
    [symbol],
  );
  const result = useApi(load);
  if (result.loading) return <p>正在核验企业画像与模型依据…</p>;
  if (result.error || !result.data)
    return (
      <Alert
        type="warning"
        message="企业画像来源暂不可核验"
        description={<Button onClick={result.retry}>重新核验</Button>}
      />
    );
  return <CompanyProfileView data={result.data} symbol={symbol} />;
}
