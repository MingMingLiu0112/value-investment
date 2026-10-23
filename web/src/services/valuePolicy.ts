import type { ValueResearchAnalysis } from "../types/api";

type EvidenceBinding = { path: string; sha256: string };

export type JointCapitalReview = {
  schema_version: "joint-capital-review-v1";
  symbol: string;
  action: "no_order";
  status: "CONDITIONAL_PATH_NOT_APPROVED";
  scope: "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS";
  candidate_binding: EvidenceBinding;
  proposal_binding: EvidenceBinding;
  policy_binding: EvidenceBinding;
  input_descriptor_sha256: string;
  selected_choice: string;
  date_scope: "DATED_CONDITIONAL_MODEL" | "UNDATED_CONDITIONAL_MODEL";
  basis_at: string | null;
  valuation_at: string | null;
  scenarios: {
    scenario: "bear" | "base" | "bull";
    drivers: Record<string, unknown> & {
      years: { year: number; revenue_growth: string; cost_ratio: string }[];
    };
    ledger: Record<string, unknown> & {
      rows: (Record<string, unknown> & { year: number })[];
      forecast_roe: string[];
      cash_funding_status: "PASS" | "FAIL";
      scope: string;
      limitations: string[];
    };
    valuation_per_share: string;
  }[];
};

export type EconomicReviewMaterial = {
  schema_version: "value-economic-review-materials-v1";
  symbol: string;
  action: "no_order";
  status: "PENDING_ECONOMIC_JUDGMENT" | "STRESS_ONLY_NOT_PRIMARY";
  candidate_binding: EvidenceBinding;
  model_context: Record<string, unknown>;
  input_descriptor_sha256: string;
  valuation_artifact_sha256: string;
  assessment_sha256: string;
  materials_sha256: string;
  primary_valuation_usable: false;
  approval_changed: false;
  groups: {
    id: string;
    title: string;
    field_paths: string[];
    verified_observations: string[];
    conditional_assumptions: string[];
    counter_evidence: string[];
    judgment_questions: string[];
    evidence_refs: EvidenceBinding[];
  }[];
  economic_assessment: NonNullable<
    ValueResearchAnalysis["economic_assessment"]
  > & {
    assessment_sha256: string;
    approval_changed: false;
    strategy_admitted: false;
    action_admitted: false;
    review_binding: {
      candidate_binding: EvidenceBinding;
      model_context: Record<string, unknown>;
      package_binding?: EvidenceBinding;
      workbench_binding?: EvidenceBinding;
      review_packet_binding?: EvidenceBinding;
    };
  };
  source_bindings: EvidenceBinding[];
  joint_capital_review?: JointCapitalReview;
};

export type PolicyRule = {
  action: "entry" | "add" | "reduce" | "exit";
  scenario: "bear" | "base" | "bull";
  value_fraction: string;
  comparison: "LTE" | "GTE";
  rationale: string;
};

export type MaterialityReviewHandoff = {
  status: string;
  approval_granted: false;
  reason?: string;
  scan_window?: { scan_from: string; scan_to: string };
  announcements?: unknown[];
  unsigned_response?: unknown;
  recompute_status?: string;
  recompute_reason?: string;
  commands?: {
    prepare_handoff?: string;
    consume_signed_response?: string;
    recompute?: string;
  };
  publication_required?: boolean;
};

export type PolicyHandoffNotReady = {
  action: "no_order";
  status: "NOT_READY";
  symbol: string;
  blockers: string[];
  bindings?: {
    draft: { path: string; sha256: string };
    package: { path: string; sha256: string };
    input_sha256: string;
  };
  verification: { approval_changed: false; research_admitted: false };
  materiality_handoff?: MaterialityReviewHandoff;
  supplemental_materiality_handoff?: MaterialityReviewHandoff;
};

export type PolicyHandoff =
  | PolicyHandoffNotReady
  | {
      action: "no_order";
      status: "EXTERNAL_SIGNATURE_REQUIRED";
      symbol: string;
      candidate_binding: unknown;
      model_context: unknown;
      valuation_artifact_sha256: string;
      review_questions: unknown;
      unsigned_response: unknown;
      authorization: { pinned_root_count: number; status: string };
      steps: { id: string; action: string }[];
      verification: { approval_changed: false; research_admitted: false };
      commands: { draft_preview: string; consume_signed_response: string };
      materiality_handoff?: MaterialityReviewHandoff;
      supplemental_materiality_handoff?: MaterialityReviewHandoff;
      economic_review_materials?: EconomicReviewMaterial;
    };

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const digest = (value: unknown): value is string =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
function binding(value: unknown): value is EvidenceBinding {
  return (
    record(value) &&
    typeof value.path === "string" &&
    value.path.length > 0 &&
    !/^(?:[\\/]|[a-z]+:)/i.test(value.path) &&
    !value.path.split(/[\\/]/).includes("..") &&
    digest(value.sha256)
  );
}
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (record(value))
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, ordered(value[key])]),
    );
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  )
    return value;
  throw new Error("Non-JSON review context");
}
const same = (left: unknown, right: unknown) =>
  JSON.stringify(ordered(left)) === JSON.stringify(ordered(right));

const finiteDecimal = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) &&
  Number.isFinite(Number(value));

export const jointRowFields = [
  "revenue",
  "cost",
  "legacy_pre_tax_profit",
  "legacy_parent_profit",
  "new_operating_profit",
  "new_liquidity_profit",
  "profit",
  "opening_book",
  "roe",
  "retained",
  "dividend",
  "closing_book",
  "net_operating_addition",
  "net_liquidity_addition",
  "maintenance_capex_assumption",
  "cash_open",
  "cash_close",
] as const;
export const jointTerminalFields = [
  "retention",
  "terminal_roe",
  "terminal_growth",
  "terminal_profit",
  "terminal_book",
  "terminal_retention",
  "terminal_net_operating_investment",
  "terminal_new_liquidity_investment",
  "terminal_dividend",
] as const;
const driverFields = [
  "retention",
  "operating_allocation",
  "new_operating_return",
  "new_liquidity_return",
  "parent_cash_conversion",
  "terminal_growth",
  "terminal_profit_scale",
];

/** Source-only presentation validation; never an approval or file-hash verifier. */
function jointCapitalSourceMatches(
  value: unknown,
  symbol: string,
  candidateBinding: unknown,
  descriptor: unknown,
  sources: EvidenceBinding[],
): value is JointCapitalReview {
  try {
    if (!record(value)) return false;
    const review = value;
    if (
      !review ||
      review.schema_version !== "joint-capital-review-v1" ||
      review.symbol !== symbol ||
      review.action !== "no_order" ||
      review.status !== "CONDITIONAL_PATH_NOT_APPROVED" ||
      review.scope !== "RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS" ||
      !binding(review.candidate_binding) ||
      !same(review.candidate_binding, candidateBinding) ||
      !binding(review.proposal_binding) ||
      !binding(review.policy_binding) ||
      ![review.proposal_binding, review.policy_binding].every((ref) =>
        sources.some((source) => same(source, ref)),
      ) ||
      !digest(review.input_descriptor_sha256) ||
      review.input_descriptor_sha256 !== descriptor ||
      typeof review.selected_choice !== "string" ||
      !review.selected_choice.trim() ||
      !(review.date_scope === "UNDATED_CONDITIONAL_MODEL"
        ? review.basis_at === null && review.valuation_at === null
        : review.date_scope === "DATED_CONDITIONAL_MODEL" &&
          [review.basis_at, review.valuation_at].every(
            (value) =>
              typeof value === "string" &&
              /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
              Number.isFinite(Date.parse(value)),
          )) ||
      !Array.isArray(review.scenarios) ||
      review.scenarios.length !== 3
    )
      return false;
    return review.scenarios.every((item, index) => {
      if (
        !record(item) ||
        item.scenario !== ["bear", "base", "bull"][index] ||
        !finiteDecimal(item.valuation_per_share) ||
        !record(item.drivers) ||
        Object.keys(item.drivers).some(
          (key) => key !== "years" && !driverFields.includes(key),
        ) ||
        !driverFields.every((key) =>
          finiteDecimal((item.drivers as Record<string, unknown>)[key]),
        ) ||
        !Array.isArray(item.drivers.years) ||
        item.drivers.years.length !== 5 ||
        !item.drivers.years.every(
          (row, i) =>
            record(row) &&
            row.year === i + 1 &&
            finiteDecimal(row.revenue_growth) &&
            finiteDecimal(row.cost_ratio),
        )
      )
        return false;
      const ledger = item.ledger;
      return (
        record(ledger) &&
        ledger.scope === review.scope &&
        typeof ledger.cash_funding_status === "string" &&
        ["PASS", "FAIL"].includes(ledger.cash_funding_status) &&
        strings(ledger.limitations) &&
        jointTerminalFields.every((key) => finiteDecimal(ledger[key])) &&
        Array.isArray(ledger.forecast_roe) &&
        ledger.forecast_roe.length === 5 &&
        ledger.forecast_roe.every(finiteDecimal) &&
        Array.isArray(ledger.rows) &&
        ledger.rows.length === 5 &&
        ledger.rows.every(
          (row, i) =>
            record(row) &&
            row.year === i + 1 &&
            jointRowFields.every((key) => finiteDecimal(row[key])) &&
            typeof row.cash_funding_status === "string" &&
            ["PASS", "FAIL"].includes(row.cash_funding_status),
        )
      );
    });
  } catch {
    return false;
  }
}

/** Retains the full signing-context check before sharing source-only validation. */
export function jointCapitalReviewMatches(
  handoff: PolicyHandoff,
  symbol: string,
): boolean {
  try {
    if (
      !economicMaterialsMatch(handoff, symbol) ||
      handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED"
    )
      return false;
    const material = handoff.economic_review_materials!;
    return jointCapitalSourceMatches(
      material.joint_capital_review,
      symbol,
      handoff.candidate_binding,
      material.input_descriptor_sha256,
      material.source_bindings,
    );
  } catch {
    return false;
  }
}

/** Public research identity checks; no fabricated signing handoff is involved. */
export function publicJointCapitalReviewMatches(
  analysis: ValueResearchAnalysis,
  symbol: string,
): boolean {
  try {
    const reviewBinding = analysis.review_binding;
    if (
      analysis.schema_version !== "value-research-analysis-v1" ||
      analysis.symbol !== symbol ||
      analysis.action !== "no_order" ||
      analysis.status !== "CONDITIONAL_ANALYSIS_VERIFIED" ||
      analysis.arithmetic_complete !== true ||
      analysis.economic_assumptions_reviewed !== false ||
      analysis.action_admitted !== false ||
      analysis.strategy_admitted !== false ||
      analysis.price_comparison_eligible !== false ||
      !digest(analysis.input_descriptor_sha256) ||
      !record(reviewBinding) ||
      !binding(reviewBinding.candidate_binding) ||
      !record(reviewBinding.model_context) ||
      reviewBinding.model_context.input_descriptor_sha256 !==
        analysis.input_descriptor_sha256 ||
      !Array.isArray(analysis.source_bindings) ||
      !analysis.source_bindings.every(binding) ||
      !analysis.source_bindings.some((source) =>
        same(source, reviewBinding.candidate_binding),
      )
    )
      return false;
    // Reject contradictory public assessment identities if one is supplied.
    const assessment = analysis.economic_assessment;
    if (
      assessment &&
      (assessment.symbol !== symbol ||
        assessment.action !== "no_order" ||
        assessment.input_descriptor_sha256 !==
          analysis.input_descriptor_sha256 ||
        assessment.primary_valuation_usable !== false ||
        assessment.economic_assumptions_reviewed !== false ||
        (assessment.review_binding &&
          (!same(
            assessment.review_binding.candidate_binding,
            reviewBinding.candidate_binding,
          ) ||
            !same(
              assessment.review_binding.model_context,
              reviewBinding.model_context,
            ))))
    )
      return false;
    ordered(reviewBinding.model_context);
    return jointCapitalSourceMatches(
      analysis.joint_capital_review,
      symbol,
      reviewBinding.candidate_binding,
      analysis.input_descriptor_sha256,
      analysis.source_bindings,
    );
  } catch {
    return false;
  }
}

/** Presentation identity check only; source/hash verification stays server-owned. */
export function economicMaterialsMatch(
  handoff: PolicyHandoff,
  symbol: string,
): boolean {
  try {
    if (
      handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED" ||
      handoff.symbol !== symbol ||
      handoff.action !== "no_order" ||
      handoff.verification.approval_changed !== false ||
      handoff.verification.research_admitted !== false
    )
      return false;
    const material = handoff.economic_review_materials;
    if (
      !material ||
      material.schema_version !== "value-economic-review-materials-v1" ||
      material.symbol !== symbol ||
      material.action !== "no_order" ||
      !["PENDING_ECONOMIC_JUDGMENT", "STRESS_ONLY_NOT_PRIMARY"].includes(
        material.status,
      ) ||
      material.primary_valuation_usable !== false ||
      material.approval_changed !== false ||
      !binding(material.candidate_binding) ||
      !binding(handoff.candidate_binding) ||
      !same(material.candidate_binding, handoff.candidate_binding) ||
      !record(material.model_context) ||
      !record(handoff.model_context) ||
      !same(material.model_context, handoff.model_context) ||
      !digest(material.input_descriptor_sha256) ||
      material.input_descriptor_sha256 !==
        handoff.model_context.input_descriptor_sha256 ||
      !digest(material.valuation_artifact_sha256) ||
      material.valuation_artifact_sha256 !==
        handoff.valuation_artifact_sha256 ||
      !digest(material.assessment_sha256) ||
      !digest(material.materials_sha256) ||
      !Array.isArray(material.source_bindings) ||
      !material.source_bindings.length ||
      !material.source_bindings.every(binding)
    )
      return false;
    const assessment = material.economic_assessment;
    if (
      !assessment ||
      assessment.schema_version !== "value-economic-assessment-v1" ||
      assessment.symbol !== symbol ||
      assessment.action !== "no_order" ||
      assessment.primary_valuation_usable !== false ||
      assessment.economic_assumptions_reviewed !== false ||
      assessment.approval_changed !== false ||
      assessment.strategy_admitted !== false ||
      assessment.action_admitted !== false ||
      assessment.assessment_sha256 !== material.assessment_sha256 ||
      assessment.input_descriptor_sha256 !== material.input_descriptor_sha256 ||
      !record(assessment.review_binding) ||
      !same(
        assessment.review_binding.candidate_binding,
        handoff.candidate_binding,
      ) ||
      !same(assessment.review_binding.model_context, handoff.model_context) ||
      !strings(assessment.blockers) ||
      (assessment.model_applicability?.assessment === "STRESS_ONLY") !==
        (material.status === "STRESS_ONLY_NOT_PRIMARY")
    )
      return false;
    const bridge = assessment.accounting_bridge_review;
    if (
      bridge &&
      (bridge.schema_version !== "economic-review-bundle-v1" ||
        bridge.symbol !== symbol ||
        bridge.action !== "no_order" ||
        bridge.primary_valuation_usable !== false ||
        bridge.economic_approval_granted !== false ||
        bridge.input_descriptor_sha256 !== material.input_descriptor_sha256 ||
        !digest(bridge.bundle_sha256) ||
        !strings(bridge.unknown_fields) ||
        !Array.isArray(bridge.source_bindings) ||
        !bridge.source_bindings.every(binding) ||
        !Array.isArray(bridge.bridge_results) ||
        !bridge.bridge_results.every(
          (row) =>
            record(row) &&
            binding(row.source_binding) &&
            record(row.terms) &&
            Object.values(row.terms).every(
              (value) => typeof value === "string",
            ) &&
            typeof row.source_url === "string" &&
            Array.isArray(row.physical_pages) &&
            row.physical_pages.every(
              (page) => Number.isInteger(page) && page > 0,
            ),
        ))
    )
      return false;
    const questions = handoff.review_questions;
    if (
      !Array.isArray(material.groups) ||
      !Array.isArray(questions) ||
      material.groups.length !== questions.length ||
      new Set(material.groups.map((group) => group.id)).size !==
        material.groups.length
    )
      return false;
    return material.groups.every((group, index) => {
      const question = questions[index];
      return (
        record(group) &&
        typeof group.id === "string" &&
        !!group.id &&
        typeof group.title === "string" &&
        !!group.title &&
        record(question) &&
        group.id === question.id &&
        strings(group.field_paths) &&
        same(group.field_paths, question.field_paths) &&
        strings(group.verified_observations) &&
        strings(group.conditional_assumptions) &&
        strings(group.counter_evidence) &&
        strings(group.judgment_questions) &&
        Array.isArray(group.evidence_refs) &&
        group.evidence_refs.every(
          (ref) =>
            binding(ref) &&
            material.source_bindings.some((source) => same(source, ref)),
        )
      );
    });
  } catch {
    return false;
  }
}

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
  handoff?(symbol: string, boundDraft?: boolean): Promise<PolicyHandoff>;
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
    handoff: async (symbol, boundDraft = false) => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}/handoff${boundDraft ? "?bound_draft=true" : ""}`,
        {
          credentials: "same-origin",
          headers: await authenticatedHeaders(),
          cache: "no-store",
        },
      );
      const result = await response.json();
      if (!response.ok || result.action !== "no_order")
        throw new Error(result.detail ?? "审核交接读取失败");
      return result as PolicyHandoff;
    },
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
