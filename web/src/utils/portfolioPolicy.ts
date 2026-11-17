export const policyAmountFields = [
  ["investable_assets_cny", "可投资总资金（元）"],
  ["core_value_budget_cny", "价值池预算（元）"],
  ["hotspot_budget_cny", "热点池预算（元）"],
  ["cash_reserve_cny", "独立现金储备（元）"],
  ["minimum_cash_cny", "最低现金要求（元）"],
  ["dividend_income_goal_cny", "年度股息收入目标（元）"],
  ["time_horizon_years", "投资期限（年）"],
  ["emergency_cash_cny", "应急现金（元，可选）"],
  ["liquidity_needs_cny", "近期流动性需求（元，可选）"],
] as const;

export const policyPercentFields = [
  ["max_single_security_pct", "单票上限（%）"],
  ["max_single_industry_pct", "单行业上限（%）"],
  ["hotspot_single_trade_risk_pct", "热点单笔风险（%）"],
  ["max_drawdown_pct", "可接受回撤（%）"],
  ["max_factor_pct", "同类风险因子上限（%）"],
  ["max_cyclical_exposure_pct", "周期行业上限（%，可选）"],
] as const;

export const policyBooleanFields = [
  ["financing_allowed", "是否允许融资"],
  ["risk_tools_allowed", "是否允许风险工具"],
  ["concentration_allowed", "是否允许集中持仓"],
] as const;

export const policySleeves = ["CORE_VALUE", "HOTSPOT_SATELLITE"] as const;

export const policyRequiredFields = [
  "investable_assets_cny",
  "core_value_budget_cny",
  "hotspot_budget_cny",
  "cash_reserve_cny",
  "minimum_cash_cny",
  "dividend_income_goal_cny",
  "time_horizon_years",
  "max_single_security_pct",
  "max_single_industry_pct",
  "hotspot_single_trade_risk_pct",
  "max_drawdown_pct",
  "max_factor_pct",
  "financing_allowed",
  "risk_tools_allowed",
  "concentration_allowed",
  "effective_date",
  "risk_tolerance",
  "sleeves.CORE_VALUE.cash_cny",
  "sleeves.CORE_VALUE.risk_budget_cny",
  "sleeves.HOTSPOT_SATELLITE.cash_cny",
  "sleeves.HOTSPOT_SATELLITE.risk_budget_cny",
  "sleeves.HOTSPOT_SATELLITE.single_security_risk_cny",
] as const;

export function missingPolicyInputs(policy: Record<string, unknown>): string[] {
  return policyRequiredFields.filter((path) => {
    let value: unknown = policy;
    for (const key of path.split("."))
      value =
        value && typeof value === "object"
          ? (value as Record<string, unknown>)[key]
          : undefined;
    return (
      value == null ||
      value === "" ||
      (path === "risk_tolerance" && value === "UNKNOWN")
    );
  });
}

export function policyFieldLabel(key: string): string {
  const labels: Record<string, string> = {
    ...Object.fromEntries([
      ...policyAmountFields,
      ...policyPercentFields,
      ...policyBooleanFields,
    ]),
    effective_date: "生效日期",
    risk_tolerance: "风险偏好",
    tax_regime: "税务口径",
    restrictions: "其他约束",
    security_attribute_bindings: "证券风险属性来源",
    _confirmed_at: "人工确认时间",
    _record_sha256: "确认记录 SHA256",
    _state_version: "绑定持仓版本",
    action: "执行边界",
  };
  if (key.startsWith("sleeves.")) {
    const [, sleeve, field] = key.split(".");
    return `${sleeve === "CORE_VALUE" ? "价值池" : "热点池"} ${field === "cash_cny" ? "现金（元）" : field === "risk_budget_cny" ? "风险预算（元）" : "单票风险（元）"}`;
  }
  return labels[key] ?? key;
}

export function policyFromForm(
  form: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { action: "no_order" };
  for (const [key] of [...policyAmountFields, ...policyPercentFields]) {
    const value = String(form[key] ?? "").trim();
    if (value) result[key] = value;
  }
  for (const [key] of policyBooleanFields)
    if (typeof form[key] === "boolean") result[key] = form[key];
    else if (form[key] === "ALLOW" || form[key] === "DENY")
      result[key] = form[key] === "ALLOW";
  for (const key of ["effective_date", "risk_tolerance", "tax_regime"])
    if (typeof form[key] === "string" && form[key].trim())
      result[key] = form[key].trim();
  if (typeof form.restrictions === "string" && form.restrictions.trim())
    result.restrictions = form.restrictions
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
  const sleeves = form.sleeves as
    Record<string, Record<string, unknown>> | undefined;
  const pools: Record<string, unknown> = {};
  for (const sleeve of policySleeves) {
    const values: Record<string, string> = {};
    for (const key of [
      "cash_cny",
      "risk_budget_cny",
      "single_security_risk_cny",
    ]) {
      const value = String(sleeves?.[sleeve]?.[key] ?? "").trim();
      if (value) values[key] = value;
    }
    if (Object.keys(values).length) pools[sleeve] = values;
  }
  if (Object.keys(pools).length) result.sleeves = pools;
  const bindings: Record<string, unknown> = {};
  const bindingRows: Record<string, unknown>[] = Array.isArray(
    form.security_bindings,
  )
    ? form.security_bindings
    : [];
  for (const row of bindingRows) {
    const symbol = String(row.symbol ?? "").trim();
    const path = String(row.path ?? "").trim();
    const sha256 = String(row.sha256 ?? "").trim();
    if (!symbol && !path && !sha256) continue;
    if (!/^\d{6}$/.test(symbol) || !path || !/^[a-f0-9]{64}$/.test(sha256))
      throw new Error("证券风险来源需同时填写六位代码、证据路径与 SHA256。");
    if (symbol in bindings) throw new Error("证券风险来源代码不能重复。");
    bindings[symbol] = { path, sha256 };
  }
  if (Object.keys(bindings).length)
    result.security_attribute_bindings = bindings;
  return result;
}

export function policyFormValues(
  policy: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...policy,
    ...Object.fromEntries(
      policyBooleanFields.map(([key]) => [
        key,
        policy[key] === true
          ? "ALLOW"
          : policy[key] === false
            ? "DENY"
            : undefined,
      ]),
    ),
    restrictions: Array.isArray(policy.restrictions)
      ? policy.restrictions.join("\n")
      : undefined,
    security_bindings: Object.entries(
      (policy.security_attribute_bindings as Record<
        string,
        { path: string; sha256: string }
      >) ?? {},
    ).map(([symbol, binding]) => ({ symbol, ...binding })),
  };
}

export function policyReviewRows(
  policy: Record<string, unknown>,
  prefix = "",
): { key: string; label: string; value: string }[] {
  return Object.entries(policy).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value))
      return policyReviewRows(value as Record<string, unknown>, path);
    return [
      {
        key: path,
        label: policyFieldLabel(path),
        value:
          typeof value === "boolean"
            ? value
              ? "允许"
              : "不允许"
            : Array.isArray(value)
              ? value.join("；")
              : String(value ?? "未提供"),
      },
    ];
  });
}

export function policyConfirmationBody(
  revision: number,
  digest: string,
  note: string,
  acknowledged: boolean,
  confirmedAt: string,
) {
  if (!acknowledged || !note.trim() || !/^[a-f0-9]{64}$/.test(digest))
    throw new Error("请逐项核对草稿并填写本人确认说明。");
  return {
    expected_revision: revision,
    prepared_record_sha256: digest,
    confirmation_note: note.trim(),
    confirmed_at: confirmedAt,
  };
}
