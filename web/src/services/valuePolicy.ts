export type PolicyRule = {
  action: "entry" | "add" | "reduce" | "exit";
  scenario: "bear" | "base" | "bull";
  value_fraction: string;
  comparison: "LTE" | "GTE";
  rationale: string;
};

export type PolicySelection = {
  effective_from: string;
  effective_through: string;
  rationale: string;
  dividend_coverage_risk: string;
  rules: PolicyRule[];
};

export type PolicyPreview = {
  action: "no_order";
  status: string;
  scope: "ISOLATED_TEST" | "LOCAL_USER_POLICY";
  preview_id: string;
  expires_at: string;
  preparation: {
    status: string;
    blockers: string[];
    existing_research_blockers: string[];
    draft_prices: Record<string, string | null>;
  };
};

export type PolicyRegistration = {
  action: "no_order";
  status: "REGISTERED";
  scope: string;
  preview_id: string;
  conditional_plan: Record<string, unknown>;
  registered_policy: {
    draft: PolicySelection;
    draft_prices: Record<string, string | null>;
    price_scope: "PRIVATE_POLICY_ARITHMETIC_NOT_ADMITTED";
  };
  formal_eligibility: false;
  portfolio_eligibility: null;
  research_approval_changed: false;
  production_published: false;
};

export type PolicyStatus =
  | PolicyRegistration
  | {
      action: "no_order";
      status: "NOT_REGISTERED" | "REVIEW_REQUIRED";
      scope: string;
      detail?: string;
      conditional_plan: null;
    };

export type ValuePolicyTransport = {
  status(symbol: string): Promise<PolicyStatus>;
  preview(symbol: string, selection: PolicySelection): Promise<PolicyPreview>;
  confirm(
    symbol: string,
    body: { preview_id: string; acknowledged: true; note: string },
  ): Promise<PolicyRegistration>;
};

/** Root supplies headers from the existing authenticated session. */
export function createValuePolicyTransport(
  authenticatedHeaders: () => Promise<Record<string, string>>,
): ValuePolicyTransport {
  async function post<T>(symbol: string, operation: string, body: unknown) {
    const response = await fetch(
      `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/${operation}`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          ...(await authenticatedHeaders()),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      },
    );
    const result = await response.json();
    if (!response.ok || result.action !== "no_order")
      throw new Error(result.detail ?? "政策操作未完成，请重新授权或重试");
    return result as T;
  }
  return {
    status: async (symbol) => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/status`,
        {
          credentials: "same-origin",
          headers: await authenticatedHeaders(),
          cache: "no-store",
        },
      );
      const result = await response.json();
      if (!response.ok || result.action !== "no_order")
        throw new Error(result.detail ?? "私人政策读取失败，请重新授权或重试");
      return result as PolicyStatus;
    },
    preview: (symbol, selection) =>
      post<PolicyPreview>(symbol, "preview", selection),
    confirm: (symbol, body) =>
      post<PolicyRegistration>(symbol, "confirm", body),
  };
}

export function fractionFromPercent(percent: string): string {
  if (!/^(?:0|[1-9]\d{0,3})(?:\.\d{1,6})?$/.test(percent))
    throw new Error("比例须为大于零的百分数，最多六位小数");
  const [whole, decimal = ""] = percent.split(".");
  const digits = whole.padStart(3, "0");
  const fraction = `${digits.slice(0, -2)}.${digits.slice(-2)}${decimal}`;
  if (!/[1-9]/.test(fraction)) throw new Error("比例必须大于零");
  return fraction;
}
