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
  applicability_contract?: {
    version: string;
    applicability_conditions: string[];
    refusal_conditions: string[];
    required_economic_inputs: string[];
  };
  missing_inputs?: string[];
  valuation_input_status?: string;
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
  report_period?: string;
  available_at?: string;
}
const refusalNames: Record<string, string> = {
  FINANCIAL_MAIN_BUSINESS_REQUIRES_SPECIALIZED_MODEL:
    "金融主营需专用模型，拒绝通用估值模板",
  UNKNOWN_OR_MIXED_OWN_BUSINESS: "自身主营未知或混合业务尚未拆分",
  OFFICIAL_SOURCE_IDENTITY_OR_HASH_INVALID: "官方原件身份或哈希不匹配",
  SOURCE_NOT_AVAILABLE_AT_CUTOFF: "来源在研究截止时点尚不可得",

  FINANCIAL_BUSINESS_REQUIRES_SPECIALIZED_MODEL:
    "金融业务需要专用模型，拒绝通用估值模板",
  REQUESTED_MODEL_NOT_AUTHORIZED_FOR_PROFILE:
    "请求的模型不适用于已确认的企业类型",
};
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
    !["company-research-profile-v1", "source-company-profile-v1"].includes(
      data.schema_version,
    ) ||
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
          : data.status === "SOURCE_BOUND_ROUTE_ONLY"
            ? "来源与路由已核验，估值输入待补"
            : data.status === "MODEL_NOT_APPLICABLE"
              ? "不适用现有通用模型"
              : "画像尚不可评价"}
      </Tag>
      <p>解释模型选择，不代表企业质量已获确认，也不授予估值或交易资格。</p>
      <Descriptions
        column={1}
        bordered
        size="small"
        styles={{
          label: { width: 160, minWidth: 140, whiteSpace: "nowrap" },
          content: { overflowWrap: "anywhere", wordBreak: "break-word" },
        }}

        items={[
          {
            key: "date",
            label: "画像资料时点",
            children: data.as_of || "尚未核验",
          },
          {
            key: "period",
            label: "财务报告期",
            children: data.report_period || "尚未核验",
          },
          {
            key: "available",
            label: "画像输入可用时间",
            children: data.available_at || "尚未核验；不以报告期代替",
          },
          {
            key: "business",
            label: "企业如何赚钱",
            children:
              display(data.business_model).length > 240 ? (
                <>
                  <span>
                    {display(data.business_model).slice(0, 240)}…（原文节选）
                  </span>
                  <details>
                    <summary>完整主营原文</summary>
                    <p style={{ overflowWrap: "anywhere" }}>
                      {display(data.business_model)}
                    </p>
                  </details>
                </>
              ) : (
                display(data.business_model)
              ),
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
      {data.applicability_contract && (
        <details>
          <summary>已固定的模型适用、拒绝与输入合同</summary>
          <p>合同版本：{data.applicability_contract.version}</p>
          <h4>适用条件</h4>
          <ul>
            {data.applicability_contract.applicability_conditions.map(
              (line) => (
                <li key={line}>{refusalNames[line] || line}</li>
              ),
            )}
          </ul>
          <h4>拒绝条件</h4>
          <ul>
            {data.applicability_contract.refusal_conditions.map((line) => (
              <li key={line}>{refusalNames[line] || line}</li>
            ))}
          </ul>
          <p>
            必需经济输入：
            {data.applicability_contract.required_economic_inputs.join("、")}
          </p>
        </details>
      )}
      {!!data.missing_inputs?.length && (
        <Alert
          type="info"
          message="模型输入尚未完整，不能据此估值"
          description={data.missing_inputs.join("、")}
        />
      )}
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
          description={data.blockers
            .map((code) => refusalNames[code] || code)
            .join("；")}
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
