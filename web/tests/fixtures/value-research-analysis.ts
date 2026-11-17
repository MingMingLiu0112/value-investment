import type { DecisionItem, ValueResearchAnalysis } from "../../src/types/api";

export function analysisFixture(): ValueResearchAnalysis {
  return {
    schema_version: "value-research-analysis-v1",
    symbol: "600887",
    action: "no_order",
    status: "CONDITIONAL_ANALYSIS_VERIFIED",
    arithmetic_complete: true,
    economic_assumptions_reviewed: false,
    action_admitted: false,
    strategy_admitted: false,
    price_comparison_eligible: false,
    valuation_date: "2026-10-11",
    research_as_of: "2026-10-21",
    computed_at: "2026-10-22T10:00:00Z",
    scenarios: [
      {
        scenario: "bear",
        per_share_value: "9.79764118439777680597278298395676515182872214703",
        inputs: { cost_of_equity: "0.09", forecast_roes: ["0.19", "0.18"] },
      },
      {
        scenario: "base",
        per_share_value: "10.098818123456789012345678901234567890",
        inputs: { cost_of_equity: "0.09", forecast_roes: ["0.20", "0.21"] },
      },
      {
        scenario: "bull",
        per_share_value: "11.286452345678901234567890",
        inputs: { terminal_growth: "0.03" },
      },
    ],
    sensitivity: {
      status: "PARTIAL",
      rows: [
        {
          assumption_name: "cost_of_equity",
          field_path: "cost_of_equity",
          basis: "登记的情景端点",
          rationale: "仍需复核经济一致性",
          evidence_refs: [{ id: "test-memo" }],
          points: [
            {
              bound: "bear",
              input_value: "0.1",
              status: "ARITHMETIC_COMPLETE",
              per_share_value: "9.51234567890123456789",
              delta_from_base: "-0.5864724445555544",
            },
            {
              bound: "base",
              input_value: "0.09",
              status: "ARITHMETIC_COMPLETE",
              per_share_value: "10.098818123456789012345678901234567890",
              delta_from_base: "0",
            },
            {
              bound: "bull",
              input_value: "0.08",
              status: "NOT_ASSESSABLE",
              per_share_value: "999999.987654321",
              delta_from_base: null,
            },
          ],
        },
      ],
    },
    counter_evidence: [
      { text: "测试反证：竞争压力仍未排除。", evidence_refs: ["test-memo"] },
    ],
    model_applicability: { blockers: ["经济假设与模型适用范围待复核"] },
    source_bindings: [
      {
        path: "runtime/test-only/source-bound-package.json",
        sha256: "a".repeat(64),
      },
    ],
  };
}

export function analysisDecision(): DecisionItem {
  return {
    id: "600887",
    symbol: "600887",
    strategy: "value",
    price_action_plan: {
      action: "no_order",
      signal_state: "WATCH",
      entry_trigger_price: null,
      invalidation_price: null,
      research_analysis: analysisFixture(),
    },
  };
}
