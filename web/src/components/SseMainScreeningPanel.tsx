import { useCallback, useState } from "react";
import { useApi } from "../hooks/useApi";

type OfficialSummary = {
  version: "official-identified-financing-sum-v1";
  status: "PARTIAL" | "NOT_AVAILABLE" | "REJECTED";
  known_total: string | null;
  unit: "CNY";
  components: {
    field: string;
    label: string;
    value: string;
    unit: "CNY";
    page: number;
    excerpt: string;
    source_url: string;
    sha256: string;
  }[];
  unknown_components: { field: string; label: string; reason: string }[];
  errors: string[];
  formula: "SUM_EXPLICIT_NONOVERLAPPING_CURRENT_AND_NONCURRENT_FINANCING_BUCKETS";
  complete_debt_verified: false;
  formal_admission: false;
  action: "no_order";
  reason: string;
};

type RowStatus = "CANDIDATE" | "EXCLUDED" | "UNASSESSABLE";
type Params = { offset: number; limit: number; query: string; status: string };
export type ScreenPage = {
  schema_version: "sse-main-screening-v1";
  action: "no_order";
  status: "VERIFIED_SCREENING" | "PARTIAL" | "UNAVAILABLE";
  scope: "SSE_MAIN_A_ONLY";
  quote_date: string | null;
  quote_date_verified: boolean;
  available_at: string | null;
  read_at: string;
  source_status: string;
  counts: {
    universe: number;
    candidate: number;
    excluded: number;
    unassessable: number;
  };
  channel_counts?: Record<string, Record<string, number>>;
  pagination: { offset: number; limit: number; total: number | null };
  items: {
    symbol: string;
    name: string;
    status: RowStatus;
    channels: string[];
    reason: string;
    gaps: string[];
    period: string | null;
    updated_at: string | null;
    financial_crosscheck?: {
      matched_count: number;
      conflict_count: number;
      fields: {
        field: string;
        label: string;
        status: "MATCHED" | "CONFLICT" | "ONE_SOURCE_ONLY" | "NOT_COMPARABLE";
        primary_value: string | null;
        secondary_value: string | null;
        unit: string;
        reason: string;
      }[];
      assurance: "E1_TWO_PROVIDER_COMPARISON_NOT_OFFICIAL_ADMISSION";
    };
    debt_details?: {
      official_summary?: OfficialSummary;
      components: {
        field: string;
        label: string;
        value: string | null;
        unit: string;
        status: string;
        reason: string;
      }[];
      official_components?: {
        field: string;
        label: string;
        value: string | null;
        unit: string;
        page: number;
        excerpt: string;
        source_url: string;
        sha256: string;
      }[];
      official_evidence_count?: number;
      identified_total: string | null;
      complete_debt_verified: false;
      reason: string;
    };
    financial_data?: {
      required_count: number;
      available_count: number;
      verified_count: number;
      missing_count: number;
      fields: {
        field: string;
        label: string;
        status:
          | "AVAILABLE_PENDING_VERIFICATION"
          | "MISSING"
          | "PARTIAL_SCOPE"
          | "VERIFIED"
          | "CONFLICT";
        value: string | null;
        unit: string;
        reason: string;
      }[];
    };
    applicability?: {
      kind: string | null;
      label: string;
      reason: string;
      required_metrics: string[];
      provisional: boolean;
    };
    channel_evaluations: { channel: string; status: string; reason: string }[];
    conditions: {
      field: string;
      value: string | number | null;
      unit: string | null;
      status: string;
      period: string | null;
    }[];
  }[];
  blockers: string[];
  rule_version: string;
  source_refs: { path: string; sha256: string }[];
  task_id?: string;
  coverage_complete: boolean;
};
export type SseMainScreeningPanelProps = {
  load: (params: Params, signal: AbortSignal) => Promise<ScreenPage>;
};
const channels: Record<string, string> = {
  quality: "质量",
  dividend_cash_return: "现金分红回报",
  value: "价值",
  cyclical: "周期",
};
const statuses: Record<string, string> = {
  CANDIDATE: "候选",
  ALL: "全部",
  EXCLUDED: "已排除",
  UNASSESSABLE: "无法判断",
  PASS: "通过初筛",
  FAIL: "未通过",
  NOT_EVALUATED: "未评估",
  REJECTED: "未通过初筛",
  DATA_GAP: "资料或核验未齐",
  CONFLICT: "资料冲突",
  UNSUPPORTED: "普通企业方法不适用",
  BUDGET_EXCLUDED: "已通过初筛（展示数量受限）",
  observed: "来源观察",
  missing: "缺失",
  conflicting: "存在冲突",
};
const fields: Record<string, string> = {
  roe_weighted: "加权净资产收益率",
  gross_margin: "毛利率",
  total_revenue_yoy: "营业收入同比",
  parent_net_income_yoy: "归母净利润同比",
};
const blockerLabels: Record<string, string> = {
  INITIAL_SCREENING_NOT_BUY_ADVICE: "初筛结果不是买入建议",
  PROVIDER_FINANCIAL_NOT_OFFICIAL_ADMISSION:
    "供应商财务数据仅作观察，尚未取得正式事实准入",
  QUOTE_TRADE_DATE_UNVERIFIED: "行情交易日未核验",
  HISTORICAL_SNAPSHOT_NOT_TODAY_REFRESH: "留存历史快照，不是今日重新采集",
  SOURCE_UNAVAILABLE_NOT_ZERO_CANDIDATES: "来源不可用，不等于没有候选公司",
};
const text = (value: string | number | null | undefined) =>
  value == null ? "未知" : String(value);
const object = (v: unknown): v is Record<string, any> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const count = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const nullable = (v: unknown) => v === null || typeof v === "string";
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");

const financialStatuses: Record<string, string> = {
  AVAILABLE_PENDING_VERIFICATION: "已取得，待核验",
  MISSING: "原始数据缺失",
  PARTIAL_SCOPE: "口径/适用性受限",
  VERIFIED: "字段已核验",
  CONFLICT: "数据冲突待核验",
};
function validFinancialData(v: unknown) {
  return (
    object(v) &&
    [
      "required_count",
      "available_count",
      "verified_count",
      "missing_count",
    ].every((k) => count(v[k])) &&
    Array.isArray(v.fields) &&
    v.fields.every(
      (f: unknown) =>
        object(f) &&
        typeof f.field === "string" &&
        typeof f.label === "string" &&
        typeof f.status === "string" &&
        Object.prototype.hasOwnProperty.call(financialStatuses, f.status) &&
        nullable(f.value) &&
        typeof f.unit === "string" &&
        typeof f.reason === "string",
    )
  );
}
function validApplicability(v: unknown) {
  return (
    object(v) &&
    nullable(v.kind) &&
    typeof v.label === "string" &&
    typeof v.reason === "string" &&
    strings(v.required_metrics) &&
    typeof v.provisional === "boolean"
  );
}

const comparisonStatuses: Record<string, string> = {
  MATCHED: "两源一致（非正式核验）",
  CONFLICT: "两源冲突",
  ONE_SOURCE_ONLY: "仅取得一源",
  NOT_COMPARABLE: "口径不具可比性",
};
function validCrosscheck(v: unknown) {
  return (
    object(v) &&
    v.assurance === "E1_TWO_PROVIDER_COMPARISON_NOT_OFFICIAL_ADMISSION" &&
    count(v.matched_count) &&
    count(v.conflict_count) &&
    Array.isArray(v.fields) &&
    v.fields.every(
      (f: unknown) =>
        object(f) &&
        typeof f.field === "string" &&
        typeof f.label === "string" &&
        typeof f.status === "string" &&
        Object.prototype.hasOwnProperty.call(comparisonStatuses, f.status) &&
        nullable(f.primary_value) &&
        nullable(f.secondary_value) &&
        typeof f.unit === "string" &&
        typeof f.reason === "string",
    ) &&
    v.matched_count ===
      v.fields.filter((f: { status: string }) => f.status === "MATCHED")
        .length &&
    v.conflict_count ===
      v.fields.filter((f: { status: string }) => f.status === "CONFLICT").length
  );
}
function officialSourceUrl(v: unknown): v is string {
  if (typeof v !== "string") return false;
  try {
    const url = new URL(v);
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

const financingFields = new Set([
  "short_term_borrowings",
  "short_term_bonds",
  "long_term_borrowings_noncurrent",
  "long_term_borrowings_current",
  "lease_liabilities_noncurrent",
  "lease_liabilities_current",
  "bonds_payable_current",
  "long_term_payables_current",
  "financial_member_deposits",
  "financial_deposits_and_interbank",
]);
const nonempty = (v: unknown): v is string =>
  typeof v === "string" && v.trim().length > 0;
const amount = (v: unknown): v is string =>
  typeof v === "string" && /^\d+(?:\.\d+)?$/.test(v);
function validOfficialSummary(v: unknown): v is OfficialSummary {
  if (
    !object(v) ||
    v.version !== "official-identified-financing-sum-v1" ||
    !["PARTIAL", "NOT_AVAILABLE", "REJECTED"].includes(v.status) ||
    v.unit !== "CNY" ||
    v.complete_debt_verified !== false ||
    v.formal_admission !== false ||
    v.action !== "no_order" ||
    v.formula !==
      "SUM_EXPLICIT_NONOVERLAPPING_CURRENT_AND_NONCURRENT_FINANCING_BUCKETS" ||
    !nonempty(v.reason) ||
    !strings(v.errors) ||
    !v.errors.every(nonempty) ||
    !Array.isArray(v.components) ||
    !Array.isArray(v.unknown_components)
  )
    return false;
  if (
    !v.components.every(
      (c: unknown) =>
        object(c) &&
        financingFields.has(c.field) &&
        nonempty(c.label) &&
        amount(c.value) &&
        c.unit === "CNY" &&
        count(c.page) &&
        c.page > 0 &&
        nonempty(c.excerpt) &&
        officialSourceUrl(c.source_url) &&
        new URL(c.source_url).hostname === "static.cninfo.com.cn" &&
        typeof c.sha256 === "string" &&
        /^[a-fA-F0-9]{64}$/.test(c.sha256),
    )
  )
    return false;
  if (
    !v.unknown_components.every(
      (c: unknown) =>
        object(c) &&
        financingFields.has(c.field) &&
        nonempty(c.label) &&
        nonempty(c.reason),
    )
  )
    return false;
  if (v.status === "REJECTED")
    return v.known_total === null && v.errors.length > 0;
  const fields = [...v.components, ...v.unknown_components].map((c) => c.field);
  if (new Set(fields).size !== fields.length || v.errors.length !== 0)
    return false;
  if (v.status === "NOT_AVAILABLE")
    return v.known_total === null && v.components.length === 0;
  const known = new Set(v.components.map((c) => c.field));
  return (
    amount(v.known_total) &&
    v.components.length > 0 &&
    !(
      known.has("financial_member_deposits") &&
      known.has("financial_deposits_and_interbank")
    )
  );
}

function OfficialFinancing({ summary: s }: { summary: OfficialSummary }) {
  return (
    <section aria-label="官方融资小计">
      <p>
        官方已识别融资小计：{s.status === "PARTIAL" ? s.known_total : "未知"}{" "}
        CNY（{s.status}）
      </p>
      <p>
        PARTIAL仅表示已识别部分，不是完整有息负债；不与供应商小计相加。不代表正式准入。
      </p>
      <p>{s.reason}</p>
      {s.errors.map((e, i) => (
        <p key={i}>拒绝汇总：{e}</p>
      ))}
      <ul>
        {s.components.map((c, i) => (
          <li key={i}>
            {c.label}：{c.value} CNY；原文第{c.page}页<p>{c.excerpt}</p>
            <a href={c.source_url} target="_blank" rel="noopener noreferrer">
              官方原件
            </a>
            <code>{c.sha256}</code>
          </li>
        ))}
      </ul>
      <p>
        未知项（不按零计；未列出也不表示完整核验）：
        {s.unknown_components.length}项
      </p>
      <ul>
        {s.unknown_components.map((c, i) => (
          <li key={i}>
            {c.label}：未知；{c.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

function validDebtDetails(v: unknown) {
  return (
    object(v) &&
    v.complete_debt_verified === false &&
    (v.official_summary === undefined ||
      validOfficialSummary(v.official_summary)) &&
    (v.official_evidence_count === undefined ||
      count(v.official_evidence_count)) &&
    (v.official_components === undefined ||
      (Array.isArray(v.official_components) &&
        v.official_components.every(
          (f: unknown) =>
            object(f) &&
            typeof f.field === "string" &&
            typeof f.label === "string" &&
            nullable(f.value) &&
            typeof f.unit === "string" &&
            count(f.page) &&
            f.page > 0 &&
            typeof f.excerpt === "string" &&
            officialSourceUrl(f.source_url) &&
            typeof f.sha256 === "string" &&
            /^[a-fA-F0-9]{64}$/.test(f.sha256),
        ))) &&
    nullable(v.identified_total) &&
    typeof v.reason === "string" &&
    Array.isArray(v.components) &&
    v.components.every(
      (f: unknown) =>
        object(f) &&
        typeof f.field === "string" &&
        typeof f.label === "string" &&
        nullable(f.value) &&
        typeof f.unit === "string" &&
        typeof f.status === "string" &&
        typeof f.reason === "string",
    )
  );
}

export function validScreenPage(v: unknown): v is ScreenPage {
  if (
    !object(v) ||
    v.schema_version !== "sse-main-screening-v1" ||
    v.action !== "no_order" ||
    v.scope !== "SSE_MAIN_A_ONLY" ||
    !["VERIFIED_SCREENING", "PARTIAL", "UNAVAILABLE"].includes(v.status) ||
    !nullable(v.quote_date) ||
    typeof v.quote_date_verified !== "boolean" ||
    !nullable(v.available_at) ||
    typeof v.read_at !== "string" ||
    typeof v.source_status !== "string" ||
    typeof v.rule_version !== "string" ||
    typeof v.coverage_complete !== "boolean" ||
    (v.task_id !== undefined && typeof v.task_id !== "string") ||
    !strings(v.blockers) ||
    !object(v.counts) ||
    !["universe", "candidate", "excluded", "unassessable"].every((k) =>
      count(v.counts[k]),
    ) ||
    (v.channel_counts !== undefined &&
      (!object(v.channel_counts) ||
        !Object.values(v.channel_counts).every(
          (c) => object(c) && Object.values(c).every(count),
        ))) ||
    !object(v.pagination) ||
    !count(v.pagination.offset) ||
    !count(v.pagination.limit) ||
    v.pagination.limit !== 20 ||
    !(v.pagination.total === null || count(v.pagination.total)) ||
    !Array.isArray(v.source_refs) ||
    !v.source_refs.every(
      (r: unknown) =>
        object(r) &&
        typeof r.path === "string" &&
        typeof r.sha256 === "string" &&
        /^[a-f0-9]{64}$/.test(r.sha256),
    ) ||
    !Array.isArray(v.items) ||
    v.items.length > 20
  )
    return false;
  return v.items.every(
    (r: unknown) =>
      object(r) &&
      typeof r.symbol === "string" &&
      /^[0-9]{6}$/.test(r.symbol) &&
      typeof r.name === "string" &&
      ["CANDIDATE", "EXCLUDED", "UNASSESSABLE"].includes(r.status) &&
      strings(r.channels) &&
      typeof r.reason === "string" &&
      strings(r.gaps) &&
      nullable(r.period) &&
      nullable(r.updated_at) &&
      (r.financial_crosscheck === undefined ||
        validCrosscheck(r.financial_crosscheck)) &&
      (r.debt_details === undefined || validDebtDetails(r.debt_details)) &&
      (r.financial_data === undefined ||
        validFinancialData(r.financial_data)) &&
      (r.applicability === undefined || validApplicability(r.applicability)) &&
      Array.isArray(r.channel_evaluations) &&
      r.channel_evaluations.every(
        (c: unknown) =>
          object(c) &&
          typeof c.channel === "string" &&
          typeof c.status === "string" &&
          typeof c.reason === "string",
      ) &&
      Array.isArray(r.conditions) &&
      r.conditions.every(
        (c: unknown) =>
          object(c) &&
          typeof c.field === "string" &&
          (nullable(c.value) ||
            (typeof c.value === "number" && Number.isFinite(c.value))) &&
          nullable(c.unit) &&
          typeof c.status === "string" &&
          nullable(c.period),
      ),
  );
}

function CrosscheckAndDebt({ row }: { row: ScreenPage["items"][number] }) {
  const comparison = row.financial_crosscheck;
  const debt = row.debt_details;
  if (!comparison && !debt) return null;
  return (
    <section aria-label={row.name + "双源比对与债务明细"}>
      {comparison && (
        <>
          <p>
            已完成实际双源比对
            {comparison.matched_count + comparison.conflict_count}项；冲突
            {comparison.conflict_count}项（一致{comparison.matched_count}项）。
          </p>
          <p>
            仅取得一源
            {
              comparison.fields.filter((f) => f.status === "ONE_SOURCE_ONLY")
                .length
            }
            项；口径不可比
            {
              comparison.fields.filter((f) => f.status === "NOT_COMPARABLE")
                .length
            }
            项，未计入已完成比对。
          </p>
          <p>
            E1
            两供应商观察比对；一致不等于正式核验或官方事实准入，更不是买入依据。
          </p>
          <details>
            <summary>双源原始值与差异（{comparison.fields.length}项）</summary>
            {comparison.fields.length ? (
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>字段</th>
                      <th>主来源值</th>
                      <th>第二来源值</th>
                      <th>状态</th>
                      <th>原因 / 口径</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.fields.map((f, i) => (
                      <tr key={i}>
                        <th scope="row" title={f.field}>
                          {f.label}
                        </th>
                        <td>
                          {text(f.primary_value)} {f.unit}
                        </td>
                        <td>
                          {text(f.secondary_value)} {f.unit}
                        </td>
                        <td>{comparisonStatuses[f.status]}</td>
                        <td>{f.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>未返回逐字段比对，不能据此认定已完成双源验证。</p>
            )}
            <p>范围：仅两供应商观察值比较，不升级已有正式事实核验状态。</p>
          </details>
        </>
      )}
      {debt && (
        <>
          <p>
            已识别借款、租赁等金额：{text(debt.identified_total)}
            （单位与范围见明细；不是完整有息负债）。
          </p>
          <p>{debt.reason}</p>
          {debt.official_summary && (
            <OfficialFinancing summary={debt.official_summary} />
          )}
          <details>
            <summary>债务项目与识别范围（{debt.components.length}项）</summary>
            <p>
              完整有息负债尚未核验。缺项、未知金额不视为零；合计未单列单位，请核对项目单位及来源口径。
            </p>
            <p>供应商已识别项目（小计不代表完整总额）</p>
            {debt.components.length ? (
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>项目</th>
                      <th>原始金额</th>
                      <th>状态</th>
                      <th>原因 / 范围</th>
                    </tr>
                  </thead>
                  <tbody>
                    {debt.components.map((c, i) => (
                      <tr key={i}>
                        <th scope="row" title={c.field}>
                          {c.label}
                        </th>
                        <td>
                          {text(c.value)} {c.unit}
                        </td>
                        <td>
                          {financialStatuses[c.status] ||
                            statuses[c.status] ||
                            c.status}
                        </td>
                        <td>{c.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>未提供债务项目明细，无法判断完整负债范围。</p>
            )}
            {(debt.official_components !== undefined ||
              debt.official_evidence_count !== undefined) && (
              <section aria-label="官方附注构成">
                <p>
                  {debt.official_evidence_count === undefined ? (
                    "官方附注构成（条数未提供）"
                  ) : (
                    <>已补{debt.official_evidence_count}条官方附注构成</>
                  )}
                </p>
                <p>
                  官方构成与供应商已识别小计分开展示，不能相加或替代完整有息负债总额；融资分类仍未完整核验。
                </p>
                {debt.official_components?.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th>官方附注项目</th>
                          <th>原始金额</th>
                          <th>原文页 / 摘录</th>
                          <th>原件</th>
                        </tr>
                      </thead>
                      <tbody>
                        {debt.official_components.map((c, i) => (
                          <tr key={i}>
                            <th scope="row" title={c.field}>
                              {c.label}
                            </th>
                            <td>
                              {text(c.value)} {c.unit}
                            </td>
                            <td>
                              原文第{c.page}页：{c.excerpt}
                            </td>
                            <td>
                              <a
                                href={c.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                官方原件
                              </a>
                              <details>
                                <summary>来源哈希</summary>
                                <code>{c.sha256}</code>
                              </details>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p>未提供官方附注构成明细，不推定金额为零。</p>
                )}
              </section>
            )}
          </details>
        </>
      )}
    </section>
  );
}

function FinancialDiagnostic({ row }: { row: ScreenPage["items"][number] }) {
  const data = row.financial_data;
  const applicability = row.applicability;
  if (!data && !applicability) return null;
  // Classification is supplied by the backend; never infer from issuer names.
  const specialized = applicability?.kind != null && applicability.kind !== "";
  const kinds: Record<string, string> = {
    bank: "银行",
    insurer: "保险",
    broker: "证券",
    financial_group: "金融机构",
    insurance: "保险",
    securities: "证券",
  };
  const kindLabel = applicability?.kind
    ? kinds[applicability.kind.toLowerCase()]
    : undefined;
  return (
    <section aria-label={row.name + "财务数据与适用性"}>
      {applicability && (
        <>
          <p>
            <strong>{applicability.label}</strong>
            {applicability.provisional ? "（初步识别，待核验）" : ""}：
            {applicability.reason}
          </p>
          {specialized && (
            <p>
              需{kindLabel || "对应行业"}
              专用指标：普通企业方法不适用，不套用普通企业9项完成率；这不是公司不好或没有财报。
            </p>
          )}
          {applicability.required_metrics.length > 0 ? (
            <details>
              <summary>
                需核验的{specialized ? "专用" : "适用"}指标（
                {applicability.required_metrics.length}项）
              </summary>
              <ul>
                {applicability.required_metrics.map((metric, i) => (
                  <li key={i}>{metric}</li>
                ))}
              </ul>
            </details>
          ) : specialized ? (
            <p>未提供具体专用指标清单，不能认定已覆盖。</p>
          ) : null}
        </>
      )}
      {data ? (
        <>
          {!specialized && (
            <p>
              已取得{data.available_count}/{data.required_count}项；真正缺
              {data.missing_count}项；已核验{data.verified_count}项。
            </p>
          )}
          <p>
            原始数据取得不等于通过正式事实准入；待核验、口径/适用性受限或冲突不应一概称为没有财报。字段核验也不构成投资批准。
          </p>
          {specialized && (
            <p>以下仅展示返回的原始字段，不作为专用指标覆盖率。</p>
          )}
          <details>
            <summary>逐字段取得与核验状态（{data.fields.length}项）</summary>
            {data.fields.length ? (
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>字段</th>
                      <th>原始值</th>
                      <th>取得 / 核验状态</th>
                      <th>口径与原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.fields.map((field, i) => (
                      <tr key={i}>
                        <th scope="row" title={field.field}>
                          {field.label}
                        </th>
                        <td>
                          {text(field.value)} {field.unit}
                        </td>
                        <td>{financialStatuses[field.status]}</td>
                        <td>{field.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>未返回字段明细，不能推断任何字段为零。</p>
            )}
          </details>
        </>
      ) : (
        <p>未提供财务字段取得与核验计数，数量未知。</p>
      )}
    </section>
  );
}

function ChannelCoverage({ counts }: { counts: ScreenPage["channel_counts"] }) {
  const names = Array.from(
    new Set([...Object.keys(channels), ...Object.keys(counts || {})]),
  );
  return (
    <section aria-label="逐通道初筛覆盖">
      <h4>逐通道初筛覆盖（不是研究完成度）</h4>
      <p>
        资料或核验未齐不等于原始数据缺失，请查看逐字段的取得、缺失与口径状态。金融机构需要金融专用指标；普通企业方法不适用，不是公司不好。公司可出现在多个通道，各通道数量不可相加为公司总数。
      </p>
      {!counts && <p>来源未提供通道计数，不能认定四通道均已评估。</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>通道</th>
              <th>通过初筛（含展示数量受限）</th>
              <th>资料或核验未齐</th>
              <th>普通企业方法不适用</th>
              <th>其他状态</th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const values = counts?.[name];
              const other = Object.entries(values || {}).filter(
                ([status]) =>
                  ![
                    "PASS",
                    "BUDGET_EXCLUDED",
                    "DATA_GAP",
                    "UNSUPPORTED",
                  ].includes(status),
              );
              return (
                <tr key={name}>
                  <th scope="row">{channels[name] || name}</th>
                  <td>
                    {values
                      ? (values.PASS ?? 0) + (values.BUDGET_EXCLUDED ?? 0)
                      : "未提供"}
                  </td>
                  <td>{values ? (values.DATA_GAP ?? 0) : "未提供"}</td>
                  <td>{values ? (values.UNSUPPORTED ?? 0) : "未提供"}</td>
                  <td>
                    {other.length ? (
                      <details>
                        <summary>查看其他状态（{other.length}类）</summary>
                        <ul>
                          {other.map(([status, value]) => (
                            <li key={status} title={status}>
                              {statuses[status] || status}：{value}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : values ? (
                      "无其他已报告状态"
                    ) : (
                      "未提供"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SseMainScreeningPanel({ load }: SseMainScreeningPanelProps) {
  const [params, setParams] = useState<Params>({
    offset: 0,
    limit: 20,
    query: "",
    status: "CANDIDATE",
  });
  const key = JSON.stringify(params);
  const fetchPage = useCallback(
    async (signal: AbortSignal) => {
      const page = await load(params, signal);
      if (
        !validScreenPage(page) ||
        page.pagination.offset !== params.offset ||
        page.pagination.limit !== params.limit
      )
        throw new Error("初筛响应合同或分页不匹配，停止展示");
      return { page, key, loader: load };
    },
    [load, key],
  );
  const { data, loading, error, retry } = useApi(fetchPage);
  // useApi keeps prior data internally. Never expose it under a new request or failure.
  const page =
    !loading && !error && data?.key === key && data.loader === load
      ? data.page
      : undefined;
  const unavailable = page?.status === "UNAVAILABLE";
  const next =
    page &&
    !unavailable &&
    (page.pagination.total === null
      ? page.items.length === 20
      : params.offset + 20 < page.pagination.total);
  return (
    <section
      aria-label="沪市主板初筛"
      style={{ padding: 16, border: "1px solid #d9d9d9", borderRadius: 8 }}
    >
      <h3>沪市主板 A 股初筛股票池</h3>
      <p>
        来源观察为 E1，非正式财务事实；初筛不是买入建议，不生成估值或正式准入。
      </p>
      <p>
        展示数量限制不会丢弃已通过初筛的公司。股票顺序、范围和分页沿用后端，页面不再次筛选。
      </p>
      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <label>
          搜索公司或代码{" "}
          <input
            aria-label="搜索公司或代码"
            value={params.query}
            onChange={(e) =>
              setParams((p) => ({ ...p, query: e.target.value, offset: 0 }))
            }
          />
        </label>
        <label>
          筛选状态{" "}
          <select
            aria-label="筛选状态"
            value={params.status}
            onChange={(e) =>
              setParams((p) => ({ ...p, status: e.target.value, offset: 0 }))
            }
          >
            {["CANDIDATE", "ALL", "EXCLUDED", "UNASSESSABLE"].map((s) => (
              <option key={s} value={s}>
                {statuses[s]}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={retry} disabled={loading}>
          重新读取
        </button>
      </div>
      {error ? (
        <p role="alert">
          来源读取失败，不能判断股票池，不能当作零候选。{error}
        </p>
      ) : !page ? (
        <p role="status">正在读取本次筛选，旧结果暂不展示。</p>
      ) : null}
      {page && (
        <>
          <p>
            行情日期：{text(page.quote_date)}；来源可得时间：
            {text(page.available_at)}；本次读取：{page.read_at}。
          </p>
          {!page.quote_date_verified && (
            <p>行情日期未核验，不能视为当前合格报价。</p>
          )}
          <p>
            来源状态：{page.source_status}；
            {page.status === "PARTIAL"
              ? "部分资料可用"
              : unavailable
                ? "来源不可用"
                : "限定范围初筛已核验"}
            ；
            {page.coverage_complete
              ? "官方名单范围均有初筛记录，不代表资料完整"
              : "官方名单初筛记录覆盖尚未证明完整"}
            。
          </p>
          {!!page.blockers.length && (
            <ul aria-label="来源缺口">
              {page.blockers.map((b, i) => (
                <li key={i} title={blockerLabels[b] ? b : undefined}>
                  {blockerLabels[b] || b}
                </li>
              ))}
            </ul>
          )}
          {unavailable ? (
            <p role="alert">来源不可用，股票池未知，不是零候选。</p>
          ) : (
            <>
              <p>
                股票池 {page.counts.universe} 家；候选 {page.counts.candidate}{" "}
                家；已排除 {page.counts.excluded} 家；无法判断{" "}
                {page.counts.unassessable} 家。
              </p>
              <ChannelCoverage counts={page.channel_counts} />
              {!page.items.length ? (
                <p role="status">
                  {page.pagination.total === 0
                    ? "当前来源与查询条件下为 0 条记录，不代表全市场没有机会。"
                    : "本页没有记录；总数或范围以来源回执为准，不据此认定零候选。"}
                </p>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <caption>本次实际股票池（每页 20 条）</caption>
                    <thead>
                      <tr>
                        <th>公司</th>
                        <th>状态 / 通道</th>
                        <th>初筛理由 / 缺口</th>
                        <th>财务期 / 更新时间</th>
                        <th>条件明细</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((row) => (
                        <tr key={row.symbol}>
                          <td>
                            <a href={`/decisions/${row.symbol}?strategy=value`}>
                              {row.name} · {row.symbol}
                            </a>
                          </td>
                          <td>
                            {statuses[row.status]}
                            <br />
                            {row.channels
                              .map((c) => channels[c] || c)
                              .join("、") || "未提供通道"}
                          </td>
                          <td>
                            <p>{row.reason}</p>
                            <FinancialDiagnostic row={row} />
                            <CrosscheckAndDebt row={row} />
                            {row.gaps.length ? (
                              <>
                                <ul>
                                  {row.gaps.slice(0, 2).map((g, i) => (
                                    <li key={i}>{g}</li>
                                  ))}
                                </ul>
                                {row.gaps.length > 2 && (
                                  <details>
                                    <summary>
                                      其余缺口（{row.gaps.length - 2}条）
                                    </summary>
                                    <ul>
                                      {row.gaps.slice(2).map((g, i) => (
                                        <li key={i}>{g}</li>
                                      ))}
                                    </ul>
                                  </details>
                                )}
                              </>
                            ) : (
                              "未列明缺口（不等于资料完整）"
                            )}
                          </td>
                          <td>
                            财务期：{text(row.period)}
                            <br />
                            更新时间：{text(row.updated_at)}
                          </td>
                          <td>
                            <details>
                              <summary>四通道理由与观察条件</summary>
                              <ul>
                                {row.channel_evaluations.map((c, i) => (
                                  <li key={i}>
                                    {channels[c.channel] || c.channel}：
                                    {statuses[c.status] || c.status}；{c.reason}
                                  </li>
                                ))}
                              </ul>
                              {row.conditions.length ? (
                                <ul>
                                  {row.conditions.map((c, i) => (
                                    <li key={i}>
                                      {fields[c.field] || c.field}：
                                      {text(c.value)} {c.unit || ""}；
                                      {statuses[c.status] || c.status}；财务期{" "}
                                      {text(c.period)}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p>未提供可展示条件，不补造数值。</p>
                              )}
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <nav
                aria-label="股票池分页"
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "center",
                  marginTop: 12,
                }}
              >
                <button
                  type="button"
                  disabled={params.offset === 0}
                  onClick={() =>
                    setParams((p) => ({
                      ...p,
                      offset: Math.max(0, p.offset - 20),
                    }))
                  }
                >
                  上一页
                </button>
                <span>
                  第 {Math.floor(params.offset / 20) + 1} 页；当前查询总数：
                  {text(page.pagination.total)}
                </span>
                <button
                  type="button"
                  disabled={!next}
                  onClick={() =>
                    setParams((p) => ({ ...p, offset: p.offset + 20 }))
                  }
                >
                  下一页
                </button>
              </nav>
            </>
          )}
          <details>
            <summary>规则与来源绑定</summary>
            <p>
              规则版本：{page.rule_version}；任务：{text(page.task_id)}
            </p>
            <ul>
              {page.source_refs.map((ref, i) => (
                <li key={i}>
                  {ref.path}
                  <br />
                  <code>{ref.sha256}</code>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
export default SseMainScreeningPanel;
